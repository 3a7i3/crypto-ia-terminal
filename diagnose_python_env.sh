#!/bin/bash
# diagnose_python_env.sh
# Diagnostic automatique de l'environnement Python et .venv pour crypto_ai_terminal (Linux/Mac)

set -e

echo "[INFO] Diagnostic de l'environnement Python..."

# 1. Vérifier la présence de python dans .venv
if [ -f .venv/bin/python ]; then
  echo "[OK] .venv/bin/python trouvé."
  .venv/bin/python --version
else
  echo "[ERREUR] .venv/bin/python introuvable. Recréez l'environnement avec install_all.sh."
fi

# 2. Vérifier la version de Python globale
python3 --version || python --version

# 3. Vérifier le PATH

echo "[INFO] PATH actuel :"
echo $PATH | tr ':' '\n'

# 4. Vérifier l'activation de .venv
if [ -f .venv/bin/python ]; then
  echo "[INFO] Test import plotly dans .venv..."
  .venv/bin/python -c "import plotly; print('plotly OK')" || echo "[ERREUR] plotly non disponible dans .venv."
else
  echo "[WARN] Impossible de tester plotly sans .venv."
fi

# 5. Conseils
cat <<EOF
[INFO] Si des erreurs persistent :
- Vérifiez que .venv est bien activé (source .venv/bin/activate)
- Vérifiez que python pointe sur .venv (which python)
- Réinstallez les dépendances avec install_all.sh
- Si besoin, redémarrez VS Code ou le terminal.
EOF
