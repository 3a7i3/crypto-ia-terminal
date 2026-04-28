import importlib

import pytest

PANEL_MODULES = [
    ("dashboard.alert_dashboard", "Supervision & Auto-Heal"),
    ("supervision.botdoctor_dashboard", "BotDoctor Dashboard"),
    ("evolution_dashboard", "Evolution Multi-Monde"),
    ("evolution_3d_view", "3D Evolution Viewer"),
    ("crypto_quant_v16.ui.quant_dashboard", "Quant V16 Panel"),
    ("quant_hedge_ai.dashboard.quant_terminal_v12", "Quant Terminal V12"),
    ("ai_autonomous_loop.feedback_dashboard", "Feedback Dashboard"),
]


def test_panel_import_and_tutorial(monkeypatch):
    """
    Vérifie que chaque module de panel s'importe sans erreur
    et que le tutoriel interactif est accessible (présence du mot 'tutoriel' dans le code source).
    """
    for modname, label in PANEL_MODULES:
        try:
            mod = importlib.import_module(modname)
            src = None
            try:
                src = open(mod.__file__, encoding="utf-8").read()
            except Exception:
                pass
            assert mod is not None, f"Import échoué pour {label} ({modname})"
            assert src is not None and (
                "tutoriel" in src.lower() or "tutorial" in src.lower()
            ), f"Tutoriel non trouvé dans {label} ({modname})"
        except Exception as e:
            pytest.fail(f"Erreur import/tutoriel pour {label} ({modname}): {e}")
