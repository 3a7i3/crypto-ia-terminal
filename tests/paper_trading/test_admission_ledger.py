"""Tests P5-02 — ledger append-only des admissions.

Vérifie que le journal :
  * est append-only (jamais de mutation d'une ligne),
  * distingue clairement ATTEMPT et OUTCOME,
  * relie causalement les deux événements par attempt_id,
  * ordonne chronologiquement les paires (attempt_id triable),
  * tolère les lignes malformées (audit robuste),
  * respecte l'env var ``PAPER_ADMISSION_LEDGER`` isolée par test,
  * ne décide rien — il observe et prouve.
"""

from __future__ import annotations

import json

import pytest

from paper_trading.admission_ledger import (
    AdmissionLedger,
    get_admission_ledger,
    reset_admission_ledger_singleton,
)
from paper_trading.admission_types import (
    AdmissionBlocker,
    AdmissionDecision,
    AdmissionLevel,
    AdmissionVerdict,
    WriteResult,
    make_attempt,
    make_outcome,
)


@pytest.fixture(autouse=True)
def isolate_admission_ledger(tmp_path, monkeypatch):
    """Chaque test reçoit un ledger dédié — jamais d'écriture croisée."""
    p = tmp_path / "admission_ledger_test.jsonl"
    monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(p))
    reset_admission_ledger_singleton()
    yield p
    reset_admission_ledger_singleton()


def _make_verdict(
    decision=AdmissionDecision.APPROVED,
    n=1,
    max_=5,
    blocker=AdmissionBlocker.NONE,
    reason="",
) -> AdmissionVerdict:
    return AdmissionVerdict(
        decision=decision,
        level=AdmissionLevel.A,
        n_at_check=n,
        hard_max_at_check=max_,
        blocker=blocker,
        reason=reason,
        checked_by="test",
    )


class TestAppendSemantics:
    def test_attempt_appends_one_line_with_correct_event(
        self, isolate_admission_ledger
    ):
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        ledger.record_attempt(att)

        raw = isolate_admission_ledger.read_text(encoding="utf-8").strip().splitlines()
        assert len(raw) == 1
        obj = json.loads(raw[0])
        assert obj["event"] == "ADMISSION_ATTEMPT"
        assert obj["attempt_id"] == att.attempt_id
        assert obj["symbol"] == "BTC/USDT"

    def test_outcome_appends_one_line_with_correct_event(
        self, isolate_admission_ledger
    ):
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=2, position_identity="BTC/USDT#abc")
        ledger.record_outcome(out)

        raw = isolate_admission_ledger.read_text(encoding="utf-8").strip().splitlines()
        assert len(raw) == 1
        obj = json.loads(raw[0])
        assert obj["event"] == "ADMISSION_OUTCOME"
        assert obj["attempt_id"] == att.attempt_id
        assert obj["write_result"] == "FILLED"
        assert obj["position_identity"] == "BTC/USDT#abc"

    def test_multiple_events_append_in_call_order(self, isolate_admission_ledger):
        ledger = AdmissionLedger()
        v = _make_verdict()
        a1 = make_attempt(v, cycle_id="1", symbol="A/USDT")
        a2 = make_attempt(v, cycle_id="2", symbol="B/USDT")
        o1 = make_outcome(a1, WriteResult.FILLED, n_after=1)
        ledger.record_attempt(a1)
        ledger.record_attempt(a2)
        ledger.record_outcome(o1)

        lines = isolate_admission_ledger.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["symbol"] == "A/USDT"
        assert json.loads(lines[1])["symbol"] == "B/USDT"
        assert json.loads(lines[2])["event"] == "ADMISSION_OUTCOME"

    def test_append_only_never_rewrites_existing_lines(self, isolate_admission_ledger):
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="X/USDT")
        ledger.record_attempt(att)
        first_bytes = isolate_admission_ledger.read_bytes()

        # Deuxième écriture — la première ligne doit rester intacte
        att2 = make_attempt(v, cycle_id="2", symbol="Y/USDT")
        ledger.record_attempt(att2)
        after_bytes = isolate_admission_ledger.read_bytes()
        assert after_bytes.startswith(first_bytes)


