"""
data_verifier.py — Vérificateur live du pipeline de données.
=============================================================
Outil de diagnostic en une seule commande pour valider :

  L1 DataFeed    — Connexion exchange, données OHLCV réelles vs synthétiques
  L2 FeatureCore — Indicateurs calculés (RSI, MACD, Bollinger, ATR, EMA)
  L3 SignalBrain — Signal généré (BUY/SELL/HOLD) + score confiance
  L9 OutputRelay — Test envoi Telegram live

Usage :
    python data_verifier.py                     # BTC/USDT 1h par défaut
    python data_verifier.py --symbols BTC ETH SOL
    python data_verifier.py --no-telegram       # skip test Telegram
    python data_verifier.py --continuous 60     # boucle toutes les 60s
    python data_verifier.py --json              # sortie JSON brute
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

os.makedirs("logs", exist_ok=True)

# Force UTF-8 sur stdout/stderr (Windows cp1252 par defaut)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]  # noqa: E501
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]  # noqa: E501
    except Exception as _enc_err:
        pass  # non-bloquant — le logging ci-dessous utilisera l'encodage par défaut
        # Note: log non disponible ici (initialisé après), on ignore silencieusement

logging.basicConfig(
    level=logging.WARNING,  # silencieux par défaut — seules les métriques s'affichent
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("logs/data_verifier.log", encoding="utf-8"),
    ],
)

log = logging.getLogger("data_verifier")

# ── Couleurs terminal ──────────────────────────────────────────────────────────

_CLR = {
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "cyan": "\033[96m",
    "bold": "\033[1m",
    "reset": "\033[0m",
    "grey": "\033[90m",
}


def _c(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{_CLR.get(color, '')}{text}{_CLR['reset']}"


def _ok(label: str) -> str:
    return _c("[OK]", "green") + f" {label}"


def _warn(label: str) -> str:
    return _c("[!!]", "yellow") + f" {label}"


def _err(label: str) -> str:
    return _c("[XX]", "red") + f" {label}"


def _section(title: str) -> None:
    w = 60
    print(f"\n{_c('-' * w, 'cyan')}")
    print(_c(f"  {title}", "bold"))
    print(_c("-" * w, "cyan"))


# ── L1 — DataFeed : Connexion exchange ────────────────────────────────────────


def verify_exchange_connection() -> dict:
    """
    Verifie la connexion a l'exchange.
    Test 1 : ping public (ticker BTC/USDT — sans auth, prouve que le reseau fonctionne).
    Test 2 : balance authentifiee (avec cles API si disponibles).
    """
    result: dict[str, Any] = {
        "exchange": "mexc",
        "mode": "unknown",
        "testnet": False,
        "has_key": False,
        "status": "error",
        "latency_ms": -1,
        "balance_usdt": 0.0,
    }
    try:
        import ccxt  # type: ignore[import]

        scanner_testnet_env = os.getenv("MARKET_SCANNER_TESTNET", "").lower()

        # Test 1 : ping public via MEXC (OHLCV feed)
        t0 = time.perf_counter()
        ex_public = ccxt.mexc({"enableRateLimit": True})
        ticker = ex_public.fetch_ticker("BTC/USDT")
        latency_public = int((time.perf_counter() - t0) * 1000)
        last_price = float(ticker.get("last") or 0)

        result["status"] = "ok"
        result["latency_ms"] = latency_public
        result["last_btc_price"] = last_price
        result["data_source"] = (
            "testnet" if scanner_testnet_env == "true" else "real_mexc"
        )

        # Test 2 : balance authentifiee
        api_key = os.getenv("MEXC_API_KEY")
        api_secret = os.getenv("MEXC_API_SECRET")
        has_key = bool(api_key and api_secret)
        result["has_key"] = has_key

        if has_key:
            try:
                t1 = time.perf_counter()
                ex_auth = ccxt.mexc(
                    {
                        "apiKey": api_key,
                        "secret": api_secret,
                        "enableRateLimit": True,
                    }
                )
                result["mode"] = "spot_live"
                bal = ex_auth.fetch_balance()
                usdt = float(bal.get("free", {}).get("USDT", 0.0))
                result["balance_usdt"] = usdt
                result["auth_latency_ms"] = int((time.perf_counter() - t1) * 1000)
            except Exception as auth_exc:
                result["auth_error"] = str(auth_exc)[:120]
                result["mode"] = "spot_live"
        else:
            result["mode"] = "paper"

    except Exception as exc:
        result["error"] = str(exc)[:120]

    return result


# ── L1 — DataFeed : Récupération OHLCV ────────────────────────────────────────


def fetch_ohlcv(symbol: str, timeframe: str = "1h", limit: int = 100) -> dict:
    """
    Recupere les donnees OHLCV via MarketScanner et retourne un rapport qualite.
    """
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "error",
        "candles_total": 0,
        "candles_real": 0,
        "candles_synthetic": 0,
        "source": "unknown",
        "freshness_ok": False,
        "latest_close": None,
        "latest_ts": None,
        "fetch_ms": 0,
        "error": None,
        "candles_raw": [],
    }

    try:
        from quant_hedge_ai.agents.market.market_scanner import MarketScanner
        from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles

        scanner = MarketScanner(
            symbols=[symbol],
            timeframe=timeframe,
            limit=limit,
        )

        raw = scanner.scan()
        result["fetch_ms"] = int((time.perf_counter() - t0) * 1000)

        history = raw.get("history", {}) if isinstance(raw, dict) else {}

        # Chercher le symbole avec normalisation
        candles = history.get(symbol) or history.get(symbol.replace("/", "")) or []

        if not candles:
            result["error"] = "Aucune bougie recue (liste vide)"
            return result

        # validate_candles retourne (clean_list, ValidationReport)
        clean_candles, report = validate_candles(candles, symbol=symbol)

        source_counts = getattr(report, "source_counts", None) or {}
        real_count = source_counts.get("ccxt_live", 0)
        synth_count = source_counts.get("synthetic", 0) + source_counts.get(
            "ccxt_incremental", 0
        )

        # Deduction source depuis stats scanner
        scanner_stats = getattr(scanner, "_stats", {})
        if scanner_stats.get("real", 0) > 0:
            source = "live"
        elif scanner_stats.get("synthetic", 0) > 0 or synth_count > 0:
            source = "synthetic"
        else:
            # Heuristique : si les bougies n'ont pas le champ "source" = synthetic
            first_src = candles[0].get("source", "") if candles else ""
            source = "live" if first_src not in ("synthetic", "") else "synthetic"

        last_candle = candles[-1]
        last_close = float(last_candle.get("close", 0))
        last_ts_raw = last_candle.get("timestamp", "")

        # Calcul fraicheur (donnees < 2h = fraiches)
        freshness_ok = False
        try:
            if isinstance(last_ts_raw, str):
                ts = datetime.fromisoformat(last_ts_raw.replace("Z", "+00:00"))
                age_h = (datetime.now(tz=timezone.utc) - ts).total_seconds() / 3600
                freshness_ok = age_h < 2.0
            elif isinstance(last_ts_raw, (int, float)):
                age_s = time.time() - last_ts_raw / 1000
                freshness_ok = age_s < 7200
        except Exception:
            pass

        result.update(
            {
                "status": "ok",
                "candles_total": report.total,
                "candles_real": real_count,
                "candles_synthetic": synth_count,
                "candles_valid": report.valid,
                "candles_dropped": report.dropped,
                "source": source,
                "freshness_ok": freshness_ok,
                "latest_close": round(last_close, 4),
                "latest_ts": last_ts_raw,
                "error": None,
                "candles_raw": clean_candles,
                "scanner_stats": scanner_stats,
            }
        )

    except Exception as exc:
        result["fetch_ms"] = int((time.perf_counter() - t0) * 1000)
        result["error"] = str(exc)
        log.exception("fetch_ohlcv erreur pour %s", symbol)

    return result


# ── L2 — FeatureCore : Calcul indicateurs ─────────────────────────────────────


def compute_indicators(symbol: str, candles_raw: Optional[list] = None) -> dict:
    """Calcule tous les indicateurs techniques et retourne le dict features."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "status": "error",
        "features": {},
        "error": None,
    }

    try:
        from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer

        if not candles_raw:
            from quant_hedge_ai.agents.market.market_scanner import MarketScanner

            scanner = MarketScanner(symbols=[symbol], limit=100)
            raw = scanner.scan()
            history = raw.get("history", {}) if isinstance(raw, dict) else {}
            candles_raw = (
                history.get(symbol) or history.get(symbol.replace("/", "")) or []
            )

        min_candles = 15
        if not candles_raw or len(candles_raw) < min_candles:
            result["error"] = (
                f"Pas assez de bougies ({len(candles_raw or [])}/{min_candles} min)"
            )
            return result

        fe = FeatureEngineer()
        features = fe.extract_features(candles_raw)
        result.update({"status": "ok", "features": features})

    except Exception as exc:
        result["error"] = str(exc)
        log.exception("compute_indicators erreur pour %s", symbol)

    return result


