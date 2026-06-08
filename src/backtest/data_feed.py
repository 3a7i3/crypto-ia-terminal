class HistoricalDataFeed:
    def __init__(self, candles: list[dict]):
        self.candles = candles
        self.index = 0

    def next(self) -> dict | None:
        if self.index >= len(self.candles):
            return None
        candle = self.candles[self.index]
        self.index += 1
        return candle

    def reset(self):
        self.index = 0
