import streamlit

from evolution_3d_view import (botdoctor_dashboard_panel,
                               evolution_multimonde_panel,
                               feedback_dashboard_panel,
                               quant_terminal_v12_panel, quant_v16_panel,
                               supervision_autoheal_panel)


def fake_streamlit(monkeypatch):
    # Patch streamlit for headless test
    monkeypatch.setattr(streamlit, "button", lambda *a, **k: False)
    monkeypatch.setattr(
        streamlit,
        "expander",
        lambda *a, **k: type(
            "Dummy",
            (),
            {"__enter__": lambda s: None, "__exit__": lambda s, a, b, c: False},
        )(),
    )
    monkeypatch.setattr(streamlit, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "info", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "success", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "dataframe", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "title", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "header", lambda *a, **k: None)
    monkeypatch.setattr(streamlit, "session_state", {})


def test_supervision_panel(monkeypatch):
    fake_streamlit(monkeypatch)
    supervision_autoheal_panel()


def test_botdoctor_panel(monkeypatch):
    fake_streamlit(monkeypatch)
    botdoctor_dashboard_panel()


def test_multimonde_panel(monkeypatch):
    fake_streamlit(monkeypatch)
    evolution_multimonde_panel()


def test_quantv16_panel(monkeypatch):
    fake_streamlit(monkeypatch)
    quant_v16_panel()


def test_terminalv12_panel(monkeypatch):
    fake_streamlit(monkeypatch)
    quant_terminal_v12_panel()


def test_feedback_panel(monkeypatch):
    fake_streamlit(monkeypatch)
    feedback_dashboard_panel()
