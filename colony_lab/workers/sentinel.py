"""SENTINEL-01 as a lab worker: fixture providers and a fixed clock only."""

from datetime import datetime, timezone

# Pinned by criteria r1: the fixtures were collected at this instant (r0 left it unpinned).
LAB_CLOCK = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
PAYLOAD_FIELDS = {"question", "shortcut", "scenario"}


def run(payload: dict) -> dict:
    if type(payload) is not dict or set(payload) != PAYLOAD_FIELDS:
        raise ValueError("PAYLOAD_INVALID")
    from governance_tower.scenarios import demo_providers
    from governance_tower.sentinel.agent import Sentinel

    def clock():
        return LAB_CLOCK

    github, host = demo_providers(payload["scenario"], clock)
    return Sentinel(github, host, clock).ask(payload["question"], payload["shortcut"]).to_dict()
