"""
trade_analysis/lmi_engine.py — Moteur Live Market Interaction (LMI).

Orchestrateur principal qui combine les 4 dimensions d'observation :
  1. FlowAnalyzer      — flux d'ordres agressifs
  2. LiquidityTracker  — dynamique de liquidite du book
  3. ResistanceMeter   — resistance / fragilite du marche
  4. classify_state    — classification en etat structurel

Produit un PressureField a chaque intervalle configurable.

Modes d'utilisation :
  - Live : via stream WebSocket (MultiExchangeStream)
  - Replay : via fichiers JSONL (ReplayEngine)
  - Snapshot : via REST (fetch_all)

Strictement passif (ADR-0007) — aucune influence sur les decisions.
"""

from __future__ import annotations

from typing import AsyncGenerator, Callable, Iterator, Optional

from market_data.models import (
    MarketEvent,
    NormalizedOrderBook,
    NormalizedTrade,
)
from trade_analysis.flow_analyzer import FlowAnalyzer
from trade_analysis.liquidity_tracker import LiquidityTracker
from trade_analysis.market_state import classify_state
from trade_analysis.models import (
    AggressiveFlow,
    LiquidityDynamics,
    MarketResistance,
    MarketStateLabel,
    PressureField,
)
from trade_analysis.recorder import LMIRecorder
from trade_analysis.resistance_meter import ResistanceMeter


class LMIEngine:
    """
    Moteur d'observation Live Market Interaction.

    Consomme des MarketEvent (trades + orderbook) et produit
    des PressureField decrivant l'etat du marche.

    Usage live :
        engine = LMIEngine(symbol="BTCUSDT")
        stream = MultiExchangeStream()
        async for pf in engine.run_live(stream):
            print(pf.state, pf.flow.pressure_ratio)

    Usage synchrone :
        engine = LMIEngine(symbol="BTCUSDT")
        for event in events:
            pf = engine.process_event(event)
            if pf:
                print(pf.state)
    """

    def __init__(
        self,
        symbol: str = "",
        flow_window_ms: int = 10_000,
        resistance_window_ms: int = 10_000,
        large_order_usd: float = 50_000.0,
        snapshot_interval_ms: int = 2_000,
        book_levels: int = 20,
        record: bool = False,
        record_dir: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.snapshot_interval_ms = snapshot_interval_ms

        self._flow = FlowAnalyzer(
            window_ms=flow_window_ms,
            large_order_usd=large_order_usd,
            snapshot_interval_ms=snapshot_interval_ms,
        )
        self._liquidity = LiquidityTracker(levels=book_levels)
        self._resistance = ResistanceMeter(
            window_ms=resistance_window_ms,
            snapshot_interval_ms=snapshot_interval_ms,
        )

        self._last_flow: Optional[AggressiveFlow] = None
        self._last_liquidity: Optional[LiquidityDynamics] = None
        self._last_resistance: Optional[MarketResistance] = None
        self._reference_price: Optional[float] = None
        self._current_price: Optional[float] = None

        self._recorder: Optional[LMIRecorder] = None
        if record:
            self._recorder = LMIRecorder(output_dir=record_dir)

        self._on_field: list[Callable[[PressureField], None]] = []
        self._event_count: int = 0

    def on_field(self, callback: Callable[[PressureField], None]) -> None:
        self._on_field.append(callback)

    def process_event(self, event: MarketEvent) -> Optional[PressureField]:
        self._event_count += 1

        if event.event_type == "trade":
            return self._on_trade(event.data)
        elif event.event_type == "orderbook":
            self._on_book(event.data)
        return None

    def _on_trade(self, trade: NormalizedTrade) -> Optional[PressureField]:
        self._current_price = trade.price
        if self._reference_price is None:
            self._reference_price = trade.price

        self._liquidity.on_trade(trade)

        flow = self._flow.update(trade)
        if flow:
            self._last_flow = flow

        resistance = self._resistance.update(trade)
        if resistance:
            self._last_resistance = resistance

        # Les trades seuls (flow + resistance) suffisent a emettre un champ :
        # la liquidite (orderbook) est un enrichissement optionnel. Sinon
        # l'observatoire ne produirait rien tant que le book n'a pas parle.
        if flow and self._last_resistance:
            return self._build_field(trade.timestamp_ms, trade.symbol)
        return None

    def _on_book(self, book: NormalizedOrderBook) -> None:
        dynamics = self._liquidity.on_book(book)
        if dynamics:
            self._last_liquidity = dynamics

    def _build_field(self, ts: int, symbol: str) -> PressureField:
        price = self._current_price or 0.0
        ref = self._reference_price or price
        price_change = (price - ref) / ref * 10_000.0 if ref > 0 else 0.0

        flow = self._last_flow
        liq = self._last_liquidity or LiquidityDynamics(
            timestamp_ms=ts,
            bid_added_usd=0.0, bid_removed_usd=0.0,
            ask_added_usd=0.0, ask_removed_usd=0.0,
            bid_consumed_usd=0.0, ask_consumed_usd=0.0,
            cancellation_rate_bid=0.0, cancellation_rate_ask=0.0,
            net_liquidity_change_usd=0.0,
        )
        res = self._last_resistance

        state, confidence, components = classify_state(
            flow, liq, res, price_change
        )

        pf = PressureField(
            timestamp_ms=ts,
            symbol=symbol or self.symbol,
            price=price,
            price_change_bps=price_change,
            flow=flow,
            liquidity=liq,
            resistance=res,
            state=state,
            state_confidence=confidence,
            state_components=components,
        )

        for cb in self._on_field:
            cb(pf)

        if self._recorder:
            self._recorder.record(pf)

        self._reference_price = price
        return pf

    # ------------------------------------------------------------------
    # Live streaming
    # ------------------------------------------------------------------

    async def run_live(
        self,
        stream,
        event_types: Optional[list[str]] = None,
    ) -> AsyncGenerator[PressureField, None]:
        """
        Consomme un MultiExchangeStream et yield des PressureField.
        """
        types = event_types or ["trade", "orderbook"]
        async for event in stream.stream_live(self.symbol, types):
            pf = self.process_event(event)
            if pf:
                yield pf

    # ------------------------------------------------------------------
    # Replay synchrone
    # ------------------------------------------------------------------

    def replay_events(
        self,
        events: Iterator[MarketEvent],
    ) -> Iterator[PressureField]:
        for event in events:
            pf = self.process_event(event)
            if pf:
                yield pf

    # ------------------------------------------------------------------
    # Stats & lifecycle
    # ------------------------------------------------------------------

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def last_state(self) -> Optional[MarketStateLabel]:
        if self._last_flow is None:
            return None
        if self._last_liquidity and self._last_resistance:
            price = self._current_price or 0.0
            ref = self._reference_price or price
            pc = (price - ref) / ref * 10_000.0 if ref > 0 else 0.0
            s, _, _ = classify_state(
                self._last_flow, self._last_liquidity, self._last_resistance, pc
            )
            return s
        return None

    def close(self) -> None:
        if self._recorder:
            self._recorder.close()

    def __enter__(self) -> "LMIEngine":
        return self

    def __exit__(self, *args) -> None:
        self.close()
