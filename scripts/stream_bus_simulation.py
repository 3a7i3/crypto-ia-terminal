"""Manual StreamBus simulation harness."""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TestSuite")


@dataclass
class Tick:
    symbol: str
    timestamp: float
    kind: str
    data: dict


@dataclass
class LatestSnapshot:
    orderbooks: dict = field(default_factory=dict)
    trades: dict = field(default_factory=dict)
    tickers: dict = field(default_factory=dict)
    funding: dict = field(default_factory=dict)
    whale_alerts: list = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)
    tick_count: int = 0
    drop_count: int = 0

    def get_mid_price(self, symbol: str) -> Optional[float]:
        ob = self.orderbooks.get(symbol)
        if ob and ob.get("bids") and ob.get("asks"):
            return (ob["bids"][0][0] + ob["asks"][0][0]) / 2
        return self.tickers.get(symbol, {}).get("last")

    def get_spread(self, symbol: str) -> Optional[float]:
        ob = self.orderbooks.get(symbol)
        if ob and ob.get("bids") and ob.get("asks"):
            bid, ask = ob["bids"][0][0], ob["asks"][0][0]
            return (ask - bid) / bid if bid > 0 else None
        return None

    def get_orderbook_imbalance(self, symbol: str, depth: int = 10) -> Optional[float]:
        ob = self.orderbooks.get(symbol)
        if not ob:
            return None
        bid_vol = sum(qty for _, qty in ob.get("bids", [])[:depth])
        ask_vol = sum(qty for _, qty in ob.get("asks", [])[:depth])
        total = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total > 0 else 0.0


class StreamBus:
    def __init__(
        self,
        symbols: list,
        whale_threshold_usd: float = 500_000,
        queue_maxsize: int = 5000,
        trade_history_size: int = 200,
        on_whale: Optional[Callable] = None,
    ):
        self.symbols = symbols
        self.whale_threshold_usd = whale_threshold_usd
        self.queue_maxsize = queue_maxsize
        self.on_whale = on_whale

        self.snapshot = LatestSnapshot()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False
        self._trade_buffer = defaultdict(lambda: deque(maxlen=trade_history_size))

    async def start(self) -> None:
        self._running = True
        await self._process_queue()

    async def stop(self) -> None:
        self._running = False

    async def _enqueue(self, tick: Tick) -> None:
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(tick)
            self.snapshot.drop_count += 1

    async def _process_queue(self) -> None:
        while self._running:
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                self._apply(tick)
                self.snapshot.tick_count += 1
                self.snapshot.updated_at = time.time()
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error(f"Queue processor error: {exc}")

    def _apply(self, tick: Tick) -> None:
        symbol = tick.symbol
        if tick.kind == "orderbook":
            self.snapshot.orderbooks[symbol] = tick.data
        elif tick.kind == "trade":
            self._trade_buffer[symbol].append(tick.data)
            self.snapshot.trades[symbol] = list(self._trade_buffer[symbol])
            self._check_whale(symbol, tick.data)
        elif tick.kind == "ticker":
            self.snapshot.tickers[symbol] = tick.data
        elif tick.kind == "funding":
            self.snapshot.funding[symbol] = tick.data

    def _check_whale(self, symbol: str, trade: dict) -> None:
        cost = trade.get("cost", 0)
        if cost >= self.whale_threshold_usd:
            alert = {
                "symbol": symbol,
                "side": trade["side"],
                "amount_usd": cost,
                "price": trade["price"],
                "timestamp": time.time(),
            }
            self.snapshot.whale_alerts.append(alert)
            if len(self.snapshot.whale_alerts) > 50:
                self.snapshot.whale_alerts = self.snapshot.whale_alerts[-50:]
            if self.on_whale:
                asyncio.create_task(self._fire_whale_callback(alert))

    async def _fire_whale_callback(self, alert: dict) -> None:
        try:
            if asyncio.iscoroutinefunction(self.on_whale):
                await self.on_whale(alert)
            else:
                self.on_whale(alert)
        except Exception as exc:
            logger.error(f"Whale callback error: {exc}")

    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "tick_count": self.snapshot.tick_count,
            "drop_count": self.snapshot.drop_count,
            "drop_rate": self.snapshot.drop_count / max(self.snapshot.tick_count, 1),
            "symbols_with_ob": len(self.snapshot.orderbooks),
            "last_update_age": time.time() - self.snapshot.updated_at,
        }


