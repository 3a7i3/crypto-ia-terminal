#!/usr/bin/env python3
"""
Phase 1 Tracker Test — Validation minimale
entry → update → exit → logs propres
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.core.trade_tracker import (
    open_position,
    update_positions,
    finalize_position,
)
from tracker_system.storage.loader import load_jsonl


def test_phase1_basic():
    log_file = Path("logs/trades.jsonl")
    state_file = Path("logs/open_positions.json")

    # ÉTAPE 1: Open Position
    print("\n[STEP 1] Open Position")
    pos = open_position(
        symbol="BTCUSDT",
        side="BUY",
        price=100.0,
        size=1.0,
        regime="bull_trend",
        confidence=0.85,
        log_file=log_file,
        state_file=state_file,
    )
    print(f"Position ouverte: {pos['id']}")
    time.sleep(0.1)

    # ÉTAPE 2: Update Positions avec prix moyen
    print("\n[STEP 2] Update Positions")
    current_prices = {"BTCUSDT": 102.0}  # +2% profit
    closed = update_positions(
        current_prices=current_prices,
        exit_engine=None,
        state_file=state_file,
        log_file=log_file,
    )
    print(f"Closed positions: {len(closed)}")
    time.sleep(0.1)

    # ÉTAPE 3: Finalize position manuellement pour testing
    print("\n[STEP 3] Finalize Position")
    if not closed:
        final = finalize_position(
            position_id=pos["id"],
            price=105.0,
            exit_reason="TEST_EXIT",
            state_file=state_file,
            log_file=log_file,
        )
        if final:
            print(f"Position close: pnl_pct={final.get('pnl_pct'):.4f}")

    # ÉTAPE 4: Vérifier logs JSONL
    print("\n[STEP 4] Verifier Logs JSONL")
    events = load_jsonl(log_file)
    print(f"Total events: {len(events)}")
    for i, event in enumerate(events[-2:]):  # derniers 2 events
        print(f"\nEvent {i+1}:")
        print(f"  type: {event.get('type')}")
        print(f"  symbol: {event.get('symbol')}")
        if event.get("type") == "entry":
            print(f"  entry_price: {event.get('entry_price')}")
            print(f"  size: {event.get('size')}")
        elif event.get("type") == "exit":
            print(f"  exit_price: {event.get('exit_price')}")
            print(f"  pnl_pct: {event.get('pnl_pct'):.4f}")
            print(f"  pnl_usd: {event.get('pnl_usd'):.4f}")
            print(f"  win: {event.get('win')}")

    print("\n[OK] Phase 1 test complet!\n")


if __name__ == "__main__":
    test_phase1_basic()
