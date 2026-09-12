"""TG-PAPER-01 — tests du notificateur PAPER Telegram (push-only).

Le transport Telegram est entièrement mocké (jamais de réseau réel dans
les tests). Ces tests couvrent : bootstrap live-only, filtrage
mode=futures_demo, honnêteté des valeurs manquantes (None != 0),
normalisation du side, avancement/non-avancement du checkpoint,
tolérance aux lignes partielles/malformées, et l'invariant de passivité
(aucune importation d'un composant de stratégie/exécution/gate).
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.paper import paper_trade_notifier as notifier


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_lines(path, records):
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _open_record(trade_id="T1", **overrides):
    rec = {
        "event": "OPEN",
        "trade_id": trade_id,
        "ts": 1000.0,
        "ts_iso": "2026-09-12T00:00:00Z",
        "symbol": "BTC/USDT",
        "side": "buy",
        "price": 112430.50,
        "size_usd": 8.0,
        "mode": "futures_demo",
        "regime": "bull_trend",
        "score": 74,
    }
    rec.update(overrides)
    return rec


def _close_record(trade_id="T1", **overrides):
    rec = {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": 1041.0,
        "ts_iso": "2026-09-12T00:41:00Z",
        "symbol": "BTC/USDT",
        "side": "buy",
        "price": 113025.20,
        "size_usd": 8.0,
        "mode": "futures_demo",
        "exit_price": 113025.20,
        "pnl_usd": 0.04,
        "pnl_pct": 0.005,
        "reason": "TP",
        "duration_s": 2460,
        "pnl_fee_evidence_incomplete": False,
    }
    rec.update(overrides)
    return rec


@pytest.fixture
def cfg(tmp_path):
    return notifier.NotifierConfig(
        bot_token="dummy-token",
        chat_id="dummy-chat",
        source_path=tmp_path / "paper_trades.jsonl",
        checkpoint_path=tmp_path / "checkpoint.json",
    )


class FakeSender:
    def __init__(self, succeed=True):
        self.succeed = succeed
        self.sent = []

    def send(self, text: str) -> bool:
        self.sent.append(text)
        return self.succeed


def _make_follower(cfg):
    store = notifier.CheckpointStore(cfg.checkpoint_path)
    follower = notifier.PaperTradeLedgerFollower(cfg, store)
    follower.bootstrap()
    return follower


# ── 1. Bootstrap live-only ────────────────────────────────────────────────────


def test_first_startup_starts_at_eof_and_sends_nothing(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    _write_lines(cfg.source_path, [_open_record("HIST1"), _close_record("HIST1")])

    follower = _make_follower(cfg)
    sender = FakeSender()

    sent = notifier.run_once(follower, sender.send)

    assert sent == 0
    assert sender.sent == []
    assert follower._offset == cfg.source_path.stat().st_size


# ── 2/3. New OPEN / CLOSE events ─────────────────────────────────────────────


def test_new_open_appended_sends_one_entry_notification(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    _write_lines(cfg.source_path, [_open_record()])
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    assert sent == 1
    assert "PAPER ENTRY" in sender.sent[0]
    assert "BTC/USDT" in sender.sent[0]


def test_new_close_appended_sends_one_exit_notification(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    _write_lines(cfg.source_path, [_close_record()])
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    assert sent == 1
    assert "PAPER EXIT" in sender.sent[0]


# ── 4/5/6. Filtering ──────────────────────────────────────────────────────────


def test_event_mode_not_futures_demo_is_ignored(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    _write_lines(cfg.source_path, [_open_record(mode="paper")])
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    assert sent == 0
    assert sender.sent == []


def test_missing_mode_is_ignored(cfg):
    rec = _open_record()
    del rec["mode"]
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    _write_lines(cfg.source_path, [rec])
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    assert sent == 0


def test_unrelated_event_type_is_ignored(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    rec = _open_record()
    rec["event"] = "SOMETHING_ELSE"
    _write_lines(cfg.source_path, [rec])
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    assert sent == 0


# ── 7/8/9. Honest unknown handling ───────────────────────────────────────────


def test_pnl_none_displays_unresolved_never_zero():
    msg = notifier.format_exit_message(_close_record(pnl_usd=None))
    assert "PAPER OUTCOME UNRESOLVED" in msg
    assert "$0.00" not in msg
    assert "UNKNOWN" in msg


def test_exit_price_none_displays_unknown_never_zero():
    msg = notifier.format_exit_message(_close_record(exit_price=None, pnl_usd=None))
    assert "Sortie : UNKNOWN" in msg
    assert "$0.00" not in msg


def test_pnl_fee_evidence_incomplete_adds_warning():
    msg = notifier.format_exit_message(
        _close_record(pnl_fee_evidence_incomplete=True)
    )
    assert "PnL fee evidence incomplete" in msg


# ── 10/11/12. Side normalization ──────────────────────────────────────────────


def test_buy_normalizes_long():
    assert notifier.normalize_side("buy") == "LONG"
    assert notifier.normalize_side("long") == "LONG"


def test_sell_normalizes_short():
    assert notifier.normalize_side("sell") == "SHORT"
    assert notifier.normalize_side("short") == "SHORT"


def test_invalid_side_is_unknown_not_short():
    assert notifier.normalize_side("sideways") == "UNKNOWN"
    assert notifier.normalize_side(None) == "UNKNOWN"


# ── 13/14. Checkpoint advance on success/failure ─────────────────────────────


def test_telegram_success_advances_checkpoint(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)
    _write_lines(cfg.source_path, [_open_record()])

    sender = FakeSender(succeed=True)
    notifier.run_once(follower, sender.send)

    saved = notifier.CheckpointStore(cfg.checkpoint_path).load()
    assert saved.byte_offset == cfg.source_path.stat().st_size


def test_telegram_failure_does_not_advance_past_event(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)
    offset_before = follower._offset
    _write_lines(cfg.source_path, [_open_record()])

    sender = FakeSender(succeed=False)
    sent = notifier.run_once(follower, sender.send)

    assert sent == 0
    saved = notifier.CheckpointStore(cfg.checkpoint_path).load()
    assert saved.byte_offset == offset_before


# ── 15. Restart resumes from checkpoint ──────────────────────────────────────


def test_restart_with_checkpoint_does_not_resend_delivered_event(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)
    _write_lines(cfg.source_path, [_open_record()])
    sender1 = FakeSender(succeed=True)
    notifier.run_once(follower, sender1.send)
    assert len(sender1.sent) == 1

    # Simule un redémarrage : nouveau follower, même checkpoint sur disque.
    follower2 = _make_follower(cfg)
    sender2 = FakeSender(succeed=True)
    sent = notifier.run_once(follower2, sender2.send)

    assert sent == 0
    assert sender2.sent == []


# ── 16. Partial trailing line ─────────────────────────────────────────────────


def test_partial_final_line_not_processed_until_complete(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    partial = json.dumps(_open_record())[:20]  # tronqué, pas de \n final
    cfg.source_path.write_text(partial, encoding="utf-8")

    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    assert sent == 0
    assert sender.sent == []

    # Complète la ligne : elle doit maintenant être traitée.
    with cfg.source_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_open_record())[20:] + "\n")
    sent = notifier.run_once(follower, sender.send)
    assert sent == 1


# ── 17. Malformed complete JSON ───────────────────────────────────────────────


def test_malformed_complete_json_is_skipped_deterministically(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)

    with cfg.source_path.open("a", encoding="utf-8") as f:
        f.write("{not valid json\n")
        f.write(json.dumps(_open_record()) + "\n")

    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)

    # La ligne malformée est sautée définitivement, la suivante est traitée.
    assert sent == 1
    assert follower._offset == cfg.source_path.stat().st_size


# ── 18. Missing source file ───────────────────────────────────────────────────


def test_missing_source_file_waits_safely(cfg):
    # Le fichier n'existe pas du tout.
    follower = _make_follower(cfg)
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)
    assert sent == 0
    assert sender.sent == []


# ── 19/20. Missing token/chat id fail closed ─────────────────────────────────


def test_missing_bot_token_fails_startup(monkeypatch):
    monkeypatch.delenv("PAPER_ARENA_BOT_TOKEN", raising=False)
    monkeypatch.setenv("PAPER_ARENA_CHAT_ID", "chat")
    with pytest.raises(notifier.NotifierConfigError):
        notifier.NotifierConfig.from_env()


def test_missing_chat_id_fails_startup(monkeypatch):
    monkeypatch.setenv("PAPER_ARENA_BOT_TOKEN", "token")
    monkeypatch.delenv("PAPER_ARENA_CHAT_ID", raising=False)
    with pytest.raises(notifier.NotifierConfigError):
        notifier.NotifierConfig.from_env()


# ── 21-28. Passivity / no forbidden imports ──────────────────────────────────


def test_notifier_source_contains_no_get_updates():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "getUpdates" not in src
    assert "setWebhook" not in src
    assert "deleteWebhook" not in src


def test_notifier_exposes_no_command_dispatcher():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "/start" not in src
    assert "/help" not in src
    assert "CommandHandler" not in src


def test_notifier_imports_no_rsi_strategy():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "RSIExtremeStrategy" not in src


def test_notifier_imports_no_paper_metrics():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "PaperMetrics" not in src


def test_notifier_imports_no_paper_gate():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "gate_passed" not in src
    assert "PaperGate" not in src


def test_notifier_imports_no_paper_position_manager():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "PaperPositionManager" not in src


def test_notifier_does_not_import_advisor_loop():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "advisor_loop" not in src


def test_notifier_does_not_import_mexc_simulator():
    src = open(notifier.__file__, encoding="utf-8").read()
    assert "mexc_simulator" not in src
    assert "MexcSimulator" not in src


# ── 29. Never writes paper_trades.jsonl ──────────────────────────────────────


def test_notifier_never_writes_source_file(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)
    _write_lines(cfg.source_path, [_open_record(), _close_record()])

    before = cfg.source_path.read_bytes()
    sender = FakeSender()
    notifier.run_once(follower, sender.send)
    after = cfg.source_path.read_bytes()

    assert before == after


# ── 30. systemd ExecStart ────────────────────────────────────────────────────


def test_systemd_execstart_points_to_notifier():
    unit_path = (
        __file__.rsplit("/tests/", 1)[0] + "/scripts/systemd/paper-arena.service"
    )
    content = open(unit_path, encoding="utf-8").read()
    assert "src.paper.paper_trade_notifier" in content
    assert "src.paper.paper_runner" not in content


# ── TG-PAPER-01-R1 §3: mandatory ordering regression ─────────────────────────


def test_failed_send_never_skips_event_past_a_later_malformed_line(cfg):
    """VALID OPEN A, MALFORMED, VALID OPEN B — A's failed send must never
    be leapfrogged by the malformed-line skip that follows it in source
    order (the R1-A defect: poll_new_records() used to advance the
    follower's committed offset internally while merely reading ahead)."""
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)
    offset_before_a = follower._offset

    with cfg.source_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_open_record("A")) + "\n")
        f.write("{not valid json\n")
        f.write(json.dumps(_open_record("B")) + "\n")

    # First run: Telegram fails on A.
    sender = FakeSender(succeed=False)
    sent = notifier.run_once(follower, sender.send)

    assert sent == 0
    assert len(sender.sent) == 1 and "A" in sender.sent[0]  # attempted, not delivered
    # Committed checkpoint (and in-memory follower position) must remain
    # strictly BEFORE A — neither the malformed line nor B may have been
    # skipped over A.
    assert follower._offset == offset_before_a
    saved = notifier.CheckpointStore(cfg.checkpoint_path).load()
    assert saved.byte_offset == offset_before_a

    # Second run: Telegram now succeeds.
    sender2 = FakeSender(succeed=True)
    sent2 = notifier.run_once(follower, sender2.send)

    assert sent2 == 2  # A delivered, then B delivered (malformed skipped in between)
    assert "A" in sender2.sent[0]
    assert "B" in sender2.sent[1]
    assert follower._offset == cfg.source_path.stat().st_size
    saved2 = notifier.CheckpointStore(cfg.checkpoint_path).load()
    assert saved2.byte_offset == cfg.source_path.stat().st_size


