"""
adaptive_calibration_engine.py — Self-Recalibration Engine

Ajuste automatiquement les paramètres du système en fonction des
performances récentes : seuils de conviction, poids d'arbitration,
seuils de régime, taille des positions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.ai_evolution.adaptive_calibration_engine")
_CALIBRATION_PATH = Path("databases/calibration_state.json")


@dataclass
class CalibrationState:
    """Paramètres du système actuellement calibrés."""

    # Seuils de conviction
    conviction_min_threshold: float = 0.40
    conviction_high_threshold: float = 0.70

    # Arbitration
    arbitration_execute_threshold: float = 0.35
    arbitration_reject_threshold: float = -0.20

    # Taille de position (multiplicateurs)
    size_scale_bull: float = 1.0
    size_scale_bear: float = 0.8
    size_scale_chop: float = 0.5
    size_scale_high_vol: float = 0.3

    # Régime
    regime_confidence_min: float = 0.45

    # Exécution
    max_acceptable_slippage_bps: float = 30.0

    # Meta
    last_calibration: float = field(default_factory=time.time)
    calibration_count: int = 0
    performance_at_last_calib: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class AdaptiveCalibrationEngine:
    """
    Ajuste les paramètres du système selon les performances récentes.
    S'appuie sur les données du UnifiedLearningLayer et du ModelDegradationMonitor.

    Stratégie d'adaptation :
    - Performance dégradée → paramètres plus conservateurs
    - Performance améliorée → paramètres légèrement assouplis
    - Régime particulier sous-performant → réduire la taille sur ce régime
    """

    # Fréquence de calibration
    MIN_INTERVAL_SECONDS = 3600  # toutes les heures au minimum
    MIN_TRADES_FOR_CALIB = 10  # minimum de trades avant calibration

    def __init__(self) -> None:
        self._state = self._load_state()
        self._last_calib_time: float = 0.0

    @property
    def state(self) -> CalibrationState:
        return self._state

    def calibrate(
        self,
        recent_win_rate: float,
        recent_avg_pnl: float,
        regime_win_rates: dict[str, float],
        degradation_alerts: list,
        n_recent_trades: int = 0,
    ) -> CalibrationState:
        """
        Lance une calibration si les conditions sont remplies.
        Retourne l'état calibré.
        """
        now = time.time()
        if (now - self._last_calib_time) < self.MIN_INTERVAL_SECONDS:
            return self._state
        if n_recent_trades < self.MIN_TRADES_FOR_CALIB:
            return self._state

        _log.info(
            "[Calibration] Calibration #%d démarrée (WR=%.0f%%)",
            self._state.calibration_count + 1,
            recent_win_rate * 100,
        )

        # Ajustement global basé sur le win rate
        self._adjust_global_thresholds(recent_win_rate, recent_avg_pnl)

        # Ajustement par régime
        self._adjust_regime_sizes(regime_win_rates)

        # Ajustement si alertes de dégradation
        if any(a.severity == "critical" for a in degradation_alerts):
            self._emergency_conservative_mode()

        self._state.last_calibration = now
        self._state.calibration_count += 1
        self._state.performance_at_last_calib = recent_win_rate
        self._last_calib_time = now
        self._save_state()

        _log.info(
            "[Calibration] Nouvelle conviction_min=%.2f, size_scale_chop=%.2f",
            self._state.conviction_min_threshold,
            self._state.size_scale_chop,
        )
        return self._state

    def get_size_scale(self, regime: str) -> float:
        mapping = {
            "bull": self._state.size_scale_bull,
            "bear": self._state.size_scale_bear,
            "chop": self._state.size_scale_chop,
            "high_vol": self._state.size_scale_high_vol,
        }
        return mapping.get(regime, 0.5)

    def apply_to_arbitrator(self, arbitrator) -> None:
        """Injecte les seuils calibrés dans le DecisionArbitrator."""
        arbitrator.EXECUTE_THRESHOLD = self._state.arbitration_execute_threshold
        arbitrator.REJECT_THRESHOLD = self._state.arbitration_reject_threshold

    # ------------------------------------------------------------------
    # Ajustements internes
    # ------------------------------------------------------------------

    def _adjust_global_thresholds(self, win_rate: float, avg_pnl: float) -> None:
        if win_rate < 0.40:
            # Mauvaise période → plus conservateur
            self._state.conviction_min_threshold = min(
                self._state.conviction_min_threshold + 0.03, 0.65
            )
            self._state.arbitration_execute_threshold = min(
                self._state.arbitration_execute_threshold + 0.03, 0.55
            )
        elif win_rate > 0.60 and avg_pnl > 0.005:
            # Bonne période → légèrement plus agressif
            self._state.conviction_min_threshold = max(
                self._state.conviction_min_threshold - 0.01, 0.30
            )
            self._state.arbitration_execute_threshold = max(
                self._state.arbitration_execute_threshold - 0.01, 0.25
            )

    def _adjust_regime_sizes(self, regime_win_rates: dict[str, float]) -> None:
        for regime, wr in regime_win_rates.items():
            attr = f"size_scale_{regime}"
            current = getattr(self._state, attr, 0.5)
            if wr < 0.35:
                setattr(self._state, attr, max(current * 0.90, 0.1))
            elif wr > 0.60:
                setattr(self._state, attr, min(current * 1.05, 1.2))

    def _emergency_conservative_mode(self) -> None:
        """Mode ultra-conservateur en cas d'alerte critique."""
        _log.warning("[Calibration] MODE CONSERVATEUR D'URGENCE activé")
        self._state.conviction_min_threshold = 0.65
        self._state.arbitration_execute_threshold = 0.50
        self._state.size_scale_bull = 0.5
        self._state.size_scale_bear = 0.4
        self._state.size_scale_chop = 0.2
        self._state.size_scale_high_vol = 0.1

    def _save_state(self) -> None:
        try:
            _CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _CALIBRATION_PATH.open("w", encoding="utf-8") as f:
                json.dump(self._state.to_dict(), f, indent=2)
        except Exception as exc:
            _log.debug("[Calibration] save error: %s", exc)

    def _load_state(self) -> CalibrationState:
        try:
            if _CALIBRATION_PATH.exists():
                with _CALIBRATION_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                state = CalibrationState()
                for k, v in data.items():
                    if hasattr(state, k):
                        setattr(state, k, v)
                _log.info("[Calibration] État chargé depuis disque")
                return state
        except Exception as exc:
            _log.debug("[Calibration] load error: %s", exc)
        return CalibrationState()
