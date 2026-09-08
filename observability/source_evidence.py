"""observability/source_evidence.py — O-02W-C source/worktree/deployment
evidence capture.

Per docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md §15
(RUNTIME_IDENTITY_CONTRACT, four-way source-claim/runtime-proof
distinction): `git rev-parse HEAD` alone is only a claimed checkout SHA —
never proof of what bytes are executing in process memory. This module
captures that claim, plus worktree cleanliness and deployment-evidence
status, ONCE at process bootstrap (a bounded boot-time mechanism, not a
per-cycle git invocation, §15) and returns an immutable evidence bundle
that every snapshot write for this process lifetime reuses unchanged.

`runtime_sha_evidence_status` NEVER becomes `VERIFIED` here — no
independent runtime-attestation mechanism exists in this codebase (that
is explicitly deferred to the future T-1 mission, §15/§21.2). A
`deployment_evidence.status = VERIFIED` value (proving only that files
were transferred) never auto-upgrades `runtime_sha_evidence_status`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DeploymentEvidence:
    """Sanitized deployment-evidence object (§15 R4.2 schema).

    `evidence_ref` must never carry a secret path, credential, token, or
    environment dump — a sanitized reference only (e.g. a deploy-tag name).
    """

    status: str = "UNKNOWN"  # VERIFIED | CLAIMED_ONLY | UNKNOWN
    source: Optional[str] = None  # deploy_tag | deploy_audit | post_deploy_verification | None
    evidence_ref: Optional[str] = None
    observed_at_utc: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "evidence_ref": self.evidence_ref,
            "observed_at_utc": self.observed_at_utc,
        }


@dataclass(frozen=True)
class SourceEvidence:
    """Immutable bundle of the four envelope fields defined by §15/§14."""

    source_sha: Optional[str]
    worktree_state: str  # CLEAN | DIRTY | UNKNOWN
    deployment_evidence: DeploymentEvidence
    runtime_sha_evidence_status: str  # CLAIMED_ONLY | UNKNOWN (never VERIFIED here)

    def to_dict(self) -> dict:
        return {
            "source_sha": self.source_sha,
            "worktree_state": self.worktree_state,
            "deployment_evidence": self.deployment_evidence.to_dict(),
            "runtime_sha_evidence_status": self.runtime_sha_evidence_status,
        }


def _run_git(args: list[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except Exception:
        return None


def capture_source_evidence(
    cwd: Optional[str] = None,
    run_git_status: bool = True,
    deployment_evidence: Optional[DeploymentEvidence] = None,
) -> SourceEvidence:
    """Capture the four envelope fields once, at process bootstrap.

    `run_git_status=False` simulates "worktree cleanliness was never
    checked" -> `worktree_state=UNKNOWN` (§22 test 20), distinct from an
    actual `git status --porcelain` call that reports no changes (CLEAN)
    or changes (DIRTY).

    A `deployment_evidence.status == VERIFIED` value is accepted as-is (it
    proves file transfer only) but NEVER upgrades
    `runtime_sha_evidence_status`, which defaults to `CLAIMED_ONLY` if a
    source SHA claim exists at all, else `UNKNOWN` (§22 test 19).
    """

    source_sha = _run_git(["rev-parse", "HEAD"], cwd=cwd)

    worktree_state = "UNKNOWN"
    if run_git_status:
        porcelain = _run_git(["status", "--porcelain"], cwd=cwd)
        if porcelain is not None:
            worktree_state = "DIRTY" if porcelain else "CLEAN"

    dep_evidence = deployment_evidence or DeploymentEvidence()

    runtime_sha_evidence_status = "CLAIMED_ONLY" if source_sha else "UNKNOWN"

    return SourceEvidence(
        source_sha=source_sha,
        worktree_state=worktree_state,
        deployment_evidence=dep_evidence,
        runtime_sha_evidence_status=runtime_sha_evidence_status,
    )


__all__ = [
    "DeploymentEvidence",
    "SourceEvidence",
    "capture_source_evidence",
]
