"""
seed_strategy_memory.py — Pré-remplit la StrategyMemory avec des backtests réels.

Télécharge 6 mois de données 1h pour BTC/ETH/SOL, fait tourner une batterie
de stratégies sur chaque régime détecté, et sauvegarde les meilleures dans
StrategyMemoryStore. Après ce script, le composant Mémoire passe de 10/20
à 15-20/20 dans les scores de signal.

Usage:
    python scripts/seed_strategy_memory.py
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("seed_memory")

from quant_hedge_ai.agents.market.market_scanner import MarketScanner
from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer
from quant_hedge_ai.agents.intelligence.regime_detector import AdvancedRegimeDetector
from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab
from quant_hedge_ai.ai_evolution.strategy_memory import StrategyMemoryStore

# ── Stratégies à tester ───────────────────────────────────────────────────────
STRATEGIES = [
    {"name": "EMA_14_trend",    "entry_indicator": "EMA",       "period": 14,  "threshold": 1.0},
    {"name": "EMA_21_trend",    "entry_indicator": "EMA",       "period": 21,  "threshold": 1.2},
    {"name": "RSI_14_reversal", "entry_indicator": "RSI",       "period": 14,  "threshold": 1.0},
    {"name": "RSI_21_reversal", "entry_indicator": "RSI",       "period": 21,  "threshold": 1.5},
    {"name": "MACD_std",        "entry_indicator": "MACD",      "period": 26,  "threshold": 1.0},
    {"name": "BOLLINGER_20",    "entry_indicator": "BOLLINGER", "period": 20,  "threshold": 2.0},
    {"name": "BOLLINGER_14",    "entry_indicator": "BOLLINGER", "period": 14,  "threshold": 1.5},
    {"name": "VWAP_trend",      "entry_indicator": "VWAP",      "period": 20,  "threshold": 1.0},
    {"name": "ATR_breakout",    "entry_indicator": "ATR",       "period": 14,  "threshold": 1.5},
    {"name": "EMA_50_long",     "entry_indicator": "EMA",       "period": 50,  "threshold": 0.8},
]

SYMBOLS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
# 6 mois de bougies 1h = ~4380 bougies
LIMIT    = 1000  # testnet limite souvent à ~1000, on prend le max disponible
MIN_SHARPE = 0.5  # seuil minimum pour sauvegarder


def detect_regime(candles: list[dict]) -> str:
    try:
        features = FeatureEngineer().extract_features(candles)
        return AdvancedRegimeDetector().classify(features)
    except Exception:
        return "unknown"


def split_by_regime(candles: list[dict]) -> dict[str, list[dict]]:
    """Découpe la série en segments par régime (fenêtres glissantes de 168 bougies = 1 semaine)."""
    window = 168
    step   = 84   # chevauchement 50%
    segments: dict[str, list[list[dict]]] = {}

    for start in range(0, len(candles) - window, step):
        chunk  = candles[start: start + window]
        regime = detect_regime(chunk)
        segments.setdefault(regime, []).append(chunk)

    return segments


def run_seed():
    lab    = BacktestLab()
    memory = StrategyMemoryStore()

    total_saved = 0

    for symbol in SYMBOLS:
        log.info("=== %s — Telechargement donnees ===", symbol)
        scanner  = MarketScanner(symbols=[symbol], timeframe="1h", limit=LIMIT)
        market   = scanner.scan()
        candles  = (
            market.get("history", {}).get(symbol)
            or market.get("candles", {}).get(symbol)
            or []
        )

        if len(candles) < 200:
            log.warning("%s — Donnees insuffisantes (%d bougies), skip", symbol, len(candles))
            continue

        log.info("%s — %d bougies recues", symbol, len(candles))

        # Découpage par régime
        segments = split_by_regime(candles)
        log.info("%s — Regimes detectes: %s", symbol,
                 {r: len(segs) for r, segs in segments.items()})

        # Backtest de chaque stratégie sur chaque régime
        regime_results: dict[str, list[dict]] = {}

        for regime, seg_list in segments.items():
            if regime == "unknown":
                continue

            best_per_strategy: dict[str, dict] = {}

            for strat in STRATEGIES:
                sharpes = []
                for seg in seg_list:
                    result = lab.run_backtest(strat, seg, timeframe="1h")
                    if result["trades"] >= 3:
                        sharpes.append(result["sharpe"])

                if not sharpes:
                    continue

                avg_sharpe = sum(sharpes) / len(sharpes)
                best_per_strategy[strat["name"]] = {
                    "strategy_name": f"{strat['name']}_{symbol.replace('/','')}",
                    "symbol":        symbol,
                    "regime":        regime,
                    "sharpe":        round(avg_sharpe, 4),
                    "win_rate":      0.0,
                    "drawdown":      0.0,
                    "config":        strat,
                    "n_segments":    len(sharpes),
                }

            # Garder celles au-dessus du seuil
            good = [
                v for v in best_per_strategy.values()
                if v["sharpe"] >= MIN_SHARPE
            ]
            good.sort(key=lambda x: x["sharpe"], reverse=True)

            if good:
                regime_results.setdefault(regime, []).extend(good[:3])
                log.info("  %s | regime %-25s | %d strategies valides (top sharpe: %.2f)",
                         symbol, regime, len(good), good[0]["sharpe"])
            else:
                log.info("  %s | regime %-25s | aucune strategie au-dessus du seuil %.1f",
                         symbol, regime, MIN_SHARPE)

        # Sauvegarde dans la mémoire
        for regime, strategies in regime_results.items():
            saved = memory.save_for_regime(regime, strategies)
            total_saved += saved
            log.info("  -> %d strategies sauvegardees pour regime '%s'", saved, regime)

    log.info("")
    log.info("=== TERMINE — %d strategies sauvegardees en memoire ===", total_saved)

    # Afficher un résumé par régime
    log.info("")
    log.info("=== RESUME MEMOIRE ===")
    for regime in ["bull_trend", "bear_trend", "sideways", "high_volatility_regime", "flash_crash"]:
        stored = memory.load_by_regime(regime, limit=5)
        if stored:
            best = max(stored, key=lambda x: x.get("sharpe", 0))
            log.info("  %-28s | %d strats | meilleur sharpe: %.2f (%s)",
                     regime, len(stored),
                     best.get("sharpe", 0), best.get("strategy_name", "?"))
        else:
            log.info("  %-28s | vide", regime)

    return total_saved


if __name__ == "__main__":
    os.makedirs("scripts", exist_ok=True)
    n = run_seed()
    log.info("")
    log.info("Pret. Le composant Memoire va maintenant contribuer jusqu'a 20/20 dans les scores.")
    sys.exit(0 if n > 0 else 1)
