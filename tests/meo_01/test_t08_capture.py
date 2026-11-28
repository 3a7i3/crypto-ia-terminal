"""T8 bounded capture behind a synthetic Kraken (no socket is ever created)."""

import json
from pathlib import Path
from unittest import mock

import pytest

from observability.radar_composite import kraken_trade_pilot as ktp
from observability.radar_composite import pilot as l3


def events(out):
    return [json.loads(x) for x in (Path(out) / "events.jsonl").read_text().splitlines()]


def manifest(out):
    return json.loads((Path(out) / "manifest.json").read_text())


def test_t08_dry_run_completes_within_its_budgets(tmp_path):
    pilot, code = ktp.dry_run(tmp_path / "c")
    m = manifest(tmp_path / "c")
    assert code == 0 and m["status"] == "COMPLETED" and m["evidence_kind"] == "SYNTHETIC"
    assert m["rest_used"] == {"time": 2, "assetPairs": 1, "assets": 1, "trades": 3}
    assert all(m["rest_used"][k] <= v for k, v in ktp.REST_BUDGET.items())
    ev = events(tmp_path / "c")
    assert sum(e["kind"] == "ws_open" for e in ev) == 1  # one connection, no reconnection
    assert m["sealed"]["frames_bytes"] + m["sealed"]["events_bytes"] < ktp.CAPS["max_storage_bytes"]
    assert all(type(e["recv_wall_ns"]) is int and e["recv_wall_ms"] == e["recv_wall_ns"] // 1_000_000 for e in ev)


def test_t08_only_the_public_trade_subscription_is_sent(tmp_path):
    ktp.dry_run(tmp_path / "c")
    sent = [e for e in events(tmp_path / "c") if e["kind"] == "sent"]
    assert len(sent) == 1
    raw = (tmp_path / "c" / "frames.bin").read_bytes()
    text = raw[sent[0]["offset"]:sent[0]["offset"] + sent[0]["bytes"]].decode()
    assert json.loads(text) == {"method": "subscribe", "req_id": 1,
                                "params": {"channel": "trade", "symbol": ["BTC/USDT"], "snapshot": True}}
    for word in ("token", "key", "secret", "executions", "balances", "add_order", "auth"):
        assert word not in text.lower()


def test_t08_rest_and_websocket_allow_lists():
    assert ktp.allowed_url(ktp.STATIC_URLS["time"])
    assert ktp.allowed_url(ktp.trades_url("1795128000"))
    for url in ("https://api.kraken.com/0/private/Balance", "https://api.kraken.com/0/public/Trades?pair=XBTUSD",
                "https://api.kraken.com/0/public/Trades?pair=XBTUSDT&since=1&count=5",
                "http://api.kraken.com/0/public/Time", "https://evil.example/0/public/Time"):
        assert not ktp.allowed_url(url), url
    with pytest.raises(l3.Refused):
        ktp.trades_url("1;x")
    with pytest.raises(l3.Refused):
        ktp.KrakenTradeSession(l3.FakeClock(0)).rest("https://api.kraken.com/0/private/Balance")
    assert ktp.WS_URL == "wss://ws.kraken.com/v2"


def test_t08_rest_requests_carry_no_credentials():
    seen = []

    def fake_urlopen(req, timeout):
        seen.append(req)
        raise OSError("offline")
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        status, _, _, error = ktp.KrakenTradeSession(l3.FakeClock(0)).rest(ktp.STATIC_URLS["time"])
    assert status is None and error.startswith("TRANSPORT_")
    headers = {k.lower() for k in seen[0].headers}
    assert headers == {"user-agent", "accept"} and seen[0].get_method() == "GET"


def test_t08_close_stops_without_reconnection_but_keeps_the_cross_check(tmp_path):
    _, code = ktp.dry_run(tmp_path / "c", faults=[("close", 400_000)])
    m = manifest(tmp_path / "c")
    assert code == 2 and m["stop_code"] == "WS_CLOSED_KRAKEN" and m["status"] == "STOPPED"
    assert sum(e["kind"] == "ws_open" for e in events(tmp_path / "c")) == 1
    assert m["rest_used"]["trades"] >= 1 and "clock_end" in m


def test_t08_refused_subscription_stops(tmp_path):
    _, code = ktp.dry_run(tmp_path / "c", faults=[("refuse",)])
    assert code == 2 and manifest(tmp_path / "c")["stop_code"] == "KRAKEN_SUBSCRIBE_REFUSED"


def test_t08_storage_frames_and_duration_caps_stop_the_capture(tmp_path):
    _, code = ktp.dry_run(tmp_path / "s", caps={"max_storage_bytes": 200_000})
    assert code == 2 and manifest(tmp_path / "s")["stop_code"] == "BUDGET_STORAGE_EXHAUSTED"
    _, code = ktp.dry_run(tmp_path / "f", caps={"max_frames": 100})
    assert code == 2 and manifest(tmp_path / "f")["stop_code"] == "BUDGET_FRAMES_EXHAUSTED"
    _, code = ktp.dry_run(tmp_path / "d", capture_ms=ktp.MAX_SECONDS * 1000)
    assert code == 2 and manifest(tmp_path / "d")["stop_code"].startswith("BUDGET_DURATION")


def test_t08_run_is_refused_without_token_or_with_another_code_digest(tmp_path, capsys):
    digest = ktp.code_identity()["digest"]
    assert ktp.main(["run", "--out", str(tmp_path / "a"), "--code-sha256", digest,
                     "--confirm-public-collection", "yes"]) == 4
    assert ktp.main(["run", "--out", str(tmp_path / "b"), "--code-sha256", "0" * 64,
                     "--confirm-public-collection", ktp.CONFIRM_TOKEN]) == 4
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()
    assert ktp.main(["code-sha256"]) == 0
    assert digest in capsys.readouterr().out


def test_t08_preflight_identity_and_clock_are_checked(tmp_path):
    clock = ktp.FakeNsClock(ktp.DRY_RUN_START_MS)
    session = ktp.FakeKraken(clock)
    real_rest = session.rest

    def skewed(url):
        status, h, body, err = real_rest(url)
        if url == ktp.STATIC_URLS["time"]:
            body = json.dumps({"error": [], "result": {"unixtime": clock.now // 1000 + 10, "rfc1123": "x"}}).encode()
        return status, h, body, err
    session.rest = skewed
    code = ktp.TradePilot(tmp_path / "c", session, clock, evidence_kind="SYNTHETIC", watchdog_s=None).run()
    assert code == 3 and manifest(tmp_path / "c")["stop_code"] == "PREFLIGHT_KRAKEN_CLOCK"
    assert not any(e["kind"] == "ws_open" for e in events(tmp_path / "c"))  # no WebSocket before preflight


def test_t08_existing_evidence_directory_is_refused(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "x").write_text("keep")
    with pytest.raises(l3.Refused):
        ktp.dry_run(tmp_path / "c")
    assert (tmp_path / "c" / "x").read_text() == "keep"
