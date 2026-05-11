"""
P2 — MULTI-ASSET PORTFOLIO MANAGEMENT
Gérer plusieurs actifs avec allocation intelligente
"""

from typing import List, Dict, Tuple
from statistics import mean


class AssetAllocationEngine:
    """Moteur d'allocation d'actifs basé sur Sharpe ratio"""

    def __init__(self,
                 total_capital: float = 10000.0,
                 max_single_asset: float = 0.25,
                 max_correlated_group: float = 0.60,
                 min_required_sharpe: float = 0.5):
        """
        Args:
            total_capital: Capital total
            max_single_asset: Max 25% par actif
            max_correlated_group: Max 60% pour groupe corrélés (ex: crypto)
            min_required_sharpe: Sharpe ratio min pour inclure actif
        """
        self.capital = total_capital
        self.max_single = max_single_asset
        self.max_correlated = max_correlated_group
        self.min_sharpe = min_required_sharpe

    def calculate_optimal_allocation(self,
                                    assets: List[Dict]) -> Dict[str, float]:
        """
        Calcule allocation optimale basée sur Sharpe ratio et corrélations

        Args:
            assets: [
                {
                    "symbol": "BTCUSDT",
                    "sharpe_ratio": 0.85,
                    "volatility": 0.03,
                    "category": "crypto",
                    "current_price": 50000
                },
                ...
            ]

        Returns:
            {"BTCUSDT": 0.25, "ETHUSDT": 0.20, ...}
        """
        # Filter assets by Sharpe ratio
        qualified_assets = [
            a for a in assets
            if a.get("sharpe_ratio", 0) >= self.min_sharpe
        ]

        if not qualified_assets:
            return {a["symbol"]: 0.0 for a in assets}

        # Sort by Sharpe ratio (meilleur d'abord)
        qualified_assets.sort(key=lambda x: x.get("sharpe_ratio", 0), reverse=True)

        allocation = {}
        remaining_capital = self.capital

        # Allocation greedy
        for asset in qualified_assets:
            symbol = asset["symbol"]
            sharpe = asset.get("sharpe_ratio", 0)

            # Proportion based on Sharpe
            proportion = min(
                self.max_single,
                remaining_capital / self.capital,
                (sharpe / 2.0)  # Plus sharpe élevé = plus d'allocation
            )

            allocation[symbol] = proportion * self.capital
            remaining_capital -= allocation[symbol]

        # Normaliser
        total_allocated = sum(allocation.values())
        if total_allocated > 0:
            for symbol in allocation:
                allocation[symbol] /= total_allocated

        return allocation

    def rebalance_portfolio(self,
                           current_holdings: Dict[str, float],
                           target_allocation: Dict[str, float],
                           transaction_cost: float = 0.0015) -> Dict[str, float]:
        """
        Calcule trades nécessaires pour rebalancer

        Args:
            current_holdings: {"BTCUSDT": 2500, "ETHUSDT": 1500}
            target_allocation: {"BTCUSDT": 0.40, "ETHUSDT": 0.30}
            transaction_cost: Frais par trade (0.15%)

        Returns:
            {"BTCUSDT": -500, "ETHUSDT": +300}  (négatif = vendre, positif = acheter)
        """
        total_value = sum(current_holdings.values())

        rebalance_trades = {}

        for symbol in set(list(current_holdings.keys()) + list(target_allocation.keys())):
            current_value = current_holdings.get(symbol, 0)
            target_value = target_allocation.get(symbol, 0) * total_value

            trade_size = target_value - current_value

            # Check if rebalance is worth it (vs transaction costs)
            if abs(trade_size) > total_value * transaction_cost * 2:
                rebalance_trades[symbol] = trade_size

        return rebalance_trades


