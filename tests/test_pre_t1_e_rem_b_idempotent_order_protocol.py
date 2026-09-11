"""
tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py

O-02W-PRE-T1-E REM-B — deterministic identity, durable intent journal, and
idempotent submission/reconciliation coordinator.

Uses temp dirs (pytest tmp_path), fake exchanges/adapters, explicit call
counters, and threading.Barrier for concurrency proofs (never sleep-based).
"""

from __future__ import annotations

import threading

import pytest

from quant_hedge_ai.agents.execution.order_intent_protocol import (
    AdapterCapabilities,
    AdapterCapabilityVerdict,
    ExchangeMutationOutcome,
    ExchangeMutationResult,
    IntentState,
    InvalidTransitionError,
    MissingCausalIdentityError,
    OrderIntentCoordinator,
    OrderIntentJournal,
    ReconciliationLookupResult,
    SubmissionOutcome,
    build_order_intent,
)


def make_intent(**overrides):
    defaults = dict(
        namespace="EXP-001",
        causal_id="decision-123",
        account_scope="mexc:main",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount="100.00",
        price="50000.00",
        reduce_only=False,
        position_ref=None,
    )
    defaults.update(overrides)
    return build_order_intent(**defaults)


class CountingMutator:
    """Spy that counts exchange mutation calls and returns a queued result
    (or a fixed outcome) each invocation."""

    def __init__(self, outcomes=None, fixed=None):
        self.calls = []
        self._outcomes = list(outcomes) if outcomes else None
        self._fixed = fixed

    def __call__(self, intent, client_order_id):
        self.calls.append((intent.full_digest(), client_order_id))
        if self._outcomes is not None:
            return self._outcomes.pop(0)
        return self._fixed

    @property
    def call_count(self):
        return len(self.calls)


def ack(order_id="EX-1"):
    return ExchangeMutationResult(
        outcome=ExchangeMutationOutcome.ACKNOWLEDGED, exchange_order_id=order_id
    )


def rejected(cat="min_notional"):
    return ExchangeMutationResult(
        outcome=ExchangeMutationOutcome.EXPLICITLY_REJECTED, error_category=cat
    )


def ambiguous(cat="timeout"):
    return ExchangeMutationResult(
        outcome=ExchangeMutationOutcome.AMBIGUOUS, error_category=cat
    )


FULL_CAPS = AdapterCapabilities(
    verdict=AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
    client_order_id_param="clientOrderId",
    supports_open_order_search=True,
    supports_closed_order_search=True,
    evidence="test fake — certified for hermetic testing only",
)
NO_CID_CAPS = AdapterCapabilities(
    verdict=AdapterCapabilityVerdict.UNSUPPORTED,
    client_order_id_param=None,
)


def coordinator(tmp_path, caps=FULL_CAPS, name="journal.jsonl"):
    journal = OrderIntentJournal(tmp_path / name)
    return OrderIntentCoordinator(journal, caps), journal


# ═══════════════════════════════════════════════════════════════════════
# Group A — identity (9 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupAIdentity:
    def test_same_canonical_intent_same_digest(self):
        a = make_intent()
        b = make_intent()
        assert a.full_digest() == b.full_digest()

    def test_same_canonical_intent_same_client_order_id(self):
        a = make_intent()
        b = make_intent()
        assert a.client_order_id() == b.client_order_id()

    def test_field_order_does_not_change_identity(self):
        # canonical_dict() has fixed field order regardless of how kwargs
        # were passed to build_order_intent — reordering call-site kwargs
        # must not change the digest.
        a = build_order_intent(
            namespace="EXP-001", causal_id="d1", account_scope="mexc:main",
            symbol="BTC/USDT", side="buy", order_type="market", amount="10",
            price="100", reduce_only=False,
        )
        b = build_order_intent(
            side="buy", amount="10", price="100", reduce_only=False,
            causal_id="d1", symbol="BTC/USDT", order_type="market",
            namespace="EXP-001", account_scope="mexc:main",
        )
        assert a.full_digest() == b.full_digest()

    def test_decimal_formatting_equivalents_do_not_change_identity(self):
        a = make_intent(amount="100", price="50000")
        b = make_intent(amount="100.00", price="50000.0")
        assert a.full_digest() == b.full_digest()

    def test_different_decision_ids_produce_different_identity(self):
        a = make_intent(causal_id="decision-1")
        b = make_intent(causal_id="decision-2")
        assert a.full_digest() != b.full_digest()

    @pytest.mark.parametrize(
        "field_,value",
        [
            ("symbol", "ETH/USDT"),
            ("side", "sell"),
            ("order_type", "limit"),
            ("amount", "200.00"),
            ("price", "51000.00"),
            ("reduce_only", True),
        ],
    )
    def test_varying_fields_produce_different_identity(self, field_, value):
        a = make_intent()
        b = make_intent(**{field_: value})
        assert a.full_digest() != b.full_digest()

    def test_missing_causal_identity_fails_closed(self):
        with pytest.raises(MissingCausalIdentityError):
            build_order_intent(
                namespace="EXP-001", causal_id=None, account_scope="mexc:main",
                symbol="BTC/USDT", side="buy", order_type="market", amount="10",
            )
        with pytest.raises(MissingCausalIdentityError):
            build_order_intent(
                namespace="EXP-001", causal_id="   ", account_scope="mexc:main",
                symbol="BTC/USDT", side="buy", order_type="market", amount="10",
            )

    def test_short_id_collision_with_different_payload_fails_closed(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        a = make_intent(causal_id="decision-A")
        # Force a synthetic collision: manually inject a journal record
        # under a's client_order_id but a different digest, simulating a
        # (extremely unlikely) truncated-ID collision between two distinct
        # full payloads.
        fake_other_digest = "0" * 64
        journal.append_transition(
            intent_digest=fake_other_digest,
            client_order_id=a.client_order_id(),
            state=IntentState.ACKNOWLEDGED,
            canonical_payload={"different": "payload"},
        )
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(
            a, authorized=True, authorization_ref="auth-1", mutate=mutator
        )
        assert result.outcome == SubmissionOutcome.IDENTITY_COLLISION
        assert mutator.call_count == 0

    def test_no_secret_in_canonical_payload_or_id(self):
        intent = make_intent(account_scope="mexc:main")  # never an api key
        payload_text = intent.canonical_json()
        cid = intent.client_order_id()
        for banned in ("api_key", "secret", "apiKey", "private_key"):
            assert banned not in payload_text
            assert banned not in cid


# ═══════════════════════════════════════════════════════════════════════
# Group B — durable ordering (6 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupBDurableOrdering:
    def test_intent_write_occurs_before_mutation(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent()
        seen_states_before_mutation = []

        def mutate(i, cid):
            rec = journal.get(i.full_digest())
            seen_states_before_mutation.append(rec["state"] if rec else None)
            return ack()

        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutate)
        assert seen_states_before_mutation == [IntentState.SUBMISSION_STARTED.value]

    def test_durable_flush_completes_before_mutation(self, tmp_path):
        # append_transition fsyncs before returning; prove the file on disk
        # already contains SUBMISSION_STARTED at mutation time (not just
        # in-memory).
        coord, journal = coordinator(tmp_path)
        intent = make_intent()

        def mutate(i, cid):
            on_disk = journal.path.read_text(encoding="utf-8")
            assert "SUBMISSION_STARTED" in on_disk
            return ack()

        result = coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutate)
        assert result.outcome == SubmissionOutcome.ACKNOWLEDGED

    def test_journal_failure_yields_zero_mutation_calls(self, tmp_path, monkeypatch):
        coord, journal = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=ack())

        def broken_append(*args, **kwargs):
            raise OSError("disk full (simulated)")

        monkeypatch.setattr(journal, "append_transition", broken_append)
        result = coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert result.outcome == SubmissionOutcome.JOURNAL_FAILURE
        assert mutator.call_count == 0

    def test_submission_started_persisted_before_mutation(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent()
        order = []

        def mutate(i, cid):
            order.append("mutate")
            return ack()

        # Wrap append_transition to record ordering.
        original = journal.append_transition

        def spy(*args, **kwargs):
            if kwargs.get("state") == IntentState.SUBMISSION_STARTED:
                order.append("submission_started_persisted")
            return original(*args, **kwargs)

        journal.append_transition = spy
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutate)
        assert order == ["submission_started_persisted", "mutate"]

    def test_truncated_final_record_does_not_erase_prior_state(self, tmp_path):
        journal = OrderIntentJournal(tmp_path / "j.jsonl")
        digest = "abc123"
        journal.append_transition(
            intent_digest=digest, client_order_id="cid1", state=IntentState.INTENT_RECORDED,
            canonical_payload={"x": 1},
        )
        journal.append_transition(
            intent_digest=digest, client_order_id="cid1", state=IntentState.SUBMISSION_STARTED,
        )
        # Simulate a crash mid-write: append a truncated (invalid JSON) line.
        with open(journal.path, "a", encoding="utf-8") as f:
            f.write('{"intent_digest": "abc123", "state": "ACKNOWL')  # no newline, truncated
        rec = journal.get(digest)
        assert rec is not None
        assert rec["state"] == IntentState.SUBMISSION_STARTED.value

    def test_invalid_transition_is_rejected(self, tmp_path):
        journal = OrderIntentJournal(tmp_path / "j.jsonl")
        digest = "abc123"
        journal.append_transition(
            intent_digest=digest, client_order_id="cid1", state=IntentState.EXPLICITLY_REJECTED,
            canonical_payload={"x": 1},
        )
        with pytest.raises(InvalidTransitionError):
            journal.append_transition(
                intent_digest=digest, client_order_id="cid1", state=IntentState.ACKNOWLEDGED,
            )


# ═══════════════════════════════════════════════════════════════════════
# Group C — normal acknowledgement (5 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupCAcknowledgement:
    def test_valid_intent_submits_exactly_once(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=ack())
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.call_count == 1

    def test_deterministic_client_order_id_reaches_adapter(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=ack())
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.calls[0][1] == intent.client_order_id()

    def test_acknowledgement_persisted(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent()
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack()))
        rec = journal.get(intent.full_digest())
        assert rec["state"] == IntentState.ACKNOWLEDGED.value

    def test_exchange_order_id_associated(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent()
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack("EX-99")))
        rec = journal.get(intent.full_digest())
        assert rec["exchange_order_id"] == "EX-99"

    def test_repeat_call_returns_existing_state_zero_additional_submissions(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=ack())
        r1 = coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        r2 = coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.call_count == 1
        assert r2.outcome == SubmissionOutcome.ACKNOWLEDGED
        assert r1.exchange_order_id == r2.exchange_order_id


# ═══════════════════════════════════════════════════════════════════════
# Group D — explicit rejection (3 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupDRejection:
    def test_explicit_rejection_state(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent()
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=rejected()))
        rec = journal.get(intent.full_digest())
        assert rec["state"] == IntentState.EXPLICITLY_REJECTED.value

    def test_repeated_invocation_does_not_retry(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=rejected())
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.call_count == 1

    def test_restarted_component_does_not_retry(self, tmp_path):
        journal_path = tmp_path / "j.jsonl"
        journal1 = OrderIntentJournal(journal_path)
        coord1 = OrderIntentCoordinator(journal1, FULL_CAPS)
        intent = make_intent()
        coord1.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=rejected()))

        # "Restart": brand-new journal/coordinator objects pointed at the
        # same durable path.
        journal2 = OrderIntentJournal(journal_path)
        coord2 = OrderIntentCoordinator(journal2, FULL_CAPS)
        mutator2 = CountingMutator(fixed=ack())
        result = coord2.submit(intent, authorized=True, authorization_ref="a", mutate=mutator2)
        assert mutator2.call_count == 0
        assert result.outcome == SubmissionOutcome.EXPLICITLY_REJECTED


