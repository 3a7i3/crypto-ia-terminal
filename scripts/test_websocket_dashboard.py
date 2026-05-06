#!/usr/bin/env python3
"""
TEST P1 — Dashboard WebSocket Client
Simule des updates de métriques et envoie des alertes
"""

import asyncio
import aiohttp
import json
import random
from datetime import datetime


class DashboardTestClient:
    """Client pour tester le dashboard WebSocket"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.equity = 10000.0
        self.trades_count = 0
        self.wins = 0

    async def update_metrics(self):
        """Envoie une update de métriques"""
        # Simulation: équité fluctue, trades augmentent
        self.equity *= random.uniform(0.995, 1.005)
        self.trades_count += random.randint(0, 2)

        if random.random() < 0.6:
            self.wins += 1

        metrics = {
            "equity": round(self.equity, 2),
            "daily_pnl": round(self.equity - 10000, 2),
            "total_trades": self.trades_count,
            "winrate": self.wins / self.trades_count if self.trades_count > 0 else 0,
            "max_drawdown": random.uniform(0.01, 0.20),
            "sharpe_ratio": random.uniform(0.5, 2.0),
            "profit_factor": random.uniform(1.0, 3.0),
            "open_positions": random.randint(0, 3),
            "regime": random.choice(["bull_trend", "bear_trend", "range", "scalp"]),
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.base_url}/api/metrics", json=metrics) as resp:
                    if resp.status == 200:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Metrics sent - Equity: ${metrics['equity']:.2f}")
                    else:
                        print(f"Error: {resp.status}")
            except Exception as e:
                print(f"Connection error: {e}")

    async def send_alert(self, message: str, severity: str = "warning"):
        """Envoie une alerte"""
        alert = {
            "type": "trade_event",
            "message": message,
            "severity": severity
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.base_url}/api/alert", json=alert) as resp:
                    if resp.status == 200:
                        print(f"  -> Alert sent: {message}")
            except Exception as e:
                print(f"Connection error: {e}")

    async def check_status(self):
        """Vérifie le statut du serveur"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/api/status") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data
            except Exception as e:
                print(f"Connection error: {e}")
        return None

    async def simulate_trading_day(self, duration_seconds: int = 30, update_interval: int = 2):
        """Simule une journée de trading"""
        print(f"\nSimulating trading day for {duration_seconds} seconds...")
        print(f"Updates every {update_interval} seconds\n")

        end_time = datetime.now().timestamp() + duration_seconds

        while datetime.now().timestamp() < end_time:
            await self.update_metrics()

            # Random alerts
            if random.random() < 0.3:
                messages = [
                    "Position opened: BTCUSDT BUY",
                    "Position closed: BTCUSDT +1.2%",
                    "Regime changed to bull_trend",
                    "Drawdown alert: 12%",
                ]
                await self.send_alert(
                    random.choice(messages),
                    severity=random.choice(["warning", "success", "info"])
                )

            await asyncio.sleep(update_interval)

        print("\nTrading day simulation complete!")
        status = await self.check_status()
        if status:
            print(f"\nFinal Status:")
            print(f"  Connected clients: {status['connected_clients']}")
            print(f"  Final equity: ${status['current_metrics']['equity']:.2f}")


async def main():
    """Main test"""
    print("\n" + "="*70)
    print("[P1-WEBSOCKET] DASHBOARD CLIENT TEST")
    print("="*70)

    print("\nNOTE: Assurez-vous que le serveur tourne:")
    print("  python dashboard/websocket_dashboard.py")
    print("\nPuis accédez au dashboard:")
    print("  http://localhost:8000")

    client = DashboardTestClient()

    # Check server availability
    print("\nChecking server availability...")
    status = await client.check_status()
    if status is None:
        print("\n[ERROR] Cannot connect to server at http://localhost:8000")
        print("Please start the server first:")
        print("  python dashboard/websocket_dashboard.py")
        return

    print("[OK] Server is running!")

    # Run simulation
    await client.simulate_trading_day(duration_seconds=30, update_interval=2)


if __name__ == "__main__":
    asyncio.run(main())
