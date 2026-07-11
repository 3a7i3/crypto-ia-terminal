"""
self_awareness_engine.py — Self-Awareness & Failure Prediction Engine

Le bot surveille 4 dimensions de dérive en continu :

  1. Performance Drift   — winrate/Sharpe récent vs baseline
  2. Behavioral Drift    — overtrading, revenge trading, hors-personnalité
  3. Market Mismatch     — stratégie dans le mauvais régime
  4. Infrastructure Drift — latence, slippage, exchange lag

Niveaux de réponse automatique :
  NIVEAU 1 → réduction taille (×0.5)
  NIVEAU 2 → safe mode (alertes suspendues)
  NIVEAU 3 → halt temporaire (N minutes)
  NIVEAU 4 → kill switch + Telegram critique

Le bot cesse de trader "vite" pour trader "juste".
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.self_awareness_engine")


class DangerLevel(IntEnum):
    OK = 0
    CAUTION = 1  # réduction taille
    WARNING = 2  # safe mode
    DANGER = 3  # halt temporaire
    CRITICAL = 4  # kill switch


@dataclass
class DriftSignal:
    """Un signal de dérive détecté."""

    dimension: str  # "performance" | "behavioral" | "market" | "infra"
    metric: str  # nom précis de la métrique
    value: float  # valeur courante
    baseline: float  # valeur de référence
    severity: DangerLevel
    message: str
    ts: float = field(default_factory=time.time)


@dataclass
class AwarenessState:
    """État courant de conscience du bot."""

    level: DangerLevel = DangerLevel.OK
    active_drifts: list = field(default_factory=list)
    size_factor: float = 1.0
    halt_until: float = 0.0
    safe_mode: bool = False
    last_evaluated: float = 0.0
    cycles_since_reset: int = 0


class SelfAwarenessEngine:
    """
    Moniteur de conscience du bot.

    Usage :
        engine = SelfAwarenessEngine()
        engine.record_trade(pnl_pct, sharpe, regime, personality,
                            latency_ms, slippage_pct)
        state  = engine.evaluate()
        if state.level >= DangerLevel.DANGER:
            # halt trading
    """

    # ── Seuils configurables ───────────────────────────────────────────────────

    # Performance
    BASELINE_WINDOW = int(os.getenv("SA_BASELINE_WINDOW", "50"))  # trades pour baseline
    RECENT_WINDOW = int(os.getenv("SA_RECENT_WINDOW", "10"))  # trades fenêtre récente
    WR_DROP_CAUTION = float(
        os.getenv("SA_WR_DROP_CAUTION", "0.15")
    )  # winrate chute 15%
    WR_DROP_WARNING = float(
        os.getenv("SA_WR_DROP_WARNING", "0.25")
    )  # winrate chute 25%
    SHARPE_DROP_WARN = float(os.getenv("SA_SHARPE_DROP", "0.5"))  # Sharpe chute de 0.5
    DD_ACCEL_WARN = float(os.getenv("SA_DD_ACCEL", "0.03"))  # drawdown +3% sur fenêtre

    # Comportemental
    OVERTRADE_WINDOW = int(os.getenv("SA_OVERTRADE_WINDOW", "60"))  # secondes
    OVERTRADE_MAX = int(os.getenv("SA_OVERTRADE_MAX", "3"))  # max ordres/fenêtre
    REVENGE_LOSS_SEQ = int(
        os.getenv("SA_REVENGE_LOSSES", "2")
    )  # pertes consec → risk revenge
    REVENGE_SIZE_MULT = float(
        os.getenv("SA_REVENGE_MULT", "1.3")
    )  # taille augmente > seuil

    # Infra
    LATENCY_WARN_MS = float(os.getenv("SA_LATENCY_WARN", "500"))  # ms
    LATENCY_CRIT_MS = float(os.getenv("SA_LATENCY_CRIT", "2000"))
    SLIPPAGE_WARN = float(os.getenv("SA_SLIPPAGE_WARN", "0.003"))  # 0.3%
    SLIPPAGE_CRIT = float(os.getenv("SA_SLIPPAGE_CRIT", "0.01"))  # 1%

    # Halt
    HALT_DURATION_L3 = float(os.getenv("SA_HALT_MINUTES", "30"))  # minutes niveau 3
    CRITICAL_HALT_SECONDS = float(
        os.getenv("SA_CRITICAL_HALT_SECONDS", "86400")
    )  # 24h par défaut
    # Après N halts DANGER sans aucun trade → rétrogradation automatique WARNING
    FREEZE_OVERRIDE_HALTS = int(os.getenv("SA_FREEZE_HALTS", "3"))

    def __init__(self, on_level_change: Optional[Callable] = None) -> None:
        self._state = AwarenessState()
        self._on_level_change = on_level_change

        # Historique trades
        self._trades: deque = deque(maxlen=self.BASELINE_WINDOW + 20)

        # Historique ordres (pour overtrading)
        self._order_timestamps: deque = deque(maxlen=50)

        # Tailles d'ordres récentes (pour revenge trading)
        self._order_sizes: deque = deque(maxlen=20)

        # Latence / slippage récents
        self._latencies: deque = deque(maxlen=20)
        self._slippages: deque = deque(maxlen=20)

        # Régimes et personnalités (pour market mismatch)
        self._regime_history: deque = deque(maxlen=20)
        self._personality_history: deque = deque(maxlen=20)

        # Événements / journal
        self._events: list[dict] = []

        # Compteur de halts DANGER consécutifs sans trade
        self._halts_without_trade: int = 0

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record_trade(
        self,
        pnl_pct: float,
        sharpe: float = 0.0,
        regime: str = "unknown",
        personality: str = "unknown",
        latency_ms: float = 0.0,
        slippage_pct: float = 0.0,
        order_size: float = 0.0,
    ) -> None:
        ts = time.time()
        self._halts_without_trade = 0
        self._trades.append(
            {
                "ts": ts,
                "pnl": pnl_pct,
                "sharpe": sharpe,
                "regime": regime,
                "personality": personality,
            }
        )
        self._order_timestamps.append(ts)
        self._order_sizes.append(order_size)
        if latency_ms > 0:
            self._latencies.append(latency_ms)
        if slippage_pct > 0:
            self._slippages.append(slippage_pct)
        self._regime_history.append(regime)
        self._personality_history.append(personality)

    def record_signal(
        self,
        regime: str,
        personality: str,
        latency_ms: float = 0.0,
    ) -> None:
        """Enregistre un signal (même refusé) — pour détecter l'overtrading."""
        self._order_timestamps.append(time.time())
        self._regime_history.append(regime)
        self._personality_history.append(personality)
        if latency_ms > 0:
            self._latencies.append(latency_ms)

    # ── Évaluation principale ─────────────────────────────────────────────────

    def evaluate(self) -> AwarenessState:
        """
        Évalue les 4 dimensions de dérive.
        Retourne l'état avec le niveau de danger le plus élevé détecté.
        """
        # Pas assez de données
        if len(self._trades) < max(3, self.RECENT_WINDOW // 2):
            self._state.last_evaluated = time.time()
            return self._state

        drifts = []
        drifts += self._check_performance_drift()
        drifts += self._check_behavioral_drift()
        drifts += self._check_market_mismatch()
        drifts += self._check_infra_drift()

        # Niveau global = max des sévérités
        max_level = max((d.severity for d in drifts), default=DangerLevel.OK)

        # Filtrage : si on est en halt actif, ne pas réenclencher
        if self._state.halt_until > time.time():
            self._state.active_drifts = drifts
            self._state.last_evaluated = time.time()
            return self._state

        # Escape freeze : après N halts sans trade → DANGER rétrogradé WARNING
        if (
            max_level >= DangerLevel.DANGER
            and self._halts_without_trade >= self.FREEZE_OVERRIDE_HALTS
        ):
            _log.warning(
                "[SelfAwareness] FREEZE_OVERRIDE — %d halts consécutifs sans trade"
                " → cap WARNING (size×0.25)",
                self._halts_without_trade,
            )
            max_level = DangerLevel.WARNING

        # Transition de niveau
        old_level = self._state.level
        self._apply_level(max_level, drifts)

        if old_level != self._state.level:
            self._log_event(
                "level_change",
                {
                    "from": old_level.name,
                    "to": self._state.level.name,
                    "drifts": [d.message for d in drifts if d.severity == max_level],
                },
            )
            if self._on_level_change:
                try:
                    self._on_level_change(self._state)
                except Exception:
                    pass

        self._state.active_drifts = drifts
        self._state.last_evaluated = time.time()
        self._state.cycles_since_reset += 1
        return self._state

    def reset(self) -> None:
        """Reset manuel après intervention humaine."""
        _log.info("[SelfAwareness] Reset manuel — retour à OK")
        self._state = AwarenessState()
        self._log_event("manual_reset", {})

    def operator_resume(self, full_reset: bool = False) -> None:
        """
        Reprise explicite après /RESUME opérateur.

        - full_reset=True  : reset complet (historique conservé, état remis à OK)
        - full_reset=False : lève uniquement le halt et rétrograde en WARNING
                             pour repartir en mode prudent.
        """
        if full_reset:
            self.reset()
            self._log_event("operator_resume", {"mode": "full_reset"})
            return

        was_halted = self._state.halt_until > time.time()
        self._state.halt_until = 0.0
        if self._state.level >= DangerLevel.DANGER:
            self._state.level = DangerLevel.WARNING
            self._state.size_factor = 0.25
            self._state.safe_mode = True
        self._halts_without_trade = 0
        self._log_event(
            "operator_resume",
            {
                "mode": "controlled",
                "was_halted": was_halted,
                "new_level": self._state.level.name,
            },
        )
        _log.warning(
            "[SelfAwareness] RESUME opérateur — halt levé, niveau=%s",
            self._state.level.name,
        )

    def state(self) -> AwarenessState:
        return self._state

    def is_safe_to_trade(self) -> bool:
        if self._state.halt_until > time.time():
            return False
        return self._state.level < DangerLevel.DANGER

    def effective_size_factor(self) -> float:
        return self._state.size_factor

    def report(self) -> dict:
        s = self._state
        return {
            "level": s.level.name,
            "size_factor": s.size_factor,
            "safe_mode": s.safe_mode,
            "halted": s.halt_until > time.time(),
            "halt_remaining": max(0, s.halt_until - time.time()),
            "active_drifts": [
                {
                    "dim": d.dimension,
                    "metric": d.metric,
                    "msg": d.message,
                    "severity": d.severity.name,
                }
                for d in s.active_drifts
            ],
            "recent_winrate": self._recent_winrate(),
            "baseline_winrate": self._baseline_winrate(),
            "recent_sharpe": self._recent_sharpe(),
            "events": self._events[-10:],
        }

    # ── 1. Performance Drift ──────────────────────────────────────────────────

    def _check_performance_drift(self) -> list[DriftSignal]:
        signals = []
        # Garde ADR-0013 : même seuil que _check_market_mismatch (ligne ~469)
        # — sans elle, drawdown_acceleration (ci-dessous) n'était protégé par
        # aucune garde de taille d'échantillon alors que win_rate/sharpe en
        # avaient une de fait via le fallback baseline==recent. Un WARNING
        # pouvait se déclencher sur aussi peu que 3 trades (incident 2026-07-10,
        # SAFE_MODE sur N=5).
        if len(self._trades) < self.RECENT_WINDOW:
            return signals

        recent = list(self._trades)[-self.RECENT_WINDOW :]
        baseline = list(self._trades)[: -self.RECENT_WINDOW] or list(self._trades)

        wr_recent = self._winrate(recent)
        wr_baseline = self._winrate(baseline)
        wr_drop = wr_baseline - wr_recent

        sh_recent = self._avg_sharpe(recent)
        sh_baseline = self._avg_sharpe(baseline)
        sh_drop = sh_baseline - sh_recent

        # Win rate
        if wr_drop >= self.WR_DROP_WARNING:
            signals.append(
                DriftSignal(
                    "performance",
                    "win_rate",
                    wr_recent,
                    wr_baseline,
                    DangerLevel.WARNING,
                    f"Win rate chute {wr_drop:.0%} ({wr_baseline:.0%}→{wr_recent:.0%})",
                )
            )
        elif wr_drop >= self.WR_DROP_CAUTION:
            signals.append(
                DriftSignal(
                    "performance",
                    "win_rate",
                    wr_recent,
                    wr_baseline,
                    DangerLevel.CAUTION,
                    f"Win rate en baisse {wr_drop:.0%}"
                    f" ({wr_baseline:.0%}→{wr_recent:.0%})",
                )
            )

        # Sharpe
        if sh_drop >= self.SHARPE_DROP_WARN and sh_baseline > 0.3:
            signals.append(
                DriftSignal(
                    "performance",
                    "sharpe",
                    sh_recent,
                    sh_baseline,
                    DangerLevel.WARNING,
                    f"Sharpe dégradé ({sh_baseline:.2f}→{sh_recent:.2f})",
                )
            )

        # Drawdown accélération
        recent_pnls = [t["pnl"] for t in recent]
        cumdd = self._max_drawdown_series(recent_pnls)
        if cumdd >= self.DD_ACCEL_WARN:
            lvl = (
                DangerLevel.DANGER
                if cumdd >= self.DD_ACCEL_WARN * 2
                else DangerLevel.WARNING
            )
            signals.append(
                DriftSignal(
                    "performance",
                    "drawdown_acceleration",
                    cumdd,
                    0.0,
                    lvl,
                    f"Drawdown accéléré: {cumdd:.1%} sur {len(recent)} trades récents",
                )
            )

        return signals

    # ── 2. Behavioral Drift ───────────────────────────────────────────────────

    def _check_behavioral_drift(self) -> list[DriftSignal]:
        signals = []

        # Overtrading — trop d'ordres dans la fenêtre glissante
        now = time.time()
        window = [t for t in self._order_timestamps if now - t <= self.OVERTRADE_WINDOW]
        if len(window) > self.OVERTRADE_MAX:
            signals.append(
                DriftSignal(
                    "behavioral",
                    "overtrading",
                    len(window),
                    self.OVERTRADE_MAX,
                    DangerLevel.WARNING,
                    f"Overtrading: {len(window)} ordres"
                    f" en {self.OVERTRADE_WINDOW}s (max {self.OVERTRADE_MAX})",
                )
            )

        # Revenge trading — pertes consécutives + taille qui augmente
        recent_trades = list(self._trades)[-self.REVENGE_LOSS_SEQ * 2 :]
        if len(recent_trades) >= self.REVENGE_LOSS_SEQ:
            last_n = recent_trades[-self.REVENGE_LOSS_SEQ :]
            if all(t["pnl"] < 0 for t in last_n):
                sizes = list(self._order_sizes)[-self.REVENGE_LOSS_SEQ :]
                if len(sizes) >= 2 and sizes[-1] > sizes[0] * self.REVENGE_SIZE_MULT:
                    signals.append(
                        DriftSignal(
                            "behavioral",
                            "revenge_trading",
                            sizes[-1],
                            sizes[0],
                            DangerLevel.DANGER,
                            f"Pattern revenge trading détecté"
                            f" — {self.REVENGE_LOSS_SEQ} pertes + taille augmentée",
                        )
                    )

        # Trades hors personnalité dominante
        if len(self._personality_history) >= 10:
            pers = list(self._personality_history)[-10:]
            dominant = max(set(pers), key=pers.count)
            outliers = sum(1 for p in pers[-3:] if p != dominant)
            if outliers >= 2:
                signals.append(
                    DriftSignal(
                        "behavioral",
                        "personality_drift",
                        float(outliers),
                        1.0,
                        DangerLevel.CAUTION,
                        f"Dérive personnalité: {outliers}/3 trades"
                        f" hors mode dominant ({dominant})",
                    )
                )

        return signals

    # ── 3. Market Mismatch ────────────────────────────────────────────────────

    def _check_market_mismatch(self) -> list[DriftSignal]:
        signals = []
        if len(self._trades) < self.RECENT_WINDOW:
            return signals

        recent = list(self._trades)[-self.RECENT_WINDOW :]

        # Régimes très instables → faux signaux récurrents
        regimes = [t["regime"] for t in recent]
        unique = len(set(regimes))
        if unique >= 4 and len(recent) >= 8:
            signals.append(
                DriftSignal(
                    "market",
                    "regime_instability",
                    float(unique),
                    2.0,
                    DangerLevel.CAUTION,
                    f"Régime très instable: {unique} régimes"
                    f" différents en {len(recent)} cycles",
                )
            )

        # Corrélation signal/résultat qui chute — stratégie dans mauvais régime
        wins_by_regime: dict[str, list[float]] = {}
        for t in recent:
            wins_by_regime.setdefault(t["regime"], []).append(
                1.0 if t["pnl"] > 0 else 0.0
            )
        for rg, outcomes in wins_by_regime.items():
            if len(outcomes) >= 4:
                wr = sum(outcomes) / len(outcomes)
                if wr < 0.35:
                    signals.append(
                        DriftSignal(
                            "market",
                            "regime_mismatch",
                            wr,
                            0.5,
                            DangerLevel.WARNING,
                            f"Win rate {wr:.0%} en régime '{rg}' — stratégie inadaptée",
                        )
                    )

        return signals

    # ── 4. Infrastructure Drift ───────────────────────────────────────────────

    def _check_infra_drift(self) -> list[DriftSignal]:
        signals = []

        # Latence
        if self._latencies:
            avg_lat = sum(self._latencies) / len(self._latencies)
            if avg_lat >= self.LATENCY_CRIT_MS:
                signals.append(
                    DriftSignal(
                        "infra",
                        "latency",
                        avg_lat,
                        self.LATENCY_WARN_MS,
                        DangerLevel.DANGER,
                        f"Latence critique: {avg_lat:.0f}ms"
                        f" (seuil: {self.LATENCY_CRIT_MS:.0f}ms)",
                    )
                )
            elif avg_lat >= self.LATENCY_WARN_MS:
                signals.append(
                    DriftSignal(
                        "infra",
                        "latency",
                        avg_lat,
                        self.LATENCY_WARN_MS,
                        DangerLevel.CAUTION,
                        f"Latence élevée: {avg_lat:.0f}ms",
                    )
                )

        # Slippage
        if self._slippages:
            avg_slip = sum(self._slippages) / len(self._slippages)
            if avg_slip >= self.SLIPPAGE_CRIT:
                signals.append(
                    DriftSignal(
                        "infra",
                        "slippage",
                        avg_slip,
                        self.SLIPPAGE_WARN,
                        DangerLevel.WARNING,
                        f"Slippage critique: {avg_slip:.3%}",
                    )
                )
            elif avg_slip >= self.SLIPPAGE_WARN:
                signals.append(
                    DriftSignal(
                        "infra",
                        "slippage",
                        avg_slip,
                        self.SLIPPAGE_WARN,
                        DangerLevel.CAUTION,
                        f"Slippage anormal: {avg_slip:.3%}",
                    )
                )

        return signals

    # ── Application du niveau ─────────────────────────────────────────────────

    def _apply_level(self, level: DangerLevel, drifts: list[DriftSignal]) -> None:
        self._state.level = level

        if level == DangerLevel.OK:
            self._state.size_factor = 1.0
            self._state.safe_mode = False

        elif level == DangerLevel.CAUTION:
            self._state.size_factor = 0.5
            self._state.safe_mode = False
            _log.warning("[SelfAwareness] CAUTION — taille réduite à 50%%")

        elif level == DangerLevel.WARNING:
            self._state.size_factor = 0.25
            self._state.safe_mode = True
            _log.warning("[SelfAwareness] WARNING — safe mode + taille 25%%")

        elif level == DangerLevel.DANGER:
            self._state.size_factor = 0.0
            self._state.safe_mode = True
            self._state.halt_until = time.time() + self.HALT_DURATION_L3 * 60
            self._halts_without_trade += 1
            _log.error(
                "[SelfAwareness] DANGER — halt %d min | %s",
                int(self.HALT_DURATION_L3),
                " | ".join(
                    d.message for d in drifts if d.severity >= DangerLevel.DANGER
                ),
            )

        elif level == DangerLevel.CRITICAL:
            self._state.size_factor = 0.0
            self._state.safe_mode = True
            self._state.halt_until = time.time() + self.CRITICAL_HALT_SECONDS
            _log.critical(
                "[SelfAwareness] CRITICAL — kill switch déclenché (halt %.0fs)",
                self.CRITICAL_HALT_SECONDS,
            )
            self._send_telegram_critical(drifts)

    def _send_telegram_critical(self, drifts: list[DriftSignal]) -> None:
        try:
            from supervision.notifications.telegram_notifier import TelegramNotifier

            msgs = "\n".join(f"• {d.message}" for d in drifts[:5])
            TelegramNotifier().send(
                f"SELF-AWARENESS CRITIQUE\n"
                f"Trading suspendu 24h — dérives détectées:\n{msgs}\n"
                f"Envoyer /RESUME pour reprendre manuellement."
            )
        except Exception:
            pass

    # ── Helpers stats ─────────────────────────────────────────────────────────

    @staticmethod
    def _winrate(trades: list[dict]) -> float:
        if not trades:
            return 0.0
        return sum(1 for t in trades if t["pnl"] > 0) / len(trades)

    @staticmethod
    def _avg_sharpe(trades: list[dict]) -> float:
        sharpes = [t["sharpe"] for t in trades if t.get("sharpe", 0) > 0]
        return sum(sharpes) / len(sharpes) if sharpes else 0.0

    @staticmethod
    def _max_drawdown_series(pnls: list[float]) -> float:
        peak = 0.0
        dd = 0.0
        cum = 0.0
        for p in pnls:
            cum += p
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
        return dd

    def _recent_winrate(self) -> float:
        recent = list(self._trades)[-self.RECENT_WINDOW :]
        return self._winrate(recent)

    def _baseline_winrate(self) -> float:
        baseline = list(self._trades)[: -self.RECENT_WINDOW] or list(self._trades)
        return self._winrate(baseline)

    def _recent_sharpe(self) -> float:
        recent = list(self._trades)[-self.RECENT_WINDOW :]
        return self._avg_sharpe(recent)

    def _log_event(self, event: str, data: dict) -> None:
        self._events.append({"ts": time.time(), "event": event, **data})
        if len(self._events) > 200:
            self._events = self._events[-200:]
