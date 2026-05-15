"""
vps_data_sync.py — Synchronise les données du VPS vers les fichiers locaux.

Poll l'API VPS toutes les INTERVAL secondes et écrit les fichiers que les
dashboards Streamlit lisent directement (dashboard_risk.py, execution_health.py, etc.)

Usage:
    python vps_data_sync.py
    VPS_API_URL=http://34.171.188.99:8000 python vps_data_sync.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

VPS_URL = os.getenv("VPS_API_URL", "http://34.171.188.99:8000")
INTERVAL = int(os.getenv("VPS_SYNC_INTERVAL", "30"))
BASE = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [VPS_SYNC] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# (endpoint, chemin local, format)
TARGETS = [
    ("snapshot", BASE / "databases" / "live_snapshot.json", "json"),
    ("blackbox", BASE / "databases" / "black_box.jsonl", "jsonl"),
    ("trades", BASE / "logs" / "trades.jsonl", "jsonl"),
    ("audit", BASE / "logs" / "execution_audit" / "audit.jsonl", "jsonl"),
    ("cycles", BASE / "databases" / "cycle_data.jsonl", "jsonl"),
    ("strategy_ranking", BASE / "databases" / "strategy_ranking.json", "json"),
    ("mistake_memory", BASE / "databases" / "mistake_memory.jsonl", "jsonl"),
    ("multi_exchange", BASE / "databases" / "multi_exchange_snapshot.json", "json"),
]


def fetch_and_write(endpoint: str, path: Path, fmt: str) -> None:
    resp = requests.get(f"{VPS_URL}/api/raw/{endpoint}", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        lines = data.get("lines", [])
        path.write_text(
            "\n".join(json.dumps(line, ensure_ascii=False) for line in lines),
            encoding="utf-8",
        )
    else:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def sync_all() -> None:
    ok = 0
    for endpoint, path, fmt in TARGETS:
        try:
            fetch_and_write(endpoint, path, fmt)
            ok += 1
        except Exception as e:
            log.warning(f"{endpoint}: {e}")
    log.info(f"Sync {ok}/{len(TARGETS)} fichiers depuis {VPS_URL}")


if __name__ == "__main__":
    log.info(f"VPS Data Sync démarré — {VPS_URL} toutes les {INTERVAL}s")
    # Premier sync immédiat
    sync_all()
    while True:
        time.sleep(INTERVAL)
        sync_all()
