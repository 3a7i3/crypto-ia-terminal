from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque


class DataPublisher(ABC):
    @abstractmethod
    async def publish_event(self, event: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish_snapshot(self, snapshot: dict) -> None:
        raise NotImplementedError


class InMemoryPublisher(DataPublisher):
    def __init__(self, max_events: int = 5000, max_snapshots: int = 1000) -> None:
        self.events: deque[dict] = deque(maxlen=max_events)
        self.snapshots: deque[dict] = deque(maxlen=max_snapshots)

    async def publish_event(self, event: dict) -> None:
        self.events.append(event)

    async def publish_snapshot(self, snapshot: dict) -> None:
        self.snapshots.append(snapshot)

    def latest_events(self, n: int = 50) -> list[dict]:
        return list(self.events)[-n:]

    def latest_snapshots(self, n: int = 10) -> list[dict]:
        return list(self.snapshots)[-n:]
