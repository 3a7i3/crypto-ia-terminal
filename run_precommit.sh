#!/bin/bash
# Script bash pour lancer pre-commit sur tout le code (Linux/Mac)
# Usage : ./run_precommit.sh

VENV_PATH=".venv/bin"
PRECOMMIT_EXE="$VENV_PATH/pre-commit"

if [ ! -x "$PRECOMMIT_EXE" ]; then
  echo "pre-commit non trouvé dans .venv. Installez-le avec 'pip install pre-commit' dans le venv."
  exit 1
fi

echo "Activation de l'environnement virtuel et exécution de pre-commit..."
$PRECOMMIT_EXE run --all-files

if [ $? -eq 0 ]; then
  echo "Tous les hooks pre-commit sont passés avec succès."
else
  echo "Des erreurs ont été détectées par pre-commit. Corrigez-les puis relancez le script."
  exit 1
fi
