"""
black_box.py — Black Box Recorder

Inspiré de la boîte noire aviation.
Enregistre CHAQUE décision importante avec :
  - Timestamp + symbole + prix
  - Signal + score + régime + personnalité
  - Pourquoi BUY / SELL / HOLD / REFUS
  - Quel module a refusé et pourquoi
  - Contexte complet (features, positions ouvertes, capital)
  - Ordre exécuté ou non, et raison

En cas de crash ou comportement inattendu :
  on sait EXACTEMENT ce qui s'est passé et pourquoi.

Format JSONL, lecture facile, rotation automatique.
Requêtes rapides : filtre par type, symbole, régime, décision.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.black_box")
_BB_PATH = os.getenv("BB_PATH", "databases/black_box.jsonl")
_BB_MAX_SIZE = int(os.getenv("BB_MAX", "5000"))  # max entrées en mémoire

# ── S-03B: discriminateurs des writers bypass historiques (plaintext) ────────
# Ces trois formes existaient avant la remédiation S-03B : elles écrivaient
# du JSON en clair directement dans le même fichier que BlackBox._append()
# (qui chiffre). Elles restent reconnues en lecture (LEGACY) pour ne jamais
# perdre silencieusement des données historiques ; les nouveaux writes de ces
# trois call sites passent désormais par BlackBox.record_structured_event().
_LEGACY_EVENT_KEYS = {"WARMUP_COMPLETE", "BYPASS_DETECTED"}
_LEGACY_TYPE_KEYS = {"P10_AUDIT_TRAIL"}

# Chiffrement AES-256-GCM des entrées (C-01) — singleton lazy
_bb_enc = None


def _get_enc():
    global _bb_enc
    if _bb_enc is None:
        from crypto.blackbox_encryption import BlackBoxEncryption

        _bb_enc = BlackBoxEncryption()
    return _bb_enc


class DecisionType(str, Enum):
    TRADE_EXECUTED = "TRADE_EXECUTED"
    TRADE_REFUSED = "TRADE_REFUSED"
    HOLD = "HOLD"
    POSITION_CLOSED = "POSITION_CLOSED"
    HALT_TRIGGERED = "HALT_TRIGGERED"
    SAFE_MODE = "SAFE_MODE"
    REGIME_CHANGE = "REGIME_CHANGE"
    AWARENESS_ALERT = "AWARENESS_ALERT"
    RULE_TRIGGERED = "RULE_TRIGGERED"
    SYSTEM_EVENT = "SYSTEM_EVENT"


@dataclass
class BlackBoxEntry:
    ts: float
    decision_type: str
    symbol: str
    signal: str  # BUY / SELL / HOLD
    score: int
    regime: str
    personality: str
    price: float
    # Raison principale
    reason: str
    # Couches qui ont refusé (vide si exécuté)
    refused_by: list = field(default_factory=list)
    # Couches OK
    passed_by: list = field(default_factory=list)
    # Contexte clé
    conviction_level: str = "unknown"
    conviction_score: float = 0.0
    awareness_level: str = "OK"
    portfolio_exposure: float = 0.0
    open_positions: int = 0
    capital_available: float = 0.0
    order_size: float = 0.0
    kelly_fraction: float = 0.0
    # Features clés (résumé)
    rsi: float = 0.0
    atr_ratio: float = 0.0
    macd_bullish: bool = False
    ema_bullish: bool = False
    bb_pct: float = 0.5
    # Résultat (rempli à la fermeture)
    pnl_pct: float = 0.0
    close_reason: str = ""
    # ID ordre si exécuté
    order_id: str = ""
    cycle: int = 0
    # Enrichissements P1
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    drawdown_session_pct: float = 0.0
    n_trades_today: int = 0

    # ── S-03B: champs de provenance (optionnels, défauts sûrs pour compat
    # ascendante — une entrée historique désérialisée sans ces clés doit
    # continuer à se construire via BlackBoxEntry(**data)) ──────────────────
    schema_version: int = 1  # stampé à 2 par les nouveaux writes S-03B
    packet_id: str = ""  # DecisionPacket.packet_id — vide si indisponible
    trace_id: str = ""  # trace_id canonique du cycle (advisor_loop)
    experiment_id: Optional[str] = None
    # first_blocker/all_blockers canoniques, copiés depuis DecisionObservation
    # (via result["blockers"]) — source unique de vérité pour "qui a bloqué".
    # `refused_by`/`passed_by` ci-dessus restent l'ordre de check INTERNE à
    # BlackBox._check(), un diagnostic de séquencement, PAS une vérité causale.
    canonical_first_blocker: str = ""
    canonical_all_blockers: list = field(default_factory=list)
    packet_side: str = ""  # vocabulaire LONG/SHORT/FLAT du DecisionPacket
    # Charge utile structurée pour les événements non-décisionnels (warmup,
    # bypass, audit trail P10) routés via record_structured_event().
    event_payload: Optional[dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BlackBox:
    """
    Enregistre chaque décision du système dans un journal indestructible.

    Usage :
        bb = BlackBox()
        bb.record_decision(result_dict, cycle)
        bb.record_position_closed(pos, reason)
        bb.record_halt(reason, level)
        bb.query(decision_type="TRADE_EXECUTED", symbol="BTC/USDT", limit=10)
    """

    def __init__(self, path: str = _BB_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[BlackBoxEntry] = []
        self._loaded = False
        self._session_capital_peak: float = 0.0
        # S-03B: compteurs observabilité (item 6/7) — protégés par _stats_lock
        self._stats_lock = threading.Lock()
        self._load_stats: Dict[str, int] = {
            "encrypted_records": 0,
            "legacy_plaintext_records": 0,
            "invalid_records": 0,
            "unrecognized_records": 0,
        }
        self._write_attempts = 0
        self._write_successes = 0
        self._write_failures = 0

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        enc = _get_enc()
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = enc.decrypt_line(line)
                        with self._stats_lock:
                            self._load_stats["encrypted_records"] += 1
                    except Exception:
                        # Fallback migration : entrée en clair (fichier pré-C-01
                        # ou l'un des trois writers bypass historiques — S-03B).
                        try:
                            data = json.loads(line)
                        except Exception:
                            with self._stats_lock:
                                self._load_stats["invalid_records"] += 1
                            continue
                        legacy = self._normalize_legacy_plaintext(data)
                        if legacy is not None:
                            with self._stats_lock:
                                self._load_stats["legacy_plaintext_records"] += 1
                            self._entries.append(legacy)
                            continue
                        # JSON en clair mais pas une des 3 formes bypass connues.
                        try:
                            self._entries.append(BlackBoxEntry(**data))
                            with self._stats_lock:
                                self._load_stats["legacy_plaintext_records"] += 1
                        except Exception:
                            with self._stats_lock:
                                self._load_stats["unrecognized_records"] += 1
                        continue
                    try:
                        self._entries.append(BlackBoxEntry(**data))
                    except Exception:
                        with self._stats_lock:
                            self._load_stats["invalid_records"] += 1
            self._entries = self._entries[-_BB_MAX_SIZE:]
        except Exception as exc:
            _log.warning("[BlackBox] Chargement partiel: %s", exc)

    @staticmethod
    def _normalize_legacy_plaintext(data: dict) -> Optional["BlackBoxEntry"]:
        """
        Reconnaît les 3 formes plaintext historiques (WARMUP_COMPLETE,
        BYPASS_DETECTED, P10_AUDIT_TRAIL) et les enveloppe dans un
        BlackBoxEntry normalisé (decision_type=SYSTEM_EVENT, event_payload=
        données brutes) — au lieu de les laisser disparaître silencieusement
        au chargement (S-03B item 6).
        """
        event = data.get("event")
        rtype = data.get("type")
        if event not in _LEGACY_EVENT_KEYS and rtype not in _LEGACY_TYPE_KEYS:
            return None
        label = event or rtype
        return BlackBoxEntry(
            ts=float(data.get("ts", 0.0)),
            decision_type=DecisionType.SYSTEM_EVENT.value,
            symbol="SYSTEM",
            signal="EVENT",
            score=0,
            regime="unknown",
            personality="legacy_bypass_writer",
            price=0.0,
            reason=f"LEGACY:{label}",
            schema_version=1,
            event_payload=dict(data),
        )

    def get_load_stats(self) -> Dict[str, int]:
        """Compteurs de chargement — S-03B item 6/7."""
        with self._stats_lock:
            return dict(self._load_stats)

    def get_write_stats(self) -> Dict[str, int]:
        """Compteurs d'écriture — S-03B item 7."""
        with self._stats_lock:
            return {
                "write_attempts": self._write_attempts,
                "write_successes": self._write_successes,
                "write_failures": self._write_failures,
            }

    # ── Helpers enrichissement ────────────────────────────────────────────────

    def _compute_drawdown(self, capital: float) -> float:
        """Drawdown depuis le pic de capital de session (%)."""
        if capital > self._session_capital_peak:
            self._session_capital_peak = capital
        if self._session_capital_peak <= 0:
            return 0.0
        return round(
            (self._session_capital_peak - capital) / self._session_capital_peak * 100, 2
        )

    def _count_trades_today(self) -> int:
        """Nombre de TRADE_EXECUTED depuis minuit UTC."""
        midnight = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        return sum(
            1
            for e in self._entries
            if e.decision_type == DecisionType.TRADE_EXECUTED.value and e.ts >= midnight
        )

    # ── Enregistrement des décisions ──────────────────────────────────────────

    def record_decision(self, r: dict, cycle: int = 0) -> BlackBoxEntry:
        """
        Enregistre une décision d'analyse de symbole depuis le résultat
        de analyze_symbol() dans advisor_loop.py.
        """
        self._ensure_loaded()

        signal = r.get("signal")
        gate = r.get("gate")
        conviction = r.get("conviction")
        awareness = r.get("awareness_state")
        pb = r.get("pb_verdict")
        allocation = r.get("allocation")
        mm = r.get("mm_check")
        persona = r.get("personality")
        feat = r.get("features", {})
        no_trade = r.get("no_trade_verdict")

        trade_allowed = r.get("trade_allowed", False)
        meta_allowed = r.get("meta_allowed", True)

        # Déterminer le type de décision
        if signal and signal.actionable:
            if (
                trade_allowed
                and r.get("futures_result", {})
                and r["futures_result"].get("mode") == "futures_demo"
            ):
                dtype = DecisionType.TRADE_EXECUTED
            elif signal.actionable:
                dtype = DecisionType.TRADE_REFUSED
            else:
                dtype = DecisionType.HOLD
        else:
            dtype = DecisionType.HOLD

        # Construire la liste des refus
        refused_by = []
        passed_by = []

        def _check(name: str, ok: bool, reason: str = "") -> None:
            if ok:
                passed_by.append(name)
            else:
                refused_by.append(f"{name}: {reason}" if reason else name)

        if signal:
            _check(
                "gate",
                gate.allowed if gate else True,
                " | ".join(gate.failed[:2]) if gate and not gate.allowed else "",
            )
            _check(
                "meta",
                meta_allowed,
                r.get("meta_reason", "") if not meta_allowed else "",
            )
            _check(
                "conviction",
                conviction is None or not conviction.blocks_trade(),
                (
                    conviction.level.value
                    if conviction and conviction.blocks_trade()
                    else ""
                ),
            )
            _check(
                "no_trade",
                no_trade is None or bool(no_trade),
                (
                    f"score={no_trade.rejection_score:.0f}"
                    if no_trade and not bool(no_trade)
                    else ""
                ),
            )
            _check(
                "awareness",
                awareness is None
                or awareness.level.value == "OK"
                or not hasattr(awareness, "is_trading_halted")
                or True,
                awareness.level.name if awareness else "",
            )
            _check(
                "mistake_mem",
                mm is None or bool(mm),
                mm.reason[:60] if mm and not bool(mm) else "",
            )
            _check(
                "portfolio",
                pb is None or bool(pb),
                pb.reason[:60] if pb and not bool(pb) else "",
            )
            _check(
                "capital_eng",
                allocation is None or bool(allocation),
                allocation.reason[:60] if allocation and not bool(allocation) else "",
            )

        # Raison principale lisible
        if refused_by:
            reason = f"Refus: {refused_by[0]}"
        elif dtype == DecisionType.TRADE_EXECUTED:
            reason = f"Ordre {signal.signal if signal else '?'} exécuté"
        elif signal and not signal.actionable:
            reason = f"Score insuffisant: {signal.score}/100"
        else:
            reason = "HOLD — pas de signal"

        _capital = pb.capital_available if pb else 0.0

        # ── S-03B: provenance canonique (item 3/4) ──────────────────────────
        # Source unique de vérité pour "qui a bloqué" = result["blockers"],
        # la même que DecisionObservation.build_from_result. refused_by/
        # passed_by ci-dessus restent le diagnostic d'ordre interne à
        # _check(), jamais la vérité causale.
        blockers_raw = r.get("blockers", "")
        canonical_all_blockers = (
            [b.strip() for b in blockers_raw.split(",") if b.strip()]
            if blockers_raw
            else []
        )
        canonical_first_blocker = (
            canonical_all_blockers[0] if canonical_all_blockers else ""
        )
        dp = r.get("decision_packet")
        packet_id = str(dp.packet_id) if dp is not None and hasattr(dp, "packet_id") else ""
        dp_metadata = getattr(dp, "metadata", {}) if dp is not None else {}
        trace_id = str(r.get("trace_id") or (dp_metadata or {}).get("trace_id") or "")
        experiment_id_raw = r.get("experiment_id") or (dp_metadata or {}).get(
            "experiment_id"
        )
        experiment_id = str(experiment_id_raw) if experiment_id_raw else None
        packet_side = ""
        if dp is not None and hasattr(dp, "side"):
            packet_side = getattr(dp.side, "value", str(dp.side))

        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=dtype.value,
            symbol=r.get("symbol", "?"),
            signal=signal.signal if signal else "HOLD",
            score=signal.score if signal else 0,
            regime=r.get("regime", "unknown"),
            personality=persona.name if persona else "N/A",
            price=r.get("prix", 0.0),
            reason=reason,
            refused_by=refused_by,
            passed_by=passed_by,
            conviction_level=conviction.level.value if conviction else "unknown",
            conviction_score=conviction.score if conviction else 0.0,
            awareness_level=awareness.level.name if awareness else "OK",
            portfolio_exposure=(
                pb.metrics.get("total_exposure_pct", 0.0)
                if pb and hasattr(pb, "metrics")
                else 0.0
            ),
            open_positions=(
                r.get("open_positions", 0)
                if isinstance(r.get("open_positions"), int)
                else len(r.get("open_positions", []))
            ),
            capital_available=_capital,
            order_size=r.get("order_size", 0.0),
            kelly_fraction=allocation.kelly_fraction if allocation else 0.0,
            rsi=float(feat.get("rsi", 0.0)),
            atr_ratio=float(feat.get("atr_ratio", 0.0)),
            macd_bullish=bool(feat.get("macd_bullish", False)),
            ema_bullish=bool(feat.get("ema_bullish", False)),
            bb_pct=float(feat.get("bb_pct", 0.5)),
            order_id=(
                r.get("futures_result", {}).get("id", "")
                if r.get("futures_result")
                else ""
            ),
            cycle=cycle,
            drawdown_session_pct=self._compute_drawdown(_capital),
            n_trades_today=self._count_trades_today(),
            schema_version=2,
            packet_id=packet_id,
            trace_id=trace_id,
            experiment_id=experiment_id,
            canonical_first_blocker=canonical_first_blocker,
            canonical_all_blockers=canonical_all_blockers,
            packet_side=packet_side,
        )

        self._append(entry)
        return entry

    def record_position_closed(self, pos, reason) -> BlackBoxEntry:
        """Enregistre la fermeture d'une position."""
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.POSITION_CLOSED.value,
            symbol=getattr(pos, "symbol", "?"),
            signal=(
                "BUY"
                if getattr(pos, "side", None) and pos.side.value == "long"
                else "SELL"
            ),
            score=getattr(pos, "signal_score", 0),
            regime=getattr(pos, "regime", "unknown"),
            personality=getattr(pos, "symbol", "main"),
            price=getattr(pos, "current_price", 0.0),
            reason=f"Fermé: {reason.value if hasattr(reason, 'value') else reason}",
            pnl_pct=getattr(pos, "pnl_pct", 0.0),
            close_reason=reason.value if hasattr(reason, "value") else str(reason),
            order_id=getattr(pos, "order_id", ""),
            conviction_level=getattr(pos, "conviction_level", "unknown"),
            order_size=getattr(pos, "size_usd", 0.0),
        )
        self._append(entry)
        return entry

    def record_halt(
        self, reason: str, level: str = "WARNING", source: str = "system"
    ) -> BlackBoxEntry:
        """Enregistre un halt ou safe mode."""
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.HALT_TRIGGERED.value,
            symbol="ALL",
            signal="HALT",
            score=0,
            regime="unknown",
            personality=source,
            price=0.0,
            reason=reason,
            awareness_level=level,
        )
        self._append(entry)
        return entry

    def record_system_event(
        self, event: str, detail: str = "", symbol: str = "SYSTEM"
    ) -> BlackBoxEntry:
        """Enregistre un événement système (démarrage, crash, reconnexion)."""
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.SYSTEM_EVENT.value,
            symbol=symbol,
            signal="EVENT",
            score=0,
            regime="unknown",
            personality="system",
            price=0.0,
            reason=f"{event}: {detail}" if detail else event,
        )
        self._append(entry)
        return entry

    def record_structured_event(
        self, event_type: str, payload: dict, symbol: str = "SYSTEM"
    ) -> BlackBoxEntry:
        """
        Enregistre un événement structuré non-décisionnel via le chemin
        chiffré canonique (S-03B item 5) — remplace les writers bypass qui
        écrivaient du JSON en clair directement dans le fichier BlackBox
        (cold_start/warmup_report.py, cold_start/bypass_detector.py,
        certification/audit_trail_final.py).

        `payload` est préservé intégralement dans `event_payload` — tous les
        champs des anciens formats plaintext restent accessibles.
        """
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.SYSTEM_EVENT.value,
            symbol=symbol,
            signal="EVENT",
            score=0,
            regime="unknown",
            personality="system",
            price=0.0,
            reason=event_type,
            schema_version=2,
            event_payload={"event_type": event_type, **dict(payload)},
        )
        self._append(entry)
        return entry

    def record_regime_change(
        self, symbol: str, old_regime: str, new_regime: str, price: float
    ) -> BlackBoxEntry:
        self._ensure_loaded()
        entry = BlackBoxEntry(
            ts=time.time(),
            decision_type=DecisionType.REGIME_CHANGE.value,
            symbol=symbol,
            signal="REGIME",
            score=0,
            regime=new_regime,
            personality="regime_detector",
            price=price,
            reason=f"Régime: {old_regime} -> {new_regime}",
        )
        self._append(entry)
        return entry

    # ── Requêtes ──────────────────────────────────────────────────────────────

    def query(
        self,
        decision_type: str = None,
        symbol: str = None,
        regime: str = None,
        since_ts: float = None,
        limit: int = 50,
    ) -> list[BlackBoxEntry]:
        """Filtre les entrées. Retourne les N plus récentes."""
        self._ensure_loaded()
        results = self._entries
        if decision_type:
            results = [e for e in results if e.decision_type == decision_type]
        if symbol:
            results = [e for e in results if e.symbol == symbol]
        if regime:
            results = [e for e in results if e.regime == regime]
        if since_ts:
            results = [e for e in results if e.ts >= since_ts]
        return sorted(results, key=lambda e: e.ts, reverse=True)[:limit]

    def last_refused_trades(self, limit: int = 10) -> list[BlackBoxEntry]:
        return self.query(decision_type=DecisionType.TRADE_REFUSED.value, limit=limit)

    def last_executed_trades(self, limit: int = 10) -> list[BlackBoxEntry]:
        return self.query(decision_type=DecisionType.TRADE_EXECUTED.value, limit=limit)

    def stats(self) -> dict:
        self._ensure_loaded()
        if not self._entries:
            return {"total": 0}
        by_type: dict[str, int] = {}
        for e in self._entries:
            by_type[e.decision_type] = by_type.get(e.decision_type, 0) + 1
        refused = [
            e
            for e in self._entries
            if e.decision_type == DecisionType.TRADE_REFUSED.value
        ]
        refusal_reasons: dict[str, int] = {}
        for e in refused:
            top = e.refused_by[0].split(":")[0] if e.refused_by else "unknown"
            refusal_reasons[top] = refusal_reasons.get(top, 0) + 1
        return {
            "total": len(self._entries),
            "by_type": by_type,
            "top_refusals": sorted(refusal_reasons.items(), key=lambda x: -x[1])[:5],
            "executed_today": sum(
                1
                for e in self._entries
                if e.decision_type == DecisionType.TRADE_EXECUTED.value
                and time.time() - e.ts < 86400
            ),
        }

    def last_n_summary(self, n: int = 5) -> list[str]:
        """Résumé texte des N dernières entrées — pour Telegram."""
        self._ensure_loaded()
        recent = sorted(self._entries, key=lambda e: e.ts, reverse=True)[:n]
        lines = []
        for e in recent:
            t = datetime.fromtimestamp(e.ts).strftime("%H:%M")
            lines.append(
                f"[{t}] {e.decision_type} | {e.symbol} {e.signal} "
                f"score={e.score} {e.regime} | {e.reason[:60]}"
            )
        return lines

    # ── Persistance ───────────────────────────────────────────────────────────

    def _append(self, entry: BlackBoxEntry) -> None:
        # S-03B-R1: durabilité mémoire/disque (MASTER §5). AVANT : l'entrée
        # rejoignait self._entries (donc visible via query()) AVANT même la
        # tentative d'écriture chiffrée — un échec disque laissait un
        # enregistrement "fantôme" interrogeable qui n'avait jamais été
        # persisté. APRÈS : self._entries ne reçoit l'entrée QUE si l'écriture
        # disque a réussi ; un échec incrémente write_failures et l'entrée
        # n'apparaît jamais dans query() sur cette même instance. Aucun fsync
        # ajouté, aucun changement de format de persistance, le pipeline ne
        # plante jamais sur un échec BlackBox.
        with self._stats_lock:
            self._write_attempts += 1
        try:
            enc = _get_enc()
            line = enc.encrypt_line(asdict(entry)) + "\n"
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
            self._entries.append(entry)
            if len(self._entries) > _BB_MAX_SIZE:
                self._entries = self._entries[-_BB_MAX_SIZE:]
            with self._stats_lock:
                self._write_successes += 1
        except Exception as exc:
            with self._stats_lock:
                self._write_failures += 1
            _log.warning("[BlackBox] Sauvegarde échouée: %s", exc)
        _log.debug(
            "[BlackBox] %s | %s %s score=%d | %s",
            entry.decision_type,
            entry.symbol,
            entry.signal,
            entry.score,
            entry.reason,
        )
