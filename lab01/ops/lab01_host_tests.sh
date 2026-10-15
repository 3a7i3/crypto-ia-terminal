#!/usr/bin/env bash
# LAB-01 — tests d'isolation EFFECTIVE sur l'hôte (après installation autorisée). Exige root.
# Lanceur fin : toute la logique est dans host_isolation_tests.py (propriétés relues des fichiers
# d'unité prévus, sondes dans le processus, essais témoins). Aucun paramètre par variable d'environnement.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "REFUS : root requis"; exit 3; }
exec /usr/bin/python3.11 -I "$HERE/host_isolation_tests.py" --unit-dir "$HERE/systemd" "$@"
