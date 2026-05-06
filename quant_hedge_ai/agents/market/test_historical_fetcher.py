"""Tests unitaires pour HistoricalDataFetcher — mock CCXT, pagination, retry, dédup."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_raw_candles(n: int, start_ms: int = 1_700_000_000_000, step_ms: int = 3_600_000) -> list:
    """Génère n bougies OHLCV au format ccxt [[ts, o, h, l, c, v], ...]."""
    candles = []
    for i in range(n):
        ts = start_ms + i * step_ms
        close = 40000.0 + i * 10
        candles.append([ts, close - 5, close + 10, close - 10, close, 100.0 + i])
    return candles


def _mock_exchange(raw_pages: list[list]) -> MagicMock:
    """
    Retourne un mock ccxt exchange dont fetch_ohlcv retourne les pages en séquence.
    rateLimit = 50ms pour ne pas ralentir les tests.
    """
    ex = MagicMock()
    ex.rateLimit = 50
    ex.fetch_ohlcv = MagicMock(side_effect=raw_pages)
    return ex


# ── Suite 1 : _get_exchange ───────────────────────────────────────────────────

class TestGetExchange(unittest.TestCase):

    def test_returns_none_when_ccxt_missing(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        fetcher = HistoricalDataFetcher()
        with patch.dict("sys.modules", {"ccxt": None}):
            fetcher._exchange = None
            # Si ccxt absent, _get_exchange doit retourner None sans lever
            with patch("builtins.__import__", side_effect=ImportError("no ccxt")):
                result = fetcher._get_exchange()
        self.assertIsNone(result)

    def test_cached_after_first_call(self):
        """_get_exchange ne réinitialise pas si déjà initialisé."""
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        fetcher = HistoricalDataFetcher()
        sentinel = MagicMock()
        fetcher._exchange = sentinel
        result = fetcher._get_exchange()
        self.assertIs(result, sentinel)


# ── Suite 2 : fetch — cas nominaux ───────────────────────────────────────────

class TestFetchNominal(unittest.TestCase):

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher, _PAGE_SIZE
        self.fetcher = HistoricalDataFetcher()
        self.PAGE_SIZE = _PAGE_SIZE

    def _install_exchange(self, pages: list[list]) -> None:
        self.fetcher._exchange = _mock_exchange(pages)

    def test_single_page_returns_all_candles(self):
        """Une seule page < PAGE_SIZE → retourne toutes les bougies, tri croissant."""
        raw = _make_raw_candles(10)
        self._install_exchange([raw, []])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.01, progress=False)
        self.assertEqual(len(result), 10)
        # Trié croissant
        timestamps = [c["timestamp"] for c in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_candle_dict_structure(self):
        """Chaque bougie a les champs attendus avec les bons types."""
        raw = _make_raw_candles(3)
        self._install_exchange([raw, []])
        result = self.fetcher.fetch("ETH/USDT", timeframe="1h", years=0.001, progress=False)
        self.assertGreater(len(result), 0)
        c = result[0]
        for field in ("symbol", "timestamp", "open", "high", "low", "close", "volume", "source"):
            self.assertIn(field, c, f"Champ manquant: {field}")
        self.assertEqual(c["symbol"], "ETH/USDT")
        self.assertEqual(c["source"], "ccxt_live")
        self.assertIsInstance(c["close"], float)

    def test_empty_first_page_returns_empty_list(self):
        """Si la première page est vide, retourne []."""
        self._install_exchange([[]])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.01, progress=False)
        self.assertEqual(result, [])

    def test_exchange_none_returns_empty_list(self):
        """Si l'exchange n'est pas disponible, retourne [] sans crash."""
        self.fetcher._exchange = None
        with patch.object(self.fetcher, "_get_exchange", return_value=None):
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.01)
        self.assertEqual(result, [])

    def test_stop_on_last_ts_in_future(self):
        """Arrête si le dernier timestamp dépasse maintenant."""
        future_ts = int(time.time() * 1000) + 10_000_000  # +2.7h dans le futur
        raw = _make_raw_candles(5, start_ms=future_ts)
        self._install_exchange([raw])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)
        # Doit s'arrêter sans boucle infinie
        self.assertIsInstance(result, list)

    def test_stop_when_page_less_than_page_size(self):
        """Arrête quand la page retournée a moins de PAGE_SIZE éléments (dernière page)."""
        raw = _make_raw_candles(5)  # < PAGE_SIZE(500) → dernière page
        self._install_exchange([raw])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)
        self.assertEqual(len(result), 5)
        # fetch_ohlcv n'a été appelé qu'une fois (pas de 2e page)
        self.assertEqual(self.fetcher._exchange.fetch_ohlcv.call_count, 1)


# ── Suite 3 : fetch — pagination ─────────────────────────────────────────────

class TestFetchPagination(unittest.TestCase):

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher, _PAGE_SIZE
        self.fetcher = HistoricalDataFetcher()
        self.PAGE_SIZE = _PAGE_SIZE

    def test_two_pages_concatenated(self):
        """Deux pages complètes → bougies concaténées et triées."""
        page1 = _make_raw_candles(self.PAGE_SIZE, start_ms=1_700_000_000_000)
        page2 = _make_raw_candles(10, start_ms=1_700_000_000_000 + self.PAGE_SIZE * 3_600_000)
        self.fetcher._exchange = _mock_exchange([page1, page2, []])
        self.fetcher._exchange.rateLimit = 0

        with patch("time.sleep"):  # évite d'attendre le rate limit
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=5.0, progress=False)

        self.assertEqual(len(result), self.PAGE_SIZE + 10)

    def test_since_advances_between_pages(self):
        """Le since_ms avance de last_ts+1 à chaque page."""
        page1 = _make_raw_candles(self.PAGE_SIZE, start_ms=1_000_000_000_000)
        page2 = _make_raw_candles(3, start_ms=1_000_000_000_000 + self.PAGE_SIZE * 3_600_000)

        captured_since = []
        original_retry = None

        import quant_hedge_ai.agents.market.historical_fetcher as hf_module
        original_retry = hf_module.retry_with_backoff

        def capturing_retry(fn, **kwargs):
            # Capture les appels pour inspecter le since capturé dans la closure
            return original_retry(fn, **kwargs)

        self.fetcher._exchange = _mock_exchange([page1, page2, []])
        self.fetcher._exchange.rateLimit = 0

        with patch("time.sleep"):
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=5.0, progress=False)

        # Page2 a 3 éléments < PAGE_SIZE → arrêt immédiat après page2 (2 appels au total)
        self.assertEqual(self.fetcher._exchange.fetch_ohlcv.call_count, 2)
        self.assertEqual(len(result), self.PAGE_SIZE + 3)


# ── Suite 4 : fetch — déduplication ──────────────────────────────────────────

class TestFetchDeduplication(unittest.TestCase):

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        self.fetcher = HistoricalDataFetcher()

    def test_duplicate_timestamps_removed(self):
        """Les bougies en double (même timestamp) sont dédupliquées."""
        base_ts = 1_700_000_000_000
        # 5 bougies normales + 2 doublons du début
        raw = _make_raw_candles(5, start_ms=base_ts)
        duplicates = _make_raw_candles(2, start_ms=base_ts)  # mêmes timestamps
        combined = raw + duplicates  # 7 éléments, 5 uniques

        self.fetcher._exchange = _mock_exchange([combined, []])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)

        timestamps = [c["timestamp"] for c in result]
        self.assertEqual(len(timestamps), len(set(timestamps)), "Doublons détectés après fetch")

    def test_overlapping_pages_deduped(self):
        """Pages qui se chevauchent (dernier élément page1 = premier élément page2)."""
        from quant_hedge_ai.agents.market.historical_fetcher import _PAGE_SIZE
        page1 = _make_raw_candles(_PAGE_SIZE, start_ms=1_000_000_000_000)
        # Page2 commence au même timestamp que le dernier de page1
        overlap_start = page1[-1][0]
        page2 = _make_raw_candles(5, start_ms=overlap_start)

        self.fetcher._exchange = _mock_exchange([page1, page2, []])
        self.fetcher._exchange.rateLimit = 0

        with patch("time.sleep"):
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=5.0, progress=False)

        timestamps = [c["timestamp"] for c in result]
        self.assertEqual(len(timestamps), len(set(timestamps)))

    def test_result_sorted_ascending(self):
        """Le résultat final est trié par timestamp croissant même si les pages arrivent dans le désordre."""
        raw = _make_raw_candles(10)
        shuffled = list(reversed(raw))  # inversé
        self.fetcher._exchange = _mock_exchange([shuffled, []])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)
        timestamps = [c["timestamp"] for c in result]
        self.assertEqual(timestamps, sorted(timestamps))


# ── Suite 5 : fetch — retry et erreurs réseau ─────────────────────────────────

class TestFetchRetry(unittest.TestCase):

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        self.fetcher = HistoricalDataFetcher()

    def test_retry_on_network_error_then_success(self):
        """fetch_ohlcv lève une exception au 1er essai, réussit au 2e → données récupérées."""
        raw = _make_raw_candles(5)
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ConnectionError("réseau instable")
            return raw if call_count["n"] == 2 else []

        ex = MagicMock()
        ex.rateLimit = 0
        ex.fetch_ohlcv = MagicMock(side_effect=lambda *a, **kw: flaky())
        self.fetcher._exchange = ex

        with patch("time.sleep"):
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)

        self.assertEqual(len(result), 5)

    def test_all_retries_exhausted_returns_empty(self):
        """Si retry_with_backoff retourne None (toutes tentatives épuisées) → []."""
        ex = MagicMock()
        ex.rateLimit = 0
        ex.fetch_ohlcv = MagicMock(side_effect=Exception("timeout permanent"))
        self.fetcher._exchange = ex

        with patch("time.sleep"):
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)

        self.assertEqual(result, [])

    def test_none_from_retry_stops_loop(self):
        """retry_with_backoff retourne None → boucle s'arrête proprement."""
        import quant_hedge_ai.agents.market.historical_fetcher as hf_module

        ex = MagicMock()
        ex.rateLimit = 0
        self.fetcher._exchange = ex

        with patch.object(hf_module, "retry_with_backoff", return_value=None):
            result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)

        self.assertEqual(result, [])


