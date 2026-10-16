"""GOV-TOWER-00 lot B — contrats fermés (UNKNOWN ≠ 0, provenance, preuves)."""

from __future__ import annotations

import pytest

from governance_tower.contracts import (
    DEFAULT_FORBIDDEN_SCOPE,
    AgentRun,
    Availability,
    ClaimStatus,
    ContractError,
    Discrepancy,
    DiscrepancyClass,
    Domain,
    EvidenceRef,
    Finding,
    HostSnapshot,
    Intent,
    MissionProposal,
    Observation,
    Provenance,
    RepositorySnapshot,
    SentinelAnswer,
    Severity,
    SourceKind,
    Statement,
)
from governance_tower.redaction import (
    is_forbidden_path,
    normalize_repo_path,
    redact,
    sanitize_untrusted,
)
from governance_tower.references import load_pinned_references

T0 = "2026-10-16T12:00:00Z"
T1 = "2026-10-16T12:00:05Z"


def ev(eid="ev-1", prov=Provenance.SYNTHETIC, locator=None, **kw):
    if locator is None:
        locator = "fixture:github/nominal" if prov is Provenance.SYNTHETIC else "https://github.com/x/y"
    return EvidenceRef(eid, SourceKind.GITHUB, locator, prov, T0, **kw)


def obs(avail=Availability.AVAILABLE, value=1, reason=None, evidence=None, **kw):
    return Observation(
        "obs-1", Domain.CI, "ci", avail, value, reason, (ev(),) if evidence is None else evidence, **kw
    )


def answer(*statements):
    return SentinelAnswer("résumé", tuple(statements), ())


def run(evidence, statements=(), mode="DEMO", **kw):
    return AgentRun(
        run_id="run-1",
        request="q",
        intent=Intent.HELP,
        started_at_utc=T0,
        finished_at_utc=T1,
        tool_calls=(),
        evidence=tuple(evidence),
        sources=(),
        answer=answer(*statements),
        reasoner="deterministic-demo",
        mode=mode,
        **kw,
    )


# ── Absence ≠ zéro ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "avail",
    [Availability.NOT_AVAILABLE, Availability.DENIED, Availability.UNKNOWN, Availability.RATE_LIMITED, Availability.ERROR],
)
def test_absent_states_never_carry_a_value_not_even_zero(avail):
    with pytest.raises(ContractError):
        obs(avail, value=0, reason="x")
    with pytest.raises(ContractError):
        obs(avail, value=[], reason="x")
    o = obs(avail, value=None, reason="SOURCE_DOWN", evidence=())
    assert not o.has_value and o.value is None


def test_real_zero_is_distinct_from_unknown():
    zero = obs(Availability.AVAILABLE, value=0)
    unknown = obs(Availability.UNKNOWN, value=None, reason="NOT_MEASURED", evidence=())
    assert zero.has_value and zero.value == 0
    assert not unknown.has_value
    assert zero.availability != unknown.availability


def test_absence_requires_reason_and_available_requires_evidence():
    with pytest.raises(ContractError):
        obs(Availability.NOT_AVAILABLE, value=None, reason=None, evidence=())
    with pytest.raises(ContractError):
        obs(Availability.AVAILABLE, value=1, evidence=())


def test_stale_requires_measured_age():
    with pytest.raises(ContractError):
        obs(Availability.STALE, value=1)
    assert obs(Availability.STALE, value=1, freshness_age_s=300.0).has_value


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), object()])
def test_non_finite_or_arbitrary_values_refused(bad):
    with pytest.raises(ContractError):
        obs(value=bad)


# ── Horodatage et provenance ─────────────────────────────────────────────────


@pytest.mark.parametrize("stamp", ["2026-10-16 12:00:00", "2026-10-16T12:00:00+00:00", "", "2026-13-40T00:00:00Z"])
def test_utc_format_is_explicit(stamp):
    with pytest.raises(ContractError):
        EvidenceRef("e", SourceKind.GITHUB, "fixture:x", Provenance.SYNTHETIC, stamp)