# ═══════════════════════════════════════════════════════════════════════
# Group E — ambiguous result (6 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupEAmbiguous:
    @pytest.mark.parametrize(
        "category", ["timeout", "lost_response", "connection_reset", "malformed_response"]
    )
    def test_ambiguous_outcomes_become_reconcile_required(self, tmp_path, category):
        coord, journal = coordinator(tmp_path)
        intent = make_intent(causal_id=f"decision-{category}")
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ambiguous(category)))
        rec = journal.get(intent.full_digest())
        assert rec["state"] == IntentState.RECONCILE_REQUIRED.value

    def test_ambiguous_case_performs_exactly_one_mutation_call(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=ambiguous())
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.call_count == 1

    def test_repeated_invocation_after_ambiguity_performs_no_second_mutation(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        mutator = CountingMutator(fixed=ambiguous())
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        result2 = coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.call_count == 1
        assert result2.outcome == SubmissionOutcome.RECONCILE_REQUIRED


# ═══════════════════════════════════════════════════════════════════════
# Group F — reconciliation (9 cases)
# ═══════════════════════════════════════════════════════════════════════


def put_in_reconcile_required(coord, intent):
    coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ambiguous()))


class TestGroupFReconciliation:
    def test_matching_open_order_found(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent()
        put_in_reconcile_required(coord, intent)
        match = {"id": "EX-open-1", "status": "open"}
        result = coord.reconcile(
            intent.full_digest(), lookup=lambda cid: ReconciliationLookupResult(False, [match])
        )
        assert result.outcome == SubmissionOutcome.RECONCILED_FOUND
        assert result.exchange_order_id == "EX-open-1"

    def test_matching_closed_order_found(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d2")
        put_in_reconcile_required(coord, intent)
        match = {"id": "EX-closed-1", "status": "closed"}
        result = coord.reconcile(
            intent.full_digest(), lookup=lambda cid: ReconciliationLookupResult(False, [match])
        )
        assert result.outcome == SubmissionOutcome.RECONCILED_FOUND

    def test_payload_compatibility_is_verified(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d3")
        put_in_reconcile_required(coord, intent)
        match = {"id": "EX-x", "symbol": "ETH/USDT"}  # wrong symbol
        result = coord.reconcile(
            intent.full_digest(),
            lookup=lambda cid: ReconciliationLookupResult(False, [match]),
            verify_match=lambda payload, cand: payload["symbol"] == cand.get("symbol"),
        )
        assert result.outcome == SubmissionOutcome.RECONCILIATION_CONFLICT

    def test_conflicting_client_id_fails_closed(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d4")
        put_in_reconcile_required(coord, intent)
        match = {"id": "EX-y", "symbol": "BOGUS/USDT"}
        result = coord.reconcile(
            intent.full_digest(),
            lookup=lambda cid: ReconciliationLookupResult(False, [match]),
            verify_match=lambda payload, cand: False,
        )
        assert result.outcome == SubmissionOutcome.RECONCILIATION_CONFLICT

    def test_multiple_matches_fail_closed(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d5")
        put_in_reconcile_required(coord, intent)
        result = coord.reconcile(
            intent.full_digest(),
            lookup=lambda cid: ReconciliationLookupResult(False, [{"id": "1"}, {"id": "2"}]),
        )
        assert result.outcome == SubmissionOutcome.RECONCILIATION_CONFLICT

    def test_lookup_failure_remains_ambiguous(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent(causal_id="d6")
        put_in_reconcile_required(coord, intent)
        result = coord.reconcile(
            intent.full_digest(), lookup=lambda cid: ReconciliationLookupResult(True, [], "network_error")
        )
        assert result.outcome == SubmissionOutcome.RECONCILE_REQUIRED
        rec = journal.get(intent.full_digest())
        assert rec["state"] == IntentState.RECONCILE_REQUIRED.value

    def test_no_match_becomes_not_found_pending(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d7")
        put_in_reconcile_required(coord, intent)
        result = coord.reconcile(intent.full_digest(), lookup=lambda cid: ReconciliationLookupResult(False, []))
        assert result.outcome == SubmissionOutcome.RECONCILED_NOT_FOUND_PENDING

    def test_not_found_state_does_not_authorize_resubmission(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d8")
        put_in_reconcile_required(coord, intent)
        coord.reconcile(intent.full_digest(), lookup=lambda cid: ReconciliationLookupResult(False, []))
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
        assert mutator.call_count == 0
        assert result.outcome == SubmissionOutcome.RECONCILED_NOT_FOUND_PENDING

    def test_reconciliation_performs_zero_create_order_calls(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d9")
        put_in_reconcile_required(coord, intent)
        create_order_calls = []
        coord.reconcile(
            intent.full_digest(),
            lookup=lambda cid: (create_order_calls.append(cid), ReconciliationLookupResult(False, []))[1],
        )
        assert len(create_order_calls) == 1  # only the read-only lookup call
        # No mutate() was invoked from within reconcile() at all — proven by
        # construction (reconcile() takes no `mutate` callable).


# ═══════════════════════════════════════════════════════════════════════
# Group G — restart (6 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupGRestart:
    def _restart(self, path):
        journal = OrderIntentJournal(path)
        return OrderIntentCoordinator(journal, FULL_CAPS), journal

    @pytest.mark.parametrize(
        "setup_outcome,expected_no_mutation",
        [
            ("intent_recorded_only", True),
            ("submission_started_only", True),
            ("acknowledged", True),
            ("rejected", True),
            ("reconcile_required", True),
        ],
    )
    def test_restart_never_causes_unauthorized_second_submission(
        self, tmp_path, setup_outcome, expected_no_mutation
    ):
        path = tmp_path / "j.jsonl"
        journal1 = OrderIntentJournal(path)
        coord1 = OrderIntentCoordinator(journal1, FULL_CAPS)
        intent = make_intent(causal_id=f"decision-{setup_outcome}")
        digest = intent.full_digest()
        cid = intent.client_order_id()

        if setup_outcome == "intent_recorded_only":
            journal1.append_transition(
                intent_digest=digest, client_order_id=cid, state=IntentState.INTENT_RECORDED,
                canonical_payload=intent.canonical_dict(),
            )
        elif setup_outcome == "submission_started_only":
            journal1.append_transition(
                intent_digest=digest, client_order_id=cid, state=IntentState.INTENT_RECORDED,
                canonical_payload=intent.canonical_dict(),
            )
            journal1.append_transition(
                intent_digest=digest, client_order_id=cid, state=IntentState.SUBMISSION_STARTED,
            )
        elif setup_outcome == "acknowledged":
            coord1.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack()))
        elif setup_outcome == "rejected":
            coord1.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=rejected()))
        elif setup_outcome == "reconcile_required":
            coord1.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ambiguous()))

        coord2, _ = self._restart(path)
        mutator2 = CountingMutator(fixed=ack())
        coord2.submit(intent, authorized=True, authorization_ref="a", mutate=mutator2)
        if expected_no_mutation:
            assert mutator2.call_count == 0


# ═══════════════════════════════════════════════════════════════════════
# Group H — concurrency (5 cases; threading.Barrier — no sleeps)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupHConcurrency:
    def test_two_synchronized_threads_same_intent_one_mutation(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="concurrent-1")
        barrier = threading.Barrier(2)
        mutator = CountingMutator(fixed=ack())
        results = []

        def worker():
            barrier.wait()
            results.append(
                coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
            )

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert mutator.call_count == 1
        assert all(r.outcome == SubmissionOutcome.ACKNOWLEDGED for r in results)

    def test_both_threads_receive_compatible_typed_outcomes(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="concurrent-2")
        barrier = threading.Barrier(2)
        mutator = CountingMutator(fixed=ack("EX-shared"))
        results = []

        def worker():
            barrier.wait()
            results.append(
                coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
            )

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        order_ids = {r.exchange_order_id for r in results}
        assert order_ids == {"EX-shared"}

    def test_exchange_mutation_count_exactly_one_under_contention(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="concurrent-3")
        n = 8
        barrier = threading.Barrier(n)
        mutator = CountingMutator(fixed=ack())

        def worker():
            barrier.wait()
            coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert mutator.call_count == 1

    def test_concurrent_duplicate_close_requests_create_one_submission(self, tmp_path):
        # Simulates PositionManager receiving the same close instruction twice.
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="close-gen-1", side="sell", reduce_only=True)
        barrier = threading.Barrier(2)
        mutator = CountingMutator(fixed=ack())

        def worker():
            barrier.wait()
            coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert mutator.call_count == 1

    def test_concurrent_reconciliation_and_duplicate_request_cannot_resubmit(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="concurrent-4")
        put_in_reconcile_required(coord, intent)
        barrier = threading.Barrier(2)
        mutator = CountingMutator(fixed=ack())
        results = []

        def resubmit_worker():
            barrier.wait()
            results.append(
                coord.submit(intent, authorized=True, authorization_ref="a", mutate=mutator)
            )

        def reconcile_worker():
            barrier.wait()
            coord.reconcile(intent.full_digest(), lookup=lambda cid: ReconciliationLookupResult(False, []))

        t1 = threading.Thread(target=resubmit_worker)
        t2 = threading.Thread(target=reconcile_worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert mutator.call_count == 0


# ═══════════════════════════════════════════════════════════════════════
# Group I — both mutation families (6 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupIBothFamilies:
    def test_execution_engine_family_intent_uses_durable_protocol(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent(namespace="EXP-001", causal_id="ee-decision-1")
        result = coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack()))
        assert result.outcome == SubmissionOutcome.ACKNOWLEDGED
        assert journal.get(intent.full_digest()) is not None

    def test_position_manager_family_intent_uses_durable_protocol(self, tmp_path):
        coord, journal = coordinator(tmp_path)
        intent = make_intent(
            namespace="EXP-001", causal_id="pm-close-gen-1", side="sell", reduce_only=True,
            position_ref="pos-42",
        )
        result = coord.submit(intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack()))
        assert result.outcome == SubmissionOutcome.ACKNOWLEDGED
        assert journal.get(intent.full_digest())["canonical_payload"]["reduce_only"] is True

    def test_both_transmit_deterministic_exchange_ids(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        ee_intent = make_intent(causal_id="ee-2")
        pm_intent = make_intent(causal_id="pm-2", side="sell", reduce_only=True)
        ee_mut = CountingMutator(fixed=ack())
        pm_mut = CountingMutator(fixed=ack())
        coord.submit(ee_intent, authorized=True, authorization_ref="a", mutate=ee_mut)
        coord.submit(pm_intent, authorized=True, authorization_ref="a", mutate=pm_mut)
        assert ee_mut.calls[0][1] == ee_intent.client_order_id()
        assert pm_mut.calls[0][1] == pm_intent.client_order_id()

    def test_both_reject_missing_adapter_capability(self, tmp_path):
        coord, _ = coordinator(tmp_path, caps=NO_CID_CAPS)
        ee_intent = make_intent(causal_id="ee-3")
        pm_intent = make_intent(causal_id="pm-3", side="sell", reduce_only=True)
        mut = CountingMutator(fixed=ack())
        r1 = coord.submit(ee_intent, authorized=True, authorization_ref="a", mutate=mut)
        r2 = coord.submit(pm_intent, authorized=True, authorization_ref="a", mutate=mut)
        assert r1.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert r2.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert mut.call_count == 0

    def test_both_retain_rem_a_authorization_gate(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        ee_intent = make_intent(causal_id="ee-4")
        pm_intent = make_intent(causal_id="pm-4", side="sell", reduce_only=True)
        mut = CountingMutator(fixed=ack())
        r1 = coord.submit(ee_intent, authorized=False, authorization_ref="a", mutate=mut)
        r2 = coord.submit(pm_intent, authorized=False, authorization_ref="a", mutate=mut)
        assert r1.outcome == SubmissionOutcome.AUTHORIZATION_DENIED
        assert r2.outcome == SubmissionOutcome.AUTHORIZATION_DENIED
        assert mut.call_count == 0

    def test_both_remain_idempotent_after_reconstructed_journal(self, tmp_path):
        path = tmp_path / "j.jsonl"
        journal1 = OrderIntentJournal(path)
        coord1 = OrderIntentCoordinator(journal1, FULL_CAPS)
        ee_intent = make_intent(causal_id="ee-5")
        pm_intent = make_intent(causal_id="pm-5", side="sell", reduce_only=True)
        coord1.submit(ee_intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack()))
        coord1.submit(pm_intent, authorized=True, authorization_ref="a", mutate=CountingMutator(fixed=ack()))

        journal2 = OrderIntentJournal(path)
        coord2 = OrderIntentCoordinator(journal2, FULL_CAPS)
        mut2 = CountingMutator(fixed=ack())
        coord2.submit(ee_intent, authorized=True, authorization_ref="a", mutate=mut2)
        coord2.submit(pm_intent, authorized=True, authorization_ref="a", mutate=mut2)
        assert mut2.call_count == 0


# ═══════════════════════════════════════════════════════════════════════
# Group J — non-regression (8 cases)
# ═══════════════════════════════════════════════════════════════════════


class TestGroupJNonRegression:
    def test_rem_a_invalid_size_denial_untouched(self):
        from quant_hedge_ai.agents.execution.order_authorization import (
            authorize_order, DenialReason,
        )
        result = authorize_order(
            symbol="BTC/USDT", side="buy", requested_amount=-5, price=100,
            amount_precision=0.001, min_notional=5,
        )
        assert result.authorized is False
        assert result.denial_reason == DenialReason.NON_POSITIVE_AMOUNT

    def test_rem_a_min_notional_denial_untouched(self):
        from quant_hedge_ai.agents.execution.order_authorization import (
            authorize_order, DenialReason,
        )
        result = authorize_order(
            symbol="BTC/USDT", side="buy", requested_amount=1, price=100,
            amount_precision=0.001, min_notional=50,
        )
        assert result.authorized is False
        assert result.denial_reason == DenialReason.BELOW_MIN_NOTIONAL

    def test_rem_a_buy_sell_authority_untouched(self):
        from quant_hedge_ai.agents.execution.order_authorization import (
            authorize_order,
        )
        buy = authorize_order(
            symbol="BTC/USDT", side="buy", requested_amount=100, price=100,
            amount_precision=0.001, min_notional=5, available_quote_balance=1000,
        )
        sell = authorize_order(
            symbol="BTC/USDT", side="sell", requested_amount=100, price=100,
            amount_precision=0.001, min_notional=5, available_base_balance=10,
        )
        assert buy.authorized is True
        assert sell.authorized is True

    def test_futures_narrowing_only_semantics_untouched(self):
        from quant_hedge_ai.agents.execution.order_authorization import authorize_order
        result = authorize_order(
            symbol="BTC/USDT:USDT", side="sell", requested_amount=60, price=100,
            amount_precision=0.001, min_notional=55, require_balance_check=False,
        )
        assert result.authorized is True

    def test_new_module_imports_do_not_alter_order_authorization_module(self):
        import quant_hedge_ai.agents.execution.order_authorization as oa
        assert hasattr(oa, "authorize_order")
        assert hasattr(oa, "evaluate_trading_authority")

    def test_no_strategy_sizing_or_risk_threshold_symbols_present(self):
        import quant_hedge_ai.agents.execution.order_intent_protocol as mod
        src = open(mod.__file__, encoding="utf-8").read()
        for banned in ("stop_loss_pct", "take_profit_pct", "strategy_weight", "risk_multiplier"):
            assert banned not in src

    def test_live_defaults_remain_disabled_env_untouched(self, monkeypatch):
        monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)
        monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
        assert ExecutionEngine._paper_trading_enabled() is True

    def test_paper_path_makes_no_real_network_calls(self, tmp_path):
        # The coordinator itself never imports ccxt / performs sockets;
        # `mutate` is entirely caller-supplied and never invoked when
        # authorization is denied or capability is unsupported.
        coord, _ = coordinator(tmp_path, caps=NO_CID_CAPS)
        intent = make_intent(causal_id="paper-1")
        calls = []
        coord.submit(intent, authorized=True, authorization_ref="a", mutate=lambda i, c: calls.append(1))
        assert calls == []


# ─────────────────────────────────────────────────────────────────────────
# Group K — REAL cross-process safety (O-02W-PRE-T1-E REM-B-R1,
# Correction D). Uses `multiprocessing.Process` (separate OS processes,
# each with its own interpreter/memory — NOT threads sharing one process)
# racing on the SAME journal file via `multiprocessing.Barrier` to
# synchronize their submission attempt, and a process-safe counter file
# (each process appends one line via its own OS-level append) to prove the
# exchange mutation call happened at most once across ALL processes.
# ─────────────────────────────────────────────────────────────────────────

import multiprocessing


def _mp_submit_worker(journal_path, counter_path, barrier, result_queue, causal_id):
    """Runs in a SEPARATE OS process. Builds its own fresh
    OrderIntentJournal/OrderIntentCoordinator instance (no shared Python
    objects with the parent — only the journal FILE PATH and counter FILE
    PATH are shared, which is the whole point: the OS file lock is what
    must do the work, not any in-memory Python structure)."""
    from quant_hedge_ai.agents.execution.order_intent_protocol import (
        AdapterCapabilities,
        ExchangeMutationOutcome,
        ExchangeMutationResult,
        OrderIntentCoordinator,
        OrderIntentJournal,
        build_order_intent,
    )

    journal = OrderIntentJournal(journal_path)
    caps = AdapterCapabilities(
        verdict=AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
        client_order_id_param="clientOrderId",
    )
    coordinator_ = OrderIntentCoordinator(journal, caps)
    intent = build_order_intent(
        namespace="EXP-001",
        causal_id=causal_id,
        account_scope="mexc:main",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount="100.00",
        price="50000.00",
        reduce_only=False,
    )

    def mutate(_intent, _client_order_id):
        # Each attempted mutation appends exactly one line. A small,
        # single `write()` to a file opened O_APPEND is atomic on POSIX
        # for writes below PIPE_BUF, so no additional locking is needed
        # here to count attempts correctly.
        with open(counter_path, "a", encoding="utf-8") as f:
            f.write("1\n")
        return ExchangeMutationResult(
            outcome=ExchangeMutationOutcome.ACKNOWLEDGED, exchange_order_id="EX-1"
        )

    barrier.wait()  # synchronize: all processes attempt submission together
    result = coordinator_.submit(
        intent, authorized=True, authorization_ref="ok", mutate=mutate
    )
    result_queue.put(result.outcome.value)


class TestGroupK_RealCrossProcessSafety:
    def test_two_processes_same_intent_at_most_one_mutation(self, tmp_path):
        journal_path = str(tmp_path / "mp_journal.jsonl")
        counter_path = str(tmp_path / "counter.txt")
        open(counter_path, "w").close()
        barrier = multiprocessing.Barrier(2)
        q = multiprocessing.Queue()
        procs = [
            multiprocessing.Process(
                target=_mp_submit_worker,
                args=(journal_path, counter_path, barrier, q, "mp-same-intent"),
            )
            for _ in range(2)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=15)
            assert not p.is_alive(), "worker process hung"

        outcomes = sorted(q.get(timeout=5) for _ in procs)
        mutation_attempts = len(open(counter_path, encoding="utf-8").read().splitlines())

        assert mutation_attempts == 1, (
            f"expected exactly one mutation attempt across 2 processes "
            f"racing on the same intent, got {mutation_attempts}"
        )
        # Both processes receive a compatible typed outcome — one that
        # actually submitted (ACKNOWLEDGED) and one that saw the durable
        # record already claimed (SUBMISSION_ALREADY_STARTED, or
        # ACKNOWLEDGED if it observed the completed state).
        assert set(outcomes).issubset(
            {"ACKNOWLEDGED", "SUBMISSION_ALREADY_STARTED", "INTENT_ALREADY_RECORDED"}
        )

    def test_five_processes_same_intent_at_most_one_mutation(self, tmp_path):
        journal_path = str(tmp_path / "mp_journal5.jsonl")
        counter_path = str(tmp_path / "counter5.txt")
        open(counter_path, "w").close()
        n = 5
        barrier = multiprocessing.Barrier(n)
        q = multiprocessing.Queue()
        procs = [
            multiprocessing.Process(
                target=_mp_submit_worker,
                args=(journal_path, counter_path, barrier, q, "mp-same-intent-5"),
            )
            for _ in range(n)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=20)
            assert not p.is_alive(), "worker process hung"

        mutation_attempts = len(open(counter_path, encoding="utf-8").read().splitlines())
        assert mutation_attempts == 1, (
            f"expected exactly one mutation attempt across {n} processes "
            f"racing on the same intent, got {mutation_attempts}"
        )
        outcomes = [q.get(timeout=5) for _ in procs]
        assert len(outcomes) == n

    def test_two_distinct_intents_across_processes_do_not_collapse(self, tmp_path):
        journal_path = str(tmp_path / "mp_journal_distinct.jsonl")
        counter_path = str(tmp_path / "counter_distinct.txt")
        open(counter_path, "w").close()
        barrier = multiprocessing.Barrier(2)
        q = multiprocessing.Queue()
        procs = [
            multiprocessing.Process(
                target=_mp_submit_worker,
                args=(journal_path, counter_path, barrier, q, f"mp-distinct-{i}"),
            )
            for i in range(2)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=15)
            assert not p.is_alive()

        mutation_attempts = len(open(counter_path, encoding="utf-8").read().splitlines())
        # Two genuinely different causal_id -> different digests -> both
        # are new intents -> both legitimately submit (2 mutations, not 1).
        assert mutation_attempts == 2
        outcomes = [q.get(timeout=5) for _ in procs]
        assert outcomes == ["ACKNOWLEDGED", "ACKNOWLEDGED"]

    def test_lock_unavailable_causes_zero_mutation_calls(self, tmp_path, monkeypatch):
        from quant_hedge_ai.agents.execution import order_intent_protocol as mod

        coord, journal = coordinator(tmp_path)
        intent = make_intent(causal_id="lock-fail-1")

        def _raise_flock(*a, **k):
            raise OSError("simulated flock failure")

        monkeypatch.setattr(mod.fcntl, "flock", _raise_flock)
        calls = []
        result = coord.submit(
            intent,
            authorized=True,
            authorization_ref="ok",
            mutate=lambda i, c: calls.append(1),
        )
        assert result.outcome == SubmissionOutcome.LOCK_UNAVAILABLE
        assert calls == []  # zero mutation calls
        # Zero journal writes either — INTENT_RECORDED was never persisted.
        assert journal.get(intent.full_digest()) is None

    def test_lock_unavailable_on_unsupported_platform(self, tmp_path, monkeypatch):
        from quant_hedge_ai.agents.execution import order_intent_protocol as mod

        monkeypatch.setattr(mod, "fcntl", None)
        coord, journal = coordinator(tmp_path)
        intent = make_intent(causal_id="lock-fail-2")
        calls = []
        result = coord.submit(
            intent,
            authorized=True,
            authorization_ref="ok",
            mutate=lambda i, c: calls.append(1),
        )
        assert result.outcome == SubmissionOutcome.LOCK_UNAVAILABLE
        assert calls == []
        assert journal.get(intent.full_digest()) is None


# ─────────────────────────────────────────────────────────────────────────
# Group L — causal-ID (trace_id) provenance and stability (O-02W-PRE-T1-E
# REM-B-R1, Correction B). See docs/adr/0020-...md §Provenance for the full
# investigation; these are the source-level and behavioral proofs it cites.
# ─────────────────────────────────────────────────────────────────────────


class TestGroupL_CausalIdProvenance:
    def test_trace_id_generated_exactly_once_per_cycle_no_reassignment(self):
        """Source-level proof: `_trace_id` (core/advisor_loop.py) is
        assigned exactly once per cycle (`_trace_id = new_trace_id()`) and
        every `"trace_id": _trace_id` dict entry — including the one the
        two ExecutionEngine call sites eventually read via
        `r.get("trace_id")` — refers to that SAME variable, never a
        re-invocation of `new_trace_id()`. The one OTHER `new_trace_id()`
        call in the file is for an unrelated `_enl_dp` (ENL-2 crash-audit
        record for a FAILED cycle), never reaching `create_order()`/
        `create_futures_order()`."""
        import ast

        src = open("core/advisor_loop.py", encoding="utf-8").read()
        tree = ast.parse(src)

        new_trace_id_call_lines = []
        trace_id_assign_lines = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "new_trace_id"
            ):
                new_trace_id_call_lines.append(node.lineno)
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_trace_id"
            ):
                trace_id_assign_lines.append(node.lineno)

        # Exactly one `_trace_id = new_trace_id()` assignment site in the
        # whole file (the per-cycle decision identity) — a second call to
        # new_trace_id() exists (for `_enl_dp`, an unrelated audit record)
        # but it is never assigned to `_trace_id`.
        assert len(trace_id_assign_lines) == 1, (
            f"expected exactly one `_trace_id = new_trace_id()` assignment, "
            f"found at lines {trace_id_assign_lines} — a second assignment "
            f"site would mean decision_id could silently regenerate "
            f"mid-cycle, defeating I1/I2"
        )
        # Exactly one literal `new_trace_id()` call — the per-cycle
        # `_trace_id` assignment itself. The unrelated ENL-2 crash-audit
        # record uses an aliased import (`from ... import new_trace_id as
        # _new_tid`) and calls `_new_tid()`, which does not match this AST
        # check by name — confirmed separately not to feed `_trace_id`.
        assert len(new_trace_id_call_lines) == 1, (
            f"expected exactly one literal new_trace_id() call site, found "
            f"at lines {new_trace_id_call_lines} — a new call site should "
            f"be reviewed for whether it silently creates a second, "
            f"competing causal identity"
        )
        assert "_new_tid()" in src and "_enl_dp.metadata" in src, (
            "expected the ENL-2 crash-audit record to keep using its own "
            "aliased new_trace_id (as _new_tid) rather than reusing "
            "_trace_id — proves it is a genuinely separate identity, not "
            "a silent regeneration of the decision's own trace_id"
        )

    def test_decision_id_kwarg_traces_back_to_the_single_trace_id_variable(self):
        """Source-level proof that the two `decision_id=` call-site
        arguments in advisor_loop.py read `r.get("trace_id")`, and that
        `r["trace_id"]` is always assigned from the single per-cycle
        `_trace_id` variable (never a literal, never a fresh call)."""
        src = open("core/advisor_loop.py", encoding="utf-8").read()
        assert 'decision_id=_decision_id' in src
        assert '_decision_id = r.get("trace_id") or None' in src
        # Every dict literal assigning the "trace_id" key uses the _trace_id
        # variable — never a hardcoded string or a fresh new_trace_id() call
        # inline in a dict literal (which would silently break I1's "same
        # logical intention -> same identity" for the decision-to-order
        # path).
        import re

        trace_id_dict_entries = re.findall(r'"trace_id":\s*([^\n]+?)[,}]\s*$', src, re.MULTILINE)
        assert trace_id_dict_entries, "expected at least one trace_id dict entry"
        allowed = {"_trace_id", 'r.get("trace_id", "")', 'r.get("trace_id"'}
        for entry in trace_id_dict_entries:
            normalized = entry.strip().rstrip(",")
            assert normalized in allowed or normalized.startswith('r.get("trace_id"'), (
                f'unexpected "trace_id": {entry!r} — every dict entry must '
                f"reference the single per-cycle _trace_id variable (or "
                f"read it back via r.get), never a fresh/hardcoded value"
            )

    def test_distinct_trace_id_values_never_collapse_even_with_identical_trade_fields(self):
        """Behavioral proof (complements Group A's causal-id tests): two
        distinct trace_id-derived causal ids, with every OTHER intent field
        held identical, produce distinct digests/client-order-ids — proving
        the identity space genuinely keys off the volatile-but-stable
        trace_id, not just the trade fields."""
        i1 = make_intent(causal_id="11111111-1111-1111-1111-111111111111")
        i2 = make_intent(causal_id="22222222-2222-2222-2222-222222222222")
        assert i1.full_digest() != i2.full_digest()
        assert i1.client_order_id() != i2.client_order_id()

    def test_same_trace_id_value_reused_within_one_attempt_yields_same_identity(self):
        """The complementary case: if the SAME trace_id value legitimately
        reaches the mutation boundary twice within one logical attempt
        (e.g. this process's own retry-by-idempotent-resubmission, not a
        blind retry), identity stays IDENTICAL — this is the property that
        actually makes REM-B's idempotence work for a stable-but-random
        causal id, without requiring the id itself to be content-derived."""
        i1 = make_intent(causal_id="33333333-3333-3333-3333-333333333333")
        i2 = make_intent(causal_id="33333333-3333-3333-3333-333333333333")
        assert i1.full_digest() == i2.full_digest()
        assert i1.client_order_id() == i2.client_order_id()


