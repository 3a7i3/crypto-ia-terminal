"""
RegimeGate — filtre les signaux selon le régime de marché détecté.

Wrapping pur : s'intercale devant n'importe quel agent sans le modifier.
Maintient une fenêtre glissante de candles pour classifier le régime courant.
"""

from src.analytics.regime_detector import RegimeDetector


class RegimeGate:
    def __init__(
        self,
        agent,
        allowed_regimes: set[str],
        detector: RegimeDetector | None = None,
        window: int = 30,
    ):
        self._agent = agent
        self._allowed = set(allowed_regimes)
        self._detector = detector or RegimeDetector()
        self._window = window
        self._history: list[dict] = []
        self.last_regime: str = "sideways"
        self.blocked: int = 0
        self.passed: int = 0

    def on_market(self, candle: dict):
        self._history.append(candle)
        if len(self._history) > self._window:
            self._history.pop(0)

        self.last_regime = self._detector.classify(self._history)

        if self.last_regime not in self._allowed:
            self.blocked += 1
            return None

        signal = self._agent.on_market(candle)
        if signal is not None:
            self.passed += 1
        return signal

    def reset(self) -> None:
        self._history.clear()
        self.last_regime = "range"
        self.blocked = 0
        self.passed = 0
