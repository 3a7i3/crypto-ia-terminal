from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pandas as pd


def main() -> int:
    audit_path = Path("supervision/alerts_audit.jsonl")
    alert = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "alert": {
            "module": "testmod",
            "type": "testtype",
            "severity": "info",
            "message": "Test message",
        },
        "correction": True,
        "result": {"ok": True},
    }
    audit_path.parent.mkdir(exist_ok=True)
    audit_path.write_text(f"{alert}\n", encoding="utf-8")

    df = pd.DataFrame([alert])
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp.close()
        exported = pd.read_csv(tmp.name)
        assert "testmod" in exported.to_string(), "Module non trouvé dans le CSV exporté"
        assert "Test message" in exported.to_string(), "Message non trouvé dans le CSV exporté"
    os.unlink(tmp.name)
    print("Test d'export CSV passé.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