class TestCausalPairing:
    def test_pairs_matches_attempt_with_outcome(self, isolate_admission_ledger):
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=2)
        ledger.record_attempt(att)
        ledger.record_outcome(out)

        pairs = ledger.pairs()
        assert len(pairs) == 1
        a, o = pairs[0]
        assert a["attempt_id"] == att.attempt_id
        assert o is not None
        assert o["attempt_id"] == att.attempt_id

    def test_pairs_returns_none_outcome_for_orphan_attempt(
        self, isolate_admission_ledger
    ):
        """Un attempt sans outcome = signal d'écriture avortée avant journalisation."""
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="Z/USDT")
        ledger.record_attempt(att)

        pairs = ledger.pairs()
        assert len(pairs) == 1
        a, o = pairs[0]
        assert a["attempt_id"] == att.attempt_id
        assert o is None

    def test_pairs_ordered_chronologically_by_attempt_id(
        self, isolate_admission_ledger
    ):
        import time as _t

        ledger = AdmissionLedger()
        v = _make_verdict()
        a1 = make_attempt(v, cycle_id="1", symbol="A/USDT")
        _t.sleep(1.01)
        a2 = make_attempt(v, cycle_id="2", symbol="B/USDT")
        # Écriture DANS L'ORDRE INVERSE — les pairs doivent quand même trier par attempt_id
        ledger.record_attempt(a2)
        ledger.record_attempt(a1)

        pairs = ledger.pairs()
        assert [p[0]["symbol"] for p in pairs] == ["A/USDT", "B/USDT"]

    def test_pairs_correctly_matches_when_events_interleaved(
        self, isolate_admission_ledger
    ):
        import time as _t

        ledger = AdmissionLedger()
        v = _make_verdict()
        a1 = make_attempt(v, cycle_id="1", symbol="A/USDT")
        _t.sleep(1.01)
        a2 = make_attempt(v, cycle_id="2", symbol="B/USDT")
        o1 = make_outcome(a1, WriteResult.FILLED, n_after=1)
        o2 = make_outcome(a2, WriteResult.REJECTED_ADMISSION, n_after=1)
        # Interleaved
        ledger.record_attempt(a1)
        ledger.record_attempt(a2)
        ledger.record_outcome(o2)
        ledger.record_outcome(o1)

        pairs = ledger.pairs()
        by_symbol = {p[0]["symbol"]: p for p in pairs}
        assert by_symbol["A/USDT"][1]["write_result"] == "FILLED"
        assert by_symbol["B/USDT"][1]["write_result"] == "REJECTED_ADMISSION"


class TestRobustness:
    def test_read_tolerates_malformed_lines(self, isolate_admission_ledger):
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="X/USDT")
        ledger.record_attempt(att)
        # Injection d'une ligne pourrie entre deux valides
        with isolate_admission_ledger.open("a", encoding="utf-8") as f:
            f.write("this is not json\n")
            f.write("{ oops not closed\n")
        att2 = make_attempt(v, cycle_id="2", symbol="Y/USDT")
        ledger.record_attempt(att2)

        events = ledger.events()
        assert len(events) == 2  # les lignes pourries sont sautées
        assert {e["symbol"] for e in events} == {"X/USDT", "Y/USDT"}

    def test_empty_ledger_returns_empty_lists(self, isolate_admission_ledger):
        ledger = AdmissionLedger()
        assert ledger.events() == []
        assert ledger.pairs() == []

    def test_parent_directory_is_created(self, tmp_path, monkeypatch):
        deep = tmp_path / "nested" / "sub" / "adm.jsonl"
        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(deep))
        reset_admission_ledger_singleton()
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="A/USDT")
        ledger.record_attempt(att)
        assert deep.exists()


class TestEnvVarIsolation:
    def test_env_var_overrides_default_path(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom_admission.jsonl"
        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(custom))
        reset_admission_ledger_singleton()
        ledger = AdmissionLedger()
        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="Q/USDT")
        ledger.record_attempt(att)
        assert custom.exists()
        assert '"symbol": "Q/USDT"' in custom.read_text(encoding="utf-8")

    def test_singleton_reset_hook_picks_up_new_env(self, tmp_path, monkeypatch):
        p1 = tmp_path / "one.jsonl"
        p2 = tmp_path / "two.jsonl"
        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(p1))
        reset_admission_ledger_singleton()
        _ = get_admission_ledger()

        monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(p2))
        reset_admission_ledger_singleton()
        ledger2 = get_admission_ledger()

        v = _make_verdict()
        att = make_attempt(v, cycle_id="1", symbol="R/USDT")
        ledger2.record_attempt(att)
        assert p2.exists()
        assert not p1.exists()


class TestObservationOnly:
    """Le ledger ne doit contenir aucune logique de décision."""

    def test_ledger_has_no_decide_or_approve_method(self):
        forbidden = {"decide", "approve", "reject", "authorize", "block", "check"}
        methods = {
            name
            for name in dir(AdmissionLedger)
            if not name.startswith("_")
        }
        overlap = methods & forbidden
        assert not overlap, (
            f"AdmissionLedger doit rester passif — méthodes suspectes: {overlap}"
        )