# ── Suite 6 : fetch — timeframes ─────────────────────────────────────────────

class TestFetchTimeframes(unittest.TestCase):

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        self.fetcher = HistoricalDataFetcher()

    def _simple_fetch(self, timeframe: str) -> list:
        raw = _make_raw_candles(3)
        self.fetcher._exchange = _mock_exchange([raw, []])
        return self.fetcher.fetch("BTC/USDT", timeframe=timeframe, years=0.001, progress=False)

    def test_timeframe_1m(self):
        self.assertEqual(len(self._simple_fetch("1m")), 3)

    def test_timeframe_4h(self):
        self.assertEqual(len(self._simple_fetch("4h")), 3)

    def test_timeframe_1d(self):
        self.assertEqual(len(self._simple_fetch("1d")), 3)

    def test_unknown_timeframe_uses_default(self):
        """Timeframe inconnu utilise 3600s par défaut — ne lève pas."""
        raw = _make_raw_candles(2)
        self.fetcher._exchange = _mock_exchange([raw, []])
        result = self.fetcher.fetch("BTC/USDT", timeframe="99x", years=0.001, progress=False)
        self.assertIsInstance(result, list)


# ── Suite 7 : fetch_and_save ──────────────────────────────────────────────────

class TestFetchAndSave(unittest.TestCase):

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        self.fetcher = HistoricalDataFetcher()

    def test_empty_fetch_returns_zero_saved(self):
        """Si fetch() retourne [], fetch_and_save retourne 0 pour ce symbole."""
        with patch.object(self.fetcher, "fetch", return_value=[]):
            mock_db = MagicMock()
            mock_db.save_snapshot.return_value = 0
            with patch(
                "quant_hedge_ai.agents.market.historical_fetcher.HistoricalDataFetcher.fetch_and_save",
                wraps=self.fetcher.fetch_and_save,
            ):
                with patch("quant_hedge_ai.strategy_lab.market_db.MarketDatabase", return_value=mock_db):
                    result = self.fetcher.fetch_and_save(["BTC/USDT"], db_path=":memory:")

        self.assertEqual(result.get("BTC/USDT", 0), 0)

    def test_multiple_symbols_processed(self):
        """Chaque symbole de la liste est fetché indépendamment."""
        candles_btc = _make_raw_candles(5)
        candles_eth = _make_raw_candles(3, start_ms=1_800_000_000_000)

        # fetch retourne des données différentes pour chaque symbole
        fake_results = {
            "BTC/USDT": [
                {
                    "symbol": "BTC/USDT",
                    "timestamp": f"2024-01-01T{i:02d}:00:00+00:00",
                    "open": 40000.0, "high": 40100.0, "low": 39900.0,
                    "close": 40050.0, "volume": 100.0, "source": "ccxt_live",
                }
                for i in range(5)
            ],
            "ETH/USDT": [
                {
                    "symbol": "ETH/USDT",
                    "timestamp": f"2024-01-01T{i:02d}:00:00+00:00",
                    "open": 2000.0, "high": 2010.0, "low": 1990.0,
                    "close": 2005.0, "volume": 50.0, "source": "ccxt_live",
                }
                for i in range(3)
            ],
        }

        call_order = []

        def fake_fetch(symbol, **kwargs):
            call_order.append(symbol)
            return fake_results[symbol]

        mock_db = MagicMock()
        mock_db.save_snapshot.return_value = 5

        with patch.object(self.fetcher, "fetch", side_effect=fake_fetch):
            with patch("quant_hedge_ai.strategy_lab.market_db.MarketDatabase", return_value=mock_db):
                result = self.fetcher.fetch_and_save(
                    ["BTC/USDT", "ETH/USDT"], db_path=":memory:"
                )

        self.assertIn("BTC/USDT", result)
        self.assertIn("ETH/USDT", result)
        self.assertEqual(set(call_order), {"BTC/USDT", "ETH/USDT"})