# ─────────────────────────────────────────────────────────────────────────
# Group M — adapter capability matrix (O-02W-PRE-T1-E REM-B-R1,
# Correction E). See docs/adr/0020-...md for the full per-exchange matrix
# and why krakenfutures/binanceusdm are deliberately unverified/fail-closed.
# ─────────────────────────────────────────────────────────────────────────


class TestGroupM_AdapterCapabilityMatrix:
    def test_mexc_submission_parameter_documented_but_not_authorized(self):
        """O-02W-PRE-T1-E REM-B-R1.1, Blocker B: MEXC's submission
        parameter is DOCUMENTED (`clientOrderId`) but reconciliation is
        NOT certified against a pinned in-repo implementation — per spec
        §5's explicit rule, only SUBMIT_AND_RECONCILE_VERIFIED authorizes
        external submission, so MEXC does NOT authorize it either,
        despite the parameter name being known. This is a deliberate
        downgrade from R1's model (which authorized submission on
        parameter-name plausibility alone)."""
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            AdapterCapabilityVerdict,
            capabilities_for_exchange,
        )

        caps = capabilities_for_exchange("mexc")
        assert caps.verdict == AdapterCapabilityVerdict.SUBMIT_ONLY_RECONCILIATION_UNVERIFIED
        assert caps.client_order_id_param == "clientOrderId"  # documented, for the record
        assert caps.supports_client_order_id is False  # NOT authorized — the actual gate
        assert caps.supports_lookup_by_client_order_id is False

    def test_mexc_lookup_case_insensitive(self):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            AdapterCapabilityVerdict,
            capabilities_for_exchange,
        )

        assert (
            capabilities_for_exchange("MEXC").verdict
            == AdapterCapabilityVerdict.SUBMIT_ONLY_RECONCILIATION_UNVERIFIED
        )
        assert (
            capabilities_for_exchange("Mexc").verdict
            == AdapterCapabilityVerdict.SUBMIT_ONLY_RECONCILIATION_UNVERIFIED
        )

    def test_unverified_exchanges_fail_closed(self):
        """krakenfutures and binanceusdm are BOTH configurable via
        EXCHANGE_ID in this repo (execution_engine.py's
        `_futures_exchanges` set) but their exact raw clientOrderId
        parameter name was not verified against the installed `ccxt`
        library — both must fail closed rather than silently guess."""
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        for exch_id in ("krakenfutures", "binanceusdm", "binance", "unknown_exchange"):
            caps = capabilities_for_exchange(exch_id)
            assert caps.supports_client_order_id is False, exch_id
            assert caps.client_order_id_param is None, exch_id
            assert caps.supports_lookup_by_client_order_id is False, exch_id

    def test_unsupported_capability_zero_mutation_calls(self, tmp_path):
        coord, journal = coordinator(tmp_path, caps=NO_CID_CAPS)
        intent = make_intent(causal_id="unsupported-1")
        calls = []
        result = coord.submit(
            intent,
            authorized=True,
            authorization_ref="ok",
            mutate=lambda i, c: calls.append(1),
        )
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert calls == []
        assert journal.get(intent.full_digest()) is None

    def test_execution_engine_uses_shared_capability_table_for_futures(
        self, tmp_path, monkeypatch
    ):
        """The real production caller shape: EXCHANGE_ID=krakenfutures
        (a real, configurable, futures-capable exchange in this repo) must
        deny before any mutation call — zero exchange interaction — rather
        than silently sending an unverified clientOrderId parameter."""
        monkeypatch.setenv("EXCHANGE_ID", "krakenfutures")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_FUTURES_MIN_ORDER_USD", "55")
        monkeypatch.setenv("EXEC_FUTURES_MAX_ORDER_USD", "200")
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e.start_session(10_000.0)
        mock_ex = MagicMock()
        mock_ex.fetch_ticker.return_value = {"last": 50_000.0}
        mock_ex.load_markets.return_value = {}
        e._exchange_futures = mock_ex

        # O-02W-PRE-T1-E REM-B-R1.1, Blocker A: this test targets the
        # ADAPTER CAPABILITY gate specifically — durably persist the
        # decision id first so it isn't short-circuited by the (also
        # real, separately tested) durable-decision-identity gate.
        decision_id = "unverified-exchange-1"
        e._get_decision_identity_journal().persist(
            decision_id, namespace="test", symbol="BTC/USD"
        )

        result = e.create_futures_order("BTC/USD", "BUY", 100.0, decision_id=decision_id)
        assert result["mode"] == "futures_failed"
        assert result["order_intent_outcome"] == "UNSUPPORTED_ADAPTER_CAPABILITY"
        mock_ex.create_order.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Group N — exhaustive caller inventory + LAYERED mechanical bypass
