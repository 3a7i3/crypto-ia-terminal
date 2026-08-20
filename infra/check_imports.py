"""
Script de vérification d'importabilité pour tous les modules principaux du projet.
Exécutez : python check_imports.py
"""

import importlib
import sys

# Liste des modules principaux à tester (à compléter dynamiquement ensuite)
MODULES = [
    "quant_hedge_ai.main_v91",
    "quant_hedge_ai.dashboard.director_dashboard",
    "quant_hedge_ai.strategy_factory.factory_core",
    "quant_hedge_ai.liquidity_map.flow_analyzer",
    "quant_hedge_ai.market_radar.radar_core",
    "quant_hedge_ai.runtime_config",
    # ... ajoutez d'autres modules ici ...
]

failures = []
for mod in MODULES:
    try:
        importlib.import_module(mod)
        print(f"[OK] {mod}")
    except Exception as e:
        print(f"[FAIL] {mod} : {e}")
        failures.append((mod, str(e)))

if failures:
    print("\n--- Résumé des échecs d'import ---")
    for mod, err in failures:
        print(f"{mod} : {err}")
    sys.exit(1)
else:
    print("\nTous les modules principaux sont importables !")