def test_future_observation_refused():
    with pytest.raises(ContractError):
        ev(observed_at_utc="2026-10-16T13:00:00Z")


def test_invalid_sha_refused():
    with pytest.raises(ContractError):
        ev(source_sha="abc")
    with pytest.raises(ContractError):
        ev(source_sha="G" * 40)


def test_fixture_locator_cannot_masquerade_as_live_and_vice_versa():
    with pytest.raises(ContractError):
        EvidenceRef("e", SourceKind.HOST, "fixture:host", Provenance.LIVE_READ, T0)
    with pytest.raises(ContractError):
        EvidenceRef("e", SourceKind.HOST, "snapshot:runtime_service", Provenance.SYNTHETIC, T0)


def test_mixed_synthetic_and_live_refused_in_snapshot_and_run():
    live = ev("ev-live", Provenance.LIVE_READ)
    fake = ev("ev-fake", Provenance.SYNTHETIC)
    o1 = Observation("o1", Domain.CI, "a", Availability.AVAILABLE, 1, None, (live,))
    o2 = Observation("o2", Domain.CI, "b", Availability.AVAILABLE, 1, None, (fake,))
    with pytest.raises(ContractError):
        RepositorySnapshot("x/y", T0, Availability.AVAILABLE, (o1, o2))
    with pytest.raises(ContractError):
        run([live, fake])
    with pytest.raises(ContractError):
        run([live], mode="DEMO")
    with pytest.raises(ContractError):
        run([fake], mode="LIVE_READ")


def test_unknown_fields_refused_on_load():
    raw = {
        "evidence_id": "e",
        "source": "GITHUB",
        "locator": "fixture:x",
        "provenance": "SYNTHETIC",
        "collected_at_utc": T0,
        "trusted": True,
    }
    with pytest.raises(ContractError):
        EvidenceRef.from_dict(raw)
    raw.pop("trusted")
    assert EvidenceRef.from_dict(raw).evidence_id == "e"


def test_bounded_text_and_lists():
    with pytest.raises(ContractError):
        obs(limits=tuple(f"l{i}" for i in range(500)))
    with pytest.raises(ContractError):
        Statement("x" * 10_000, ClaimStatus.INFERRED)
    with pytest.raises(ContractError):
        Statement("ligne\x00cachée", ClaimStatus.INFERRED)


# ── Snapshots ────────────────────────────────────────────────────────────────


def test_unavailable_host_cannot_claim_a_deployed_sha():
    with pytest.raises(ContractError):
        HostSnapshot("vps", T0, Availability.NOT_AVAILABLE, (), deployed_source_sha="a" * 40, reason="down")
    with pytest.raises(ContractError):
        HostSnapshot("vps", T0, Availability.NOT_AVAILABLE, ())
    HostSnapshot("vps", T0, Availability.NOT_AVAILABLE, (), reason="VPS_NOT_CONFIGURED")


def test_unavailable_repo_cannot_claim_head():
    with pytest.raises(ContractError):
        RepositorySnapshot("x/y", T0, Availability.DENIED, (), head_sha="a" * 40)


# ── Comparaisons, constats, propositions ─────────────────────────────────────


def test_conclusive_discrepancy_requires_both_facts_and_evidence():
    with pytest.raises(ContractError):
        Discrepancy("d", "s", DiscrepancyClass.POSSIBLE_DRIFT, "e", "x", (ev(),), github_value="a")
    with pytest.raises(ContractError):
        Discrepancy("d", "s", DiscrepancyClass.ALIGNED, "e", "x", (), github_value="a", host_value="a")
    Discrepancy("d", "s", DiscrepancyClass.INSUFFICIENT_EVIDENCE, "e", "VPS non disponible", ())


