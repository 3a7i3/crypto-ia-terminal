"""Groupe F — terminal. Rendu en processus (sans garde) et CLI réelle en sous-processus."""
import json
import re

import pytest

from tests.radar_selection._helpers import NAMES, cli, ev, session

MARKETS_TO_SHOW = ("kraken:spot:BTC/USDT", "mexc:perp:BTC/USDT", "kraken:spot:ADA/USDT")
SCREENS = [["status"], ["universe"], ["candidates"], ["help"],
           *[["inspect", m] for m in MARKETS_TO_SHOW], *[["evidence", m] for m in MARKETS_TO_SHOW]]


def _render(name, width, argv):
    code, text = session(name, width).run(argv)
    assert code == 0
    return text


def _lines_fit(text, width):
    bad = [line for line in text.splitlines() if len(line) > width]
    assert not bad, bad[:3]


@pytest.mark.parametrize("name", NAMES)
def test_F01_readable_on_80_columns(name):
    for argv in SCREENS:
        if argv[0] in ("inspect", "evidence") and argv[1] not in {m["market_id"] for m in ev(name)["markets"]}:
            continue
        _lines_fit(_render(name, 80, argv), 80)


@pytest.mark.parametrize("name", NAMES)
def test_F02_usable_on_48_columns_without_critical_truncation(name):
    e = ev(name)
    status = _render(name, 48, ["status"])
    _lines_fit(status, 48)
    lines = status.splitlines()
    for x in e["candidates"]:
        assert any(line.strip().endswith(x["market_id"]) for line in lines), x["market_id"]
    for key in ("NETWORK: DISABLED", "L2 COLLECTION: DISABLED", "PAPER: DISABLED", "MODE: SYNTHETIC / OFFLINE"):
        assert key in lines
    for argv in SCREENS:
        if argv[0] in ("inspect", "evidence") and argv[1] not in {m["market_id"] for m in e["markets"]}:
            continue
        _lines_fit(_render(name, 48, argv), 48)
    # Exact values stay available: the full dataset digest is printed by `evidence`.
    ev_text = _render(name, 48, ["evidence", "kraken:spot:BTC/USDT"])
    assert e["dataset"]["sha256"] in ev_text.replace("\n", "").replace(" ", "")


def test_F03_non_interactive_commands_are_testable(tmp_path):
    state = tmp_path / "state"
    script = "status\ncandidates\ninspect mexc:spot:SOL/USDT\nselect mexc:spot:SOL/USDT\nhistory\nquit\n"
    rc, out, err = cli(["--fixture", "calm", "--state-dir", str(state), "shell"], tmp_path, stdin=script.encode())
    assert rc == 0, err
    assert out.count("CAT MARKET INTELLIGENCE") == 3
    assert "SELECT enregistré" in out and "HISTORIQUE (BORNÉ À 20)" in out
    assert "radar>" not in out  # no prompt when stdin is not a terminal
    rc, out, err = cli(["--fixture", "calm", "shell"], tmp_path, stdin=b"bogus\nquit\n")
    assert rc == 4 and "UNKNOWN_COMMAND:bogus" in err
    for argv in (["status"], ["universe", "--venue", "mexc", "--type", "perpetual"], ["candidates"], ["help"]):
        rc, out, err = cli(["--fixture", "calm", *argv], tmp_path)
        assert rc == 0 and out, (argv, err)


def test_F04_synthetic_and_offline_status_visible():
    for argv in (["status"], ["universe"], ["candidates"], ["inspect", "kraken:spot:BTC/USDT"],
                 ["evidence", "kraken:spot:BTC/USDT"]):
        text = _render("calm", 80, argv)
        assert "MODE: SYNTHETIC / OFFLINE" in text and "NETWORK: DISABLED" in text
        assert "LIVE" not in text.replace("aucune valeur LIVE", "")  # only the disclaimer mentions LIVE


def test_F05_evidence_and_unknown_reasons_shown():
    text = _render("gaps", 80, ["evidence", "kraken:spot:ADA/USDT"])
    assert "UNKNOWN ET MOTIFS" in text and "BBO_NOT_PROVIDED" in text and "L2_NOT_PROVIDED" in text
    assert "SYN:R0-SYN-03-ACTIVE-GAPS:kraken:SPOT:ADAUSDT" in text
    text = _render("gaps", 80, ["evidence", "kraken:spot:DOGE/USDT"])
    assert "absente (NO_OBSERVATION)" in text
    inspect = _render("gaps", 80, ["inspect", "kraken:spot:ATOM/USDT"])
    assert "TIMESTAMP_MISSING" in inspect and "Score: non calculé" in inspect
    for label in ("1. Qualité L2", "2. Continuité", "3. Spread et profondeur", "4. Activité et volatilité",
                  "5. Coût de collecte", "6. Diversité"):
        assert label in inspect


def test_F06_no_mandatory_horizontal_columns():
    for name in NAMES:
        for argv in (["status"], ["universe"], ["candidates"]):
            text = _render(name, 80, argv)
            assert "\t" not in text and "+---" not in text
            assert not re.search(r"\S {3,}\S", text), argv


def test_F07_clean_exit(tmp_path):
    state = tmp_path / "state"
    rc, out, err = cli(["--fixture", "calm", "--state-dir", str(state), "shell"], tmp_path,
                       stdin=b"exclude mexc:spot:SOL/USDT\npin kraken:spot:BTC/USD\nquit\nstatus\n")
    assert rc == 0, err
    assert out.rstrip().endswith("rien en cours.")
    assert out.count("CAT MARKET INTELLIGENCE") == 0  # 'status' after quit is never run
    prefs = json.loads((state / "preferences.json").read_text())
    assert prefs["excluded"] == ["mexc:spot:SOL/USDT"] and prefs["pinned"] == ["kraken:spot:BTC/USD"]
    assert sorted(p.name for p in state.iterdir()) == ["preferences.json"]  # no temp file left
    rc, out, _ = cli(["--fixture", "calm", "shell"], tmp_path, stdin=b"status\n")  # EOF without quit
    assert rc == 0 and out.rstrip().endswith("rien en cours.")


def test_F08_no_sensitive_data_displayed(tmp_path):
    state = tmp_path / "state"
    outputs = []
    for name in NAMES:
        for argv in (["status"], ["universe"], ["candidates"], ["scan"], ["history"],
                     ["evidence", "kraken:spot:BTC/USDT"]):
            rc, out, err = cli(["--fixture", name, "--state-dir", str(state), *argv], tmp_path)
            assert rc == 0, err
            outputs.append(out + err)
    text = "\n".join(outputs)
    assert str(tmp_path) not in text
    for pattern in (r"[\w.+-]+@[\w-]+\.[\w.]+", r"/home/", r"/root", r"(?i)secret", r"(?i)api[_-]?key",
                    r"(?i)password", r"(?i)token", r"(?i)bearer"):
        assert not re.search(pattern, text), pattern
