#!/usr/bin/env python3
"""
Observer — surveille logs en temps réel pendant le test
Cherche patterns critiques: SL, trade spam, dedup issues, cooldown
"""

import time
import subprocess
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def monitor_logs(log_file: str = "logs/advisor_loop.log", check_interval: float = 1.0):
    """Tail logs + pattern detection."""
    log_path = Path(log_file)

    if not log_path.exists():
        print(f"Log file not found: {log_file}")
        print("Starting test first...")
        return

    stats = defaultdict(int)
    last_trades = {}  # {symbol: (timestamp, signal)}
    last_pos_close = {}  # {symbol: timestamp}

    print("""
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                        OBSERVER — LOG MONITORING                           ║
    ║                   Press Ctrl+C to stop monitoring                          ║
    ╚════════════════════════════════════════════════════════════════════════════╝
    """)

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
                    print(f"  ⚠ SL TRIGGERED")

                # TP reached
                elif "tp_pct" in line.lower() and "POSITION" in line:
                    stats["tp_reached"] += 1
                    print(f"  ✓ TP REACHED")

                # Position closed
                elif "POSITION FERMEE" in line or "FERMEE" in line:
                    stats["positions_closed"] += 1
                    print(f"  ✗ POSITION CLOSED")

                # Protections blocking
                elif "[PROTECTION]" in line and "BLOQUE" in line:
                    if "cooldown" in line:
                        stats["block_cooldown"] += 1
                        print(f"  🔒 COOLDOWN BLOCK")
                    elif "same_direction" in line:
                        stats["block_reentry"] += 1
                        print(f"  🔒 RE-ENTRY BLOCK")
                    elif "max_trades" in line:
                        stats["block_max_trades"] += 1
                        print(f"  🔒 MAX TRADES BLOCK")

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

                # Print every 20 seconds summary
                if sum(stats.values()) % 100 == 0:
                    elapsed = datetime.now().strftime("%H:%M:%S")
                    print(f"\n[{elapsed}] STATS:")
                    print(f"  Trades: BUY={stats['trades_buy']} SELL={stats['trades_sell']}")
                    print(f"  Exits: TP={stats['tp_reached']} SL={stats['sl_triggered']}")
                    print(f"  Closed: {stats['positions_closed']}")
                    print(f"  Blocks: Cooldown={stats['block_cooldown']} ReEntry={stats['block_reentry']} MaxTrades={stats['block_max_trades']}")
                    print(f"  Errors: {stats['errors']}\n")

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        print("\nFinal stats:")
        for key, val in sorted(stats.items()):
            print(f"  {key}: {val}")

if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else "logs/advisor_loop.log"
    monitor_logs(log_file)
