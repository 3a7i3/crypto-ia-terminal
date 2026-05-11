import streamlit

from evolution_3d_view import show_sidebar_tutorial


def test_show_sidebar_tutorial_renders(monkeypatch):
    # Simule l’état Streamlit
    state = {}

    def fake_button(label, key=None):
        state[key] = not state.get(key, False)
        return True

    def fake_expander(label, expanded=False):
        class Dummy:
            def __enter__(self):
                return None

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        return Dummy()

    monkeypatch.setattr(streamlit, "button", fake_button)
    monkeypatch.setattr(streamlit, "expander", fake_expander)
    monkeypatch.setattr(streamlit, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "session_state", state)
    # Appel pour chaque panel
    for panel in [
        "3d",
        "supervision",
        "botdoctor",
        "multimonde",
        "quantv16",
        "terminalv12",
        "feedback",
    ]:
        show_sidebar_tutorial(panel, "DOC.md")
        assert f"show_tuto_sidebar_{panel}" in state
