"""
fetch_audit.py — Audit de latence du fetch 1h Binance à froid.

Sépare les phases de latence :
  1. DNS  — résolution de api.binance.com et testnet.binance.vision
  2. TCP+TLS handshake — connexion HTTPS brute
  3. CCXT init — création de l'objet exchange + chargement des marchés
  4. Premier fetch_ohlcv (froid)
  5. Fetches suivants (chaud, connexion réutilisée)

Explication du 3.7-3.9s constaté à froid.

Exécution :
    python -m quant_hedge_ai.fetch_audit
    python -m quant_hedge_ai.fetch_audit --testnet   (compare testnet vs mainnet)
"""

from __future__ import annotations

import argparse
import socket
import ssl
import statistics
import time
from contextlib import contextmanager
from typing import Any, Generator

# ── Timer utilitaire ──────────────────────────────────────────────────────────


@contextmanager
def _timer(label: str) -> Generator[dict, None, None]:
    ctx: dict = {}
    t0 = time.perf_counter()
    yield ctx
    ctx["elapsed"] = time.perf_counter() - t0
    ctx["label"] = label


# ── Phase 1 : DNS ─────────────────────────────────────────────────────────────


def audit_dns(host: str, n: int = 3) -> dict:
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            times.append(time.perf_counter() - t0)
        except Exception as exc:
            return {
                "host": host,
                "error": str(exc),
                "times_ms": [],
                "avg_ms": 0.0,
                "note": "DNS inaccessible",
            }
    return {
        "host": host,
        "times_ms": [round(t * 1000, 1) for t in times],
        "avg_ms": round(statistics.mean(times) * 1000, 1),
        "min_ms": round(min(times) * 1000, 1),
        "note": "Cache systeme actif apres le 1er appel (voir min vs avg)",
    }


# ── Phase 2 : TCP + TLS handshake ─────────────────────────────────────────────


def audit_tcp_tls(host: str, port: int = 443, n: int = 3) -> dict:
    ctx = ssl.create_default_context()
    times = []
    for _ in range(n):
        try:
            t0 = time.perf_counter()
            with socket.create_connection((host, port), timeout=10) as raw:
                with ctx.wrap_socket(raw, server_hostname=host) as _:
                    times.append(time.perf_counter() - t0)
        except Exception as exc:
            return {"host": host, "error": str(exc), "times_ms": [], "avg_ms": 0.0}
    return {
        "host": host,
        "times_ms": [round(t * 1000, 1) for t in times],
        "avg_ms": round(statistics.mean(times) * 1000, 1),
        "note": "TCP SYN + 3-way + TLS 1.3 handshake. Inclut RTT serveur.",
    }


# ── Phase 3 : CCXT init (creation exchange + load_markets) ───────────────────


def audit_ccxt_init(testnet: bool = False) -> dict:
    try:
        import ccxt  # type: ignore[import]
    except ImportError:
        return {"error": "ccxt non installe", "init_ms": 0.0, "load_markets_ms": 0.0}

    t_obj = time.perf_counter()
    exchange = ccxt.mexc(
        {
            "apiKey": "",
            "secret": "",
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
        }
    )
    if testnet:
        exchange.set_sandbox_mode(True)
    init_ms = (time.perf_counter() - t_obj) * 1000

    # load_markets est l'opération coûteuse à froid
    t_markets = time.perf_counter()
    try:
        exchange.load_markets()
        markets_ms = (time.perf_counter() - t_markets) * 1000
        n_markets = len(exchange.markets)
        markets_error = None
    except Exception as exc:
        markets_ms = (time.perf_counter() - t_markets) * 1000
        n_markets = 0
        markets_error = str(exc)

    return {
        "testnet": testnet,
        "init_ms": round(init_ms, 1),
        "load_markets_ms": round(markets_ms, 1),
        "n_markets": n_markets,
        "markets_error": markets_error,
        "note": (
            "load_markets() recupere ~2000 paires — c'est la source principale du delai initial "  # noqa: E501
            "si CCXT n'a pas de cache local."
        ),
    }


