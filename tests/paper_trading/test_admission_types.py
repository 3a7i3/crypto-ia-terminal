"""Tests P5-01 — contrat des types d'admission (fail-closed).

Portée strictement type-level : immutabilité, distinction sémantique
entre REJECTED et MissingAdmissionVerdict, cohérence attempt↔outcome.
Les tests d'intégration fail-closed (verdict=None à l'écriture, TOCTOU
stale, absence de mutation sans attempt persisté) arrivent en P5-04.

Objectifs :
  * garantir que MissingAdmissionVerdict n'est PAS confondable avec un
    rejet stratégique — sémantiques distinctes dans le ledger scientifique ;
  * garantir que AdmissionVerdict est immuable (frozen) — pas de
    mutation post-check accidentelle ;
  * garantir que AdmissionAttempt et AdmissionOutcome sont deux
    événements séparés reliés par attempt_id (jamais un objet mutable
    unique) ;
  * garantir que make_attempt/make_outcome produisent une paire
    causalement cohérente (mêmes attempt_id, symbol, timestamps
    monotones).
"""

from __future__ import annotations

import time

import pytest

from paper_trading.admission_types import (
    AdmissionAttempt,
    AdmissionBlocker,
    AdmissionDecision,
    AdmissionLevel,
    AdmissionOutcome,
    AdmissionVerdict,
    MissingAdmissionVerdict,
    WriteResult,
    make_attempt,
    make_outcome,
)


class TestVerdictImmutability:
    """AdmissionVerdict doit être immuable — pas de mutation post-check."""

    def test_verdict_is_frozen(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=2,
            hard_max_at_check=5,
            checked_by="test",
        )
        with pytest.raises(Exception):  # FrozenInstanceError (dataclass frozen)
            v.decision = AdmissionDecision.REJECTED  # type: ignore[misc]

    def test_verdict_default_blocker_is_none(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=1,
            hard_max_at_check=5,
        )
        assert v.blocker == AdmissionBlocker.NONE


class TestMissingVerdictSemantics:
    """MissingAdmissionVerdict ne doit JAMAIS être confondable avec REJECTED."""

    def test_missing_is_exception_not_verdict(self):
        # Une exception, pas un dataclass — impossible de la manipuler
        # comme un AdmissionVerdict.decision == REJECTED.
        assert issubclass(MissingAdmissionVerdict, Exception)
        assert not issubclass(MissingAdmissionVerdict, AdmissionVerdict)

    def test_missing_carries_symbol_context(self):
        exc = MissingAdmissionVerdict("BTC/USDT", context="from test")
        assert exc.symbol == "BTC/USDT"
        assert exc.context == "from test"
        # Message doit nommer le code d'anomalie architectural
        assert "MEXC_ADMISSION_CONTRACT_MISSING" in str(exc)
        assert "BTC/USDT" in str(exc)

    def test_missing_can_be_raised_and_caught(self):
        with pytest.raises(MissingAdmissionVerdict) as excinfo:
            raise MissingAdmissionVerdict("ETH/USDT")
        assert excinfo.value.symbol == "ETH/USDT"


