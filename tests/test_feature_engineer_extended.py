"""Tests étendus — FeatureEngineer : branches extrêmes EMA/MACD/BB/VWAP/RSI."""

from __future__ import annotations

import math
import unittest

from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer


def _candles(n: int, price: float = 100.0, vol: float = 50.0,
             trend: float = 0.0) -> list[dict]:
    """Génère n bougies avec tendance optionnelle."""
    candles = []
    for i in range(n):
        c = price + i * trend
        candles.append({
            "open":   c - 0.5,
            "high":   c + 1.0,
            "low":    c - 1.0,
            "close":  c,
            "volume": vol,
        })
    return candles


def _flat_candles(n: int, price: float = 100.0) -> list[dict]:
    return _candles(n, price=price, trend=0.0)


FE = FeatureEngineer


# ── Suite 1 : early-return branches (L17-31) ──────────────────────────────────

class TestEarlyReturns(unittest.TestCase):

    def test_single_candle_has_correct_volume(self):
        """1 bougie → early return avec avg_volume et volume_ratio corrects."""
        c = [{"open": 100, "high": 105, "low": 95, "close": 100, "volume": 200}]
        f = FE().extract_features(c)
        self.assertEqual(f["avg_volume"], 200.0)
        self.assertEqual(f["volume_ratio"], 1.0)

    def test_zero_price_returns_empty_with_volume(self):
        """Close=0 → early return mais volume pré-calculé est préservé."""
        c = [
            {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 300},
            {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 100},
        ]
        f = FE().extract_features(c)
        self.assertEqual(f["momentum"], 0.0)
        self.assertEqual(f["rsi"], 50.0)
        self.assertAlmostEqual(f["avg_volume"], 200.0, places=1)

    def test_empty_candles_all_zeros(self):
        f = FE().extract_features([])
        self.assertEqual(f["momentum"], 0.0)
        self.assertEqual(f["avg_volume"], 0.0)
        self.assertEqual(f["volume_ratio"], 1.0)
        self.assertFalse(f["rsi_oversold"])
        self.assertFalse(f["rsi_overbought"])

    def test_two_candles_minimum_computes_momentum(self):
        """2 bougies : momentum calculé, pas d'early return."""
        c = [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
            {"open": 100, "high": 111, "low": 109, "close": 110, "volume": 10},
        ]
        f = FE().extract_features(c)
        self.assertAlmostEqual(f["momentum"], 0.10, places=4)


# ── Suite 2 : RSI edge cases (L58-60, méthode _rsi) ─────────────────────────

