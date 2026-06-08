from typing import Callable


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, fn: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(fn)

    def unsubscribe(self, event_type: str, fn: Callable) -> None:
        bucket = self._subscribers.get(event_type, [])
        if fn in bucket:
            bucket.remove(fn)

    def emit(self, event: dict) -> None:
        for fn in self._subscribers.get(event.get("type", ""), []):
            fn(event)

    def clear(self) -> None:
        self._subscribers.clear()
