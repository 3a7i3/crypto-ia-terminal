from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


# ── Indicateurs techniques (stdlib + math, pas de dépendance externe) ──────────


def _ema(prices: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out = [prices[0]]
    for p in prices[1:]:
        out.append(p * k + out[-1] * (1 - k))
    return out


def _sma(prices: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(prices)
    for i in range(period - 1, len(prices)):
        out[i] = sum(prices[i - period + 1 : i + 1]) / period
    return out


def _rsi(prices: list[float], period: int) -> list[float]:
    rsi = [50.0] * len(prices)
    if len(prices) <= period:
        return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    for i in range(period, len(prices)):
        rsi[i] = 100 - 100 / (1 + avg_g / avg_l) if avg_l else 100.0
        d = prices[i] - prices[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
    return rsi


def _bollinger(prices: list[float], period: int, k: float = 2.0):
    upper, lower = [None] * len(prices), [None] * len(prices)
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        mu = sum(window) / period
        std = math.sqrt(sum((x - mu) ** 2 for x in window) / period)
        upper[i] = mu + k * std
        lower[i] = mu - k * std
    return upper, lower


def _macd(prices: list[float], fast: int, slow: int, sig: int):
    ema_f = _ema(prices, fast)
    ema_s = _ema(prices, slow)
    macd_line = [f - s for f, s in zip(ema_f, ema_s)]
    signal_line = _ema(macd_line, sig)
    return macd_line, signal_line


def _vwap(closes: list[float], volumes: list[float]) -> list[float]:
    cum_vp, cum_v = 0.0, 0.0
    out = []
    for c, v in zip(closes, volumes):
        cum_vp += c * v
        cum_v += v
        out.append(cum_vp / cum_v if cum_v else c)
    return out


# ── Génération de signaux ──────────────────────────────────────────────────────


def _signals(
    strategy: dict,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> list[int]:
    """Retourne +1 (long), -1 (short / sortie), 0 (flat) par barre."""
    n = len(closes)
    period = max(5, min(strategy.get("period", 14), n // 4))
    thr = strategy.get("threshold", 1.0)
    indicator = strategy.get("entry_indicator", "EMA")
    sig = [0] * n

    if indicator == "RSI":
        rsi = _rsi(closes, period)
        buy_lvl = max(15, 50 - thr * 15)
        sell_lvl = min(85, 50 + thr * 15)
        for i in range(period, n):
            sig[i] = 1 if rsi[i] < buy_lvl else (-1 if rsi[i] > sell_lvl else 0)

    elif indicator == "EMA":
        ema = _ema(closes, period)
        band = thr * 0.002
        for i in range(period, n):
            sig[i] = (
                1
                if closes[i] > ema[i] * (1 + band)
                else (-1 if closes[i] < ema[i] * (1 - band) else 0)
            )

    elif indicator == "MACD":
        fast = max(2, period // 3)
        slow_p = period
        macd, signal = _macd(closes, fast, slow_p, max(2, period // 6))
        for i in range(1, n):
            if macd[i] > signal[i] and macd[i - 1] <= signal[i - 1]:
                sig[i] = 1
            elif macd[i] < signal[i] and macd[i - 1] >= signal[i - 1]:
                sig[i] = -1

    elif indicator == "BOLLINGER":
        upper, lower = _bollinger(closes, period)
        for i in range(period, n):
            if lower[i] is not None and closes[i] < lower[i]:
                sig[i] = 1
            elif upper[i] is not None and closes[i] > upper[i]:
                sig[i] = -1

    elif indicator == "VWAP":
        vwap = _vwap(closes, volumes)
        band = thr * 0.002
        for i in range(1, n):
            sig[i] = (
                1
                if closes[i] > vwap[i] * (1 + band)
                else (-1 if closes[i] < vwap[i] * (1 - band) else 0)
            )

    elif indicator == "ATR":
        sma = _sma(closes, period)
        tr_list = [abs(closes[0])]
        for i in range(1, n):
            tr_list.append(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
        atr_val = sum(tr_list[:period]) / period
        for i in range(period, n):
            atr_val = (atr_val * (period - 1) + tr_list[i]) / period
            mu = sma[i]
            if mu is not None:
                sig[i] = (
                    1
                    if closes[i] > mu + thr * atr_val
                    else (-1 if closes[i] < mu - thr * atr_val else 0)
                )

    return sig


# ── BacktestLab ────────────────────────────────────────────────────────────────


class BacktestLab:
    """
    Backtest basé sur de vrais signaux calculés depuis la série OHLCV réelle.
    Prend en entrée une liste de bougies (chacune: open/close/high/low/volume).
    """

    COMMISSION = 0.001  # 0.1 % par trade (maker Binance)
    MIN_BARS = 20  # minimum pour backtester

    def run_backtest(self, strategy: dict, data: list[dict]) -> dict:
        closes = [float(c["close"]) for c in data]
        highs = [float(c.get("high", c["close"])) for c in data]
        lows = [float(c.get("low", c["close"])) for c in data]
        volumes = [float(c.get("volume", 1.0)) for c in data]

        if len(closes) < self.MIN_BARS:
            logger.warning("[BacktestLab] Série trop courte (%d barres)", len(closes))
            return self._empty_result(strategy)

        sigs = _signals(strategy, closes, highs, lows, volumes)

        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        bar_returns: list[float] = []
        wins = trades = 0
        position = 0
        entry_px = 0.0

        for i in range(1, len(closes)):
            bar_ret = 0.0

            if sigs[i] == 1 and position == 0:
                position = 1
                entry_px = closes[i]
                equity *= 1 - self.COMMISSION

            elif (sigs[i] == -1 or (sigs[i] == 1 and position == 1)) and position == 1:
                trade_ret = (closes[i] - entry_px) / entry_px if entry_px else 0.0
                equity *= (1 + trade_ret) * (1 - self.COMMISSION)
                bar_ret = trade_ret
                trades += 1
                if trade_ret > 0:
                    wins += 1
                position = 0
                entry_px = 0.0

            elif position == 1:
                bar_ret = (closes[i] - closes[i - 1]) / closes[i - 1]
                equity *= 1 + bar_ret

            bar_returns.append(bar_ret)
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak else 0.0
            max_dd = max(max_dd, dd)

        # Clôturer la position finale
        if position == 1 and entry_px:
            trade_ret = (closes[-1] - entry_px) / entry_px
            equity *= 1 + trade_ret
            trades += 1
            if trade_ret > 0:
                wins += 1

        sharpe = self._sharpe(bar_returns)
        return {
            "strategy": strategy,
            "pnl": round((equity - 1.0) * 100, 4),
            "sharpe": round(sharpe, 4),
            "drawdown": round(max_dd, 4),
            "win_rate": round(wins / trades, 4) if trades else 0.0,
            "trades": trades,
            "bars": len(closes),
        }

    @staticmethod
    def _sharpe(returns: list[float], periods_per_year: int = 8760) -> float:
        n = len(returns)
        if n < 2:
            return 0.0
        mu = sum(returns) / n
        var = sum((r - mu) ** 2 for r in returns) / n
        std = math.sqrt(var) if var > 0 else 1e-9
        return (mu / std) * math.sqrt(periods_per_year)

    def _empty_result(self, strategy: dict) -> dict:
        return {
            "strategy": strategy,
            "pnl": 0.0,
            "sharpe": 0.0,
            "drawdown": 0.0,
            "win_rate": 0.0,
            "trades": 0,
            "bars": 0,
        }
