"""Groupe D — contrôle manuel (R0-D), par la vraie CLI dans un processus séparé."""
import json

from tests.radar_selection._helpers import cli, ev, tree


def _prefs(state):
    return json.loads((state / "preferences.json").read_text(encoding="utf-8"))


def _export(tmp_path, state, fixture="gaps"):
    code, out, _ = cli(["--fixture", fixture, "--state-dir", str(state), "export"], tmp_path)
    assert code == 0
    return json.loads(out)


def test_D01_valid_manual_selection(tmp_path):
    state = tmp_path / "state"
    code, out, err = cli(["--fixture", "gaps", "--state-dir", str(state), "select", "kraken:spot:SOL/USDT"], tmp_path)
    assert code == 0, err
    assert "SELECT enregistré" in out
    assert "A_QUALIFIER — NON présenté comme admissible" in out
    assert _prefs(state)["selected"] == ["kraken:spot:SOL/USDT"]
    e = _export(tmp_path, state)
    item = e["manual"]["selected"][0]
    assert item == {"market_id": "kraken:spot:SOL/USDT", "present": True, "decision": "A_QUALIFIER",
                    "presented_as_admissible": False, "note": "MANUAL_CHOICE_DOES_NOT_AUTHORIZE_COLLECTION"}
    code, out, _ = cli(["--fixture", "gaps", "--state-dir", str(state), "status"], tmp_path)
    assert "Sélection manuelle : kraken:spot:SOL/USDT\n   NON présenté comme admissible (A_QUALIFIER)" in out


def test_D02_unknown_instrument_refused(tmp_path):
    state = tmp_path / "state"
    code, out, err = cli(["--fixture", "gaps", "--state-dir", str(state), "select", "kraken:spot:NOPE/USDT"], tmp_path)
    assert code == 2 and "UNKNOWN_MARKET" in err and out == ""
    assert not (state / "preferences.json").exists()


def test_D03_unauthorised_instrument_refused(tmp_path):
    state = tmp_path / "state"
    for action in ("select", "pin"):
        code, _, err = cli(["--fixture", "gaps", "--state-dir", str(state), action, "kraken:spot:USDC/USDT"], tmp_path)
        assert code == 2 and "MARKET_NOT_AUTHORIZED:ASSET_CLASS_NOT_AUTHORIZED" in err
    assert not (state / "preferences.json").exists()


def test_D04_manual_exclusion_respected(tmp_path):
    state = tmp_path / "state"
    before = ev("gaps")
    top = before["candidates"][0]["market_id"]
    code, out, _ = cli(["--fixture", "gaps", "--state-dir", str(state), "exclude", top], tmp_path)
    assert code == 0
    after = _export(tmp_path, state)
    assert top not in [x["market_id"] for x in after["candidates"]]
    assert len(after["candidates"]) == len(before["candidates"])
    m = next(m for m in after["markets"] if m["market_id"] == top)
    assert m["manual"]["excluded"] is True and m["admissibility"]["decision"] == "ADMISSIBLE"
    assert after["counts"]["manually_excluded"] == 1


def test_D05_reset_restores_defaults(tmp_path):
    state = tmp_path / "state"
    base = ev("gaps")
    for args in (["exclude", base["candidates"][0]["market_id"]], ["pin", "mexc:spot:ETH/USDT"],
                 ["select", "kraken:spot:BTC/USD"]):
        assert cli(["--fixture", "gaps", "--state-dir", str(state), *args], tmp_path)[0] == 0
    assert cli(["--fixture", "gaps", "--state-dir", str(state), "reset"], tmp_path)[0] == 0
    prefs = _prefs(state)
    assert (prefs["selected"], prefs["pinned"], prefs["excluded"]) == ([], [], [])
    assert prefs["seq"] == 4 and [x["action"] for x in prefs["log"]] == ["exclude", "pin", "select", "reset"]
    after = _export(tmp_path, state)
    assert after["candidates"] == base["candidates"]


def test_D06_pinned_kept_without_bypassing_gates(tmp_path):
    state = tmp_path / "state"
    mid = "kraken:spot:BTC/USD"   # A_QUALIFIER (continuity partial)
    assert cli(["--fixture", "gaps", "--state-dir", str(state), "pin", mid], tmp_path)[0] == 0
    e = _export(tmp_path, state)
    m = next(m for m in e["markets"] if m["market_id"] == mid)
    assert m["manual"]["pinned"] is True
    assert m["admissibility"]["decision"] == "A_QUALIFIER" and m["score"] is None
    assert mid not in [x["market_id"] for x in e["candidates"]]
    assert e["manual"]["pinned"][0]["presented_as_admissible"] is False


def test_D07_selection_starts_no_collection(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    state = work / "state"
    before_cwd = tree(tmp_path)
    code, _, _ = cli(["--fixture", "gaps", "--state-dir", str(state), "select", "mexc:spot:SOL/USDT"], work)
    assert code == 0
    assert sorted(p.name for p in state.iterdir()) == ["preferences.json"]
    assert {k: v for k, v in tree(tmp_path).items() if not k.startswith("work/state/")} == before_cwd
    e = _export(work, state)
    assert e["deep_observation_jobs"] == []
    assert e["mode"]["l2_collection"] == "DISABLED" and e["authority"]["collection_authority"] is False
