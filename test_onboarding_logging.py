import os

import pytest

from ONBOARDING_SCRIPT import save_feedback_local


def test_logging_on_error(tmp_path):
    # Provoque une erreur d'ouverture de fichier (chemin non autorisé)
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "ok",
    }
    forbidden_path = os.path.join(os.path.abspath(os.sep), "forbidden_feedback.csv")
    log_path = os.path.join(os.getcwd(), "onboarding_feedback.log")
    if os.path.exists(log_path):
        os.remove(log_path)
    with pytest.raises(ValueError):
        save_feedback_local(feedback, forbidden_path)
    # Vérifie que le log a bien été écrit
    assert os.path.exists(log_path)
    with open(log_path, encoding="utf-8") as f:
        log_content = f.read()
    assert "Erreur critique" in log_content
