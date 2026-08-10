"""
P1 — ADVANCED METRICS
Sharpe ratio, Sortino ratio, CAGR, Calmar ratio, etc.
"""

from typing import List, Dict, Tuple
from statistics import mean, stdev
import math


class AdvancedMetrics:
    """Calcul de métriques financières avancées"""

    def __init__(self, risk_free_rate: float = 0.02):
        """
        Args:
            risk_free_rate: Taux sans risque annualisé (ex: 0.02 = 2%)
        """
        self.risk_free_rate = risk_free_rate

    def calculate_sharpe_ratio(self,
                              returns: List[float],
                              period_days: int = 252) -> float:
        """
        Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev

        Args:
            returns: Liste des returns quotidiens/horaires
            period_days: Jours annualisés (252 pour quotidien, 252*24 pour horaire)

        Returns:
            Sharpe ratio annualisé
        """
        if len(returns) < 2:
            return 0.0

        mean_return = mean(returns)
        std_dev = stdev(returns)

        if std_dev == 0:
            return 0.0

        # Annualize
        annual_return = mean_return * period_days
        annual_std = std_dev * math.sqrt(period_days)

        sharpe = (annual_return - self.risk_free_rate) / annual_std
        return sharpe

    def calculate_sortino_ratio(self,
                               returns: List[float],
                               target_return: float = 0.0,
                               period_days: int = 252) -> float:
        """
        Sortino Ratio = (Mean Return - Target) / Downside Deviation

        Comme Sharpe mais penalise seulement volatilité baisse

        Args:
            returns: Liste des returns
            target_return: Return cible (ex: 0.0 = pas de perte)
            period_days: Jours annualisés

        Returns:
            Sortino ratio annualisé
        """
        if len(returns) < 2:
            return 0.0

        mean_return = mean(returns)

        # Downside deviation: std dev des returns négatifs seulement
        downside_returns = [r for r in returns if r < target_return]

        if not downside_returns:
            # Tous les returns sont positifs
            return float('inf') if mean_return > target_return else 0.0

        downside_std = stdev(downside_returns)

        if downside_std == 0:
            return float('inf') if mean_return > target_return else 0.0

        # Annualize
        annual_return = mean_return * period_days
        annual_downside = downside_std * math.sqrt(period_days)

        sortino = (annual_return - target_return) / annual_downside
        return sortino

    def calculate_cagr(self,
                       starting_value: float,
                       ending_value: float,
                       years: float) -> float:
        """
        Compound Annual Growth Rate

        CAGR = (Ending / Starting) ^ (1/Years) - 1

        Args:
            starting_value: Valeur initiale
            ending_value: Valeur finale
            years: Nombre d'années (peut être fraction)

        Returns:
            CAGR en %
        """
        if starting_value <= 0 or years <= 0:
            return 0.0

        ratio = ending_value / starting_value
        cagr = (ratio ** (1 / years)) - 1

        return cagr

    def calculate_calmar_ratio(self,
                               returns: List[float],
                               starting_value: float,
                               period_days: int = 252) -> float:
        """
        Calmar Ratio = Annual Return / Max Drawdown

        Mesure return par unité de drawdown max

        Args:
            returns: Liste des returns
            starting_value: Valeur initiale (pour equity curve)
            period_days: Jours annualisés

        Returns:
            Calmar ratio
        """
        if len(returns) < 1:
            return 0.0

        # Reconstruire equity curve
        equity = [starting_value]
        for ret in returns:
            equity.append(equity[-1] * (1 + ret))

        # Drawdown max
        max_dd = 0.0
        peak = equity[0]

        for value in equity[1:]:
            if value > peak:
                peak = value

            dd = (peak - value) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        if max_dd == 0:
            return 0.0

        # Annual return
        annual_return = mean(returns) * period_days

        calmar = annual_return / max_dd
        return calmar

    def calculate_max_drawdown(self,
                              starting_value: float,
                              returns: List[float]) -> Tuple[float, int, int]:
        """
        Calcule le drawdown max et période

        Returns:
            (max_drawdown %, jour_peak, jour_trough)
        """
        if len(returns) < 1:
            return 0.0, 0, 0

        equity = [starting_value]
        for ret in returns:
            equity.append(equity[-1] * (1 + ret))

        max_dd = 0.0
        peak_idx = 0
        trough_idx = 0
        peak_value = equity[0]
        peak_idx_temp = 0

        for i, value in enumerate(equity[1:], 1):
            if value > peak_value:
                peak_value = value
                peak_idx_temp = i

            dd = (peak_value - value) / peak_value if peak_value > 0 else 0

            if dd > max_dd:
                max_dd = dd
                peak_idx = peak_idx_temp
                trough_idx = i

        return max_dd, peak_idx, trough_idx

    def calculate_win_rate(self,
                          returns: List[float]) -> Tuple[float, int, int]:
        """
        Win rate et breakdown gains/pertes

        Returns:
            (win_rate %, num_wins, num_losses)
        """
        if len(returns) < 1:
            return 0.0, 0, 0

        wins = len([r for r in returns if r > 0])
        losses = len([r for r in returns if r < 0])
        total = wins + losses

        if total == 0:
            return 0.0, 0, 0

        win_rate = wins / total if total > 0 else 0.0
        return win_rate, wins, losses

    def calculate_profit_factor(self,
                               returns: List[float]) -> float:
        """
        Profit Factor = Total Gains / Total Losses

        Returns:
            Profit factor (> 1.0 = profitable)
        """
        if len(returns) < 1:
            return 0.0

        total_gains = sum(r for r in returns if r > 0)
        total_losses = abs(sum(r for r in returns if r < 0))

        if total_losses == 0:
            return float('inf') if total_gains > 0 else 0.0

        return total_gains / total_losses

    def calculate_recovery_factor(self,
                                 net_profit: float,
                                 max_drawdown_usd: float) -> float:
        """
        Recovery Factor = Net Profit / Max Drawdown (USD)

        Returns:
            Recovery factor
        """
        if max_drawdown_usd == 0:
            return 0.0

        return net_profit / max_drawdown_usd

    def get_full_report(self,
                        starting_capital: float,
                        ending_capital: float,
                        returns: List[float],
                        years: float,
                        period_days: int = 252) -> Dict:
        """Rapport complet de toutes les métriques"""

        # Equity curve
        equity = [starting_capital]
        for ret in returns:
            equity.append(equity[-1] * (1 + ret))

        max_dd, dd_peak, dd_trough = self.calculate_max_drawdown(starting_capital, returns)
        max_dd_usd = starting_capital * max_dd

        win_rate, num_wins, num_losses = self.calculate_win_rate(returns)
        profit_factor = self.calculate_profit_factor(returns)

        net_profit = ending_capital - starting_capital
        net_profit_pct = (ending_capital / starting_capital - 1) if starting_capital > 0 else 0

        return {
            "starting_capital": starting_capital,
            "ending_capital": ending_capital,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "num_trades": len(returns),
            "years": years,
            "cagr": self.calculate_cagr(starting_capital, ending_capital, years),
            "sharpe_ratio": self.calculate_sharpe_ratio(returns, period_days),
            "sortino_ratio": self.calculate_sortino_ratio(returns, 0.0, period_days),
            "calmar_ratio": self.calculate_calmar_ratio(returns, starting_capital, period_days),
            "max_drawdown": max_dd,
            "max_drawdown_usd": max_dd_usd,
            "max_drawdown_period": (dd_peak, dd_trough),
            "win_rate": win_rate,
            "num_wins": num_wins,
            "num_losses": num_losses,
            "profit_factor": profit_factor,
            "recovery_factor": self.calculate_recovery_factor(net_profit, max_dd_usd),
            "avg_return": mean(returns) if returns else 0.0,
            "std_dev": stdev(returns) if len(returns) > 1 else 0.0,
        }


def create_advanced_metrics_manager(risk_free_rate: float = 0.02) -> AdvancedMetrics:
    """Factory pour créer manager"""
    return AdvancedMetrics(risk_free_rate=risk_free_rate)