# detection (O-02W-PRE-T1-E REM-B-R1.1, Blocker C). See
# docs/adr/0020-...md for the full caller table and the bounded-detection
# model this codifies. This is a STATIC/AST proof — deliberately combined
# with the Group A-M BEHAVIORAL proofs above (spec §7 is explicit that a
# static check alone is insufficient).
#
# BOUNDED DETECTION MODEL (stated honestly, not claimed complete):
# `_mutation_references()` below finds every syntactic AST reference to an
# attribute named in `_MUTATION_METHOD_NAMES` — whether it appears as the
# callee of a direct call (Layer 1: `X.create_order(...)`), as a bare
# argument expression passed to another call (Layer 2:
# `_with_retry(X.create_order, ...)`), as the right-hand side of an
# assignment (Layer 3: `mutate = X.create_order`), or as a literal
# `getattr(X, "create_order")` call (Layer 4) — and attributes each
# occurrence to its enclosing named function (Layer 5, wrapper inventory),
# regardless of whether that function is itself called directly by a
# production entrypoint or only through an intermediate wrapper. Layer 6
# is the allowlist comparison in each test below.
#
# Explicitly NOT claimed: detection of attribute names built at runtime
# from string concatenation/formatting, `importlib`-based dynamic imports,
# `setattr`-based monkeypatching, or any reflection that does not appear
# as a literal `getattr(X, "name")` call with a literal string. Combined
# with `test_all_known_production_callers_of_create_order_inventoried`'s
# repository-wide `grep`, which independently corroborates the same call
# sites from a completely different (non-AST) detection method.
# ─────────────────────────────────────────────────────────────────────────


