"""
test_dataset_gate_restore_window.py — Régression conflit DatasetGate vs
MexcSimulator._restore_positions() (réconciliation Telegram 2026-07-13).

Avant ce correctif, _remediate_orphan_opens() supprimait TOUTE OPEN
orpheline au boot, sans condition d'âge — y compris une position ouverte
quelques minutes avant un restart, que _restore_positions() (appelé juste
après par MexcSimulator.start()) aurait normalement reprise en position
live. Constaté en direct le 2026-07-13 18:00:02 UTC : 1 OPEN orpheline
effacée avant que le restore ait la moindre chance de la voir.
"""

from __future__ import annotations

import json
import time

import pytest

from core import advisor_loop
from paper_trading.mexc_simulator import _RESTORE_MAX_AGE_S


def _write_jsonl(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _open(trade_id, ts, symbol="BTC/USDT"):
    return {"event": "OPEN", "trade_id": trade_id, "ts": ts, "symbol": symbol}


def _close(trade_id, ts, symbol="BTC/USDT"):
    return {"event": "CLOSE", "trade_id": trade_id, "ts": ts, "symbol": symbol}


def test_fresh_orphan_open_survives_remediation(tmp_path):
    """Régression centrale : une OPEN orpheline récente (< fenêtre de
    restauration) ne doit plus être supprimée — MexcSimulator la reprendra."""
    log_path = tmp_path / "paper_trades.jsonl"
    now = time.time()
    _write_jsonl(
        log_path,
        [
            _open("A1", now - 60.0),  # ouverte il y a 1 min — fraîche
            _open("PAIRED", now - 100.0),
            _close("PAIRED", now - 50.0),
        ],
    )

    ok = advisor_loop._remediate_orphan_opens(str(log_path))

    assert ok is True
    ids = {e["trade_id"] for e in _read_jsonl(log_path)}
    assert "A1" in ids  # l'orpheline fraîche est toujours là
    assert "PAIRED" in ids  # trade apparié intact


def test_stale_orphan_open_still_removed(tmp_path):
    """Contre-épreuve : une OPEN orpheline plus vieille que la fenêtre de
    restauration reste supprimée — c'est le cas d'usage original du gate
    (crash ancien, jamais restaurable)."""
    log_path = tmp_path / "paper_trades.jsonl"
    now = time.time()
    _write_jsonl(
        log_path,
        [
            _open("OLD", now - (_RESTORE_MAX_AGE_S + 3600.0)),  # bien au-delà
            _open("PAIRED", now - 100.0),
            _close("PAIRED", now - 50.0),
        ],
    )

    ok = advisor_loop._remediate_orphan_opens(str(log_path))

    assert ok is True
    ids = {e["trade_id"] for e in _read_jsonl(log_path)}
    assert "OLD" not in ids
    assert "PAIRED" in ids
    backups = list(tmp_path.glob("paper_trades.jsonl.bak_*"))
    assert len(backups) == 1  # sauvegarde créée avant réécriture


def test_mixed_fresh_and_stale_orphans(tmp_path):
    """Un mélange doit trier correctement : la fraîche reste, la vieille part."""
    log_path = tmp_path / "paper_trades.jsonl"
    now = time.time()
    _write_jsonl(
        log_path,
        [
            _open("FRESH", now - 60.0),
            _open("STALE", now - (_RESTORE_MAX_AGE_S + 3600.0)),
        ],
    )

    advisor_loop._remediate_orphan_opens(str(log_path))

    ids = {e["trade_id"] for e in _read_jsonl(log_path)}
    assert ids == {"FRESH"}


def test_no_backup_written_when_nothing_stale(tmp_path):
    """Si tout est dans la fenêtre de restauration, aucune réécriture/backup
    n'est nécessaire — évite du bruit disque à chaque restart normal."""
    log_path = tmp_path / "paper_trades.jsonl"
    now = time.time()
    _write_jsonl(log_path, [_open("A1", now - 60.0)])

    advisor_loop._remediate_orphan_opens(str(log_path))

    assert list(tmp_path.glob("paper_trades.jsonl.bak_*")) == []


class _FakeReport:
    def __init__(self, violations, paired_trades=0, total_events=1):
        self.violations = violations
        self.paired_trades = paired_trades
        self.total_events = total_events
        self.burnin_eligible = False


def test_gate_tolerates_fresh_orphans_after_remediation(tmp_path, monkeypatch):
    """Après remédiation, s'il ne reste QUE des violations 'OPEN sans CLOSE'
    (orphelines fraîches volontairement laissées), le gate doit laisser
    démarrer le moteur — pas de sys.exit."""
    import paper_trading.dataset_validator as dataset_validator

    log_path = tmp_path / "paper_trades.jsonl"
    log_path.write_text("{}\n")  # contenu peu importe, validate_corpus mocké
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    reports = iter(
        [
            _FakeReport(["1 OPEN sans CLOSE (positions fantômes)"], total_events=3),
            _FakeReport(["1 OPEN sans CLOSE (positions fantômes)"], total_events=3),
        ]
    )
    monkeypatch.setattr(
        dataset_validator, "validate_corpus", lambda log_path: next(reports)
    )
    monkeypatch.setattr(advisor_loop, "_remediate_orphan_opens", lambda p: True)

    advisor_loop._gate_paper_dataset()  # ne doit pas lever SystemExit


def test_gate_still_exits_on_non_orphan_violation(tmp_path, monkeypatch):
    """Contre-épreuve : une violation qui n'est PAS 'OPEN sans CLOSE' (ex.
    trade_id dupliqué) doit toujours arrêter le démarrage — le
    correctif ne doit pas élargir la tolérance au-delà des orphelines."""
    import paper_trading.dataset_validator as dataset_validator

    log_path = tmp_path / "paper_trades.jsonl"
    log_path.write_text("{}\n")
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    monkeypatch.setattr(
        dataset_validator,
        "validate_corpus",
        lambda log_path: _FakeReport(["2 trade_id(s) dupliqué(s)"], total_events=5),
    )

    with pytest.raises(SystemExit):
        advisor_loop._gate_paper_dataset()
