"""Finite, injectable pilot. No import-time I/O and no wiring to the Operator API."""

from dataclasses import replace
import re
import time
import uuid
from .plan import PilotPlan, RequestSpec, roster
from .capture import Capture, Response, SystemClock, metadata_problem, probe_result
from .store import RunStore, StorageBudgetExceeded
from observability.market_venues.decoders import decode_snapshot, unavailable
from observability.market_venues.models import iso
from observability.market_venues.publication import build_publication

FATAL = {
    "ACCESS_OR_RATE_LIMIT_REFUSED",
    "NATIVE_API_REFUSED",
    "CONTENT_ENCODING_REFUSED",
    "RESPONSE_TOO_LARGE",
}


def run_bounded_pilot(
    transport,
    run_parent,
    *,
    source_sha,
    plan=None,
    clock=None,
    sleeper=time.sleep,
    run_id=None,
):
    plan = (plan or PilotPlan()).validate()
    if not isinstance(source_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("PINNED_SOURCE_SHA_REQUIRED")
    evidence_kind = transport.evidence_kind
    if evidence_kind not in ("OBSERVATION", "SYNTHETIC"):
        raise ValueError("EXPLICIT_TRANSPORT_EVIDENCE_REQUIRED")
    clock = clock or SystemClock()
    run_id = run_id or "pilot539-" + uuid.uuid4().hex
    store = RunStore(run_parent, run_id, max_bytes=plan.max_run_bytes)
    bindings = roster()
    started = clock.sample()
    clock_id = run_id
    count = 0
    published = 0
    latest = None
    stop = None
    result = {
        "schema_version": "1.0.0",
        "status": "INCOMPLETE",
        "source_sha": source_sha,
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "activation_authority_granted": False,
        "started_at_utc": iso(started.utc),
    }

    def take(spec):
        nonlocal count, stop
        if count >= 4 + 6 * plan.cycles:
            raise RuntimeError("REQUEST_BUDGET")
        before = clock.sample()
        if before.monotonic_ns - started.monotonic_ns >= plan.duration_ms * 1000000:
            raise TimeoutError("PILOT_DURATION")
        remaining_ms = (
            plan.duration_ms * 1000000 - (before.monotonic_ns - started.monotonic_ns)
        ) // 1000000
        if remaining_ms < 1:
            raise TimeoutError("PILOT_DURATION")
        next_index = count + 1
        intent_hash = store.intent(next_index, spec, before, clock_id, evidence_kind)
        count = next_index
        response = transport.fetch(
            spec,
            timeout_ms=min(plan.request_timeout_ms, remaining_ms),
            max_bytes=plan.max_response_bytes,
        )
        after = clock.sample()
        if not isinstance(response, Response):
            raise ValueError("INVALID_TRANSPORT_RESPONSE")
        if response.body is not None and (
            not isinstance(response.body, bytes)
            or len(response.body) > plan.max_response_bytes
        ):
            raise ValueError("UNBOUNDED_TRANSPORT_RESPONSE")
        capture = Capture(spec, response, before, after)
        store.capture(count, capture, intent_hash)
        if after.monotonic_ns - started.monotonic_ns > plan.duration_ms * 1000000:
            raise TimeoutError("PILOT_DURATION")
        reason = capture.response_problem()
        if reason in FATAL:
            stop = reason
        return capture

    try:
        store.json(
            "plan.json",
            {
                "plan": plan.document(),
                "source_sha": source_sha,
                "evidence_kind": evidence_kind,
                "run_id": run_id,
            },
        )
        metadata = {}
        for binding in bindings:
            if stop:
                metadata[(binding.venue, binding.native_symbol)] = (
                    "SOURCE_NOT_ATTEMPTED"
                )
                continue
            captured = take(
                RequestSpec(binding.venue, "metadata", binding.native_symbol)
            )
            metadata[(binding.venue, binding.native_symbol)] = metadata_problem(
                captured, binding, plan
            )
        store.json(
            "metadata-qualification.json",
            {
                "sources": [
                    {
                        "venue": b.venue,
                        "native_symbol": b.native_symbol,
                        "reason": metadata[(b.venue, b.native_symbol)],
                    }
                    for b in bindings
                ]
            },
        )
        metadata_ok = all(reason is None for reason in metadata.values())
        if not metadata_ok:
            stop = stop or "METADATA_NOT_QUALIFIED"
        for cycle in range(1, plan.cycles + 1):
            cycle_start = clock.sample()
            if (
                cycle_start.monotonic_ns - started.monotonic_ns
                >= plan.duration_ms * 1000000
            ):
                stop = stop or "DURATION_LIMIT"
                break
            probes = {}
            probe_captures = {}
            if metadata_ok and not stop:
                for venue in ("bybit", "okx"):
                    if stop:
                        break
                    captured = take(RequestSpec(venue, "time"))
                    probe_captures[venue] = captured
                    probes[venue] = probe_result(captured, plan)
            observations = []
            for binding in bindings:
                reason = metadata[(binding.venue, binding.native_symbol)]
                captured = None
                if reason is None and not stop:
                    captured = take(
                        RequestSpec(binding.venue, "book", binding.native_symbol)
                    )
                    reason = captured.response_problem() or captured.timing_problem(
                        plan
                    )
                else:
                    reason = reason or "SOURCE_NOT_ATTEMPTED"
                if captured is None:
                    observations.append(unavailable(binding, reason=reason))
                    continue
                try:
                    decoded = (
                        decode_snapshot(
                            binding,
                            captured.response.body,
                            requested_symbol=binding.native_symbol,
                            requested_market_kind="SPOT",
                            requested_category="spot"
                            if binding.venue == "bybit"
                            else None,
                            received_at=captured.after.utc,
                            clock_id=clock_id,
                        )
                        if reason is None
                        else unavailable(
                            binding,
                            received_at=captured.after.utc,
                            clock_id=clock_id,
                            reason=reason,
                            payload_sha256=captured.payload_sha256,
                        )
                    )
                except (ValueError, RecursionError):
                    decoded = unavailable(
                        binding,
                        received_at=captured.after.utc,
                        clock_id=clock_id,
                        reason="INVALID_NATIVE_SNAPSHOT",
                        payload_sha256=captured.payload_sha256,
                    )
                probe = probes.get(binding.venue)
                if decoded.decode_error is None and (
                    probe is None or probe["status"] != "AVAILABLE"
                ):
                    decoded = replace(decoded, decode_error="CLOCK_PROBE_NOT_QUALIFIED")
                observations.append(decoded)
            finish = clock.sample()
            delta_mono = finish.monotonic_ns - cycle_start.monotonic_ns
            delta_wall = finish.utc_ns - cycle_start.utc_ns
            run_delta_mono = finish.monotonic_ns - started.monotonic_ns
            run_delta_wall = finish.utc_ns - started.utc_ns
            clock_bad = (
                delta_mono < 0
                or delta_wall < 0
                or abs(delta_mono - delta_wall) > plan.max_clock_jump_ms * 1000000
                or run_delta_mono < 0
                or run_delta_wall < 0
                or abs(run_delta_mono - run_delta_wall)
                > plan.max_clock_jump_ms * 1000000
            )
            for i, decoded in enumerate(observations):
                probe = probe_captures.get(decoded.binding.venue)
                if clock_bad:
                    observations[i] = replace(decoded, decode_error="CLOCK_JUMP")
                elif (
                    probe is not None
                    and finish.monotonic_ns - probe.after.monotonic_ns
                    > plan.max_age_ms * 1000000
                ):
                    observations[i] = replace(
                        decoded, decode_error="CLOCK_PROBE_EXPIRED"
                    )
            if clock_bad:
                stop = "CLOCK_JUMP"
            publication = build_publication(
                bindings,
                observations,
                as_of=finish.utc,
                max_age_ms=plan.max_age_ms,
                max_skew_ms=plan.max_skew_ms,
                evidence_kind=evidence_kind,
            )
            store.json(
                f"quality-{cycle:04d}.json",
                {
                    "cycle": cycle,
                    "clock_id": clock_id,
                    "probes": probes,
                    "cycle_monotonic_ns": str(delta_mono),
                    "wall_minus_monotonic_ns": str(delta_wall - delta_mono),
                    "stopped_reason": stop,
                },
            )
            latest = store.publish(cycle, publication)
            published += 1
            if stop:
                break
            if cycle < plan.cycles:
                delay = (
                    plan.interval_ms / 1000
                    - (finish.monotonic_ns - cycle_start.monotonic_ns) / 1000000000
                )
                if delay <= 0:
                    stop = "CYCLE_OVERRUN"
                    break
                remaining = (
                    plan.duration_ms * 1000000
                    - (finish.monotonic_ns - started.monotonic_ns)
                ) / 1000000000
                if remaining <= 0:
                    stop = "DURATION_LIMIT"
                    break
                sleeper(min(delay, remaining))
        result["status"] = "COMPLETED" if stop is None else "STOPPED"
    except StorageBudgetExceeded:
        stop = "STORAGE_BUDGET_EXHAUSTED"
        result["status"] = "INCOMPLETE"
    except TimeoutError:
        stop = "DURATION_LIMIT"
        result["status"] = "INCOMPLETE"
    except (OSError, ValueError, RuntimeError):
        stop = "RUN_REFUSED"
        result["status"] = "INCOMPLETE"
        raise
    finally:
        if result["status"] == "INCOMPLETE" and stop is None:
            stop = "INTERRUPTED_OR_UNEXPECTED_FAILURE"
        result.update(
            stopped_reason=stop,
            requests_attempted=count,
            cycles_published=published,
            last_snapshot=latest,
            finished_at_utc=iso(clock.sample().utc),
            bytes_before_final_receipt=store.used,
        )
        try:
            store.json("run-result.json", result, final=True)
        finally:
            store.close()
    return result