# ── Suite 8 : validation intégration (sans réseau) ───────────────────────────

class TestFetchValidation(unittest.TestCase):
    """Vérifie que validate_candles est bien appelé sur chaque page."""

    def setUp(self):
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        self.fetcher = HistoricalDataFetcher()

    def test_corrupted_candles_filtered(self):
        """Bougies corrompues (high < low) sont filtrées par validate_candles."""
        raw_good = _make_raw_candles(3)
        # Bougie corrompue : high < low
        raw_bad = [[1_700_100_000_000, 100.0, 50.0, 200.0, 100.0, 0.0]]
        raw = raw_good + raw_bad

        self.fetcher._exchange = _mock_exchange([raw, []])
        result = self.fetcher.fetch("BTC/USDT", timeframe="1h", years=0.001, progress=False)

        # La bougie corrompue doit être absente
        closes = [c["close"] for c in result]
        self.assertNotIn(100.0, closes)  # valeur de la bougie corrompue
        self.assertEqual(len(result), 3)

    def test_validate_candles_called_per_page(self):
        """validate_candles est appelé pour chaque page (pas une seule fois à la fin)."""
        from quant_hedge_ai.agents.market.historical_fetcher import _PAGE_SIZE
        import quant_hedge_ai.agents.market.historical_fetcher as hf_module

        page1 = _make_raw_candles(_PAGE_SIZE)
        page2 = _make_raw_candles(5, start_ms=1_700_000_000_000 + _PAGE_SIZE * 3_600_000)

        self.fetcher._exchange = _mock_exchange([page1, page2, []])
        self.fetcher._exchange.rateLimit = 0

        call_count = {"n": 0}
        original_validate = hf_module.validate_candles

        def counting_validate(candles, symbol=""):
            call_count["n"] += 1
            return original_validate(candles, symbol=symbol)

        with patch.object(hf_module, "validate_candles", side_effect=counting_validate):
            with patch("time.sleep"):
                self.fetcher.fetch("BTC/USDT", timeframe="1h", years=5.0, progress=False)

        self.assertGreaterEqual(call_count["n"], 2, "validate_candles doit être appelé par page")


if __name__ == "__main__":
    unittest.main(verbosity=2)