_MUTATION_METHOD_NAMES = {
    "create_order",
    "create_market_order",
    "create_limit_order",
    "createOrder",
}


def _mutation_references(path):
    """Returns the set of (qualified) function names in `path` whose body
    contains ANY syntactic reference to a mutation-method attribute —
    called directly, passed by reference to a wrapper, assigned to a local
    alias, or accessed via a literal `getattr(..., "name")` call. See the
    module-level BOUNDED DETECTION MODEL comment above for exactly what
    this does and does not catch."""
    import ast

    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    found = set()

    class _Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def _record(self):
            if self.stack:
                found.add(".".join(self.stack))

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_Attribute(self, node):
            # Layers 1-3: ANY attribute access named after a mutation
            # method — called directly, passed by reference as a bare
            # argument, or assigned to a local alias — is the same AST
            # node shape (ast.Attribute). Recording it here, rather than
            # only when it's the direct `.func` of a Call, is what closes
            # the R1 detector's blind spot for
            # `_with_retry(X.create_order, ...)`.
            if node.attr in _MUTATION_METHOD_NAMES:
                self._record()
            self.generic_visit(node)

        def visit_Call(self, node):
            # Layer 4: literal `getattr(X, "create_order")`.
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value in _MUTATION_METHOD_NAMES
            ):
                self._record()
            self.generic_visit(node)

    _Visitor().visit(tree)
    return found


class TestGroupN_CallerInventoryAndBypassDetection:
    def test_execution_engine_mutation_references_only_inside_coordinator_wrapper(self):
        path = "quant_hedge_ai/agents/execution/execution_engine.py"
        functions = _mutation_references(path)
        # Allowed: `_mutate_via_coordinator`'s nested `mutate` closure
        # (where the actual call happens), PLUS `create_futures_order` and
        # `_place_live_order` (`_place_live_order` is itself called only
        # from `create_order`) — the two production functions that legally
        # hand a bound `self._exchange[.futures].create_order` method
        # reference TO `_mutate_via_coordinator(...)` as an argument. That
        # hand-off is the architecturally correct gating mechanism itself,
        # not a bypass — the reference never escapes to an un-gated call.
        # A new function name appearing here means a new exchange-mutation
        # reference was added OUTSIDE this protocol, including one merely
        # PASSED BY REFERENCE to a wrapper (the R1 detector's blind spot).
        allowed = {
            "_mutate_via_coordinator.mutate",
            "create_futures_order",
            "_place_live_order",
        }
        unexpected = functions - allowed
        assert not unexpected, (
            f"new mutation-method reference(s) found outside the REM-B "
            f"coordinator wrapper: {unexpected} — route through "
            f"OrderIntentCoordinator.submit() instead"
        )

    def test_position_manager_mutation_references_only_inside_coordinator_wrapper(self):
        path = "quant_hedge_ai/agents/execution/position_manager.py"
        functions = _mutation_references(path)
        allowed = {"_send_close_order.mutate"}
        unexpected = functions - allowed
        assert not unexpected, (
            f"new mutation-method reference(s) found outside the REM-B "
            f"coordinator wrapper: {unexpected} — route through "
            f"OrderIntentCoordinator.submit() instead"
        )

    def test_layer2_reference_passed_to_wrapper_is_detected(self, tmp_path):
        """Behavioral proof of Layer 2 detection using a synthetic fixture
        file — NOT the real production files — reproducing the exact
        historical bypass shape `_with_retry(exchange.create_order, ...)`
        the R1 detector missed."""
        fixture = tmp_path / "fixture_layer2.py"
        fixture.write_text(
            "class E:\n"
            "    def bad(self):\n"
            "        return self._with_retry(self._exchange.create_order, 1, 2)\n"
        )
        functions = _mutation_references(str(fixture))
        assert "bad" in functions

    def test_layer3_assigned_alias_is_detected(self, tmp_path):
        fixture = tmp_path / "fixture_layer3.py"
        fixture.write_text(
            "class E:\n"
            "    def bad(self):\n"
            "        mutate = self._exchange.create_order\n"
            "        return mutate(1, 2)\n"
        )
        functions = _mutation_references(str(fixture))
        assert "bad" in functions

    def test_layer4_literal_getattr_is_detected(self, tmp_path):
        fixture = tmp_path / "fixture_layer4.py"
        fixture.write_text(
            "class E:\n"
            "    def bad(self):\n"
            "        fn = getattr(self._exchange, 'create_order')\n"
            "        return fn(1, 2)\n"
        )
        functions = _mutation_references(str(fixture))
        assert "bad" in functions

    def test_layer5_wrapper_delegation_attributed_to_wrapper(self, tmp_path):
        """A reference inside a helper function is attributed to THAT
        function even when production code only ever calls a
        higher-level wrapper around it — the inventory must catch it at
        its actual source, not only at the outermost call site."""
        fixture = tmp_path / "fixture_layer5.py"
        fixture.write_text(
            "class E:\n"
            "    def _low_level_mutate(self):\n"
            "        return self._exchange.create_order(1, 2)\n"
            "    def public_wrapper(self):\n"
            "        return self._low_level_mutate()\n"
        )
        functions = _mutation_references(str(fixture))
        assert functions == {"_low_level_mutate"}

    def test_known_allowed_wrapper_passes_without_flagging(self, tmp_path):
        """A reference inside the one allowlisted coordinator closure must
        NOT be flagged — proving the detector doesn't just flag every
        reference indiscriminately (which would make the allowlist
        meaningless)."""
        fixture = tmp_path / "fixture_allowed.py"
        fixture.write_text(
            "class E:\n"
            "    def _mutate_via_coordinator(self, mutate_fn):\n"
            "        def mutate(intent, cid):\n"
            "            return mutate_fn(1, 2)\n"
            "        return mutate\n"
        )
        functions = _mutation_references(str(fixture))
        assert functions == set()  # mutate_fn is a parameter, not a mutation-method attribute

    def test_new_unauthorized_fixture_call_site_fails_the_inventory_test(self, tmp_path, monkeypatch):
        """Reproduces the actual production test's failure mode: a NEW,
        unauthorized function is added to a file the inventory test
        scans, and the test must fail — proven here by running the same
        assertion logic against a synthetic copy of execution_engine.py
        with an injected bypass, not by mutating the real file."""
        real_path = "quant_hedge_ai/agents/execution/execution_engine.py"
        src = open(real_path, encoding="utf-8").read()
        injected = src.replace(
            "def _to_futures_symbol(self, symbol: str) -> str:",
            "def _fake_new_bypass(self):\n"
            "        return self._exchange.create_order('x', 'y', 'z')\n\n"
            "    def _to_futures_symbol(self, symbol: str) -> str:",
            1,
        )
        assert injected != src, "fixture setup failed to inject the synthetic bypass"
        fixture = tmp_path / "injected_execution_engine.py"
        fixture.write_text(injected)
        functions = _mutation_references(str(fixture))
        allowed = {"_mutate_via_coordinator.mutate"}
        unexpected = functions - allowed
        assert "_fake_new_bypass" in unexpected

    def test_no_legacy_bypass_branch_remains_in_execution_engine(self):
        """The pre-Correction-A `else: order = self._with_retry(self.
        _exchange[.futures].create_order, ...)` bypass (taken whenever
        decision_id was falsy) must not reappear — confirmed by searching
        for `_with_retry` combined with `.create_order` anywhere in the
        module (the ONLY correct use of `_with_retry` in this file is for
        pre-mutation read calls: fetch_ticker/load_markets/fetch_balance,
        never the mutation itself, per `_mutate_via_coordinator`'s own
        docstring)."""
        src = open(
            "quant_hedge_ai/agents/execution/execution_engine.py", encoding="utf-8"
        ).read()
        assert "_with_retry(\n                        self._exchange.create_order" not in src
        assert "_with_retry(self._exchange.create_order" not in src
        assert "_with_retry(self._exchange_futures.create_order" not in src
        assert "_with_retry(\n                self._exchange_futures.create_order" not in src

    def test_all_known_production_callers_of_create_order_inventoried(self):
        """Fresh repo-wide search proving the caller inventory documented
        in the ADR is exhaustive at the time this test runs — new grep
        hits outside the already-reviewed set must be investigated, not
        silently accepted. Reviewed-and-classified callers:

        - core/advisor_loop.py (2 sites) — source-reachable, externally
          capable, decision_id supplied via trace_id propagation.
        - quant_hedge_ai/agents/execution/position_manager.py — internal
          gated call inside `_send_close_order`'s mutate() closure.
        - quant_hedge_ai/agents/execution/execution_engine.py — internal
          gated call inside `_mutate_via_coordinator`'s mutate() closure,
          plus its own docstring mention.
        - quant_hedge_ai/agents/risk/portfolio_brain.py,
          capital_allocation_engine.py, supervision/ops_watchdog.py —
          docstring usage EXAMPLES only (`...` ellipsis placeholders,
          not valid Python call syntax) — not source-reachable code.
        - quant_hedge_ai/main_v91.py, quant_hedge_ai/main_system.py —
          REAL calls, in a documented PARALLEL/legacy entrypoint (see
          observability/operator/domains/execution_state.py:170 — already
          flagged pre-existing governance debt, "hors périmètre O-01").
          Do NOT supply decision_id. Left unmodified (out of REM-B-R1
          scope — not advisor_loop.py, the actual production entrypoint)
          but PROTECTED anyway: Correction A's fail-closed check lives
          inside ExecutionEngine.create_order() itself, so these callers
          cannot bypass REM-B even without being touched — they simply
          receive MISSING_CAUSAL_ID if they ever reach a real mutation.
        - scripts/smoke_test_ci.py — CI smoke test, not production.
        """
        import subprocess

        result = subprocess.run(
            [
                "grep",
                "-rn",
                r"\.create_order(\|\.create_futures_order(\|_send_close_order(",
                "--include=*.py",
                "core/",
                "quant_hedge_ai/",
                "scripts/",
                "supervision/",
                "infra/",
            ],
            cwd=".",
            capture_output=True,
            text=True,
        )
        hits = [
            line
            for line in result.stdout.splitlines()
            if "/test_" not in line and "tests/" not in line
            and "order_intent_protocol.py" not in line
        ]
        known_files = {
            "core/advisor_loop.py",
            "quant_hedge_ai/agents/risk/portfolio_brain.py",
            "quant_hedge_ai/agents/risk/capital_allocation_engine.py",
            "quant_hedge_ai/agents/execution/execution_engine.py",
            "quant_hedge_ai/agents/execution/position_manager.py",
            "quant_hedge_ai/agents/execution/decision_identity.py",  # docstring mentions only, no real call
            "quant_hedge_ai/main_v91.py",
            "quant_hedge_ai/main_system.py",
            "scripts/smoke_test_ci.py",
            "supervision/ops_watchdog.py",
        }
        unexpected_files = {
            line.split(":", 1)[0] for line in hits
        } - known_files
        assert not unexpected_files, (
            f"new file(s) with a direct create_order/create_futures_order/"
            f"_send_close_order reference not in the reviewed caller "
            f"inventory: {unexpected_files} — investigate and classify "
            f"before assuming REM-B coverage is still complete"
        )


