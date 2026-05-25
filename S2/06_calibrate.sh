#!/usr/bin/env bash
# S2/06_calibrate.sh — Lance les 4 rapports de calibration S2 d'un coup.
#
# Usage:
#   bash S2/06_calibrate.sh
#   bash S2/06_calibrate.sh --tail 200   # gate_logger: 200 derniers événements
#
# Sortie: 4 rapports dans le terminal + résumé dans S2/calibration_report.txt

set -e
cd "$(dirname "$0")/.."  # se placer à la racine du projet

TAIL_FLAG=${1:-""}
REPORT_FILE="S2/calibration_report.txt"
PYTHON=${PYTHON:-python}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         CALIBRATION S2 — $(date '+%Y-%m-%d %H:%M')                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "" | tee "$REPORT_FILE"

run_script() {
    local label="$1"
    local script="$2"
    shift 2
    echo "──────────────────────────────────────────────────────────"
    echo "  $label"
    echo "──────────────────────────────────────────────────────────"
    $PYTHON "$script" "$@" 2>&1 | tee -a "$REPORT_FILE"
    echo ""
}

run_script "① GATE LOGGER — Analyse des rejets" \
    S2/01_gate_logger.py ${TAIL_FLAG:+--tail "$TAIL_FLAG"}

run_script "② SCORE DISTRIBUTION — Seuil optimal" \
    S2/02_score_distribution.py

run_script "③ SELF-AWARENESS CALIBRATOR — Seuils DANGER/FREEZE" \
    S2/03_self_awareness_calibrator.py

run_script "④ CONVICTION CALIBRATOR — Tailles de position" \
    S2/04_conviction_calibrator.py

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Rapport complet sauvegardé dans: $REPORT_FILE"
echo "║"
echo "║  Prochaines étapes:"
echo "║    1. Vérifier les recommandations .env ci-dessus"
echo "║    2. Appliquer les seuils dans .env + redémarrer le bot"
echo "║    3. Initialiser le tracker: python S2/05_paper_tracker.py --init --day 1"
echo "║    4. Chaque jour: python S2/05_paper_tracker.py --auto --day N"
echo "║    5. Rapport: python S2/05_paper_tracker.py --report"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
