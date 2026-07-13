"""
advisor_loop.py — Boucle d'observation multi-symboles en mode ADVISOR ONLY.

Analyse BTC/USDT, ETH/USDT, SOL/USDT, DOGE/USDT toutes les 5 minutes.
Envoie un rapport Telegram toutes les 15 min (cycle 3, 6, 9...).
Alerte immédiate si un signal actionable est détecté (score >= 70).
Watchdog surveille les latences et auto-heal si dégradation.

Usage:
    python advisor_loop.py
    python advisor_loop.py --interval 300   # 5 min (défaut)
    python advisor_loop.py --interval 60    # 1 min (debug)
    python advisor_loop.py --symbols BTC/USDT ETH/USDT
"""

from __future__ import annotations

import argparse
import atexit
import logging
import os
import smtplib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace
from typing import Any, cast

from advisor_runtime_adapters import AdvisorRuntime, load_advisor_runtime

from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)

try:
    from core.authority import get_authority as _get_authority
    from core.authority import init_authority as _init_authority

    _AUTHORITY_AVAILABLE = True
except ImportError:
    _AUTHORITY_AVAILABLE = False

    def _get_authority() -> None:  # type: ignore[misc]
        # ATC: get_authority() must never return None.
        # Import failure = authority absent = execution impossible.
        raise RuntimeError(
            "core.authority indisponible (ImportError) — "
            "exécution sans gouvernance interdite (ATC)"
        )

    def _init_authority(rsm: Any) -> None:  # type: ignore[misc]
        pass


from observability.json_logger import new_trace_id, set_trace_id

try:
    from risk.risk_limits import HardLimitBreached, check_hard_limits
except ImportError:

    class HardLimitBreached(Exception):  # type: ignore[no-redef]
        pass

    def check_hard_limits(**kwargs) -> None:  # type: ignore[misc]
        pass


# IMPORTANT : créer logs/ avant FileHandler
os.makedirs("logs", exist_ok=True)

import requests
from dotenv import load_dotenv

from observability.system_snapshot import (
    AIDecisionSnapshot,
    APIAccountSnapshot,
    BlockStatsAccumulator,
    DecisionState,
    DecisionTraceNode,
    HealthSnapshot,
    InMemorySnapshotProvider,
    MarketSnapshot,
    PipelineStage,
    PipelineStageStatus,
    PortfolioSnapshot,
    ReasonCode,
    build_system_snapshot,
)
from observability.system_snapshot_event_bus import get_snapshot_bus
from observability.system_snapshot_renderers import (
    render_ai_decision_block,
    render_block_stats_block,
    render_health_block,
    render_heartbeat,
    render_pipeline_block,
    render_quant_overview_block,
    render_real_account_block,
)

JSONDict = dict[str, Any]
Candle = dict[str, Any]
Candles = list[Candle]
MTFCandles = dict[str, Candles]
AnalysisResult = dict[str, Any]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stats_dict(value: Any) -> JSONDict:
    return cast(JSONDict, value if isinstance(value, dict) else {})


def _snapshot_list(value: Any) -> list[JSONDict]:
    return cast(list[JSONDict], value if isinstance(value, list) else [])


def _get_exchange_futures(exec_engine: Any) -> Any:
    return getattr(exec_engine, "_exchange_futures", None)


def _get_regret_counts(regret_engine: Any) -> tuple[int, int]:
    records = cast(list[Any], getattr(regret_engine, "_records", []))
    candidates = cast(list[Any], getattr(regret_engine, "_candidates", []))
    return len(records), len(candidates)


def _decision_packet_allows_execution(packet: Any) -> tuple[bool, str]:
    """
    G8 guard slice: prevent execution when DecisionPacket is already terminal.

    Returns:
        (allowed, state_name)
    """
    if packet is None:
        return True, ""

    try:
        _is_terminal = bool(packet.is_terminal())
    except Exception:
        return False, "UNKNOWN"

    if not _is_terminal:
        return True, ""

    _state = getattr(packet, "lifecycle_state", "UNKNOWN")
    _state_name = getattr(_state, "value", str(_state))
    return False, str(_state_name)


def _decision_packet_disagrees(
    legacy_trade_allowed: bool,
    packet: Any,
) -> tuple[bool, bool, str]:
    """
    G8-B instrumentation helper.

    Returns:
        (disagrees, packet_allows, packet_state)
    """
    _packet_allows, _packet_state = _decision_packet_allows_execution(packet)
    return (legacy_trade_allowed != _packet_allows), _packet_allows, _packet_state


def _decision_packet_disagreement_type(
    legacy_trade_allowed: bool,
    packet_allows: bool,
) -> str:
    """
    Classify disagreement direction.

    TYPE_A: legacy=True, packet=False  (safety critical)
    TYPE_B: legacy=False, packet=True  (opportunity/coherence gap)
    NONE  : no disagreement
    """
    if legacy_trade_allowed and not packet_allows:
        return "TYPE_A"
    if (not legacy_trade_allowed) and packet_allows:
        return "TYPE_B"
    return "NONE"


def _metric_key_fragment(value: Any, default: str = "unknown") -> str:
    """Normalize dynamic labels into metric-safe key fragments."""
    text = str(value or "").strip().lower()
    if not text:
        return default
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text)
    normalized = "_".join(part for part in cleaned.split("_") if part)
    return normalized or default


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _brain_score(results: list[Any]) -> tuple[int, str]:
    if not results:
        return 0, "░" * 10
    raw_scores = [
        max(0, min(100, int(_to_float(getattr(r.get("signal"), "score", 0), 0))))
        for r in results
    ]
    avg = int(round(sum(raw_scores) / max(1, len(raw_scores))))
    filled = max(0, min(10, int(round(avg / 10))))
    return avg, ("█" * filled) + ("░" * (10 - filled))


def _decision_diagnostics(
    results: list[Any], min_required_score: float
) -> tuple[DecisionState, ReasonCode, str, str, dict[str, int], str, float]:
    n_actionable = 0
    n_tradable = 0
    blocked: dict[str, int] = {}
    highest_symbol = ""
    highest_score = 0.0

    def _bump(key: str) -> None:
        blocked[key] = blocked.get(key, 0) + 1

    for r in results:
        sig = r.get("signal")
        symbol = str(r.get("symbol", ""))
        score = _to_float(getattr(sig, "score", 0), 0.0)
        if score > highest_score:
            highest_score = score
            highest_symbol = symbol
        actionable = bool(getattr(sig, "actionable", False))
        gate_allowed = bool(getattr(r.get("gate"), "allowed", False))
        if actionable:
            n_actionable += 1
        if bool(r.get("trade_allowed")):
            n_tradable += 1
        if actionable and not bool(r.get("trade_allowed")):
            if not gate_allowed:
                _bump("gate")
            elif not bool(r.get("meta_allowed", True)):
                _bump("meta_strategy")
            elif not bool(getattr(r.get("no_trade_verdict"), "allow", True)):
                _bump("no_trade_layer")
            elif not bool(getattr(r.get("pb_verdict"), "allow", True)):
                _bump("portfolio")
            elif not bool(getattr(r.get("eo_verdict"), "allow", True)):
                _bump("risk")
            elif not bool(getattr(r.get("awareness_state"), "ok", True)):
                _bump("cooldown")
            elif r.get("radar_report") and not bool(
                getattr(r.get("radar_report"), "safe", True)
            ):
                _bump("exchange")
            else:
                _bump("other")

    if n_tradable > 0:
        return (
            DecisionState.ACTIVE,
            ReasonCode.NONE,
            f"{n_tradable} setup(s) tradable",
            "ExecutionEngine",
            blocked,
            highest_symbol,
            highest_score,
        )
    if n_actionable > 0:
        top_reason = max(blocked.items(), key=lambda x: x[1])[0] if blocked else "other"
        reason_code = {
            "gate": ReasonCode.CONFIDENCE_TOO_LOW,
            "meta_strategy": ReasonCode.CONFIDENCE_TOO_LOW,
            "no_trade_layer": ReasonCode.COOLDOWN_ACTIVE,
            "portfolio": ReasonCode.EXPOSURE_LIMIT,
            "risk": ReasonCode.RISK_EXCEEDED,
            "cooldown": ReasonCode.COOLDOWN_ACTIVE,
            "exchange": ReasonCode.EXCHANGE_UNAVAILABLE,
        }.get(top_reason, ReasonCode.RISK_EXCEEDED)
        module = {
            "gate": "RiskManager",
            "meta_strategy": "MetaStrategy",
            "no_trade_layer": "NoTradeLayer",
            "portfolio": "PortfolioBrain",
            "risk": "ExecutiveOverride",
            "cooldown": "Awareness",
            "exchange": "ExchangeMonitor",
        }.get(top_reason, "RiskManager")
        return (
            DecisionState.BLOCKED,
            reason_code,
            f"{top_reason} ({blocked.get(top_reason, 0)}/{n_actionable})",
            module,
            blocked,
            highest_symbol,
            highest_score,
        )
    if highest_score >= min_required_score:
        return (
            DecisionState.WAIT,
            ReasonCode.COOLDOWN_ACTIVE,
            "Setup found but waiting for pipeline confirmation",
            "DecisionPipeline",
            blocked,
            highest_symbol,
            highest_score,
        )
    return (
        DecisionState.WAIT,
        ReasonCode.CONFIDENCE_TOO_LOW,
        "No setup exceeds confidence threshold",
        "SignalScoring",
        blocked,
        highest_symbol,
        highest_score,
    )


def _decision_engine_summary(results: list[Any]) -> tuple[str, str]:
    """Utilitaire testable générique (seuil 66 par défaut, indépendant du seuil
    effectif ATE/RECOVERY). Non utilisé sur le chemin live — voir les appels de
    _decision_diagnostics() dans main() qui, eux, passent le seuil effectif réel."""
    state, _, reason_text, _, _, _, _ = _decision_diagnostics(
        results, min_required_score=66
    )
    return state.value, reason_text


def _display_position_summary(
    virtual_portfolio: Any, pb_health: dict
) -> tuple[int, float]:
    """Positions ouvertes + PnL latent pour l'AFFICHAGE (SystemSnapshot) uniquement.

    pos_manager (via portfolio_brain.portfolio_health()) reste la source des
    contraintes de décision (exposition, corrélation) — jamais modifié ici,
    corriger son entrée changerait le comportement de décision en pleine
    validation scientifique. Ce bug est documenté, gelé, à corriger à la
    calibration (même statut que le trou ExecutionEngine.live, cf CLAUDE.md).

    L'affichage, lui, doit dire la vérité : MexcSimulator est la source qui
    exécute réellement les positions en paper trading (cf RECOVERY.md §
    "Pos: 0 menteur", 2026-07-05) — quand disponible, il prime sur pos_manager
    pour ce qui est montré à l'opérateur.
    """
    if virtual_portfolio is not None:
        try:
            summary = virtual_portfolio.get_open_positions_summary()
            return summary.n_open, summary.unrealized_pnl_usd
        except Exception:
            pass
    return (
        int(pb_health.get("n_positions", 0) or 0),
        _to_float(pb_health.get("open_pnl_usd", 0), 0.0),
    )


def _positions_for_display(virtual_portfolio: Any, pos_manager: Any) -> list[JSONDict]:
    """Positions ouvertes pour les panneaux Telegram (CommandCenterBot).

    Même principe que _display_position_summary : MexcSimulator est la source
    qui exécute réellement les positions en paper trading — quand il est
    disponible, c'est lui qu'on montre. Régression du 2026-07-12 21:00 UTC :
    le rapport programmé affichait "POSITIONS 0 ouverte" (pos_manager vide)
    alors que le ledger MexcSim portait 3 positions ouvertes (BTC/BNB/ETH).
    pos_manager reste le fallback hors paper. Affichage uniquement — ne
    nourrit jamais les contraintes de décision (ADR-0007).
    """
    if virtual_portfolio is not None:
        try:
            summary = virtual_portfolio.get_open_positions_summary()
            now = time.time()
            return [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "entry": p.entry_price,
                    "current": p.current_price,
                    "pnl_usd": p.live_pnl_usd,
                    "unrealized_pnl": p.live_pnl_usd,
                    "pnl_pct": p.live_pnl_pct,
                    "tp": p.tp_price,
                    "sl": p.sl_price,
                    "size_usd": p.qty_usd,
                    "age_min": max(0.0, (now - p.opened_ts) / 60.0),
                }
                for p in summary.positions
            ]
        except Exception:
            pass
    try:
        return _snapshot_list(pos_manager.snapshot())
    except Exception:
        return []


def _replay_base_capital() -> float:
    """Base de capital pour rejouer le dataset canonique (drawdown/sharpe).

    Les trades du dataset sont exécutés et dimensionnés par MexcSimulator sur
    le wallet paper (WALLET_PAPER_CAPITAL, ~ centaines de $) — pas sur les
    $10 alloués Phase F-01 ni sur le solde API réel. Utiliser une autre base
    fabriquerait un drawdown fantaisiste (cf confusion des 3 échelles de
    capital, réconciliation 2026-07-12).
    """
    base = _to_float(getattr(_virtual_portfolio, "_initial_capital", 0.0), 0.0)
    if base > 0:
        return base
    try:
        from infra.wallet_sync import get_wallet_sync

        base = _to_float(get_wallet_sync().get_balance(), 0.0)
    except Exception:
        base = 0.0
    # Dernier recours — même défaut que PhaseKPITracker.__init__
    return base if base > 0 else 100.0


def _replay_clean_trades_kpis(clean_trades: list[dict], base_capital: float) -> Any:
    """Rejoue le dataset canonique dans un PhaseKPITracker jetable.

    Mêmes formules que le tracker live (win rate pnl>0, Sharpe annualisé sur
    rendements journaliers, max DD fraction du pic d'equity) — seule la
    source de données change : les CLOSE MexcSim filtrés CLEAN_DATA_SINCE_V3
    au lieu d'un flux pos_manager qui ne reçoit jamais rien. Zéro nouvelle
    métrique (gel scientifique) ; instance jetable, jamais partagée.
    """
    from capital_deployment.phase_kpi_tracker import PhaseKPITracker, TradeRecord

    events = sorted(clean_trades, key=lambda d: _to_float(d.get("ts", 0.0), 0.0))
    first_ts = _to_float(events[0].get("ts", 0.0), 0.0) or time.time()
    tracker = PhaseKPITracker(
        phase="F-01", initial_capital=base_capital, started_at=first_ts
    )
    for evt in events:
        tracker.record_trade(
            TradeRecord(
                ts=_to_float(evt.get("ts", 0.0), 0.0),
                pnl=_to_float(evt.get("pnl_usd", 0.0), 0.0),
                symbol=str(evt.get("symbol", "?")),
                side=str(evt.get("side", "?")),
                entry_price=0.0,
                exit_price=_to_float(evt.get("exit_price", 0.0), 0.0),
                signed=True,
            )
        )
    return tracker.snapshot()


def _kpi_snapshot_with_canonical_n(kpi_tracker: Any) -> Any:
    """Snapshot KPI pour l'affichage (CommandCenterBot), recalé sur le dataset.

    PhaseKPITracker.record_trade() est alimenté par la fermeture de position
    côté pos_manager — jamais atteint pour les trades exécutés par
    MexcSimulator (même divergence que P2, RECOVERY.md "Pos: 0 menteur").
    Sans correction, le panneau affichait "Trades: 27 | Win Rate: 0%" —
    mensonge constaté en réconciliation 2026-07-12 (réalité : 9W/18L = 33%).
    Ici, total_trades / win_rate / sharpe / max_drawdown / current_drawdown
    sont recalculés en rejouant le dataset canonique (load_clean_trades,
    borne CLEAN_DATA_SINCE_V3) dans les formules du tracker. phase /
    days_elapsed / unsigned_decisions restent ceux du tracker réel.
    Affichage uniquement — le tracker live n'est jamais modifié.
    """
    if kpi_tracker is None:
        return None
    from dataclasses import replace

    from tools.cri_calculator import load_clean_trades

    snap = kpi_tracker.snapshot()
    try:
        clean = load_clean_trades()
    except Exception:
        return snap
    if not clean:
        return replace(snap, total_trades=0)
    try:
        replayed = _replay_clean_trades_kpis(clean, _replay_base_capital())
    except Exception:
        return replace(snap, total_trades=len(clean))
    return replace(
        snap,
        total_trades=len(clean),
        win_rate=replayed.win_rate,
        sharpe=replayed.sharpe,
        max_drawdown=replayed.max_drawdown,
        current_drawdown=replayed.current_drawdown,
    )


load_dotenv(override=True)

P6_SAFE_MODE: bool = os.environ.get("P6_SAFE_MODE", "false").lower() in (
    "true",
    "1",
    "yes",
)

