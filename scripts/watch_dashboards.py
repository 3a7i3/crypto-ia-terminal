import subprocess
import time
from pathlib import Path


def watch_dashboards():
    root = Path(__file__).parent.parent
    last_mtimes = {}
    while True:
        changed = False
        for py in root.rglob("*.py"):
            mtime = py.stat().st_mtime
            if py not in last_mtimes or last_mtimes[py] != mtime:
                changed = True
                last_mtimes[py] = mtime
        if changed:
            print(
                "[Watcher] Changement détecté, régénération du tableau des dashboards et de l’audit..."
            )
            subprocess.run(
                [".venv/Scripts/python", "scripts/generate_dashboards_table.py"]
            )
            subprocess.run([".venv/Scripts/python", "scripts/generate_audit_report.py"])
        time.sleep(5)


if __name__ == "__main__":
    watch_dashboards()