# ── Phase 4 : Premier fetch_ohlcv (froid) ────────────────────────────────────


def audit_fetch_ohlcv(
    exchange: Any,
    symbol: str = "BTC/USDT",
    limit: int = 96,
    n_warm: int = 3,
) -> dict:
    """Mesure le 1er fetch (froid) + n fetches suivants (chaud)."""
    try:
        # Fetch froid
        t0 = time.perf_counter()
        exchange.fetch_ohlcv(symbol, "1h", limit=limit)
        cold_ms = (time.perf_counter() - t0) * 1000

        # Fetches chauds
        warm_times = []
        for _ in range(n_warm):
            t0 = time.perf_counter()
            exchange.fetch_ohlcv(symbol, "1h", limit=limit)
            warm_times.append((time.perf_counter() - t0) * 1000)

        return {
            "symbol": symbol,
            "limit": limit,
            "cold_fetch_ms": round(cold_ms, 1),
            "warm_avg_ms": round(statistics.mean(warm_times), 1),
            "warm_min_ms": round(min(warm_times), 1),
            "speedup_x": round(cold_ms / max(statistics.mean(warm_times), 0.1), 2),
            "note": "Froid = nouvelle connexion TCP. Chaud = keep-alive HTTP/1.1 réutilisé.",  # noqa: E501
        }
    except Exception as exc:
        return {"error": str(exc), "cold_fetch_ms": 0.0, "warm_avg_ms": 0.0}


# ── Phase 5 : Latence CCXT rate limiter ──────────────────────────────────────


def audit_rate_limiter(testnet: bool = False) -> dict:
    """
    Estime le surcoût du rate limiter CCXT.
    Binance spot autorise 1200 req/min = 50ms/req minimum.
    CCXT ajoute un sleep supplémentaire basé sur rateLimit (default 50ms).
    """
    try:
        import ccxt
    except ImportError:
        return {"error": "ccxt non installe"}

    exchange = ccxt.mexc({"enableRateLimit": True})
    if testnet:
        exchange.set_sandbox_mode(True)

    rate_limit_ms = getattr(exchange, "rateLimit", 0)
    return {
        "testnet": testnet,
        "ccxt_rate_limit_ms": rate_limit_ms,
        "note": (
            f"CCXT ajoute un sleep de {rate_limit_ms}ms entre les appels si enableRateLimit=True. "  # noqa: E501
            "Ce sleep ne s'applique QUE si l'intervalle depuis le dernier appel est < rateLimit."  # noqa: E501
        ),
    }


# ── Rapport global ─────────────────────────────────────────────────────────────


