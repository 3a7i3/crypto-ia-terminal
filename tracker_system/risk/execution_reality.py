"""
P0 — RÉALISME EXECUTION (Slippage + Frais)
Simule conditions réelles: slippage 2bps, frais 0.15% maker/0.15% taker
"""

from typing import Dict


class ExecutionReality:
    """
    Ajoute du réalisme aux prix d'exécution et calcul PnL

    Frais réels Binance:
    - Maker: 0.1% (ou moins avec BNB)
    - Taker: 0.1% (normal), 0.15% (élevé)

    Slippage réaliste:
    - Marché normal: 1-2 bps
    - Marché volatil: 5-10 bps
    - Petits caps: 10-50 bps
    """

    def __init__(self,
                 slippage_bps: float = 2.0,
                 fee_maker: float = 0.001,
                 fee_taker: float = 0.0015):
        """
        Args:
            slippage_bps: Slippage en basis points (0.01% = 1 bp)
            fee_maker: Frais maker (0.1%)
            fee_taker: Frais taker (0.15%)
        """
        self.slippage_bps = slippage_bps  # 2 bps
        self.fee_maker = fee_maker  # 0.1%
        self.fee_taker = fee_taker  # 0.15%

    def adjust_entry_price(self, nominal_price: float, side: str = "BUY") -> float:
        """
        Ajuste le prix d'entrée pour réalisme (pire cas)

        BUY: prix monte à cause du slippage + frais taker
        SELL: prix descend
        """
        slippage = nominal_price * (self.slippage_bps / 10000)
        fee = nominal_price * self.fee_taker

        if side.upper() == "BUY":
            return nominal_price + slippage + fee
        else:  # SELL
            return nominal_price - slippage - fee

    def adjust_exit_price(self, nominal_price: float, side: str = "SELL") -> float:
        """
        Ajuste le prix de sortie pour réalisme (pire cas)

        SELL (depuis BUY): prix descend à cause slippage + frais
        BUY (depuis SELL): prix monte
        """
        slippage = nominal_price * (self.slippage_bps / 10000)
        fee = nominal_price * self.fee_taker

        if side.upper() == "SELL":
            return nominal_price - slippage - fee
        else:  # BUY (from SHORT)
            return nominal_price + slippage + fee

    def calculate_realistic_pnl(self,
                                entry_price: float,
                                exit_price: float,
                                side: str = "BUY",
                                quantity: float = 1.0) -> Dict:
        """
        Calcule PnL réaliste avec friction

        Returns:
            {
                "nominal_pnl_usd": float,
                "nominal_pnl_pct": float,
                "realistic_pnl_usd": float,
                "realistic_pnl_pct": float,
                "friction_cost": float,
                "friction_pct": float
            }
        """
        adj_entry = self.adjust_entry_price(entry_price, side)
        adj_exit = self.adjust_exit_price(exit_price, side)

        if side.upper() == "BUY":
            nominal_pnl_per_unit = exit_price - entry_price
            realistic_pnl_per_unit = adj_exit - adj_entry
        else:  # SELL
            nominal_pnl_per_unit = entry_price - exit_price
            realistic_pnl_per_unit = adj_entry - adj_exit

        nominal_pnl_usd = nominal_pnl_per_unit * quantity
        realistic_pnl_usd = realistic_pnl_per_unit * quantity
        friction_cost = nominal_pnl_usd - realistic_pnl_usd

        nominal_pnl_pct = (nominal_pnl_per_unit / entry_price) if entry_price > 0 else 0
        realistic_pnl_pct = (realistic_pnl_per_unit / adj_entry) if adj_entry > 0 else 0
        friction_pct = friction_cost / abs(nominal_pnl_usd) if nominal_pnl_usd != 0 else 0

        return {
            "nominal_pnl_usd": nominal_pnl_usd,
            "nominal_pnl_pct": nominal_pnl_pct,
            "realistic_pnl_usd": realistic_pnl_usd,
            "realistic_pnl_pct": realistic_pnl_pct,
            "friction_cost": friction_cost,
            "friction_pct": friction_pct,
            "adj_entry": adj_entry,
            "adj_exit": adj_exit,
        }

    def get_impact_summary(self, num_trades: int = 100, avg_nominal_pnl_per_trade: float = 0.005) -> Dict:
        """
        Résumé de l'impact sur une série de trades

        Args:
            num_trades: Nombre de trades
            avg_nominal_pnl_per_trade: PnL moyen nominal par trade (ex: 0.005 = 0.5%)

        Returns:
            Impact total de friction
        """
        avg_friction_per_trade = avg_nominal_pnl_per_trade * (self.slippage_bps / 10000 * 2 + self.fee_taker * 2)
        total_friction = avg_friction_per_trade * num_trades * 100

        return {
            "num_trades": num_trades,
            "avg_friction_per_trade_pct": avg_friction_per_trade * 100,
            "total_friction_pct": total_friction,
            "example_on_10000_account": total_friction * 100,
            "message": f"Friction totale: -{total_friction:.2%} sur {num_trades} trades"
        }

    def create_realistic_trade(self, trade: Dict) -> Dict:
        """
        Ajoute des ajustements réalistes à un trade existant

        Input trade:
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_price": 50000,
                "exit_price": 51000,
                "quantity": 0.1
            }

        Returns:
            Trade enrichi avec pnl réaliste
        """
        pnl_calc = self.calculate_realistic_pnl(
            entry_price=trade['entry_price'],
            exit_price=trade['exit_price'],
            side=trade.get('side', 'BUY'),
            quantity=trade.get('quantity', 1.0)
        )

        trade_with_reality = trade.copy()
        trade_with_reality.update({
            "entry_price_adjusted": pnl_calc['adj_entry'],
            "exit_price_adjusted": pnl_calc['adj_exit'],
            "pnl_realistic": pnl_calc['realistic_pnl_usd'],
            "pnl_realistic_pct": pnl_calc['realistic_pnl_pct'],
            "friction_cost": pnl_calc['friction_cost'],
        })

        return trade_with_reality
