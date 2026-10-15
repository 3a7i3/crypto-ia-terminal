#!/usr/bin/env bash
# LAB-01 — tests de REFUS sur l'hôte (après installation autorisée). Exige root (sudo).
# Chaque test lance une unité transitoire dans lab01.slice avec les mêmes restrictions que
# lab01-run.service et DOIT être refusé. Ne modifie aucune unité de production.
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "REFUS : root requis"; exit 3; }
PY=/usr/bin/python3.11; FAIL=0
RUN=(systemd-run --quiet --wait --collect --pipe --slice=lab01.slice -p User=lab01 -p Group=lab01
  -p PrivateNetwork=yes -p IPAddressDeny=any -p ProtectSystem=strict -p ProtectHome=yes
  -p InaccessiblePaths="/home /root /opt/crypto-ai-terminal /srv/claude-audit"
  -p ReadWritePaths=/srv/lab01/runs -p NoNewPrivileges=yes -p CapabilityBoundingSet=)
# Un refus n'est reconnu que s'il vient de l'OS : le code Python capture l'erreur d'accès
# (OSError) et sort avec 42. Toute autre issue (outil absent, unité en échec) n'est PAS un refus.
probe() {  # corps python à exécuter ; sort 42 si OSError, 0 sinon
  printf 'import sys\ntry:\n    %s\nexcept OSError:\n    sys.exit(42)\nsys.exit(0)\n' "$1"
}
run_py() { "${RUN[@]}" "$PY" -c "$(probe "$1")" >/dev/null 2>&1; }
expect_denied() {
  run_py "$2"; local rc=$?
  if [ "$rc" -eq 42 ]; then echo "OK  $1 : refusé par l'OS"
  elif [ "$rc" -eq 0 ]; then echo "KO  $1 : AUTORISÉ (attendu : refusé)"; FAIL=1
  else echo "KO  $1 : indéterminé (code $rc)"; FAIL=1; fi
}
expect_allowed() {
  run_py "$2"; local rc=$?
  if [ "$rc" -eq 0 ]; then echo "OK  $1 : autorisé"
  else echo "KO  $1 : refusé ou indéterminé (code $rc)"; FAIL=1; fi
}
# Contrôle : si l'unité transitoire ne s'exécute pas, aucun refus ci-dessous n'est interprétable.
run_py 'pass' || { echo "ABANDON : contrôle d'exécution échoué (systemd-run / lab01 / slice)"; exit 5; }
echo "OK  contrôle : le processus s'exécute dans lab01.slice"
expect_denied  "réseau sortant"            'import socket; socket.create_connection(("1.1.1.1", 53), 2)'
expect_denied  "résolution DNS"            'import socket; socket.getaddrinfo("example.com", 443)'
expect_denied  "lecture /home/mathieu"     'import os; os.listdir("/home/mathieu")'
expect_denied  "lecture arbre production"  'import os; os.listdir("/opt/crypto-ai-terminal")'
expect_denied  "écriture /etc"             'open("/etc/lab01_probe", "w")'
expect_denied  "écriture hors runs"        'open("/srv/lab01/release/probe", "w")'
expect_denied  "montée de privilèges"      'import os; os.setuid(0)'
expect_allowed "écriture sous runs"        'open("/srv/lab01/runs/.probe", "w").close()'
rm -f /srv/lab01/runs/.probe
echo "--- unités de production inchangées : relever avant/après avec :"
echo "    systemctl show crypto-advisor.service -p MainPID -p ActiveEnterTimestamp"
exit $FAIL
