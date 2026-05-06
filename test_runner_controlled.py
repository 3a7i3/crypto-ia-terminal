#!/usr/bin/env python3
"""
Test runner contrôlé — MODE TEST OBLIGATOIRE
Avant de passer en live, validate le système en mode test serré:
- BTCUSDT uniquement
- 10s cycle interval (génère beaucoup de cycles rapidement)
- 50$ par trade
- Run 30-60 min
- Observe: boucle trading, SL handling, dedup, dashboard, drawdown
"""

import os
import sys
import time
import subprocess

def main():
    # ── Configuration test STRICTE ─────────────────────────────────────────────
    env = os.environ.copy()

    # Mode test
    env["FORCE_TEST"] = "true"
    env["V9_ADVISOR_ONLY"] = "false"  # ← Active vraie exécution

    # Symbole + sizing test
    env["TEST_SYMBOLS"] = "BTCUSDT"
    env["EXEC_MAX_ORDER_USD"] = "50"
    env["V9_MAX_POSITION_WEIGHT"] = "0.05"

    # Cycle rapide (10s)
    env["ADVISOR_CYCLE_INTERVAL"] = "10"

    # Logging verbeux
    env["V9_LOG_LEVEL"] = "DEBUG"

    # Dashboard actif
    env["ADVISOR_BACKGROUND_POSITION_WATCH"] = "true"

    # Anti-overtrading
    env["ADVISOR_1H_LIMIT"] = "20"  # moins de bougies pour accélérer

    print("""
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                    MODE TEST CONTRÔLÉ — VALIDATION RÉELLE                  ║
    ╚════════════════════════════════════════════════════════════════════════════╝

    Configuration:
    ✓ Symbole: BTCUSDT
    ✓ Cycle: 10s (génère 360 cycles/heure)
    ✓ Taille: $50 par trade
    ✓ Durée recommandée: 30-60 minutes
    ✓ Exécution réelle: ACTIVÉE
    ✓ Protections: cooldown(5min), re-entry block, max 10 trades/heure

    OBSERVATIONS CRITIQUES à faire pendant 30-60 min:
    ════════════════════════════════════════════════════════════════

    A) BOUCLE DE TRADING — est-ce que ça spam ?
       Chercher dans logs: BUY → SELL → BUY → SELL rapide
       ❌ MAUVAIS: repeats rapides = overtrading loop
       ✓ BON: 2-3 trades par 10 min max

    B) GESTION DES PERTES — SL → immédiate réouverture ?
       Chercher: "[SL TRIGGERED]" + signal immédiatement après
       ❌ MAUVAIS: SL hit → BUY signal immédiat
       ✓ BON: cooldown 5 min après SL

    C) DRAWDOWN RÉEL — logique du guard ?
       Chercher: guard.state() dans les logs
       ✓ BON: drawdown progresse, blocage si seuil atteint

    D) DASHBOARD COHÉRENCE — positions disparaissent après fermeture ?
       Vérifier: positions ouvertes → fermeture → absent du dashboard
       ❌ MAUVAIS: position reste visible après fermeture
       ✓ BON: Position immédiatement supprimée

    E) PnL LOGIQUE — pas NaN, pas constant à 0 ?
       ✓ BON: PnL réaliste (±0.5% à ±2% par trade)

    RAPPORT À DONNER APRÈS 30-60 MIN:
    ════════════════════════════════════════════════════════════════
    - Nombre total de trades lancés
    - Nombre de SL déclenchés
    - Nombre de TP atteints
    - Drawdown maximal observé
    - Comportement suspect (si oui → lequel)
    - Taux de réouverture après SL

    LANCEMENT — ctrl+c pour arrêter proprement:
    ════════════════════════════════════════════════════════════════
    """)

    input("Appuyer sur ENTER pour démarrer le test...")

    # Lancer advisor_loop avec le symbole test
    cmd = [
        sys.executable,
        "advisor_loop.py",
        "--interval", "10",
        "--symbols", "BTC/USDT",
        "--max-cycles", "360",  # 3600s = 1 heure
    ]

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n\n[TEST ARRÊTE] Ctrl+C reçu")
        print("\nFermeture propre du système...")

    print("""
    ════════════════════════════════════════════════════════════════
    Test terminé. Vérifier:
    - logs/advisor_loop.log
    - databases/positions_snapshot.json
    - dashboard (si actif)
    ════════════════════════════════════════════════════════════════
    """)

if __name__ == "__main__":
    main()