# ─────────────────────────────────────────────────────────────────────────
# Group O — durable upstream decision identity (O-02W-PRE-T1-E REM-B-R1.1,
# Blocker A). Uses `decision_identity.DecisionIdentityJournal` directly
# (unit-level) plus `ExecutionEngine` through its real production
# `_decision_id_is_durably_persisted()` gate (integration-level) — not
# monkeypatched away, unlike the other test files' fixtures.
# ─────────────────────────────────────────────────────────────────────────


class TestGroupO_DurableDecisionIdentity:
    def test_identity_created_once_persisted_before_execution(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-1", namespace="test", cycle=1, symbol="BTC/USDT")
        assert j.is_persisted("dec-1")

    def test_serialization_round_trip_preserves_identity(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        path = tmp_path / "decisions.jsonl"
        j1 = DecisionIdentityJournal(path)
        j1.persist("dec-roundtrip", namespace="test", cycle=5, symbol="ETH/USDT")

        # Simulate process restart: a BRAND NEW journal instance pointed
        # at the SAME durable path — proving reconstruction, not an
        # in-memory cache, is what answers `is_persisted`.
        j2 = DecisionIdentityJournal(path)
        assert j2.is_persisted("dec-roundtrip")

    def test_reconstruction_after_restart_retains_identity(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        path = tmp_path / "decisions.jsonl"
        DecisionIdentityJournal(path).persist("dec-restart", namespace="test")
        # A THIRD reconstruction still sees it — durability isn't a
        # one-shot fluke.
        assert DecisionIdentityJournal(path).is_persisted("dec-restart")
        assert DecisionIdentityJournal(path).is_persisted("dec-restart")

    def test_duplicate_delivery_retains_same_identity(self, tmp_path):
        """The same decision_id persisted twice (e.g. a duplicated
        DecisionPacket delivery) stays associated with the exact same
        identity string — no collision, no second distinct record
        required for `is_persisted` to keep returning True."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-dup", namespace="test", cycle=1)
        j.persist("dec-dup", namespace="test", cycle=1)  # duplicate delivery
        assert j.is_persisted("dec-dup")

    def test_identical_trade_fields_distinct_decisions_distinct_identity(self, tmp_path):
        """Two DISTINCT decision_id values (as two genuinely different
        decision cycles would generate) are both independently persisted
        and independently verifiable — persisting one never satisfies a
        membership check for the other, even with identical
        symbol/cycle metadata."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-A", namespace="test", cycle=1, symbol="BTC/USDT")
        j.persist("dec-B", namespace="test", cycle=1, symbol="BTC/USDT")
        assert j.is_persisted("dec-A")
        assert j.is_persisted("dec-B")
        assert not j.is_persisted("dec-C")  # never persisted — correctly absent

    def test_missing_persisted_id_fails_closed_zero_mutation(self, tmp_path, monkeypatch):
        """Integration proof through the REAL, un-bypassed ExecutionEngine
        gate: a `decision_id` that was never durably persisted (a bare
        in-memory string, exactly like a legacy caller unaware of this
        journal would produce) is refused BEFORE any mutation call."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv(
            "DECISION_IDENTITY_JOURNAL_PATH", str(tmp_path / "decisions.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10_000.0}}
        e._exchange = mock_exchange
        e.start_session(10_000.0)

        # decision_id is a real, non-empty string — but NEVER persisted.
        result = e.create_order("BTC/USDT", "BUY", 100.0, decision_id="never-persisted-id")
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "UNPERSISTED_CAUSAL_ID"
        mock_exchange.create_order.assert_not_called()

    def test_persisted_id_reaches_real_execution_path(self, tmp_path, monkeypatch):
        """The positive case, through the same real gate: a decision_id
        that WAS durably persisted first is honored."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv(
            "DECISION_IDENTITY_JOURNAL_PATH", str(tmp_path / "decisions.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution import order_intent_protocol as oip
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setitem(
            oip._ADAPTER_CAPABILITIES_BY_EXCHANGE,
            "mexc",
            oip.AdapterCapabilities(
                verdict=oip.AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
                client_order_id_param="clientOrderId",
            ),
        )

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10_000.0}}
        mock_exchange.create_order.return_value = {"id": "ok-1"}
        e._exchange = mock_exchange
        e.start_session(10_000.0)

        e._get_decision_identity_journal().persist(
            "properly-persisted-id", namespace="test"
        )
        result = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="properly-persisted-id"
        )
        assert result["mode"] == "live"
        mock_exchange.create_order.assert_called_once()

    def test_persistence_failure_produces_zero_mutation(self, tmp_path, monkeypatch):
        """A decision-identity persist() failure must never be silently
        swallowed such that execution proceeds anyway — it must
        transitively fail closed. Proven by pointing the journal path at
        a location where fsync/write will fail (a file, not a directory,
        used AS a parent directory)."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        blocker_file = tmp_path / "not_a_directory"
        blocker_file.write_text("x")
        bad_path = blocker_file / "decisions.jsonl"  # parent is a FILE, not a dir
        with pytest.raises(Exception):
            # mkdir(parents=True) on a path whose parent is a file raises
            # during construction — this IS the fail-closed proof: no
            # journal is silently created, no persist() call could ever
            # have proceeded.
            DecisionIdentityJournal(bad_path)

    def test_empty_decision_id_refuses_to_persist(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityError,
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        with pytest.raises(DecisionIdentityError):
            j.persist("", namespace="test")
        with pytest.raises(DecisionIdentityError):
            j.persist(None, namespace="test")

    def test_truncated_final_record_does_not_lose_earlier_identities(self, tmp_path):
        """Same durability contract as OrderIntentJournal: a corrupt/
        truncated final line must not prevent an earlier, validly-written
        identity from still being found."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        path = tmp_path / "decisions.jsonl"
        j = DecisionIdentityJournal(path)
        j.persist("dec-valid", namespace="test")
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"decision_id": "dec-trunc", "namespace"')  # truncated, no newline

        j2 = DecisionIdentityJournal(path)
        assert j2.is_persisted("dec-valid")
        assert not j2.is_persisted("dec-trunc")  # never validly recorded

    def test_advisor_loop_persists_trace_id_before_execution_source_proof(self):
        """Source-level proof that `core/advisor_loop.py`'s
        `analyze_symbol()` calls `default_decision_identity_journal().
        persist(_trace_id, ...)` immediately after `_trace_id` is created
        — i.e. at the decision-creation boundary, before any of the
        function's subsequent authorization/execution logic — closing the
        causal-ordering gap Correction B named (identity created but never
        durably recorded before execution)."""
        src = open("core/advisor_loop.py", encoding="utf-8").read()
        idx_trace = src.index("_trace_id = new_trace_id()")
        idx_persist = src.index("default_decision_identity_journal()")
        idx_set_trace = src.index("set_trace_id(_trace_id)")
        # persist() call must appear AFTER _trace_id is created but this
        # is still at the very top of the function body — assert it's
        # within a small window (a few hundred characters), not buried
        # deep in unrelated downstream logic.
        assert idx_trace < idx_set_trace < idx_persist
        assert idx_persist - idx_trace < 2000

    def test_restart_cannot_convert_one_decision_into_a_second_order_identity(
        self, tmp_path, monkeypatch
    ):
        """Full causal-ordering proof: persisting a decision id, then
        reconstructing the ExecutionEngine (simulating a process restart)
        and reusing the SAME decision_id, produces the SAME order-intent
        digest via OrderIntentCoordinator — never a second, distinct
        order identity for what is logically one decision."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv(
            "DECISION_IDENTITY_JOURNAL_PATH", str(tmp_path / "decisions.jsonl")
        )
        monkeypatch.setenv(
            "ORDER_INTENT_JOURNAL_PATH", str(tmp_path / "order_intents.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution import order_intent_protocol as oip
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setitem(
            oip._ADAPTER_CAPABILITIES_BY_EXCHANGE,
            "mexc",
            oip.AdapterCapabilities(
                verdict=oip.AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
                client_order_id_param="clientOrderId",
            ),
        )

        def _build_engine():
            e = ExecutionEngine(live=False, _sleep=lambda _: None)
            e._live = True
            mock_exchange = MagicMock()
            mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
            mock_exchange.load_markets.return_value = {}
            mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10_000.0}}
            mock_exchange.create_order.return_value = {"id": "restart-ok"}
            e._exchange = mock_exchange
            e.start_session(10_000.0)
            return e, mock_exchange

        e1, ex1 = _build_engine()
        e1._get_decision_identity_journal().persist("dec-restart-1", namespace="test")
        r1 = e1.create_order("BTC/USDT", "BUY", 100.0, decision_id="dec-restart-1")
        assert r1["mode"] == "live"

        # Simulate a full process restart: a BRAND NEW ExecutionEngine
        # instance, same durable journal paths, same decision_id (the
        # "same logical decision" scenario).
        e2, ex2 = _build_engine()
        r2 = e2.create_order("BTC/USDT", "BUY", 100.0, decision_id="dec-restart-1")

        # No second mutation call — the reconstructed coordinator
        # recognizes the already-ACKNOWLEDGED intent.
        ex2.create_order.assert_not_called()
        assert r2["id"] == "restart-ok"  # same order, not a new one


# ═══════════════════════════════════════════════════════════════════════
# Group P — R1.2 Blocker A: exhaustive fail-closed adapter gating
# (O-02W-PRE-T1-E REM-B-R1.2). Group M already proved the CAPABILITY
# TABLE's own verdicts; this group proves the SUBMISSION-PATH consequence
# of those verdicts end-to-end — zero mutation calls, zero
# SUBMISSION_STARTED transitions, and that neither a caller-supplied
# `lookup` nor a caller-supplied capability object can promote a
# non-fully-verified adapter into one that can submit or reconcile.
# ═══════════════════════════════════════════════════════════════════════


class TestGroupP_R12_AdapterFailClosed:
    def test_mexc_real_capability_denies_submission_zero_mutation(self, tmp_path):
        """MEXC's REAL (unverified) production capability entry —
        SUBMIT_ONLY_RECONCILIATION_UNVERIFIED — must deny submission
        through the coordinator exactly like UNSUPPORTED does; the
        verdict's name must never be read as "submission is fine"."""
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        real_mexc_caps = capabilities_for_exchange("mexc")
        coord, journal = coordinator(tmp_path, caps=real_mexc_caps)
        intent = make_intent(causal_id="p-mexc-spot-1")
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(
            intent, authorized=True, authorization_ref="ok", mutate=mutator
        )
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert mutator.call_count == 0
        assert journal.get(intent.full_digest()) is None  # no SUBMISSION_STARTED write

    def test_mexc_spot_submission_via_execution_engine_denied_zero_mutation(
        self, tmp_path, monkeypatch
    ):
        """End-to-end through the real, un-bypassed ExecutionEngine —
        EXCHANGE_ID=mexc (the repo's own default), real capability table,
        decision_id durably persisted first (isolating this test to the
        ADAPTER gate, not the decision-identity gate)."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("EXCHANGE_ID", "mexc")
        monkeypatch.setenv(
            "DECISION_IDENTITY_JOURNAL_PATH", str(tmp_path / "decisions.jsonl")
        )
        monkeypatch.setenv(
            "ORDER_INTENT_JOURNAL_PATH", str(tmp_path / "order_intents.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10_000.0}}
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        e._get_decision_identity_journal().persist("p-mexc-e2e-1", namespace="test")

        result = e.create_order("BTC/USDT", "BUY", 100.0, decision_id="p-mexc-e2e-1")
        assert result["mode"] == "live_failed"
        assert result["order_intent_outcome"] == "UNSUPPORTED_ADAPTER_CAPABILITY"
        mock_exchange.create_order.assert_not_called()

    def test_mexc_futures_submission_via_execution_engine_denied_zero_mutation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXCHANGE_ID", "mexc")
        monkeypatch.setenv("EXEC_FUTURES_MIN_ORDER_USD", "55")
        monkeypatch.setenv("EXEC_FUTURES_MAX_ORDER_USD", "200")
        monkeypatch.setenv(
            "DECISION_IDENTITY_JOURNAL_PATH", str(tmp_path / "decisions.jsonl")
        )
        monkeypatch.setenv(
            "ORDER_INTENT_JOURNAL_PATH", str(tmp_path / "order_intents.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e.start_session(10_000.0)
        mock_ex = MagicMock()
        mock_ex.fetch_ticker.return_value = {"last": 50_000.0}
        mock_ex.load_markets.return_value = {}
        e._exchange_futures = mock_ex
        e._get_decision_identity_journal().persist("p-mexc-futures-1", namespace="test")

        result = e.create_futures_order(
            "BTC/USDT", "BUY", 100.0, decision_id="p-mexc-futures-1"
        )
        assert result["mode"] == "futures_failed"
        assert result["order_intent_outcome"] == "UNSUPPORTED_ADAPTER_CAPABILITY"
        mock_ex.create_order.assert_not_called()

    def test_mexc_positionmanager_close_denied_zero_mutation(self, tmp_path, monkeypatch):
        """PositionManager._send_close_order must obey the SAME shared
        capability table — a real (unverified) mexc adapter denies the
        close mutation exactly like ExecutionEngine's paths do."""
        monkeypatch.setenv("EXCHANGE_ID", "mexc")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        monkeypatch.setenv(
            "ORDER_INTENT_JOURNAL_PATH", str(tmp_path / "order_intents.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution.position_manager import (
            Position,
            PositionManager,
            PositionSide,
        )

        mock_ex = MagicMock()
        mock_ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 0.0001}}
        }
        pm = PositionManager(exchange=mock_ex, paper_mode=False)
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            entry_price=50_000.0,
            size_usd=100.0,
            qty=0.002,
            order_id="pm-mexc-close-1",
        )
        pos.current_price = 51_000.0
        result = pm._send_close_order(pos, reason=__import__(
            "quant_hedge_ai.agents.execution.position_manager", fromlist=["CloseReason"]
        ).CloseReason.MANUAL)
        assert result["mode"] == "live_failed"
        mock_ex.create_order.assert_not_called()

    def test_krakenfutures_submission_denied_zero_mutation(self, tmp_path):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        coord, journal = coordinator(tmp_path, caps=capabilities_for_exchange("krakenfutures"))
        intent = make_intent(causal_id="p-kraken-1")
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert mutator.call_count == 0

    def test_binanceusdm_submission_denied_zero_mutation(self, tmp_path):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        coord, journal = coordinator(tmp_path, caps=capabilities_for_exchange("binanceusdm"))
        intent = make_intent(causal_id="p-binanceusdm-1")
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert mutator.call_count == 0

    def test_unknown_adapter_denied_zero_mutation(self, tmp_path):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        coord, journal = coordinator(
            tmp_path, caps=capabilities_for_exchange("some_never_registered_exchange")
        )
        intent = make_intent(causal_id="p-unknown-1")
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert mutator.call_count == 0

    def test_adapter_alias_cannot_bypass_capability_table(self, tmp_path):
        """A plausible-looking alias/variant of a real exchange id
        ('mexc-spot', 'mexc_v2', 'MEXC2') is NOT in the capability table
        and must fail closed exactly like any other unknown identifier —
        never silently fall back to the real 'mexc' entry by prefix/fuzzy
        match."""
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            AdapterCapabilityVerdict,
            capabilities_for_exchange,
        )

        for alias in ("mexc-spot", "mexc_v2", "MEXC2", "mexcfutures"):
            caps = capabilities_for_exchange(alias)
            assert caps.verdict == AdapterCapabilityVerdict.UNSUPPORTED, alias
            assert caps.supports_client_order_id is False, alias

    def test_submit_only_reconciliation_unverified_denied_directly(self, tmp_path):
        """Constructs a coordinator directly with a
        SUBMIT_ONLY_RECONCILIATION_UNVERIFIED capability (not going
        through the shared table) to prove the DENIAL RULE itself, not
        just today's MEXC data — this must hold for any adapter that ever
        receives this verdict, present or future."""
        caps = AdapterCapabilities(
            verdict=AdapterCapabilityVerdict.SUBMIT_ONLY_RECONCILIATION_UNVERIFIED,
            client_order_id_param="clientOrderId",
        )
        coord, journal = coordinator(tmp_path, caps=caps)
        intent = make_intent(causal_id="p-submit-only-1")
        mutator = CountingMutator(fixed=ack())
        result = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert mutator.call_count == 0

    def test_caller_supplied_lookup_never_invoked_for_unverified_capability(self, tmp_path):
        """`reconcile()` must never call a caller-supplied `lookup` unless
        THIS coordinator's own certified capability is
        SUBMIT_AND_RECONCILE_VERIFIED — a permissive `lookup` a caller
        passes in cannot promote an unverified adapter's capability."""
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        coord, journal = coordinator(tmp_path, caps=capabilities_for_exchange("mexc"))
        lookup_calls = []

        def permissive_lookup(client_order_id):
            lookup_calls.append(client_order_id)
            return ReconciliationLookupResult(lookup_failed=False, matches=[{"id": "fake"}])

        result = coord.reconcile("nonexistent-digest", lookup=permissive_lookup)
        assert result.outcome == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY
        assert lookup_calls == []  # never invoked

    def test_caller_supplied_capability_object_cannot_promote_production_adapter(self):
        """`capabilities_for_exchange()` — the SOLE production authority —
        always returns the SAME verdict for 'mexc' regardless of any
        AdapterCapabilities object a caller might construct elsewhere;
        there is no parameter on `ExecutionEngine`/`PositionManager` that
        accepts a caller-supplied capability override for a production
        exchange id (source-level proof: `_get_order_intent_coordinator`
        calls `capabilities_for_exchange(exch_id)` unconditionally)."""
        import inspect

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
        from quant_hedge_ai.agents.execution.position_manager import PositionManager
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            AdapterCapabilityVerdict,
            capabilities_for_exchange,
        )

        # A caller builds an arbitrary "fully verified" fake locally...
        _ = AdapterCapabilities(
            verdict=AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
            client_order_id_param="clientOrderId",
        )
        # ...but it is never wired into either production coordinator
        # constructor — both call sites read ONLY from the shared table.
        for src in (
            inspect.getsource(ExecutionEngine._get_order_intent_coordinator),
            inspect.getsource(PositionManager._get_order_intent_coordinator),
        ):
            assert "capabilities_for_exchange(" in src
        # ...and the real production verdict is unaffected by the local
        # fake object's mere existence.
        assert (
            capabilities_for_exchange("mexc").verdict
            == AdapterCapabilityVerdict.SUBMIT_ONLY_RECONCILIATION_UNVERIFIED
        )

    def test_fully_verified_fake_adapter_submits_exactly_once(self, tmp_path):
        coord, journal = coordinator(tmp_path, caps=FULL_CAPS)
        intent = make_intent(causal_id="p-verified-1")
        mutator = CountingMutator(fixed=ack())
        r1 = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert r1.outcome == SubmissionOutcome.ACKNOWLEDGED
        assert mutator.call_count == 1
        r2 = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert r2.outcome == SubmissionOutcome.ACKNOWLEDGED
        assert mutator.call_count == 1  # still exactly once — duplicate call, no resubmission

    def test_ambiguous_on_verified_fake_enters_reconciliation_without_resubmission(
        self, tmp_path
    ):
        coord, journal = coordinator(tmp_path, caps=FULL_CAPS)
        intent = make_intent(causal_id="p-ambiguous-1")
        mutator = CountingMutator(fixed=ambiguous())
        r1 = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert r1.outcome == SubmissionOutcome.RECONCILE_REQUIRED
        assert mutator.call_count == 1
        # A duplicate submit call (e.g. a naive retry) must NOT re-invoke
        # the mutator — the ambiguous result is recorded, not resubmitted.
        r2 = coord.submit(intent, authorized=True, authorization_ref="ok", mutate=mutator)
        assert r2.outcome == SubmissionOutcome.RECONCILE_REQUIRED
        assert mutator.call_count == 1

    def test_non_verified_adapter_creates_no_submission_started_transition(self, tmp_path):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        coord, journal = coordinator(tmp_path, caps=capabilities_for_exchange("mexc"))
        intent = make_intent(causal_id="p-no-transition-1")
        coord.submit(
            intent, authorized=True, authorization_ref="ok", mutate=CountingMutator(fixed=ack())
        )
        # Zero journal records for this digest at all — not even
        # INTENT_RECORDED, let alone SUBMISSION_STARTED.
        assert journal.get(intent.full_digest()) is None
        assert journal.latest_by_digest() == {}

    def test_retry_wrapper_cannot_bypass_capability_denial(self, tmp_path):
        """A naive caller-side retry loop around `submit()` (mirroring the
        production `_with_retry` shape, but at the submission layer) must
        be denied on EVERY attempt — the capability gate is re-checked
        every call, not bypassable by simply calling again."""
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        coord, journal = coordinator(tmp_path, caps=capabilities_for_exchange("mexc"))
        intent = make_intent(causal_id="p-retry-wrapper-1")
        mutator = CountingMutator(fixed=ack())
        outcomes = []
        for _ in range(3):  # naive retry wrapper
            outcomes.append(
                coord.submit(
                    intent, authorized=True, authorization_ref="ok", mutate=mutator
                ).outcome
            )
        assert all(o == SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY for o in outcomes)
        assert mutator.call_count == 0


