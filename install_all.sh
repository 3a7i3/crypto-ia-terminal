#!/bin/bash
# install_all.sh - Installation automatique et robuste de l'environnement Python pour crypto_ai_terminal (Linux/Mac)

set -e

if [ -d ".venv" ]; then
  echo "[INFO] Suppression de l'ancien environnement .venv..."
  rm -rf .venv
fi

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

if [ -f "crypto_quant_v16/requirements.txt" ]; then
  pip install -r crypto_quant_v16/requirements.txt
fi
if [ -f "quant-ai-system/requirements.txt" ]; then
  pip install -r quant-ai-system/requirements.txt
fi
if [ -f "quant-hedge-ai/requirements.txt" ]; then
  pip install -r quant-hedge-ai/requirements.txt
fi

pip install plotly

echo "[INFO] Installation terminée. Vous pouvez lancer :"
echo "    source .venv/bin/activate"
echo "    python run_all_tests.py"
