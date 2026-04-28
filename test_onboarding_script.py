import csv
import os
import sys
import tempfile

import pytest

# Ajoute le dossier courant au sys.path pour permettre l'import du script
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from ONBOARDING_SCRIPT import save_feedback_local


def test_save_feedback_local_creates_file_and_writes_row():
    feedback = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "test",
        "note": 5,
        "comment": "Parfait!",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "feedback.csv")
        save_feedback_local(feedback, csv_path, allow_temp=True)
        assert os.path.isfile(csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["user"] == "test"
            assert rows[0]["note"] == "5"
            assert rows[0]["comment"] == "Parfait!"


def test_save_feedback_local_appends():
    feedback1 = {
        "timestamp": "2026-03-22T12:00:00",
        "user": "A",
        "note": 4,
        "comment": "Bien",
    }
    feedback2 = {
        "timestamp": "2026-03-22T12:01:00",
        "user": "B",
        "note": 3,
        "comment": "Moyen",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "feedback.csv")
        save_feedback_local(feedback1, csv_path, allow_temp=True)
        save_feedback_local(feedback2, csv_path, allow_temp=True)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[1]["user"] == "B"
            assert rows[1]["note"] == "3"
            assert rows[1]["comment"] == "Moyen"

        def test_save_feedback_local_injection():
            feedback = {
                "timestamp": "2026-03-22T12:00:00",
                "user": "test",
                "note": 5,
                "comment": "Malicious,Injection",
            }
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = os.path.join(tmpdir, "feedback.csv")
                try:
                    save_feedback_local(feedback, csv_path, allow_temp=True)
                    assert False, "Injection non détectée"
                except ValueError as e:
                    assert "Caractère interdit" in str(e)

        def test_save_feedback_local_newline_injection():
            feedback = {
                "timestamp": "2026-03-22T12:00:00",
                "user": "test",
                "note": 5,
                "comment": "Line\nbreak",
            }
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = os.path.join(tmpdir, "feedback.csv")
                try:
                    save_feedback_local(feedback, csv_path, allow_temp=True)
                    assert False, "Injection non détectée"
                except ValueError as e:
                    assert "Caractère interdit" in str(e)

        def test_save_feedback_local_path_refused():
            feedback = {
                "timestamp": "2026-03-22T12:00:00",
                "user": "test",
                "note": 5,
                "comment": "ok",
            }
            # Chemin non autorisé (racine système)
            forbidden_path = os.path.join(
                os.path.abspath(os.sep), "forbidden_feedback.csv"
            )
            try:
                save_feedback_local(feedback, forbidden_path)
                assert False, "Chemin non autorisé accepté"
            except ValueError as e:
                assert "Chemin de fichier non autorisé" in str(e)