logging.basicConfig(
    level=getattr(logging, os.getenv("V9_LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            "logs/advisor_loop.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    if hasattr(sys.stdout, "reconfigure"):
        cast(Any, sys.stdout).reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("advisor_loop")

# ── Observability integration (non-blocking — graceful if layers not ready) ──
try:
    from errors.error_bus import ErrorCategory, ErrorSeverity, error_bus
    from observability.heartbeat_system import heartbeat_system
    from observability.metrics_bus import metrics_bus
    from system.module_registry import ModulePriority, ModuleStatus, module_registry

    _OBS_AVAILABLE = True
except Exception:
    _OBS_AVAILABLE = False

# P2 Operational Closure — execution constraints + simulation pipeline
import json as _json

try:
    import exchange_constraints.binance_rules as _binance_rules_mod
    from exchange_constraints.order_validator import OrderValidator as _OrderValidator
    from exchange_constraints.rate_limiter import OrderRateLimiter as _OrderRateLimiter
    from execution_simulator.config import mexc_futures_simulator as _mexc_sim_factory
    from execution_simulator.models import MarketSnapshot as _MarketSnapshot
    from execution_simulator.models import OrderIntent as _OrderIntent

    _EXEC_CONSTRAINTS_AVAILABLE = True
except Exception:
    _EXEC_CONSTRAINTS_AVAILABLE = False

# P7 — Circuit breakers (initialisés dans main, None jusqu'alors)
try:
    from supervision.circuit_breaker_robust import ComponentCircuitBreaker as _CBClass

    _CB_AVAILABLE = True
except Exception:
    _CB_AVAILABLE = False
    _CBClass: Any = None

_cb_gate: Any = None
_cb_mistake_memory: Any = None

# S3 — Alertes Telegram + Shadow refusals (fail-silent si scripts/ absent)
try:
    from scripts.telegram_alerts import TelegramAlert as _TelegramAlertCls

    _S3_TELEGRAM_AVAILABLE = True
except Exception:
    _S3_TELEGRAM_AVAILABLE = False
    _TelegramAlertCls: Any = None

try:
    from scripts.shadow_execution import ShadowTracker as _ShadowTrackerCls

    _S3_SHADOW_AVAILABLE = True
except Exception:
    _S3_SHADOW_AVAILABLE = False
    _ShadowTrackerCls: Any = None

_telegram_alert: Any = None
_shadow_s3: Any = None
_virtual_portfolio: Any = None

SYMBOLS_DEFAULT = [
    # ── Tier 1 — Core majors : leaders structurels, vol > $1B/j (8) ──────────
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "TON/USDT",
    # ── Tier 2 — L1 / Layer 2 : infrastructure, vol $50M-$500M/j (12) ────────
    "AVAX/USDT",
    "SUI/USDT",
    "NEAR/USDT",
    "APT/USDT",
    "ARB/USDT",
    "OP/USDT",
    "ATOM/USDT",
    "DOT/USDT",
    "HBAR/USDT",
    "FTM/USDT",
    "SEI/USDT",
    "STX/USDT",
    # ── Tier 3 — DeFi / protocoles : vol $10M-$100M/j (10) ───────────────────
    "LINK/USDT",
    "AAVE/USDT",
    "UNI/USDT",
    "INJ/USDT",
    "LDO/USDT",
    "PENDLE/USDT",
    "ENA/USDT",
    "JUP/USDT",
    "EIGEN/USDT",
    "ONDO/USDT",
    # ── Tier 4 — IA / narratives (8) ──────────────────────────────────────────
    "TAO/USDT",
    "FET/USDT",
    "RENDER/USDT",
    "WLD/USDT",
    "PYTH/USDT",
    "JTO/USDT",
    "W/USDT",
    "STRK/USDT",
    # ── Tier 5 — Meme / high-beta momentum (8) ────────────────────────────────
    "PEPE/USDT",
    "WIF/USDT",
    "BONK/USDT",
    "FLOKI/USDT",
    "SHIB/USDT",
    "NEIRO/USDT",
    "MEME/USDT",
    "HYPE/USDT",
    # ── Tier 6 — Stress / diversification classique (4) ──────────────────────
    "LTC/USDT",
    "BCH/USDT",
    "TIA/USDT",
    "IMX/USDT",
]
# Total : 50 paires — univers perp candidat complet
# Pour découverte dynamique : RANKER_ENABLED=true + RANKER_TOP_N=20 (ou N souhaité)
# Pour scan ponctuel     : python scripts/perp_universe_scan.py --top 100
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_BEHAVIOR_CHAT = os.getenv("TELEGRAM_BEHAVIOR_CHAT_ID", "")
INTEL_TOKEN = os.getenv("INTEL_BOT_TOKEN", "")
INTEL_CHAT = os.getenv("INTEL_BOT_CHAT_ID", "")
INTEL_INTERVAL_S = int(os.getenv("INTEL_REPORT_EVERY_H", "6")) * 3600
# Bot compte réel — STANDBY jusqu'à activation du trading live sur l'API
REAL_BOT_TOKEN = os.getenv("REAL_ACCOUNT_BOT_TOKEN", "")
REAL_BOT_CHAT = os.getenv("REAL_ACCOUNT_CHAT_ID", "")
REAL_BOT_REPORT_EVERY = int(os.getenv("REAL_BOT_REPORT_EVERY", "12"))  # cycles
NOTIFY_EVERY = int(os.getenv("ADVISOR_NOTIFY_EVERY", "3"))
MTF_REFRESH_EVERY = int(os.getenv("ADVISOR_MTF_REFRESH_EVERY", "12"))
ADVISOR_1H_LIMIT = int(os.getenv("ADVISOR_1H_LIMIT", "96"))
ADVISOR_PREWARM_1H = (
    os.getenv(
        "ADVISOR_PREWARM_1H",
        os.getenv("ADVISOR_WARMUP", "true"),
    ).lower()
    == "true"
)
# Prewarm MTF optionnel (4h + 1d) en parallèle du bootstrap.
# Ne s'active que si ADVISOR_PREWARM_1H est aussi actif (même executor).
# Désactivé par défaut — activer avec ADVISOR_PREWARM_MTF=true.
ADVISOR_PREWARM_MTF = (
    os.getenv("ADVISOR_PREWARM_MTF", "false").lower() == "true" and ADVISOR_PREWARM_1H
)
ADVISOR_LIVE_EXECUTION_BOOTSTRAP = (
    os.getenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false").lower() == "true"
)
ADVISOR_BACKGROUND_POSITION_WATCH = (
    os.getenv("ADVISOR_BACKGROUND_POSITION_WATCH", "false").lower() == "true"
)
ADVISOR_DEFER_OPTIONAL_INTEL = (
    os.getenv("ADVISOR_DEFER_OPTIONAL_INTEL", "true").lower() == "true"
)
ADVISOR_DEFER_POST_CYCLE_SERVICES = (
    os.getenv("ADVISOR_DEFER_POST_CYCLE_SERVICES", "true").lower() == "true"
)
ADVISOR_STARTUP_LIGHT = os.getenv("ADVISOR_STARTUP_LIGHT", "false").lower() == "true"
ADVISOR_THREAT_RADAR_EVERY = max(1, int(os.getenv("ADVISOR_THREAT_RADAR_EVERY", "1")))
ADVISOR_CYCLE_BUDGET_SECONDS = float(os.getenv("ADVISOR_CYCLE_BUDGET_SECONDS", "0"))
ADVISOR_LOAD_SHED_CYCLES = max(1, int(os.getenv("ADVISOR_LOAD_SHED_CYCLES", "1")))
# Warmup persistant : thread daemon qui maintient le cache OHLCV chaud entre les cycles.
# Active avec ADVISOR_PERSISTENT_WARMUP=true ; ne remplace pas ADVISOR_PREWARM_1H.
ADVISOR_PERSISTENT_WARMUP = (
    os.getenv("ADVISOR_PERSISTENT_WARMUP", "false").lower() == "true"
)
# Session primer — pre-create the CCXT exchange and call load_markets() in a daemon thread
# launched BEFORE scanner creation so exchange_init + load_markets overlap the full bootstrap.
# Prewarm threads then skip directly to fetch_ohlcv(), saving up to ~650ms from cycle 1.
ADVISOR_SESSION_PRIMER = os.getenv("ADVISOR_SESSION_PRIMER", "true").lower() == "true"


def _session_primer_config() -> JSONDict:
    _futures_exchanges = {"krakenfutures", "binanceusdm", "bybit", "okx"}
    _exch = os.getenv("EXCHANGE_ID", "mexc").lower()
    _default_type = "swap" if _exch in _futures_exchanges else "spot"
    return {
        "enableRateLimit": True,
        "options": {
            "defaultType": _default_type,
            "adjustForTimeDifference": os.getenv(
                "MARKET_SCANNER_ADJUST_TIME", "false"
            ).lower()
            == "true",
            "connectionPoolSize": int(os.getenv("MARKET_SCANNER_POOL_SIZE", "8")),
        },
    }


def _prime_exchange_session(
    exchange_id: str,
    testnet: bool,
    scanner_cls: Any,
    *,
    trace: bool = False,
) -> float:
    """
    Pre-create the shared CCXT exchange and call load_markets() — runs in a daemon
    thread started before scanner creation so that both steps overlap with the
    bootstrap sequence.  Returns elapsed seconds for the timing report.
    """
    import threading as _threading

    t0 = time.perf_counter()
    key = (exchange_id, testnet)
    try:
        import ccxt  # type: ignore[import]

        config = _session_primer_config()
        exchange = getattr(ccxt, exchange_id)(config)
        t_init_ms = (time.perf_counter() - t0) * 1000
        if testnet:
            exchange.set_sandbox_mode(True)

        # Inject into pool before load_markets so concurrent scanner threads
        # block on exchange_call_lock (inside _ensure_markets_loaded) rather
        # than racing to create a second exchange object.
        with scanner_cls._exchange_pool_lock:
            if key not in scanner_cls._exchange_pool:
                scanner_cls._exchange_pool[key] = exchange
                scanner_cls._exchange_call_locks.setdefault(key, _threading.Lock())
                scanner_cls._exchange_markets_ready.setdefault(key, _threading.Event())
                scanner_cls._exchange_created_at[key] = time.monotonic()
                scanner_cls._exchange_generation.setdefault(key, 0)
                injected = True
            else:
                injected = False

        if injected:
            exchange_call_lock = scanner_cls._get_exchange_call_lock(key)
            markets_ready = scanner_cls._get_exchange_markets_ready(key)
            if not markets_ready.is_set():
                with exchange_call_lock:
                    if not markets_ready.is_set():
                        exchange.load_markets()
                        markets_ready.set()

        elapsed = time.perf_counter() - t0
        t_lm_ms = elapsed * 1000 - t_init_ms
        if trace:
            log.info(
                "[SessionPrimer] exchange_init=%.0fms load_markets=%.0fms total=%.0fms",
                t_init_ms,
                t_lm_ms,
                elapsed * 1000,
            )
        return elapsed
    except Exception as exc:
        log.warning("[SessionPrimer] échec (non bloquant): %s", exc)
        return time.perf_counter() - t0


# ── Telegram ──────────────────────────────────────────────────────────────────


def _telegram(text: str) -> None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram erreur: %s", r.text)
    except Exception as exc:
        log.warning("Telegram indisponible: %s", exc)


def _send_email(subject: str, body: str) -> None:
    """Envoie un email de notification via SMTP (config .env)."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    from_addr = os.getenv("EMAIL_FROM_ADDR", "")
    smtp_pass = os.getenv("EMAIL_SMTP_PASS", "")
    to_addr = os.getenv("EMAIL_TO_ADDR", "")
    if not all([smtp_server, from_addr, smtp_pass, to_addr]):
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[Crypto AI] {subject}"
        msg["From"] = from_addr
        msg["To"] = to_addr
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as srv:
            srv.starttls()
            srv.login(from_addr, smtp_pass)
            srv.sendmail(from_addr, [to_addr], msg.as_string())
        log.info("[Email] Envoyé : %s", subject)
    except Exception as exc:
        log.warning("[Email] Échec : %s", exc)


def _write_behavioral_event(event_type: str, data: dict) -> None:
    """Persiste un événement comportemental dans cache/startup/behavioral_events.jsonl."""
    import json as _json
    import time as _time

    try:
        record = {"ts": _time.time(), "event": event_type, **data}
        path = "cache/startup/behavioral_events.jsonl"
        import os as _os

        _os.makedirs("cache/startup", exist_ok=True)
        with open(path, "a", encoding="utf-8") as _f:
            _f.write(_json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _telegram_behavior(text: str) -> None:
    """Canal comportemental — [BEHAVIOR], transitions, REGIME_MISMATCH, BSM."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    chat = TELEGRAM_BEHAVIOR_CHAT or TELEGRAM_CHAT  # fallback canal principal
    if not TELEGRAM_TOKEN or not chat:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram behavior erreur: %s", r.text)
    except Exception as exc:
        log.warning("Telegram behavior indisponible: %s", exc)


def _telegram_real(text: str) -> None:
    """Bot compte réel — solde API, STANDBY/LIVE, statut périodique.

    Canal séparé du bot paper (@QuantCrpto_bot). En standby tant que
    PAPER_TRADING_ENABLED=true. Passe en LIVE quand trading API activé.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    if not REAL_BOT_TOKEN or not REAL_BOT_CHAT:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{REAL_BOT_TOKEN}/sendMessage",
            json={"chat_id": REAL_BOT_CHAT, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.status_code != 200:
            log.debug("[RealBot] Telegram erreur: %s", r.text)
    except Exception as exc:
        log.debug("[RealBot] Indisponible: %s", exc)


def _send_intel(text: str) -> None:
    """Bot Intelligence — résumé 6h en langage naturel (ChiefOfficer briefing).

    Utilise exclusivement INTEL_BOT_TOKEN + INTEL_BOT_CHAT_ID (@rapport_automatique_bot).
    Si non configuré : silencieux (pas de fallback vers @QuantCrpto_bot).
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    token = INTEL_TOKEN
    chat = INTEL_CHAT
    if not token or not chat:
        log.debug(
            "[Intel] INTEL_BOT_TOKEN/INTEL_BOT_CHAT_ID non configurés — briefing ignoré"
        )
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("[Intel] Telegram erreur: %s", r.text)
    except Exception as exc:
        log.warning("[Intel] Telegram indisponible: %s", exc)


# ── Analyse d'un symbole ──────────────────────────────────────────────────────


def analyze_symbol(
    symbol: str,
    scanners: dict[str, dict[str, Any]],
    engine: Any,
    gate: Any,
    advisor: Any,
    shadow: Any,
    watchdog: Any,
    memory: Any,
    cycle: int,
    order_size_usd: float = 50.0,
    meta_engine: Any = None,
    ranker: Any = None,
    open_positions: list[Any] | None = None,
    consecutive_losses: int = 0,
    no_trade_layer: Any = None,
    conviction_engine: Any = None,
    awareness_engine: Any = None,
    dqe: Any = None,
    portfolio_brain: Any = None,
    capital_engine: Any = None,
    mistake_memory: Any = None,
    executive_override: Any = None,
    black_box: Any = None,
    regret_engine: Any = None,
    threat_radar: Any = None,
    # ── V2 modules (optionnels, enrichissement progressif) ──────────────
    v2_data_unifier: Any = None,
    v2_microstructure: Any = None,
    v2_hmm_regime: Any = None,
    v2_regime_predictor: Any = None,
    v2_arbitrator: Any = None,
    v2_feature_store: Any = None,
    v2_learning: Any = None,
    v2_degradation_monitor: Any = None,
    v2_onchain: Any = None,
    v2_flow_tracker: Any = None,
    v2_slippage_predictor: Any = None,
    v2_execution_optimizer: Any = None,
    v2_timing_engine: Any = None,
    meta_learner: Any = None,
    runtime: AdvisorRuntime | None = None,
    sl_factor_override: float | None = None,
    tp_factor_override: float | None = None,
    # ── Sweep detection (optionnel) ─────────────────────────────────────
    sweep_detector: Any = None,
    sweep_outcome_tracker: Any = None,
) -> AnalysisResult:
    _trace_id = new_trace_id()
    set_trace_id(_trace_id)

    # G1 — fail-fast governance: RuntimeAuthority must block the pipeline at entry.
    # If authority says NO, we return an immediate non-actionable decision and
    # skip all downstream work (scans, features, conviction, portfolio, execution).
    try:
        _auth = _get_authority()  # ATC: never None — raises RuntimeError if absent
        if not _auth.can_trade():
            _rsm_state = _auth.rsm_state()
            log.warning(
                "[AUTHORITY] %s short-circuit — RSM:%s",
                symbol,
                _rsm_state,
            )
            _signal_blocked = SimpleNamespace(
                signal="HOLD",
                score=0,
                actionable=False,
                confirmed=False,
                strength=0.0,
                components={},
                regime="unknown",
                timestamp=time.time(),
                side="hold",
            )
            _gate_blocked = SimpleNamespace(
                allowed=False,
                failed=[f"authority:{_rsm_state}"],
            )
            _advice_blocked = SimpleNamespace(
                risk_level="critical",
                confidence="low",
                text=f"RuntimeAuthority blocked trading (state={_rsm_state})",
            )
            return {
                "symbol": symbol,
                "prix": 0.0,
                "signal": _signal_blocked,
                "gate": _gate_blocked,
                "advice": _advice_blocked,
                "explanation": None,
                "shadow": None,
                "personality": None,
                "meta_allowed": False,
                "meta_reason": "AUTHORITY_BLOCKED",
                "conviction": None,
                "no_trade_verdict": None,
                "awareness_state": None,
                "pb_verdict": None,
                "allocation": None,
                "mm_check": None,
                "eo_verdict": None,
                "dq_record": None,
                "trade_allowed": False,
                "blockers": "authority",
                "order_size": 0.0,
                "regime": "unknown",
                "features": {},
                "radar_report": None,
                "ml_decision": None,
                "n_1h": 0,
                "n_4h": 0,
                "n_1d": 0,
                "signal_to_execute": "HOLD",
                "decision_packet": None,
                "trace_id": _trace_id,
                "transition_forecast": None,
            }
    except RuntimeError:
        # GovernanceKernel non initialisé — autorité indisponible.
        # Principe : autorité absente = pas de décision. Fail-closed.
        # En production, init_authority(rsm) est appelé avant le premier cycle.
        # En test, appeler init_authority() explicitement ou utiliser reset_authority().
        log.critical(
            "[AUTHORITY] %s — GovernanceKernel non initialisé. "
            "Pipeline bloqué : autorité indisponible = aucune décision.",
            symbol,
        )
        _signal_no_auth = SimpleNamespace(
            signal="HOLD",
            score=0,
            actionable=False,
            confirmed=False,
            strength=0.0,
            components={},
            regime="unknown",
            timestamp=time.time(),
            side="hold",
        )
        return {
            "symbol": symbol,
            "prix": 0.0,
            "signal": _signal_no_auth,
            "gate": SimpleNamespace(
                allowed=False, failed=["authority:kernel_uninitialized"]
            ),
            "advice": SimpleNamespace(
                risk_level="critical",
                confidence="low",
                text="GovernanceKernel non initialisé — pipeline bloqué",
            ),
            "explanation": None,
            "shadow": None,
            "personality": None,
            "meta_allowed": False,
            "meta_reason": "AUTHORITY_UNINITIALIZED",
            "conviction": None,
            "no_trade_verdict": None,
            "awareness_state": None,
            "pb_verdict": None,
            "allocation": None,
            "mm_check": None,
            "eo_verdict": None,
            "dq_record": None,
            "trade_allowed": False,
            "blockers": "authority:kernel_uninitialized",
            "order_size": 0.0,
            "regime": "unknown",
            "features": {},
            "radar_report": None,
            "ml_decision": None,
            "n_1h": 0,
            "n_4h": 0,
            "n_1d": 0,
            "signal_to_execute": "HOLD",
            "decision_packet": None,
            "trace_id": _trace_id,
            "transition_forecast": None,
        }

    runtime = runtime or load_advisor_runtime()
    MultiTimeframeScanner = runtime.MultiTimeframeScanner
    FeatureEngineer = runtime.FeatureEngineer
    AdvancedRegimeDetector = runtime.AdvancedRegimeDetector
    ConfidenceExplainer = runtime.ConfidenceExplainer

    # Scan 1h
    with watchdog.measure(f"scan_1h_{symbol}"):
        market = scanners["1h"][symbol].scan()
        candles_1h: Candles = cast(
            Candles,
            (
                market.get("history", {}).get(symbol)
                or market.get("candles", {}).get(symbol)
                or []
            ),
        )

    # Bloc synthétique : si le scanner a dû générer des données synthétiques
    # (API OHLCV échouée), on traite cela comme "pas de données" pour éviter
    # qu'une position s'ouvre à un prix fictif (seed=$1000 par défaut).
    if candles_1h and candles_1h[-1].get("source") == "synthetic":
        log.warning(
            "[DataQuality] %s — données synthétiques (fetch OHLCV échoué) → analyse bloquée",
            symbol,
        )
        candles_1h = []

    # Scan MTF (4h + 1d)
    with watchdog.measure(f"scan_mtf_{symbol}"):
        mtf_data = scanners["mtf"][symbol].scan(cycle=cycle)
        mtf_scanner_cls = MultiTimeframeScanner
        mtf_candles: MTFCandles = cast(
            MTFCandles,
            mtf_scanner_cls.merge_base(mtf_data, symbol, candles_1h),
        )

    # ── V2 : Data Unification (enrichit le MarketSnapshot) ───────────────────
    market_snapshot = None
    if v2_data_unifier and candles_1h:
        try:
            market_snapshot = v2_data_unifier.unify(symbol, candles_1h)
        except Exception as _exc_v2:
            log.debug("[V2/DataUnifier] %s skip: %s", symbol, _exc_v2)

    # ── V2 : Microstructure Engine ────────────────────────────────────────────
    micro_report = None
    if v2_microstructure:
        try:
            micro_report = v2_microstructure.analyze(symbol)
        except Exception as _exc_v2:
            log.debug("[V2/Microstructure] %s skip: %s", symbol, _exc_v2)

    # Features + regime
    with watchdog.measure("features"):
        feature_engineer = FeatureEngineer()
        features: JSONDict = cast(
            JSONDict,
            feature_engineer.extract_features(candles_1h) if candles_1h else {},
        )

        # Enrichissement V2 : features microstructure + on-chain
        if market_snapshot:
            features.update(
                {
                    "ob_imbalance": market_snapshot.order_book_imbalance,
                    "funding_rate": market_snapshot.funding_rate,
                    "funding_velocity": market_snapshot.funding_velocity,
                    "liquidation_risk": market_snapshot.liquidation_risk_score,
                    "whale_score": market_snapshot.whale_accumulation_score,
                }
            )
        if micro_report:
            features.update(
                {
                    "micro_pressure": micro_report.directional_pressure,
                    "micro_spread_bps": micro_report.spread_bps,
                    "execution_risk": micro_report.execution_risk,
                }
            )

        # ── Stabilité OHLCV — injectée dans features pour le ConvictionEngine ──
        # Lue depuis last_stability (cache mis à jour par scan() ci-dessus).
        # Zéro appel réseau supplémentaire.
        _stab = scanners["1h"][symbol].last_stability.get(symbol, {})
        if _stab:
            features["stability_regime"] = _stab.get("regime", "unknown")
            features["stability_score"] = float(_stab.get("score", 50))

        try:
            regime_detector = AdvancedRegimeDetector()
            regime = regime_detector.classify(features) if features else "unknown"
        except Exception:
            regime = "unknown"

        # ── V2 : HMM Regime (distribution probabiliste) ──────────────────────
        regime_probs = None
        if v2_hmm_regime and features:
            try:
                regime_probs = v2_hmm_regime.predict(symbol, features)
                # Mise à jour du snapshot avec les probabilités HMM
                if market_snapshot and regime_probs:
                    market_snapshot.regime_bull_prob = regime_probs.bull
                    market_snapshot.regime_bear_prob = regime_probs.bear
                    market_snapshot.regime_chop_prob = regime_probs.chop
                    market_snapshot.regime_volatility_prob = regime_probs.high_vol
                    # Raffinement du régime avec HMM si confiance suffisante
                    if regime_probs.confidence >= 0.50:
                        regime = regime_probs.dominant
            except Exception as _exc_v2:
                log.debug("[V2/HMM] %s skip: %s", symbol, _exc_v2)

        # ── V2 : Regime Transition Predictor ─────────────────────────────────
        transition_forecast = None
        if v2_regime_predictor and regime_probs:
            try:
                transition_forecast = v2_regime_predictor.forecast(
                    symbol, regime_probs, features
                )
                if transition_forecast.crash_risk:
                    log.warning("[V2/RegimePredictor] %s — CRASH RISK détecté", symbol)
            except Exception as _exc_v2:
                log.debug("[V2/RegimePredictor] %s skip: %s", symbol, _exc_v2)

    # ── Sweep Detector — perception de liquidité (après régime, avant signal) ──
    sweep_events: list = []
    if sweep_detector and candles_1h:
        try:
            _sweep_close = float(candles_1h[-1].get("close", 0))
            if sweep_outcome_tracker and _sweep_close > 0:
                sweep_outcome_tracker.tick(symbol, _sweep_close)
            atr_val = float(features.get("atr", features.get("atr_value", 0.0)))
            sweep_events = sweep_detector.detect(
                symbol=symbol,
                candles=candles_1h,
                atr=atr_val,
                regime=regime,
                timeframe="1h",
            )
            if sweep_events:
                best = sweep_events[0]
                # Expose aux features ML
                features["sweep_strength"] = best.sweep_strength
                features["sweep_direction"] = 1.0 if best.direction == "long" else -1.0
                features["sweep_volume_ratio"] = best.volume_ratio
                features["sweep_confidence"] = best.confidence
                # Suivi de l'outcome si tracker branché
                if sweep_outcome_tracker:
                    current_price = float(candles_1h[-1].get("close", 0))
                    for evt in sweep_events:
                        sweep_outcome_tracker.register(evt, current_price, regime)
        except Exception as _exc_sweep:
            log.debug("[SweepDetector] %s skip: %s", symbol, _exc_sweep)

    # MetaLearner — recommandation exit selon régime + volatilité
    ml_decision = None
    if meta_learner:
        volatility = float(features.get("atr_ratio", features.get("volatility", 0.015)))
        ml_decision = meta_learner.find_best(
            {"regime": regime, "volatility": volatility}
        )
        if ml_decision:
            log.debug(
                "[MetaLearner] %s → exit=%s tp=%s sl=%s",
                regime,
                ml_decision.get("exit_type"),
                ml_decision.get("tp"),
                ml_decision.get("sl"),
            )

    # Threat Radar — feed candles + check environnement
    radar_report = None
    if threat_radar and candles_1h:
        threat_radar.feed_candles(symbol, candles_1h)
        radar_report = threat_radar.scan_sync([symbol])
        if radar_report.threats:
            log.info("[ThreatRadar] %s: %s", symbol, radar_report.summary)

    # Normalisation de open_positions (accepte int ou list)
    if open_positions is None:
        open_positions = []
    open_positions_list: list[Any] = open_positions
    open_positions_count = len(open_positions_list)

    # Meilleur Sharpe mémorisé — depuis ranker en priorité, sinon memory store
    memory_sharpe = None
    try:
        if ranker:
            memory_sharpe = ranker.best_sharpe(regime) or None
        if not memory_sharpe:
            stored = memory.load_by_regime(regime, limit=10)
            # Filtrer les entrées sans stratégie nommée (données de test/garbage)
            valid_sharpes = [
                s.get("sharpe", 0)
                for s in stored
                if s.get("strategy")
                and isinstance(s.get("strategy"), dict)
                and s["strategy"].get("name")
                and s.get("sharpe", 0) > 0
            ]
            memory_sharpe = max(valid_sharpes, default=None)
        # Plafond sanity : Sharpe > 5.0 est irréaliste → probablement données de test
        if memory_sharpe and memory_sharpe > 5.0:
            memory_sharpe = None
    except Exception:
        memory_sharpe = None

    # ── Meta-Strategy Engine — personnalité adaptée au régime ─────────────────
    personality = None
    if meta_engine:
        with watchdog.measure("meta_strategy"):
            personality = meta_engine.select(
                regime=regime,
                features=features,
                memory_sharpe=memory_sharpe,
                consecutive_losses=consecutive_losses,
                open_positions=open_positions_count,
                sl_factor_override=sl_factor_override,
                tp_factor_override=tp_factor_override,
            )
        # Ajuster la taille d'ordre selon la personnalité
        order_size_usd = meta_engine.effective_order_size(order_size_usd, personality)

    # Signal
    with watchdog.measure("signal"):
        signal = engine.evaluate(
            symbol, mtf_candles, features=features, memory_sharpe=memory_sharpe
        )
    log.info(
        "[FLOW] %s SIGNAL → %s score=%d actionable=%s",
        symbol,
        signal.signal,
        signal.score,
        signal.actionable,
    )

    # ── DecisionPacket — pipeline souverain parallèle ────────────────────────
    # Dual track : le packet traverse les 4 couches dans l'ordre du lifecycle.
    # Les variables legacy (gate_result, pb_verdict…) pilotent encore les décisions.
    # Ce bloc produit l'audit trail complet + prépare la migration future.
    _dp = None
    try:
        from quant_hedge_ai.agents.execution.live_signal_engine import (
            _to_decision_packet,
        )

        _dp = _to_decision_packet(signal, cycle_id=str(cycle))
        if _dp:
            _dp.metadata["trace_id"] = _trace_id  # I-16: trace_id obligatoire
        if conviction_engine and _dp:
            conviction_engine.enrich_packet(
                _dp,
                candles_1h,
                memory_sharpe,
                personality_name=personality.name if personality else "unknown",
            )
        # Enrichissement sweep — après conviction, avant risk gate
        if _dp and sweep_events:
            try:
                from core.decision_packet import ReasoningCategory, ReasoningSeverity

                for evt in sweep_events:
                    impact = evt.sweep_strength * 0.15  # +0 à +15 pts de confiance
                    _dp.add_reasoning(
                        actor="sweep_detector",
                        message=(
                            f"[SWEEP/{evt.sweep_type.upper()}] {evt.direction.upper()} "
                            f"strength={evt.sweep_strength:.0f} "
                            f"vol×{evt.volume_ratio:.1f} "
                            f"wick×{evt.wick_ratio:.1f}"
                        ),
                        confidence_impact=impact,
                        category=ReasoningCategory.SIGNAL_QUALITY,
                        severity=ReasoningSeverity.INFO,
                    )
                    _dp.metadata["sweep_event"] = evt.to_dict()
            except Exception as _sweep_dp_exc:
                log.debug("[SweepDetector/DP] enrich: %s", _sweep_dp_exc)
    except Exception as _dp_exc:
        log.debug("[DecisionPacket] init/enrich: %s", _dp_exc)
        _dp = None

    # ── Validation Meta-Strategy ───────────────────────────────────────────────
    meta_allowed = True
    meta_reason = "OK"
    if meta_engine and personality:
        meta_allowed, meta_reason = meta_engine.validate_signal(
            signal.signal, signal.score, signal.confirmed, personality
        )

    # Risk gate — protégé par circuit-breaker (P7)
    with watchdog.measure("risk"):
        if _cb_gate is not None:
            gate_result = _cb_gate.call(
                gate.check,
                signal,
                portfolio_drawdown=0.0,
                order_size_usd=order_size_usd,
            )
        else:
            gate_result = gate.check(
                signal, portfolio_drawdown=0.0, order_size_usd=order_size_usd
            )
    if _dp and not _dp.is_terminal() and hasattr(gate, "check_packet"):
        try:
            gate.check_packet(
                _dp, portfolio_drawdown=0.0, order_size_usd=order_size_usd
            )
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] check_packet: %s", _dp_exc)

    # ── TEST MODE — réduire seuil de score pour forcer des trades faibles ──
    min_score_override = float(os.getenv("GATE_MIN_SCORE_OVERRIDE", "0"))
    signal_to_execute = signal.signal  # Default: use original signal
    if (
        min_score_override > 0
        and signal.score >= min_score_override
        and getattr(signal, "regime", "unknown") != "flash_crash"
    ):
        # Override gate pour mode test — permet de trader avec score < 70
        # flash_crash=999 est inviolable même avec override
        gate_result.allowed = True
        # Force BUY signal pour tester (pas HOLD)
        if signal.signal == "HOLD":
            signal_to_execute = "BUY"
            log.info(
                "[GATE_OVERRIDE] Score %.0f >= override %.0f → force BUY (was HOLD)",
                signal.score,
                min_score_override,
            )
        else:
            signal_to_execute = signal.signal

    log.info(
        "[FLOW] %s GATE → %s",
        symbol,
        (
            "OK"
            if gate_result.allowed
            else f"BLOQUÉ({getattr(gate_result, 'reason', '?')})"
        ),
    )

    # Advisor
    with watchdog.measure("advisor"):
        advice = advisor.explain(signal)

    # Confidence explainer — décomposition détaillée du score
    explanation = ConfidenceExplainer().explain(signal)

    prix = float(candles_1h[-1].get("close", 0)) if candles_1h else 0.0

    # ── Self-Awareness check ──────────────────────────────────────────────────
    awareness_state = None
    if awareness_engine:
        awareness_state = awareness_engine.evaluate()
        if not awareness_engine.is_safe_to_trade():
            log.warning(
                "[SelfAwareness] Trading bloqué — niveau: %s",
                awareness_state.level.name,
            )

    # ── Conviction Engine ─────────────────────────────────────────────────────
    conviction = None
    if conviction_engine:
        with watchdog.measure("conviction"):
            conviction = conviction_engine.evaluate(
                signal,
                features,
                candles_1h,
                regime,
                memory_sharpe,
                personality_name=personality.name if personality else "unknown",
            )
            if conviction.blocks_trade():
                log.info(
                    "[Conviction] Trade bloqué — conviction minimale (score=%.0f)",
                    conviction.score,
                )

    # ── No-Trade Intelligence check ───────────────────────────────────────────
    no_trade_verdict = None
    if no_trade_layer and signal.actionable:
        with watchdog.measure("no_trade"):
            no_trade_verdict = no_trade_layer.check(
                signal,
                candles_1h,
                features,
                regime,
                personality_name=personality.name if personality else "unknown",
            )

    # ── Mistake Memory — vérification avant trade (protégée CB P7) ──────────────
    mm_check = None
    if mistake_memory and signal.actionable:
        with watchdog.measure("mistake_memory"):
            if _cb_mistake_memory is not None:
                mm_check = _cb_mistake_memory.call(
                    mistake_memory.check_before_trade,
                    symbol=symbol,
                    signal=signal.signal,
                    score=signal.score,
                    regime=regime,
                    features=features,
                    consecutive_losses=consecutive_losses,
                    conviction_level=conviction.level.value if conviction else "medium",
                    signal_age_sec=time.time() - signal.timestamp,
                )
            else:
                mm_check = mistake_memory.check_before_trade(
                    symbol=symbol,
                    signal=signal.signal,
                    score=signal.score,
                    regime=regime,
                    features=features,
                    consecutive_losses=consecutive_losses,
                    conviction_level=conviction.level.value if conviction else "medium",
                    signal_age_sec=time.time() - signal.timestamp,
                )
            if mm_check.blocked:
                log.info("[MistakeMemory] Trade bloqué: %s", mm_check.reason)

    # ── Portfolio Brain — risque portefeuille global ──────────────────────────
    # Portfolio check sur la taille meta-ajustée (sans conviction) pour être cohérent
    # avec l'exécution réelle (effective_size ligne ~3571 n'applique pas conviction).
    # Conviction réduit la taille uniquement dans shadow_execute (eff_size ligne ~1247).
    _pb_size = order_size_usd
    pb_verdict = None
    if portfolio_brain and signal.actionable:
        with watchdog.measure("portfolio_brain"):
            pb_verdict = portfolio_brain.check_new_trade(
                symbol=symbol,
                action=signal.signal,
                size_usd=_pb_size,
                regime=regime,
                open_positions=open_positions_list,
                leverage=1,
                conviction_score=conviction.score if conviction else 50.0,
            )
            if not pb_verdict.allowed:
                log.info("[PortfolioBrain] Bloqué: %s", pb_verdict.reason)
            elif pb_verdict.size_factor < 1.0:
                order_size_usd = order_size_usd * pb_verdict.size_factor
                log.debug(
                    "[PortfolioBrain] Taille réduite ×%.2f → $%.2f",
                    pb_verdict.size_factor,
                    order_size_usd,
                )
    if _dp and _dp.lifecycle_state.value == "RISK_EVALUATED" and portfolio_brain:
        try:
            portfolio_brain.approve_packet(_dp, open_positions_list, order_size_usd)
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] approve_packet: %s", _dp_exc)

    # ── Capital Allocation Engine — taille optimale Kelly/EV/vol ─────────────
    allocation = None
    if (
        capital_engine
        and signal.actionable
        and (pb_verdict is None or pb_verdict.allowed)
    ):
        with watchdog.measure("capital_engine"):
            # Récupère les stats depuis le ranker si disponible
            cae_stats: JSONDict = {}
            if ranker:
                strategy_key = symbol.replace("/", "_").lower()
                cae_stats = capital_engine.stats_from_ranker(
                    ranker, strategy_key, regime
                )
            volatility = float(
                features.get("atr_ratio", features.get("volatility", 0.015))
            )
            allocation = capital_engine.allocate(
                base_size_usd=order_size_usd,
                win_rate=cae_stats.get("win_rate", 0.50),
                avg_win_pct=cae_stats.get("avg_win_pct", 0.03),
                avg_loss_pct=cae_stats.get("avg_loss_pct", 0.02),
                volatility=volatility,
                conviction_factor=conviction.size_factor if conviction else 1.0,
                regime=regime,
                leverage=1,
                n_trades_history=cae_stats.get("n_trades_history", 0),
            )
            if allocation.size_usd > 0:
                order_size_usd = allocation.size_usd
                log.debug(
                    "[CAE] Taille allouée: $%.2f | kelly=%.4f ev=%.5f",
                    allocation.size_usd,
                    allocation.kelly_fraction,
                    allocation.ev_score,
                )
            else:
                log.info("[CAE] Allocation refusée: %s", allocation.reason)

    if _dp and _dp.lifecycle_state.value == "APPROVED":
        try:
            from core.decision_packet import (
                DecisionState,
                ReasoningCategory,
                ReasoningSeverity,
            )

            _dp.add_agent("capital_engine")
            if allocation and allocation.size_usd > 0:
                _dp.features["os_size_usd"] = round(allocation.size_usd, 2)
                _dp.features["os_kelly"] = getattr(allocation, "kelly_fraction", 0.0)
                _dp.add_reasoning(
                    "capital_engine",
                    f"Kelly={getattr(allocation,'kelly_fraction',0):.3f}"
                    f" ev={getattr(allocation,'ev_score',0):.4f}"
                    f" → ${allocation.size_usd:.2f}",
                    confidence_impact=0.0,
                    category=ReasoningCategory.SIZING,
                )
                _dp.transition_to(
                    DecisionState.EXECUTION_PENDING,
                    "capital_engine",
                    f"Sizing: ${allocation.size_usd:.2f}",
                )
            else:
                reason = (
                    getattr(allocation, "reason", "allocation refusée")
                    if allocation is not None
                    else (
                        "capital_engine non initialisé"
                        if not capital_engine
                        else (
                            "signal non actionable"
                            if not signal.actionable
                            else "portfolio_brain bloqué"
                        )
                    )
                )
                _dp.add_reasoning(
                    "capital_engine",
                    f"Sizing refusé: {reason}",
                    confidence_impact=-20.0,
                    category=ReasoningCategory.SIZING,
                    severity=ReasoningSeverity.WARNING,
                )
                _dp.reject("capital_engine", f"Sizing refusé: {reason}")
        except Exception as _dp_exc:
            log.debug("[DecisionPacket] sizing: %s", _dp_exc)

    # ── Executive Override — commandement suprême ─────────────────────────────
    eo_verdict = None
    if executive_override and signal.actionable:
        eo_verdict = executive_override.check_trade(
            size_usd=order_size_usd,
            conviction_score=conviction.score if conviction else 50.0,
        )
        if not eo_verdict.allowed:
            log.warning("[ExecutiveOverride] VETO: %s", eo_verdict.reason)
        elif eo_verdict.size_factor < 1.0:
            order_size_usd = order_size_usd * eo_verdict.size_factor
            log.info(
                "[ExecutiveOverride] %s — taille x%.0f%%",
                eo_verdict.level.name,
                eo_verdict.size_factor * 100,
            )

    # ── V2 : Decision Arbitrator — consensus pondéré multi-agents ────────────
    arbitration_result = None
    if v2_arbitrator and signal.actionable:
        try:
            from quant_hedge_ai.agents.intelligence.decision_arbitrator import AgentVote

            arb_votes = [
                AgentVote(
                    "global_risk_gate",
                    1.0 if gate_result.allowed else -1.0,
                    veto=not gate_result.allowed,
                ),
                AgentVote(
                    "conviction_engine",
                    ((conviction.score / 100.0) * 2 - 1) if conviction else 0.0,
                ),
                AgentVote(
                    "no_trade_layer",
                    (
                        0.0
                        if no_trade_verdict is None
                        else (1.0 if bool(no_trade_verdict) else -0.6)
                    ),
                ),
                AgentVote(
                    "portfolio_brain",
                    0.0 if pb_verdict is None else (1.0 if bool(pb_verdict) else -0.8),
                ),
                AgentVote("meta_strategy", 0.8 if meta_allowed else -0.5),
                AgentVote(
                    "mistake_memory",
                    0.0 if mm_check is None else (0.5 if bool(mm_check) else -0.7),
                ),
                AgentVote(
                    "executive_override",
                    0.0 if eo_verdict is None else (1.0 if bool(eo_verdict) else -1.0),
                    veto=(eo_verdict is not None and not bool(eo_verdict)),
                ),
                AgentVote(
                    "threat_radar",
                    (
                        0.0
                        if radar_report is None
                        else (0.5 if radar_report.trade_allowed else -0.8)
                    ),
                ),
            ]
            # Enrichir avec signaux V2
            if micro_report:
                side_pressure = (
                    micro_report.directional_pressure
                    if signal.signal == "long"
                    else -micro_report.directional_pressure
                )
                arb_votes.append(AgentVote("microstructure", side_pressure * 0.7))
            if regime_probs:
                if signal.signal == "long":
                    regime_vote = regime_probs.bull - regime_probs.bear
                else:
                    regime_vote = regime_probs.bear - regime_probs.bull
                arb_votes.append(AgentVote("hmm_regime", regime_vote))
            if transition_forecast and transition_forecast.crash_risk:
                arb_votes.append(AgentVote("hmm_regime", -0.9, veto=True))

            arbitration_result = v2_arbitrator.arbitrate(arb_votes)
            log.debug("[V2/Arbitrator] %s: %s", symbol, arbitration_result.reasoning)
        except Exception as _exc_v2:
            log.debug("[V2/Arbitrator] skip: %s", _exc_v2)

    # ── V2 : Timing Engine — attendre le bon moment d'exécution ──────────────
    timing_signal = None
    if (
        v2_timing_engine
        and signal.actionable
        and (arbitration_result is None or arbitration_result.size_multiplier > 0)
    ):
        try:
            spread = micro_report.spread_bps if micro_report else 5.0
            imbalance = micro_report.imbalance if micro_report else 0.0
            atr = float(features.get("atr_pct", features.get("atr_ratio", 0.01)))
            urgency = float(signal.score) / 100.0 if hasattr(signal, "score") else 0.5
            timing_signal = v2_timing_engine.evaluate(
                symbol, signal.signal, spread, imbalance, atr, urgency
            )
            if not timing_signal.execute_now:
                log.debug("[V2/Timing] %s — attendre: %s", symbol, timing_signal.reason)
        except Exception as _exc_v2:
            log.debug("[V2/Timing] skip: %s", _exc_v2)

    # Décision finale d'autorisation — I-14 : fail-closed
    # Règle : agent=None → non configuré (intentionnel → pass)
    #         agent configuré + résultat None → exception capturée → BLOQUÉ
    # Un agent qui plante ne produit jamais un BUY.
    _awareness_ok = awareness_engine is None or awareness_engine.is_safe_to_trade()
    _conviction_ok = conviction_engine is None or (
        conviction is not None and not conviction.blocks_trade()
    )
    _notrade_ok = (
        no_trade_layer is None
        or not signal.actionable
        or (no_trade_verdict is not None and bool(no_trade_verdict))
    )
    _pb_ok = (
        portfolio_brain is None
        or not signal.actionable
        or (pb_verdict is not None and pb_verdict.allowed)
    )
    _cae_ok = (
        capital_engine is None
        or not signal.actionable
        or (
            pb_verdict is not None and not pb_verdict.allowed
        )  # pb bloqué → cae skipped
        or (allocation is not None and bool(allocation))
    )
    _mm_ok = (
        mistake_memory is None
        or not signal.actionable
        or (mm_check is not None and bool(mm_check))
    )
    _eo_ok = (
        executive_override is None
        or not signal.actionable
        or (eo_verdict is not None and bool(eo_verdict))
    )
    _radar_ok = (
        threat_radar is None
        or not candles_1h
        or (radar_report is not None and radar_report.trade_allowed)
    )

    # ── G1: Governance authority — la RSM est le gouverneur ─────────────────
    # _authority_ok n'est PAS bypassé par FORCE_TEST_EXECUTION.
    # C'est le seul check qui ne peut pas être outrepassé par une variable d'env.
    _authority_ok = True
    try:
        _auth = _get_authority()  # ATC: never None
        _authority_ok = _auth.can_trade()
        if not _authority_ok:
            log.warning("[AUTHORITY] %s bloqué — RSM:%s", symbol, _auth.rsm_state())
    except RuntimeError:
        # ATC: RuntimeError = autorité absente = pas de décision (fail-closed).
        _authority_ok = False

    # ── FORCE_TEST_EXECUTION — bypass all checks except gate/signal ──
    force_test_execution = os.getenv("FORCE_TEST_EXECUTION", "false").lower() == "true"
    if (
        force_test_execution
        and gate_result.allowed
        and signal.score >= min_score_override
    ):
        meta_allowed = (
            True  # bypass meta-strategy (sinon MEAN_REVERSION exige score>=72)
        )
        _awareness_ok = True
        _conviction_ok = True
        _notrade_ok = True
        _pb_ok = True
        _cae_ok = True
        _mm_ok = True
        _eo_ok = True
        _radar_ok = True
        # Restaure la taille d'ordre si elle a ete reduite a 0 par
        # meta_strategy (TRADING BLOQUE) ou conviction (size_factor=0).
        # Sinon les logs affichent $0.00 et l'execution_engine fallback
        # sur min_notional Binance (~5$) au lieu d'EXEC_MAX_ORDER_USD.
        if order_size_usd <= 0:
            order_size_usd = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))
        log.info(
            "[FORCE_TEST_EXECUTION] Bypass all layers — signal only (size=$%.2f)",
            order_size_usd,
        )

    # V2 arbitration : si disponible, son verdict remplace la logique dispersée
    if arbitration_result is not None:
        from quant_hedge_ai.agents.intelligence.decision_arbitrator import (
            ArbitrationDecision,
        )

        _arb_ok = arbitration_result.decision not in (
            ArbitrationDecision.REJECT,
            ArbitrationDecision.EMERGENCY_EXIT,
        )
        if arbitration_result.size_multiplier > 0 and _arb_ok:
            order_size_usd = order_size_usd * arbitration_result.size_multiplier
    else:
        _arb_ok = True
    trade_allowed = (
        _authority_ok
        and meta_allowed
        and gate_result.allowed
        and _awareness_ok
        and _conviction_ok
        and _notrade_ok
        and _pb_ok
        and _cae_ok
        and _mm_ok
        and _eo_ok
        and _radar_ok
        and _arb_ok
    )
    if signal.actionable:
        _flow_blockers = ", ".join(
            filter(
                None,
                [
                    "authority" if not _authority_ok else "",
                    "meta" if not meta_allowed else "",
                    "gate" if not gate_result.allowed else "",
                    "awareness" if not _awareness_ok else "",
                    "conviction" if not _conviction_ok else "",
                    "no_trade" if not _notrade_ok else "",
                    "portfolio" if not _pb_ok else "",
                    "cae" if not _cae_ok else "",
                    "mistake_mem" if not _mm_ok else "",
                    "exec_override" if not _eo_ok else "",
                    "radar" if not _radar_ok else "",
                    "arbitrator" if not _arb_ok else "",
                ],
            )
        )
        _alloc_str = (
            f" alloc=${allocation.size_usd:.0f}"
            if allocation and allocation.size_usd > 0
            else ""
        )
        log.info(
            "[FLOW] %s VERDICT → %s%s%s",
            symbol,
            "TRADE_OK" if trade_allowed else "BLOQUÉ",
            _alloc_str,
            f" [{_flow_blockers}]" if _flow_blockers else "",
        )

    # ── G8-D — Synchronisation DecisionPacket ↔ décision pipeline ───────────────
    # Si le pipeline refuse (trade_allowed=False) et que le packet est encore
    # actionable, le rejeter explicitement. Cela élimine les divergences TYPE-B
    # (legacy=False, packet=True) avant le retour de analyze_symbol(), garantissant
    # que le packet reflète fidèlement le verdict complet du pipeline.
    # Invariant : après cette ligne, tout packet non-terminal EST la décision.
    if not trade_allowed and _dp and not _dp.is_terminal():
        try:
            _g8d_blockers = (
                _flow_blockers  # défini uniquement si signal.actionable
                if signal.actionable
                else "signal_non_actionable"
            )
            _dp.reject(
                "pipeline_g8d",
                f"trade_allowed=False [{_g8d_blockers or 'unknown'}]",
            )
        except Exception:
            pass

    # ── Regret Engine — enregistre les refus potentiellement rentables ─────────
    if regret_engine and signal.actionable and not trade_allowed:
        refused_by_list: list[str] = []
        if not _eo_ok:
            refused_by_list.append("executive_override")
        if not _mm_ok:
            refused_by_list.append("mistake_memory")
        if not _pb_ok:
            refused_by_list.append("portfolio_brain")
        if not _conviction_ok:
            refused_by_list.append("conviction")
        if not _notrade_ok:
            refused_by_list.append("no_trade")
        if not _awareness_ok:
            refused_by_list.append("awareness")
        if not meta_allowed:
            refused_by_list.append("meta_strategy")
        if not gate_result.allowed:
            refused_by_list.append("gate")
        if not _radar_ok:
            refused_by_list.append("threat_radar")
        regret_engine.register_candidate(
            symbol=symbol,
            signal=signal.signal,
            score=signal.score,
            regime=regime,
            price=prix,
            refused_by=refused_by_list,
            cycle=cycle,
            conviction_level=conviction.level.value if conviction else "medium",
        )

        # S3 — log gate refusal pour analyse coût gate
        if _shadow_s3 is not None and not gate_result.allowed:
            try:
                _shadow_s3.log_refused(
                    symbol=symbol,
                    side=signal.signal,
                    score=float(signal.score),
                    regime=regime,
                    failed_checks=list(gate_result.failed),
                    price=prix,
                    cycle_id=str(cycle),
                )
            except Exception:
                pass

    # ── Decision Quality — évaluation avant exécution ─────────────────────────
    dq_record = None
    if dqe and signal.actionable:
        dq_record = dqe.evaluate_decision(
            signal,
            conviction_score=conviction.score if conviction else 50.0,
            conviction_level=conviction.level.value if conviction else "medium",
            regime=regime,
            personality_name=personality.name if personality else "unknown",
            no_trade_score=(
                no_trade_verdict.rejection_score if no_trade_verdict else 0.0
            ),
            meta_allowed=meta_allowed,
            gate_allowed=gate_result.allowed,
        )

    # Shadow execution — simule l'ordre sans l'envoyer
    # G0 — Un trade sans trace_id valide ne s'exécute pas.
    # _dp doit exister et porter trace_id dans ses metadata.
    # Sans trace_id : aucune reconstruction de cycle possible, packet rejeté.
    shadow_trade = None
    if signal.actionable and trade_allowed:
        # G8-C (étape 1) — packet.is_actionable() comme garde secondaire.
        # Si _dp existe et est terminal (REJECTED, VETOED…), shadow est bloqué.
        # Ceci avance la migration : DecisionPacket co-souverain avant le legacy boolean.
        _dp_actionable = _dp.is_actionable() if _dp else True
        _shadow_trace_ok = bool(_dp and _dp.metadata.get("trace_id"))
        if not _dp_actionable:
            log.warning(
                "[G8-C] %s — shadow bloqué : packet non-actionable (state=%s)",
                symbol,
                getattr(getattr(_dp, "lifecycle_state", None), "value", "?"),
            )
        elif not _shadow_trace_ok:
            log.error(
                "[G0] %s — shadow bloqué : DP absent ou trace_id manquant"
                " (cycle_trace_id=%s)",
                symbol,
                _trace_id,
            )
            if _dp and not _dp.is_terminal():
                try:
                    _dp.reject("governance_g0", "missing_trace_id")
                except Exception:
                    pass
        else:
            with watchdog.measure("shadow"):
                eff_size = order_size_usd
                if conviction:
                    eff_size = order_size_usd * conviction.size_factor
                if awareness_engine:
                    eff_size *= awareness_engine.effective_size_factor()
                shadow_trade = shadow.shadow_execute(
                    signal,
                    live_price=prix,
                    capital=max(1.0, eff_size),
                )
                if shadow_trade:
                    log.info("[SHADOW] %s", shadow_trade.summary())

    # MexcSimulator — respecte la politique MetaStrategy (personality).
    # Indépendant de PortfolioBrain : le simulateur a son propre capital ($10-100).
    # Corrige deux bypasses :
    #   1. flash_crash / capital_protection : meta_allowed=False bloque ici
    #   2. max_positions : on lit l'état réel de _virtual_portfolio._positions
    _vp_n_open = len(_virtual_portfolio._positions) if _virtual_portfolio else 0
    _vp_max_pos = personality.max_positions if personality else 5
    if (
        _virtual_portfolio is not None
        and signal.actionable
        and gate_result.allowed
        and meta_allowed
        and _conviction_ok
        and prix > 0
        and _vp_n_open < _vp_max_pos
    ):
        _tp = personality.tp_pct if personality else 0.04
        _sl = personality.sl_pct if personality else 0.02
        _vp_side = signal.signal.upper() if hasattr(signal, "signal") else "BUY"
        _vp_persona = personality.name if personality else "unknown"
        _virtual_portfolio.place_market_order(
            symbol=signal.symbol,
            side=_vp_side,
            qty_usd=0.0,  # auto: 15% du capital simulateur
            tp_pct=_tp,
            sl_pct=_sl,
            score=int(signal.score) if hasattr(signal, "score") else 0,
            personality=_vp_persona,
            regime=getattr(signal, "regime", "unknown"),
            current_price=float(prix),
        )

    persona_name = personality.name if personality else "N/A"
    conv_str = (
        f" | conv: {conviction.level.value}({conviction.score:.0f})"
        if conviction
        else ""
    )
    aw_str = f" | aware: {awareness_state.level.name}" if awareness_state else ""
    pb_str = f" | pb: {pb_verdict.size_factor:.2f}" if pb_verdict else ""
    cae_str = (
        f" | cae: ${allocation.size_usd:.0f}"
        if allocation and allocation.size_usd > 0
        else ""
    )
    mm_str = " | mm: BLOQUE" if mm_check and mm_check.blocked else ""
    eo_str = (
        f" | eo: {eo_verdict.level.name}"
        if eo_verdict and eo_verdict.level.value > 0
        else ""
    )
    log.info(
        "  %s | $%.2f | score: %d/100 | %s | regime: %s | perso: %s | gate: %s%s%s%s%s%s%s",
        symbol,
        prix,
        signal.score,
        signal.signal,
        regime,
        persona_name,
        "OK" if trade_allowed else "BLOQUE",
        conv_str,
        aw_str,
        pb_str,
        cae_str,
        mm_str,
        eo_str,
    )

    # ── Persistance DecisionPacket ────────────────────────────────────────────
    # Rotation quotidienne : DP_LOG_PATH explicite → utilisé tel quel (compat).
    # Sinon : DP_LOG_DIR/decision_packets_YYYY-MM-DD.jsonl (UTC).
    if _dp and _dp.lifecycle_state.value != "CREATED":
        # I-16 — trace_id obligatoire avant toute persistance
        if not _dp.metadata.get("trace_id"):
            log.warning(
                "[GOVERNANCE/I-16] %s — DP sans trace_id, packet invalide (non persisté)",
                symbol,
            )
        else:
            try:
                import json as _json
                from datetime import datetime as _dt
                from pathlib import Path as _Path

                _explicit = os.getenv("DP_LOG_PATH")
                if _explicit:
                    _dp_path = _Path(_explicit)
                else:
                    _log_dir = _Path(os.getenv("DP_LOG_DIR", "databases"))
                    _date = _dt.utcnow().strftime("%Y-%m-%d")
                    _dp_path = _log_dir / f"decision_packets_{_date}.jsonl"
                _dp_path.parent.mkdir(parents=True, exist_ok=True)
                with open(_dp_path, "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps(_dp.to_dict(), ensure_ascii=False) + "\n")
            except Exception as _dp_exc:
                log.debug("[DecisionPacket] log: %s", _dp_exc)

    return {
        "symbol": symbol,
        "prix": prix,
        "signal": signal,
        "gate": gate_result,
        "advice": advice,
        "explanation": explanation,
        "shadow": shadow_trade,
        "personality": personality,
        "meta_allowed": meta_allowed,
        "meta_reason": meta_reason,
        "conviction": conviction,
        "no_trade_verdict": no_trade_verdict,
        "awareness_state": awareness_state,
        "pb_verdict": pb_verdict,
        "allocation": allocation,
        "mm_check": mm_check,
        "eo_verdict": eo_verdict,
        "dq_record": dq_record,
        "trade_allowed": trade_allowed,
        "blockers": _flow_blockers if signal.actionable else "",
        "order_size": order_size_usd,
        "regime": regime,
        "features": features,
        "radar_report": radar_report,
        "ml_decision": ml_decision,
        "n_1h": len(candles_1h),
        "n_4h": len(mtf_candles.get("4h", [])),
        "n_1d": len(mtf_candles.get("1d", [])),
        "signal_to_execute": signal_to_execute,
        "decision_packet": _dp,
        "trace_id": _trace_id,
        "transition_forecast": transition_forecast,
    }


# ── Construction messages Telegram ───────────────────────────────────────────

_SIGNAL_ICON = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}
_REGIME_FR = {
    "bull_trend": "Tendance haussiere",
    "bear_trend": "Tendance baissiere",
    "sideways": "Range lateral",
    "high_volatility_regime": "Haute volatilite",
    "flash_crash": "KRACH ECLAIR",
    "unknown": "Indetermine",
}
_SCORE_BAR = [
    (85, "FORT"),
    (70, "BON"),
    (50, "MOYEN"),
    (30, "FAIBLE"),
    (0, "TRES FAIBLE"),
]


