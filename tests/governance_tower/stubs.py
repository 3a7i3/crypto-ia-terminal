"""Fournisseurs factices minimaux pour tester Sentinel indépendamment des fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

from governance_tower.contracts import (
    Availability,
    Domain,
    EvidenceRef,
    HostSnapshot,
    Observation,
    Provenance,
    RepositorySnapshot,
    SourceKind,
)
from governance_tower.providers.base import ProviderInfo

T0 = "2026-10-16T12:00:00Z"
PINNED = "116634be0d3c015cce1cfa58be7da7255414fbfd"
HEAD = "de5e0000000000000000000000000000000000a1"
OTHER = "de5e000000000000000000000000000000000bad"


def clock() -> datetime:
    return datetime(2026, 10, 16, 12, 0, 1, tzinfo=timezone.utc)


def _ev(eid: str, source: SourceKind) -> EvidenceRef:
    return EvidenceRef(eid, source, f"fixture:stub/{eid}", Provenance.SYNTHETIC, T0)


class StubGithub:
    info = ProviderInfo("stub-github", Provenance.SYNTHETIC, False, "stub")

    def __init__(self, head: str | None = HEAD, ci: str = "SUCCESS", titles: tuple[str, ...] = ()):
        self.head, self.ci, self.titles = head, ci, titles
        self.calls: list[str] = []

    def repository_snapshot(self) -> RepositorySnapshot:
        self.calls.append("repository_snapshot")
        if self.head is None:
            return RepositorySnapshot("3a7i3/crypto-ia-terminal", T0, Availability.DENIED, (
                Observation.absent("gh-repo", Domain.REPOSITORY, "dépôt", Availability.DENIED, "HTTP_401"),
            ))
        e = _ev("ev-gh-head", SourceKind.GITHUB)
        obs = [
            Observation("gh-repo", Domain.REPOSITORY, "dépôt", Availability.AVAILABLE,
                        {"default_branch": "main", "head_sha": self.head}, None, (e,)),
            Observation("gh-ci", Domain.CI, "CI du HEAD", Availability.AVAILABLE, {"status": self.ci},
                        None, (_ev("ev-gh-ci", SourceKind.GITHUB),)),
        ]
        if self.titles:
            obs.append(Observation("gh-prs", Domain.PULL_REQUESTS, "PR ouvertes", Availability.AVAILABLE,
                                   [{"number": i + 1, "title": t} for i, t in enumerate(self.titles)], None,
                                   (_ev("ev-gh-prs", SourceKind.GITHUB),), untrusted_content=True))
        return RepositorySnapshot("3a7i3/crypto-ia-terminal", T0, Availability.AVAILABLE, tuple(obs),
                                  default_branch="main", head_sha=self.head)

    def locate_code(self, terms):
        self.calls.append("locate_code")
        return Observation("gh-code", Domain.CODE, "chemins", Availability.AVAILABLE,
                           {"terms": list(terms), "paths": ["observability/publish_runtime_service.py"]}, None,
                           (_ev("ev-gh-code", SourceKind.GITHUB),))

    def compare_commits(self, base, head):
        self.calls.append("compare_commits")
        return Observation("gh-compare", Domain.REPOSITORY, "commits entre runtime et main", Availability.AVAILABLE,
                           {"base": base, "head": head, "ahead_by": 42}, None,
                           (_ev("ev-gh-compare", SourceKind.GITHUB),), untrusted_content=True)


class StubHost:
    info = ProviderInfo("stub-host", Provenance.SYNTHETIC, False, "stub")

    def __init__(self, deployed: str | None = PINNED, availability=Availability.AVAILABLE, active=("active", "running"),
                 restarts: int = 0, age: float | None = None, journal: str | None = None):
        self.deployed, self.availability, self.active = deployed, availability, active
        self.restarts, self.age, self.journal = restarts, age, journal
        self.calls: list[str] = []

    def host_snapshot(self) -> HostSnapshot:
        self.calls.append("host_snapshot")
        if self.availability not in (Availability.AVAILABLE, Availability.STALE):
            return HostSnapshot("VPS", T0, self.availability, (), reason="UNREACHABLE")
        e = _ev("ev-host-svc", SourceKind.HOST)
        obs = [
            Observation("host-svc", Domain.HOST_SERVICE, "crypto-advisor.service", self.availability,
                        {"unit": "crypto-advisor.service", "active_state": self.active[0],
                         "sub_state": self.active[1], "restart_count": self.restarts}, None, (e,),
                        freshness_age_s=self.age),
        ]
        if self.deployed:
            obs.append(Observation("host-dep", Domain.HOST_DEPLOYMENT, "déploiement", self.availability,
                                   {"source_code_sha": self.deployed}, None, (_ev("ev-host-dep", SourceKind.HOST),),
                                   freshness_age_s=self.age))
        if self.journal:
            obs.append(Observation("host-journal", Domain.HOST_SERVICE, "journal_excerpt", Availability.AVAILABLE,
                                   self.journal, None, (_ev("ev-host-journal", SourceKind.HOST),),
                                   untrusted_content=True))
        return HostSnapshot("VPS", T0, self.availability, tuple(obs), deployed_source_sha=self.deployed)


class ExplodingHost(StubHost):
    def host_snapshot(self):
        self.calls.append("host_snapshot")
        raise RuntimeError("boom")
