"""
Exemple d'intégration de l'orchestrateur central dans quant-hedge-ai/main_v91.py
"""

import asyncio
import os
import sys

# Ajuster le chemin si besoin
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../orchestrator/core"))
)
from bootstrap import build_orchestrator


def main():
    orchestrator = build_orchestrator()
    try:
        asyncio.run(orchestrator.run_cycle())
    except KeyboardInterrupt:
        orchestrator.stop()
        print("Orchestrateur arrêté.")


if __name__ == "__main__":
    main()