def _score_label(score: int) -> str:
    for threshold, label in _SCORE_BAR:
        if score >= threshold:
            return label
    return "TRES FAIBLE"


def _score_bar(score: int, width: int = 5) -> str:
    """Barre de score visuelle : score 80 → '████░'"""
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


_REGIME_SHORT = {
    "bull_trend": "bull",
    "bear_trend": "bear",
    "sideways": "range",
    "high_volatility_regime": "volat",
    "flash_crash": "KRACH",
    "unknown": "?",
}


def _build_summary(
    results: list[AnalysisResult], cycle: int, min_score: int = 70
) -> str:
    """Rapport compact multi-niveaux — lisible pour 100+ paires sous Telegram."""
    import datetime as _dt

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%d %b %H:%M")
    n_total = len(results)

    # Tri par score décroissant
    sorted_r = sorted(results, key=lambda r: r["signal"].score, reverse=True)

    actionnables = [r for r in sorted_r if r["signal"].score >= min_score]
    surveillance = [r for r in sorted_r if 50 <= r["signal"].score < min_score]
    faibles = [r for r in sorted_r if r["signal"].score < 50]

    # Régime dominant (le plus fréquent parmi les actionnables, sinon global)
    pool = actionnables or sorted_r
    regimes = [r["signal"].regime for r in pool]
    dominant_regime = max(set(regimes), key=regimes.count) if regimes else "unknown"
    regime_label = _REGIME_FR.get(dominant_regime, dominant_regime)

    lines = [
        f"@QuantCrpto — Cycle {cycle} | {ts} UTC",
        f"{n_total} paires | {regime_label} | Seuil {min_score}",
        "",
    ]

    # ── Section 1 : Actionnables ──────────────────────────────────────────────
    if actionnables:
        lines.append(f"ACTIONNABLES ({len(actionnables)})")
        for r in actionnables:
            s = r["signal"]
            g = r["gate"]
            a = r["advice"]
            icon = _SIGNAL_ICON.get(s.signal, "?")
            reg = _REGIME_SHORT.get(s.regime, s.regime[:5])
            bar = _score_bar(s.score)
            gate = "OK" if g.allowed else "BLQ"
            sym = r["symbol"].replace("/USDT", "").ljust(6)
            lines.append(
                f"  {icon} {sym} {s.score:>3}  {bar}  {reg:<5}  {gate}"
                f"  {a.risk_level if a else '?'}"
            )
        lines.append("")
    else:
        # Pas d'actionnable : top 5 pour ne pas avoir un message vide
        lines.append(f"Aucun signal >= {min_score} — Top 5")
        for r in sorted_r[:5]:
            s = r["signal"]
            icon = _SIGNAL_ICON.get(s.signal, "?")
            sym = r["symbol"].replace("/USDT", "").ljust(6)
            bar = _score_bar(s.score)
            lines.append(f"  {icon} {sym} {s.score:>3}  {bar}")
        lines.append("")

    # ── Section 2 : Surveillance (score 50 à seuil-1) ────────────────────────
    if surveillance:
        lines.append(f"SURVEILLANCE ({len(surveillance)} | 50-{min_score - 1})")
        # 4 symboles par ligne pour rester compact
        row: list[str] = []
        for r in surveillance:
            s = r["signal"]
            icon = _SIGNAL_ICON.get(s.signal, "?")
            sym = r["symbol"].replace("/USDT", "")
            row.append(f"{icon}{sym} {s.score}")
            if len(row) == 4:
                lines.append("  " + "  ".join(row))
                row = []
        if row:
            lines.append("  " + "  ".join(row))
        lines.append("")

    # ── Section 3 : Faibles (score < 50) — compteur seul ─────────────────────
    if faibles:
        scores_faibles = [r["signal"].score for r in faibles]
        avg_f = sum(scores_faibles) // len(scores_faibles)
        lines.append(
            f"FAIBLES ({len(faibles)} | moy {avg_f}) — observation silencieuse"
        )
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true"
    mode = "Observation" if advisor_only else f"PAPER TRADING actif (>= {min_score})"
    lines.append(f"Mode: {mode}")

    return "\n".join(lines)


def _build_alert(r: AnalysisResult, cycle: int) -> str:
    """Message d'alerte immédiate — signal actionable détecté."""
    s = r["signal"]
    g = r["gate"]
    a = r.get("advice")
    sh = r.get("shadow")
    ex = r.get("explanation")
    _sig = getattr(s, "signal", "?")
    icon = _SIGNAL_ICON.get(_sig, "?")
    _s_regime = getattr(s, "regime", "unknown")
    regime = _REGIME_FR.get(_s_regime, _s_regime)
    comps = getattr(s, "components", {})

    lines = [
        f"SIGNAL ACTIONABLE — Cycle {cycle}",
        "",
        f"{icon} {r['symbol']} | ${r.get('prix', 0.0):.2f}",
        f"Score: {getattr(s, 'score', 0)}/100 | {_sig}",
        f"Regime: {regime} | Confirme: {getattr(s, 'confirmed', False)}",
        f"Force: {getattr(s, 'strength', 0.0):.0%}",
        "",
        "Scores detail:",
        f"  MTF:     {comps.get('mtf',0):.1f}/40",
        f"  Regime:  {comps.get('regime',0):.1f}/25",
        f"  Donnees: {comps.get('data_quality',0):.1f}/15",
        f"  Memoire: {comps.get('memory',0):.1f}/20",
        "",
        f"Gate: {'PRET A TRADER' if g.allowed else 'BLOQUE — ' + ' | '.join(g.failed)}",
        f"Risque: {a.risk_level if a else '?'} | Confiance: {a.confidence if a else '?'}",
    ]

    # Explication du score si disponible
    if ex:
        verdict_clean = ex.verdict.encode("ascii", errors="replace").decode("ascii")
        lines += [
            "",
            f"Verdict: {verdict_clean}",
            f"Niveau confiance: {ex.confidence_level}",
        ]
        if ex.penalties:
            _score_penalty_keywords = ("seuil", "score", "threshold")
            _filtered_penalties = [
                p
                for p in ex.penalties
                if not g.allowed
                or not any(kw in p[0].lower() for kw in _score_penalty_keywords)
            ]
            if _filtered_penalties:
                pen_str = " | ".join(
                    p[0].encode("ascii", errors="replace").decode("ascii")
                    for p in _filtered_penalties[:2]
                )
                lines.append(f"Alertes: {pen_str}")
        if ex.bonuses:
            bon_str = " | ".join(
                b[0].encode("ascii", errors="replace").decode("ascii")
                for b in ex.bonuses[:2]
            )
            lines.append(f"Points forts: {bon_str}")

    # Données shadow si disponibles
    if sh:
        lines += [
            "",
            "SHADOW EXECUTION (simule, pas envoye):",
            f"  Prix signal:   ${sh.signal_price:.2f}",
            f"  Prix fill sim: ${sh.simulated_fill_price:.2f}",
            f"  Slippage:      {sh.slippage_pct:.3f}%",
            f"  Taille:        {sh.size:.6f} ({r['symbol'].split('/')[0]})",
            f"  Notionnel:     ${sh.notional:.2f}",
            f"  Latence:       {sh.signal_to_order_ms:.1f}ms",
            f"  ID:            {sh.id}",
        ]

    # Futures result si un ordre a été exécuté
    fut = r.get("futures_result")
    if fut:
        mode = fut.get("mode", "?")
        if mode == "futures_demo":
            lines += [
                "",
                "ORDRE FUTURES DEMO PLACE:",
                f"  ID:         {fut.get('id', '?')}",
                f"  Notionnel:  ${fut.get('usd_size', 0):.2f}",
                f"  Statut:     {fut.get('status', '?')}",
            ]
        elif mode == "paper":
            lines += [
                "",
                "ORDRE PAPER PLACE (simulation locale):",
                f"  Cote:       {r.get('signal', {}).side if hasattr(r.get('signal', None), 'side') else '?'}",
                f"  Taille:     ${r.get('order_size', 0):.2f}",
            ]
        elif mode == "futures_failed":
            lines += [
                "",
                f"ORDRE FUTURES ECHOUE: {fut.get('error', '?')}",
            ]
    else:
        advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true"
        blockers = r.get("blockers", "")
        if advisor_only:
            suffix = "Mode observation — aucun ordre place"
        elif blockers:
            suffix = f"Bloque par: {blockers} — aucun ordre place"
        else:
            suffix = "Gate bloquee ou safe mode — aucun ordre place"
        lines += ["", suffix]

    lines += [
        "",
        f"Analyse: {str(a.text)[:250]}",
    ]
    return "\n".join(lines)


def _build_guide() -> str:
    """Guide d'interprétation envoyé au démarrage."""
    _threshold = int(os.getenv("SIGNAL_MIN_SCORE", "70"))
    return (
        "Crypto AI Terminal — Guide de lecture\n"
        "\n"
        "SCORE (0-100):\n"
        "  85-100 : FORT    — signal tres fiable\n"
        "  70-84  : BON     — signal actionable\n"
        "  50-69  : MOYEN   — signal a surveiller\n"
        "  0-49   : FAIBLE  — pas d'action\n"
        "\n"
        "SIGNAL:\n"
        "  BUY  : le bot recommanderait un achat\n"
        "  SELL : le bot recommanderait une vente\n"
        "  HOLD : attendre, pas de signal clair\n"
        "\n"
        "GATE:\n"
        "  PRET     : toutes les conditions passent\n"
        "  BLOQUE   : une condition echoue (score, confirmation, regime)\n"
        "\n"
        "REGIME:\n"
        "  Tendance haussiere : BTC monte clairement\n"
        "  Range lateral      : BTC consolide (normal)\n"
        "  Haute volatilite   : mouvements brusques\n"
        "  KRACH ECLAIR       : danger — pas de trade\n"
        "\n"
        "SCORES DETAIL:\n"
        "  MTF (40pts)    : alignement 1h+4h+1d\n"
        "  Regime (25pts) : contexte de marche\n"
        "  Donnees (15pts): qualite des bougies\n"
        "  Memoire (20pts): historique strategies\n"
        "\n"
        "Rapport toutes les 15 min.\n"
        f"Alerte immediate si score >= {_threshold}."
    )


# ── Boucle principale ─────────────────────────────────────────────────────────


def _gate_paper_dataset() -> None:
    """Abort startup if config is broken or the paper trade dataset contains violations.

    Checks in order:
      1. PAPER_TRADE_LOG path is writable (ledger access)
      2. No integrity violations in the dataset (duplicates, phantom trades…)
    Empty dataset (clean slate) is allowed — burn-in is just starting.
    """
    log_path = os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")

    # Ledger write access — fail fast before loading ccxt or the exchange
    try:
        import pathlib as _pathlib

        _p = _pathlib.Path(log_path)
        _p.parent.mkdir(parents=True, exist_ok=True)
        _probe = _p.parent / ".gate_probe"
        _probe.write_text("ok")
        _probe.unlink()
    except OSError as exc:
        log.critical(
            "[DatasetGate] Ledger inaccessible en écriture (%s): %s — démarrage annulé.",
            log_path,
            exc,
        )
        sys.exit(1)

    try:
        from paper_trading.dataset_validator import validate_corpus
    except ImportError:
        log.warning(
            "[DatasetGate] dataset_validator non disponible — vérification ignorée"
        )
        return

    log_path = os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")
    report = validate_corpus(log_path=log_path)

    if report.total_events == 0:
        log.info("[DatasetGate] Dataset vide — burn-in repart de zéro. OK.")
        return

    if report.violations:
        only_orphan_opens = all("OPEN sans CLOSE" in v for v in report.violations)
        if only_orphan_opens:
            log.warning(
                "[DatasetGate] %d violation(s) OPEN orphelin(es) détectée(s) — "
                "probable crash précédent (le simulateur ne persiste pas les "
                "positions en mémoire au redémarrage). Auto-remédiation : "
                "retrait des OPEN sans CLOSE, trades appariés préservés.",
                len(report.violations),
            )
            if _remediate_orphan_opens(log_path):
                report = validate_corpus(log_path=log_path)
                if not report.violations:
                    log.info(
                        "[DatasetGate] Auto-remédiation réussie — %d trades "
                        "préservés, dataset propre.",
                        report.paired_trades,
                    )
                    return

        for v in report.violations:
            log.critical("[DatasetGate] VIOLATION: %s", v)
        log.critical(
            "[DatasetGate] Dataset INVALIDE (%d violations) — démarrage annulé. "
            "Archivez le dataset corrompu avant de relancer.",
            len(report.violations),
        )
        sys.exit(1)

    log.info(
        "[DatasetGate] Dataset certifié — %d trades, burn-in eligible=%s",
        report.paired_trades,
        report.burnin_eligible,
    )


def _remediate_orphan_opens(log_path: str) -> bool:
    """
    Retire les OPEN sans CLOSE correspondant (positions fantômes laissées par
    un crash précédent). Préserve tous les trades appariés (OPEN+CLOSE) et
    tous les CLOSE. Sauvegarde l'original avant modification.

    Retourne True si la remédiation a réussi (fichier réécrit sans erreur).
    """
    try:
        import json as _gate_json
        import shutil

        events = []
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(_gate_json.loads(line))

        closes = {e["trade_id"] for e in events if e.get("event") == "CLOSE"}
        kept = [
            e
            for e in events
            if e.get("event") == "CLOSE"
            or (e.get("event") == "OPEN" and e.get("trade_id") in closes)
        ]
        kept.sort(key=lambda e: e.get("ts", 0))

        backup_path = f"{log_path}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(log_path, backup_path)

        with open(log_path, "w", encoding="utf-8") as f:
            for e in kept:
                f.write(_gate_json.dumps(e) + "\n")

        log.info(
            "[DatasetGate] Remédiation : %d événements avant, %d après "
            "(sauvegarde: %s)",
            len(events),
            len(kept),
            backup_path,
        )
        return True
    except Exception as exc:
        log.error("[DatasetGate] Remédiation échouée: %s", exc)
        return False


_LOCK_FILE = os.getenv("ADVISOR_LOCK_FILE", "logs/advisor.lock")
_lock_fh = None
# Renseignés par _acquire_instance_lock() — consommés par le marqueur BOOT
# (aucun redémarrage anonyme : cf. incident 2026-07-07, 3 arrêts sans auteur identifié).
_boot_lock_preexisted = False
_boot_previous_pid: str = ""


def _boot_cause_text(lock_preexisted: bool, previous_pid: str) -> str:
    """Cause apparente du boot, dérivée de l'état du verrou d'instance."""
    if lock_preexisted:
        return (
            f"verrou précédent non nettoyé (PID {previous_pid or 'inconnu'} — "
            "arrêt non-propre, crash ou signal non intercepté)"
        )
    return "verrou absent au démarrage (arrêt propre du process précédent, ou premier démarrage)"