class PortfolioPerformanceTracker:
    """Suivi de performance multi-actif"""

    def __init__(self):
        self.trades_history = []
        self.daily_values = []

    def add_trade(self, symbol: str, side: str, price: float, quantity: float, pnl: float):
        """Enregistre un trade"""
        self.trades_history.append({
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "pnl": pnl,
            "timestamp": None  # À faire
        })

    def get_asset_breakdown(self) -> Dict[str, float]:
        """Retourne la répartition par actif"""
        total_pnl = sum(t["pnl"] for t in self.trades_history)
        breakdown = {}

        for symbol in set(t["symbol"] for t in self.trades_history):
            trades = [t for t in self.trades_history if t["symbol"] == symbol]
            symbol_pnl = sum(t["pnl"] for t in trades)

            breakdown[symbol] = {
                "pnl": symbol_pnl,
                "pct": symbol_pnl / total_pnl if total_pnl != 0 else 0,
                "num_trades": len(trades)
            }

        return breakdown

    def get_correlation_matrix(self, returns_data: Dict[str, List[float]]) -> Dict[Tuple[str, str], float]:
        """Calcule matrice de corrélation entre actifs"""
        correlations = {}

        symbols = list(returns_data.keys())

        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i:]:
                if sym1 == sym2:
                    corr = 1.0
                else:
                    corr = self._calculate_correlation(
                        returns_data[sym1],
                        returns_data[sym2]
                    )

                correlations[(sym1, sym2)] = corr
                correlations[(sym2, sym1)] = corr

        return correlations

    @staticmethod
    def _calculate_correlation(returns1: List[float], returns2: List[float]) -> float:
        """Calcule corrélation de Pearson"""
        if len(returns1) < 2 or len(returns2) < 2:
            return 0.0

        mean1 = mean(returns1)
        mean2 = mean(returns2)

        numerator = sum(
            (returns1[i] - mean1) * (returns2[i] - mean2)
            for i in range(min(len(returns1), len(returns2)))
        )

        sum_sq1 = sum((r - mean1) ** 2 for r in returns1)
        sum_sq2 = sum((r - mean2) ** 2 for r in returns2)

        denominator = (sum_sq1 * sum_sq2) ** 0.5

        if denominator == 0:
            return 0.0

        return numerator / denominator


class MultiAssetOptimizer:
    """Optimiseur pour stratégies multi-actif"""

    def __init__(self, capital: float = 10000.0):
        self.capital = capital
        self.allocation_engine = AssetAllocationEngine(capital)
        self.tracker = PortfolioPerformanceTracker()

    def optimize_for_maximum_sharpe(self, assets: List[Dict]) -> Dict:
        """
        Optimise portfolio pour Sharpe ratio maximum

        Args:
            assets: Liste des actifs avec métriques

        Returns:
            {
                "allocation": {"BTCUSDT": 0.40, ...},
                "expected_sharpe": float,
                "expected_volatility": float,
                "recommendation": str
            }
        """
        # Calculer allocation
        allocation = self.allocation_engine.calculate_optimal_allocation(assets)

        # Calculer Sharpe attendu
        weighted_sharpe = sum(
            allocation.get(a["symbol"], 0) * a.get("sharpe_ratio", 0)
            for a in assets
        )

        weighted_volatility = sum(
            allocation.get(a["symbol"], 0) * a.get("volatility", 0)
            for a in assets
        )

        return {
            "allocation": allocation,
            "expected_sharpe": weighted_sharpe,
            "expected_volatility": weighted_volatility,
            "recommendation": self._generate_recommendation(allocation, weighted_sharpe)
        }

    def _generate_recommendation(self, allocation: Dict, sharpe: float) -> str:
        """Génère recommandation"""
        top_assets = sorted(
            allocation.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        recommendation = "Allocation optimale: "
        recommendation += ", ".join(
            f"{symbol} {pct*100:.0f}%"
            for symbol, pct in top_assets if pct > 0
        )

        if sharpe > 1.0:
            recommendation += " (Sharpe excellent)"
        elif sharpe > 0.5:
            recommendation += " (Sharpe bon)"
        else:
            recommendation += " (Sharpe faible - ajouter actifs)"

        return recommendation

    def calculate_sector_limits(self, assets: List[Dict]) -> Dict[str, float]:
        """
        Calcule les limites par secteur

        Ex: Crypto max 60%, Stocks max 30%, Forex max 10%
        """
        sectors = {}

        for asset in assets:
            sector = asset.get("sector", "other")
            if sector not in sectors:
                sectors[sector] = 0

            sectors[sector] += 1

        # Default limits
        sector_limits = {
            "crypto": 0.60,
            "stocks": 0.30,
            "forex": 0.10,
            "commodities": 0.10,
            "other": 0.05
        }

        return {s: sector_limits.get(s, 0.05) for s in sectors}
