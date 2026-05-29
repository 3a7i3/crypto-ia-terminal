#!/usr/bin/env python3
"""
Observer — surveille logs en temps réel pendant le test
Cherche patterns critiques: SL, trade spam, dedup issues, cooldown
"""

import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def monitor_logs(log_file: str = "logs/advisor_loop.log", check_interval: float = 1.0):
    """Tail logs + pattern detection."""
    log_path = Path(log_file)

    if not log_path.exists():
        print(f"Log file not found: {log_file}")
        print("Starting test first...")
        return

    stats = defaultdict(int)
    last_trades = {}  # {symbol: (timestamp, signal)}

    print(
        """
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                        OBSERVER — LOG MONITORING                           ║
    ║                   Press Ctrl+C to stop monitoring                          ║
    ╚════════════════════════════════════════════════════════════════════════════╝
    """
    )

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # Fast-forward to end
            f.seek(0, 2)
            print(f"Tailing {log_file}...\n")

            while True:
                line = f.readline()
                if not line:
                    time.sleep(check_interval)
                    continue

                # ── EXTRACTION PATTERNS ─────────────────────────────────────────
                # Signals
                if "[LSE]" in line and "score=" in line:
                    import re

                    match = re.search(r"score=(\d+)\s+signal=(\w+)", line)
                    if match:
                        score, signal = match.group(1), match.group(2)
                        stats[f"signal_{signal}"] = stats.get(f"signal_{signal}", 0) + 1
                        if signal != "HOLD":
                            print(f"  📊 SIGNAL: {signal} score={score}")

                # Gate decisions
                if "[FLOW]" in line and "GATE" in line:
                    if "OK" in line:
                        stats["gate_allowed"] += 1
                        print("  ✓ GATE ALLOWED")
                    elif "BLOQUE" in line:
                        stats["gate_blocked"] += 1

                # Trade execution
                if "[EXECUTION]" in line or "[FUTURES DEMO]" in line:
                    if "BUY" in line:
                        sym = line.split()[-4] if len(line.split()) > 4 else "?"
                        last_trades[sym] = (time.time(), "BUY")
                        stats["trades_buy"] += 1
                        print(f"  ✓ BUY {sym}")
                    elif "SELL" in line:
                        sym = line.split()[-4] if len(line.split()) > 4 else "?"
                        last_trades[sym] = (time.time(), "SELL")
                        stats["trades_sell"] += 1
                        print(f"  ✓ SELL {sym}")

                # SL triggered
                elif "TP/SL" in line or "sl_pct" in line.lower():
                    stats["sl_triggered"] += 1
                    print("  ⚠ SL TRIGGERED")

                # TP reached
                elif "tp_pct" in line.lower() and "POSITION" in line:
                    stats["tp_reached"] += 1
                    print("  ✓ TP REACHED")

                # Position closed
                elif "POSITION FERMEE" in line or "FERMEE" in line:
                    stats["positions_closed"] += 1
                    print("  ✗ POSITION CLOSED")

                # Protections blocking
                elif "[PROTECTION]" in line and "BLOQUE" in line:
                    if "cooldown" in line:
                        stats["block_cooldown"] += 1
                        print("  🔒 COOLDOWN BLOCK")
                    elif "same_direction" in line:
                        stats["block_reentry"] += 1
                        print("  🔒 RE-ENTRY BLOCK")
                    elif "max_trades" in line:
                        stats["block_max_trades"] += 1
                        print("  🔒 MAX TRADES BLOCK")

                # Gate override
                elif "[GATE_OVERRIDE]" in line:
                    stats["gate_overrides"] += 1
                    print("  ⚡ GATE OVERRIDE (test mode)")

                # Dedup checks
                elif "dedup" in line.lower():
                    stats["dedup_checks"] += 1

                # Drawdown update
                elif "drawdown" in line.lower() and "guard" in line.lower():
                    stats["drawdown_updates"] += 1

                # Errors
                elif "ERROR" in line or "FAILED" in line:
                    stats["errors"] += 1
                    print(f"  ❌ ERROR: {line.strip()[:80]}")

                # Print every 50 updates summary
                if sum(stats.values()) % 50 == 0:
                    elapsed = datetime.now().strftime("%H:%M:%S")
                    print(f"\n[{elapsed}] SUMMARY:")
                    print(
                        f"  Signals: BUY={stats.get('signal_BUY', 0)} SELL={stats.get('signal_SELL', 0)} HOLD={stats.get('signal_HOLD', 0)}"
                    )
                    print(
                        f"  Gate: Allowed={stats.get('gate_allowed', 0)} Blocked={stats.get('gate_blocked', 0)} Overrides={stats.get('gate_overrides', 0)}"
                    )
                    print(
                        f"  Trades: BUY={stats['trades_buy']} SELL={stats['trades_sell']}"
                    )
                    print(
                        f"  Exits: TP={stats['tp_reached']} SL={stats['sl_triggered']}"
                    )
                    print(f"  Closed: {stats['positions_closed']}")
                    print(
                        f"  Blocks: Cooldown={stats['block_cooldown']} ReEntry={stats['block_reentry']} MaxTrades={stats['block_max_trades']}"
                    )
                    print(f"  Errors: {stats['errors']}\n")

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        print("\nFinal stats:")
        for key, val in sorted(stats.items()):
            print(f"  {key}: {val}")


if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else "logs/advisor_loop.log"
    monitor_logs(log_file)
