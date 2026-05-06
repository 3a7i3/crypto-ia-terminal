"""
Validation: vérifie que build_dashboard() écrit bien dans vault_dir/06_Dashboard/dashboard.md.

Usage:
    python validate_vault_dashboard.py
    OBSIDIAN_VAULT_PATH=/tmp/my_vault python validate_vault_dashboard.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from tracker_system.dashboard.builder import build_dashboard
from tracker_system.storage.saver import append_jsonl, save_json


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        trades = root / "trades.jsonl"
        optimizer = root / "optimizer.json"

        append_jsonl(trades, {
            "type": "exit", "symbol": "BTCUSDT",
            "pnl_usd": 55.0, "pnl_pct": 0.018,
            "mfe": 0.025, "mae": -0.007, "regime": "bullish",
        })
        save_json(optimizer, {"bullish": {"tp": 0.025, "sl": 0.01, "trailing": 0.005, "score": 0.042, "winrate": 0.65}})

        path = build_dashboard(log_file=trades, optimizer_file=optimizer, vault_dir=vault)

        assert path == vault / "06_Dashboard" / "dashboard.md", f"Mauvais chemin: {path}"
        assert path.exists(), "Fichier non créé"
        content = path.read_text(encoding="utf-8")
        for section in ("# Dashboard Intelligence", "## Performance", "## Trade Quality", "## Regime State", "## Optimizer State"):
            assert section in content, f"Section manquante: {section!r}"

        print(f"[OK] Dashboard généré: {path}")
        print(f"     {len(content)} caractères, sections valides")


if __name__ == "__main__":
    try:
        run()
        sys.exit(0)
    except AssertionError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(1)
