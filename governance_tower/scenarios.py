"""Scénarios de démonstration SYNTHETIC et construction des fournisseurs.

Les lectures réelles sont opt-in, explicites, et ne se combinent jamais avec des
fixtures (refus par ``Sentinel``).
"""

from __future__ import annotations

from pathlib import Path

from governance_tower.contracts import utc_now
from governance_tower.providers.base import Clock, GithubReadProvider, HostObservationProvider
from governance_tower.providers.github import FixtureGithubProvider, HttpGithubProvider
from governance_tower.providers.host import (
    FixtureHostProvider,
    NotConfiguredHostProvider,
    OperatorApiHostProvider,
    SnapshotDirectoryHostProvider,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: scénario → (fixture GitHub, fixture hôte)
SCENARIOS: dict[str, tuple[str, str]] = {
    "nominal": ("nominal", "nominal"),
    "injection": ("injection", "injection"),
    "drift": ("nominal", "drift"),
    "stale": ("nominal", "stale"),
    "host_unavailable": ("nominal", "host_unavailable"),
    "github_denied": ("github_denied", "nominal"),
}


def demo_providers(scenario: str, clock: Clock = utc_now) -> tuple[GithubReadProvider, HostObservationProvider]:
    if scenario not in SCENARIOS:
        raise KeyError(f"scénario inconnu: {scenario}")
    gh, host = SCENARIOS[scenario]
    return (
        FixtureGithubProvider(FIXTURES / "github" / f"{gh}.json", clock),
        FixtureHostProvider(FIXTURES / "host" / f"{host}.json", clock),
    )


def live_providers(
    *,
    github_live: bool,
    host_snapshots: Path | None,
    host_operator_api: str | None,
    clock: Clock = utc_now,
) -> tuple[GithubReadProvider, HostObservationProvider]:
    """Fournisseurs réels opt-in. Sans option explicite, l'hôte reste NOT_AVAILABLE."""
    if host_snapshots is not None and host_operator_api is not None:
        raise ValueError("choisir une seule source hôte")
    if not github_live:
        raise ValueError("le mode lecture réelle exige --github-live explicite")
    github = HttpGithubProvider(clock=clock)
    host: HostObservationProvider
    if host_snapshots is not None:
        host = SnapshotDirectoryHostProvider(host_snapshots, clock)
    elif host_operator_api is not None:
        host = OperatorApiHostProvider(host_operator_api, clock)
    else:
        host = NotConfiguredHostProvider(clock)
    return github, host
