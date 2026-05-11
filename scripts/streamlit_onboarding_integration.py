from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import requests


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    onboarding_script = repo_root / "ONBOARDING_SCRIPT.py"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(onboarding_script),
            "--server.headless=true",
            "--server.port=8502",
        ],
        cwd=str(repo_root),
    )
    time.sleep(5)
    try:
        response = requests.get("http://localhost:8502", timeout=10)
        if response.status_code != 200:
            print(f"[ERREUR] HTTP {response.status_code}")
            return 1
        if "onboarding" not in response.text.lower():
            print("[ERREUR] Le mot 'onboarding' est absent de la page")
            return 1
        print("[OK] Le dashboard Streamlit d'onboarding répond correctement.")
        return 0
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