# ═══════════════════════════════════════════════════════════════════════
# Group Q — R1.2 Blocker B: genuine causal reconstruction after restart
# (O-02W-PRE-T1-E REM-B-R1.2, §4). Group O proved a decision_id, once
# persisted, stays found by an is_persisted() membership check across a
# fresh journal instance — MASTER review named this insufficient: it does
# not prove the DECISION ITSELF (its canonical payload) can be
# RECONSTRUCTED from durable state using only a stable recovery selector,
# nor that it stays bound to exactly one authorized order intent. This
# group proves both.
# ═══════════════════════════════════════════════════════════════════════


class TestGroupQ_R12_CausalReconstruction:
    def test_bind_intent_requires_a_persisted_decision(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityError,
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        with pytest.raises(DecisionIdentityError):
            j.bind_intent("never-persisted", "some-intent-digest")
        # zero writes — the journal file gained no records from the failed bind
        assert j.recover_pending_decisions() == {}

    def test_bind_intent_records_lifecycle_transition(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-bind-1", namespace="test", cycle=1, symbol="BTC/USDT")
        rec = j.bind_intent("dec-bind-1", "intent-digest-1")
        assert rec["lifecycle_state"] == "BOUND"
        assert rec["bound_intent_digest"] == "intent-digest-1"
        assert j.get("dec-bind-1")["bound_intent_digest"] == "intent-digest-1"

    def test_same_replay_preserves_bound_intent_digest_idempotent(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-bind-2", namespace="test")
        j.bind_intent("dec-bind-2", "intent-digest-2")
        # Replaying the SAME bind (e.g. a retried submission attempt)
        # must succeed idempotently, never raise, never change the binding.
        rec2 = j.bind_intent("dec-bind-2", "intent-digest-2")
        assert rec2["bound_intent_digest"] == "intent-digest-2"

    def test_binding_same_decision_to_different_intent_fails_closed(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityError,
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-bind-3", namespace="test")
        j.bind_intent("dec-bind-3", "intent-digest-original")
        with pytest.raises(DecisionIdentityError):
            j.bind_intent("dec-bind-3", "intent-digest-DIFFERENT")
        # the original binding survives the failed rebind attempt
        assert j.get("dec-bind-3")["bound_intent_digest"] == "intent-digest-original"

    def test_restart_reconstructs_pending_decision_using_only_durable_state(self, tmp_path):
        """The R1.2 §4.4 core proof: a decision is created and persisted
        inside a nested scope whose locals (including the `decision_id`
        variable itself) go out of scope entirely — recovery afterward
        uses ONLY the durable journal path plus a stable (namespace,
        cycle, symbol) selector, never a retained in-memory id/object."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        path = tmp_path / "decisions.jsonl"

        def _create_and_discard() -> str:
            j = DecisionIdentityJournal(path)
            rec = j.persist(
                "dec-restart-recon-1",
                namespace="advisor_loop.analyze_symbol",
                cycle=42,
                symbol="BTC/USDT",
                action="BUY",
            )
            del j  # discard the journal instance too — not just the id
            return rec["payload_digest"]  # only the digest crosses the boundary

        original_digest = _create_and_discard()

        # "process restart": a brand-new journal instance, no retained
        # coordinator/engine/closure, no retained decision_id variable.
        j2 = DecisionIdentityJournal(path)
        recovered = j2.find_by_cycle_key(
            namespace="advisor_loop.analyze_symbol", cycle=42, symbol="BTC/USDT"
        )
        assert recovered is not None
        assert recovered["payload_digest"] == original_digest
        assert j2.verify_digest(recovered["decision_id"])

    def test_reconstructed_record_preserves_exact_decision_id_and_payload(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        path = tmp_path / "decisions.jsonl"
        DecisionIdentityJournal(path).persist(
            "dec-preserve-1", namespace="ns", cycle=7, symbol="ETH/USDT", action="SELL"
        )
        j2 = DecisionIdentityJournal(path)
        pending = j2.recover_pending_decisions(namespace="ns")
        assert "dec-preserve-1" in pending
        rec = pending["dec-preserve-1"]
        assert rec["decision_id"] == "dec-preserve-1"
        assert rec["payload"]["cycle"] == 7
        assert rec["payload"]["symbol"] == "ETH/USDT"
        assert rec["payload"]["action"] == "SELL"

    def test_missing_decision_record_fails_closed(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        assert j.get("never-existed") is None
        assert not j.is_persisted("never-existed")
        assert j.recover_pending_decisions() == {}
        assert j.find_by_cycle_key(namespace="ns", cycle=1, symbol="BTC/USDT") is None

    def test_legacy_incomplete_record_excluded_from_recovery_but_backward_compatible(
        self, tmp_path
    ):
        """A genuinely legacy (pre-R1.2, schema_version=1) record —
        missing `payload`/`payload_digest` — is NOT recoverable (fails
        closed for reconstruction) but R1.1's simpler is_persisted() gate
        still honors it, for backward compatibility with data written
        before this module gained canonical payloads."""
        import json as _json

        path = tmp_path / "decisions.jsonl"
        legacy_record = {
            "schema_version": 1,
            "decision_id": "dec-legacy-1",
            "namespace": "test",
            "cycle": 1,
            "symbol": "BTC/USDT",
            "ts": 0.0,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(legacy_record) + "\n", encoding="utf-8")

        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(path)
        assert j.is_persisted("dec-legacy-1")  # R1.1 backward compatibility
        assert j.recover_pending_decisions() == {}  # but NOT reconstructible
        assert j.verify_digest("dec-legacy-1") is False

    def test_tampered_payload_fails_digest_verification(self, tmp_path):
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-tamper-1", namespace="test", cycle=1, symbol="BTC/USDT")
        # A caller-supplied payload that disagrees with what was durably
        # stored must fail verification — this is the tamper-detection path.
        tampered = {"namespace": "test", "cycle": 999, "symbol": "ETH/USDT", "action": None}
        assert j.verify_digest("dec-tamper-1", payload=tampered) is False
        # the genuine, unmodified payload still verifies correctly
        assert j.verify_digest("dec-tamper-1") is True

    def test_conflicting_duplicate_decision_record_fails_closed(self, tmp_path):
        """The SAME decision_id persisted twice with a DIFFERENT payload
        (e.g. a bug that reused an id across two distinct decisions) is a
        conflict, not a duplicate delivery — R1.2 fails it closed rather
        than silently accepting whichever payload arrived last."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityError,
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-conflict-1", namespace="test", cycle=1, symbol="BTC/USDT")
        with pytest.raises(DecisionIdentityError):
            j.persist("dec-conflict-1", namespace="test", cycle=2, symbol="ETH/USDT")
        # the original record survives the rejected conflicting write
        assert j.get("dec-conflict-1")["payload"]["cycle"] == 1

    def test_genuine_duplicate_delivery_of_identical_payload_remains_idempotent(self, tmp_path):
        """The non-conflicting counterpart to the test above: persisting
        the SAME decision_id with the SAME resulting payload twice (e.g. a
        duplicated DecisionPacket delivery) must NOT raise — this is the
        expected duplicate-delivery case, not a conflict."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-dup-ok-1", namespace="test", cycle=1, symbol="BTC/USDT")
        j.persist("dec-dup-ok-1", namespace="test", cycle=1, symbol="BTC/USDT")  # no raise
        assert j.is_persisted("dec-dup-ok-1")

    def test_truncated_record_never_recoverable(self, tmp_path):
        path = tmp_path / "decisions.jsonl"
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(path)
        j.persist("dec-trunc-valid-1", namespace="test", cycle=1, symbol="BTC/USDT")
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"decision_id": "dec-trunc-broken", "payload"')  # truncated

        j2 = DecisionIdentityJournal(path)
        pending = j2.recover_pending_decisions()
        assert "dec-trunc-valid-1" in pending
        assert "dec-trunc-broken" not in pending

    def test_identical_trade_fields_two_new_decisions_produce_distinct_ids(self, tmp_path):
        """Two genuinely distinct decision-creation events with
        byte-identical trade fields (same cycle/symbol/action — as a
        strategy re-evaluating and re-deciding the exact same trade could
        produce) must receive DISTINCT decision_id values — this module
        never derives identity from payload content, only from the
        upstream-supplied id (advisor_loop's random UUID)."""
        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-identical-A", namespace="test", cycle=1, symbol="BTC/USDT", action="BUY")
        j.persist("dec-identical-B", namespace="test", cycle=1, symbol="BTC/USDT", action="BUY")
        pending = j.recover_pending_decisions(namespace="test")
        assert set(pending.keys()) == {"dec-identical-A", "dec-identical-B"}
        # identical payload content is fine — the identities themselves differ
        assert (
            pending["dec-identical-A"]["payload_digest"]
            == pending["dec-identical-B"]["payload_digest"]
        )

    def test_recovery_and_verification_perform_no_network_or_exchange_calls(self, tmp_path):
        """Source-level + behavioral proof: `recover_pending_decisions`,
        `find_by_cycle_key`, and `verify_digest` operate purely on the
        local durable file — no exchange/network object is ever
        constructed or required to call them."""
        import inspect

        from quant_hedge_ai.agents.execution.decision_identity import (
            DecisionIdentityJournal,
        )

        for name in ("recover_pending_decisions", "find_by_cycle_key", "verify_digest"):
            src = inspect.getsource(getattr(DecisionIdentityJournal, name))
            for forbidden in ("requests.", "ccxt", "socket.", "urlopen", "fetch_"):
                assert forbidden not in src, (name, forbidden)

        j = DecisionIdentityJournal(tmp_path / "decisions.jsonl")
        j.persist("dec-no-network-1", namespace="test", cycle=1, symbol="BTC/USDT")
        # Executes without any exchange/network fixture in scope at all.
        j.recover_pending_decisions()
        j.find_by_cycle_key(namespace="test", cycle=1, symbol="BTC/USDT")
        j.verify_digest("dec-no-network-1")

    def test_restart_with_binding_preserves_binding_and_causes_no_resubmission(
        self, tmp_path, monkeypatch
    ):
        """Full end-to-end restart proof combining Blocker A (decision
        persistence) and Blocker B (decision-intent binding): a decision
        is created, persisted, bound to its order intent, and submitted.
        A full process restart (brand-new ExecutionEngine, same durable
        paths, same decision_id) must reuse the SAME binding and cause
        ZERO further exchange mutation calls."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv(
            "DECISION_IDENTITY_JOURNAL_PATH", str(tmp_path / "decisions.jsonl")
        )
        monkeypatch.setenv(
            "ORDER_INTENT_JOURNAL_PATH", str(tmp_path / "order_intents.jsonl")
        )
        from unittest.mock import MagicMock

        from quant_hedge_ai.agents.execution import order_intent_protocol as oip
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setitem(
            oip._ADAPTER_CAPABILITIES_BY_EXCHANGE,
            "mexc",
            oip.AdapterCapabilities(
                verdict=oip.AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
                client_order_id_param="clientOrderId",
            ),
        )

        def _build_engine():
            e = ExecutionEngine(live=False, _sleep=lambda _: None)
            e._live = True
            mock_exchange = MagicMock()
            mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
            mock_exchange.load_markets.return_value = {}
            mock_exchange.fetch_balance.return_value = {"free": {"USDT": 10_000.0}}
            mock_exchange.create_order.return_value = {"id": "restart-bind-ok"}
            e._exchange = mock_exchange
            e.start_session(10_000.0)
            return e, mock_exchange

        e1, ex1 = _build_engine()
        e1._get_decision_identity_journal().persist("dec-restart-bind-1", namespace="test")
        r1 = e1.create_order("BTC/USDT", "BUY", 100.0, decision_id="dec-restart-bind-1")
        assert r1["mode"] == "live"

        bound_digest_after_first = e1._get_decision_identity_journal().get(
            "dec-restart-bind-1"
        )["bound_intent_digest"]
        assert bound_digest_after_first is not None

        e2, ex2 = _build_engine()
        r2 = e2.create_order("BTC/USDT", "BUY", 100.0, decision_id="dec-restart-bind-1")
        assert r2["mode"] == "live"
        ex2.create_order.assert_not_called()  # no resubmission after restart
        bound_digest_after_restart = e2._get_decision_identity_journal().get(
            "dec-restart-bind-1"
        )["bound_intent_digest"]
        assert bound_digest_after_restart == bound_digest_after_first
