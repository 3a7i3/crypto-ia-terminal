from __future__ import annotations

import csv
import logging

from ONBOARDING_SCRIPT import save_feedback_local


def test_save_feedback_local_creates_file_and_writes_row(tmp_path) -> None:
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "Parfait!",
    }
    csv_path = tmp_path / "feedback.csv"

    save_feedback_local(feedback, str(csv_path), allow_temp=True)

    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["user"] == "test"
    assert rows[0]["note"] == "5"
    assert rows[0]["comment"] == "Parfait!"


def test_save_feedback_local_appends(tmp_path) -> None:
    csv_path = tmp_path / "feedback.csv"
    save_feedback_local(
        {"timestamp": "2026-03-22T12:00:00", "user": "A", "note": 4, "comment": "Bien"},
        str(csv_path),
        allow_temp=True,
    )
    save_feedback_local(
        {"timestamp": "2026-03-22T12:01:00", "user": "B", "note": 3, "comment": "Moyen"},
        str(csv_path),
        allow_temp=True,
    )

    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[1]["user"] == "B"
    assert rows[1]["note"] == "3"
    assert rows[1]["comment"] == "Moyen"


def test_save_feedback_local_rejects_csv_injection(tmp_path) -> None:
    csv_path = tmp_path / "feedback.csv"
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "Malicious,Injection",
    }

    try:
        save_feedback_local(feedback, str(csv_path), allow_temp=True)
        raise AssertionError("Injection non détectée")
    except ValueError as exc:
        assert "Caractère interdit" in str(exc)


def test_save_feedback_local_rejects_newline_injection(tmp_path) -> None:
    csv_path = tmp_path / "feedback.csv"
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "Line\nbreak",
    }

    try:
        save_feedback_local(feedback, str(csv_path), allow_temp=True)
        raise AssertionError("Injection non détectée")
    except ValueError as exc:
        assert "Caractère interdit" in str(exc)


def test_save_feedback_local_rejects_forbidden_path() -> None:
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "ok",
    }
    forbidden_path = "/forbidden_feedback.csv"

    try:
        save_feedback_local(feedback, forbidden_path)
        raise AssertionError("Chemin non autorisé accepté")
    except ValueError as exc:
        assert "Chemin de fichier non autorisé" in str(exc)


def test_save_feedback_local_logs_on_error(tmp_path, monkeypatch) -> None:
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "ok",
    }
    monkeypatch.chdir(tmp_path)
    for handler in logging.getLogger().handlers[:]:
        logging.getLogger().removeHandler(handler)
        handler.close()

    forbidden_dir = tmp_path.parent / "outside_feedback_logs"
    forbidden_dir.mkdir()
    forbidden_path = forbidden_dir / "forbidden_feedback.csv"
    log_path = forbidden_dir / "onboarding_feedback.log"

    try:
        save_feedback_local(feedback, str(forbidden_path))
        raise AssertionError("Chemin non autorisé accepté")
    except ValueError as exc:
        assert "Chemin de fichier non autorisé" in str(exc)

    assert log_path.exists()
    assert "Erreur critique" in log_path.read_text(encoding="utf-8")