class MarketSimulator:
    BASE_PRICES = {
        "BTC/USDT": 65_000.0,
        "ETH/USDT": 3_200.0,
        "SOL/USDT": 170.0,
    }

    def __init__(self, bus: StreamBus, tick_rate: float = 0.01):
        self.bus = bus
        self.tick_rate = tick_rate
        self._prices = dict(self.BASE_PRICES)
        self._t = 0.0

    async def run(
        self,
        duration: float,
        inject_whale_at: float = 2.0,
        inject_error_at: float = 3.5,
    ) -> None:
        start = time.time()
        whale_sent = False
        error_sent = False

        while time.time() - start < duration:
            elapsed = time.time() - start
            self._t += self.tick_rate

            for symbol in self.bus.symbols:
                base = self.BASE_PRICES[symbol]
                drift = math.sin(self._t * 0.3) * base * 0.002
                noise = random.gauss(0, base * 0.0005)
                self._prices[symbol] = max(
                    self._prices[symbol] + drift * self.tick_rate + noise,
                    base * 0.90,
                )
                price = self._prices[symbol]
                spread_bps = random.uniform(1, 5) / 10_000

                bids = [
                    [
                        round(price * (1 - spread_bps * (i + 1)), 2),
                        round(random.uniform(0.1, 3.0), 4),
                    ]
                    for i in range(5)
                ]
                asks = [
                    [
                        round(price * (1 + spread_bps * (i + 1)), 2),
                        round(random.uniform(0.1, 3.0), 4),
                    ]
                    for i in range(5)
                ]
                await self.bus._enqueue(
                    Tick(symbol=symbol, timestamp=time.time(), kind="orderbook", data={"bids": bids, "asks": asks})
                )

                side = random.choice(["buy", "sell"])
                amount = random.uniform(0.01, 0.5)
                cost = amount * price
                await self.bus._enqueue(
                    Tick(
                        symbol=symbol,
                        timestamp=time.time(),
                        kind="trade",
                        data={"price": price, "amount": amount, "side": side, "cost": cost},
                    )
                )
                await self.bus._enqueue(
                    Tick(
                        symbol=symbol,
                        timestamp=time.time(),
                        kind="ticker",
                        data={"last": price, "volume": random.uniform(1000, 5000), "change": drift / base * 100},
                    )
                )

            if not whale_sent and elapsed >= inject_whale_at:
                price = self._prices["BTC/USDT"]
                await self.bus._enqueue(
                    Tick(
                        symbol="BTC/USDT",
                        timestamp=time.time(),
                        kind="trade",
                        data={"price": price, "amount": 12.0, "side": "buy", "cost": 12.0 * price},
                    )
                )
                whale_sent = True
                logger.info(f"[SIM] Whale trade injecté — BTC/USDT BUY ${12.0 * price:,.0f}")

            if not error_sent and elapsed >= inject_error_at:
                await self.bus._enqueue(
                    Tick(
                        symbol="BTC/USDT",
                        timestamp=time.time(),
                        kind="trade",
                        data={"price": None, "amount": None, "side": "buy", "cost": None},
                    )
                )
                error_sent = True
                logger.info("[SIM] Tick corrompu injecté (None values)")

            await asyncio.sleep(self.tick_rate)


class FakeMLCycle:
    def __init__(self, bus: StreamBus, cycle_interval: float = 0.5):
        self.bus = bus
        self.cycle_interval = cycle_interval
        self.cycles_run = 0
        self.prices_seen = []
        self.imbalances_seen = []

    async def run(self, duration: float) -> None:
        start = time.time()
        while time.time() - start < duration:
            snap = self.bus.snapshot
            btc_price = snap.get_mid_price("BTC/USDT")
            imbalance = snap.get_orderbook_imbalance("BTC/USDT")

            if btc_price:
                self.prices_seen.append(btc_price)
            if imbalance is not None:
                self.imbalances_seen.append(imbalance)

            self.cycles_run += 1
            await asyncio.sleep(self.cycle_interval)

        logger.info(
            f"[ML] {self.cycles_run} cycles — BTC last={self.prices_seen[-1]:,.2f} | imbalance last={self.imbalances_seen[-1]:.3f}"
            if self.prices_seen and self.imbalances_seen
            else f"[ML] {self.cycles_run} cycles — aucune donnée reçue"
        )


PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    message = f"  [{status}] {name}"
    if detail:
        message += f"  ({detail})"
    print(message)
    results.append((name, condition))


