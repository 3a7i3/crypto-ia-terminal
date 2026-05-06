"""
P0 — GESTIONNAIRE DE RISQUE PORTEFEUILLE
Valide: exposition max, corrélation, concentration par actif
"""

from typing import List, Dict, Tuple, Optional
from statistics import mean, stdev


class PortfolioRiskManager:
    """Vérifie les limites de risque au niveau portefeuille"""

    def __init__(self,
                 total_capital: float = 10000.0,
                 max_single_exposure: float = 0.20,
                 max_total_exposure: float = 0.80,
                 max_drawdown_portfolio: float = 0.15,
                 max_avg_correlation: float = 0.70):
        """
        Args:
            total_capital: Capital total (ex: 10000)
            max_single_exposure: Max 20% par position
            max_total_exposure: Max 80% total
            max_drawdown_portfolio: Max 15% drawdown
            max_avg_correlation: Max corrélation moyenne 0.70
        """
        self.capital = total_capital
        self.max_single = max_single_exposure
        self.max_total = max_total_exposure
        self.max_dd = max_drawdown_portfolio
        self.max_corr = max_avg_correlation
        self.correlations_cache: Dict[Tuple[str, str], float] = {}

    def validate_new_position(self,
                              symbol: str,
                              size: float,
                              current_positions: List[Dict],
                              estimated_price: float = 1.0) -> Tuple[bool, str]:
        """
        Valide si on peut ouvrir une nouvelle position

        Args:
            symbol: Ex: "BTCUSDT"
            size: Taille (en USD ou nombre de coins)
            current_positions: Positions ouvertes
            estimated_price: Prix estimé

        Returns:
            (valide: bool, raison: str)
        """
        position_value = size * estimated_price

        # Check 1: Taille absolue
        if self.capital > 0:
            single_ratio = position_value / self.capital
            if single_ratio > self.max_single:
                return False, f"Position {single_ratio:.1%} > max {self.max_single:.1%}"

        # Check 2: Exposition totale
        total_current = sum(p.get('size', 0) * p.get('price', 1.0) for p in current_positions)
        total_after = total_current + position_value

        if self.capital > 0:
            total_ratio = total_after / self.capital
            if total_ratio > self.max_total:
                return False, f"Total {total_ratio:.1%} > max {self.max_total:.1%}"

        # Check 3: Corrélation moyenne avec positions existantes
        if current_positions:
            correlations = []
            for pos in current_positions:
                corr = self._get_correlation(symbol, pos.get('symbol', ''))
                correlations.append(corr)

            if correlations:
                avg_corr = mean(correlations)
                if avg_corr > self.max_corr:
                    return False, f"Corrélation {avg_corr:.2f} > max {self.max_corr:.2f}"

        return True, "OK"

    def check_portfolio_concentration(self, positions: List[Dict]) -> Dict[str, any]:
        """Analyse la concentration du portefeuille"""
        if not positions:
            return {
                "total_exposure": 0.0,
                "max_single": 0.0,
                "is_concentrated": False,
                "breakdown": {}
            }

        total = sum(p.get('size', 0) for p in positions)
        breakdown = {}

        for pos in positions:
            symbol = pos.get('symbol', 'UNKNOWN')
            size = pos.get('size', 0)
            ratio = (size / total) if total > 0 else 0  # Pas de *100, c'est un decimal
            breakdown[symbol] = ratio

        max_single = max(breakdown.values()) if breakdown else 0
        is_concentrated = total > self.capital * self.max_total

        return {
            "total_exposure": total,
            "total_capital": self.capital,
            "exposure_ratio": total / self.capital if self.capital > 0 else 0,
            "max_single_ratio": max_single,
            "is_concentrated": is_concentrated,
            "breakdown": breakdown
        }

    def suggest_position_size(self, symbol: str, volatility: float = 0.02) -> float:
        """
        Suggère une taille de position basée sur Kelly Criterion

        Args:
            symbol: Ex: "BTCUSDT"
            volatility: Volatilité estimée (ex: 0.02 = 2%)

        Returns:
            Taille suggérée en USD
        """
        # Taille conservative: 5% du capital par position
        base_size = self.capital * 0.05

        # Ajustement volatilité: moins volatil = plus grand
        volatility_factor = 1.0 / max(volatility, 0.001)
        suggested = base_size * min(volatility_factor, 2.0)  # Cap à 2x

        # Vérifier limites
        single_max = self.capital * self.max_single
        return min(suggested, single_max)

    def _get_correlation(self, symbol1: str, symbol2: str) -> float:
        """
        Retourne corrélation entre deux symboles
        En production: ferait appel à API historique
        """
        if symbol1 == symbol2:
            return 1.0

        # Cache
        key = tuple(sorted([symbol1, symbol2]))
        if key in self.correlations_cache:
            return self.correlations_cache[key]

        # Corrélations par défaut (crypto)
        crypto_symbols = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "LINKUSDT", "ADAUSDT"}

        if symbol1 in crypto_symbols and symbol2 in crypto_symbols:
            corr = 0.75  # Crypto très corrélées
        else:
            corr = 0.30  # Autres actifs

        self.correlations_cache[key] = corr
        return corr

    def get_portfolio_report(self, positions: List[Dict]) -> Dict:
        """Rapport complet du portefeuille"""
        concentration = self.check_portfolio_concentration(positions)

        return {
            "capital": self.capital,
            "total_positions": len(positions),
            "total_exposure": concentration['total_exposure'],
            "exposure_ratio": concentration['exposure_ratio'],
            "is_within_limits": concentration['exposure_ratio'] <= self.max_total,
            "max_single_allowed": self.capital * self.max_single,
            "max_total_allowed": self.capital * self.max_total,
            "breakdown": concentration['breakdown'],
            "recommendations": self._generate_recommendations(concentration)
        }

    def _generate_recommendations(self, concentration: Dict) -> List[str]:
        """Génère des recommandations basées sur l'état"""
        recs = []

        if concentration['exposure_ratio'] > self.max_total * 0.9:
            recs.append("Exposition proche du max — réduire nouvelles positions")

        if concentration['exposure_ratio'] < self.max_total * 0.3:
            recs.append("Exposition basse — peut augmenter si stratégie valide")

        symbols = concentration['breakdown']
        if symbols:
            max_sym = max(symbols, key=lambda k: symbols[k])
            if symbols[max_sym] > 0.4:
                recs.append(f"{max_sym} représente {symbols[max_sym]:.1%} — réduire concentration")

        return recs
