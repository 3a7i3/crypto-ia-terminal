"""
Walk-forward validation : découpe un historique en fenêtres glissantes
et retourne la liste de HistoricalDataFeed pour chaque fenêtre.

Utilisé pour valider une stratégie sur données réelles diversifiées
sans introduire de look-ahead bias.
"""

from src.backtest.data_feed import HistoricalDataFeed


def sliding_windows(
    candles: list[dict],
    window: int = 120,
    step: int = 15,
) -> list[HistoricalDataFeed]:
    """
    Découpe `candles` en fenêtres de taille `window` avec un pas `step`.
    Exemple : 500 candles, window=120, step=15 → ~25 fenêtres.
    """
    feeds = []
    i = 0
    while i + window <= len(candles):
        feeds.append(HistoricalDataFeed(candles[i : i + window]))
        i += step
    return feeds