async def test_snapshot_population():
    print("\n── T1 : Population du snapshot ──")
    bus = StreamBus(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    await asyncio.gather(sim.run(duration=0.5, inject_whale_at=99, inject_error_at=99))
    await asyncio.sleep(0.1)

    check("Orderbook BTC peuplé", "BTC/USDT" in bus.snapshot.orderbooks)
    check("Orderbook ETH peuplé", "ETH/USDT" in bus.snapshot.orderbooks)
    check("Ticker BTC peuplé", "BTC/USDT" in bus.snapshot.tickers)
    check("Trades BTC peuplés", "BTC/USDT" in bus.snapshot.trades)
    check("Tick count > 0", bus.snapshot.tick_count > 0, f"{bus.snapshot.tick_count} ticks")
    await bus.stop()


async def test_mid_price_and_spread():
    print("\n── T2 : Mid-price et spread ──")
    bus = StreamBus(symbols=["BTC/USDT"])
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    await asyncio.gather(sim.run(0.3, inject_whale_at=99, inject_error_at=99))
    await asyncio.sleep(0.05)

    mid = bus.snapshot.get_mid_price("BTC/USDT")
    spread = bus.snapshot.get_spread("BTC/USDT")
    check("Mid price non-None", mid is not None, f"{mid:,.2f}" if mid else "None")
    check("Mid price dans plage BTC", mid is not None and 58_000 < mid < 72_000, f"{mid:,.2f}" if mid else "None")
    check("Spread positif", spread is not None and spread > 0, f"{spread*10000:.2f} bps" if spread else "None")
    check("Spread < 10 bps", spread is not None and spread < 0.001, f"{spread*10000:.2f} bps" if spread else "None")
    await bus.stop()


async def test_orderbook_imbalance():
    print("\n── T3 : Orderbook imbalance ──")
    bus = StreamBus(symbols=["BTC/USDT"])
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    await asyncio.gather(sim.run(0.3, inject_whale_at=99, inject_error_at=99))
    await asyncio.sleep(0.05)

    imbalance = bus.snapshot.get_orderbook_imbalance("BTC/USDT")
    check("Imbalance non-None", imbalance is not None, str(imbalance))
    check("Imbalance entre -1 et 1", imbalance is not None and -1.0 <= imbalance <= 1.0, f"{imbalance:.4f}" if imbalance is not None else "None")
    await bus.stop()


async def test_whale_detection():
    print("\n── T4 : Détection whale ──")
    whale_alerts_received = []

    async def on_whale(alert):
        whale_alerts_received.append(alert)

    bus = StreamBus(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"], whale_threshold_usd=500_000, on_whale=on_whale)
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    await asyncio.gather(sim.run(duration=3.0, inject_whale_at=0.5, inject_error_at=99))
    await asyncio.sleep(0.2)

    check("Whale alert dans snapshot", len(bus.snapshot.whale_alerts) > 0, f"{len(bus.snapshot.whale_alerts)} alertes")
    check("Callback on_whale appelé", len(whale_alerts_received) > 0)
    if whale_alerts_received:
        alert = whale_alerts_received[0]
        check("Alert contient symbol", "symbol" in alert and alert["symbol"] == "BTC/USDT")
        check("Alert contient side=buy", alert.get("side") == "buy")
        check("Montant > seuil", alert.get("amount_usd", 0) >= 500_000, f"${alert.get('amount_usd', 0):,.0f}")
    await bus.stop()


async def test_corrupt_tick_resilience():
    print("\n── T5 : Résilience tick corrompu ──")
    bus = StreamBus(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    before_tick_count = bus.snapshot.tick_count
    crashed = False
    try:
        await asyncio.gather(sim.run(duration=4.5, inject_whale_at=99, inject_error_at=0.5))
        await asyncio.sleep(0.1)
    except Exception:
        crashed = True

    check("Bus non planté après tick corrompu", not crashed)
    check("Snapshot toujours peuplé après erreur", len(bus.snapshot.orderbooks) > 0)
    check("tick_count toujours croissant", bus.snapshot.tick_count > before_tick_count, f"{bus.snapshot.tick_count} ticks")
    await bus.stop()


async def test_queue_saturation():
    print("\n── T6 : Saturation de queue ──")
    bus = StreamBus(symbols=["BTC/USDT"], queue_maxsize=10)
    asyncio.create_task(bus.start())
    for i in range(500):
        await bus._enqueue(Tick(symbol="BTC/USDT", timestamp=time.time(), kind="ticker", data={"last": 65_000 + i}))
    await asyncio.sleep(0.3)

    check("Drop count > 0", bus.snapshot.drop_count > 0, f"{bus.snapshot.drop_count} drops")
    check("Bus toujours running", bus._running)
    check("Queue non bloquée", bus._queue.qsize() <= 10)
    check("tick_count > 0", bus.snapshot.tick_count > 0, f"{bus.snapshot.tick_count} ticks traités")
    await bus.stop()


async def test_ml_cycle_non_blocking():
    print("\n── T7 : Cycle ML non-bloquant ──")
    bus = StreamBus(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    ml = FakeMLCycle(bus, cycle_interval=0.2)
    sim = MarketSimulator(bus, tick_rate=0.008)
    asyncio.create_task(bus.start())
    await asyncio.gather(sim.run(duration=2.0, inject_whale_at=1.0, inject_error_at=99), ml.run(duration=2.0))

    check("Cycles ML exécutés", ml.cycles_run >= 5, f"{ml.cycles_run} cycles")
    check("Prix reçus par le ML", len(ml.prices_seen) > 0, f"{len(ml.prices_seen)} snapshots lus")
    check("Imbalances reçues par le ML", len(ml.imbalances_seen) > 0)
    check("Bus tick count élevé", bus.snapshot.tick_count > 50, f"{bus.snapshot.tick_count} ticks pendant que ML tournait")
    check("Drop rate < 5%", bus.snapshot.drop_count / max(bus.snapshot.tick_count, 1) < 0.05, f"{bus.snapshot.drop_count / max(bus.snapshot.tick_count, 1):.1%}")
    await bus.stop()


async def test_multi_symbol():
    print("\n── T8 : Isolation multi-symboles ──")
    bus = StreamBus(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    await asyncio.gather(sim.run(0.5, inject_whale_at=99, inject_error_at=99))
    await asyncio.sleep(0.05)

    btc = bus.snapshot.get_mid_price("BTC/USDT")
    eth = bus.snapshot.get_mid_price("ETH/USDT")
    sol = bus.snapshot.get_mid_price("SOL/USDT")
    check("BTC et ETH ont des prix différents", btc is not None and eth is not None and btc != eth, f"BTC={btc:,.0f} ETH={eth:,.0f}" if btc and eth else "None")
    check("SOL dans la bonne plage", sol is not None and 100 < sol < 250, f"SOL={sol:.2f}" if sol else "None")
    check("3 orderbooks distincts", len(bus.snapshot.orderbooks) == 3)
    await bus.stop()


async def test_stats():
    print("\n── T9 : Stats du bus ──")
    bus = StreamBus(symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    asyncio.create_task(bus.start())
    sim = MarketSimulator(bus, tick_rate=0.005)
    await asyncio.gather(sim.run(0.5, inject_whale_at=99, inject_error_at=99))
    await asyncio.sleep(0.1)

    stats = bus.stats()
    check("tick_count dans stats", stats["tick_count"] > 0, str(stats["tick_count"]))
    check("drop_rate entre 0 et 1", 0 <= stats["drop_rate"] <= 1.0, f"{stats['drop_rate']:.2%}")
    check("last_update_age < 2s", stats["last_update_age"] < 2.0, f"{stats['last_update_age']:.3f}s")
    check("symbols_with_ob == 3", stats["symbols_with_ob"] == 3, str(stats["symbols_with_ob"]))
    await bus.stop()


async def main() -> bool:
    print("=" * 56)
    print("  ANNALISE — StreamBus Test Suite (simulation locale)")
    print("=" * 56)

    await test_snapshot_population()
    await test_mid_price_and_spread()
    await test_orderbook_imbalance()
    await test_whale_detection()
    await test_corrupt_tick_resilience()
    await test_queue_saturation()
    await test_ml_cycle_non_blocking()
    await test_multi_symbol()
    await test_stats()

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    failed = [(name, ok) for name, ok in results if not ok]

    print("\n" + "=" * 56)
    print(f"  Résultat : {passed}/{total} tests passés")
    if failed:
        print("\n  Échecs :")
        for name, _ in failed:
            print(f"    - {name}")
    else:
        print("  Tous les tests sont verts.")
    print("=" * 56)
    return passed == total


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)