def test_poll_new_records_never_mutates_offset_itself(cfg):
    """poll_new_records() is pure read-ahead: it must never advance the
    follower's committed offset on its own, even across a malformed line —
    only run_once()/advance() may do that, and only in source order."""
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.source_path.write_text("", encoding="utf-8")
    follower = _make_follower(cfg)
    offset_before = follower._offset

    with cfg.source_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_open_record("A")) + "\n")
        f.write("{not valid json\n")

    results = follower.poll_new_records()

    assert follower._offset == offset_before
    assert [kind for kind, _, _ in results] == ["event", "malformed"]


# ── TG-PAPER-01-R1 §4: no Markdown parse_mode ────────────────────────────────


def test_send_payload_never_sets_parse_mode():
    sender = notifier.TelegramSender("tok", "chat")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["data"] = request.data
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b'{"ok": true}'
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    with patch.object(notifier.urllib.request, "urlopen", side_effect=fake_urlopen):
        ok = sender.send("hello")

    assert ok is True
    body = captured["data"].decode()
    assert "parse_mode" not in body


# ── TG-PAPER-01-R1 §5: strict Telegram ACK contract ──────────────────────────


def _mock_response(status, body_bytes):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body_bytes
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_ack_http_2xx_with_ok_true_is_success():
    sender = notifier.TelegramSender("tok", "chat")
    with patch.object(
        notifier.urllib.request,
        "urlopen",
        return_value=_mock_response(200, b'{"ok": true, "result": {}}'),
    ):
        assert sender.send("hi") is True