def _acquire_instance_lock() -> None:
    """Verrou exclusif — une seule instance autorisée. Exit(1) si doublon détecté."""
    global _lock_fh, _boot_lock_preexisted, _boot_previous_pid
    os.makedirs(os.path.dirname(os.path.abspath(_LOCK_FILE)), exist_ok=True)
    try:
        import fcntl

        for _attempt in range(2):  # 1 tentative + 1 retry après nettoyage lock périmé
            # r+ si le fichier existe (pour lire le PID en cas d'échec), w+ sinon
            try:
                fh = open(_LOCK_FILE, "r+")
                # Fichier déjà présent = l'ancien process n'a pas nettoyé son verrou
                # à la sortie (atexit non exécuté — arrêt non-propre). Capturé pour
                # le marqueur BOOT, avant d'écraser le contenu plus bas.
                _boot_lock_preexisted = True
                _boot_previous_pid = fh.read().strip()
                fh.seek(0)
            except FileNotFoundError:
                fh = open(_LOCK_FILE, "w+")
            # FD_CLOEXEC : empêche les child processes d'hériter ce fd (flock hérité)
            fcntl.fcntl(fh.fileno(), fcntl.F_SETFD, fcntl.FD_CLOEXEC)
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break  # Verrou acquis — sortir de la boucle
            except BlockingIOError:
                fh.seek(0)
                existing_pid = fh.read().strip() or "inconnu"
                fh.close()
                # Lock périmé ? Si le PID est mort, on nettoie et on réessaie une fois
                if _attempt == 0 and existing_pid.isdigit():
                    try:
                        os.kill(int(existing_pid), 0)
                    except ProcessLookupError:
                        # PID mort : verrou périmé — supprimer et recommencer
                        log.warning(
                            "[Lock] Verrou périmé détecté (PID %s mort) — nettoyage",
                            existing_pid,
                        )
                        try:
                            os.unlink(_LOCK_FILE)
                        except FileNotFoundError:
                            pass
                        continue
                    except PermissionError:
                        pass  # PID vivant (permission refusée = process existe)
                print(
                    f"[FATAL] Instance déjà active (PID {existing_pid}). "
                    "Double exécution interdite — invariant d'unicité. Arrêt.",
                    file=sys.stderr,
                )
                sys.exit(1)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()) + "\n")
        fh.flush()
        _lock_fh = fh
    except ImportError:
        # Windows : fcntl absent — vérification PID via psutil (fiable sur Windows)
        if os.path.exists(_LOCK_FILE):
            try:
                with open(_LOCK_FILE) as f:
                    _raw_pid = f.read().strip()
                _boot_lock_preexisted = True
                _boot_previous_pid = _raw_pid
                pid = int(_raw_pid)
                try:
                    import psutil

                    alive = psutil.pid_exists(pid)
                except ImportError:
                    # psutil absent : os.kill(pid, 0) échoue sur Windows même si vivant
                    # On tente quand même — au pire on laisse passer (cas dégradé)
                    try:
                        os.kill(pid, 0)
                        alive = True
                    except ProcessLookupError:
                        alive = False
                    except PermissionError:
                        # Sur Windows, PermissionError = process EXISTE (on n'a pas le droit)
                        alive = True
                if alive:
                    print(
                        f"[FATAL] Instance déjà active (PID {pid}). "
                        "Double exécution interdite — invariant d'unicité. Arrêt.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            except ValueError:
                pass  # fichier corrompu, on continue
        with open(_LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    atexit.register(_release_instance_lock)


def _release_instance_lock() -> None:
    global _lock_fh
    if _lock_fh is not None:
        try:
            import fcntl

            fcntl.flock(_lock_fh, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            _lock_fh.close()
        except Exception:
            pass
        _lock_fh = None
    try:
        os.unlink(_LOCK_FILE)
    except FileNotFoundError:
        pass


_CRITICAL_DEPS = [
    ("pydantic_settings", "pydantic-settings", True),  # silent data loss si absent
    ("httpx", "httpx", False),  # LM Studio — fallback explicite
]


def _check_critical_deps() -> None:
    """Fail-fast si un module critique est absent. Mieux vaut arrêter que tourner silencieusement dégradé."""
    missing_fatal = []
    for mod, pkg, is_fatal in _CRITICAL_DEPS:
        try:
            __import__(mod)
        except ImportError:
            if is_fatal:
                missing_fatal.append(pkg)
            else:
                log.warning(
                    "[DepsCheck] Module optionnel absent: %s (pip install %s) — fallback actif",
                    mod,
                    pkg,
                )
    if missing_fatal:
        msg = (
            f"[FATAL] Modules critiques manquants: {missing_fatal}. "
            "Exécuter: pip install -r requirements.txt"
        )
        log.critical(msg)
        raise SystemExit(msg)


def main(
    symbols: list[str],
    interval: int = 300,
    max_cycles: int | None = None,
    runtime: AdvisorRuntime | None = None,
    _sleep=time.sleep,
) -> None:
    _acquire_instance_lock()
    _check_critical_deps()

    runtime = runtime or load_advisor_runtime()

    os.makedirs("logs", exist_ok=True)
    os.makedirs("databases/shadow_execution", exist_ok=True)

    _t_main_start = (
        time.perf_counter()
    )  # référence pour comparaison bootstrap / cycle 1
    bootstrap_profile: list[tuple[str, float]] = []

    def _profile_bootstrap_step(label: str, fn: Any) -> Any:
        started = time.perf_counter()
        try:
            return fn()
        finally:
            bootstrap_profile.append((label, time.perf_counter() - started))

    log.info("=== ADVISOR LOOP DEMARRE ===")
    log.info(
        "Symboles: %s | Intervalle: %ds | Notify every: %d cycles",
        symbols,
        interval,
        NOTIFY_EVERY,
    )

    if _OBS_AVAILABLE:
        try:
            module_registry.register(
                "advisor_loop",
                priority=ModulePriority.HIGH,
                heartbeat_timeout_sec=max(interval * 2, 120),
            )
            heartbeat_system.register(
                "advisor_loop", timeout_sec=max(interval * 2, 120)
            )
        except Exception:
            pass

    # ── Session primer — lancé AVANT la création des scanners ─────────────────
    # Crée l'exchange CCXT et appelle load_markets() dans un thread daemon.
    # Démarré en tout premier pour maximiser le chevauchement avec le reste
    # du bootstrap (services, exec_engine, modules intel).
    # Quand les threads prewarm démarrent, ils trouvent l'exchange et les markets
    # déjà prêts → ils sautent directement à fetch_ohlcv() (~650ms gagnés).
    _t_primer_start: float | None = None
    _primer_future: Any = None
    _primer_executor: ThreadPoolExecutor | None = None
    if ADVISOR_SESSION_PRIMER:
        _exchange_id = os.getenv(
            "MARKET_SCANNER_EXCHANGE", os.getenv("EXCHANGE_ID", "mexc")
        )
        # MARKET_SCANNER_TESTNET prioritaire — OHLCV publics = vrai exchange
        _scanner_testnet_env = os.getenv("MARKET_SCANNER_TESTNET", "").lower()
        if _scanner_testnet_env in ("true", "false"):
            _testnet = _scanner_testnet_env == "true"
        else:
            _testnet = os.getenv("EXCHANGE_TESTNET", "false").lower() == "true"
        _trace_primer = (
            os.getenv("MARKET_SCANNER_TRACE_TIMINGS", "false").lower() == "true"
        )
        try:
            _scanner_cls = runtime.MarketScanner  # class reference, not instance
            _primer_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="SessionPrimer"
            )
            _t_primer_start = time.perf_counter()
            _primer_future = _primer_executor.submit(
                _prime_exchange_session,
                _exchange_id,
                _testnet,
                _scanner_cls,
                trace=_trace_primer,
            )
            log.info(
                "[SessionPrimer] Lancé en avance (exchange=%s testnet=%s) "
                "— exchange_init + load_markets en parallèle du bootstrap",
                _exchange_id,
                _testnet,
            )
        except Exception as _pe:
            log.warning("[SessionPrimer] Impossible de lancer: %s", _pe)
            _primer_future = None

    # ── PerpUniverseService — boot : charge fichier + démarre thread refresh ──
    # Le service tourne en daemon thread : rafraîchit l'univers toutes les
    # UNIVERSE_REFRESH_H heures (défaut: 6h) et expose les nouveaux symboles
    # via drain_new_symbols() — injectés dynamiquement dans le cycle principal.
    _universe_service: Any = None
    try:
        from core.perp_universe_service import PerpUniverseService as _PerpUS

        _universe_service = _PerpUS()
        _universe_service.start()
        _universe_initial = _universe_service.initial_symbols()
        if _universe_initial:
            _existing_syms = set(symbols)
            _to_merge = [s for s in _universe_initial if s not in _existing_syms]
            if _to_merge:
                symbols = list(symbols) + _to_merge
                log.info(
                    "[Universe] +%d symboles chargés depuis univers persisté (total: %d)",
                    len(_to_merge),
                    len(symbols),
                )
            # Drain initial — tous déjà dans symbols, pas besoin de ré-injecter
            _universe_service.drain_new_symbols()
        else:
            log.info(
                "[Universe] Pas de fichier persisté — premier scan en background"
                " (univers: %d sym défaut)",
                len(symbols),
            )
    except Exception as _ue:
        log.warning("[Universe] Service non disponible: %s", _ue)
        _universe_service = None
    # ─────────────────────────────────────────────────────────────────────────

    # ── Warmup anticipé — AVANT tous les services non-critiques ───────────────
    # Les scanners ne dépendent que de runtime.MarketScanner (pur Python).
    # On les crée ici et on lance immédiatement les futures 1h en background
    # pour que le fetch HTTP Binance tourne EN PARALLELE du reste du boot
    # (kill_switch, exchange_monitor, healer, exec_engine, modules intel).
    # Gain mesuré : overlap max avec les 3-4s de boot non-réseau.
    scanners: dict[str, dict[str, Any]] = _profile_bootstrap_step(
        "scanners",
        lambda: {
            "1h": {
                sym: runtime.MarketScanner(
                    symbols=[sym], timeframe="1h", limit=ADVISOR_1H_LIMIT
                )
                for sym in symbols
            },
            "mtf": {
                sym: runtime.MultiTimeframeScanner(
                    symbols=[sym], refresh_every=MTF_REFRESH_EVERY
                )
                for sym in symbols
            },
        },
    )
    prewarm_executor: ThreadPoolExecutor | None = None
    prewarm_futures: dict[str, Any] = {}
    prewarm_mtf_futures: dict[str, Any] = {}
    _t_warmup_start: float | None = None
    _t_warmup_end: float | None = None
    advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower() == "true"
    _paper_trading_enabled = os.getenv("PAPER_TRADING_ENABLED", "false").lower() in {
        "true",
        "1",
        "yes",
    }
    if _paper_trading_enabled:
        _gate_paper_dataset()
    startup_light = advisor_only and ADVISOR_STARTUP_LIGHT
    prewarm_1h_enabled = ADVISOR_PREWARM_1H
    prewarm_mtf_enabled = ADVISOR_PREWARM_MTF and not startup_light
    live_execution_bootstrap = ADVISOR_LIVE_EXECUTION_BOOTSTRAP and not startup_light
    background_position_watch = ADVISOR_BACKGROUND_POSITION_WATCH and not startup_light
    defer_optional_intel = ADVISOR_DEFER_OPTIONAL_INTEL or startup_light
    defer_post_cycle_services = advisor_only and (
        ADVISOR_DEFER_POST_CYCLE_SERVICES or startup_light
    )
    persistent_warmup_enabled = ADVISOR_PERSISTENT_WARMUP and not startup_light
    threat_radar_every = max(ADVISOR_THREAT_RADAR_EVERY, 3 if startup_light else 1)
    cycle_budget_seconds = ADVISOR_CYCLE_BUDGET_SECONDS
    load_shed_cycles = ADVISOR_LOAD_SHED_CYCLES

    if startup_light:
        log.info(
            "[StartupLight] Actif — prewarm_mtf=%s persistent_warmup=%s threat_radar_every=%d",
            "off",
            "off",
            threat_radar_every,
        )

    if prewarm_1h_enabled:
        n_mtf_slots = len(symbols) if prewarm_mtf_enabled else 0
        max_workers = max(
            1,
            min(
                len(symbols) + n_mtf_slots,
                int(
                    os.getenv(
                        "ADVISOR_PREWARM_MAX_WORKERS",
                        str(len(symbols) + n_mtf_slots or 1),
                    )
                ),
            ),
        )
        prewarm_executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="AdvisorWarm"
        )
        _t_warmup_start = time.perf_counter()
        prewarm_futures = {
            sym: prewarm_executor.submit(scanners["1h"][sym].scan)
            for sym in symbols
            if hasattr(scanners["1h"][sym], "scan")
        }
        if prewarm_futures:
            log.info(
                "[Warmup] Prechauffage 1h lance EN AVANCE pour %d symbole(s) (avant services boot)",
                len(prewarm_futures),
            )
        if prewarm_mtf_enabled:
            prewarm_mtf_futures = {
                sym: prewarm_executor.submit(scanners["mtf"][sym].scan)
                for sym in symbols
                if hasattr(scanners["mtf"][sym], "scan")
            }
            if prewarm_mtf_futures:
                log.info(
                    "[Warmup] Prechauffage MTF (4h+1d) lance en background",
                )
        if not prewarm_futures and not prewarm_mtf_futures:
            prewarm_executor.shutdown(wait=False, cancel_futures=True)
            prewarm_executor = None

    # Kill switch — état partagé entre thread Telegram et boucle principale.
    # threading.Event : thread-safe sans dépendance au GIL, sémantique claire.
    # set()     → arrêt demandé
    # clear()   → reprise autorisée
    # is_set()  → vérification état
    _halt_requested = threading.Event()
    _awareness_ref: dict = {"engine": None}  # rempli après création awareness_engine
    _op_state_ref: list = [None]  # rempli après init OperationalState (P10-F)
    _black_box_ref: dict = {"instance": None}
    runtime_authority = RuntimeStateMachine()
    if _AUTHORITY_AVAILABLE:
        _init_authority(runtime_authority)
        log.info(
            "[main] GovernanceKernel initialisé — RSM state=%s",
            runtime_authority.state.value,
        )
        # I-1: P6_SAFE_MODE propagated to RSM immediately after authority init.
        # This ensures can_trade()=False before any cycle starts, so the G1
        # pre-compute gate in analyze_symbol() blocks all computation.
        if P6_SAFE_MODE:
            runtime_authority.request_safe_mode(
                "p6_safe_mode",
                "P6_SAFE_MODE env flag — computation sealed at entry (I-1)",
            )
            log.warning(
                "[G1/I-1] P6_SAFE_MODE → RSM verrouillé (SAFE_MODE) — "
                "pipeline bloqué pre-compute"
            )

    def _runtime_safe_mode_active() -> bool:
        return runtime_authority.state == SystemState.SAFE_MODE

    def _on_stop_all():
        _halt_requested.set()
        runtime_authority.request_safe_mode("kill_switch_stop_all", "STOP_ALL telegram")
        log.critical("[main] STOP_ALL recu — la boucle va s'arreter au prochain cycle")

    def _on_close_all():
        _halt_requested.set()
        runtime_authority.request_safe_mode(
            "kill_switch_close_all", "CLOSE_ALL telegram"
        )
        log.critical("[main] CLOSE_ALL recu — la boucle va s'arreter au prochain cycle")

    def _on_safe_mode():
        runtime_authority.request_safe_mode(
            "kill_switch_safe_mode", "SAFE_MODE telegram"
        )
        log.warning("[main] SAFE_MODE recu — autorité runtime en SAFE_MODE")

    def _on_resume():
        _halt_requested.clear()
        runtime_authority.clear_all_safe_mode_requests()
        if _awareness_ref["engine"] is not None:
            if hasattr(_awareness_ref["engine"], "operator_resume"):
                _awareness_ref["engine"].operator_resume(full_reset=False)
                log.info("[main] /RESUME — SelfAwareness operator_resume")
            else:
                _awareness_ref["engine"].reset()
                log.info("[main] /RESUME — SelfAwareness reset (retour a OK)")
        if _op_state_ref[0] is not None:
            _op_state_ref[0].reset()
            log.info("[main] /RESUME — OperationalState reset → RUNNING")
        if _black_box_ref["instance"] is not None:
            try:
                _black_box_ref["instance"].record_system_event(
                    "OPERATOR_RESUME",
                    "Resume manuel via Telegram /RESUME",
                )
            except Exception as _bb_exc:
                log.debug("[main] BlackBox OPERATOR_RESUME non journalise: %s", _bb_exc)

    kill_switch = _profile_bootstrap_step(
        "kill_switch",
        lambda: runtime.TelegramKillSwitch(
            on_stop_all=_on_stop_all,
            on_close_all=_on_close_all,
            on_safe_mode=_on_safe_mode,
            on_resume=_on_resume,
        ),
    )
    kill_switch_started = False

    def _start_kill_switch() -> None:
        nonlocal kill_switch_started
        if not kill_switch_started:
            _profile_bootstrap_step("kill_switch.start", kill_switch.start)
            kill_switch_started = True

    if defer_post_cycle_services:
        log.info("[Startup] KillSwitch differe apres le cycle 1 (observation seule)")
    else:
        _start_kill_switch()

    # Exchange monitor — surveillance connexion Binance en background
    exchange_monitor = _profile_bootstrap_step(
        "exchange_monitor",
        lambda: runtime.ExchangeMonitor(
            on_offline=lambda: log.warning("[main] Exchange hors ligne signalé"),
            on_recovered=lambda: log.info("[main] Exchange rétabli"),
        ),
    )
    exchange_monitor_started = False

    def _start_exchange_monitor() -> None:
        nonlocal exchange_monitor_started
        if not exchange_monitor_started:
            _profile_bootstrap_step("exchange_monitor.start", exchange_monitor.start)
            exchange_monitor_started = True

    if defer_post_cycle_services:
        log.info(
            "[Startup] ExchangeMonitor differe apres le cycle 1 (observation seule)"
        )
    else:
        _start_exchange_monitor()

    # Self-healing bot — surveille les composants critiques
    healer = _profile_bootstrap_step(
        "self_healing",
        lambda: runtime.SelfHealingBot(global_check_interval_s=10.0),
    )

    # Composant 1 : exchange
    def _exchange_restart() -> None:
        log.warning("[SelfHeal] Exchange unhealthy — tentative de reconnexion")
        try:
            ok = exec_engine.reconnect()
            if ok:
                log.info("[SelfHeal] Exchange reconnecté avec succès")
            else:
                log.error("[SelfHeal] Reconnexion échouée — bot en mode dégradé")
        except Exception as exc:
            log.exception("[SelfHeal] Reconnexion exception: %s", exc)

    def _exchange_health_check() -> bool:
        # Tolère les timeouts transitoires du testnet — ne déclenche une reconnexion
        # qu'après 3 échecs consécutifs pour éviter les faux positifs.
        if not exchange_monitor.is_healthy():
            snap = exchange_monitor.snapshot()
            failures = snap.get("consecutive_failures", 0)
            if failures < 3:
                return True  # transitoire, pas encore critique
            err = snap.get("last_error") or f"ping KO ({failures} échecs)"
            raise RuntimeError(err)
        return True

    _profile_bootstrap_step(
        "self_healing.register_exchange",
        lambda: healer.register_simple(
            "exchange",
            health_fn=_exchange_health_check,
            restart_fn=_exchange_restart,
        ),
    )

    # Composant 2 : LM Studio (non bloquant — le bot fonctionne sans)
    def _lm_health() -> bool:
        try:
            import requests as _r

            lm_url = os.environ.get("LM_STUDIO_URL", "http://localhost:1234")
            r = _r.get(f"{lm_url}/v1/models", timeout=0.5)
            return r.status_code == 200
        except Exception:
            return True  # LM Studio optionnel — pas de restart si absent

    def _lm_restart() -> None:
        log.warning("[SelfHeal] LM Studio inaccessible — bascule déterministe")
        os.environ["LM_STUDIO_AVAILABLE"] = "false"

    _profile_bootstrap_step(
        "self_healing.register_lm_studio",
        lambda: healer.register_simple(
            "lm_studio", health_fn=_lm_health, restart_fn=_lm_restart
        ),
    )
    healer_started = False

    def _start_healer() -> None:
        nonlocal healer_started
        if not healer_started:
            _profile_bootstrap_step("self_healing.start", healer.start)
            healer_started = True

    if defer_post_cycle_services:
        log.info("[Startup] SelfHealing differe apres le cycle 1 (observation seule)")
    else:
        _start_healer()

    # Warmup persistant — maintient le cache OHLCV chaud entre les cycles
    _persistent_warmer: Any = None
    if persistent_warmup_enabled:
        try:
            from quant_hedge_ai.persistent_warmup import CacheWarmer

            _persistent_warmer = _profile_bootstrap_step(
                "persistent_warmup",
                lambda: CacheWarmer(
                    scanner=None, symbols=symbols, timeframes=["1h", "4h", "1d"]
                ),
            )
            _profile_bootstrap_step("persistent_warmup.start", _persistent_warmer.start)
            log.info("[PersistentWarmup] daemon demarre pour %d symboles", len(symbols))
        except Exception as _pw_exc:
            log.warning("[PersistentWarmup] echec demarrage: %s", _pw_exc)

    # Init modules
    Position = runtime.Position
    tracker_finalize_position = runtime.tracker_finalize_position
    tracker_open_position = runtime.tracker_open_position
    tracker_run_cycle = runtime.tracker_run_cycle

    if advisor_only and not live_execution_bootstrap:
        exec_engine = _profile_bootstrap_step(
            "execution_engine", runtime.ExecutionEngine
        )
        has_futures = False
        futures_bal = 0.0
    else:
        exec_engine = _profile_bootstrap_step(
            "execution_engine.from_env", runtime.ExecutionEngine.from_env
        )
        has_futures = exec_engine.has_futures_demo()
        futures_bal = exec_engine.fetch_futures_balance() if has_futures else 0.0

    # ── Portefeuille totalitaire unique : bootstrap X depuis l'API ────────────
    # X = solde spot/futures USDT du compte API connecté.
    # Si aucune clé API ou solde=0 → X=null → alerte + mode paper fallback.
    # Tous les modules partagent ce seul X via WalletSync singleton.
    from infra.wallet_sync import MIN_CAPITAL_X
    from infra.wallet_sync import bootstrap_capital_x as _bootstrap_x
    from infra.wallet_sync import get_wallet_sync as _get_wallet_sync_boot

    _capital_x = _bootstrap_x(getattr(exec_engine, "_exchange", None))
    _paper_mode = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
    _paper_capital = float(os.getenv("WALLET_PAPER_CAPITAL", "1000"))
    if _capital_x is not None:
        log.info(
            "[WalletSync] Portefeuille unique X = $%.2f USDT (depuis API)", _capital_x
        )
        # Notification bot compte réel — STANDBY ou LIVE selon mode
        if _paper_mode:
            # Format aligné sur le rapport périodique (compte 2 = grand livre
            # continu, session PnL = affichage seul) — cf ADR-0011 wallet_sync.
            _boot_wallet = _get_wallet_sync_boot()
            _telegram_real(
                "🔴 <b>STANDBY — Compte Réel</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Solde API MEXC : <b>${_capital_x:.4f} USDT</b>\n"
                f"📈 Paper Equity (machine) : <b>${_boot_wallet.get_balance():.2f} USDT</b>\n"
                f"🔄 PnL depuis ce redémarrage : "
                f"<b>{_boot_wallet.session_pnl_since_restart():+.2f}$</b>\n"
                f"🔒 Aucun ordre réel — simulation uniquement (compte 2)\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "⏳ Active le trading sur l'API pour passer en LIVE"
            )
        else:
            _telegram_real(
                "🟢 <b>LIVE — Compte Réel</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Capital X : <b>${_capital_x:.4f} USDT</b>\n"
                "⚡ Trading live actif sur MEXC"
            )
    else:
        _exch_obj = getattr(exec_engine, "_exchange", None)
        if _exch_obj is not None:
            log.error(
                "[WalletSync] Solde API = 0 USDT — X=null. Ajoutez des fonds "
                "ou vérifiez les permissions de la clé API."
            )
            try:
                _telegram(
                    "⚠️ PORTEFEUILLE X = NULL\n"
                    "Solde API = 0 USDT — impossible de trader.\n"
                    "Ajoutez des fonds sur votre compte ou vérifiez la clé API."
                )
            except Exception:
                pass
            _telegram_real(
                "⚠️ <b>COMPTE RÉEL — X = NULL</b>\n"
                "Solde API = 0 USDT\n"
                "Ajoutez des fonds ou vérifiez la clé API."
            )
        else:
            log.info(
                "[WalletSync] Aucune clé API détectée — X=%s (paper fallback WALLET_PAPER_CAPITAL)",
                os.getenv("WALLET_PAPER_CAPITAL", "100"),
            )

    # Lire le capital réel disponible (balance USDT testnet ou .env fallback)
    # Après bootstrap, WalletSync retourne X si défini, sinon WALLET_PAPER_CAPITAL.
    real_capital = exec_engine.fetch_available_capital()
    if real_capital < MIN_CAPITAL_X:
        log.warning(
            "[WalletSync] Capital = $%.4f < $%.1f — système en mode dégradé",
            real_capital,
            MIN_CAPITAL_X,
        )

    # P2: Init execution pipeline (snapshot statique — pas de refresh réseau)
    if _EXEC_CONSTRAINTS_AVAILABLE:
        _binance_rules_mod.refresh_from_exchange()  # no-op en mode MEXC
        _order_validator = _OrderValidator()
        _rate_limiter = _OrderRateLimiter()
        _exec_sim = _mexc_sim_factory()
        os.makedirs("logs/execution_audit", exist_ok=True)
    else:
        _order_validator = _rate_limiter = _exec_sim = None

    max_order = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))

    # ── P10-F — Capital Throttle + Emergency Stop + KPI Tracker ──────────────
    _P10_PHASE = os.getenv("P10_PHASE", "F-01")
    _p10_throttle = None
    _p10_emergency = None
    _p10_kpi = None
    try:
        from capital_deployment.capital_throttle import (
            CapitalThrottle as _P10ThrottleCls,
        )
        from capital_deployment.emergency_stop_manager import (
            EmergencyStopManager as _P10EmgCls,
        )
        from capital_deployment.phase_kpi_tracker import PhaseKPITracker as _P10KPICls

        # ADR-0011: base épinglée pour stationnarité du sizing pendant la validation.
        # Revoir à la phase calibration si un sizing proportionnel à l'equity est validé.
        _p10_throttle = _P10ThrottleCls(total_capital=_paper_capital, phase=_P10_PHASE)
        _p10_emergency = _P10EmgCls(
            phase=_P10_PHASE,
            halt_fn=lambda reason: _halt_requested.set(),
        )
        _p10_kpi = _P10KPICls(phase=_P10_PHASE, initial_capital=real_capital)
        if advisor_only:
            # Paper mode : capital paper indépendant du capital réel throttlé.
            # Le CapitalThrottle (basé sur $real_capital live) ne s'applique pas.
            # Invariant : paper_order_usd n'affecte jamais la taille des ordres live.
            _paper_order_usd = float(os.getenv("PAPER_SIM_ORDER_USD", "25.0"))
            max_order = min(max_order, _paper_order_usd)
            log.info(
                "[SIZING] Paper mode | order_usd=%.2f (PAPER_SIM_ORDER_USD) | "
                "live capital=%.2f (CapitalThrottle ignoré)",
                _paper_order_usd,
                _p10_throttle.allocated_capital,
            )
        else:
            max_order = min(max_order, _p10_throttle.throttled_size(max_order))
            log.info(
                "[P10-F] Phase=%s | capital alloué=%.2f | max_order=%.2f",
                _P10_PHASE,
                _p10_throttle.allocated_capital,
                max_order,
            )
    except Exception as _p10_init_exc:
        log.warning("[P10-F] Non disponible: %s", _p10_init_exc)

    # ── P10-F OperationalState (RUNNING / DEGRADED / HALTED) ─────────────────
    _op_state = None
    try:
        from capital_deployment.operational_state import OperationalState as _OpStateCls

        def _on_op_degraded(reason: str) -> None:
            log.warning("[P10-F] DEGRADED: %s", reason)
            _telegram(
                f"Mode DEGRADED — exchange instable\n{reason}\n"
                f"Trading continue. Envoyez /RESUME si intervention requise."
            )

        def _on_op_halted(reason: str) -> None:
            log.critical("[P10-F] HALTED: %s", reason)
            _halt_requested.set()
            _telegram(
                f"P10-F HALTED — intervention requise\n{reason}\n"
                f"Envoyez /RESUME pour reprendre."
            )

        def _on_op_recovered() -> None:
            log.info("[P10-F] Exchange stabilise — retour RUNNING")
            _telegram("Exchange stabilise — retour mode RUNNING.")

        _op_state = _OpStateCls(
            on_degraded=_on_op_degraded,
            on_halted=_on_op_halted,
            on_recovered=_on_op_recovered,
        )
        _op_state_ref[0] = _op_state
        log.info("[P10-F] OperationalState initialise (RUNNING)")
    except Exception as _op_init_exc:
        log.warning("[P10-F] OperationalState non disponible: %s", _op_init_exc)
    # ─────────────────────────────────────────────────────────────────────────

    # ── P10-F Command Center Bot (lecture + écriture depuis Telegram) ────────
    _portfolio_bot = None
    _chart_server = None
    try:
        from capital_deployment.command_center_bot import CommandCenterBot
        from capital_deployment.command_center_bot import CommandDataProvider as _CDP

        def _set_param_live(name: str, value: str) -> bool:
            os.environ[name] = value
            if name == "EXEC_MAX_ORDER_USD":
                nonlocal max_order
                max_order = float(value)
            return True

        def _get_trades_for_bot():
            try:
                from paper_trading.recorder import get_recorder as _gr

                return _gr().get_trades()
            except Exception:
                return []

        def _get_signals_for_bot():
            try:
                _r = results  # noqa: F821 — closure, défini plus loin dans le cycle
                if not _r:
                    return {}
                return {
                    r["symbol"]: {
                        "score": getattr(r.get("signal"), "score", 0),
                        "action": getattr(r.get("signal"), "signal", "?"),
                        "actionable": getattr(r.get("signal"), "actionable", False),
                        "regime": r.get("regime", ""),
                    }
                    for r in _r
                }
            except Exception:
                return {}

        def _get_positions_for_bot():
            # MexcSim d'abord (vrai ledger paper), pos_manager en fallback —
            # régression "POSITIONS 0 ouverte" du rapport 21:00, 2026-07-12.
            return _positions_for_display(_virtual_portfolio, pos_manager)  # noqa: F821

        def _get_eo_for_bot():
            try:
                return executive_override.metrics_snapshot()  # noqa: F821
            except Exception:
                return None

        def _get_gate_for_bot():
            try:
                snap = gate._last_snapshot  # noqa: F821
                return vars(snap) if snap is not None else None
            except Exception:
                return None

        def _get_blackbox_for_bot(n: int):
            try:
                return black_box.query(limit=n)  # noqa: F821
            except Exception:
                return []

        def _get_regime_for_bot():
            try:
                return {
                    s: {"regime": _adaptive_regime, "score": 0}
                    for s in symbols  # noqa: F821
                }
            except Exception:
                return {}

        _pb_provider = _CDP(
            get_kpis=lambda: _kpi_snapshot_with_canonical_n(_p10_kpi),
            get_balances=lambda: {"spot": real_capital, "futures": 0.0},
            get_positions=_get_positions_for_bot,
            get_phase=lambda: _P10_PHASE,
            get_throttle=lambda: _p10_throttle,
            get_regime=_get_regime_for_bot,
            get_signals=_get_signals_for_bot,
            get_risk=_get_eo_for_bot,
            get_health=lambda: {"advisor_loop": True},
            get_eo=_get_eo_for_bot,
            get_gate=_get_gate_for_bot,
            get_blackbox=_get_blackbox_for_bot,
            get_trades=_get_trades_for_bot,
            set_param=_set_param_live,
        )
        _portfolio_bot = CommandCenterBot.from_env(_pb_provider)
        _portfolio_bot.start()
    except Exception as _pb_exc:
        log.warning("[CommandCenter] Non disponible: %s", _pb_exc)

    # ── Chart Server (dashboard web temps réel) ───────────────────────────────
    try:
        from capital_deployment.chart_server import ChartServer as _CS

        _chart_server = _CS.from_env(
            _pb_provider if "_pb_provider" in dir() else type("_", (), {})()
        )
        _chart_server.start()
    except Exception as _cs_exc:
        log.warning("[ChartServer] Non disponible: %s", _cs_exc)
    # ─────────────────────────────────────────────────────────────────────────

    order_size = min(
        max_order, real_capital * float(os.getenv("V9_MAX_POSITION_WEIGHT", "0.05"))
    )
    log.info(
        "Capital disponible: $%.2f | Taille ordre: $%.2f (max $%.2f)",
        real_capital,
        order_size,
        max_order,
    )

    trading_mode = (
        "OBSERVATION ONLY (V9_ADVISOR_ONLY=true)"
        if advisor_only
        else f"TRADING ACTIF - Futures Demo ({'CONNECTE $%.0f USDT' % futures_bal if has_futures else 'NON DISPONIBLE'})"
    )

    log.info("Mode: %s", trading_mode)

    _x_status = (
        f"X=${_capital_x:.2f} USDT (API)"
        if _capital_x is not None
        else "X=null (paper fallback)"
    )
    _telegram(
        f"Crypto AI Terminal demarre\n"
        f"Symboles: {', '.join(symbols)}\n"
        f"Intervalle: {interval}s | Rapport: toutes les {interval * NOTIFY_EVERY // 60} min\n"
        f"Portefeuille unique: {_x_status}\n"
        f"Capital: ${real_capital:.0f} | Ordre max: ${order_size:.0f}\n"
        f"Mode: {trading_mode}\n"
        f"Kill Switch: actif | Exchange Monitor: actif\n"
        f"Self-Healing: actif | Watchdog: actif\n"
        f"Portfolio Brain: actif | Capital Engine: actif (Kelly+EV+Vol)"
    )

    _telegram(_build_guide())

    # SubaccountManager — supprimé. Portefeuille totalitaire unique X.
    # Un seul solde, une seule source de vérité : WalletSync.get_balance().
    sub_manager = None
    log.info(
        "[Portefeuille] Unique — X=$%.2f USDT (SubaccountManager désactivé définitivement)",
        real_capital,
    )

    # Position Manager — surveille les positions ouvertes (TP/SL/trailing)
    pos_manager = _profile_bootstrap_step(
        "position_manager",
        lambda: runtime.PositionManager(
            exchange=_get_exchange_futures(exec_engine),
            paper_mode=advisor_only or not has_futures,
        ),
    )
    if not advisor_only or background_position_watch:
        _profile_bootstrap_step("position_manager.start", pos_manager.start)
    else:
        log.info("[PositionManager] Désactivé en observation seule")

    def _tracker_payload_from_position(pos: Any) -> dict[str, Any]:
        side = (
            "BUY" if getattr(pos, "side", None) and pos.side.value == "long" else "SELL"
        )
        return {
            "id": str(
                getattr(pos, "order_id", "")
                or f"{pos.symbol}_{int(getattr(pos, 'opened_at', time.time()) * 1000)}"
            ),
            "symbol": pos.symbol,
            "side": side,
            "entry_price": float(pos.entry_price),
            "size": float(pos.size_usd),
            "timestamp": float(getattr(pos, "opened_at", time.time())),
            "regime": getattr(pos, "regime", "unknown"),
            "confidence": float(getattr(pos, "signal_score", 0.0)),
            "max_price": float(getattr(pos, "highest_price", pos.entry_price)),
            "min_price": float(getattr(pos, "lowest_price", pos.entry_price)),
            "price_path": [
                float(pos.entry_price),
                float(
                    getattr(pos, "current_price", pos.entry_price) or pos.entry_price
                ),
            ],
            "subaccount": "main",
            "leverage": int(getattr(pos, "leverage", 1)),
            "qty": float(getattr(pos, "qty", 0.0)),
            "tp_pct": float(getattr(pos, "tp_pct", 0.0)),
            "sl_pct": float(getattr(pos, "sl_pct", 0.0)),
            "trailing_pct": float(getattr(pos, "trailing_pct", 0.0)),
            "atr": float(getattr(pos, "atr", 0.0)),
            "volatility": float(getattr(pos, "volatility", 0.0)),
        }

    def _refresh_tracker_artifacts(event_name: str) -> None:
        try:
            tracker_run_cycle(run_optimizer=False)
        except Exception as tracker_exc:
            log.warning(
                "[TrackerSystem] refresh échoué après %s: %s", event_name, tracker_exc
            )

    def _build_position_from_execution(
        order_result: JSONDict,
        result_row: AnalysisResult,
        symbol: str,
        action: str,
        effective_size: float,
    ) -> Any:
        personality = result_row.get("personality")
        feat = result_row.get("features", {})
        atr_val = float(feat.get("atr", 0.0))
        vol_val = float(feat.get("atr_ratio", feat.get("volatility", 0.0)))
        entry_price = _to_float(
            order_result.get("price")
            or order_result.get("average")
            or _stats_dict(order_result.get("info")).get("avgPrice"),
            _to_float(result_row.get("prix", 0.0)),
        )
        qty = _to_float(
            order_result.get("amount")
            or order_result.get("filled")
            or order_result.get("qty"),
            0.0,
        )
        if qty <= 0 and entry_price > 0:
            qty = effective_size / entry_price

        normalized_result = dict(order_result)
        if entry_price > 0 and not normalized_result.get("price"):
            normalized_result["price"] = entry_price
        if qty > 0 and not normalized_result.get("amount"):
            normalized_result["amount"] = qty

        if hasattr(Position, "from_futures_order"):
            pos = Position.from_futures_order(
                normalized_result,
                symbol,
                action,
                effective_size,
                tp_pct=(
                    (result_row.get("ml_decision") or {}).get("tp")
                    or (personality.tp_pct if personality else 0.04)
                ),
                sl_pct=(
                    (result_row.get("ml_decision") or {}).get("sl")
                    or (personality.sl_pct if personality else 0.02)
                ),
                trailing=(
                    (result_row.get("ml_decision") or {}).get("trail_pct")
                    or (personality.trailing_pct if personality else 0.0)
                ),
                atr=atr_val,
                volatility=vol_val,
                regime=result_row.get("regime", "unknown"),
            )
        else:
            from quant_hedge_ai.agents.execution.position_manager import (
                PositionSide as _PS,
            )

            pos = Position(
                symbol=symbol,
                side=_PS.LONG if action.upper() == "BUY" else _PS.SHORT,
                entry_price=entry_price,
                size_usd=effective_size,
                qty=qty,
                subaccount="main",
            )

        pos.signal_score = result_row["signal"].score
        pos.conviction_level = (
            result_row["conviction"].level.value
            if result_row.get("conviction")
            else "medium"
        )
        pos.signal_age_sec = time.time() - result_row["signal"].timestamp
        raw_features = result_row.get("features")
        pos.entry_features = raw_features if isinstance(raw_features, dict) else {}
        pos.regime = result_row.get("regime", "unknown")
        pos.subaccount = "main"
        return pos

    def _register_position_from_execution(
        order_result: JSONDict,
        result_row: AnalysisResult,
        symbol: str,
        action: str,
        effective_size: float,
    ) -> bool:
        result_mode = str(order_result.get("mode", ""))
        if result_mode not in {"futures_demo", "paper", "live"}:
            return False

        try:
            executive_override.record_trade()
        except Exception:
            pass

        try:
            pos = _build_position_from_execution(
                order_result,
                result_row,
                symbol,
                action,
                effective_size,
            )
            pos_manager.add_position(pos)
            try:
                import json as _json
                import os as _os

                _snap_path: str = _os.path.join("databases", "positions_snapshot.json")
                _snap_tmp: str = _snap_path + ".tmp"
                _snap_positions: list[dict[str, Any]] = _snapshot_list(
                    pos_manager.snapshot()
                )
                _snap_data: dict[str, Any] = {
                    "ts": time.time(),
                    "positions": _snap_positions,
                }
                with open(_snap_tmp, "w", encoding="utf-8") as _sf:
                    _json.dump(_snap_data, _sf)
                _os.replace(_snap_tmp, _snap_path)
            except Exception as _snap_exc:
                log.debug("[SNAPSHOT] write échoué: %s", _snap_exc)
            try:
                tracker_open_position(
                    symbol=symbol,
                    side=action,
                    price=float(
                        getattr(
                            pos, "entry_price", _to_float(result_row.get("prix", 0.0))
                        )
                    ),
                    size=float(effective_size),
                    regime=result_row.get("regime", "unknown"),
                    confidence=float(result_row["signal"].score),
                    id=str(getattr(pos, "order_id", "")),
                    timestamp=float(getattr(pos, "opened_at", time.time())),
                    subaccount=getattr(pos, "subaccount", "default"),
                    leverage=int(getattr(pos, "leverage", 1)),
                    qty=float(getattr(pos, "qty", 0.0)),
                    tp_pct=float(getattr(pos, "tp_pct", 0.0)),
                    sl_pct=float(getattr(pos, "sl_pct", 0.0)),
                    trailing_pct=float(getattr(pos, "trailing_pct", 0.0)),
                    atr=float(getattr(pos, "atr", 0.0)),
                    volatility=float(getattr(pos, "volatility", 0.0)),
                    source="advisor_loop",
                )
                _refresh_tracker_artifacts("open")
            except Exception as tracker_exc:
                log.warning(
                    "[TrackerSystem] open échoué pour %s: %s", symbol, tracker_exc
                )
            # ── PaperTradeRecorder — source de vérité entry ───────────────────
            try:
                from paper_trading.recorder import DecisionContext as _DecisionContext
                from paper_trading.recorder import MarketContext as _MarketContext
                from paper_trading.recorder import get_recorder as _get_recorder

                _conviction = result_row.get("conviction")
                _tf = result_row.get("transition_forecast")
                _get_recorder().record_open(
                    trade_id=str(getattr(pos, "order_id", "") or id(pos)),
                    symbol=symbol,
                    side=action,
                    price=float(
                        getattr(
                            pos, "entry_price", _to_float(result_row.get("prix", 0.0))
                        )
                    ),
                    size_usd=float(effective_size),
                    regime=result_row.get("regime", "unknown"),
                    score=int(_to_float(getattr(result_row.get("signal"), "score", 0))),
                    order_id=str(getattr(pos, "order_id", "")),
                    mode=str(order_result.get("mode", "futures_demo")),
                    market_context=_MarketContext.from_features(
                        result_row.get("features") or {}
                    ),
                    decision_context=_DecisionContext(
                        score=float(getattr(result_row.get("signal"), "score", 0) or 0),
                        conviction_level=getattr(
                            getattr(_conviction, "level", None), "value", None
                        ),
                        conviction_value=(
                            float(getattr(_conviction, "value", None) or 0)
                            if _conviction
                            else None
                        ),
                        personality=(str(result_row.get("personality") or "") or None),
                        regime=result_row.get("regime", "unknown"),
                        transition_forecast=(
                            str(getattr(_tf, "most_likely_next", "") or "") or None
                            if _tf
                            else None
                        ),
                    ),
                )
            except Exception as _rec_exc:
                log.debug("[PaperRecorder] open échoué: %s", _rec_exc)
            # ── CommandCenter — push position ouverte ──────────────────────────
            try:
                if _portfolio_bot is not None:
                    _entry_px = float(getattr(pos, "entry_price", 0.0))
                    _tp_px = float(getattr(pos, "tp_price", 0.0))
                    _sl_px = float(getattr(pos, "sl_price", 0.0))
                    _trail_pct = float(getattr(pos, "trailing_pct", 0.0))
                    _vol = float(getattr(pos, "volatility", 0.0))
                    _regime = result_row.get("regime", "?")
                    _score = getattr(result_row.get("signal"), "score", 0)
                    _tp_s = f"${_tp_px:.4g}" if _tp_px else "N/A"
                    _sl_s = f"${_sl_px:.4g}" if _sl_px else "N/A"
                    _tr_s = f" trail {_trail_pct:.1%}" if _trail_pct else ""
                    _vol_s = f"{_vol:.3f}" if _vol else "N/A"
                    _portfolio_bot.send(
                        f"ENTREE {action.upper()} — {symbol}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Entry:  ${_entry_px:.4g}\n"
                        f"TP:     {_tp_s}  SL: {_sl_s}{_tr_s}\n"
                        f"Vol:    ${float(effective_size):.2f}  |  Volatilite: {_vol_s}\n"
                        f"Score:  {_score}  |  Regime: {_regime}"
                    )
            except Exception:
                pass
            _consecutive_losses["value"] = 0
            return True
        except Exception as pos_exc:
            log.warning("[POSITION] add échoué: %s", pos_exc)
            return False

    def _on_position_close(pos: Any, reason: Any) -> None:
        try:
            tracker_finalize_position(
                str(getattr(pos, "order_id", "")),
                float(getattr(pos, "current_price", 0.0) or pos.entry_price),
                getattr(reason, "value", str(reason)),
                fallback_position=_tracker_payload_from_position(pos),
            )
            _refresh_tracker_artifacts("close")
        except Exception as tracker_exc:
            log.warning(
                "[TrackerSystem] finalize échoué pour %s: %s", pos.symbol, tracker_exc
            )

        # ── PaperTradeRecorder — source de vérité exit ───────────────────────
        try:
            from paper_trading.recorder import get_recorder as _get_recorder

            _mae = getattr(pos, "mae_pct", None)
            _mfe = getattr(pos, "mfe_pct", None)
            _get_recorder().record_close(
                trade_id=str(getattr(pos, "order_id", "") or id(pos)),
                exit_price=float(getattr(pos, "current_price", 0.0) or pos.entry_price),
                pnl_usd=float(getattr(pos, "pnl_usd", 0.0) or 0.0),
                pnl_pct=float(getattr(pos, "pnl_pct", 0.0) or 0.0),
                reason=getattr(reason, "value", str(reason)),
                opened_at=float(getattr(pos, "opened_at", 0.0) or 0.0),
                symbol=str(getattr(pos, "symbol", "")),
                side=getattr(
                    getattr(pos, "side", None), "value", str(getattr(pos, "side", ""))
                ),
                size_usd=float(getattr(pos, "size_usd", 0.0) or 0.0),
                mode=str(getattr(pos, "mode", "futures_demo")),
                mae_pct=float(_mae) if _mae is not None else None,
                mfe_pct=float(_mfe) if _mfe is not None else None,
            )
        except Exception as _rec_exc:
            log.debug("[PaperRecorder] close échoué: %s", _rec_exc)

        sign = "+" if pos.pnl_usd >= 0 else ""
        _age_min = (time.time() - float(getattr(pos, "opened_at", time.time()))) / 60
        _age_s = (
            f"{int(_age_min // 60)}h{int(_age_min % 60):02d}m"
            if _age_min >= 60
            else f"{int(_age_min)}m{int((_age_min % 1) * 60):02d}s"
        )
        _close_msg = (
            f"SORTIE {pos.side.value.upper()} — {pos.symbol}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Entry:  ${pos.entry_price:.4g}  →  Exit: ${pos.current_price:.4g}\n"
            f"PnL:    {sign}${pos.pnl_usd:.2f}  ({sign}{pos.pnl_pct:.2%})\n"
            f"Raison: {reason.value.upper()}  |  Duree: {_age_s}\n"
            f"Compte: {pos.subaccount}"
        )
        _telegram(_close_msg)
        if _portfolio_bot is not None:
            try:
                _portfolio_bot.send(_close_msg)
            except Exception:
                pass

    pos_manager.on_close(_on_position_close)

    if P6_SAFE_MODE:
        log.info(
            "[P6] SAFE MODE — RSM scellé au démarrage, "
            "boucles adaptatives désactivées (threshold fixe)"
        )
    else:
        log.info("[P6] Mode adaptatif — ATE + RegimeSmoother + REGIME_MISMATCH actifs")

    _gate_min_score = int(os.getenv("SIGNAL_MIN_SCORE", "70"))
    _gate_require_confirmed = (
        os.getenv("GATE_REQUIRE_CONFIRMED", "true").lower() == "true"
    )
    gate = _profile_bootstrap_step(
        "global_risk_gate",
        lambda: runtime.GlobalRiskGate(
            min_signal_score=_gate_min_score,
            require_confirmed=_gate_require_confirmed,
            safe_mode=P6_SAFE_MODE,
        ),
    )
    engine = _profile_bootstrap_step("live_signal_engine", runtime.LiveSignalEngine)
    advisor = _profile_bootstrap_step("ai_advisor", runtime.AIAdvisor)
    shadow = _profile_bootstrap_step(
        "shadow_execution", lambda: runtime.ShadowExecutionEngine(risk_gate=gate)
    )
    watchdog = _profile_bootstrap_step(
        "performance_watchdog", runtime.PerformanceWatchdog
    )
    memory = _profile_bootstrap_step(
        "strategy_memory_store", runtime.StrategyMemoryStore
    )

    # Meta-Strategy Engine — personnalité adaptée au régime
    meta_engine = _profile_bootstrap_step(
        "meta_strategy",
        lambda: runtime.MetaStrategyEngine(safe_mode=P6_SAFE_MODE),
    )

    # Strategy Ranker — notation et auto-promotion/rétrogradation
    ranker = _profile_bootstrap_step("strategy_ranker", runtime.StrategyRanker)

    # Self-Awareness Engine — détection dérive comportementale/perf/infra
    def _on_awareness_change(state: Any) -> None:
        if state.level >= runtime.DangerLevel.WARNING:
            runtime_authority.request_safe_mode(
                "self_awareness",
                f"level={state.level.name}",
            )
        else:
            runtime_authority.clear_safe_mode_request("self_awareness")

        if state.level >= runtime.DangerLevel.WARNING:
            drifts_msg = " | ".join(d.message for d in state.active_drifts[:3])
            _telegram(
                f"SELF-AWARENESS — {state.level.name}\n"
                f"Taille: x{state.size_factor:.1f} | Safe mode: {state.safe_mode}\n"
                f"Dérives: {drifts_msg}"
            )

    awareness_engine = _profile_bootstrap_step(
        "self_awareness",
        lambda: runtime.SelfAwarenessEngine(on_level_change=_on_awareness_change),
    )
    _awareness_ref["engine"] = awareness_engine  # expose pour /RESUME callback

    # No-Trade Intelligence — refus intelligents
    no_trade_layer = _profile_bootstrap_step(
        "no_trade_intelligence", runtime.NoTradeIntelligence
    )

    # Conviction Engine — 4 niveaux de conviction
    conviction_engine = _profile_bootstrap_step(
        "conviction_engine", runtime.ConvictionEngine
    )

    # Decision Quality Engine — note qualité indépendamment du résultat
    dqe = _profile_bootstrap_step("decision_quality", runtime.DecisionQualityEngine)

    # Portfolio Brain — risque global du portefeuille (corrélation, concentration, exposition)
    portfolio_brain = _profile_bootstrap_step(
        "portfolio_brain",
        lambda: runtime.PortfolioBrain(total_capital=real_capital),
    )

    # Capital Allocation Engine — taille optimale par Kelly/EV/volatilité
    capital_engine = _profile_bootstrap_step(
        "capital_engine",
        lambda: runtime.CapitalAllocationEngine(total_capital=real_capital),
    )

    # ── System Controller — méta-régulateur post-trade ────────────────────────
    # Complète le Decision Layer : trade_gate gère le signal (pre-trade),
    # system_controller gère l'état du système (post-trade).
    # Règle stricte : appelé uniquement après fermeture d'un trade,
    # jamais pendant un cycle d'analyse. Séparation micro/macro.
    _sc_state: dict = {
        "risk_factor": 1.0,  # REDUCE_RISK réduit, RESUME reset à 1.0
        "tp_factor": 1.0,  # ADJUST_TP amplifie, borné [0.8, 1.5]
        "sl_factor": 1.0,  # ADJUST_SL réduit, borné [0.7, 1.3]
        "trade_count": 0,
        "cooldowns": {},  # action_type → last_fired_timestamp
    }
    _SC_MIN_TRADES = 5  # pas de décision avant N trades fermés
    _SC_MIN_CONFIDENCE = 0.65  # décisions incertaines ignorées
    _SC_COOLDOWNS: dict[str, float] = {
        "STOP_TRADING": 3600.0,
        "REDUCE_RISK": 1800.0,
        "ADJUST_TP": 900.0,
        "ADJUST_SL": 900.0,
        "RESUME_TRADING": 600.0,
        "APPLY_META": 300.0,
    }

    try:
        from tracker_system.autonomous.auto_decision_engine import (
            AutoDecisionOrchestrator as _ADO,
        )

        _system_controller = _ADO(
            initial_config={
                "trading_enabled": True,
                "tp": float(os.getenv("DEFAULT_TP_PCT", "0.04")),
                "sl": float(os.getenv("DEFAULT_SL_PCT", "0.02")),
                "position_size": 1.0,
            },
            limits={
                "max_tp_increase": 0.5,
                "max_sl_decrease": 0.3,
                "max_position_reduction": 0.75,
            },
            log_file="logs/system_controller_decisions.jsonl",
        )
        log.info("[SystemController] AutoDecisionOrchestrator initialisé")
    except Exception as _sc_init_exc:
        _system_controller = None
        log.warning("[SystemController] init échoué (non bloquant): %s", _sc_init_exc)

    mistake_memory: Any = None

    def _get_mistake_memory() -> Any:
        nonlocal mistake_memory
        if mistake_memory is None:
            mistake_memory = _profile_bootstrap_step(
                "mistake_memory", runtime.MistakeMemory
            )
            mm_stats = _stats_dict(mistake_memory.stats())
            log.info(
                "[MistakeMemory] %d erreurs memorisees | %d regles actives",
                int(mm_stats.get("total", 0) or 0),
                int(mm_stats.get("rules_active", 0) or 0),
            )
        return mistake_memory

    if not (advisor_only and defer_optional_intel):
        _get_mistake_memory()

    # Executive Override — commandement supreme (domine toutes les couches)
    def _on_override_change(
        old_level: Any, new_level: Any, triggers: list[str]
    ) -> None:
        trigger_str = " | ".join(triggers[:3])
        _telegram(
            f"EXECUTIVE OVERRIDE — {old_level.name} -> {new_level.name}\n"
            f"Triggers: {trigger_str}\n"
            f"Taille: x{_SIZE_FACTORS_MAP.get(new_level.value, 0):.0%}"
        )

    _SIZE_FACTORS_MAP = {0: 1.0, 1: 0.5, 2: 0.25, 3: 0.10, 4: 0.0}
    executive_override = _profile_bootstrap_step(
        "executive_override",
        lambda: runtime.ExecutiveOverride(
            total_capital=real_capital,
            on_level_change=_on_override_change,
        ),
    )

    # Black Box Recorder — boite noire indestructible
    black_box = _profile_bootstrap_step("black_box", runtime.BlackBox)
    _black_box_ref["instance"] = black_box
    black_box.record_system_event(
        "DEMARRAGE", f"capital={real_capital:.0f} mode={trading_mode}"
    )
    # Marqueur BOOT automatique — plus jamais de redémarrage anonyme (cf. incident
    # 2026-07-07 : 3 arrêts sans auteur identifié entre 04:00 et 04:08 UTC).
    black_box.record_system_event(
        "BOOT",
        f"pid={os.getpid()} invocation_id={os.getenv('INVOCATION_ID', 'absent')} "
        f"cause={_boot_cause_text(_boot_lock_preexisted, _boot_previous_pid)}",
    )
    # Marqueur EPOCH — ADR-0012 + addendum (SEC-01, 2026-07-09). Réaffirmé à
    # chaque boot (fait constant, pas un événement ponctuel) : la contamination
    # consecutive_losses (5 consommateurs : RiskGovernor, MetaStrategyEngine,
    # ExecutiveOverride, check_hard_limits, MistakeMemory jamais atteint) est
    # close depuis le gate SEC-01 (PAPER_TRADING_ENABLED + LIVE_TRADING_CONFIRMED).
    # 47% de la fenetre CLEAN_DATA_SINCE v1 etait contaminee (27.9% par le bruit
    # seul), >=278 MISSED_WIN concernes (plancher). La borne v2 (01:16Z) reposait
    # sur un deploiement silencieusement partiel (SEC-01 jamais charge) —
    # generateur nominal depuis CLEAN_DATA_SINCE_V3, voir addendum ADR-0012,
    # scripts/data_quality.py.
    from scripts.data_quality import CLEAN_DATA_SINCE_V3 as _epoch_v3

    black_box.record_system_event(
        "EPOCH",
        f"SEC-01 actif depuis {_epoch_v3.isoformat()} (ADR-0012 + addendum) — fin "
        f"de la contamination consecutive_losses (5 consommateurs). Generateur nominal.",
    )

    regret_engine: Any = None

    def _get_regret_engine() -> Any:
        nonlocal regret_engine
        if regret_engine is None:
            regret_engine = _profile_bootstrap_step(
                "regret_engine", runtime.RegretEngine
            )
            regret_record_count, regret_candidate_count = _get_regret_counts(
                regret_engine
            )
            log.info(
                "[RegretEngine] %d records charges | %d candidats en attente",
                regret_record_count,
                regret_candidate_count,
            )
        return regret_engine

    if not (advisor_only and defer_optional_intel):
        _get_regret_engine()

    # ── Observabilité P0-P3 — Decision Event Bus + observers ─────────────────
    # Chargement conditionnel : aucun crash si les modules sont absents.
    _decision_event_bus: Any = None
    _obs_rejection_store: Any = None
    _obs_regret_scheduler: Any = None
    try:
        from config.feature_flags import (
            FEATURE_DECISION_EXPLAINER,
            FEATURE_EVENT_BUS,
            FEATURE_REGRET_SCHEDULER,
            FEATURE_REJECTION_STORE,
        )

        if FEATURE_EVENT_BUS:
            from observability.decision_event_bus import get_bus as _get_obs_bus

            _decision_event_bus = _get_obs_bus()

            # Listener P1 — Telegram enrichi
            if FEATURE_DECISION_EXPLAINER:
                from observability.decision_explainer import explain as _obs_explain

                def _telegram_explainer_listener(obs: Any) -> None:  # type: ignore[misc]
                    try:
                        msg = _obs_explain(obs, obs.cycle)
                        _telegram.decision_report(msg)
                    except Exception as _e:
                        log.debug("[OBS/Telegram] explainer: %s", _e)

                _decision_event_bus.subscribe(_telegram_explainer_listener)
                log.info("[OBS] Listener Telegram enrichi abonné")

            # Listener P2 — Rejection Store
            if FEATURE_REJECTION_STORE:
                from observability.rejection_store import (
                    RejectionStore as _RejectionStore,
                )

                _obs_rejection_store = _RejectionStore()
                _decision_event_bus.subscribe(_obs_rejection_store.on_observation)
                log.info("[OBS] Listener RejectionStore abonné")

            # Listener P3 — Regret Scheduler multi-horizon
            if FEATURE_REGRET_SCHEDULER:
                from observability.regret_scheduler import (
                    RegretScheduler as _RegretScheduler,
                )

                _obs_regret_scheduler = _RegretScheduler()
                _obs_regret_scheduler.start()
                _decision_event_bus.subscribe(_obs_regret_scheduler.on_observation)
                log.info("[OBS] Listener RegretScheduler abonné (7 horizons)")

    except Exception as _obs_init_exc:
        log.warning(
            "[OBS] Init observabilité échouée (non bloquant): %s", _obs_init_exc
        )
        _decision_event_bus = None
        _obs_rejection_store = None
        _obs_regret_scheduler = None

    # ── OBS-001 — SystemSnapshot provider + event bus ─────────────────────────
    _snapshot_provider = InMemorySnapshotProvider()
    _snapshot_block_stats = BlockStatsAccumulator()
    _snapshot_bus = get_snapshot_bus()
    from infra.wallet_sync import get_wallet_sync as _get_wallet_sync_snap

    _wallet_sync_singleton = _get_wallet_sync_snap()

    chief_officer: Any = None

    def _get_chief_officer() -> Any:
        nonlocal chief_officer
        if chief_officer is None:
            chief_officer = _profile_bootstrap_step(
                "chief_officer", runtime.ChiefOfficer
            )
        return chief_officer

    intel_reporter: Any = None

    def _get_intel_reporter() -> Any:
        nonlocal intel_reporter
        if intel_reporter is None:
            intel_reporter = _profile_bootstrap_step(
                "intel_reporter", runtime.SystemIntelReporter
            )
        return intel_reporter

    threat_radar = _profile_bootstrap_step("threat_radar", runtime.ThreatRadar)
    log.info("[ThreatRadar] initialise")

    # MetaLearner — sélection exit par régime (Phase 1)
    meta_learner = _profile_bootstrap_step("meta_learner", runtime.MetaLearner)
    log.info("[MetaLearner] %d entrées en mémoire", len(meta_learner.memory))
    _meta_pnl_buffer: dict[str, list[float]] = {}

    def _stop_runtime_services() -> None:
        kill_switch.stop()
        exchange_monitor.stop()
        healer.stop()
        if _portfolio_bot is not None:
            try:
                _portfolio_bot.stop()
            except Exception:
                pass
        if _chart_server is not None:
            try:
                _chart_server.stop()
            except Exception:
                pass
        if prewarm_executor is not None:
            prewarm_executor.shutdown(wait=False, cancel_futures=False)
        pos_manager.stop()

    def _sc_run_cycle(pos: Any, pm_stats: dict) -> None:
        """Exécute un cycle system_controller post-trade avec guards anti-bruit.

        Guards actifs :
        - min_trades : silence les N premiers trades (données insuffisantes)
        - min_confidence : ignore les décisions incertaines
        - cooldown par type d'action : évite le spam paramétrique
        - bounds sur les facteurs : protège contre la dérive runaway
        """
        if _system_controller is None:
            return
        _sc_state["trade_count"] += 1
        if _sc_state["trade_count"] < _SC_MIN_TRADES:
            return
        now = time.time()
        _mfe = float(getattr(pos, "mfe_pct", 0.0) or 0.0)
        _pnl = float(getattr(pos, "pnl_pct", 0.0) or 0.0)
        metrics = {
            "efficiency": (_pnl / _mfe) if _mfe > 0.001 else 0.5,
            "mae_pct": float(getattr(pos, "mae_pct", 0.0) or 0.0),
        }
        risk_state = {
            "drawdown": max(
                0.0,
                -_to_float(pm_stats.get("total_pnl_usd", 0.0)) / max(1.0, real_capital),
            ),
            "loss_streak": _consecutive_losses["value"],
        }
        meta_suggestion = None
        try:
            if hasattr(meta_learner, "suggest"):
                meta_suggestion = meta_learner.suggest()
        except Exception:
            pass

        _, decision, _ = _system_controller.run_decision_cycle(
            metrics=metrics,
            risk_state=risk_state,
            meta_suggestion=meta_suggestion,
        )

        if decision.action == "NO_ACTION" or decision.confidence < _SC_MIN_CONFIDENCE:
            return

        cooldown = _SC_COOLDOWNS.get(decision.action, 600.0)
        if now - _sc_state["cooldowns"].get(decision.action, 0.0) < cooldown:
            log.debug(
                "[SystemController] %s en cooldown (%.0fs restants)",
                decision.action,
                cooldown - (now - _sc_state["cooldowns"].get(decision.action, 0.0)),
            )
            return

        _sc_state["cooldowns"][decision.action] = now
        log.info(
            "[SystemController] %s — %s (conf=%.0f%%)",
            decision.action,
            decision.reason,
            decision.confidence * 100,
        )

        if decision.action == "REDUCE_RISK":
            factor = decision.params.get("position_size_factor", 0.5)
            _sc_state["risk_factor"] = max(0.25, _sc_state["risk_factor"] * factor)
            _telegram(
                f"[AUTO] REDUCE_RISK ×{factor:.0%}"
                f" → taille effective={_sc_state['risk_factor']:.0%}\n"
                f"{decision.reason}"
            )

        elif decision.action == "RESUME_TRADING":
            _sc_state["risk_factor"] = 1.0
            log.info("[SystemController] RESUME — risk_factor reset 1.0")

        elif decision.action == "ADJUST_TP":
            factor = decision.params.get("tp_factor", 1.15)
            _sc_state["tp_factor"] = min(1.5, max(0.8, _sc_state["tp_factor"] * factor))
            log.info(
                "[SystemController] ADJUST_TP → tp_factor=%.3f", _sc_state["tp_factor"]
            )

        elif decision.action == "ADJUST_SL":
            factor = decision.params.get("sl_factor", 0.85)
            _sc_state["sl_factor"] = min(1.3, max(0.7, _sc_state["sl_factor"] * factor))
            log.info(
                "[SystemController] ADJUST_SL → sl_factor=%.3f", _sc_state["sl_factor"]
            )

        # STOP_TRADING et APPLY_META sont gérés directement par ActionExecutor
        # dans run_decision_cycle : state_machine.transition("HALTED") pour STOP,
        # mutation de config pour APPLY_META.

    # Callback PositionManager → enregistre le résultat dans le ranker
    def _on_position_close_rank(pos: Any, reason: Any) -> None:
        try:
            pos_regime = getattr(pos, "regime", "unknown")
            # Ranker
            ranker.record_trade(
                strategy_name=pos.symbol,
                regime=pos_regime,
                pnl_pct=pos.pnl_pct,
                sharpe=(
                    max(0.0, pos.pnl_pct / max(0.001, abs(pos.pnl_pct)))
                    if pos.pnl_pct
                    else 0.0
                ),
                drawdown=max(0.0, -pos.pnl_pct) if pos.pnl_pct < 0 else 0.0,
            )
            # Meta-strategy
            meta_engine.record_trade_result(
                regime=pos_regime,
                personality=pos.symbol,
                pnl_pct=pos.pnl_pct,
            )
            # Self-Awareness — nourrit le détecteur de dérive
            awareness_engine.record_trade(
                pnl_pct=pos.pnl_pct,
                regime=pos_regime,
                personality=pos.symbol,
                order_size=pos.size_usd,
            )
            # Decision Quality — ferme la décision associée
            dqe.close_decision(pos.order_id, pos.pnl_pct)
            # Mistake Memory — analyse l'erreur et génère des règles
            try:
                side_signal = (
                    "BUY"
                    if getattr(pos, "side", None) and pos.side.value == "long"
                    else "SELL"
                )
                _get_mistake_memory().record_trade_result(
                    order_id=pos.order_id,
                    symbol=pos.symbol,
                    signal=side_signal,
                    score=getattr(pos, "signal_score", 70),
                    regime=pos_regime,
                    conviction_level=getattr(pos, "conviction_level", "medium"),
                    pnl_pct=pos.pnl_pct,
                    context_features=getattr(pos, "entry_features", {}),
                    signal_age_sec=getattr(pos, "signal_age_sec", 0.0),
                    consecutive_losses=_consecutive_losses["value"],
                    exit_reason=getattr(pos, "close_reason", ""),
                    personality=getattr(pos, "symbol", ""),
                    entry_price=getattr(pos, "entry_price", 0.0),
                    exit_price=getattr(pos, "current_price", 0.0),
                    opened_at=getattr(pos, "opened_at", 0.0),
                    tp_pct=getattr(pos, "tp_pct", 0.0),
                    sl_pct=getattr(pos, "sl_pct", 0.0),
                    tp_price=getattr(pos, "tp_price", 0.0),
                    sl_price=getattr(pos, "sl_price", 0.0),
                    atr_entry=getattr(pos, "atr", 0.0),
                )
            except Exception as _me:
                log.debug("[MistakeMemory] record échoué: %s", _me)
            # Mise à jour compteur pertes consécutives + Executive Override
            if pos.pnl_pct < 0:
                _consecutive_losses["value"] += 1
                # ── PROTECTIONS: Enregistre SL pour cooldown ──
                last_loss_time[pos.symbol] = time.time()
            else:
                _consecutive_losses["value"] = 0
            # Libère la protection same_direction après fermeture de position
            # (last_loss_time couvre déjà la re-entry immédiate après perte)
            last_trade_signal.pop(pos.symbol, None)
            # Alimenter l'Override avec les métriques de session
            try:
                pm_stats_live = _stats_dict(pos_manager.stats())
                open_pnl_pct = _to_float(pm_stats_live.get("open_pnl_usd", 0.0)) / max(
                    1.0, real_capital
                )
                executive_override.update(
                    loss_streak=_consecutive_losses["value"],
                    open_pnl_pct=open_pnl_pct,
                    daily_loss_pct=max(
                        0.0,
                        -_to_float(pm_stats_live.get("total_pnl_usd", 0.0))
                        / max(1.0, real_capital),
                    ),
                )
            except Exception:
                pass
            # Black Box — fermeture position
            try:
                black_box.record_position_closed(pos, reason)
            except Exception:
                pass
            # P9 — PerformanceSupervisor + PortfolioIntelligence
            try:
                if _perf_supervisor is not None:
                    _perf_supervisor.record_trade(pnl_pct=pos.pnl_pct)
                if _portfolio_intel is not None:
                    _portfolio_intel.close_position(pos.symbol)
            except Exception:
                pass
            # P10-F — KPI Tracker (Win Rate / Sharpe / Max DD)
            try:
                if _p10_kpi is not None:
                    from capital_deployment.phase_kpi_tracker import TradeRecord as _TR

                    _p10_kpi.record_trade(
                        _TR(
                            ts=time.time(),
                            pnl=getattr(pos, "pnl_usd", pos.pnl_pct * pos.size_usd),
                            symbol=pos.symbol,
                            side=(
                                "buy"
                                if getattr(pos, "side", None)
                                and pos.side.value == "long"
                                else "sell"
                            ),
                            entry_price=pos.entry_price,
                            exit_price=getattr(pos, "current_price", 0.0),
                            signed=True,
                        )
                    )
            except Exception:
                pass
            # MetaLearner — accumule PnL par régime, apprend tous les 5 trades
            try:
                buf = _meta_pnl_buffer.setdefault(pos_regime, [])
                buf.append(pos.pnl_pct)
                if len(buf) >= 5:
                    wins = sum(1 for p in buf if p > 0)
                    win_rate = wins / len(buf)
                    avg_pnl = sum(buf) / len(buf)
                    sharpe = avg_pnl * win_rate * 10
                    trailing = getattr(pos, "trailing", 0) or 0
                    exit_type = "trailing" if trailing > 0 else "tp_sl"
                    meta_learner.learn(
                        context={
                            "regime": pos_regime,
                            "volatility": getattr(pos, "volatility", 0.015),
                        },
                        decision={
                            "exit_type": exit_type,
                            "tp": getattr(pos, "tp_pct", 0.04),
                            "sl": getattr(pos, "sl_pct", 0.02),
                            "trail_pct": trailing or None,
                        },
                        performance={
                            "sharpe": round(sharpe, 4),
                            "win_rate": round(win_rate, 4),
                            "avg_pnl": round(avg_pnl, 6),
                            "n_trades": len(buf),
                        },
                    )
                    log.info(
                        "[MetaLearner] Apprentissage %s: exit=%s wr=%.0f%% sharpe=%.3f n=%d",
                        pos_regime,
                        exit_type,
                        win_rate * 100,
                        sharpe,
                        len(buf),
                    )
                    buf.clear()
            except Exception as _mle:
                log.debug("[MetaLearner] learn échoué: %s", _mle)

            # ── System Controller — méta-régulateur post-trade ────────────────
            try:
                _sc_run_cycle(pos, _stats_dict(pos_manager.stats()))
            except Exception as _sc_exc:
                log.debug("[SystemController] cycle échoué: %s", _sc_exc)

        except Exception as _re:
            log.debug("[Feedback] record échoué: %s", _re)

    pos_manager.on_close(_on_position_close_rank)

    _consecutive_losses = {"value": 0}  # pertes trading consécutives (meta strategy)
    _consecutive_exec_errors = {"value": 0}  # échecs d'exécution techniques (P10-F)

    # ── PROTECTIONS OBLIGATOIRES POUR MODE TEST ───────────────────────────────────
    # #1 Cooldown après perte (5 min)
    last_loss_time: dict[str, float] = {}
    # #2 Pas de re-entry même direction
    last_trade_signal: dict[str, str] = {}
    # #3 Max 10 trades par heure
    trades_this_hour: dict[str, list[float]] = {}

    _t_bootstrap_end = time.perf_counter()
    _send_email(
        "Système démarré",
        f"Crypto AI Terminal démarré avec succès.\n"
        f"Symboles : {symbols}\n"
        f"Intervalle : {interval}s\n"
        f"Bootstrap : {_t_bootstrap_end - _t_main_start:.1f}s",
    )

    cycle = 0
    consecutive_errors = 0
    _clean_exit = False
    shed_optional_until_cycle = 0
    _last_intel_ts = 0.0  # timestamp du dernier briefing intel (bot 6h)

    # ── P12-B MetricsCollector + AlertEngine — source de données burn-in ─────
    _metrics_collector: Any = None
    _alert_engine_p12: Any = None
    _health_scorer_p12: Any = None
    try:
        from pathlib import Path as _MCPath

        from observability.alerting import AlertEngine as _AECls
        from observability.health_score import HealthScore as _HSCls
        from observability.metrics_collector import MetricsCollector as _MCCls

        _metrics_collector = _MCCls(
            capital_fn=lambda: real_capital,
            positions_fn=lambda: (
                len(pos_manager.get_open_positions())
                if hasattr(pos_manager, "get_open_positions")
                else 0
            ),
            initial_capital=real_capital,
        )
        _metrics_collector.set_boot_gate_cleared(True)
        _alert_engine_p12 = _AECls(
            alert_path=_MCPath("cache/startup/alerts.jsonl"),
            persist=True,
        )
        _health_scorer_p12 = _HSCls()
        log.info("[P12-B] MetricsCollector + AlertEngine initialises")
    except Exception as _mc_init_exc:
        log.debug("[P12-B] MetricsCollector non disponible: %s", _mc_init_exc)
    # ── Boucle de rétroaction adaptative ──────────────────────────────────────
    # _adaptive_regime : régime stable (confirmé sur N cycles consécutifs)
    # _regime_votes    : fenêtre glissante des N dernières observations
    # _activity_tracker: métriques d'inactivité du capital
    _adaptive_regime: str = "unknown"
    _regime_votes: list = []  # dernières N observations de régime
    _REGIME_STABILITY = int(
        os.getenv("REGIME_STABILITY_WINDOW", "3")
    )  # cycles à confirmer
    _last_mismatch_cycle: int = 0  # cooldown REGIME_MISMATCH
    _stalled_alerted: bool = False  # alerte TRADING_STALLED déjà envoyée
    _atr_last: float = 0.0  # P7 — ATR ratio moyen du cycle précédent → RiskGovernor

    # P7 — Risk Governor + Capital Throttle + Exposure Manager
    try:
        from quant_hedge_ai.agents.risk.capital_throttle import (
            CapitalThrottle as _CTCls,
        )
        from quant_hedge_ai.agents.risk.exposure_manager import (
            DynamicExposureManager as _DEMCls,
        )
        from quant_hedge_ai.agents.risk.risk_governor import RiskGovernor as _RGCls

        _risk_governor: Any = _RGCls()
        _capital_throttle: Any = _CTCls()
        _dyn_exposure: Any = _DEMCls(real_capital)
        log.info(
            "[P7] RiskGovernor + CapitalThrottle + DynamicExposureManager initialisés"
        )
    except Exception as _p7_exc:
        log.warning("[P7] Composants indisponibles: %s", _p7_exc)
        _risk_governor = None
        _capital_throttle = None
        _dyn_exposure = None

    # S2 — GovernanceAuditor : observateur constitutionnel permanent.
    # Indépendant de _OBS_AVAILABLE — fonctionne même sans stack observabilité complète.
    _gov_auditor: Any = None
    try:
        from governance.auditor import GovernanceAuditor as _GovAuditorCls

        _gov_auditor = _GovAuditorCls()
        log.info("[GovernanceAuditor] Initialisé — observateur constitutionnel actif")
    except Exception as _ga_exc:
        log.warning("[GovernanceAuditor] Indisponible: %s", _ga_exc)

    _safety_auditor: Any = None
    if _OBS_AVAILABLE:
        try:
            from system.safety_auditor import SystemSafetyAuditor as _SafetyAuditorCls

            module_registry.register(
                "global_risk_gate",
                priority=ModulePriority.CRITICAL,
                heartbeat_timeout_sec=max(interval * 2, 120),
                health_fn=lambda: gate is not None,
            )
            module_registry.register(
                "execution_engine",
                priority=ModulePriority.CRITICAL,
                heartbeat_timeout_sec=max(interval * 2, 120),
                health_fn=lambda: exec_engine is not None,
            )
            module_registry.register(
                "risk_governor",
                priority=ModulePriority.CRITICAL,
                heartbeat_timeout_sec=max(interval * 2, 120),
                health_fn=lambda: _risk_governor is not None,
            )
            if _risk_governor is None:
                module_registry.set_status(
                    "risk_governor",
                    ModuleStatus.UNHEALTHY,
                    "P7 component unavailable",
                )
            _safety_auditor = _SafetyAuditorCls(
                required_modules={
                    "global_risk_gate",
                    "execution_engine",
                    "risk_governor",
                },
                critical_modules={
                    "global_risk_gate",
                    "execution_engine",
                    "risk_governor",
                },
            )
            log.info("[P7] SystemSafetyAuditor initialisé")
        except Exception as _safety_boot_exc:
            log.warning("[P7] SystemSafetyAuditor indisponible: %s", _safety_boot_exc)

    # P7 — Circuit breakers
    global _cb_gate, _cb_mistake_memory
    _cb_registry_adapter: Any = None
    if _CB_AVAILABLE:
        _cb_gate = _CBClass(
            "global_risk_gate",
            fallback=SimpleNamespace(
                allowed=False,
                conditions={},
                failed=["gate_circuit_breaker"],
                warnings=[],
            ),
        )
        _cb_mistake_memory = _CBClass("mistake_memory", fallback=None)

        class _AdvisorCircuitBreakers:
            def snapshot_all(self) -> list[dict]:
                return [
                    cb.snapshot()
                    for cb in (_cb_gate, _cb_mistake_memory)
                    if cb is not None
                ]

        _cb_registry_adapter = _AdvisorCircuitBreakers()
        log.info("[P7] CircuitBreakers initialisés: gate + mistake_memory")

    # P8 — Strategy Allocator + Probation + Confidence + Correlation
    _strategy_allocator: Any = None
    _probation_system: Any = None
    _confidence_scorers: dict = {}
    _correlation_monitor: Any = None
    _p8_pers_map: dict = {}
    try:
        from quant_hedge_ai.agents.intelligence.confidence_scorer import (
            StrategyConfidenceScorer as _SCSCls,
        )
        from quant_hedge_ai.agents.intelligence.correlation_monitor import (
            CorrelationMonitor as _CMCls,
        )
        from quant_hedge_ai.agents.intelligence.strategy_allocator import (
            PERSONALITY_TO_STRATEGY as _P8PM,
        )
        from quant_hedge_ai.agents.intelligence.strategy_allocator import (
            STRATEGY_IDS as _P8_STRAT_IDS,
        )
        from quant_hedge_ai.agents.intelligence.strategy_allocator import (
            StrategyAllocator as _SACls,
        )
        from quant_hedge_ai.agents.intelligence.strategy_probation import (
            StrategyProbationSystem as _SPSCls,
        )

        _p8_pers_map = _P8PM
        _probation_system = _SPSCls()
        for _p8_sid in _P8_STRAT_IDS:
            _probation_system.register(_p8_sid)
            _confidence_scorers[_p8_sid] = _SCSCls(strategy_id=_p8_sid)
        _correlation_monitor = _CMCls()
        _strategy_allocator = _SACls(
            probation_system=_probation_system,
            confidence_scorers=_confidence_scorers,
            correlation_monitor=_correlation_monitor,
        )
        log.info(
            "[P8] StrategyAllocator + ProbationSystem initialisés (%d stratégies)",
            len(_P8_STRAT_IDS),
        )
    except Exception as _p8_boot_exc:
        log.warning("[P8] Composants indisponibles: %s", _p8_boot_exc)

    # P8 — Forbidden Patterns Registry (mémoire collective inter-stratégies)
    _forbidden_patterns_registry: Any = None
    try:
        from quant_hedge_ai.agents.intelligence.forbidden_patterns_registry import (
            ForbiddenPatternsRegistry as _FPRCls,
        )

        _forbidden_patterns_registry = _FPRCls()
        log.info("[P8] ForbiddenPatternsRegistry initialisé")
    except Exception as _fpr_boot_exc:
        log.warning("[P8/FPR] Indisponible: %s", _fpr_boot_exc)

    # Sweep Detection — perception de liquidité (SweepDetector + SweepOutcomeTracker)
    _sweep_detector: Any = None
    _sweep_outcome_tracker: Any = None
    try:
        from quant_hedge_ai.agents.intelligence.sweep_detector import (
            SweepDetector as _SDCls,
        )
        from quant_hedge_ai.agents.intelligence.sweep_outcome_tracker import (
            SweepOutcomeTracker as _SOTCls,
        )

        _sweep_detector = _SDCls()
        _sweep_outcome_tracker = _SOTCls()
        log.info("[Sweep] SweepDetector + SweepOutcomeTracker initialisés")
    except Exception as _sweep_boot_exc:
        log.warning("[Sweep] Composants indisponibles: %s", _sweep_boot_exc)

    # P9 — Meta Governance
    _health_monitor: Any = None
    _drift_detector: Any = None
    _self_monitoring: Any = None
    _anomaly_gov: Any = None
    _perf_supervisor: Any = None
    _portfolio_intel: Any = None
    try:
        from quant_hedge_ai.agents.intelligence.behavioral_drift_detector import (
            BehavioralDriftDetector as _BDDCls,
        )
        from quant_hedge_ai.agents.intelligence.performance_supervisor import (
            PerformanceSupervisor as _PSCls,
        )
        from quant_hedge_ai.agents.intelligence.self_monitoring_loop import (
            SelfMonitoringLoop as _SMLCls,
        )
        from quant_hedge_ai.agents.risk.anomaly_governance import (
            AnomalyGovernance as _AGCls,
        )
        from quant_hedge_ai.agents.risk.portfolio_intelligence import (
            PortfolioIntelligence as _PICls,
        )
        from quant_hedge_ai.agents.risk.system_health_monitor import (
            SystemHealthMonitor as _SHMCls,
        )

        _health_monitor = _SHMCls()
        _drift_detector = _BDDCls()
        _self_monitoring = _SMLCls()
        _anomaly_gov = _AGCls()
        _perf_supervisor = _PSCls()
        _portfolio_intel = _PICls()
        log.info("[P9] Meta Governance initialisée (6 composants)")
    except Exception as _p9_boot_exc:
        log.warning("[P9] Composants indisponibles: %s", _p9_boot_exc)

    # S3 — Telegram alerts + shadow refusals tracker
    global _telegram_alert, _shadow_s3, _virtual_portfolio
    if _S3_TELEGRAM_AVAILABLE:
        _telegram_alert = _TelegramAlertCls()
        log.info("[S3] TelegramAlert initialisé")
    if _S3_SHADOW_AVAILABLE:
        _shadow_s3 = _ShadowTrackerCls()
        log.info("[S3] ShadowTracker initialisé")

    # MexcSimulator — actif si advisor-only OU si PAPER_TRADING_ENABLED=true.
    # Fonctionne en miroir indépendant du live : capital propre $10-100, pas de gate portefeuille.
    if advisor_only or _paper_trading_enabled:
        try:
            from infra.mexc_reader import MexcReader as _MexcReaderCls
            from paper_trading.mexc_simulator import MexcSimulator as _SimCls

            _mexc_reader_sim = _MexcReaderCls()
            _vp_tg_fn = _telegram_alert.info if _telegram_alert else None
            _virtual_portfolio = _SimCls(
                mexc_reader=_mexc_reader_sim,
                telegram_fn=_vp_tg_fn,
            )
            _virtual_portfolio.start()
            log.info("[SIM] MexcSimulator initialise")
        except Exception as _vp_exc:
            log.warning("[SIM] Non disponible: %s", _vp_exc)

    # P6 — Adaptive Core
    _ate: Any = _profile_bootstrap_step(
        "adaptive_threshold_engine",
        lambda: runtime.AdaptiveThresholdEngine(safe_mode=P6_SAFE_MODE),
    )
    _regime_smoother: Any = _profile_bootstrap_step(
        "regime_transition_smoother",
        lambda: runtime.RegimeTransitionSmoother(safe_mode=P6_SAFE_MODE),
    )
    _regime_tracker: Any = _profile_bootstrap_step(
        "regime_state_tracker", runtime.RegimeStateTracker
    )
    try:
        from quant_hedge_ai.agents.intelligence.activity_tracker import (
            ActivityTracker as _ActivityTrackerCls,
        )

        _activity_tracker: Any = _ActivityTrackerCls()
    except Exception:
        _activity_tracker = None

    try:
        from quant_hedge_ai.agents.intelligence.behavioral_stability_monitor import (
            BehavioralStabilityMonitor as _BSMCls,
        )

        _stability_monitor: Any = _BSMCls(
            threshold_baseline=int(os.getenv("SIGNAL_MIN_SCORE", "70"))
        )
    except Exception:
        _stability_monitor = None

    # ── Initialisation unique des composants d'observabilité ─────────────────
    try:
        from system.position_reconciler import PositionReconciler as _RecCls
        from system.state_machine import get_state_machine as _get_sm_boot

        _sm_boot = _get_sm_boot()
        # Amorcer last_successful_order_at si des positions existent déjà au boot
        if (
            hasattr(pos_manager, "get_open_positions")
            and pos_manager.get_open_positions()
        ):
            _sm_boot.update_heartbeat(
                n_signals=0,
                n_orders=1,
                exchange_ok=True,
                open_positions=len(pos_manager.get_open_positions()),
            )
        _position_reconciler = _RecCls(_get_exchange_futures(exec_engine), pos_manager)
    except Exception as _obs_boot_exc:
        log.debug("[Observability] init boot échoué: %s", _obs_boot_exc)
        _position_reconciler = None

    # ── State Integrity Audit — truth arbitration layer ───────────────────────
    _integrity_audit: Any = None
    try:
        from system.state_integrity import StateIntegrityAudit as _SIACls

        _integrity_audit = _SIACls()
        log.info(
            "[Integrity] StateIntegrityAudit initialisé (every=%d cycles)",
            _integrity_audit._every,
        )
    except Exception as _sia_exc:
        log.warning("[Integrity] StateIntegrityAudit indisponible: %s", _sia_exc)

    _p8_transition_cache: tuple | None = None  # (next_regime, prob) du cycle précédent

    while True:
        cycle += 1
        cycle_completed = False
        shed_optional_work = cycle <= shed_optional_until_cycle

        if _OBS_AVAILABLE:
            try:
                heartbeat_system.beat("advisor_loop")
                module_registry.heartbeat("advisor_loop")
            except Exception:
                pass

        # ── Kill switch check ──────────────────────────────────────────────────
        if kill_switch.is_halted() or _halt_requested.is_set():
            log.critical("[main] Kill switch actif — boucle suspendue")
            _telegram(
                "Boucle suspendue par Kill Switch. Envoyer /RESUME pour reprendre."
            )
            # Attendre que l'opérateur envoie /RESUME.
            # _halt_requested.clear() est appelé dans _on_resume.
            # Intervalle 0.5s pour une reprise quasi-immédiate après /RESUME.
            while kill_switch.is_halted() or _halt_requested.is_set():
                time.sleep(0.5)
            log.info("[main] Kill switch levé — reprise boucle")
            _telegram("Kill Switch leve — reprise du cycle normal.")
            # Réinitialise l'état d'urgence P10-F après intervention opérateur
            if _p10_emergency is not None:
                _p10_emergency.reset()
            if "_consecutive_exec_errors" in dir():
                _consecutive_exec_errors["value"] = 0
            continue

        # ── P10-F Emergency Stop check ─────────────────────────────────────────
        if _p10_emergency is not None:
            try:
                _p10_metrics = {
                    "current_drawdown": (
                        _capital_throttle.drawdown_pct
                        if "_capital_throttle" in dir()
                        and _capital_throttle is not None
                        else 0.0
                    ),
                    "consecutive_tech_errors": 0,  # géré par OperationalState
                    "blackbox_inaccessible_cycles": 0,
                    "killswitch_triggered": kill_switch.is_halted(),
                    "invalid_signature_detected": False,
                    "api_key_compromised": False,
                    "exchange_down_s": 0.0,
                    "new_anomaly_suspensions": 0,
                }
                _p10_was_active = _p10_emergency.is_emergency_active()
                _p10_trigger = _p10_emergency.check(_p10_metrics)
                if _p10_trigger and not _p10_was_active:
                    log.critical("[P10-F] Emergency stop: %s", _p10_trigger.details)
                    _telegram(
                        f"P10-F EMERGENCY STOP\nCritère: {_p10_trigger.criteria.value}\n{_p10_trigger.details}"
                    )
            except Exception as _p10_chk_exc:
                log.debug("[P10-F] Emergency check error: %s", _p10_chk_exc)

        # ── Safe mode check ────────────────────────────────────────────────────
        if _runtime_safe_mode_active():
            log.warning("[main] Cycle %d — SAFE MODE actif (observation seule)", cycle)

        log.info("--- Cycle %d ---", cycle)
        _t_cycle_start = time.perf_counter()
        try:
            if cycle == 1 and (prewarm_futures or prewarm_mtf_futures):
                # Attendre les futures avec un timeout court par future (non-bloquant).
                # Si un fetch est lent, on continue sans lui — cycle 1 fetche à la volée.
                warmup_timeout = float(os.getenv("ADVISOR_PREWARM_TIMEOUT", "12"))
                from concurrent.futures import FIRST_COMPLETED as _FC
                from concurrent.futures import wait as _fut_wait

                all_futures = list(prewarm_futures.values()) + list(
                    prewarm_mtf_futures.values()
                )
                _deadline = time.perf_counter() + warmup_timeout
                _remaining = list(all_futures)
                while _remaining and time.perf_counter() < _deadline:
                    _done, _remaining = _fut_wait(
                        _remaining,
                        timeout=min(2.0, _deadline - time.perf_counter()),
                        return_when=_FC,
                    )
                    for _f in _done:
                        try:
                            _f.result()
                        except Exception as exc:
                            log.warning("[Warmup] Prechauffage echoue: %s", exc)
                if _remaining:
                    log.info(
                        "[Warmup] %d fetch(s) incomplet(s) — cycle 1 fetche a la volee",
                        len(_remaining),
                    )
                    for _f in _remaining:
                        _f.cancel()
                _t_warmup_end = time.perf_counter()
                prewarm_futures.clear()
                prewarm_mtf_futures.clear()

            # Maintenance ranker — oublie les stratégies stales
            ranker.auto_demote()

            # ── Universe sync — injection automatique de nouveaux symboles ────
            # Vérifie toutes les sync_every cycles si le service a découvert
            # de nouvelles paires. Crée les scanners manquants à la volée.
            if _universe_service and cycle % _universe_service.sync_every == 0:
                try:
                    _new_universe_syms = _universe_service.drain_new_symbols()
                    for _ns in _new_universe_syms:
                        if _ns not in scanners["1h"]:
                            scanners["1h"][_ns] = runtime.MarketScanner(
                                symbols=[_ns], timeframe="1h", limit=ADVISOR_1H_LIMIT
                            )
                            scanners["mtf"][_ns] = runtime.MultiTimeframeScanner(
                                symbols=[_ns], refresh_every=MTF_REFRESH_EVERY
                            )
                            symbols.append(_ns)
                            log.info(
                                "[Universe] +%s injecté dans le scan (total: %d sym)",
                                _ns,
                                len(symbols),
                            )
                except Exception as _use:
                    log.debug("[Universe] Sync erreur cycle %d: %s", cycle, _use)
            # ─────────────────────────────────────────────────────────────────

            # Mise à jour du capital réel en début de cycle (balance live)
            try:
                fresh_capital = exec_engine.fetch_available_capital()
                if fresh_capital > 0:
                    real_capital = fresh_capital
                    portfolio_brain.update_capital(real_capital)
                    capital_engine.update_capital(real_capital)
            except Exception:
                pass

            # ── Runtime config — rechargement à chaud chaque cycle ────────────
            # GOUVERNANCE : GATE_MIN_SCORE_OVERRIDE et FORCE_TEST_EXECUTION sont
            # des variables de gouvernance — elles ne peuvent jamais être rechargées
            # depuis un fichier JSON externe sans redémarrage du processus.
            # Modifier ces valeurs à chaud contourne G4 (gate) et I-14 (fail-closed).
            # Elles sont lues à chaque appel à analyze_symbol() via os.getenv(),
            # donc un rechargement ici serait immédiatement effectif sur le prochain cycle.
            _GOVERNANCE_KEYS: frozenset[str] = frozenset(
                {
                    "GATE_MIN_SCORE_OVERRIDE",
                    "FORCE_TEST_EXECUTION",
                }
            )
            # Variables reconfigurables à chaud (sans impact sur la gouvernance).
            # Note : SIGNAL_MIN_SCORE, EO_DD_*, EXCHANGE_HEARTBEAT_S sont lus à
            # l'initialisation uniquement — la mise à jour os.environ est une mise
            # à jour morte jusqu'au prochain redémarrage.
            _RUNTIME_KEYS: frozenset[str] = frozenset(
                {
                    "EXEC_MAX_ORDER_USD",
                    "SIGNAL_MIN_SCORE",
                    "EO_DD_VETO",
                    "EO_DD_RECOVERY",
                    "EXCHANGE_HEARTBEAT_S",
                }
            )
            try:
                import json as _rtjson
                from pathlib import Path as _rtPath

                _rt_path = _rtPath("databases/runtime_config.json")
                if _rt_path.exists():
                    _rt = _rtjson.loads(_rt_path.read_text(encoding="utf-8"))
                    for _k, _v in _rt.items():
                        if _k in _GOVERNANCE_KEYS:
                            log.critical(
                                "[RuntimeConfig] REFUSÉ — tentative d'override clé "
                                "de gouvernance via runtime_config.json: %s=%s. "
                                "Modification requiert redémarrage du processus.",
                                _k,
                                _v,
                            )
                        elif _k in _RUNTIME_KEYS:
                            os.environ[_k] = (
                                str(_v).lower() if isinstance(_v, bool) else str(_v)
                            )
            except Exception as _rt_exc:
                log.debug("[RuntimeConfig] Erreur rechargement: %s", _rt_exc)

            # ── P6 — Adaptive Core : ATE + RegimeSmoother — AVANT scoring ────
            # L'ATE calcule le delta PID (I+D) toutes les 6 cycles (anti-oscil.)
            # puis gate.set_adaptive_delta remplace l'ancien accumulation naïf.
            if _ate is not None and cycle % 6 == 0 and cycle > 1:
                try:
                    _re_raw = 0
                    if regret_engine is not None:
                        _pm_fb = _stats_dict(pos_manager.stats())
                        _closed_trades = int(_pm_fb.get("closed_trades", 0))
                        # Neutraliser le signal winrate si pas assez de trades fermés
                        # (évite que win_rate=0% au démarrage lève le threshold)
                        if _closed_trades >= 5:
                            _winrate_exec = float(_pm_fb.get("win_rate", 0.5))
                        else:
                            _winrate_exec = 0.5  # neutre — pas assez de données
                        _re_raw = regret_engine.get_threshold_delta(
                            current_regime=_adaptive_regime,
                            winrate_executed=_winrate_exec,
                        )
                    _ate_delta = _ate.update(_adaptive_regime, _re_raw)
                    gate.set_adaptive_delta(_ate_delta)
                    if _stability_monitor is not None:
                        _stability_monitor.on_threshold_delta(_ate_delta)
                    if _re_raw != 0 or _ate_delta != 0:
                        log.info(
                            "[P6/ATE] Cycle %d régime=%s raw=%+d → ate_delta=%+d",
                            cycle,
                            _adaptive_regime,
                            _re_raw,
                            _ate_delta,
                        )
                except Exception as _ate_exc:
                    log.debug("[P6/ATE] Erreur: %s", _ate_exc)

            # RegimeSmoother : avance la rampe + câblage threshold/SL vers gate
            _smoothed_sl: float | None = None
            _smoothed_tp: float | None = None
            if _regime_smoother is not None:
                try:
                    _regime_smoother.update(_adaptive_regime)
                    if _regime_smoother.in_transition:
                        _from_r = _regime_smoother._state.from_regime
                        _to_r = _adaptive_regime
                        _old_thr = gate._effective_min_score(_from_r)
                        _new_thr = gate._effective_min_score(_to_r)
                        _s_thr = _regime_smoother.smooth_int(_old_thr, _new_thr)
                        gate.set_transition_threshold(_s_thr)
                        # Factors SL/TP via configs régime
                        try:
                            from quant_hedge_ai.agents.intelligence.market_regime_classifier import (  # noqa: E501
                                MarketRegimeClassifier as _SMRC,
                            )

                            _smrc = _SMRC()
                            _old_cfg = _smrc.get_config(_from_r)
                            _new_cfg = _smrc.get_config(_to_r)
                            _smoothed_sl = _regime_smoother.smooth_float(
                                _old_cfg.sl_factor_atr, _new_cfg.sl_factor_atr
                            )
                            _smoothed_tp = _regime_smoother.smooth_float(
                                _old_cfg.tp_factor_atr, _new_cfg.tp_factor_atr
                            )
                        except Exception:
                            pass
                        log.info(
                            "[TRANSITION] %s→%s %d/%d (%.0f%%) "
                            "| thr %d→%d smoothed=%d "
                            "| SL×%.2f→%.2f smoothed=%.2f",
                            _from_r,
                            _to_r,
                            _regime_smoother._state.elapsed,
                            _regime_smoother._state.duration,
                            _regime_smoother.progress * 100,
                            _old_thr,
                            _new_thr,
                            _s_thr,
                            _old_cfg.sl_factor_atr if _smoothed_sl else 0,
                            _new_cfg.sl_factor_atr if _smoothed_sl else 0,
                            _smoothed_sl or 0,
                        )
                    else:
                        gate.set_transition_threshold(None)
                except Exception as _smth_exc:
                    log.debug("[RegimeSmoother] Erreur câblage: %s", _smth_exc)

            # ── P7 — RiskGovernor + CapitalThrottle — AVANT exécution ────────
            _rg_snapshot = None
            if _risk_governor is not None:
                try:
                    _ct_factor = (
                        _capital_throttle.update(real_capital)
                        if _capital_throttle is not None
                        else 1.0
                    )
                    _rg_snapshot = _risk_governor.update(
                        cycle=cycle,
                        drawdown_pct=(
                            _capital_throttle.drawdown_pct if _capital_throttle else 0.0
                        ),
                        consecutive_losses=_consecutive_losses.get("value", 0),
                        atr_current=_atr_last,
                        cycle_pnl_pct=float(
                            (_pm_fb or {}).get("last_pnl_pct", 0.0)
                            if "_pm_fb" in locals()
                            else 0.0
                        ),
                        regime=_adaptive_regime,
                    )
                    # Appliquer le delta threshold du governor sur le gate
                    if _rg_snapshot.threshold_delta != 0:
                        gate.set_governor_delta(_rg_snapshot.threshold_delta)
                    else:
                        gate.set_governor_delta(0)
                    if _rg_snapshot.state != "normal":
                        log.info(
                            "[P7/RiskGov] état=%s size×%.2f thr%+d trades=%s vol_em=%s",
                            _rg_snapshot.state,
                            _rg_snapshot.size_multiplier,
                            _rg_snapshot.threshold_delta,
                            _rg_snapshot.allow_new_trades,
                            _rg_snapshot.vol_emergency,
                        )
                except Exception as _rg_exc:
                    log.debug("[P7/RiskGov] Erreur: %s", _rg_exc)

            _safety_verdict = None
            if _safety_auditor is not None:
                try:
                    module_registry.heartbeat("global_risk_gate")
                    module_registry.heartbeat("execution_engine")
                    if _risk_governor is not None:
                        module_registry.heartbeat("risk_governor")
                    else:
                        module_registry.set_status(
                            "risk_governor",
                            ModuleStatus.UNHEALTHY,
                            "P7 component unavailable",
                        )
                    _safety_verdict = _safety_auditor.inspect(
                        circuit_breaker_registry=_cb_registry_adapter
                    )
                    if _safety_verdict.block_new_trades:
                        _issues = "; ".join(
                            f"{i.module}:{i.severity}:{i.reason}"
                            for i in _safety_verdict.issues[:3]
                        )
                        log.critical(
                            "[Safety] mode=%s block_new_trades=True | %s",
                            _safety_verdict.mode.value,
                            _issues,
                        )
                except Exception as _safety_exc:
                    log.warning("[Safety] audit impossible: %s", _safety_exc)

            # P8 — Allocation pré-cycle (une fois par cycle, avant la boucle symboles)
            _p8_alloc = None
            if _strategy_allocator is not None:
                try:
                    _rg_state_str = (
                        (_rg_snapshot.state if _rg_snapshot else "normal")
                    ).upper()
                    _p8_alloc = _strategy_allocator.allocate(
                        cycle=cycle,
                        regime=_adaptive_regime,
                        risk_state=_rg_state_str,
                        capital_total=real_capital,
                        exposure_factor=(
                            _rg_snapshot.size_multiplier if _rg_snapshot else 1.0
                        ),
                        transition_forecast=_p8_transition_cache,
                    )
                    _probation_system.tick_cycle(cycle, regime=_adaptive_regime)
                    for _p8_scorer in _confidence_scorers.values():
                        _p8_scorer.tick_cycle()
                except Exception as _p8_cyc_exc:
                    log.debug("[P8/Allocator] Erreur cycle: %s", _p8_cyc_exc)

            results: list[AnalysisResult] = []
            _dp_compared_count = 0
            _dp_disagreement_count = 0
            _dp_type_a_count = 0
            _dp_type_b_count = 0
            _cycle_exec_failed = (
                False  # une seule incrémentation par cycle, pas par symbole
            )
            # Parallel OHLCV pre-scan — remplit le cache pour tous les symboles
            # avant la boucle séquentielle de décision/exécution.
            _prescan_workers = min(
                len(symbols), int(os.getenv("ADVISOR_PRESCAN_WORKERS", "20"))
            )
            with ThreadPoolExecutor(
                max_workers=_prescan_workers, thread_name_prefix="prescan"
            ) as _prescan_pool:
                _prescan_futures = {
                    _prescan_pool.submit(scanners["1h"][s].scan): s for s in symbols
                }
                for _pf, _ps in _prescan_futures.items():
                    try:
                        _pf.result(
                            timeout=float(os.getenv("ADVISOR_PRESCAN_TIMEOUT", "8"))
                        )
                    except Exception as _pfe:
                        log.debug("[prescan] %s ignoré: %s", _ps, _pfe)

            # Tri des symboles par score de stabilité/tradabilité (score DESC, tier ASC).
            # Les symboles les plus "propres" à trader sont analysés en premier dans le cycle.
            try:
                from quant_hedge_ai.agents.market.symbol_stability import (
                    sort_by_tradability,
                )

                _stab_map = {}
                for _s in symbols:
                    try:
                        _stab_map.update(scanners["1h"][_s].last_stability)
                    except Exception:
                        pass
                symbols_ordered = sort_by_tradability(symbols, _stab_map)
                if symbols_ordered:
                    log.debug(
                        "[Stability] Top 3 tradables: %s",
                        ", ".join(
                            f"{s}={_stab_map[s]['score']:.0f}({_stab_map[s]['regime']})"
                            for s in symbols_ordered[:3]
                            if s in _stab_map
                        ),
                    )
            except Exception as _sort_exc:
                symbols_ordered = symbols
                log.debug("[Stability] tri ignoré: %s", _sort_exc)

            for sym in symbols_ordered:
                r = analyze_symbol(
                    sym,
                    scanners,
                    engine,
                    gate,
                    advisor,
                    shadow,
                    watchdog,
                    memory,
                    cycle,
                    order_size_usd=order_size * _sc_state["risk_factor"],
                    meta_engine=meta_engine,
                    ranker=ranker,
                    open_positions=pos_manager.get_open(),
                    consecutive_losses=_consecutive_losses["value"],
                    no_trade_layer=no_trade_layer,
                    conviction_engine=conviction_engine,
                    awareness_engine=awareness_engine,
                    dqe=dqe,
                    portfolio_brain=portfolio_brain,
                    capital_engine=capital_engine,
                    mistake_memory=(
                        None
                        if advisor_only and defer_optional_intel
                        else _get_mistake_memory()
                    ),
                    executive_override=executive_override,
                    black_box=black_box,
                    regret_engine=(
                        None
                        if advisor_only and defer_optional_intel
                        else _get_regret_engine()
                    ),
                    threat_radar=(
                        threat_radar
                        if (
                            not shed_optional_work
                            and (
                                threat_radar_every <= 1
                                or cycle % threat_radar_every == 0
                            )
                        )
                        else None
                    ),
                    meta_learner=meta_learner,
                    runtime=runtime,
                    sl_factor_override=(
                        (_smoothed_sl or 1.0) * _sc_state["sl_factor"]
                        if _sc_state["sl_factor"] != 1.0 or _smoothed_sl is not None
                        else None
                    ),
                    tp_factor_override=(
                        (_smoothed_tp or 1.0) * _sc_state["tp_factor"]
                        if _sc_state["tp_factor"] != 1.0 or _smoothed_tp is not None
                        else None
                    ),
                    sweep_detector=_sweep_detector,
                    sweep_outcome_tracker=_sweep_outcome_tracker,
                )
                results.append(r)
                log.debug(
                    "[trace] %s cycle=%d trace_id=%s signal=%s score=%s",
                    sym,
                    cycle,
                    r.get("trace_id", ""),
                    r["signal"].signal,
                    r["signal"].score,
                )
                # S2 — GovernanceAuditor : audit constitutionnel après chaque analyse.
                # L'auditeur est indépendant : ses anomalies n'affectent pas r["trade_allowed"].
                # Il observe, log, et alerte — il ne décide pas.
                if _gov_auditor is not None:
                    try:
                        _gov_anomalies = _gov_auditor.audit_cycle(
                            result=r,
                            rsm_state=runtime_authority.state,
                            cycle=cycle,
                        )
                        if _gov_anomalies:
                            log.warning(
                                "[GovernanceAuditor] %d anomalie(s) cycle=%d sym=%s "
                                "health=%.0f",
                                len(_gov_anomalies),
                                cycle,
                                sym,
                                _gov_auditor.health_trend(),
                            )
                    except Exception as _ga_exc:
                        log.debug("[GovernanceAuditor] erreur: %s", _ga_exc)

                # ── Exécution réelle/paper ─────────────────────────────────────
                r["futures_result"] = None
                # Taille effective : depuis CAE si disponible, sinon order_size global
                allocation = r.get("allocation")
                effective_size = (
                    allocation.size_usd
                    if allocation and allocation.size_usd > 0
                    else r.get("order_size", order_size)
                )

                # ── P7 — Appliquer RiskGovernor + CapitalThrottle ────────────
                if _rg_snapshot is not None:
                    _rg_size_mul = _rg_snapshot.size_multiplier * (
                        _ct_factor if "_ct_factor" in locals() else 1.0
                    )
                    effective_size = effective_size * _rg_size_mul
                    if (
                        not _rg_snapshot.allow_new_trades
                        and r["signal"].signal != "HOLD"
                    ):
                        r["futures_result"] = {
                            "mode": "risk_governor_blocked",
                            "reason": f"état={_rg_snapshot.state}"
                            + (" vol_emergency" if _rg_snapshot.vol_emergency else ""),
                        }
                        r["trade_allowed"] = False
                        log.info(
                            "[P7] Trade bloqué %s — %s",
                            sym,
                            r["futures_result"]["reason"],
                        )

                # ── P8 — Cap effective_size au budget de la stratégie ────────
                _p8_sid_cur = "mean_reversion"
                _p8_cap_cur = 0.0
                if _p8_alloc is not None:
                    try:
                        _p8_pers = r.get("personality")
                        _p8_sid_cur = _p8_pers_map.get(
                            _p8_pers.name if _p8_pers else "", "mean_reversion"
                        )
                        _p8_cap_cur = _p8_alloc.capital_for(_p8_sid_cur)
                        if _p8_cap_cur > 0 and effective_size > _p8_cap_cur:
                            effective_size = _p8_cap_cur
                    except Exception as _p8_apply_exc:
                        log.debug("[P8/Apply] Erreur: %s", _p8_apply_exc)

                if (
                    _safety_verdict is not None
                    and _safety_verdict.block_new_trades
                    and r["signal"].signal != "HOLD"
                ):
                    if not r.get("futures_result"):
                        r["futures_result"] = {
                            "mode": "safety_auditor_blocked",
                            "reason": _safety_verdict.mode.value,
                        }
                    r["trade_allowed"] = False
                    log.info(
                        "[Safety] Trade bloqué %s — verdict=%s",
                        sym,
                        _safety_verdict.mode.value,
                    )

                # ── PROTECTIONS OBLIGATOIRES POUR MODE TEST ───────────────────────────────────
                # Vérification AVANT exécution
                protection_blocks = []
                current_time = time.time()
                current_signal = r["signal"].signal

                # #1 Cooldown après perte (5 min = 300s)
                if sym in last_loss_time:
                    time_since_loss = current_time - last_loss_time[sym]
                    if time_since_loss < 300:
                        protection_blocks.append(
                            f"cooldown_loss({time_since_loss:.0f}s)"
                        )

                # #2 Pas de re-entry même direction (seulement si position ouverte)
                _has_open_pos = (
                    any(
                        getattr(p, "symbol", None) == sym
                        for p in pos_manager.get_open_positions()
                    )
                    if hasattr(pos_manager, "get_open_positions")
                    else False
                )
                if sym in last_trade_signal and _has_open_pos:
                    if last_trade_signal[sym] == current_signal:
                        protection_blocks.append(f"same_direction({current_signal})")

                # #3 Max 10 trades par heure
                now = current_time
                hour_ago = now - 3600
                if sym not in trades_this_hour:
                    trades_this_hour[sym] = []
                trades_this_hour[sym] = [
                    t for t in trades_this_hour[sym] if t > hour_ago
                ]
                if len(trades_this_hour[sym]) >= 10:
                    protection_blocks.append(
                        f"max_trades_1h({len(trades_this_hour[sym])})"
                    )

                if protection_blocks:
                    log.info(
                        "[PROTECTION] %s BLOQUE par: %s",
                        sym,
                        " | ".join(protection_blocks),
                    )
                    if r["signal"].actionable:
                        _existing = r.get("blockers", "")
                        _prot_str = "protection(" + "|".join(protection_blocks) + ")"
                        r["blockers"] = (
                            (_existing + ", " + _prot_str) if _existing else _prot_str
                        )

                # ── Test mode check: allow execution even if signal.actionable=False if gate override ──
                gate_override_active = (
                    r.get("signal_to_execute") is not None
                    and r.get("signal_to_execute") != r["signal"].signal
                )

                # P9 — AnomalyGovernance : suspension composant exécution
                if (
                    _anomaly_gov is not None
                    and _anomaly_gov.is_suspended("execution", cycle)
                    and r["signal"].signal != "HOLD"
                ):
                    r["futures_result"] = {
                        "mode": "anomaly_governance_suspended",
                        "reason": "execution suspendu par AnomalyGovernance P9",
                    }
                    r["trade_allowed"] = False
                    log.warning(
                        "[P9/Gov] Execution SUSPENDUE cycle=%d sym=%s",
                        cycle,
                        sym,
                    )

                # G8 — DecisionPacket guard: terminal packet cannot be executed,
                # even if legacy booleans still evaluate to trade_allowed=True.
                _legacy_trade_allowed = bool(r.get("trade_allowed", r["gate"].allowed))
                _dp_packet = r.get("decision_packet")
                if _dp_packet is not None:
                    _dp_compared_count += 1
                _dp_disagrees, _dp_exec_ok, _dp_state = _decision_packet_disagrees(
                    _legacy_trade_allowed,
                    _dp_packet,
                )
                _dp_kind = _decision_packet_disagreement_type(
                    _legacy_trade_allowed,
                    _dp_exec_ok,
                )

                if _dp_disagrees:
                    _dp_disagreement_count += 1
                    if _dp_kind == "TYPE_A":
                        _dp_type_a_count += 1
                    elif _dp_kind == "TYPE_B":
                        _dp_type_b_count += 1
                    if _OBS_AVAILABLE:
                        try:
                            _dp_state_key = _metric_key_fragment(
                                _dp_state or "NON_TERMINAL"
                            )
                            _dp_regime_key = _metric_key_fragment(
                                r.get("regime", "unknown")
                            )
                            metrics_bus.increment(
                                "advisor_loop", "decision_packet_disagreement_total"
                            )
                            metrics_bus.increment(
                                "advisor_loop",
                                f"decision_packet_disagreement_by_state.{_dp_state_key}",
                            )
                            metrics_bus.increment(
                                "advisor_loop",
                                f"decision_packet_disagreement_by_regime.{_dp_regime_key}",
                            )
                            if _dp_kind != "NONE":
                                _dp_kind_key = _metric_key_fragment(_dp_kind)
                                metrics_bus.increment(
                                    "advisor_loop",
                                    f"decision_packet_disagreement_type.{_dp_kind_key}",
                                )
                        except Exception:
                            pass
                    log.error(
                        "[G8] divergence",
                        extra={
                            "trace_id": r.get("trace_id", ""),
                            "symbol": sym,
                            "legacy": _legacy_trade_allowed,
                            "packet": _dp_exec_ok,
                            "packet_state": _dp_state or "NON_TERMINAL",
                            "disagreement_type": _dp_kind,
                            "cycle": cycle,
                        },
                    )

                if not _dp_exec_ok:
                    if not r.get("futures_result"):
                        r["futures_result"] = {
                            "mode": "decision_packet_blocked",
                            "reason": f"terminal_state={_dp_state}",
                        }
                    r["trade_allowed"] = False
                    if r["signal"].actionable:
                        _existing = r.get("blockers", "")
                        _dp_block = f"decision_packet({_dp_state})"
                        r["blockers"] = (
                            (_existing + ", " + _dp_block) if _existing else _dp_block
                        )
                    log.warning(
                        "[G8] %s execution blocked by DecisionPacket state=%s",
                        sym,
                        _dp_state,
                    )

                # G8-D/E — Le DecisionPacket est la source unique d'autorisation.
                # G8-E : si _dp est None (création du packet échouée), l'exécution
                # est bloquée. Un système gouverné ne peut pas exécuter sans packet.
                # Principe : DecisionPacket absent = autorité absente = pas d'ordre.
                _dp_r = r.get("decision_packet")
                if _dp_r is None:
                    _effective_trade_allowed = False
                    log.warning(
                        "[G8-E] %s — execution bloquée : DecisionPacket absent "
                        "(création échouée ou pipeline non initialisé).",
                        sym,
                    )
                else:
                    _effective_trade_allowed = _dp_r.is_actionable()
                if (
                    (r["signal"].actionable or gate_override_active)
                    and _effective_trade_allowed
                    and not advisor_only
                    and not _runtime_safe_mode_active()
                    and not protection_blocks  # ← CRITICAL: skip si protections activées
                    and float(r.get("prix", 0.0))
                    > 0  # prix=0 → données absentes ou synthétiques
                ):
                    try:
                        # Use signal_to_execute if available (test mode override), else original signal
                        signal_action = r.get("signal_to_execute", r["signal"].signal)
                        _ref_price = float(r.get("prix", 0.0))
                        _side = "buy" if signal_action in ("buy", "long") else "sell"
                        _validated = True
                        _sim_fill_dict: dict = {}

                        # 0. Hard limits — filet de sécurité absolu (P5.4)
                        try:
                            _open_count = (
                                len(pos_manager.get_open_positions())
                                if hasattr(pos_manager, "get_open_positions")
                                else 0
                            )
                            check_hard_limits(
                                order_size_usd=effective_size,
                                capital_usd=max(real_capital, 1.0),
                                current_drawdown_pct=(
                                    float(r.get("gate", {}).get("drawdown_pct", 0.0))
                                    if hasattr(r.get("gate"), "get")
                                    else 0.0
                                ),
                                open_positions=_open_count,
                                consecutive_losses=int(
                                    _consecutive_losses.get("value", 0)
                                ),
                            )
                        except HardLimitBreached as _hlb:
                            log.warning("[HARD_LIMIT] %s %s", sym, _hlb)
                            r["futures_result"] = {
                                "mode": "hard_limit_breached",
                                "reason": str(_hlb),
                            }
                            _validated = False
                        except Exception:
                            pass  # hard limits non disponibles — non bloquant

                        # A. OrderValidator — validate + adjust qty before exchange
                        if _EXEC_CONSTRAINTS_AVAILABLE and _order_validator is not None:
                            try:
                                _sym_clean = sym.replace("/", "")
                                _sym_info = _binance_rules_mod.FUTURES_SYMBOLS.get(
                                    _sym_clean
                                )
                                if _sym_info is not None and _ref_price > 0:
                                    _qty_base = effective_size / _ref_price
                                    _validation = _order_validator.validate(
                                        _sym_info, _qty_base, _ref_price, "market"
                                    )
                                    if not _validation.is_valid:
                                        log.warning(
                                            "[VALIDATION] %s rejeté: %s",
                                            sym,
                                            _validation.rejection_reason,
                                        )
                                        r["futures_result"] = {
                                            "mode": "validation_rejected",
                                            "reason": _validation.rejection_reason,
                                        }
                                        _validated = False
                                    elif _validation.size_was_adjusted:
                                        effective_size = (
                                            _validation.adjusted_size * _ref_price
                                        )
                                        log.info(
                                            "[VALIDATION] %s qty ajustée → %.4f (%.2f USD)",
                                            sym,
                                            _validation.adjusted_size,
                                            effective_size,
                                        )
                            except Exception as _ve:
                                log.debug("[VALIDATION] erreur non-bloquante: %s", _ve)

                        # B. RateLimiter — wait before sending to exchange
                        if (
                            _validated
                            and _EXEC_CONSTRAINTS_AVAILABLE
                            and _rate_limiter is not None
                        ):
                            _rl_ok = _rate_limiter.wait_and_acquire(
                                "POST /fapi/v1/order", timeout_s=5.0
                            )
                            if not _rl_ok:
                                log.warning(
                                    "[RATE_LIMIT] %s timeout — ordre annulé", sym
                                )
                                _validated = False

                        # C. ExecutionSimulator — fill réaliste pour audit pré-envoi
                        if (
                            _validated
                            and _EXEC_CONSTRAINTS_AVAILABLE
                            and _exec_sim is not None
                            and _ref_price > 0
                        ):
                            try:
                                _qty_base = max(0.001, effective_size / _ref_price)
                                _intent = _OrderIntent(
                                    symbol=sym.replace("/", ""),
                                    side=_side,
                                    size=_qty_base,
                                    order_type="market",
                                    signal_price=_ref_price,
                                    timestamp=time.time(),
                                )
                                _snapshot = _MarketSnapshot(
                                    symbol=sym.replace("/", ""),
                                    price=_ref_price,
                                    volume_24h=float(
                                        r.get("features", {}).get(
                                            "volume_24h", 1_000_000.0
                                        )
                                    ),
                                    volatility_pct=float(
                                        r.get("features", {}).get("atr_ratio", 1.0)
                                    ),
                                    timestamp=time.time(),
                                )
                                _sim = _exec_sim.execute(_intent, _snapshot)
                                _sim_fill_dict = {
                                    "fill_price": round(_sim.fill_price, 4),
                                    "slippage_bps": round(_sim.slippage_bps, 2),
                                    "latency_ms": round(_sim.latency_ms, 1),
                                    "fee_usd": round(_sim.fee_usd, 4),
                                    "is_partial": _sim.is_partial,
                                    "is_rejected": _sim.is_rejected,
                                }
                                r["simulated_fill"] = _sim_fill_dict
                            except Exception as _se:
                                log.debug("[SIM] erreur non-bloquante: %s", _se)

                        # D. Audit log — une ligne JSONL par ordre tenté
                        if _validated and _EXEC_CONSTRAINTS_AVAILABLE:
                            try:
                                _audit = {
                                    "ts": time.time(),
                                    "symbol": sym,
                                    "side": _side,
                                    "intent": {
                                        "size_usd": round(effective_size, 4),
                                        "price": _ref_price,
                                    },
                                    "validated": True,
                                    "adjusted": {
                                        "size_usd": round(effective_size, 4),
                                        "price": _ref_price,
                                    },
                                    "simulated_fill": _sim_fill_dict,
                                }
                                with open(
                                    "logs/execution_audit/audit.jsonl",
                                    "a",
                                    encoding="utf-8",
                                ) as _af:
                                    _af.write(_json.dumps(_audit) + "\n")
                            except Exception:
                                pass

                        if _validated:
                            if exec_engine.has_futures_demo():
                                fut = _stats_dict(
                                    exec_engine.create_futures_order(
                                        sym, signal_action, effective_size
                                    )
                                )
                                exec_label = "FUTURES DEMO"
                            else:
                                fut = _stats_dict(
                                    exec_engine.create_order(
                                        sym, signal_action, effective_size
                                    )
                                )
                                exec_label = "EXECUTION"
                            fut_mode = str(fut.get("mode", ""))
                            fut_id = str(fut.get("id", ""))
                            r["futures_result"] = fut
                            log.info(
                                "[FLOW] %s EXECUTION → %s $%.2f trace_id=%s",
                                sym,
                                exec_label,
                                effective_size,
                                r.get("trace_id", ""),
                            )
                            log.info(
                                "[%s] %s %s $%.2f → mode=%s id=%s",
                                exec_label,
                                signal_action,
                                sym,
                                effective_size,
                                fut_mode,
                                fut_id,
                            )
                            _pos_registered = _register_position_from_execution(
                                fut,
                                r,
                                sym,
                                signal_action,
                                effective_size,
                            )
                            if _pos_registered:
                                _consecutive_exec_errors["value"] = 0
                                if _stalled_alerted:
                                    _at_res = (
                                        _activity_tracker.metrics()
                                        if _activity_tracker
                                        else None
                                    )
                                    _write_behavioral_event(
                                        "TRADING_RESUMED",
                                        {
                                            "cycle": cycle,
                                            "after_cycles": (
                                                _at_res.cycles_since_last_trade
                                                if _at_res
                                                else 0
                                            ),
                                            "symbol": sym,
                                        },
                                    )
                                _stalled_alerted = False
                                if _ate is not None:
                                    try:
                                        _ate.record_mismatch(had_trade=True)
                                    except Exception:
                                        pass
                                log.info(
                                    "[FLOW] %s POSITION → registered mode=%s",
                                    sym,
                                    fut_mode,
                                )
                                # S3 — alerte Telegram pour trade exécuté
                                if _telegram_alert is not None:
                                    try:
                                        _telegram_alert.trade(
                                            signal_action,
                                            sym,
                                            effective_size,
                                            float(r.get("prix", 0.0)),
                                        )
                                    except Exception:
                                        pass
                                # ── PROTECTIONS: Enregistre le trade pour tracking ──
                                last_trade_signal[sym] = signal_action
                                trades_this_hour[sym].append(current_time)
                                # P8 — Energy budget + capital efficiency
                                if _strategy_allocator is not None:
                                    try:
                                        _strategy_allocator.record_trade_executed(
                                            _p8_sid_cur
                                        )
                                        _strategy_allocator.record_capital_used(
                                            _p8_sid_cur,
                                            (
                                                _p8_cap_cur
                                                if _p8_cap_cur > 0
                                                else effective_size
                                            ),
                                            effective_size,
                                        )
                                    except Exception:
                                        pass
                                # P9 — PortfolioIntelligence : position ouverte
                                try:
                                    if _portfolio_intel is not None:
                                        _portfolio_intel.record_position(
                                            symbol=sym,
                                            exchange=os.getenv(
                                                "ACTIVE_EXCHANGE", "unknown"
                                            ),
                                            strategy=r.get("personality", "unknown"),
                                            side=signal_action.lower(),
                                            size_usd=float(effective_size),
                                        )
                                except Exception:
                                    pass
                            elif fut_mode in {"futures_failed", "live_failed"}:
                                _consecutive_losses["value"] += 1
                                _cycle_exec_failed = True
                    except Exception as _fe:
                        log.error("[EXECUTION] Erreur ordre %s: %s", sym, _fe)
                        _consecutive_losses["value"] += 1
                        _cycle_exec_failed = True

                # Black Box — enregistre chaque décision
                try:
                    r["futures_result"] = r.get("futures_result")  # assure la clé
                    black_box.record_decision(r, cycle)
                except Exception:
                    pass

                # Mise à jour ATR live dans le PositionManager (TP/SL adaptatifs)
                try:
                    feat = r.get("features", {})
                    atr_val = float(feat.get("atr", 0.0))
                    vol_val = float(feat.get("atr_ratio", feat.get("volatility", 0.0)))
                    if atr_val > 0:
                        pos_manager.update_market_data(sym, atr_val, vol_val)
                except Exception:
                    pass

                # Vérification TP/SL avec le prix spot du cycle courant.
                # Toujours actif : en futures_demo sur Kraken testnet SOL/XRP, les prix testnet
                # suivent le spot réel — le _watch_loop retourne 503 trop souvent pour être fiable.
                try:
                    prix_live = float(r.get("prix", 0.0))
                    if prix_live > 0:
                        pos_manager.update_price_and_check(sym, prix_live)
                except Exception as _tpsl_exc:
                    log.warning("[TP/SL] check échoué pour %s: %s", sym, _tpsl_exc)

                # Métriques par symbole
                if _OBS_AVAILABLE:
                    try:
                        metrics_bus.record(
                            "advisor_loop", "signal_score", float(r["signal"].score)
                        )
                        if r["signal"].actionable:
                            metrics_bus.increment("advisor_loop", "signals_actionable")
                        if r.get("trade_allowed"):
                            metrics_bus.increment("advisor_loop", "trades_approved")
                        if r.get("futures_result") and r["futures_result"].get(
                            "mode"
                        ) not in ("futures_failed", "live_failed", None):
                            metrics_bus.increment("advisor_loop", "trades_executed")
                    except Exception:
                        pass

                # Alerte immédiate si signal actionable (sauf si safe mode)
                if r["signal"].actionable and not _runtime_safe_mode_active():
                    log.info(
                        "SIGNAL ACTIONABLE: %s score=%d %s",
                        sym,
                        r["signal"].score,
                        r["signal"].signal,
                    )
                    # ── P0-P3 : Event Bus — observateurs découplés ────────────
                    _obs_published = False
                    if _decision_event_bus is not None:
                        try:
                            from observability.decision_observation import (
                                build_from_result as _build_obs,
                            )

                            _obs = _build_obs(r, cycle=cycle, engine_version="v9")
                            _decision_event_bus.publish(_obs)
                            # Alimenter le cache de prix du RegretScheduler
                            if _obs_regret_scheduler is not None:
                                _obs_regret_scheduler.update_price_cache(
                                    {sym: float(r.get("prix", 0.0))}
                                )
                            _obs_published = True
                        except Exception as _obs_exc:
                            log.debug("[OBS] publish: %s", _obs_exc)
                    # Fallback legacy : si bus inactif ou erreur, envoyer le message simple
                    if not _obs_published:
                        _alert_msg = _build_alert(r, cycle)
                        _telegram(_alert_msg)
                elif r["signal"].actionable and _runtime_safe_mode_active():
                    log.info(
                        "SIGNAL ACTIONABLE (safe mode — non envoye): %s score=%d",
                        sym,
                        r["signal"].score,
                    )

            # G8-B — cycle-level disagreement telemetry for migration readiness.
            if _OBS_AVAILABLE and _dp_compared_count > 0:
                try:
                    metrics_bus.increment(
                        "advisor_loop",
                        "decision_packet_compared_total",
                        _dp_compared_count,
                    )
                    _dp_rate = _safe_ratio(_dp_disagreement_count, _dp_compared_count)
                    _dp_type_a_rate = _safe_ratio(_dp_type_a_count, _dp_compared_count)
                    _dp_type_b_rate = _safe_ratio(_dp_type_b_count, _dp_compared_count)
                    metrics_bus.gauge(
                        "advisor_loop", "decision_packet_disagreement_rate", _dp_rate
                    )
                    metrics_bus.gauge(
                        "advisor_loop", "decision_packet_type_a_rate", _dp_type_a_rate
                    )
                    metrics_bus.gauge(
                        "advisor_loop", "decision_packet_type_b_rate", _dp_type_b_rate
                    )
                except Exception:
                    pass

            # Incrémentation unique exec_errors par cycle (pas par symbole)
            if _cycle_exec_failed:
                _consecutive_exec_errors["value"] += 1
                if _op_state is not None:
                    _op_state.record_error()
            elif _op_state is not None:
                _op_state.record_success()

            # ── Post-cycle: régime dominant + métriques d'activité ───────────
            # P8 — Mettre à jour le cache de transition pour le prochain cycle
            for _r in results:
                _tf = _r.get("transition_forecast")
                if _tf is not None and hasattr(_tf, "most_likely_next"):
                    _p8_transition_cache = (_tf.most_likely_next, _tf.next_prob)
                    break

            # P7 — ATR ratio moyen pour le prochain cycle (utilisé par RiskGovernor)
            if results:
                _atrs = [
                    float(r.get("features", {}).get("atr_ratio", 0.0))
                    for r in results
                    if r.get("features")
                ]
                _valid_atrs = [a for a in _atrs if a > 0]
                if _valid_atrs:
                    _atr_last = sum(_valid_atrs) / len(_valid_atrs)

            # Régime : mise à jour seulement si N cycles consécutifs identiques
            # (évite l'oscillation TREND→SIDEWAYS→TREND en 15 min).
            if results:
                _obs = results[0].get("regime", _adaptive_regime)
                # P6 — RegimeStateTracker : confidence + entropy (post-scoring)
                if _regime_tracker is not None:
                    try:
                        _rpkt = _regime_tracker.update(_obs)
                        if cycle % 12 == 0:
                            log.info(
                                "[P6/RegimeTracker] %s conf=%.0f%% entropy=%.2f dur=%dc",
                                _rpkt.regime,
                                _rpkt.confidence * 100,
                                _rpkt.entropy,
                                _rpkt.duration_cycles,
                            )
                    except Exception:
                        pass
                _regime_votes.append(_obs)
                if len(_regime_votes) > _REGIME_STABILITY:
                    _regime_votes = _regime_votes[-_REGIME_STABILITY:]
                if (
                    len(_regime_votes) == _REGIME_STABILITY
                    and len(set(_regime_votes)) == 1
                    and _regime_votes[0] != _adaptive_regime
                ):
                    _new_regime = _regime_votes[0]
                    log.info(
                        "[RegimeStability] Transition confirmée: %s → %s (%d cycles)",
                        _adaptive_regime,
                        _new_regime,
                        _REGIME_STABILITY,
                    )
                    _telegram_behavior(
                        f"🔄 TRANSITION RÉGIME — {_adaptive_regime} → {_new_regime}\n"
                        f"Confirmée sur {_REGIME_STABILITY} cycles consécutifs"
                    )
                    _adaptive_regime = _new_regime
            if _activity_tracker is not None:
                try:
                    _open_pos_count = len(pos_manager.get_open())
                    _any_refused = any(
                        r.get("signal") is not None
                        and r["signal"].actionable
                        and not r.get("trade_allowed", True)
                        for r in results
                    )
                    _any_executed = any(
                        r.get("futures_result") is not None
                        and r["futures_result"].get("mode")
                        not in (None, "futures_failed", "live_failed")
                        for r in results
                    )
                    _activity_tracker.record_cycle(
                        has_position=_open_pos_count > 0,
                        signal_refused=_any_refused,
                        signal_executed=_any_executed,
                    )
                    # Alimenter la distribution des blockers
                    _cycle_blockers = ", ".join(
                        r.get("blockers", "") for r in results if r.get("blockers")
                    )
                    if _cycle_blockers:
                        _activity_tracker.record_blockers(_cycle_blockers)
                    if cycle % 12 == 0:
                        log.info(_activity_tracker.summary())
                    # Alerte immédiate TRADING_STALLED (une fois par épisode)
                    if _activity_tracker.is_stalled() and not _stalled_alerted:
                        _stalled_alerted = True
                        _stall_diag = _activity_tracker.stalled_diagnosis()
                        _stall_b = (
                            " | ".join(
                                f"{k}:{v}" for k, v in _stall_diag.top_blockers[:3]
                            )
                            or "aucun signal refuse"
                        )
                        _stall_msg = (
                            f"TRADING_STALLED [{_stall_diag.label().upper()}]"
                            f" — {_stall_diag.cycles_stalled} cycles sans trade"
                            f" (confiance={_stall_diag.confidence:.0%})\n"
                            f"Blockers: {_stall_b}"
                        )
                        log.warning(
                            "[STALLED] %d cycles sans trade | confiance=%.0f%% | %s",
                            _stall_diag.cycles_stalled,
                            _stall_diag.confidence * 100,
                            _stall_b,
                        )
                        _telegram_behavior(_stall_msg)
                        _write_behavioral_event(
                            "TRADING_STALLED",
                            {
                                "cycle": cycle,
                                "cycles_stalled": _stall_diag.cycles_stalled,
                                "label": _stall_diag.label(),
                                "confidence": _stall_diag.confidence,
                                "top_blockers": dict(_stall_diag.top_blockers),
                            },
                        )
                    # P6 — REGIME_MISMATCH: capital gelé → baisser threshold (désactivé en safe mode)
                    _mismatch_cooldown = int(
                        os.getenv("REGIME_MISMATCH_COOLDOWN", "15")
                    )
                    if (
                        not P6_SAFE_MODE
                        and regret_engine is not None
                        and cycle % 3 == 0
                        and (cycle - _last_mismatch_cycle) >= _mismatch_cooldown
                        and (
                            awareness_engine is None
                            or awareness_engine.is_safe_to_trade()
                        )
                    ):
                        _at = _activity_tracker.metrics()
                        if _at.cycles_since_last_trade > 30:
                            gate.apply_regret_delta(-1)
                            _regime_votes.clear()  # force recalcul classifieur
                            _last_mismatch_cycle = cycle
                            if _stability_monitor is not None:
                                try:
                                    _stability_monitor.on_mismatch()
                                except Exception:
                                    pass
                            # Méta-boucle : ATE suit l'inefficacité de l'adaptation
                            if _ate is not None:
                                try:
                                    _ate.record_mismatch(had_trade=False)
                                    if _ate.is_adaptation_ineffective():
                                        _inef_snap = _ate.snapshot()
                                        log.warning(
                                            "[ATE] ADAPTATION_INEFFECTIVE — %d mismatches"
                                            " consecutifs sans trade",
                                            _inef_snap["consecutive_mismatch"],
                                        )
                                        _inef_msg = (
                                            f"ADAPTATION_INEFFECTIVE"
                                            f" — threshold reduit {_inef_snap['consecutive_mismatch']}x"
                                            f" sans effet observable\n"
                                            f"→ recalibration PID | delta courant={_inef_snap['current_delta']:+d}"
                                        )
                                        _telegram_behavior(_inef_msg)
                                        _write_behavioral_event(
                                            "ADAPTATION_INEFFECTIVE",
                                            {
                                                "cycle": cycle,
                                                "consecutive_mismatch": _inef_snap[
                                                    "consecutive_mismatch"
                                                ],
                                                "current_delta": _inef_snap[
                                                    "current_delta"
                                                ],
                                                "integral": _inef_snap["integral"],
                                            },
                                        )
                                        _ate.reset()  # recalibrer le PID
                                except Exception:
                                    pass
                            _mm_msg = (
                                f"REGIME_MISMATCH — {_at.cycles_since_last_trade} cycles sans trade"
                                f" ({_at.inactivity_ratio:.0%} inactif)\n"
                                f"→ threshold -1 | reset classifieur"
                            )
                            log.warning(
                                "[ActivityTracker] REGIME_MISMATCH: %d cycles sans trade "
                                "(inactivite=%.0f%%) → threshold -1, regime reset",
                                _at.cycles_since_last_trade,
                                _at.inactivity_ratio * 100,
                            )
                            _telegram_behavior(_mm_msg)
                except Exception:
                    pass

            if _stability_monitor is not None:
                try:
                    _eff_threshold = gate.min_signal_score + getattr(
                        gate, "_regret_delta", 0
                    )
                    _traded_sym = next(
                        (
                            r.get("symbol", "")
                            for r in results
                            if r.get("futures_result") is not None
                            and r["futures_result"].get("mode")
                            not in (None, "futures_failed", "live_failed")
                        ),
                        "",
                    )
                    _stability_monitor.record_cycle(
                        regime=_adaptive_regime,
                        threshold=_eff_threshold,
                        strategy_name=_traded_sym,
                        trade_executed=bool(_traded_sym),
                    )
                    # V2 — scores acceptés (signaux ayant passé le gate)
                    for _r in results:
                        _gate_r = _r.get("gate")
                        if (
                            _gate_r is not None
                            and getattr(_gate_r, "allowed", False)
                            and _r.get("signal") is not None
                        ):
                            try:
                                _stability_monitor.on_score_accepted(
                                    int(_r["signal"].score)
                                )
                            except Exception:
                                pass
                    _bsm_violations = _stability_monitor.check_invariants()
                    if _bsm_violations:
                        for _viol in _bsm_violations:
                            log.warning("[BSM] Invariante violee: %s", _viol)
                        # Router violation critique vers canal comportemental
                        _bsm_state = _stability_monitor.behavioral_state().value
                        if _bsm_state in ("oscillating", "degraded"):
                            _telegram_behavior(
                                f"⚠️ BSM ALERTE — état={_bsm_state}\n"
                                + "\n".join(f"  • {v}" for v in _bsm_violations)
                            )
                    if cycle % 12 == 0:
                        log.info("[BSM] %s", _stability_monitor.summary_line())
                    # V3 — log [BEHAVIOR] toutes les 50 cycles
                    if cycle % 50 == 0:
                        _bh_line = _stability_monitor.behavior_log()
                        log.info(_bh_line)
                        _telegram_behavior(f"📊 {_bh_line}")
                except Exception:
                    pass

            # ── P9 — Meta Governance (tick par cycle) ────────────────────────
            try:
                if _health_monitor is not None:
                    _health_monitor.tick_cycle()

                if _drift_detector is not None and results:
                    _avg_score_p9 = sum(
                        r["signal"].score for r in results if r.get("signal")
                    ) / max(len(results), 1)
                    _trades_p9 = sum(
                        1
                        for r in results
                        if r.get("futures_result") is not None
                        and r["futures_result"].get("mode")
                        not in (
                            None,
                            "futures_failed",
                            "live_failed",
                            "risk_governor_blocked",
                        )
                    )
                    _eff_thr = gate.min_signal_score + getattr(gate, "_regret_delta", 0)
                    for _r in results:
                        _sig = _r.get("signal")
                        if _sig:
                            _drift_detector.record(
                                cycle=cycle,
                                threshold_used=float(_eff_thr),
                                score=float(_sig.score),
                                signal_generated=_sig.actionable,
                                refused=not _r.get("trade_allowed", True),
                                regime=_adaptive_regime,
                            )
                    _drift_report = _drift_detector.check(regime=_adaptive_regime)
                    if _drift_report.drifting:
                        log.warning(
                            "[P9/Drift] Dérive cycle=%d métriques=%s confiance=%.2f",
                            cycle,
                            _drift_report.drifting_metrics,
                            _drift_report.meta_confidence,
                        )

                    if _anomaly_gov is not None:
                        _anomalies = _anomaly_gov.detect(
                            cycle=cycle,
                            trades_this_cycle=_trades_p9,
                            avg_score=_avg_score_p9,
                            threshold_used=float(_eff_thr),
                            rg_state=(
                                _rg_state_str
                                if "_rg_state_str" in locals()
                                else "NORMAL"
                            ),
                        )
                        for _an in _anomalies:
                            log.warning(
                                "[P9/Gov] %s : %s",
                                _an.anomaly_type.value,
                                _an.description,
                            )

                if _self_monitoring is not None:
                    _meta_snap = _self_monitoring.tick(
                        cycle=cycle,
                        health_monitor=_health_monitor,
                        drift_detector=_drift_detector,
                        rg_state=(
                            _rg_state_str if "_rg_state_str" in locals() else "NORMAL"
                        ),
                    )
                    if _meta_snap.level2_alert and cycle % 5 == 0:
                        log.critical(
                            "[P9/Meta] ALERTE NIVEAU 2 score=%.2f",
                            _meta_snap.meta_health_score,
                        )

                if cycle % 20 == 0 and _perf_supervisor is not None:
                    _perf_snap = _perf_supervisor.snapshot(cycle=cycle)
                    if _perf_snap.alerts:
                        for _pa in _perf_snap.alerts:
                            log.warning("[P9/Perf] %s", _pa)

                if cycle % 10 == 0 and _portfolio_intel is not None:
                    # Sync positions ouvertes depuis pos_manager
                    _open_pos = pos_manager.get_open()
                    _tracked = set(_portfolio_intel.position_symbols())
                    _active = {p.symbol for p in _open_pos}
                    for _sym_gone in _tracked - _active:
                        _portfolio_intel.close_position(_sym_gone)
                    for _p in _open_pos:
                        _portfolio_intel.record_position(
                            symbol=_p.symbol,
                            exchange=os.getenv("ACTIVE_EXCHANGE", "unknown"),
                            strategy=getattr(_p, "symbol", "unknown"),
                            side=(
                                _p.side.value
                                if hasattr(_p.side, "value")
                                else str(_p.side)
                            ),
                            size_usd=float(_p.size_usd),
                        )
                    _port_alerts = _portfolio_intel.get_alerts()
                    for _pal in _port_alerts:
                        log.warning("[P9/Port] %s", _pal)
            except Exception as _p9_cyc_exc:
                log.warning("[P9] Erreur inattendue cycle=%d: %s", cycle, _p9_cyc_exc)

            # ── Rapport timing bootstrap vs cycle 1 ──────────────────────────
            if cycle == 1:
                _t_cycle_1_end = time.perf_counter()
                t_bootstrap_s = _t_bootstrap_end - _t_main_start
                t_warmup_s = (
                    (_t_warmup_end - _t_warmup_start)
                    if (_t_warmup_start and _t_warmup_end)
                    else 0.0
                )
                t_cycle_1_s = _t_cycle_1_end - _t_cycle_start
                t_total_s = _t_cycle_1_end - _t_main_start
                # Session primer: collect elapsed and estimate cycle-1 gain.
                t_primer_s = 0.0
                if _primer_future is not None:
                    try:
                        t_primer_s = float(_primer_future.result(timeout=0))
                    except Exception:
                        t_primer_s = (
                            (time.perf_counter() - _t_primer_start)
                            if _t_primer_start
                            else 0.0
                        )
                    finally:
                        if _primer_executor is not None:
                            _primer_executor.shutdown(wait=False)
                log.info(
                    "[Timing] Bootstrap=%.1fs | Primer=%.1fs | Warmup=%.1fs"
                    " | Cycle1=%.1fs | Total=%.1fs | Cache_1h=%s",
                    t_bootstrap_s,
                    t_primer_s,
                    t_warmup_s,
                    t_cycle_1_s,
                    t_total_s,
                    "CHAUD" if prewarm_1h_enabled else "FROID",
                )
                if bootstrap_profile:
                    bootstrap_detail = " | ".join(
                        f"{name}={duration:.2f}s"
                        for name, duration in sorted(
                            bootstrap_profile, key=lambda item: item[1], reverse=True
                        )
                    )
                    log.info("[Timing] Bootstrap detail: %s", bootstrap_detail)
                if ADVISOR_SESSION_PRIMER and t_primer_s > 0:
                    log.info(
                        "[Timing] Gain SessionPrimer: exchange_init + load_markets (%.1fs)"
                        " effectués en parallèle du bootstrap — ~%.0fms économisés sur le cycle 1",
                        t_primer_s,
                        t_primer_s * 1000,
                    )
                if prewarm_1h_enabled:
                    log.info(
                        "[Timing] Gain warmup: cycle 1 a profite du cache 1h"
                        " (warmup %.1fs effectue en parallele du bootstrap)",
                        t_warmup_s,
                    )

            # Regret Engine — évaluer les candidats en attente
            try:
                if regret_engine is not None:
                    current_prices = {r["symbol"]: r.get("prix", 0.0) for r in results}
                    # Alimenter aussi le RegretScheduler multi-horizon (P3)
                    if _obs_regret_scheduler is not None:
                        try:
                            _obs_regret_scheduler.update_price_cache(current_prices)
                        except Exception:
                            pass
                    new_regrets = regret_engine.evaluate_pending(current_prices, cycle)
                    for reg in new_regrets:
                        _telegram(
                            f"REGRET DETECTE: {reg.symbol} {reg.signal} "
                            f"score={reg.score} | move={reg.move_pct:.2%}\n"
                            f"Refuse par: {' | '.join(reg.refused_by)}\n"
                            f"Gain potentiel manque: {reg.potential_pnl_pct:.2%}"
                        )
            except Exception:
                pass

            # Executive Override — mise à jour capital live
            try:
                executive_override.update(capital_current=real_capital)
            except Exception:
                pass

            consecutive_errors = 0

            # ── P12-B flush MetricsCollector → cache/startup/metrics.jsonl ────
            if _metrics_collector is not None:
                try:
                    _mc_snap = _metrics_collector.snapshot()
                    if _health_scorer_p12 is not None:
                        _mc_snap.health_score = _health_scorer_p12.compute(_mc_snap)
                    _metrics_collector.flush_to_jsonl(
                        _MCPath("cache/startup/metrics.jsonl")
                    )
                    if _alert_engine_p12 is not None:
                        _alert_engine_p12.check(_mc_snap)
                except Exception as _mc_flush_exc:
                    log.debug("[P12-B] flush error: %s", _mc_flush_exc)

            # Rapport périodique toutes les N cycles
            if cycle % NOTIFY_EVERY == 0:
                try:
                    _eff_score = gate._effective_min_score(_adaptive_regime)
                    msg = _build_summary(results, cycle, min_score=_eff_score)
                    # Indiquer safe mode dans le rapport
                    if _runtime_safe_mode_active():
                        msg += "\n\n[SAFE MODE] Alertes actions suspendues."
                    # Etat exchange monitor
                    ex = _stats_dict(exchange_monitor.snapshot())
                    _api_ok = bool(ex.get("healthy", True))
                    _db_ok = os.path.isdir("databases")
                    _tg_ok = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT)
                    _market_ok = len(results) > 0
                    _strategy_ok = (
                        awareness_engine is None or awareness_engine.is_safe_to_trade()
                    )
                    _ex = getattr(exec_engine, "_exchange", None)
                    _api_equity = _to_float(
                        _capital_x if "_capital_x" in dir() else 0.0, 0.0
                    )
                    _api_free_usdt = 0.0
                    _api_pos_count = 0
                    _api_assets: tuple[tuple[str, float], ...] = ()
                    if _ex is not None:
                        try:
                            _bal = _ex.fetch_balance()
                            _free = _bal.get("free", {}) or {}
                            _total = _bal.get("total", {}) or {}
                            _api_free_usdt = _to_float(
                                _free.get("USDT") or _free.get("USD") or 0.0, 0.0
                            )
                            _api_equity = _to_float(
                                _free.get("USDT") or _total.get("USDT") or _api_equity,
                                _api_equity,
                            )
                            _assets = [
                                (str(_sym), float(_qty))
                                for _sym, _qty in _total.items()
                                if _sym not in {"USDT", "USD", "info"}
                                and _qty is not None
                                and float(_qty) > 0
                            ]
                            _assets.sort(key=lambda _it: _it[1], reverse=True)
                            _api_assets = tuple(_assets[:6])
                            try:
                                _raw_pos = _ex.fetch_positions()
                                _api_pos_count = sum(
                                    1
                                    for _p in _raw_pos
                                    if _to_float(_p.get("contracts", 0), 0.0) != 0
                                )
                            except Exception:
                                _api_pos_count = 0
                        except Exception as _exb:
                            log.debug("[RealBot] fetch_balance erreur: %s", _exb)
                    if not ex.get("healthy", True):
                        msg += (
                            f"\n\nEXCHANGE HORS LIGNE — {ex.get('consecutive_failures', 0)} echecs\n"
                            f"Derniere erreur: {ex.get('last_error', '?')}"
                        )
                    else:
                        msg += f"\n\nExchange: OK ({_to_float(ex.get('last_latency_ms', 0)):.0f}ms | uptime {_to_float(ex.get('uptime_pct', 0)):.1f}%)"
                    (
                        _decision_state,
                        _reason_code,
                        _decision_reason,
                        _blocking_module,
                        _block_cycle,
                        _top_symbol,
                        _top_score,
                    ) = _decision_diagnostics(results, min_required_score=_eff_score)
                    _brain_pct, _brain_bar = _brain_score(results)
                    _decision_id = f"{cycle}{int(time.time()) % 10000:04d}"

                    pm_stats = _stats_dict(pos_manager.stats())
                    pb_health = _stats_dict(
                        portfolio_brain.portfolio_health(pos_manager.get_open())
                    )
                    _display_open_positions, _display_open_pnl_usd = (
                        _display_position_summary(_virtual_portfolio, pb_health)
                    )
                    _open_positions = pos_manager.get_open()
                    _deployed_notional = sum(
                        _to_float(getattr(_p, "size_usd", 0.0), 0.0)
                        for _p in _open_positions
                    )
                    _paper_equity = _to_float(
                        pb_health.get("capital", real_capital), 0.0
                    )
                    _paper_cash = max(0.0, _paper_equity - _deployed_notional)

                    _watchdog_components = _stats_dict(
                        getattr(watchdog, "_components", {})
                    )

                    def _stage(
                        name: str, status: PipelineStageStatus, msg_txt: str
                    ) -> PipelineStage:
                        _comp = _watchdog_components.get(name)
                        _dur = (
                            _to_float(getattr(_comp, "last_latency", 0.0), 0.0) * 1000
                        )
                        return PipelineStage(
                            name=name,
                            status=status,
                            duration_ms=round(_dur, 1),
                            message=msg_txt,
                        )

                    _pipeline = (
                        _stage(
                            "Scanner",
                            (
                                PipelineStageStatus.OK
                                if _market_ok
                                else PipelineStageStatus.FAILED
                            ),
                            f"{len(results)}/{len(symbols)}",
                        ),
                        _stage(
                            "Feature Engine", PipelineStageStatus.OK, "features_ready"
                        ),
                        _stage("AI Scoring", PipelineStageStatus.OK, "scores_computed"),
                        _stage(
                            "Portfolio Brain",
                            PipelineStageStatus.OK,
                            "constraints_checked",
                        ),
                        _stage(
                            "Risk Manager",
                            (
                                PipelineStageStatus.OK
                                if _reason_code
                                in {ReasonCode.NONE, ReasonCode.CONFIDENCE_TOO_LOW}
                                else PipelineStageStatus.FAILED
                            ),
                            _reason_code.value,
                        ),
                        _stage(
                            "Execution",
                            (
                                PipelineStageStatus.READY
                                if _decision_state is DecisionState.ACTIVE
                                else PipelineStageStatus.WAIT
                            ),
                            _decision_state.value,
                        ),
                        _stage(
                            "Exchange",
                            (
                                PipelineStageStatus.READY
                                if _api_ok
                                else PipelineStageStatus.FAILED
                            ),
                            f"lat={_to_float(ex.get('last_latency_ms', 0)):.0f}ms",
                        ),
                        _stage(
                            "Telegram",
                            (
                                PipelineStageStatus.OK
                                if _tg_ok
                                else PipelineStageStatus.FAILED
                            ),
                            "main_channel",
                        ),
                    )

                    _block_stats = _snapshot_block_stats.update(_block_cycle)
                    _snapshot = build_system_snapshot(
                        cycle=cycle,
                        engine_version=os.getenv("ENGINE_VERSION", "v9.1"),
                        health=HealthSnapshot(
                            api=_api_ok,
                            database=_db_ok,
                            telegram=_tg_ok,
                            market=_market_ok,
                            strategy=_strategy_ok,
                        ),
                        portfolio=PortfolioSnapshot(
                            paper_equity=round(_paper_equity, 2),
                            paper_cash=round(_paper_cash, 2),
                            free_cash=round(
                                _to_float(pb_health.get("free_capital", 0), 0.0), 2
                            ),
                            portfolio_exposure_pct=round(
                                _to_float(pb_health.get("total_exposure_pct", 0), 0.0),
                                1,
                            ),
                            open_pnl_usd=round(_display_open_pnl_usd, 2),
                            open_positions=_display_open_positions,
                            correlation_risk_pct=round(
                                _to_float(pb_health.get("correlation_risk", 0), 0.0), 1
                            ),
                            session_pnl_usd=round(
                                _wallet_sync_singleton.session_pnl_since_restart(), 2
                            ),
                        ),
                        ai_decision=AIDecisionSnapshot(
                            decision_id=_decision_id,
                            state=_decision_state,
                            reason_code=_reason_code,
                            reason_text=_decision_reason,
                            blocking_module=_blocking_module,
                            confidence_pct=_brain_pct,
                            highest_candidate_symbol=_top_symbol,
                            highest_candidate_score=round(_top_score, 2),
                            required_score=round(_eff_score, 2),
                            next_evaluation_sec=int(interval),
                            brain_score_pct=_brain_pct,
                        ),
                        market=MarketSnapshot(
                            regime=_adaptive_regime or "unknown",
                            exchange_latency_ms=round(
                                _to_float(ex.get("last_latency_ms", 0), 0.0), 1
                            ),
                            exchange_uptime_pct=round(
                                _to_float(ex.get("uptime_pct", 0), 0.0), 2
                            ),
                        ),
                        pipeline=_pipeline,
                        api_account=APIAccountSnapshot(
                            api_equity_usdt=round(_api_equity, 6),
                            api_free_cash_usdt=round(_api_free_usdt, 6),
                            api_positions=int(_api_pos_count),
                            api_assets=tuple(
                                (sym, round(qty, 8)) for sym, qty in _api_assets
                            ),
                        ),
                        block_stats=_block_stats,
                        decision_trace=(
                            DecisionTraceNode(
                                node="Signal Generator",
                                ts_utc=datetime.now(timezone.utc).strftime(
                                    "%Y-%m-%dT%H:%M:%SZ"
                                ),
                                duration_ms=0.0,
                                decision="SCORED",
                                reason_code=ReasonCode.NONE,
                                score=round(_top_score, 2),
                            ),
                            DecisionTraceNode(
                                node="Execution",
                                ts_utc=datetime.now(timezone.utc).strftime(
                                    "%Y-%m-%dT%H:%M:%SZ"
                                ),
                                duration_ms=0.0,
                                decision=_decision_state.value,
                                reason_code=_reason_code,
                                score=round(_top_score, 2),
                            ),
                        ),
                    )
                    _snapshot_provider.set_latest(_snapshot)
                    _snapshot_bus.publish(_snapshot)

                    msg += "\n\n" + render_health_block(_snapshot)
                    msg += "\n\n" + render_ai_decision_block(_snapshot)
                    msg += "\n\n" + render_pipeline_block(_snapshot)
                    msg += "\n\n" + render_block_stats_block(_snapshot)
                    # Stats positions ouvertes
                    if (
                        pm_stats.get("open_count", 0) > 0
                        or pm_stats.get("closed_count", 0) > 0
                    ):
                        msg += (
                            f"\n\nPOSITIONS:\n"
                            f"  Ouvertes:   {pm_stats.get('open_count', 0)} | PnL ouvert: {_to_float(pm_stats.get('open_pnl_usd', 0)):+.2f}$\n"
                            f"  Fermees:    {pm_stats.get('closed_count', 0)} | PnL realise: {_to_float(pm_stats.get('total_pnl_usd', 0)):+.2f}$\n"
                            f"  Win rate:   {_to_float(pm_stats.get('win_rate', 0.0)):.0%}"
                        )
                        # Détail positions ouvertes
                        for snap in _snapshot_list(pos_manager.snapshot()):
                            dist = snap.get("liq_dist_pct", 100)
                            liq_warn = f" LIQ RISK {dist:.0f}%!" if dist < 10 else ""
                            msg += (
                                f"\n  {snap.get('side', '?').upper()} {snap.get('symbol', '?')} "
                                f"entry=${_to_float(snap.get('entry', 0)):.0f} | PnL {_to_float(snap.get('pnl_usd', 0)):+.1f}$ "
                                f"({_to_float(snap.get('pnl_pct', 0)):+.1f}%){liq_warn}"
                            )

                    # Ajouter stats shadow si des trades ont été simulés
                    shadow_stats = _stats_dict(shadow.stats())
                    if shadow_stats.get("n_trades", 0) > 0:
                        msg += (
                            f"\n\nSHADOW STATS ({shadow_stats.get('n_trades', 0)} trades simules):\n"
                            f"  Slippage moy: {_to_float(shadow_stats.get('avg_slippage_pct', 0)):.3f}%\n"
                            f"  Latence moy:  {_to_float(shadow_stats.get('avg_latency_ms', 0)):.1f}ms\n"
                            f"  Par regime:   {shadow_stats.get('by_regime', '?')}"
                        )

                    # Executive Override — état du commandement
                    eo_snap = _stats_dict(executive_override.metrics_snapshot())
                    eo_lvl = eo_snap.get("level", "CLEAR")
                    if eo_lvl != "CLEAR":
                        msg += (
                            f"\n\nCOMMANDEMENT OVERRIDE: {eo_lvl}"
                            f"\n  DD: -{_to_float(eo_snap.get('drawdown_pct', 0)):.1f}%"
                            f" | Daily: -{_to_float(eo_snap.get('daily_loss_pct', 0)):.1f}%"
                            f" | Streak: {eo_snap.get('loss_streak', 0)}"
                            f" | Taille: x{_to_float(eo_snap.get('size_factor', 1.0)):.0%}"
                        )
                    else:
                        msg += "\n\nCOMMANDEMENT: CLEAR | Taille x100%"

                    # Mistake Memory — dernières erreurs + règles actives
                    mm = _get_mistake_memory()
                    mm_stats = _stats_dict(mm.stats())
                    if mm_stats.get("total", 0) > 0:
                        last_errors = cast(list[str], mm.explain_last_mistakes(3))
                        rules = cast(list[str], mm.active_rules_summary())
                        msg += (
                            f"\n\nMISTAKE MEMORY ({mm_stats.get('total', 0)} trades | "
                            f"erreur rate: {_to_float(mm_stats.get('error_rate', 0)):.0%} | "
                            f"{mm_stats.get('rules_active', 0)} règles actives)"
                        )
                        for err in last_errors:
                            msg += f"\n  {err}"
                        for rule in rules[:3]:
                            msg += f"\n  REGLE: {rule}"

                    # Portfolio Brain — santé globale du portefeuille
                    msg += "\n\n" + render_quant_overview_block(_snapshot)

                    # SystemIntelReporter — diagnostic complet 6h vers bot Intelligence
                    _now = time.time()
                    if _now - _last_intel_ts >= INTEL_INTERVAL_S:
                        _last_intel_ts = _now
                        try:
                            awareness_current = (
                                awareness_engine.evaluate()
                                if awareness_engine
                                else None
                            )
                            _dataset_report = None
                            try:
                                from paper_trading.dataset_validator import (
                                    validate_corpus as _validate_corpus,
                                )

                                _dataset_report = _validate_corpus(
                                    log_path=os.getenv(
                                        "PAPER_TRADE_LOG",
                                        "databases/paper_trades.jsonl",
                                    )
                                )
                            except Exception:
                                pass

                            intel_text = _get_intel_reporter().build_report(
                                cycle=cycle,
                                results=results,
                                pos_manager=pos_manager,
                                awareness_state=awareness_current,
                                override=executive_override,
                                regret_engine=regret_engine,
                                mistake_memory=mistake_memory,
                                black_box=black_box,
                                activity_tracker=_activity_tracker,
                                stability_monitor=_stability_monitor,
                                dataset_report=_dataset_report,
                            )
                            if intel_text:
                                _send_intel(intel_text)
                        except Exception as _coo_exc:
                            log.warning(
                                "[Intel] briefing error: %s", _coo_exc, exc_info=True
                            )

                    # Alertes probation stratégies (une seule fois par seuil)
                    try:
                        for _prob_msg in ranker.check_probation_alerts():
                            _telegram(f"PROBATION STRATEGIE\n{_prob_msg}")
                    except Exception:
                        pass

                    # Meta-Strategy + Ranker — personnalité active + top stratégies
                    current_personality = meta_engine.current_personality()
                    if current_personality is not None:
                        p = current_personality
                        _conf = max(
                            0,
                            min(
                                100, int(round(_to_float(p.order_size_factor, 0) * 100))
                            ),
                        )
                        if p.order_size_factor <= 0.0:
                            _risk_profile = "Capital Protection"
                        elif p.order_size_factor <= 0.5:
                            _risk_profile = "Conservative"
                        elif p.order_size_factor <= 0.9:
                            _risk_profile = "Moderate"
                        else:
                            _risk_profile = "Aggressive"
                        msg += (
                            f"\n\nMETA-STRATEGY: {p.name}"
                            f"\n  Taille: x{p.order_size_factor:.1f} | "
                            f"TP:{p.tp_pct:.1%} SL:{p.sl_pct:.1%}"
                            f"\n  Confidence: {_conf}% | Risk Profile: {_risk_profile}"
                        )
                    top3 = cast(list[JSONDict], ranker.leaderboard(3))
                    if top3:
                        msg += "\n\nTOP STRATEGIES:"
                        for i, s in enumerate(top3, 1):
                            msg += (
                                f"\n  #{i} {s.get('name', '?')}/{s.get('regime', '?')} "
                                f"score={_to_float(s.get('composite', 0)):.0f} wr={_to_float(s.get('win_rate', 0.0)):.0%} "
                                f"sharpe={_to_float(s.get('avg_sharpe', 0.0)):.2f}"
                            )
                    _telegram(msg)
                    # Duplication vers Mon Portefeuille Bot supprimée (P3, 2026-07)
                    # — CommandCenterBot garde son propre rapport (_fmt_rapport),
                    # plus de copie du rapport de cycle principal.

                    # ── Rapport périodique bot compte réel ───────────────────
                    if cycle % REAL_BOT_REPORT_EVERY == 0:
                        try:
                            _rm = (
                                os.getenv("PAPER_TRADING_ENABLED", "true").lower()
                                == "true"
                            )
                            _rmode = "PAPER (standby)" if _rm else "🟢 LIVE"
                            _real_status = render_real_account_block(_snapshot, _rmode)
                            _telegram_real(_real_status)
                        except Exception as _rbe:
                            log.debug("[RealBot] rapport erreur: %s", _rbe)
                    # ─────────────────────────────────────────────────────────

                    log.info(
                        "[RAPPORT] Telegram envoye — cycle %d (%d symboles)",
                        cycle,
                        len(results),
                    )
                except Exception as report_exc:
                    log.warning("[RAPPORT] Erreur construction rapport: %s", report_exc)

            # ── Snapshot live — écrit databases/live_snapshot.json chaque cycle ──
            try:
                from pathlib import Path as _Path

                from quant_hedge_ai.dashboard.live_snapshot import (
                    write_snapshot as _write_snap,
                )

                _cycle_elapsed_ms = round(
                    (time.perf_counter() - _t_cycle_start) * 1000, 1
                )

                # Refusal breakdown — compte combien de fois chaque couche a bloqué
                _refusal_tally: dict[str, int] = {}
                _regime_tally: dict[str, int] = {}
                _n_actionable = 0
                _n_traded = 0
                for _r in results:
                    _sig = _r["signal"]
                    _regime_tally[_sig.regime] = _regime_tally.get(_sig.regime, 0) + 1
                    if _sig.actionable and _r["gate"].allowed:
                        _n_actionable += 1
                    if _r.get("trade_allowed"):
                        _n_traded += 1
                    if not _r.get("trade_allowed") and _sig.actionable:
                        for _layer in [
                            ("gate", not _r["gate"].allowed),
                            (
                                "conviction",
                                not (getattr(_r.get("conviction"), "ok", True)),
                            ),
                            ("meta", not _r.get("meta_allowed", True)),
                            (
                                "no_trade",
                                not (
                                    getattr(_r.get("no_trade_verdict"), "allow", True)
                                ),
                            ),
                            (
                                "awareness",
                                not (getattr(_r.get("awareness_state"), "ok", True)),
                            ),
                            (
                                "portfolio",
                                not (getattr(_r.get("pb_verdict"), "allow", True)),
                            ),
                            (
                                "exec_override",
                                not (getattr(_r.get("eo_verdict"), "allow", True)),
                            ),
                            (
                                "threat_radar",
                                _r.get("radar_report")
                                and not getattr(_r.get("radar_report"), "safe", True),
                            ),
                        ]:
                            if _layer[1]:
                                _refusal_tally[_layer[0]] = (
                                    _refusal_tally.get(_layer[0], 0) + 1
                                )

                _snap_data = {
                    "ts": time.time(),
                    "cycle": cycle,
                    "capital": real_capital,
                    "safe_mode": _runtime_safe_mode_active(),
                    "cycle_duration_ms": _cycle_elapsed_ms,
                    "n_symbols": len(results),
                    "n_actionable": _n_actionable,
                    "n_traded": _n_traded,
                    "n_refused": _n_actionable - _n_traded,
                    "refusal_breakdown": _refusal_tally,
                    "regime_distribution": _regime_tally,
                    "exchange": exchange_monitor.snapshot(),
                    "positions": _snapshot_list(pos_manager.snapshot()),
                    "symbols": [
                        {
                            "symbol": r["symbol"],
                            "prix": r.get("prix", 0.0),
                            "signal": r["signal"].signal,
                            "score": r["signal"].score,
                            "actionable": r["signal"].actionable,
                            "regime": r["signal"].regime,
                            "confirmed": r["signal"].confirmed,
                            "gate_allowed": r["gate"].allowed,
                            "gate_reason": getattr(r["gate"], "reason", ""),
                            "trade_allowed": r.get("trade_allowed"),
                            "conviction_level": (
                                r["conviction"].level.value
                                if r.get("conviction")
                                else None
                            ),
                            "conviction_score": (
                                r["conviction"].score if r.get("conviction") else None
                            ),
                            "personality": (
                                r["personality"].name if r.get("personality") else None
                            ),
                            "signal_to_execute": r.get("signal_to_execute"),
                            "futures_result": r.get("futures_result"),
                            # ── Indicateurs techniques enrichis ──────────────
                            "rsi": r.get("features", {}).get("rsi"),
                            "atr_ratio": r.get("features", {}).get("atr_ratio"),
                            "bb_pct": r.get("features", {}).get("bb_pct"),
                            "macd_bullish": r.get("features", {}).get("macd_bullish"),
                            "ema_bullish": r.get("features", {}).get("ema_bullish"),
                            "bb_squeeze": r.get("features", {}).get("bb_squeeze"),
                            "vwap_dist": r.get("features", {}).get("vwap_dist"),
                            "n_candles_1h": r.get("n_1h", 0),
                        }
                        for r in results
                    ],
                }
                _snap_latest = _snapshot_provider.get_latest()
                if _snap_latest is not None:
                    _snap_data["system_snapshot"] = _snap_latest.to_dict()

                # ── P9 Meta Governance snapshot ───────────────────────────────
                try:
                    _p9_block: dict = {}
                    if _self_monitoring is not None:
                        _p9_block["meta"] = _self_monitoring.summary()
                    if _health_monitor is not None:
                        _p9_block["health"] = _health_monitor.summary()
                    if _drift_detector is not None:
                        _p9_block["drift"] = _drift_detector.summary()
                    if _anomaly_gov is not None:
                        _p9_block["governance"] = _anomaly_gov.summary()
                    if _perf_supervisor is not None:
                        _p9_block["performance"] = _perf_supervisor.summary()
                    if _portfolio_intel is not None:
                        _p9_block["portfolio"] = _portfolio_intel.summary()
                    if _p9_block:
                        _snap_data["p9"] = _p9_block
                except Exception as _p9_snap_exc:
                    log.debug("[P9] snapshot partiel: %s", _p9_snap_exc)

                _write_snap(_snap_data, _Path("databases/live_snapshot.json"))

                # ── JSONL persistence — une ligne par cycle ──────────────────
                import datetime as _dt_mod
                import json as _json_mod

                _jsonl_path = _Path("databases/cycle_data.jsonl")
                try:
                    if (
                        _jsonl_path.exists()
                        and _jsonl_path.stat().st_size > 50 * 1024 * 1024
                    ):
                        _archive = (
                            _jsonl_path.parent
                            / f"cycle_data.{_dt_mod.date.today().strftime('%Y%m%d')}.jsonl"
                        )
                        _jsonl_path.rename(_archive)
                        log.info("[CycleData] Rotation → %s", _archive.name)
                    with _jsonl_path.open("a", encoding="utf-8") as _jf:
                        _jf.write(_json_mod.dumps(_snap_data, default=str) + "\n")
                except Exception as _jl_exc:
                    log.debug("[CycleData] Erreur écriture JSONL: %s", _jl_exc)

                # ── SystemStateMachine heartbeat ─────────────────────────────
                try:
                    from system.state_machine import get_state_machine as _get_sm

                    _ex_ok = bool(exchange_monitor.snapshot().get("uptime_pct", 0) > 0)
                    _open_cnt = (
                        len(pos_manager.get_open())
                        if hasattr(pos_manager, "get_open")
                        else 0
                    )
                    # Fallback : MexcSimulator peut avoir des positions que
                    # pos_manager ne connaît pas (ex: restaurées au boot)
                    if _open_cnt == 0 and _virtual_portfolio is not None:
                        try:
                            _open_cnt = len(_virtual_portfolio._positions)
                        except Exception:
                            pass
                    _sm_alerts = _get_sm().update_heartbeat(
                        n_signals=_n_actionable,
                        n_orders=_n_traded,
                        exchange_ok=_ex_ok,
                        open_positions=_open_cnt,
                    )
                    for _alert_key, _alert_msg in _sm_alerts.items():
                        log.warning("[SystemState] %s: %s", _alert_key, _alert_msg)
                        if _alert_key == "STALL":
                            _telegram(
                                f"[ALERTE] Pipeline execution bloque\n{_alert_msg}"
                            )
                except Exception as _sm_exc:
                    log.debug("[SystemState] heartbeat échoué: %s", _sm_exc)

                # ── Position Reconciliation (toutes les heures) ───────────────
                try:
                    if (
                        _position_reconciler is not None
                        and _position_reconciler.should_reconcile()
                    ):
                        _rec_report = _position_reconciler.reconcile()
                        if _rec_report.has_drift:
                            _has_ghost = bool(_rec_report.ghost_positions)
                            _log_fn = log.critical if _has_ghost else log.warning
                            _log_fn("[Reconciler] DRIFT: %s", _rec_report.summary())
                            if _has_ghost:
                                _telegram(
                                    f"[ALERTE] Reconciliation positions\n{_rec_report.summary()}"
                                )
                except Exception as _rec_exc:
                    log.debug("[Reconciler] erreur non-bloquante: %s", _rec_exc)

                # ── State Integrity Audit (tous les N cycles) ─────────────────
                try:
                    if _integrity_audit is not None and _integrity_audit.should_run(
                        cycle
                    ):
                        _ir = _integrity_audit.run(
                            cycle=cycle,
                            real_capital=real_capital,
                            last_trade_signal=last_trade_signal,
                            last_loss_time=last_loss_time,
                            trades_this_hour=trades_this_hour,
                            pos_manager=pos_manager,
                            portfolio_brain=portfolio_brain,
                        )
                        if not _ir.is_clean:
                            _sev = _ir.severity.name
                            if not _ir.is_safe:
                                log.error(
                                    "[INTEGRITY] UNSAFE score=%d — %s",
                                    _ir.score,
                                    _ir.summary_line(),
                                )
                                _telegram(
                                    f"[INTEGRITE] score={_ir.score}/100 | {_sev}\n"
                                    + _integrity_audit.telegram_summary(_ir)
                                )
                            else:
                                log.warning(
                                    "[INTEGRITY] %s",
                                    _ir.summary_line(),
                                )
                except Exception as _ia_exc:
                    log.debug("[Integrity] audit échoué (non-bloquant): %s", _ia_exc)

            except Exception as _snap_exc:
                log.debug("[LiveSnapshot] Erreur: %s", _snap_exc)

            # Watchdog fin de cycle
            watchdog.end_cycle(cycle)
            cycle_completed = True

            # ── Heartbeat Telegram compact (toutes les N cycles ≈ 15 min) ────
            _hb_every = int(os.getenv("HEARTBEAT_CYCLES", "3"))
            if cycle % _hb_every == 0:
                try:
                    import resource as _res

                    _ram_mb = _res.getrusage(_res.RUSAGE_SELF).ru_maxrss // 1024
                except Exception:
                    _ram_mb = 0
                _hb_snapshot = _snapshot_provider.get_latest()
                if _hb_snapshot is None:
                    # Même seuil effectif que le rapport périodique (ATE/RECOVERY
                    # inclus) — jamais la constante générique 66 utilisée par
                    # _decision_engine_summary() en dehors du chemin live.
                    _hb_eff_score = gate._effective_min_score(_adaptive_regime)
                    (
                        _hb_decision_state,
                        _hb_reason_code,
                        _hb_reason_text,
                        _hb_blocking,
                        _hb_block_cycle,
                        _hb_symbol,
                        _hb_score,
                    ) = _decision_diagnostics(results, min_required_score=_hb_eff_score)
                    _hb_brain_pct, _ = _brain_score(results)
                    _hb_ex = _stats_dict(exchange_monitor.snapshot())
                    _hb_pb = _stats_dict(
                        portfolio_brain.portfolio_health(pos_manager.get_open())
                    )
                    _hb_display_open_positions, _hb_display_open_pnl_usd = (
                        _display_position_summary(_virtual_portfolio, _hb_pb)
                    )
                    _hb_block_stats = _snapshot_block_stats.update(_hb_block_cycle)
                    _hb_snapshot = build_system_snapshot(
                        cycle=cycle,
                        engine_version=os.getenv("ENGINE_VERSION", "v9.1"),
                        health=HealthSnapshot(
                            api=bool(_hb_ex.get("healthy", True)),
                            database=os.path.isdir("databases"),
                            telegram=bool(TELEGRAM_TOKEN and TELEGRAM_CHAT),
                            market=len(results) > 0,
                            strategy=(
                                awareness_engine is None
                                or awareness_engine.is_safe_to_trade()
                            ),
                        ),
                        portfolio=PortfolioSnapshot(
                            paper_equity=round(
                                _to_float(_hb_pb.get("capital", real_capital), 0.0), 2
                            ),
                            paper_cash=round(
                                max(
                                    0.0,
                                    _to_float(_hb_pb.get("capital", real_capital), 0.0)
                                    - sum(
                                        _to_float(getattr(p, "size_usd", 0.0), 0.0)
                                        for p in pos_manager.get_open()
                                    ),
                                ),
                                2,
                            ),
                            free_cash=round(
                                _to_float(_hb_pb.get("free_capital", 0), 0.0), 2
                            ),
                            portfolio_exposure_pct=round(
                                _to_float(_hb_pb.get("total_exposure_pct", 0), 0.0), 1
                            ),
                            open_pnl_usd=round(_hb_display_open_pnl_usd, 2),
                            open_positions=_hb_display_open_positions,
                            correlation_risk_pct=round(
                                _to_float(_hb_pb.get("correlation_risk", 0), 0.0), 1
                            ),
                            session_pnl_usd=round(
                                _wallet_sync_singleton.session_pnl_since_restart(), 2
                            ),
                        ),
                        ai_decision=AIDecisionSnapshot(
                            decision_id=f"{cycle}{int(time.time()) % 10000:04d}",
                            state=_hb_decision_state,
                            reason_code=_hb_reason_code,
                            reason_text=_hb_reason_text,
                            blocking_module=_hb_blocking,
                            confidence_pct=_hb_brain_pct,
                            highest_candidate_symbol=_hb_symbol,
                            highest_candidate_score=round(_hb_score, 2),
                            required_score=round(_hb_eff_score, 2),
                            next_evaluation_sec=int(interval),
                            brain_score_pct=_hb_brain_pct,
                        ),
                        market=MarketSnapshot(
                            regime=_adaptive_regime or "unknown",
                            exchange_latency_ms=round(
                                _to_float(_hb_ex.get("last_latency_ms", 0), 0.0), 1
                            ),
                            exchange_uptime_pct=round(
                                _to_float(_hb_ex.get("uptime_pct", 0), 0.0), 2
                            ),
                        ),
                        pipeline=(),
                        api_account=APIAccountSnapshot(
                            api_equity_usdt=0.0,
                            api_free_cash_usdt=0.0,
                            api_positions=0,
                            api_assets=(),
                        ),
                        block_stats=_hb_block_stats,
                    )
                    _snapshot_provider.set_latest(_hb_snapshot)
                    _snapshot_bus.publish(_hb_snapshot)
                _hb_msg = render_heartbeat(_hb_snapshot, _ram_mb)
                _telegram(_hb_msg)
                log.info("[Heartbeat] %s", _hb_msg.replace("\n", " | "))

            cycle_elapsed = time.perf_counter() - _t_cycle_start
            if cycle_budget_seconds > 0 and cycle_elapsed > cycle_budget_seconds:
                shed_optional_until_cycle = max(
                    shed_optional_until_cycle,
                    cycle + load_shed_cycles,
                )
                log.info(
                    "[LoadBudget] Cycle %d hors budget %.2fs > %.2fs — travaux optionnels reduits jusqu'au cycle %d",
                    cycle,
                    cycle_elapsed,
                    cycle_budget_seconds,
                    shed_optional_until_cycle,
                )

            # ADR-0013 — symétrique de report_error("cycle_exception") (except
            # ci-dessous) : sans ce report_ok(), RECOVERY (et DEGRADED/CRITICAL)
            # ne peuvent jamais graduer automatiquement, report_ok() étant sinon
            # inappelé en production (incident SAFE_MODE 2026-07-10/11). No-op
            # garanti si une requête SAFE_MODE reste active (runtime_state_machine
            # ligne 169-170) ; ne vide jamais les compteurs d'erreur (pas de risque
            # de masquer une dégradation en cours).
            try:
                runtime_authority.report_ok()
            except Exception:
                pass

        except KeyboardInterrupt:
            log.info("Arret manuel.")
            _stop_runtime_services()
            _telegram("Crypto AI Terminal arrete manuellement.")
            _clean_exit = True
            break
        except Exception as exc:
            consecutive_errors += 1
            log.error("Erreur cycle %d: %s", cycle, exc, exc_info=True)
            # G3 — Toute exception non récupérée dans un cycle doit notifier le RSM.
            # Cela permet à RuntimeStateMachine de dégrader l'état système
            # (NORMAL → DEGRADED → CRITICAL → SAFE_MODE) si les erreurs persistent.
            try:
                runtime_authority.report_error("cycle_exception")
            except Exception:
                pass
            # ENL-2 trace record : persist un DP minimal pour que le cycle
            # échoué reste visible dans l'audit trail (gap ENL-2 fermé).
            try:
                from pathlib import Path as _Path

                from core.decision_packet import DecisionPacket as _DP
                from core.decision_packet import PacketEventCategory as _PEC
                from observability.json_logger import new_trace_id as _new_tid

                # DPSS: SYSTEM category isolates ENL records from trading metrics.
                _enl_dp = _DP(symbol="CYCLE_EXCEPTION", event_category=_PEC.SYSTEM)
                _enl_dp.reject("enl2_g3", f"{type(exc).__name__}:{exc!s:.120}")
                _enl_dp.metadata["cycle"] = cycle
                _enl_dp.metadata["trace_id"] = _new_tid()
                _enl_log = _Path(os.getenv("DP_LOG_DIR", "databases"))
                _enl_log.mkdir(parents=True, exist_ok=True)
                from datetime import datetime as _dt

                _enl_file = (
                    _enl_log
                    / f"decision_packets_{_dt.utcnow().strftime('%Y-%m-%d')}.jsonl"
                )
                import json as _json

                with open(_enl_file, "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps(_enl_dp.to_dict(), ensure_ascii=False) + "\n")
            except Exception:
                pass
            if _OBS_AVAILABLE:
                try:
                    sev = (
                        ErrorSeverity.CRITICAL
                        if consecutive_errors >= 3
                        else ErrorSeverity.HIGH
                    )
                    error_bus.emit(
                        module="advisor_loop",
                        error=exc,
                        category=ErrorCategory.SYSTEM,
                        severity=sev,
                        context={
                            "cycle": cycle,
                            "consecutive_errors": consecutive_errors,
                        },
                    )
                    module_registry.report_error("advisor_loop", str(exc))
                except Exception:
                    pass
            if _metrics_collector is not None:
                try:
                    _metrics_collector.record_exception(exc)
                except Exception:
                    pass
            if consecutive_errors >= 5:
                _crash_msg = (
                    f"CRASH — 5 erreurs consecutives au cycle {cycle}\n"
                    f"Derniere: {type(exc).__name__}: {exc}\n"
                    f"Le systeme va s'arreter. Verifier logs/advisor_loop.log"
                )
                _telegram(_crash_msg)
                _send_email(
                    f"CRASH cycle {cycle}",
                    _crash_msg,
                )
                log.critical("Trop d'erreurs, arret.")
                _stop_runtime_services()
                break

        if max_cycles is not None and cycle >= max_cycles:
            log.info("Max cycles atteint (%d) — arrêt propre.", max_cycles)
            _stop_runtime_services()
            _clean_exit = True
            break

        if cycle == 1 and cycle_completed and defer_post_cycle_services:
            _start_kill_switch()
            _start_exchange_monitor()
            _start_healer()

        log.info("Prochain cycle dans %ds...", interval)
        _sleep(interval)

    if not _clean_exit:
        log.critical("[main] Sortie anormale — sys.exit(1)")
        sys.exit(1)


if __name__ == "__main__":
    _env_symbols = os.getenv("V9_SYMBOLS", "")
    _symbols_from_env = (
        _env_symbols.split() if _env_symbols.strip() else SYMBOLS_DEFAULT
    )

    # ── MarketUniverseRanker — sélection dynamique des symboles ──────────────
    # Pipeline 2 étapes :
    #   1. PerpUniverseBuilder.discover() — 1 seul appel fetch_tickers() sur MEXC
    #      → filtre volume+spread+volatilité → top 80 candidats USDT+USDC
    #   2. MarketUniverseRanker.rank() — scoring 6 critères (vol/liquidity/spread/
    #      volatilité/corrélation/fiabilité) → top RANKER_TOP_N (défaut 50)
    # Fallback : CANDIDATES_ALL (50 statiques) si MEXC indisponible.
    if os.getenv("RANKER_ENABLED", "false").lower() == "true":
        try:
            from infra.live_exchange_reader import LiveExchangeReader
            from tools.market_universe_ranker import (
                CANDIDATES_ALL,
                MarketUniverseRanker,
            )
            from tools.perp_universe_builder import PerpUniverseBuilder

            _ranker_exchange = os.getenv("RANKER_EXCHANGE", "mexc")
            _ranker_top_n = int(os.getenv("RANKER_TOP_N", "50"))
            _ranker_min_vol = float(os.getenv("RANKER_MIN_VOL_USD", "500000"))
            _ranker_reader = LiveExchangeReader(exchange_id=_ranker_exchange)
            _ping = _ranker_reader.ping()

            if _ping.get("status") == "OK":
                # Étape 1 — Scan MEXC complet (1 appel batch, USDT+USDC)
                _candidates_syms: list[str] = CANDIDATES_ALL
                try:
                    _builder = PerpUniverseBuilder(exchange_id=_ranker_exchange)
                    _discovered = _builder.discover(
                        top_n=80,
                        min_vol_usd=_ranker_min_vol,
                    )
                    if _discovered:
                        _candidates_syms = [c.symbol for c in _discovered]
                        log.info(
                            "[Ranker] PerpBuilder: %d paires MEXC qualifiées "
                            "(vol>$%.0fk, spread<%.1f%%)",
                            len(_candidates_syms),
                            _ranker_min_vol / 1000,
                            float(os.getenv("PERP_BUILDER_MAX_SPREAD_PCT", "0.50")),
                        )
                except Exception as _be:
                    log.warning(
                        "[Ranker] PerpBuilder indisponible (%s) — 50 candidats statiques",
                        _be,
                    )

                # Étape 2 — Scoring 6 critères → top N
                _ranker_inst = MarketUniverseRanker(reader=_ranker_reader)
                _ranked = _ranker_inst.rank(_candidates_syms, top_n=_ranker_top_n)
                _ranked_syms = [e.symbol for e in _ranked if e.score > 0]
                _ranker_bl = frozenset(
                    s.strip().upper()
                    for s in os.getenv("SYMBOL_BLACKLIST", "").split(",")
                    if s.strip()
                )
                if _ranker_bl:
                    _before = len(_ranked_syms)
                    _ranked_syms = [
                        s for s in _ranked_syms if s.upper() not in _ranker_bl
                    ]
                    if len(_ranked_syms) < _before:
                        log.info(
                            "[Ranker] Blacklist: %d symbole(s) exclus: %s",
                            _before - len(_ranked_syms),
                            ", ".join(
                                s
                                for s in [e.symbol for e in _ranked if e.score > 0]
                                if s.upper() in _ranker_bl
                            ),
                        )
                if _ranked_syms:
                    log.info(
                        "[Ranker] Top %d selectionnes (sur %d candidats MEXC): %s%s",
                        len(_ranked_syms),
                        len(_candidates_syms),
                        ", ".join(_ranked_syms[:15]),
                        "..." if len(_ranked_syms) > 15 else "",
                    )
                    _symbols_from_env = _ranked_syms
                else:
                    log.warning(
                        "[Ranker] Aucun symbole valide — fallback SYMBOLS_DEFAULT"
                    )
            else:
                log.warning(
                    "[Ranker] Exchange %s inaccessible (ping KO) — fallback SYMBOLS_DEFAULT",
                    _ranker_exchange,
                )
        except Exception as _ranker_exc:
            log.warning(
                "[Ranker] Erreur demarrage: %s — fallback SYMBOLS_DEFAULT", _ranker_exc
            )
    # ─────────────────────────────────────────────────────────────────────────

    parser = argparse.ArgumentParser(description="Advisor loop multi-symboles")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--symbols", nargs="+", default=_symbols_from_env)
    parser.add_argument("--max-cycles", type=int, default=None)
    args = parser.parse_args()
    main(symbols=args.symbols, interval=args.interval, max_cycles=args.max_cycles)
