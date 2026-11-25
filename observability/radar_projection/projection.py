"""S4-a — ``radar-projection/1.0.0``: read-only projection of one verified Radar export.

The projection re-arranges, it does not compute. Every scientific value (decision,
reasons, criteria, score, rank, counts) is copied from the verified export; an
unknown stays ``null`` with its reason, never ``0``. The only values the projection
adds are the digests of the export it was built from, the list of checks the
verifier performed, and fixed statements of integrity and authority.

Deterministic: a pure function of the export bytes. No clock, no publication time,
no environment value enters the projection. Publication freshness (E2) belongs to
the serving layer (S4-b), outside this document.

Publication boundary (S4A-RV-03). The only public ways to obtain a projection start
from BYTES: ``project(raw)`` and ``project_bytes(raw)``. Both run the verifier first
and build on a private deep copy of what it returned. The builder is private and is
never given a document that did not come out of ``verify_export`` in the same call,
so no public interface can attach ``integrity.seal = VERIFIED`` to an arbitrary,
unverified document. S4-b must serve the bytes of ``project_bytes(raw)`` as they are.
"""
from __future__ import annotations

import copy

from observability.radar_selection.fixture import canonical, sha256_hex

from . import contract as pc
from .verifier import IDENTITY_KEYS, ProjectionRefusal, verify_export


def _instrument(m: dict, rank: int | None) -> dict:
    return {
        "identity": {k: m[k] for k in IDENTITY_KEYS},
        "catalogue": m["catalogue"],
        "change": m["change"],
        "previous": m["previous"],
        "lifecycle": m["lifecycle"],
        "observation": m["observation"],
        "admissibility": m["admissibility"],
        "criteria": m["criteria"],
        "score": m["score"],
        "rank": rank,
        "manual": m["manual"],
    }


__all__ = ["project", "project_bytes"]


def _build_projection(verified: dict) -> dict:
    """Private: projection of what ``verify_export`` returned in the same ``project`` call."""
    d = copy.deepcopy(verified["doc"])
    ranks = {cd["market_id"]: cd["rank"] for cd in d["candidates"]}
    out = {
        "schema": pc.PROJECTION_SCHEMA,
        "source": {
            "evaluation_schema": d["schema_version"],
            "rules_version": d["rules_version"],
            "ranking_version": d["ranking_version"],
            "evaluation_sha256": d["evaluation_sha256"],
            "export_sha256": verified["export_sha256"],
            "export_bytes": verified["export_bytes"],
        },
        "integrity": {**pc.INTEGRITY, "checks": list(pc.CHECKS)},
        "evidence": {"kind": d["dataset"]["evidence_kind"], "mode": d["mode"]},
        "dataset": d["dataset"],
        "inputs": d["inputs"],
        "scanner_universe": {
            "sha256": None,
            "state": pc.SCANNER_UNIVERSE_STATE,
            "reason": pc.SCANNER_UNIVERSE_REASON,
            "catalogue_sources": d["sources"],
        },
        "evaluation_time_ms": d["evaluation_time_ms"],
        "mission": d["mission"],
        "policy": d["policy"],
        "population": {"counts": d["counts"], "orphan_observations": d["orphan_observations"]},
        "instruments": [_instrument(m, ranks.get(m["market_id"])) for m in d["markets"]],
        "candidates": d["candidates"],
        "candidates_empty_reason": d["candidates_empty_reason"],
        "preferences": {"preferences_sha256": d["preferences_sha256"], "manual": d["manual"]},
        "budgets": d["budgets"],
        "authority": {
            **d["authority"],
            "admission": d["dataset"]["admission"],
            "deep_observation_jobs": d["deep_observation_jobs"],
            "projection_status": pc.PROJECTION_STATUS,
        },
    }
    out["projection_sha256"] = sha256_hex(canonical(out))
    return out


def project(raw: bytes) -> dict:
    """Verify one frozen export and return its ``radar-projection/1.0.0`` document.

    The single public entry point that produces a verified projection.
    """
    verified = verify_export(raw)
    try:
        return _build_projection(verified)
    except (TypeError, KeyError, ValueError, RecursionError) as exc:
        # Unreachable for a verified document (every field is bounded); kept typed anyway.
        raise ProjectionRefusal(f"STRUCTURE_INVALID:{type(exc).__name__}") from None


def project_bytes(raw: bytes) -> bytes:
    """``project(raw)`` in canonical form (the Radar seal's form), newline-terminated."""
    return canonical(project(raw)) + b"\n"
