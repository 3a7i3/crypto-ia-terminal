from __future__ import annotations

import subprocess
import sys


def main() -> int:
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
    except Exception as exc:
        print(f"Erreur lors du lancement du dashboard : {exc}")
        return 1

    if proc.returncode == 0 or b"Fichiers/dossiers critiques manquants" in proc.stdout:
        return 0

    stderr = proc.stderr.decode(errors="replace")
    print(stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
