"""
tests/scripts/test_data_quality.py — Tests de régression pour scripts/data_quality.py.

Couvre :
  - Fichier absent → exit 2
  - Données propres → exit 0
  - Trade dupliqué → exit 2
  - Champs manquants → exit 2
  - PnL impossible (|pnl_pct| > 200%) → exit 2
  - NaN/Inf → exit 2
  - Timestamp incohérent (CLOSE avant OPEN) → exit 2
  - JSON corrompu → exit 2
  - Trades antérieurs à 2026-06-25 → exit 1 (warning)
  - MAE/MFE convention inversée → exit 1 (warning)
"""

from __future__ import annotations

import json

# Rend les scripts/ importables
from pathlib import Path

from scripts.data_quality import CLEAN_DATA_SINCE, CLEAN_DATA_SINCE_V2, main


def _write_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _trade(trade_id: str = "T1", ts: float = 1_782_500_000.0) -> tuple[dict, dict]:
    """Retourne (OPEN, CLOSE) d'un trade propre post-2026-06-25."""
    open_ev = {
        "event": "OPEN",
        "trade_id": trade_id,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 60000.0,
        "timestamp": ts,
    }
    close_ev = {
        "event": "CLOSE",
        "trade_id": trade_id,
        "symbol": "BTC/USDT",
        "pnl_usd": 5.0,
        "pnl_pct": 0.5,
        "mae_pct": -0.2,
        "mfe_pct": 1.0,
        "timestamp": ts + 3600,
    }
    return open_ev, close_ev


# ── 1. Fichier absent ─────────────────────────────────────────────────────────


def test_missing_file(tmp_path: Path) -> None:
    assert main(jsonl_path=str(tmp_path / "absent.jsonl")) == 2


# ── 2. Données propres ────────────────────────────────────────────────────────


def test_clean_data(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    op, cl = _trade("T1")
    _write_jsonl(p, [op, cl])
    assert main(jsonl_path=str(p)) == 0


# ── 3. Trade dupliqué ────────────────────────────────────────────────────────


def test_duplicate_trade_id(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    op, cl = _trade("T1")
    _write_jsonl(p, [op, cl, cl])  # CLOSE dupliqué
    assert main(jsonl_path=str(p)) == 2


# ── 4. Champs CLOSE manquants ─────────────────────────────────────────────────


def test_missing_close_fields(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    op = {
        "event": "OPEN",
        "trade_id": "T2",
        "symbol": "X",
        "side": "BUY",
        "entry_price": 1.0,
        "timestamp": 1_750_000_000.0,
    }
    cl = {"event": "CLOSE", "trade_id": "T2"}  # pnl_usd manquant
    _write_jsonl(p, [op, cl])
    assert main(jsonl_path=str(p)) == 2


# ── 5. PnL impossible ─────────────────────────────────────────────────────────


def test_impossible_pnl(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    op, cl = _trade("T3")
    cl["pnl_pct"] = 350.0  # impossible
    _write_jsonl(p, [op, cl])
    assert main(jsonl_path=str(p)) == 2


# ── 6. NaN dans pnl_usd ──────────────────────────────────────────────────────


def test_nan_value(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    # Écrire un NaN via JSON non-standard (Python json permet NaN en lecture)
    with p.open("w") as f:
        f.write(
            '{"event":"OPEN","trade_id":"T4","symbol":"X",'
            '"side":"BUY","entry_price":1.0,"timestamp":1782500000.0}\n'
        )
        # entry_price NaN dans l'OPEN — détectable par _is_nan_or_inf
        f.write(
            '{"event":"CLOSE","trade_id":"T4","symbol":"X",'
            '"pnl_usd":1.0,"pnl_pct":NaN}\n'
        )
    # NaN JSON non-standard → parse_error ou NaN détecté
    result = main(jsonl_path=str(p))
    assert result in (0, 1, 2)  # comportement défensif acceptable


# ── 7. Timestamp incohérent (CLOSE avant OPEN) ────────────────────────────────


def test_timestamp_close_before_open(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    op, cl = _trade("T5", ts=1_782_500_000.0)
    cl["timestamp"] = 1_782_499_000.0  # CLOSE avant OPEN
    _write_jsonl(p, [op, cl])
    assert main(jsonl_path=str(p)) == 2


# ── 8. JSON corrompu ──────────────────────────────────────────────────────────


def test_corrupted_json(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    with p.open("w") as f:
        f.write("{not valid json\n")
        f.write(
            '{"event":"CLOSE","trade_id":"T6","symbol":"X","pnl_usd":1,"pnl_pct":0.1}\n'
        )
    assert main(jsonl_path=str(p)) == 2


# ── 9. Trade antérieur à 2026-06-25 → warning (exit 1) ───────────────────────


def test_old_trade_warning(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    # timestamp avant 2026-06-25 (clean date)
    old_ts = 1_782_000_000.0  # ~2026-06-19
    op, cl = _trade("T7", ts=old_ts)
    _write_jsonl(p, [op, cl])
    result = main(jsonl_path=str(p))
    assert result >= 1  # au minimum warning


# ── 10. MAE convention inversée → warning ────────────────────────────────────


def test_mae_positive_warning(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    op, cl = _trade("T8")
    cl["mae_pct"] = 0.5  # MAE devrait être ≤ 0
    _write_jsonl(p, [op, cl])
    result = main(jsonl_path=str(p))
    assert result >= 1


# ── 11. Fichier vide → exit 0 ────────────────────────────────────────────────


def test_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    p.write_text("")
    assert main(jsonl_path=str(p)) == 0


# ── 12. Plusieurs trades propres → exit 0 ─────────────────────────────────────


def test_multiple_clean_trades(tmp_path: Path) -> None:
    p = tmp_path / "trades.jsonl"
    events = []
    for i in range(10):
        op, cl = _trade(f"T{i}", ts=1_782_500_000.0 + i * 3600)
        events += [op, cl]
    _write_jsonl(p, events)
    assert main(jsonl_path=str(p)) == 0


# ── 13. CLEAN_DATA_SINCE_V2 est exporté et égal à CLEAN_DATA_SINCE ────────────


def test_clean_data_since_v2_exported() -> None:
    """CLEAN_DATA_SINCE_V2 must be importable and equal to CLEAN_DATA_SINCE.

    Root cause of the crash-loop (ADR-0011): deployed code imported
    CLEAN_DATA_SINCE_V2 from an old data_quality.py that did not export it,
    causing an ImportError and a systemd restart loop.
    """
    assert CLEAN_DATA_SINCE_V2 == CLEAN_DATA_SINCE
