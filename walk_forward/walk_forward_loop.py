"""
walk_forward/walk_forward_loop.py — Boucle d'optimisation + validation par fenetre.

La boucle garantit l'isolation complete train / test :
  1. optimizer(train_data)            → params  (uniquement sur les donnees d'entrainement)
  2. validator(test_data, params)     → list[TradeResult]  (uniquement sur le test fold)
  3. compute_oos_metrics(trades)      → OOSMetrics  (100% OOS)

Les callables optimizer et validator sont entierement injectables —
le module ne connait pas la logique de strategie.

Usage :
    def my_optimizer(train: list) -> dict:
        # Optimise sur train, retourne les meilleurs parametres
        return {"threshold": best_threshold}

    def my_validator(test: list, params: dict) -> list[TradeResult]:
        # Simule la strategie sur test avec les params trouves
        return [TradeResult(...)]

    loop = WalkForwardLoop(optimizer=my_optimizer, validator=my_validator)
    result = loop.run_fold(data, window)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from metrics.oos_metrics import OOSMetrics, TradeResult, compute_oos_metrics
from walk_forward.window_splitter import WalkForwardWindow


@dataclass
class FoldResult:
    """
    Resultat complet d'un fold walk-forward.

    fold         : la fenetre utilisee (indices train / test)
    params       : parametres trouves par l'optimiseur sur le train
    oos_metrics  : performance sur le test (hors-echantillon)
    train_metrics: performance sur le train (in-sample, pour diagnostiquer l'overfitting)
    trades       : trades executes sur le test fold
    error        : None si succes, message d'erreur si exception levee
    """

    fold: WalkForwardWindow
    params: Any
    oos_metrics: OOSMetrics
    train_metrics: OOSMetrics
    trades: list[TradeResult]
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None

    @property
    def overfitting_ratio(self) -> Optional[float]:
        """
        OOS Sharpe / Train Sharpe.
        Un ratio < 0.5 suggere un surapprentissage sur le train.
        Retourne None si le train Sharpe est nul.
        """
        if self.train_metrics.sharpe_ratio <= 0:
            return None
        return self.oos_metrics.sharpe_ratio / self.train_metrics.sharpe_ratio

    def as_dict(self) -> dict:
        return {
            "fold_index": self.fold.fold_index,
            "train_range": [self.fold.train_start, self.fold.train_end],
            "test_range": [self.fold.test_start, self.fold.test_end],
            "train_size": self.fold.train_size,
            "test_size": self.fold.test_size,
            "gap": self.fold.gap_size,
            "oos": self.oos_metrics.as_dict(),
            "train": self.train_metrics.as_dict(),
            "overfitting_ratio": (
                round(self.overfitting_ratio, 4)
                if self.overfitting_ratio is not None
                else None
            ),
            "error": self.error,
        }


class WalkForwardLoop:
    """
    Execute la paire (optimizer, validator) sur chaque fenetre walk-forward.

    optimizer  : Callable[[list], Any]
      Recoit uniquement le train fold.
      Retourne des parametres dans n'importe quel format (dict, tuple, objet...).

    validator  : Callable[[list, Any], list[TradeResult]]
      Recoit le test fold + les parametres de l'optimiseur.
      Retourne la liste des trades executes (OOS uniquement).

    train_validator (optionnel) :
      Meme signature que validator mais pour le fold d'entrainement.
      Utilise pour mesurer l'overfitting. Si None, train_metrics = OOSMetrics vide.

    fill_cost_bps : friction realiste par trade (slippage + spread + fees).
      Soustrait de chaque pnl_pct OOS pour obtenir des metriques honnetes.
      Exemple Binance USDT-M Futures : ~6.5 bps (slippage 2 + spread 0.5 + fees 4).
      0.0 = pas d'ajustement (comportement historique).
    """

    def __init__(
        self,
        optimizer: Callable[[list], Any],
        validator: Callable[[list, Any], list[TradeResult]],
        train_validator: Optional[Callable[[list, Any], list[TradeResult]]] = None,
        annualization_factor: float = 252.0,
        risk_free_rate: float = 0.0,
        fill_cost_bps: float = 0.0,
    ) -> None:
        self._optimizer = optimizer
        self._validator = validator
        self._train_validator = train_validator
        self._annualization_factor = annualization_factor
        self._risk_free_rate = risk_free_rate
        self._fill_cost_bps = fill_cost_bps

    def run_fold(self, data: list, window: WalkForwardWindow) -> FoldResult:
        """
        Execute un fold complet.
        Les exceptions internes sont capturees et retournees dans FoldResult.error.
        """
        try:
            train_data = data[window.train_start : window.train_end]
            test_data = data[window.test_start : window.test_end]

            # 1. Optimisation (uniquement sur train)
            params = self._optimizer(train_data)

            # 2. Validation OOS (uniquement sur test)
            oos_trades = self._validator(test_data, params)
            # Appliquer la friction d'execution si fill_cost_bps > 0
            if self._fill_cost_bps > 0.0 and oos_trades:
                _cost_pct = self._fill_cost_bps / 10_000.0 * 100.0
                oos_trades = [
                    TradeResult(
                        timestamp_ms=t.timestamp_ms,
                        pnl_pct=t.pnl_pct - _cost_pct,
                        side=t.side,
                        regime=t.regime,
                    )
                    for t in oos_trades
                ]
            oos_metrics = compute_oos_metrics(
                oos_trades,
                self._annualization_factor,
                self._risk_free_rate,
            )

            # 3. Validation in-sample (optionnel)
            if self._train_validator is not None:
                train_trades = self._train_validator(train_data, params)
                train_metrics = compute_oos_metrics(
                    train_trades,
                    self._annualization_factor,
                    self._risk_free_rate,
                )
            else:
                train_metrics = compute_oos_metrics([], self._annualization_factor)

            return FoldResult(
                fold=window,
                params=params,
                oos_metrics=oos_metrics,
                train_metrics=train_metrics,
                trades=oos_trades,
            )

        except Exception as exc:  # noqa: BLE001
            empty = compute_oos_metrics([], self._annualization_factor)
            return FoldResult(
                fold=window,
                params=None,
                oos_metrics=empty,
                train_metrics=empty,
                trades=[],
                error=str(exc),
            )
