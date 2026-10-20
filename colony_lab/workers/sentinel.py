"""SENTINEL-01 as a lab worker: fixture providers and a fixed clock only."""

from datetime import datetime, timezone

LAB_CLOCK = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
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
