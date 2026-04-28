# market_db.py (stub)


class MarketDatabase:
    """Stub minimal pour MarketDatabase. Remplacez par une vraie implémentation si besoin."""

    def __init__(self, *args, **kwargs):
        pass

    def save_snapshot(self, market):
        self._latest = market

    def get_latest_snapshot(self) -> dict:
        return getattr(self, "_latest", {})
