import subprocess
import sys


def test_monitoring_profiler_runs():
    """Vérifie que le script de monitoring s'exécute sans erreur et affiche les logs."""
    result = subprocess.run(
        [sys.executable, "supervision/monitoring_profiler.py", "--duration", "2"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Erreur d'exécution: {result.stderr}"
    assert (
        "Démarrage du monitoring" in result.stdout
        or "Démarrage du monitoring" in result.stderr
    )


def test_monitoring_profiler_bad_args():
    """Vérifie la robustesse aux mauvais arguments."""
    result = subprocess.run(
        [sys.executable, "supervision/monitoring_profiler.py", "--duration", "abc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
