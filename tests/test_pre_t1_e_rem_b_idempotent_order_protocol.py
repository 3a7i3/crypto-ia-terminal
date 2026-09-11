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
    supports_client_order_id=True,
    client_order_id_param="clientOrderId",
    supports_lookup_by_client_order_id=True,
)
NO_CID_CAPS = AdapterCapabilities(
    supports_client_order_id=False,
    client_order_id_param=None,
    supports_lookup_by_client_order_id=False,
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
        assert result.outcome == SubmissionOutcome.IDENTITY_COLLISION

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
        assert result.outcome == SubmissionOutcome.IDENTITY_COLLISION

    def test_multiple_matches_fail_closed(self, tmp_path):
        coord, _ = coordinator(tmp_path)
        intent = make_intent(causal_id="d5")
        put_in_reconcile_required(coord, intent)
        result = coord.reconcile(
            intent.full_digest(),
            lookup=lambda cid: ReconciliationLookupResult(False, [{"id": "1"}, {"id": "2"}]),
        )
        assert result.outcome == SubmissionOutcome.IDENTITY_COLLISION

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
