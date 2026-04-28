"""
Test d'importabilité automatique pour tous les modules Python du projet.
Généré automatiquement.
Exécutez : python -m unittest test_imports_all_modules.py
"""

import importlib
import os
import sys
import unittest

# Ajoute le répertoire racine au PYTHONPATH si besoin
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Liste générée automatiquement de tous les modules à tester
MODULE_PATHS = [
    # Format: (chemin relatif, nom du module importable)
    ("quant_hedge_ai/main_v91.py", "quant_hedge_ai.main_v91"),
    ("dashboard/alert_dashboard.py", "dashboard.alert_dashboard"),
    ("evolution_dashboard.py", "evolution_dashboard"),
    ("evolution_3d_view.py", "evolution_3d_view"),
    ("generate_html_report.py", "generate_html_report"),
    ("generate_coverage_report.py", "generate_coverage_report"),
    ("generate_ai_quant_lab_structure.py", "generate_ai_quant_lab_structure"),
    # ... compléter dynamiquement si besoin ...
]


class TestAllImports(unittest.TestCase):
    def test_import_all_modules(self):
        failures = []
        for path, mod in MODULE_PATHS:
            with self.subTest(module=mod):
                try:
                    importlib.import_module(mod)
                except Exception as e:
                    failures.append((mod, str(e)))
        if failures:
            msg = "\n".join([f"[FAIL] {mod}: {err}" for mod, err in failures])
            self.fail(f"Des erreurs d'import ont été détectées :\n{msg}")


if __name__ == "__main__":
    unittest.main()