# ── L2 — FeatureCore : Détection régime ────────────────────────────────────────


def detect_regime(
    symbol: str, features: Optional[dict] = None, candles_raw: Optional[list] = None
) -> dict:
    """Detecte le regime marche actuel via AdvancedRegimeDetector."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "regime": "unknown",
        "strategy_type": "neutral",
        "status": "error",
        "error": None,
    }

    try:
        from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer
        from quant_hedge_ai.agents.intelligence.regime_detector import (
            AdvancedRegimeDetector,
        )

        # Calcul des features si non fournies
        if not features:
            if not candles_raw:
                from quant_hedge_ai.agents.market.market_scanner import MarketScanner

                scanner = MarketScanner(symbols=[symbol], limit=100)
                raw = scanner.scan()
                history = raw.get("history", {}) if isinstance(raw, dict) else {}
                candles_raw = (
                    history.get(symbol) or history.get(symbol.replace("/", "")) or []
                )

            if not candles_raw or len(candles_raw) < 10:
                result["error"] = "Pas assez de bougies pour le regime"
                return result

            fe = FeatureEngineer()
            features = fe.extract_features(candles_raw)

        rd = AdvancedRegimeDetector()
        closes = (
            [float(c.get("close", 0)) for c in (candles_raw or [])]
            if candles_raw
            else None
        )
        regime = rd.classify(features, recent_prices=closes)
        strategy_type = rd.suggest_strategy_type(regime)

        result.update(
            {
                "status": "ok",
                "regime": regime,
                "strategy_type": strategy_type,
            }
        )

    except Exception as exc:
        result["error"] = str(exc)
        log.exception("detect_regime erreur pour %s", symbol)

    return result


# ── L3 — SignalBrain : Génération signal ──────────────────────────────────────


def generate_signal(
    symbol: str,
    candles_raw: Optional[list] = None,
    features: Optional[dict] = None,
) -> dict:
    """Genere le signal BUY/SELL/HOLD via LiveSignalEngine.evaluate()."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "signal": "UNKNOWN",
        "score": 0,
        "status": "error",
        "error": None,
    }

    try:
        from quant_hedge_ai.agents.execution.live_signal_engine import LiveSignalEngine
        from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer

        if not candles_raw:
            from quant_hedge_ai.agents.market.market_scanner import MarketScanner

            scanner = MarketScanner(symbols=[symbol], limit=100)
            raw = scanner.scan()
            history = raw.get("history", {}) if isinstance(raw, dict) else {}
            candles_raw = (
                history.get(symbol) or history.get(symbol.replace("/", "")) or []
            )

        if not candles_raw:
            result["error"] = "Aucune bougie pour generation signal"
            return result

        # Features requises par LiveSignalEngine
        if not features and len(candles_raw) >= 15:
            fe = FeatureEngineer()
            features = fe.extract_features(candles_raw)

        # mtf_candles : dict {timeframe: [candles]}
        mtf_candles = {"1h": candles_raw}

        engine = LiveSignalEngine()
        sig = engine.evaluate(
            symbol=symbol,
            mtf_candles=mtf_candles,
            features=features or {},
        )

        if sig is None:
            result.update({"status": "ok", "signal": "HOLD", "score": 0})
            return result

        d = (
            sig.as_dict()
            if hasattr(sig, "as_dict")
            else (sig.__dict__ if hasattr(sig, "__dict__") else {})
        )

        result.update(
            {
                "status": "ok",
                "signal": d.get("signal", "HOLD"),
                "score": d.get("score", 0),
                "regime": d.get("regime", "unknown"),
                "confirmed_mtf": d.get("confirmed", False),
                "actionable": d.get("actionable", False),
                "strength": d.get("strength", 0),
                "components": d.get("components", {}),
            }
        )

    except Exception as exc:
        result["error"] = str(exc)
        log.exception("generate_signal erreur pour %s", symbol)

    return result


