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
        supports_client_order_id=True,
        client_order_id_param="clientOrderId",
        supports_lookup_by_client_order_id=True,
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
    def test_mexc_is_supported_with_correct_param(self):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        caps = capabilities_for_exchange("mexc")
        assert caps.supports_client_order_id is True
        assert caps.client_order_id_param == "clientOrderId"
        assert caps.supports_lookup_by_client_order_id is True

    def test_mexc_lookup_case_insensitive(self):
        from quant_hedge_ai.agents.execution.order_intent_protocol import (
            capabilities_for_exchange,
        )

        assert capabilities_for_exchange("MEXC").supports_client_order_id is True
        assert capabilities_for_exchange("Mexc").supports_client_order_id is True

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

        result = e.create_futures_order(
            "BTC/USD", "BUY", 100.0, decision_id="unverified-exchange-1"
        )
        assert result["mode"] == "futures_failed"
        assert result["order_intent_outcome"] == "UNSUPPORTED_ADAPTER_CAPABILITY"
        mock_ex.create_order.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Group N — exhaustive caller inventory + mechanical bypass detection
# (O-02W-PRE-T1-E REM-B-R1, Correction C). See docs/adr/0020-...md for the
# full caller table this codifies. This is a STATIC/AST proof — it is
# deliberately combined with the Group A-M BEHAVIORAL proofs above (a
# static check alone is explicitly insufficient per spec §5).
# ─────────────────────────────────────────────────────────────────────────


class TestGroupN_CallerInventoryAndBypassDetection:
    def _functions_containing_create_order_call(self, path):
        """Returns the set of (qualified) function names in `path` whose
        body contains a `.create_order(...)` call — regardless of nesting
        depth, so a call inside a nested closure is correctly attributed
        to its enclosing named function."""
        import ast

        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        found = set()

        class _Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "create_order"
                    and self.stack
                ):
                    found.add(".".join(self.stack))
                self.generic_visit(node)

        _Visitor().visit(tree)
        return found

    def test_execution_engine_create_order_calls_only_inside_coordinator_wrapper(self):
        path = "quant_hedge_ai/agents/execution/execution_engine.py"
        functions = self._functions_containing_create_order_call(path)
        # The ONLY function in this file allowed to contain a raw
        # `.create_order(...)` call is `_mutate_via_coordinator`'s nested
        # `mutate` closure — every source-reachable submission path MUST
        # go through it. A new function name appearing here means a new
        # direct exchange-mutation call site was added OUTSIDE the
        # durable/idempotent protocol — exactly the bypass Correction C
        # exists to catch.
        allowed = {"_mutate_via_coordinator.mutate"}
        unexpected = functions - allowed
        assert not unexpected, (
            f"new direct .create_order(...) call site(s) found outside "
            f"the REM-B coordinator wrapper: {unexpected} — route through "
            f"OrderIntentCoordinator.submit() instead"
        )

    def test_position_manager_create_order_calls_only_inside_coordinator_wrapper(self):
        path = "quant_hedge_ai/agents/execution/position_manager.py"
        functions = self._functions_containing_create_order_call(path)
        allowed = {"_send_close_order.mutate"}
        unexpected = functions - allowed
        assert not unexpected, (
            f"new direct .create_order(...) call site(s) found outside "
            f"the REM-B coordinator wrapper: {unexpected} — route through "
            f"OrderIntentCoordinator.submit() instead"
        )

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