def test_finding_is_candidate_only_and_observed_needs_evidence():
    with pytest.raises(ContractError):
        Finding("f", "t", Severity.INFO, "r", ClaimStatus.OBSERVED, (), "i")
    with pytest.raises(ContractError):
        Finding("f", "t", Severity.INFO, "r", ClaimStatus.INFERRED, (), "i", status="APPROVED")


def test_mission_proposal_has_no_authority_and_keeps_forbidden_scope():
    p = MissionProposal("p", "t", "f-1", "d", ("docs",), ("preuve",), ("pytest",))
    assert p.authority == "NONE" and p.execution == "NOT_EXECUTED"
    assert set(DEFAULT_FORBIDDEN_SCOPE) <= set(p.forbidden_scope)
    with pytest.raises(ContractError):
        MissionProposal("p", "t", "f-1", "d", (), (), (), authority="OPERATOR")
    with pytest.raises(ContractError):
        MissionProposal("p", "t", "f-1", "d", (), (), (), forbidden_scope=())


def test_observed_statement_needs_known_evidence():
    with pytest.raises(ContractError):
        Statement("x", ClaimStatus.OBSERVED)
    with pytest.raises(ContractError):
        run([ev("ev-1")], [Statement("x", ClaimStatus.OBSERVED, ("ev-missing",))])
    r = run([ev("ev-1")], [Statement("x", ClaimStatus.OBSERVED, ("ev-1",))])
    assert r.to_dict()["operational_authority"] == "DENIED"


def test_agent_identity_cannot_be_escalated():
    with pytest.raises(ContractError):
        run([], capability="WRITE")
    with pytest.raises(ContractError):
        run([], operational_authority="GRANTED")


# ── Rédaction et chemins ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "A" * 36,
        "github_pat_" + "B" * 40,
        "sk-ant-api03-" + "c" * 30,
        "AKIA" + "D" * 16,
        "123456789:" + "E" * 35,
        "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----",
        "MEXC_API_SECRET=abcdef123456",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    ],
)
def test_secrets_are_redacted(secret):
    out, n = redact(f"avant {secret} après")
    assert n >= 1 and "[REDACTED]" in out
    assert secret.split("\n")[0] not in out or secret.startswith("-----")
    assert "abcdef123456" not in out and "A" * 36 not in out


def test_untrusted_text_is_bounded_and_controls_stripped():
    r = sanitize_untrusted("a\x1b[31m" + "x" * 2000 + "‮", limit=100)
    assert r.truncated and len(r.text) <= 100 and "\x1b" not in r.text


@pytest.mark.parametrize(
    "path",
    [".env", "config/.env.production", "keys/id_rsa", "a/b/server.pem", ".git/config", "secrets/x.txt",
     "../etc/passwd", "/etc/shadow", "a/../../b", "~/.ssh/config", "a\\b", "deploy/credentials.json"],
)
def test_forbidden_paths(path):
    assert is_forbidden_path(path)


@pytest.mark.parametrize("path", ["README.md", "observability/runtime_service_contract.py", "docs/a/b.md"])
def test_allowed_paths(path):
    assert not is_forbidden_path(path)
    assert normalize_repo_path(path) == path


def test_pinned_reference_is_declared_not_observed():
    (ref,) = load_pinned_references(collected_at_utc=T0)
    assert ref.runtime_source_sha == "116634be0d3c015cce1cfa58be7da7255414fbfd"
    assert ref.epoch_id == "BURN-IN-EPOCH-01-20260926T064144Z"
    assert ref.evidence.provenance is Provenance.DECLARED_REFERENCE
    assert ref.evidence.locator.endswith("/issues/286")


def test_secret_redaction_precedes_truncation():
    from governance_tower.redaction import sanitize_untrusted
    secret = "ghp_" + "A" * 36
    result = sanitize_untrusted("x" * 189 + " " + secret, limit=210)
    assert "ghp_" not in result.text and result.redactions == 1 and result.truncated