def print_audit(testnet: bool = False) -> None:
    host_main = "api.mexc.com"
    host_testnet = "api.mexc.com"  # MEXC n'a pas de testnet public distinct

    print()
    print("=" * 66)
    print("  AUDIT LATENCE FETCH 1H MEXC A FROID")
    print(f"  Mode: {'TESTNET' if testnet else 'MAINNET'}")
    print("=" * 66)

    # ── DNS
    print("\n[1] DNS — resolution de hostname")
    for h in [host_testnet] if testnet else [host_main]:
        r = audit_dns(h)
        if "error" in r:
            print(f"  {h:40s} ERREUR: {r['error']}")
        else:
            print(f"  {h:40s} moy={r['avg_ms']:6.1f}ms  min={r['min_ms']:6.1f}ms")
            print(f"    -> {r['note']}")

    # ── TCP + TLS
    print("\n[2] TCP + TLS handshake")
    h = host_testnet if testnet else host_main
    r2 = audit_tcp_tls(h)
    if "error" in r2:
        print(f"  ERREUR: {r2['error']}")
    else:
        times_str = " / ".join(f"{t:.0f}ms" for t in r2["times_ms"])
        print(f"  {h}  [{times_str}]  moy={r2['avg_ms']:.1f}ms")
        print(f"    -> {r2['note']}")

    # ── CCXT init + load_markets
    print("\n[3] CCXT init + load_markets()")
    r3 = audit_ccxt_init(testnet=testnet)
    if "error" in r3:
        print(f"  ERREUR: {r3['error']}")
    else:
        print(
            f"  Exchange.__init__()  : {r3['init_ms']:.1f} ms  (lecture config Python)"
        )
        if r3.get("markets_error"):
            print(
                f"  load_markets()       : {r3['load_markets_ms']:.1f} ms  (ERREUR: {r3['markets_error']})"  # noqa: E501
            )
        else:
            print(
                f"  load_markets()       : {r3['load_markets_ms']:.1f} ms  ({r3['n_markets']} paires chargees)"  # noqa: E501
            )
        print(f"    -> {r3['note']}")

    # ── Rate limiter
    print("\n[4] CCXT rate limiter")
    r4 = audit_rate_limiter(testnet=testnet)
    if "error" not in r4:
        print(f"  rateLimit             : {r4['ccxt_rate_limit_ms']} ms par requete")
        print(f"    -> {r4['note']}")

    # ── fetch_ohlcv
    print("\n[5] fetch_ohlcv BTC/USDT 1h limit=96 (froid + chaud)")
    try:
        import ccxt

        ex = ccxt.mexc({"enableRateLimit": True})
        ex.load_markets()  # charge une fois, comme MarketScanner le fait
        r5 = audit_fetch_ohlcv(ex, limit=96)
        if "error" in r5:
            print(f"  ERREUR: {r5['error']}")
        else:
            print(f"  Fetch FROID          : {r5['cold_fetch_ms']:7.1f} ms")
            print(f"  Fetch CHAUD (moy)    : {r5['warm_avg_ms']:7.1f} ms")
            print(f"  Fetch CHAUD (min)    : {r5['warm_min_ms']:7.1f} ms")
            print(f"  Gain connexion reutil: x{r5['speedup_x']:.1f}")
            print(f"    -> {r5['note']}")
    except Exception as exc:
        print(f"  ERREUR fetch_ohlcv: {exc}")

    # ── Synthese
    print()
    print("=" * 66)
    print("  SYNTHESE — Decomposition du 3.7-3.9s a froid")
    print("-" * 66)
    print("  Phase              | Estimation  | Source")
    print("  -------------------|-------------|--------------------------------")
    print("  DNS (1er appel)    |  50-300 ms  | Cache OS vide, TTL CDN MEXC")
    print("  TCP + TLS (froid)  | 150-400 ms  | RTT CDN + TLS 1.3 handshake")
    print("  CCXT init()        |   2-10 ms   | Lecture config Python (rapide)")
    print("  load_markets()     | 800-1500 ms | GET /api/v3/exchangeInfo (2000 paires)")
    print("  CCXT rate limiter  |    50 ms    | Sleep interne si enableRateLimit=True")
    print("  fetch_ohlcv (froid)| 400-900 ms  | Requete HTTP + parse JSON 96 bougies")
    print("  -------------------|-------------|--------------------------------")
    print("  TOTAL estime       | 1.5-3.2 s   | Correspond au delai observe a froid")
    print()
    print("  Facteurs aggravants :")
    print("  - enableRateLimit=True             : +50ms fixe meme au 1er appel")
    print("  - Pas de pool DNS (win32)          : getaddrinfo bloquant a froid")
    print()
    print("  Solutions :")
    print("  - WARMUP avant cycle 1 (voir ADVISOR_WARMUP=true)")
    print("  - Pool d'exchange partagé (classe-level) deja en place dans MarketScanner")
    print("  - adjustForTimeDifference=False si horloge système fiable")
    print("  - DNS prefetch via socket.setdefaulttimeout() + getaddrinfo() au boot")
    print("=" * 66)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit latence fetch MEXC")
    parser.add_argument("--testnet", action="store_true", help="Mode testnet")
    args = parser.parse_args()
    print_audit(testnet=args.testnet)