# ── L9 — OutputRelay : Test Telegram ──────────────────────────────────────────


def test_telegram(message: Optional[str] = None) -> dict:
    """Envoie un message test à Telegram et retourne le statut."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    result: dict[str, Any] = {
        "configured": bool(token and chat_id),
        "status": "skip",
        "latency_ms": -1,
    }

    if not token or not chat_id:
        result["error"] = "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env"
        return result

    try:
        import requests as _req

        now = datetime.now().strftime("%H:%M:%S")
        text = message or (
            f"🔍 *Data Verifier* — Test live [{now}]\n" f"Pipeline données actif ✓"
        )
        t0 = time.perf_counter()
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        latency = int((time.perf_counter() - t0) * 1000)
        result["latency_ms"] = latency

        if r.status_code == 200:
            result["status"] = "ok"
            try:
                _resp = r.json() or {}
                result["message_id"] = _resp.get("result", {}).get("message_id")
            except Exception as _json_err:
                log.warning("Telegram: réponse JSON invalide: %s", _json_err)
        else:
            result["status"] = "error"
            result["error"] = f"HTTP {r.status_code}: {r.text[:200]}"

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    return result


# ── Affichage résultats ────────────────────────────────────────────────────────


def _print_exchange(conn: dict) -> None:
    _section("L1 — DataFeed : Connexion Exchange")
    exch = conn.get("exchange", "?")
    mode = conn.get("mode", "?")
    testnet = conn.get("testnet", False)
    st = conn.get("status", "error")
    latency = conn.get("latency_ms", -1)
    balance = conn.get("balance_usdt", 0.0)
    data_src = conn.get("data_source", "?")

    print(f"  Exchange   : {_c(exch.upper(), 'bold')}")
    print(
        f"  Ordres     : {_c(mode.upper(), 'yellow' if testnet else 'green')}"
        + (_c("  (testnet)", "yellow") if testnet else "")
    )
    print(f"  Donnees    : {_c(data_src, 'cyan')}")

    if st == "ok":
        btc = conn.get("last_btc_price", 0)
        print(
            f"  Ping       : {_ok(f'Reseau OK')}  {_c(f'{latency} ms', 'grey')}"
            + (f"  BTC={btc:,.0f}" if btc else "")
        )
        if balance > 0:
            print(f"  Balance    : {_c(f'{balance:.2f} USDT', 'green')}")
        elif conn.get("auth_error"):
            print(f"  Auth       : {_warn('Erreur auth: ' + conn['auth_error'][:80])}")
    elif st == "paper":
        print(
            f"  Connexion  : {_warn('Mode PAPER (simulation, aucune donnee reelle)')}"
        )
    else:
        print(f"  Connexion  : {_err('ECHEC')}")
        if "error" in conn:
            print(f"  Erreur     : {_c(conn['error'][:120], 'red')}")


def _print_ohlcv(rep: dict) -> None:
    sym = rep.get("symbol", "?")
    st = rep.get("status", "error")
    total = rep.get("candles_total", 0)
    real = rep.get("candles_real", 0)
    synth = rep.get("candles_synthetic", 0)
    source = rep.get("source", "?")
    fresh = rep.get("freshness_ok", False)
    close = rep.get("latest_close")
    ts = rep.get("latest_ts", "")
    fetch_ms = rep.get("fetch_ms", 0)
    dropped = rep.get("candles_dropped", 0)

    print(f"\n  {_c(sym, 'bold')}")
    if st != "ok":
        print(f"    {_err('ERREUR')} : {rep.get('error', '?')[:100]}")
        return

    # Source réelle ou synthétique
    if source == "live":
        src_label = _ok(f"Données réelles MEXC  ({real}/{total} bougies)")
    elif source == "synthetic":
        src_label = _warn(
            f"DONNÉES SYNTHÉTIQUES ({synth}/{total}) — exchange inaccessible ?"
        )
    else:
        src_label = _warn(f"Source inconnue ({total} bougies)")

    print(f"    Source     : {src_label}")
    print(f"    Fetch      : {_c(f'{fetch_ms} ms', 'grey')}")

    if dropped:
        print(f"    Rejetées   : {_warn(str(dropped))} bougies corrompues")

    if close:
        print(f"    Dernier prix: {_c(f'{close:,.4f} USDT', 'cyan')}")

    if fresh:
        print(f"    Fraîcheur  : {_ok('Données à jour')}")
    else:
        print(f"    Fraîcheur  : {_warn('Données potentiellement périmées (> 2h)')}")


def _print_indicators(ind: dict) -> None:
    sym = ind.get("symbol", "?")
    st = ind.get("status", "error")
    features = ind.get("features", {})

    print(f"\n  {_c(sym, 'bold')}")
    if st != "ok":
        print(f"    {_err('ERREUR')} : {ind.get('error', '?')[:100]}")
        return

    rsi = features.get("rsi", None)
    macd_hist = features.get("macd_hist", None)
    bb_pct = features.get("bb_pct", None)
    atr_ratio = features.get("atr_ratio", None)
    ema_cross = features.get("ema_cross", None)
    momentum = features.get("momentum", None)
    vol_ratio = features.get("volume_ratio", None)

    def _rsi_color(v: float) -> str:
        if v > 70:
            return "red"
        if v < 30:
            return "green"
        return "cyan"

    if rsi is not None:
        rsi_v = float(rsi)
        rsi_tag = ""
        if rsi_v > 70:
            rsi_tag = _c(" (surachat)", "red")
        elif rsi_v < 30:
            rsi_tag = _c(" (survendu)", "green")
        print(f"    RSI(14)    : {_c(f'{rsi_v:.1f}', _rsi_color(rsi_v))}{rsi_tag}")

    if macd_hist is not None:
        sign = "+" if float(macd_hist) >= 0 else ""
        color = "green" if float(macd_hist) >= 0 else "red"
        bullish = features.get("macd_bullish", float(macd_hist) >= 0)
        tag = " (haussier)" if bullish else " (baissier)"
        print(
            f"    MACD hist  : {_c(f'{sign}{float(macd_hist):.6f}', color)}{_c(tag, color)}"  # noqa: E501
        )

    if bb_pct is not None:
        bb_v = float(bb_pct)
        bb_color = "red" if bb_v > 0.8 else ("green" if bb_v < 0.2 else "cyan")
        print(f"    BB %       : {_c(f'{bb_v:.2%}', bb_color)}")

    if atr_ratio is not None:
        print(f"    ATR/prix   : {_c(f'{float(atr_ratio):.4%}', 'grey')}")

    if ema_cross is not None:
        cross_v = float(ema_cross)
        cross_color = "green" if cross_v > 0 else "red"
        print(f"    EMA cross  : {_c(f'{cross_v:+.4%}', cross_color)}")

    if momentum is not None:
        mom_v = float(momentum)
        mom_color = "green" if mom_v > 0 else "red"
        print(f"    Momentum   : {_c(f'{mom_v:+.4%}', mom_color)}")

    if vol_ratio is not None:
        vr = float(vol_ratio)
        vr_color = "yellow" if vr > 2 else "grey"
        print(f"    Vol ratio  : {_c(f'{vr:.2f}x', vr_color)}")


def _print_regime(reg: dict) -> None:
    sym = reg.get("symbol", "?")
    st = reg.get("status", "error")
    regime = reg.get("regime", "unknown")

    print(f"\n  {_c(sym, 'bold')}")
    if st != "ok":
        print(f"    {_err('ERREUR')} : {reg.get('error', '?')[:100]}")
        return

    regime_colors = {
        "bull_trend": "green",
        "bear_trend": "red",
        "sideways": "yellow",
        "high_volatility_regime": "yellow",
        "flash_crash": "red",
    }
    color = regime_colors.get(regime, "cyan")
    print(f"    Régime     : {_c(regime.upper(), color)}")

    if "strategy_type" in reg:
        print(f"    Strategie  : {reg['strategy_type']}")


def _print_signal(sig: dict) -> None:
    sym = sig.get("symbol", "?")
    st = sig.get("status", "error")
    signal = sig.get("signal", "HOLD")
    score = sig.get("score", 0)
    conf = sig.get("confidence", 0)
    confirmed_mtf = sig.get("confirmed_mtf", False)

    print(f"\n  {_c(sym, 'bold')}")
    if st != "ok":
        print(f"    {_err('ERREUR')} : {sig.get('error', '?')[:100]}")
        return

    signal_colors = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}
    color = signal_colors.get(signal, "grey")
    print(f"    Signal     : {_c(signal, color)}  score={_c(str(score), 'bold')}/100")

    if score >= 70:
        print(f"    Threshold  : {_ok('Score >= 70 (actionable)')}")
    else:
        print(f"    Threshold  : {_warn(f'Score < 70 (non actionable, seuil=70)')}")

    if conf:
        print(f"    Confiance  : {float(conf):.1%}")

    mtf_label = (
        _ok("Confirmé multi-timeframe") if confirmed_mtf else _warn("Non confirmé MTF")
    )
    print(f"    MTF        : {mtf_label}")


def _print_telegram(tg: dict) -> None:
    _section("L9 — OutputRelay : Telegram")
    if not tg.get("configured"):
        print(
            f"  {_err('Non configuré')} — vérifier .env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)"  # noqa: E501
        )
        return

    st = tg.get("status", "error")
    latency = tg.get("latency_ms", -1)

    if st == "ok":
        msg_id = tg.get("message_id", "?")
        lat_str = f"{latency} ms"
        print(
            f"  Envoi      : {_ok('Message livré')}  id={msg_id}  {_c(lat_str, 'grey')}"
        )
    elif st == "skip":
        print(f"  Envoi      : {_warn('Test sauté (--no-telegram)')}")
    else:
        print(f"  Envoi      : {_err('ECHEC')}")
        if "error" in tg:
            print(f"  Erreur     : {_c(tg['error'][:120], 'red')}")


# ── Rapport JSON ───────────────────────────────────────────────────────────────


def build_report(
    symbols: list[str],
    conn: dict,
    ohlcv_reports: list[dict],
    indicator_reports: list[dict],
    regime_reports: list[dict],
    signal_reports: list[dict],
    telegram: dict,
) -> dict:
    return {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "exchange": conn,
        "ohlcv": ohlcv_reports,
        "indicators": indicator_reports,
        "regimes": regime_reports,
        "signals": signal_reports,
        "telegram": telegram,
    }


# ── Boucle principale ──────────────────────────────────────────────────────────


def run_verification(
    symbols: list[str],
    timeframe: str = "1h",
    limit: int = 100,
    skip_telegram: bool = False,
    output_json: bool = False,
) -> dict:
    ts_start = time.perf_counter()

    # ── L1 — Connexion exchange
    conn = verify_exchange_connection()

    # ── L1 — OHLCV par symbole (fetch unique, donnees partagees entre couches)
    ohlcv_reports: list[dict] = []
    candles_cache: dict[str, list] = {}
    for sym in symbols:
        rep = fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
        ohlcv_reports.append(rep)
        # Garde les bougies propres pour les etapes suivantes (evite double-fetch)
        if rep["status"] == "ok" and rep.get("candles_raw"):
            candles_cache[sym] = rep["candles_raw"]

    # ── L2 — Indicateurs (reutilise les bougies deja fetched)
    indicator_reports: list[dict] = [
        compute_indicators(sym, candles_raw=candles_cache.get(sym)) for sym in symbols
    ]

    # ── L2 — Regimes (reutilise features deja calculees)
    regime_reports: list[dict] = []
    features_cache: dict[str, dict] = {}
    for rep in indicator_reports:
        sym = rep["symbol"]
        feats = rep.get("features") or {}
        features_cache[sym] = feats
        regime_reports.append(
            detect_regime(
                sym, features=feats or None, candles_raw=candles_cache.get(sym)
            )
        )

    # ── L3 — Signaux (reutilise bougies + features)
    signal_reports: list[dict] = [
        generate_signal(
            sym, candles_raw=candles_cache.get(sym), features=features_cache.get(sym)
        )
        for sym in symbols
    ]

    # ── L9 — Telegram
    if skip_telegram:
        tg_result = {
            "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "status": "skip",
        }
    else:
        # Compose un message de résumé
        sig_parts = []
        for sig in signal_reports:
            if sig.get("status") == "ok":
                emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}.get(
                    sig.get("signal", ""), "❓"
                )
                sig_parts.append(
                    f"{sig['symbol']}: {sig.get('signal', '?')} score={sig.get('score', 0)}"  # noqa: E501
                )
        msg = (
            f"[Data Verifier] [{datetime.now().strftime('%H:%M:%S')}]\n"
            f"Exchange: {conn.get('exchange', '?').upper()} [{conn.get('mode', '?')}]\n"
            + "\n".join(sig_parts)
        )
        tg_result = test_telegram(msg)

    elapsed = int((time.perf_counter() - ts_start) * 1000)

    report = build_report(
        symbols,
        conn,
        ohlcv_reports,
        indicator_reports,
        regime_reports,
        signal_reports,
        tg_result,
    )
    report["total_ms"] = elapsed

    if output_json:
        print(json.dumps(report, indent=2, default=str))
        return report

    # ── Affichage lisible ──────────────────────────────────────────────────────
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{_c('=' * 60, 'bold')}")
    print(_c(f"  CRYPTO AI TERMINAL - Data Verifier  [{now}]", "bold"))
    print(_c("=" * 60, "bold"))

    _print_exchange(conn)

    _section("L1 — DataFeed : OHLCV")
    for rep in ohlcv_reports:
        _print_ohlcv(rep)

    _section("L2 — FeatureCore : Indicateurs")
    for ind in indicator_reports:
        _print_indicators(ind)

    _section("L2 — FeatureCore : Régimes marché")
    for reg in regime_reports:
        _print_regime(reg)

    _section("L3 — SignalBrain : Signaux générés")
    for sig in signal_reports:
        _print_signal(sig)

    _print_telegram(tg_result)

    print(f"\n{_c('-' * 60, 'grey')}")
    print(_c(f"  Verification complete en {elapsed} ms", "grey"))
    print(_c("-" * 60, "grey"))

    return report


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vérificateur live du pipeline de données Crypto AI Terminal"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        help="Symboles à analyser (défaut: BTC/USDT ETH/USDT SOL/USDT)",
    )
    parser.add_argument(
        "--timeframe",
        default="1h",
        help="Timeframe OHLCV (défaut: 1h)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Nombre de bougies à récupérer (défaut: 100)",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Ne pas envoyer de message Telegram",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Sortie en format JSON brut",
    )
    parser.add_argument(
        "--continuous",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Boucle continue toutes les N secondes (0 = une seule fois)",
    )

    args = parser.parse_args()

    # Normalise les symboles (BTC → BTC/USDT)
    symbols = []
    for s in args.symbols:
        if "/" not in s:
            s = f"{s.upper()}/USDT"
        symbols.append(s)

    if args.continuous > 0:
        print(
            _c(
                f"Mode continu - rafraichissement toutes les {args.continuous}s (Ctrl+C pour arreter)",  # noqa: E501
                "yellow",
            )
        )
        while True:
            try:
                run_verification(
                    symbols=symbols,
                    timeframe=args.timeframe,
                    limit=args.limit,
                    skip_telegram=args.no_telegram,
                    output_json=args.json,
                )
                time.sleep(args.continuous)
            except KeyboardInterrupt:
                print("\nArrêt demandé.")
                break
    else:
        run_verification(
            symbols=symbols,
            timeframe=args.timeframe,
            limit=args.limit,
            skip_telegram=args.no_telegram,
            output_json=args.json,
        )


if __name__ == "__main__":
    main()