def test_ack_http_2xx_with_ok_false_is_failure():
    sender = notifier.TelegramSender("tok", "chat")
    with patch.object(
        notifier.urllib.request,
        "urlopen",
        return_value=_mock_response(200, b'{"ok": false, "description": "bad"}'),
    ):
        assert sender.send("hi") is False


def test_ack_http_2xx_with_malformed_body_is_failure():
    sender = notifier.TelegramSender("tok", "chat")
    with patch.object(
        notifier.urllib.request,
        "urlopen",
        return_value=_mock_response(200, b"not json at all"),
    ):
        assert sender.send("hi") is False


def test_ack_http_2xx_with_json_missing_ok_is_failure():
    sender = notifier.TelegramSender("tok", "chat")
    with patch.object(
        notifier.urllib.request,
        "urlopen",
        return_value=_mock_response(200, b'{"result": {}}'),
    ):
        assert sender.send("hi") is False


def test_ack_http_error_is_failure():
    sender = notifier.TelegramSender("tok", "chat")
    with patch.object(
        notifier.urllib.request,
        "urlopen",
        side_effect=urllib.error.HTTPError("url", 500, "Internal Error", {}, None),
    ):
        assert sender.send("hi") is False


def test_ack_network_failure_is_failure():
    sender = notifier.TelegramSender("tok", "chat")
    with patch.object(
        notifier.urllib.request, "urlopen", side_effect=OSError("network down")
    ):
        assert sender.send("hi") is False


