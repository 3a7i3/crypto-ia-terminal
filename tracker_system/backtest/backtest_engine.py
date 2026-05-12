"""
BACKTEST ENGINE — Simule trading complet avec système autonome
"""

from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BacktestConfig:
    """Configuration du backtest"""
    initial_capital: float = 10000.0
    symbol: str = "BTCUSDT"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    use_auto_decisions: bool = True
    use_safe_mode: bool = True


class BacktestEngine:
    """Moteur de backtest complet avec système autonome"""

    def __init__(self,
                 config: BacktestConfig,
                 binance_client,
                 auto_orchestrator=None,
                 safe_framework=None):
        """
        Args:
            config: Configuration du backtest
            binance_client: Client Binance (ou stub pour test)
            auto_orchestrator: Orchestrateur de décisions autonomes
            safe_framework: Framework de sécurité
        """
        self.config = config
        self.binance = binance_client
        self.auto_engine = auto_orchestrator
        self.safe_fw = safe_framework

        # État du backtest
        self.capital = config.initial_capital
        self.equity = config.initial_capital
        self.trades = []
        self.positions = {}
        self.daily_values = [config.initial_capital]

    def run(self) -> Dict[str, Any]:
        """
        Exécute le backtest complet

        Returns:
            Résumé des résultats
        """
        print("\n[BACKTEST] Démarrage")
        print(f"  Capital: ${self.capital:,.2f}")
        print(f"  Symbole: {self.config.symbol}")
        print(f"  Auto decisions: {self.config.use_auto_decisions}")
        print(f"  Safe mode: {self.config.use_safe_mode}")

        # Récupérer données historiques
        klines = self.binance.get_klines(
            self.config.symbol,
            interval="1h",
            limit=500
        )

        if not klines:
            return {"error": "No data available"}

        # Simuler chaque bougie
        for i, kline in enumerate(klines):
            price = kline["close"]

            # STEP 1: Décision autonome (si activée)
            if self.config.use_auto_decisions and self.auto_engine:
                metrics = self._calculate_metrics()
                decision, executed = self._auto_decision_cycle(metrics)

                if executed and self.config.use_safe_mode and self.safe_fw:
                    # Exécuter avec safe framework
                    self._safe_execute_decision(decision, metrics)

            # STEP 2: Signaux de trading simples
            signal = self._generate_signal(klines[:i+1])

            # STEP 3: Exécuter trade si signal
            if signal:
                self._execute_trade(self.config.symbol, signal["side"], price)

            # STEP 4: Update equity
            self.equity = self.capital + self._calculate_unrealized_pnl(price)
            self.daily_values.append(self.equity)

            # STEP 5: Monitor (every 50 candles)
            if (i + 1) % 50 == 0:
                print(f"  Candle {i+1}: ${price:,.0f} | Equity: ${self.equity:,.2f}")

        # Fermer positions ouvertes
        final_price = klines[-1]["close"]
        for symbol in list(self.positions.keys()):
            self._execute_trade(symbol, "SELL", final_price)

        # Résultats
        return self._generate_report()

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calcule les métriques pour décisions autonomes"""
        pnls = [t["pnl_pct"] for t in self.trades]

        return {
            "num_trades": len(self.trades),
            "equity": self.equity,
            "capital": self.capital,
            "winrate": len([p for p in pnls if p > 0]) / len(pnls) if pnls else 0,
            "expectancy": sum(pnls) / len(pnls) if pnls else 0,
            "consistency": 0.65,  # Placeholder
        }

    def _auto_decision_cycle(self, metrics: Dict) -> tuple:
        """Exécute un cycle de décision autonome"""
        if not self.auto_engine:
            return None, False

        # Générer décision
        decision = self.auto_engine.engine.decide(
            metrics,
            None,
            {"drawdown": 0.03, "loss_streak": 1}
        )

        return decision, decision.action != "NO_ACTION"

    def _safe_execute_decision(self, decision, metrics):
        """Exécute décision avec sécurité"""
        if not self.safe_fw:
            return

        current_config = {"tp": 0.025, "sl": 0.010}
        historical = [{"pnl_pct": t["pnl_pct"]} for t in self.trades[-20:]]

        new_config, executed, reason = self.safe_fw.execute_decision(
            {"action": decision.action, "params": decision.params},
            metrics,
            historical,
            current_config
        )

        if executed:
            print(f"    [AUTO] {decision.action}: {reason}")

    def _generate_signal(self, klines: List[Dict]) -> Dict:
        """Génère signals de trading simples"""
        if len(klines) < 20:
            return None

        closes = [k["close"] for k in klines[-20:]]
        sma = sum(closes) / 20

        if klines[-1]["close"] > sma and len(self.positions) == 0:
            return {"side": "BUY"}

        if klines[-1]["close"] < sma * 0.98 and len(self.positions) > 0:
            return {"side": "SELL"}

        return None

    def _execute_trade(self, symbol: str, side: str, price: float):
        """Exécute un trade"""
        if side == "BUY":
            qty = self.capital * 0.1 / price  # 10% du capital
            self.positions[symbol] = {"entry": price, "qty": qty}
            self.capital -= qty * price

        elif side == "SELL" and symbol in self.positions:
            pos = self.positions[symbol]
            pnl_usd = (price - pos["entry"]) * pos["qty"]
            pnl_pct = (price - pos["entry"]) / pos["entry"]

            self.trades.append({
                "symbol": symbol,
                "entry": pos["entry"],
                "exit": price,
                "qty": pos["qty"],
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "timestamp": datetime.utcnow().isoformat()
            })

            self.capital += price * pos["qty"]
            del self.positions[symbol]

    def _calculate_unrealized_pnl(self, current_price: float) -> float:
        """Calcule P&L non-réalisé"""
        pnl = 0
        for symbol, pos in self.positions.items():
            pnl += (current_price - pos["entry"]) * pos["qty"]
        return pnl

    def _generate_report(self) -> Dict[str, Any]:
        """Génère rapport final"""
        if not self.trades:
            return {"error": "No trades executed"}

        pnls = [t["pnl_pct"] for t in self.trades]
        wins = len([p for p in pnls if p > 0])

        total_pnl = sum(t["pnl_usd"] for t in self.trades)
        final_capital = self.capital + total_pnl

        return {
            "initial_capital": self.config.initial_capital,
            "final_capital": final_capital,
            "total_pnl": total_pnl,
            "total_pnl_pct": (final_capital / self.config.initial_capital - 1) * 100,
            "num_trades": len(self.trades),
            "wins": wins,
            "losses": len(self.trades) - wins,
            "winrate": wins / len(self.trades) * 100,
            "avg_win": sum(p for p in pnls if p > 0) / wins * 100 if wins > 0 else 0,
            "avg_loss": sum(p for p in pnls if p < 0) / (len(self.trades) - wins) * 100 if wins < len(self.trades) else 0,
            "max_dd": self._calculate_max_dd(),
            "trades": self.trades[-10:],  # Derniers 10 trades
        }

    def _calculate_max_dd(self) -> float:
        """Calcule le drawdown maximum"""
        if not self.daily_values:
            return 0

        peak = self.daily_values[0]
        max_dd = 0

        for value in self.daily_values:
            if value > peak:
                peak = value

            dd = (peak - value) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd * 100
