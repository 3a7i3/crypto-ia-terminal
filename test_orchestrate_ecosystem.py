import os
import sys


sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import sys


def test_orchestrate_ecosystem_main(monkeypatch, tmp_path):
    import builtins
    import shutil
    import types
    from pathlib import Path

    import orchestrate_ecosystem

    # Patch subprocess.run pour éviter l'exécution réelle
    calls = []

    def fake_run(cmd, check=False, **kwargs):
        calls.append(cmd)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr("subprocess.run", fake_run)

    # Prépare des dossiers temporaires pour results et archives
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    monkeypatch.setattr(orchestrate_ecosystem, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(orchestrate_ecosystem, "ARCHIVE_DIR", archive_dir)

    # Crée un faux fichier à archiver
    fake_csv = results_dir / "result1.csv"
    fake_csv.write_text("col1,col2\n1,2")

    # Patch shutil.copy pour tracer les copies
    copied = []
    monkeypatch.setattr(shutil, "copy", lambda src, dst: copied.append((src, dst)))

    # Patch Path.mkdir pour éviter la création réelle sur archive_path
    monkeypatch.setattr(Path, "mkdir", lambda self, exist_ok: None)

    # Patch datetime pour un timestamp fixe
    monkeypatch.setattr(
        "orchestrate_ecosystem.datetime",
        types.SimpleNamespace(
            now=lambda: types.SimpleNamespace(strftime=lambda fmt: "20260101_120000")
        ),
    )

    # Patch feedback_dir.exists pour simuler l'absence de feedback_logs
    monkeypatch.setattr(builtins, "print", lambda *a, **k: None)  # Silence output
    monkeypatch.setattr(Path, "exists", lambda self: False)

    orchestrate_ecosystem.run_and_archive()

    # Vérifie que les sous-processus ont été appelés
    assert any("run_strategy_factory.py" in str(cmd) for cmd in calls)
    assert any("analyze_strategy_niches.py" in str(cmd) for cmd in calls)
    # Vérifie que le fichier a été copié dans l'archive
    assert any(str(fake_csv) in str(src) for src, dst in copied)