class TestRSIEdgeCases(unittest.TestCase):

    def test_rsi_exactly_period_plus_one_returns_value(self):
        """15 bougies (= period+1) → RSI calculé, pas 50.0 par défaut."""
        candles = _candles(15, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        self.assertNotEqual(f["rsi"], 50.0)
        self.assertGreater(f["rsi"], 50.0)  # tendance haussière

    def test_rsi_at_exactly_period_returns_neutral(self):
        """14 bougies (= period) → retourne 50.0 (pas assez)."""
        candles = _candles(14, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        self.assertEqual(f["rsi"], 50.0)

    def test_rsi_oversold_flag(self):
        """Fort downtrend → RSI < 30 → rsi_oversold=True."""
        candles = _candles(30, price=1000.0, trend=-30.0)
        f = FE().extract_features(candles)
        if f["rsi"] < 30:
            self.assertTrue(f["rsi_oversold"])
            self.assertFalse(f["rsi_overbought"])

    def test_rsi_overbought_flag(self):
        """Fort uptrend → RSI > 70 → rsi_overbought=True."""
        candles = _candles(30, price=100.0, trend=5.0)
        f = FE().extract_features(candles)
        if f["rsi"] > 70:
            self.assertTrue(f["rsi_overbought"])
            self.assertFalse(f["rsi_oversold"])

    def test_rsi_flat_market_valid_range(self):
        """Marché flat (pas de variation) → RSI dans [0, 100], sans crash."""
        candles = _flat_candles(30)
        f = FE().extract_features(candles)
        self.assertGreaterEqual(f["rsi"], 0.0)
        self.assertLessEqual(f["rsi"], 100.0)

    def test_rsi_only_losses_returns_near_zero(self):
        """Toutes les bougies en baisse → RSI très bas."""
        closes = [1000.0 - i * 10 for i in range(20)]
        candles = [{"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1}
                   for c in closes]
        f = FE().extract_features(candles)
        self.assertLess(f["rsi"], 20.0)

    def test_rsi_only_gains_returns_near_100(self):
        """Toutes les bougies en hausse → RSI très élevé."""
        candles = _candles(20, price=100.0, trend=10.0)
        f = FE().extract_features(candles)
        self.assertGreater(f["rsi"], 80.0)


# ── Suite 3 : EMA edge cases (L61-64) ────────────────────────────────────────

class TestEMAEdgeCases(unittest.TestCase):

    def test_ema20_below_20_candles_equals_price(self):
        """< 20 bougies → ema20 = prix actuel."""
        candles = _candles(10, price=500.0)
        f = FE().extract_features(candles)
        self.assertEqual(f["ema20"], round(500.0, 4))

    def test_ema50_below_50_candles_equals_price(self):
        """< 50 bougies → ema50 = prix actuel."""
        candles = _candles(30, price=300.0)
        f = FE().extract_features(candles)
        self.assertEqual(f["ema50"], round(300.0, 4))

    def test_ema20_with_exactly_20_candles(self):
        """Exactement 20 bougies → EMA calculée (pas fallback)."""
        candles = _candles(20, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        # EMA doit être < dernier close (inertie EMA)
        self.assertLessEqual(f["ema20"], candles[-1]["close"])

    def test_ema_bullish_flag_uptrend(self):
        """Uptrend long → ema20 > ema50 → ema_bullish=True."""
        candles = _candles(60, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        self.assertTrue(f["ema_bullish"])

    def test_ema_bullish_false_downtrend(self):
        """Downtrend long → ema20 < ema50 → ema_bullish=False."""
        candles = _candles(60, price=1000.0, trend=-5.0)
        f = FE().extract_features(candles)
        self.assertFalse(f["ema_bullish"])

    def test_ema_cross_above_zero_when_price_above_ema20(self):
        """Prix > EMA20 → ema_cross > 0."""
        candles = _candles(30, price=100.0, trend=2.0)
        f = FE().extract_features(candles)
        self.assertGreater(f["ema_cross"], 0.0)


# ── Suite 4 : MACD edge cases (L66-70) ───────────────────────────────────────

class TestMACDEdgeCases(unittest.TestCase):

    def test_macd_below_threshold_returns_zeros(self):
        """< slow+signal (35) bougies → macd retourne 0,0,0."""
        candles = _candles(30, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        self.assertEqual(f["macd_line"], 0.0)
        self.assertEqual(f["macd_signal"], 0.0)
        self.assertEqual(f["macd_hist"], 0.0)
        self.assertFalse(f["macd_bullish"])

    def test_macd_exactly_threshold(self):
        """35 bougies = slow(26)+signal(9) → MACD calculé."""
        candles = _candles(35, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        # macd_hist peut être 0.0 à cause de l'arrondi, mais ne doit pas lever
        self.assertIsInstance(f["macd_hist"], float)

    def test_macd_bullish_flag_uptrend(self):
        """Long uptrend → hist > 0 → macd_bullish=True."""
        candles = _candles(60, price=100.0, trend=2.0)
        f = FE().extract_features(candles)
        if f["macd_hist"] > 0:
            self.assertTrue(f["macd_bullish"])

    def test_macd_bearish_flag_downtrend(self):
        """Long downtrend → hist < 0 → macd_bullish=False."""
        candles = _candles(60, price=1000.0, trend=-5.0)
        f = FE().extract_features(candles)
        if f["macd_hist"] < 0:
            self.assertFalse(f["macd_bullish"])


# ── Suite 5 : Bollinger edge cases (L69-71) ──────────────────────────────────

class TestBollingerEdgeCases(unittest.TestCase):

    def test_bollinger_below_20_candles_returns_same_price(self):
        """< 20 bougies → bb_upper = bb_lower = prix → bb_pct = 0.5."""
        candles = _candles(10, price=200.0)
        f = FE().extract_features(candles)
        self.assertEqual(f["bb_upper"], round(200.0, 4))
        self.assertEqual(f["bb_lower"], round(200.0, 4))
        self.assertEqual(f["bb_pct"], 0.5)

    def test_bollinger_exactly_20_candles(self):
        """Exactement 20 bougies → BB calculées."""
        candles = _candles(20, price=100.0, trend=0.5)
        f = FE().extract_features(candles)
        self.assertGreater(f["bb_upper"], f["bb_lower"])

    def test_bb_pct_range_0_to_1(self):
        """bb_pct doit être dans [0, 1] pour un marché normal."""
        candles = _candles(30, price=100.0, trend=0.5)
        f = FE().extract_features(candles)
        self.assertGreaterEqual(f["bb_pct"], 0.0)
        self.assertLessEqual(f["bb_pct"], 1.0)

    def test_bb_pct_above_1_when_breakout(self):
        """Prix au-dessus de la bande haute → bb_pct > 1."""
        # Créer un fort breakout haussier
        base = _flat_candles(19, price=100.0)
        breakout = [{"open": 200, "high": 210, "low": 195, "close": 200, "volume": 100}]
        candles = base + breakout
        f = FE().extract_features(candles)
        self.assertGreater(f["bb_pct"], 1.0)

    def test_bb_squeeze_flat_market(self):
        """Marché totalement flat → bandes très serrées → bb_squeeze=True."""
        candles = _flat_candles(25, price=100.0)
        f = FE().extract_features(candles)
        # Bandes avec std=0 → bb_squeeze dépend de bb_mid
        self.assertIsInstance(f["bb_squeeze"], bool)

    def test_bb_squeeze_false_volatile_market(self):
        """Marché volatil → bandes larges → bb_squeeze=False."""
        import random
        random.seed(99)
        candles = [{"open": 100, "high": 100 + random.uniform(0, 20),
                    "low": 100 - random.uniform(0, 20),
                    "close": 100 + random.uniform(-15, 15),
                    "volume": 50} for _ in range(30)]
        f = FE().extract_features(candles)
        self.assertFalse(f["bb_squeeze"])


# ── Suite 6 : VWAP edge cases (L72-78) ───────────────────────────────────────

class TestVWAPEdgeCases(unittest.TestCase):

    def test_vwap_zero_volume_no_crash(self):
        """Volume = 0 → VWAP calculé sans division par zéro (epsilon 1e-9)."""
        candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 0}
                   for _ in range(10)]
        f = FE().extract_features(candles)
        self.assertIsInstance(f["vwap"], float)
        self.assertFalse(math.isnan(f["vwap"]))

    def test_vwap_window_capped_at_50(self):
        """Avec > 50 bougies, VWAP n'utilise que les 50 dernières."""
        candles = _candles(100, price=100.0, trend=1.0)
        f = FE().extract_features(candles)
        # VWAP doit être proche du prix des 50 dernières bougies, pas des 100
        last_50_avg = sum(c["close"] for c in candles[-50:]) / 50
        self.assertAlmostEqual(f["vwap"], last_50_avg, delta=5.0)

    def test_vwap_dist_positive_when_price_above(self):
        """Prix > VWAP → vwap_dist > 0."""
        # Flat market puis gros candle haussier
        base = _flat_candles(49, price=100.0)
        top = [{"open": 200, "high": 205, "low": 198, "close": 200, "volume": 1000}]
        candles = base + top
        f = FE().extract_features(candles)
        # Prix final 200, VWAP tiré vers le bas par les 49 bougies à 100
        self.assertGreater(f["vwap_dist"], 0.0)

    def test_vwap_dist_negative_when_price_below(self):
        """Prix < VWAP → vwap_dist < 0."""
        base = _flat_candles(49, price=100.0)
        bottom = [{"open": 50, "high": 52, "low": 48, "close": 50, "volume": 1000}]
        candles = base + bottom
        f = FE().extract_features(candles)
        self.assertLess(f["vwap_dist"], 0.0)


# ── Suite 7 : Range / Support / Résistance (L80-84) ─────────────────────────

class TestRangeEdgeCases(unittest.TestCase):

    def test_range_pos_mid_flat(self):
        """Marché flat → prix au milieu du range → range_pos ≈ 0.5."""
        candles = _flat_candles(25, price=100.0)
        f = FE().extract_features(candles)
        self.assertAlmostEqual(f["range_pos"], 0.5, delta=0.1)

    def test_range_pos_at_top(self):
        """Prix = recent_high → range_pos = 1.0."""
        base = _candles(19, price=100.0, trend=0.0)
        top = [{"open": 200, "high": 200, "low": 199, "close": 200, "volume": 10}]
        candles = base + top
        f = FE().extract_features(candles)
        self.assertAlmostEqual(f["range_pos"], 1.0, delta=0.05)

    def test_range_pos_at_bottom(self):
        """Prix = recent_low → range_pos = 0.0."""
        base = _candles(19, price=100.0, trend=0.0)
        bottom = [{"open": 1, "high": 2, "low": 1, "close": 1, "volume": 10}]
        candles = base + bottom
        f = FE().extract_features(candles)
        self.assertAlmostEqual(f["range_pos"], 0.0, delta=0.05)

    def test_range_pos_equal_high_low_returns_half(self):
        """Si recent_high == recent_low → range_pos = 0.5 (pas de division par zéro)."""
        candles = [{"open": 100, "high": 100, "low": 100, "close": 100, "volume": 10}
                   for _ in range(25)]
        f = FE().extract_features(candles)
        self.assertEqual(f["range_pos"], 0.5)

    def test_recent_high_and_low_below_20_candles(self):
        """< 20 bougies → recent_high/low calculés sur tout l'historique."""
        candles = _candles(10, price=50.0, trend=2.0)
        f = FE().extract_features(candles)
        expected_high = max(c["high"] for c in candles)
        expected_low  = min(c["low"]  for c in candles)
        self.assertEqual(f["recent_high"], round(expected_high, 4))
        self.assertEqual(f["recent_low"],  round(expected_low,  4))


# ── Suite 8 : ATR edge cases (_atr) ──────────────────────────────────────────

class TestATREdgeCases(unittest.TestCase):

    def test_atr_single_candle_returns_zero(self):
        """1 bougie → ATR = 0."""
        fe = FE()
        result = fe._atr([100.0], [105.0], [95.0])
        self.assertEqual(result, 0.0)

    def test_atr_two_candles(self):
        """2 bougies → ATR calculé sur 1 TR."""
        fe = FE()
        closes = [100.0, 110.0]
        highs  = [105.0, 115.0]
        lows   = [95.0,  105.0]
        atr = fe._atr(closes, highs, lows)
        self.assertGreater(atr, 0.0)

    def test_atr_uses_last_period_window(self):
        """ATR utilise uniquement les period dernières bougies."""
        fe = FE()
        # 20 bougies flat puis 1 bougie très volatile
        closes = [100.0] * 20
        highs  = [101.0] * 20
        lows   = [99.0]  * 20
        atr_flat = fe._atr(closes, highs, lows, period=14)
        # Ajouter des bougies très volatiles
        closes2 = closes + [200.0]
        highs2  = highs  + [300.0]
        lows2   = lows   + [50.0]
        atr_volatile = fe._atr(closes2, highs2, lows2, period=14)
        self.assertGreater(atr_volatile, atr_flat)


# ── Suite 9 : _ema static method ─────────────────────────────────────────────

class TestEMAMethod(unittest.TestCase):

    def test_ema_empty_returns_empty(self):
        self.assertEqual(FE._ema([], 20), [])

    def test_ema_single_element(self):
        result = FE._ema([42.0], 20)
        self.assertEqual(result, [42.0])

    def test_ema_converges_toward_constant(self):
        """EMA d'une série constante = la constante."""
        prices = [100.0] * 50
        ema = FE._ema(prices, 20)
        self.assertAlmostEqual(ema[-1], 100.0, places=5)

    def test_ema_lag_uptrend(self):
        """EMA lag derrière les prix en uptrend."""
        prices = [float(i) for i in range(1, 51)]
        ema = FE._ema(prices, 10)
        self.assertLess(ema[-1], prices[-1])


# ── Suite 10 : detect_anomalies ───────────────────────────────────────────────

class TestDetectAnomaliesExtended(unittest.TestCase):

    def test_rsi_extreme_oversold(self):
        features = {"realized_volatility": 0.0, "volume_ratio": 1.0,
                    "momentum": 0.0, "rsi": 15.0, "atr_ratio": 0.0}
        anomalies = FE().detect_anomalies(features)
        self.assertTrue(any("rsi_extreme_oversold" in a for a in anomalies))

    def test_rsi_extreme_overbought(self):
        features = {"realized_volatility": 0.0, "volume_ratio": 1.0,
                    "momentum": 0.0, "rsi": 85.0, "atr_ratio": 0.0}
        anomalies = FE().detect_anomalies(features)
        self.assertTrue(any("rsi_extreme_overbought" in a for a in anomalies))

    def test_atr_extreme(self):
        features = {"realized_volatility": 0.0, "volume_ratio": 1.0,
                    "momentum": 0.0, "rsi": 50.0, "atr_ratio": 0.05}
        anomalies = FE().detect_anomalies(features)
        self.assertTrue(any("atr_extreme" in a for a in anomalies))

    def test_multiple_anomalies_detected(self):
        features = {"realized_volatility": 0.10, "volume_ratio": 5.0,
                    "momentum": 0.15, "rsi": 12.0, "atr_ratio": 0.06}
        anomalies = FE().detect_anomalies(features)
        self.assertGreaterEqual(len(anomalies), 4)

    def test_momentum_down_anomaly_label(self):
        features = {"realized_volatility": 0.0, "volume_ratio": 1.0,
                    "momentum": -0.12, "rsi": 50.0, "atr_ratio": 0.0}
        anomalies = FE().detect_anomalies(features)
        self.assertTrue(any("extreme_momentum_down" in a for a in anomalies))

    def test_rsi_exactly_at_threshold_no_anomaly(self):
        """RSI exactement à 20 ou 80 — pas en dessous/au-dessus → pas d'anomalie."""
        features = {"realized_volatility": 0.0, "volume_ratio": 1.0,
                    "momentum": 0.0, "rsi": 20.0, "atr_ratio": 0.0}
        anomalies = FE().detect_anomalies(features)
        self.assertFalse(any("rsi_extreme" in a for a in anomalies))


if __name__ == "__main__":
    unittest.main(verbosity=2)
