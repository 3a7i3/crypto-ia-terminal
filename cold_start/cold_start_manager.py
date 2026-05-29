"""
cold_start_manager.py — Orchestrateur du démarrage à froid (P10)

Point d'entrée unique pour le protocole de warmup.
Appelé par advisor_loop.py à chaque cycle tant que LIVE_READY n'est pas atteint.

Philosophie : le système refuse d'être dangereux tant qu'il n'est pas prêt.
Objectif    : confiance opérationnelle, pas un timer.

Usage dans advisor_loop.py :
    _cold_start = ColdStartManager()
    ...
    while True:
        cycle += 1
        if not _cold_start.is_live_ready():
            state = _cold_start.tick(build_system_snapshot())
            if state == WarmupState.FAILED:
                log.critical("[ColdStart] FAILED — %s", _cold_start.failure_reason())
                time.sleep(30)
                continue
            continue  # pas encore prêt — pas d'exécution ce cycle
        # ... logique normale
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Optional

from cold_start.bypass_detector import revoke_live_ready_token, write_live_ready_token
from cold_start.warmup_invariants import WarmupInvariants
from cold_start.warmup_metrics import MetricsHistory, WarmupMetrics
from cold_start.warmup_report import WarmupReport
from cold_start.warmup_signer import WarmupSigner
from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine
from observability.json_logger import get_logger

_log = get_logger("cold_start.cold_start_manager")

# Nombre de cycles en shadow avant de valider LIVE_READY
_SHADOW_VALIDATION_CYCLES = int(os.getenv("P10_SHADOW_MIN_CYCLES", "10"))
# Score DWE minimum pour passer SHADOW_MODE
_DWE_MIN_COVERAGE = float(os.getenv("P10_DWE_MIN_COVERAGE", "0.40"))
# Ticks 0% données consécutifs avant d'échouer (évite d'attendre le timeout)
_MAX_ZERO_DATA_TICKS = int(os.getenv("P10_MAX_ZERO_DATA_TICKS", "10"))
# Durée maximale globale avant alerte (30 min)
_WARMUP_MAX_DURATION_S = float(os.getenv("P10_WARMUP_MAX_DURATION_S", "1800.0"))


def _compute_state_confidence(
    state: WarmupState,
    metrics: WarmupMetrics,
    history: MetricsHistory,
) -> float:
    """
    Calcule un score de confiance adapté à l'état courant.
    Chaque état a ses propres critères de passage.
    """
    if state == WarmupState.BOOTING:
        # Boot = vérifier que les modules essentiels sont joignables
        return 0.90 if metrics.hard_limits_ok else 0.0

    if state == WarmupState.FETCHING_MARKET_DATA:
        # Besoin d'au moins 60% des symboles avec des données
        return (
            metrics.data_coverage
            if metrics.data_coverage >= 0.60
            else metrics.data_coverage * 0.5
        )

    if state == WarmupState.BUILDING_FEATURES:
        # Features suffisamment complètes
        return metrics.avg_feature_confidence

    if state == WarmupState.STABILIZING_REGIMES:
        # Régime stable + cohérent sur plusieurs cycles
        stability = history.stability_score()
        regime = metrics.regime_stability
        return round((regime * 0.6 + stability * 0.4), 4)

    if state == WarmupState.VALIDATING_RISK:
        # Risk sync + pas d'anomalies critiques + probation cohérent
        base = metrics.warmup_score
        if not metrics.risk_sync:
            base *= 0.5
        if not metrics.probation_consistent:
            base *= 0.7
        return round(base, 4)

    if state == WarmupState.SHADOW_MODE:
        # Shadow complet + score stable sur la fenêtre
        if metrics.shadow_cycles_completed < _SHADOW_VALIDATION_CYCLES:
            # Score progressif : monte au fur et à mesure des cycles shadow
            progress = metrics.shadow_cycles_completed / _SHADOW_VALIDATION_CYCLES
            return round(metrics.warmup_score * progress, 4)
        return round(history.avg_score(), 4)

    return metrics.warmup_score


class ColdStartManager:
    """
    Orchestre le protocole de démarrage à froid.

    Interface avec advisor_loop :
        tick(snapshot)        → avance la machine d'état, retourne l'état courant
        is_live_ready()       → True si LIVE_READY atteint
        warmup_score()        → score composite courant [0.0, 1.0]
        failure_reason()      → raison si FAILED
        snapshot()            → état sérialisable pour dashboard
    """

    def __init__(self, scenario_id: Optional[str] = None) -> None:
        self._machine = WarmupStateMachine()
        self._invariants = WarmupInvariants()
        self._history = MetricsHistory(window=5)
        self._signer = WarmupSigner()
        self._session_id = str(uuid.uuid4())[:8]
        self._report = WarmupReport(
            session_id=self._session_id,
            scenario_id=scenario_id,
        )
        self._last_metrics: Optional[WarmupMetrics] = None
        self._shadow_cycles: int = 0
        self._zero_data_ticks: int = 0
        self._prev_state: WarmupState = WarmupState.BOOTING
        self._started_at: float = time.time()
        self._duration_alerted: bool = False
        _log.info("[ColdStart] session=%s démarré", self._session_id)

    # ── Interface principale ─────────────────────────────────────────────────

    def tick(self, system_snapshot: dict) -> WarmupState:
        """
        Avance la machine d'état d'un cycle.

        system_snapshot : dict avec les clés décrites dans WarmupMetrics.
        Retourne l'état courant après le tick.
        """
        if self._machine.state in (WarmupState.LIVE_READY, WarmupState.FAILED):
            return self._machine.state

        # 0. Alerte durée globale > 30 min
        self._check_duration_alert()

        # 1. Construire les métriques depuis le snapshot
        metrics = self._build_metrics(system_snapshot)
        self._last_metrics = metrics
        self._history.record(metrics)

        # 2. Incrémenter le compteur shadow si dans SHADOW_MODE
        if self._machine.state == WarmupState.SHADOW_MODE:
            self._shadow_cycles += 1
            metrics.shadow_cycles_completed = self._shadow_cycles

        # 2b. 0% données N fois → fail sans attendre le timeout mur-horloge
        if (
            self._machine.state == WarmupState.FETCHING_MARKET_DATA
            and metrics.data_coverage == 0.0
        ):
            self._zero_data_ticks += 1
            if self._zero_data_ticks >= _MAX_ZERO_DATA_TICKS:
                new_state = self._machine.force_fail(
                    f"aucune donnée marché après {self._zero_data_ticks} cycles "
                    f"(exchange indisponible ?)"
                )
                self._finalize(new_state, metrics, self.failure_reason())
                return new_state
        else:
            self._zero_data_ticks = 0

        # 3. Vérifier les invariants
        inv_results, critical_fail = self._invariants.check(
            self._machine.state.name, system_snapshot
        )
        inv_summary = self._invariants.summary(inv_results)
        self._report.record_invariants(self._machine.state.name, inv_summary)

        if critical_fail:
            reason = " | ".join(
                r["reason"] for r in inv_summary.get("failed_critical", [])
            )
            new_state = self._machine.force_fail(f"invariant critique: {reason}")
            self._finalize(new_state, metrics, reason)
            return new_state

        # 4. Calculer la confiance pour l'état courant
        confidence = _compute_state_confidence(
            self._machine.state, metrics, self._history
        )

        # 5. Tenter la transition
        prev = self._machine.state
        new_state = self._machine.try_advance(confidence)

        if new_state != prev:
            self._report.record_transition(
                prev, new_state, confidence, metrics.to_dict()
            )
            _log.info(
                "[ColdStart] %s → %s conf=%.3f score=%.3f",
                prev.name,
                new_state.name,
                confidence,
                metrics.warmup_score,
            )

        # 6. Finaliser si état terminal
        if new_state in (WarmupState.LIVE_READY, WarmupState.FAILED):
            self._finalize(new_state, metrics)

        self._prev_state = new_state
        return new_state

    def is_live_ready(self) -> bool:
        return self._machine.state == WarmupState.LIVE_READY

    def is_failed(self) -> bool:
        return self._machine.state == WarmupState.FAILED

    def warmup_score(self) -> float:
        if self._last_metrics is None:
            return 0.0
        return self._last_metrics.warmup_score

    def failure_reason(self) -> str:
        if self._machine.state != WarmupState.FAILED:
            return ""
        history = self._machine.snapshot().get("history", [])
        failed = [h for h in history if h.get("state") == "FAILED"]
        return failed[-1].get("failure_reason", "inconnu") if failed else "inconnu"

    def current_state(self) -> WarmupState:
        return self._machine.state

    def report(self) -> WarmupReport:
        return self._report

    def snapshot(self) -> dict:
        return {
            "session_id": self._session_id,
            "state": self._machine.state.name,
            "warmup_score": self.warmup_score(),
            "shadow_cycles": self._shadow_cycles,
            "live_ready": self.is_live_ready(),
            "failed": self.is_failed(),
            "failure_reason": self.failure_reason() if self.is_failed() else "",
            "metrics": self._last_metrics.to_dict() if self._last_metrics else {},
            "machine": self._machine.snapshot(),
        }

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_int(v, default: int = 0) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def _build_metrics(self, snap: dict) -> WarmupMetrics:
        """Construit un WarmupMetrics depuis le snapshot brut."""
        si = self._safe_int
        sf = self._safe_float
        m = WarmupMetrics()
        m.symbols_ready = si(snap.get("symbols_ready", 0))
        m.symbols_total = max(1, si(snap.get("symbols_total", 100), default=100))
        m.avg_feature_confidence = sf(snap.get("avg_feature_confidence", 0.0))
        m.regime_stability = sf(snap.get("regime_stability", 0.0))
        m.dwe_sample_coverage = sf(snap.get("dwe_sample_coverage", 0.0))
        m.risk_sync = bool(snap.get("risk_sync", False))
        m.hard_limits_ok = bool(snap.get("hard_limits_ok", True))
        m.probation_consistent = bool(snap.get("probation_consistent", True))
        m.evolution_memory_loaded = bool(snap.get("evolution_memory_loaded", False))
        m.transition_cache_populated = bool(
            snap.get("transition_cache_populated", False)
        )
        m.shadow_cycles_completed = self._shadow_cycles
        m.open_positions_unknown = bool(snap.get("open_positions_unknown", False))
        m.anomaly_count = si(snap.get("anomaly_count", 0))
        m.ts = time.time()
        return m

    def _check_duration_alert(self) -> None:
        """Émet une alerte si le warmup total dépasse _WARMUP_MAX_DURATION_S (30 min)."""
        if self._duration_alerted:
            return
        elapsed = time.time() - self._started_at
        if elapsed >= _WARMUP_MAX_DURATION_S:
            _log.warning(
                "[ColdStart] ALERTE DURÉE — warmup dure %.0f min (seuil %.0f min)",
                elapsed / 60,
                _WARMUP_MAX_DURATION_S / 60,
            )
            self._duration_alerted = True

    def _finalize(
        self,
        state: WarmupState,
        metrics: Optional[WarmupMetrics],
        reason: str = "",
    ) -> None:
        self._report.finalize(state, metrics, failure_reason=reason)
        _log.info(
            "[ColdStart] TERMINÉ session=%s état=%s durée=%.1fs",
            self._session_id,
            state.name,
            self._report.duration_s,
        )
        print(self._report.print_summary())
        try:
            self._report.save()
        except Exception as exc:
            _log.debug("[ColdStart] sauvegarde rapport: %s", exc)
        try:
            self._report.archive_to_black_box()
        except Exception as exc:
            _log.debug("[ColdStart] archivage BlackBox: %s", exc)
        # Émettre le token LIVE_READY (ou révoquer si FAILED)
        if state == WarmupState.LIVE_READY:
            try:
                write_live_ready_token(
                    session_id=self._session_id,
                    warmup_score=metrics.warmup_score if metrics else 0.0,
                )
            except Exception as exc:
                _log.warning("[ColdStart] écriture token LIVE_READY: %s", exc)
        elif state == WarmupState.FAILED:
            revoke_live_ready_token()
