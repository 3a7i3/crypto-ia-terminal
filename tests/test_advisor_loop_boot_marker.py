"""Tests du marqueur BOOT — plus jamais de redémarrage anonyme.

Régression : 3 arrêts sans auteur identifié le 2026-07-07 (04:00-04:08 UTC),
aucune trace de qui/quoi les a déclenchés. _acquire_instance_lock() capture
désormais si un verrou préexistait (= l'ancien process n'a pas nettoyé à la
sortie, arrêt non-propre) et le PID précédent, consommés par le marqueur
BOOT écrit dans la BlackBox au démarrage.
"""

from __future__ import annotations

import advisor_loop


class TestAcquireInstanceLockCapturesBootCause:
    def test_fresh_lock_file_reports_no_preexisting_lock(self, tmp_path, monkeypatch):
        lock_path = tmp_path / "advisor.lock"
        monkeypatch.setattr(advisor_loop, "_LOCK_FILE", str(lock_path))
        monkeypatch.setattr(advisor_loop, "_boot_lock_preexisted", False)
        monkeypatch.setattr(advisor_loop, "_boot_previous_pid", "")

        advisor_loop._acquire_instance_lock()
        try:
            assert advisor_loop._boot_lock_preexisted is False
            assert advisor_loop._boot_previous_pid == ""
        finally:
            advisor_loop._release_instance_lock()

    def test_preexisting_lock_file_reports_previous_pid(self, tmp_path, monkeypatch):
        lock_path = tmp_path / "advisor.lock"
        dead_pid = 999999999  # PID quasi certainement inexistant
        lock_path.write_text(str(dead_pid), encoding="utf-8")
        monkeypatch.setattr(advisor_loop, "_LOCK_FILE", str(lock_path))
        monkeypatch.setattr(advisor_loop, "_boot_lock_preexisted", False)
        monkeypatch.setattr(advisor_loop, "_boot_previous_pid", "")

        advisor_loop._acquire_instance_lock()
        try:
            assert advisor_loop._boot_lock_preexisted is True
            assert advisor_loop._boot_previous_pid == str(dead_pid)
        finally:
            advisor_loop._release_instance_lock()


class TestBootCauseText:
    def test_fresh_start_describes_clean_shutdown_or_first_boot(self):
        text = advisor_loop._boot_cause_text(False, "")
        assert "propre" in text or "premier" in text

    def test_preexisting_lock_names_previous_pid(self):
        text = advisor_loop._boot_cause_text(True, "12345")
        assert "12345" in text
        assert "non-propre" in text or "crash" in text

    def test_preexisting_lock_without_pid_falls_back_to_inconnu(self):
        text = advisor_loop._boot_cause_text(True, "")
        assert "inconnu" in text
