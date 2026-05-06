"""
P0 INTEGRATION — Wrapper pour ajouter réalisme + alertes + risque

Utilisation:
    from tracker_system.p0_integration import P0Manager

    p0 = P0Manager(initial_capital=10000.0)
    p0.validate_position(symbol, size, current_positions)
    p0.record_trade_execution(entry_price, exit_price, side, quantity)
    p0.check_alerts(current_equity, current_positions)
"""

from typing import Dict, List, Tuple, Optional, Any
from tracker_system.risk.alert_system import AlertSystem
from tracker_system.risk.portfolio_risk import PortfolioRiskManager
from tracker_system.risk.execution_reality import ExecutionReality


class P0Manager:
    """Gestionnaire central P0 — Intègre AlertSystem + PortfolioRiskManager + ExecutionReality"""

    def __init__(self,
                 initial_capital: float = 10000.0,
                 daily_loss_threshold: float = -100.0,
                 drawdown_threshold: float = 0.15,
                 max_single_exposure: float = 0.20,
                 max_total_exposure: float = 0.80,
                 slippage_bps: float = 2.0,
                 fee_taker: float = 0.0015):
        """
        Initialise tous les composants P0

        Args:
            initial_capital: Capital de départ
            daily_loss_threshold: Max perte jour
            drawdown_threshold: Max drawdown
            max_single_exposure: Max 20% par position
            max_total_exposure: Max 80% total
            slippage_bps: Slippage en basis points
            fee_taker: Frais taker
        """
        self.alert_system = AlertSystem(
            initial_capital=initial_capital,
            daily_loss_threshold=daily_loss_threshold,
            drawdown_threshold=drawdown_threshold,
            position_concentration_threshold=max_total_exposure
        )

        self.risk_manager = PortfolioRiskManager(
            total_capital=initial_capital,
            max_single_exposure=max_single_exposure,
            max_total_exposure=max_total_exposure
        )

        self.execution_reality = ExecutionReality(
            slippage_bps=slippage_bps,
            fee_taker=fee_taker
        )

        self.initial_capital = initial_capital
        self.trades_executed = []

    def validate_position_before_open(self,
                                      symbol: str,
                                      size: float,
                                      current_positions: List[Dict],
                                      estimated_price: float = 1.0) -> Tuple[bool, str, Optional[float]]:
        """
        Valide et ajuste une position avant ouverture

        Returns:
            (valide, raison, taille_suggeree_ou_none)
        """
        valide, raison = self.risk_manager.validate_new_position(
            symbol=symbol,
            size=size,
            current_positions=current_positions,
            estimated_price=estimated_price
        )

        if not valide:
            return False, raison, None

        # Si position valide mais grande, suggérer taille
        if size > self.initial_capital * 0.15:  # Si > 15%
            volatility = self._estimate_volatility(symbol)
            suggested = self.risk_manager.suggest_position_size(
                symbol=symbol,
                volatility=volatility
            )
            if suggested < size:
                return True, "Position grande — taille suggérée", suggested

        return True, "OK", None

    def record_trade_with_reality(self,
                                  symbol: str,
                                  side: str,
                                  entry_price: float,
                                  exit_price: float,
                                  quantity: float) -> Dict[str, Any]:
        """
        Enregistre un trade avec calcul PnL réaliste

        Returns:
            Trade enrichi avec données réaliste
        """
        pnl_calc = self.execution_reality.calculate_realistic_pnl(
            entry_price=entry_price,
            exit_price=exit_price,
            side=side,
            quantity=quantity
        )

        trade = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "entry_price_adjusted": pnl_calc['adj_entry'],
            "exit_price_adjusted": pnl_calc['adj_exit'],
            "pnl_nominal": pnl_calc['nominal_pnl_usd'],
            "pnl_nominal_pct": pnl_calc['nominal_pnl_pct'],
            "pnl_realistic": pnl_calc['realistic_pnl_usd'],
            "pnl_realistic_pct": pnl_calc['realistic_pnl_pct'],
            "friction_cost": pnl_calc['friction_cost'],
            "friction_pct": pnl_calc['friction_pct'],
        }

        self.trades_executed.append(trade)
        return trade

    def update_equity_and_check_alerts(self,
                                       current_equity: float,
                                       current_positions: List[Dict]) -> List[str]:
        """
        Met à jour équité et lance tous les checks d'alerte

        Returns:
            Liste des alertes (vide si OK)
        """
        self.alert_system.update_equity(current_equity)
        alerts = self.alert_system.run_all_checks(current_positions)
        return alerts

    def get_portfolio_summary(self, positions: List[Dict]) -> Dict:
        """Résumé complet du portefeuille et risques"""
        concentration = self.risk_manager.check_portfolio_concentration(positions)

        return {
            "total_positions": len(positions),
            "total_exposure": concentration['total_exposure'],
            "exposure_ratio": concentration['exposure_ratio'],
            "within_limits": concentration['exposure_ratio'] <= self.risk_manager.max_total,
            "breakdown": concentration['breakdown'],
            "alerts": self.alert_system.get_alert_history(),
            "critical_alerts": self.alert_system.get_critical_alerts(),
            "alert_summary": self.alert_system.summary(),
        }

    def get_friction_impact(self, num_trades: int = 100, avg_pnl: float = 0.005) -> Dict:
        """Impact total de la friction sur une série"""
        return self.execution_reality.get_impact_summary(
            num_trades=num_trades,
            avg_nominal_pnl_per_trade=avg_pnl
        )

    def get_trades_summary(self) -> Dict:
        """Résumé des trades exécutés"""
        if not self.trades_executed:
            return {
                "total_trades": 0,
                "total_pnl_nominal": 0.0,
                "total_pnl_realistic": 0.0,
                "total_friction": 0.0,
            }

        total_nominal = sum(t['pnl_nominal'] for t in self.trades_executed)
        total_realistic = sum(t['pnl_realistic'] for t in self.trades_executed)
        total_friction = sum(t['friction_cost'] for t in self.trades_executed)

        return {
            "total_trades": len(self.trades_executed),
            "total_pnl_nominal": total_nominal,
            "total_pnl_realistic": total_realistic,
            "total_friction": total_friction,
            "friction_impact_pct": total_friction / total_nominal if total_nominal != 0 else 0,
        }

    def _estimate_volatility(self, symbol: str) -> float:
        """Estime la volatilité d'un symbole (stub)"""
        # En production: ferait appel à des données réelles
        volatility_map = {
            "BTCUSDT": 0.03,
            "ETHUSDT": 0.04,
            "BNBUSDT": 0.05,
            "LINKUSDT": 0.06,
        }
        return volatility_map.get(symbol, 0.02)

    def reset_daily(self) -> None:
        """Réinitialise les métriques quotidiennes"""
        self.alert_system.reset_daily()


# ============================================================================
# HELPERS
# ============================================================================

def create_default_p0_manager(initial_capital: float = 10000.0) -> P0Manager:
    """Factory pour créer P0Manager avec paramètres par défaut"""
    return P0Manager(
        initial_capital=initial_capital,
        daily_loss_threshold=-100.0,
        drawdown_threshold=0.15,
        max_single_exposure=0.20,
        max_total_exposure=0.80,
        slippage_bps=2.0,
        fee_taker=0.0015
    )