class TestAttemptOutcomeSeparation:
    """Attempt et Outcome sont deux événements distincts, jamais un seul mutable."""

    def test_attempt_and_outcome_are_different_classes(self):
        assert AdmissionAttempt is not AdmissionOutcome
        # Ne partagent pas d'ancêtre commun (autre que object)
        assert AdmissionAttempt.__bases__ == (object,)
        assert AdmissionOutcome.__bases__ == (object,)

    def test_attempt_is_frozen(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=1,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        with pytest.raises(Exception):  # FrozenInstanceError
            att.symbol = "OTHER"  # type: ignore[misc]

    def test_outcome_is_frozen(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=1,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=2)
        with pytest.raises(Exception):  # FrozenInstanceError
            out.n_after = 99  # type: ignore[misc]

    def test_attempt_has_event_tag_admission_attempt(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=1,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        assert att.event == "ADMISSION_ATTEMPT"

    def test_outcome_has_event_tag_admission_outcome(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=1,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="1", symbol="BTC/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=2)
        assert out.event == "ADMISSION_OUTCOME"


class TestCausalPairing:
    """make_attempt + make_outcome forment une paire causalement cohérente."""

    def test_outcome_carries_same_attempt_id(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=1,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="42", symbol="BTC/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=2)
        assert out.attempt_id == att.attempt_id

    def test_outcome_carries_same_symbol(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=0,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="1", symbol="SOL/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=1)
        assert out.symbol == att.symbol == "SOL/USDT"

    def test_attempt_id_format_is_time_sortable(self):
        """attempt_id doit trier chronologiquement — indispensable pour audit."""
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=0,
            hard_max_at_check=5,
        )
        a1 = make_attempt(v, cycle_id="1", symbol="A/USDT")
        time.sleep(1.01)  # >1s pour garantir un timestamp différent au format YYYYMMDDTHHMMSS
        a2 = make_attempt(v, cycle_id="2", symbol="B/USDT")
        assert a1.attempt_id < a2.attempt_id
        assert a1.attempt_id.startswith("adm_")
        assert a2.attempt_id.startswith("adm_")

    def test_outcome_timestamp_is_not_before_attempt(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=0,
            hard_max_at_check=5,
        )
        att = make_attempt(v, cycle_id="1", symbol="A/USDT")
        out = make_outcome(att, WriteResult.FILLED, n_after=1)
        assert out.ts >= att.ts

    def test_verdict_capture_preserved_in_attempt(self):
        v = AdmissionVerdict(
            decision=AdmissionDecision.REJECTED,
            level=AdmissionLevel.A,
            n_at_check=5,
            hard_max_at_check=5,
            blocker=AdmissionBlocker.PORTFOLIO_HARD_CEILING,
            reason="Max positions atteint",
            checked_by="evaluate_hard_portfolio_ceiling",
        )
        att = make_attempt(v, cycle_id="99", symbol="X/USDT")
        assert att.n_before == 5
        assert att.hard_max == 5
        assert att.level == AdmissionLevel.A
        assert att.decision == AdmissionDecision.REJECTED
        assert att.blocker == AdmissionBlocker.PORTFOLIO_HARD_CEILING
        assert att.reason == "Max positions atteint"
        assert att.verdict_checked_by == "evaluate_hard_portfolio_ceiling"
        assert att.cycle_id == "99"


class TestEnumSemantics:
    """Les enums encodent la sémantique architecturale, pas des strings libres."""

    def test_level_values_stable(self):
        # Persisté dans le ledger — casser ces valeurs invaliderait des ledgers historiques
        assert AdmissionLevel.OFF.value == "off"
        assert AdmissionLevel.A.value == "A"
        assert AdmissionLevel.B.value == "B"
        assert AdmissionLevel.C.value == "C"

    def test_decision_values_stable(self):
        assert AdmissionDecision.APPROVED.value == "APPROVED"
        assert AdmissionDecision.REJECTED.value == "REJECTED"

    def test_blocker_covers_expected_categories(self):
        # INV-001 (hard ceiling), INV-002 (signal), INV-003 (restore),
        # INV-004 (policy tightening), TOCTOU frontière écriture.
        values = {b.value for b in AdmissionBlocker}
        assert "NONE" in values
        assert "SIGNAL" in values
        assert "PORTFOLIO_HARD_CEILING" in values
        assert "OVER_LIMIT_RESTORED" in values
        assert "OVER_LIMIT_POLICY_TIGHTENED" in values
        assert "STALE_TOCTOU" in values

    def test_write_result_covers_expected_outcomes(self):
        values = {w.value for w in WriteResult}
        assert "FILLED" in values
        assert "REJECTED_DUPLICATE" in values
        assert "REJECTED_INSUFFICIENT_CAPITAL" in values
        assert "REJECTED_STALE" in values
        assert "REJECTED_ADMISSION" in values
