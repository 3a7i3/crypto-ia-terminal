#!/usr/bin/env python3
"""
Phase 9 Audit Test — Trade replay with full decision trace
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.config.settings import TRADES_LOG_FILE
from audit.trade_audit import audit_all_trades
from audit.replay_engine import ReplayEngine
from audit.decision_trace import DecisionTraceLog


def test_phase9_audit():
    print("\n" + "=" * 70)
    print("PHASE 9 — AUDIT ENGINE TEST")
    print("=" * 70)

    print("\n[STEP 1] Audit all trades")
    audits = audit_all_trades(TRADES_LOG_FILE)
    print(f"Audits created: {len(audits)}")

    if not audits:
        print("No trades to audit")
        return

    print("\n[STEP 2] Show detailed analysis for first trade")
    first_audit = audits[0]
    print(first_audit.generate_narrative())

    print("\n[STEP 3] Quality breakdown")
    qualities = {}
    for audit in audits:
        quality = audit.get_quality_label()
        qualities[quality] = qualities.get(quality, 0) + 1

    for quality, count in qualities.items():
        pct = count / len(audits) * 100
        print(f"  {quality}: {count} ({pct:.1f}%)")

    print("\n[STEP 4] Replay trades with trace")
    replay_engine = ReplayEngine(audits)
    replays = replay_engine.replay_all()
    print(f"Replays: {len(replays)}")

    if replays:
        first_replay = replays[0]
        print(f"\nFirst replay trace ({first_replay['symbol']}):")
        print(f"  Regime: {first_replay['regime']}")
        print(f"  Entry: {first_replay['entry_price']:.8f}")
        print(f"  Total ticks: {first_replay['total_ticks']}")
        for tick in first_replay['trace'][-3:]:
            print(f"    Tick {tick['tick']}: price={tick['price']:.8f}, exit={tick['exit_triggered']}")

    print("\n[STEP 5] Alternative exits analysis")
    if audits:
        first_audit = audits[0]
        replay = first_audit.__class__(first_audit.entry, first_audit.exit)
        alternatives = replay.get_alternative_exits() if hasattr(replay, 'get_alternative_exits') else []

        from audit.replay_engine import TradeReplay
        trade_replay = TradeReplay(first_audit.entry, first_audit.exit)
        alternatives = trade_replay.get_alternative_exits()

        if alternatives:
            print("\nTop 3 alternative exits:")
            for alt in alternatives[:3]:
                print(f"  TP={alt['tp']:.4f} SL={alt['sl']:.4f}: pnl={alt['pnl_pct']:+.2%}")

    print("\n[STEP 6] Decision quality report")
    quality_report = replay_engine.get_decision_quality_report()
    print(f"Total trades: {quality_report['total_trades']}")
    print(f"Skilled ratio: {quality_report['skilled_ratio']:.1%}")
    print(f"Quality breakdown:")
    for quality, ratio in quality_report['breakdown'].items():
        print(f"  {quality}: {ratio}")

    print("\n[STEP 7] Log decision traces")
    trace_log = DecisionTraceLog()
    print(f"Decision trace log: {trace_log.log_file}")

    print("\n[OK] Phase 9 test complet!")


if __name__ == "__main__":
    test_phase9_audit()
