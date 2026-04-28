import subprocess
import sys


def test_dashboard_launch():
    """Teste si le dashboard Streamlit se lance sans erreur de dépendance/fichier."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "evolution_dashboard.py",
                "--server.headless",
                "true",
                "--server.port",
                "8888",
            ],
            capture_output=True,
            timeout=120,
        )
        assert (
            proc.returncode == 0
            or b"Fichiers/dossiers critiques manquants" in proc.stdout
        ), proc.stderr.decode()
    except Exception as e:
        assert False, f"Erreur lors du lancement du dashboard : {e}"
