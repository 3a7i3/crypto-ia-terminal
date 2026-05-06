#!/usr/bin/env python3
"""
TEST AUDIT PHASE 9 — Analyse des trades en français
Montre: qualité, rejeu, alternatives, traçage
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
    print("PHASE 9 — AUDIT ENGINE (EN FRANCAIS)")
    print("=" * 70)

    print("\n[ETAPE 1] Charger et auditer les trades")
    audits = audit_all_trades(TRADES_LOG_FILE)
    print(f"Trades auditees: {len(audits)}")

    if not audits:
        print("Aucun trade a auditer")
        return

    print("\n[ETAPE 2] Analyse detaillee du premier trade")
    first_audit = audits[0]
    print(first_audit.generate_narrative())

    print("\n[ETAPE 3] Repartition de qualite")
    qualities = {}
    for audit in audits:
        quality = audit.get_quality_label()
        qualities[quality] = qualities.get(quality, 0) + 1

    for quality, count in qualities.items():
        pct = count / len(audits) * 100
        print(f"  {quality}: {count} ({pct:.1f}%)")

    print("\n[ETAPE 4] Rejeu des trades avec trace")
    replay_engine = ReplayEngine(audits)
    replays = replay_engine.replay_all()
    print(f"Rejeus: {len(replays)}")

    if replays:
        first_replay = replays[0]
        print(f"\nTrace du premier rejeu ({first_replay['symbol']}):")
        print(f"  Regime: {first_replay['regime']}")
        print(f"  Entree: {first_replay['entry_price']:.8f}")
        print(f"  Total ticks: {first_replay['total_ticks']}")
        for tick in first_replay['trace'][-3:]:
            print(f"    Tick {tick['tick']}: prix={tick['price']:.8f}, exit={tick['exit_triggered']}")

    print("\n[ETAPE 5] Analyse d'alternatives d'exit")
    if audits:
        first_audit = audits[0]
        from audit.replay_engine import TradeReplay
        trade_replay = TradeReplay(first_audit.entry, first_audit.exit)
        alternatives = trade_replay.get_alternative_exits()

        if alternatives:
            print("\n3 meilleures alternatives d'exit:")
            for alt in alternatives[:3]:
                print(f"  TP={alt['tp']:.4f} SL={alt['sl']:.4f}: pnl={alt['pnl_pct']:+.2%}")

    print("\n[ETAPE 6] Rapport de qualite des decisions")
    quality_report = replay_engine.get_decision_quality_report()
    print(f"Total trades: {quality_report['total_trades']}")
    print(f"Ratio skilled: {quality_report['skilled_ratio']:.1%}")
    print(f"Repartition qualite:")
    for quality, ratio in quality_report['breakdown'].items():
        print(f"  {quality}: {ratio}")

    print("\n[ETAPE 7] Tracer les decisions")
    trace_log = DecisionTraceLog()
    print(f"Fichier decision trace: {trace_log.log_file}")

    print("\n" + "=" * 70)
    print("RESUME DE L'AUDIT")
    print("=" * 70)

    print("\nCe qu'on apprend:")
    print(f"  - {len(audits)} trades analysees")
    print(f"  - Qualite moyenne: voir repartition ci-dessus")
    print(f"  - Meilleure alternative: voir etape 5")
    print(f"  - Decision quality: {quality_report['skilled_ratio']:.1%} skilled")

    print("\nLabels de qualite:")
    print("  SKILLED = Bien exécuté, sorti au bon moment")
    print("  LUCKY = Chance (attrapé un pic)")
    print("  MISTAKE = Erreur recuperée")
    print("  UNLUCKY = Malchance (mauvais timing)")

    print("\nProchaine etape:")
    print("  Analyser les trades MISTAKE pour améliorer la stratégie")

    print("\n[OK] Test Phase 9 complet!\n")


if __name__ == "__main__":
    test_phase9_audit()
