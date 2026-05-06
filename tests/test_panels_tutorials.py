from panel_registry import PANEL_SPECS


def test_panel_tutorial_sources_are_declared():
    """
    Vérifie que chaque panel déclaré expose bien une source lisible
    et un tutoriel détectable sans importer l'application Streamlit complète.
    """
    for spec in PANEL_SPECS:
        source = spec["source"]
        label = spec["label"]
        module = spec["module"]
        assert source.exists(), f"Source introuvable pour {label} ({module})"
        src = source.read_text(encoding="utf-8")
        assert "tutoriel" in src.lower() or "tutorial" in src.lower(), (
            f"Tutoriel non trouvé dans {label} ({module})"
        )