def test_ack_failure_never_logs_bot_token(caplog):
    sender = notifier.TelegramSender("super-secret-token", "chat")
    with patch.object(
        notifier.urllib.request,
        "urlopen",
        side_effect=urllib.error.HTTPError("url", 401, "Unauthorized", {}, None),
    ):
        with caplog.at_level("WARNING"):
            sender.send("hi")
    assert "super-secret-token" not in caplog.text


# ── TG-PAPER-01-R1 §7: checkpoint offset validity ────────────────────────────


def test_negative_checkpoint_offset_rebootstraps_safely(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    _write_lines(cfg.source_path, [_open_record("HIST1")])
    notifier.CheckpointStore(cfg.checkpoint_path).save(
        notifier.Checkpoint(source_path=str(cfg.source_path), byte_offset=-5)
    )

    follower = _make_follower(cfg)

    assert follower._offset == cfg.source_path.stat().st_size
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)
    assert sent == 0  # no historical replay


def test_checkpoint_offset_beyond_eof_rebootstraps_safely(cfg):
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    _write_lines(cfg.source_path, [_open_record("HIST1")])
    real_size = cfg.source_path.stat().st_size
    notifier.CheckpointStore(cfg.checkpoint_path).save(
        notifier.Checkpoint(
            source_path=str(cfg.source_path), byte_offset=real_size + 999
        )
    )

    follower = _make_follower(cfg)

    assert follower._offset == real_size
    sender = FakeSender()
    sent = notifier.run_once(follower, sender.send)
    assert sent == 0  # no historical replay, no infinite seek-past-EOF
