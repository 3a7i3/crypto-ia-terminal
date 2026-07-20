"""Comptes réels multi-exchange — observation passive (« compte n°1 »).

Lit les soldes des comptes API réels configurés via ``{EXCHANGE}_API_KEY`` /
``{EXCHANGE}_API_SECRET`` (binance, mexc, kraken, gateio). Lecture seule
stricte : ``fetch_balance`` + ``fetch_ticker`` uniquement, jamais d'ordre.
Affichage uniquement — jamais utilisé pour le sizing (ADR-0007, base de
sizing épinglée à WALLET_PAPER_CAPITAL, voir CLAUDE.md).

Séparation des sources (même principe que OBS_EXCHANGES, dc86160) :
chaque compte porte son champ ``exchange``, deux comptes ne partagent
jamais une ligne ; l'échec d'une source est visible sur sa propre ligne
et ne casse jamais la lecture des autres.
"""

from __future__ import annotations

import html
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger(__name__)

# Exchanges dont les clés sont cherchées dans l'environnement, dans cet ordre.
SUPPORTED_EXCHANGES: tuple[str, ...] = ("mexc", "binance", "kraken", "gateio")

# Actifs valorisés 1:1 en USD sans passer par un ticker.
STABLE_ASSETS: frozenset[str] = frozenset(
    {"USDT", "USDC", "USD", "FDUSD", "TUSD", "DAI", "BUSD", "USDE", "USD1"}
)

# Bornes de sécurité : jamais plus de N tickers par compte et par refresh.
_MAX_PRICED_ASSETS = 30


@dataclass(frozen=True)
class RealAsset:
    asset: str
    total: float
    free: float
    usd_value: float | None  # None = prix introuvable (exclu du total)


@dataclass(frozen=True)
class RealAccountSnapshot:
    exchange: str
    ok: bool
    ts_utc: str
    assets: tuple[RealAsset, ...] = field(default_factory=tuple)
    total_usd: float | None = None  # somme des actifs valorisés uniquement
    unpriced: int = 0
    error: str = ""


def configured_exchanges() -> list[str]:
    """Exchanges dont clé ET secret sont présents dans l'environnement.

    ``REAL_ACCOUNTS_EXCHANGES`` (liste séparée par des virgules) restreint
    ou réordonne la détection ; par défaut, tous les SUPPORTED_EXCHANGES
    sont candidats.
    """
    forced = os.getenv("REAL_ACCOUNTS_EXCHANGES", "").strip()
    if forced:
        names = [x.strip().lower() for x in forced.split(",") if x.strip()]
    else:
        names = list(SUPPORTED_EXCHANGES)
    out: list[str] = []
    for ex in names:
        key = os.getenv(f"{ex.upper()}_API_KEY", "").strip()
        secret = os.getenv(f"{ex.upper()}_API_SECRET", "").strip()
        if key and secret:
            out.append(ex)
    return out


def _default_client_factory(exchange: str) -> Any:
    import ccxt  # import paresseux — jamais au boot

    cls = getattr(ccxt, exchange)
    return cls(
        {
            "apiKey": os.getenv(f"{exchange.upper()}_API_KEY", "").strip(),
            "secret": os.getenv(f"{exchange.upper()}_API_SECRET", "").strip(),
            "enableRateLimit": True,
            "timeout": 10_000,
        }
    )


class RealAccountsObserver:
    """Observation passive des soldes réels, avec cache TTL.

    TTL par défaut 900 s (REAL_ACCOUNTS_TTL_S) : au rythme du rapport
    15 min, chaque compte est interrogé au plus une fois par rapport.
    """

    def __init__(
        self,
        ttl_s: float | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._ttl = (
            float(os.getenv("REAL_ACCOUNTS_TTL_S", "900")) if ttl_s is None else ttl_s
        )
        self._client_factory = client_factory or _default_client_factory
        self._clients: dict[str, Any] = {}
        self._cache: tuple[float, tuple[RealAccountSnapshot, ...]] | None = None

    def snapshot(self, force: bool = False) -> tuple[RealAccountSnapshot, ...]:
        now = time.monotonic()
        if not force and self._cache is not None and now - self._cache[0] < self._ttl:
            return self._cache[1]
        snaps = tuple(self._read_one(ex) for ex in configured_exchanges())
        self._cache = (now, snaps)
        return snaps

    # ── interne ──────────────────────────────────────────────────────────

    def _client(self, exchange: str) -> Any:
        if exchange not in self._clients:
            self._clients[exchange] = self._client_factory(exchange)
        return self._clients[exchange]

    def _read_one(self, exchange: str) -> RealAccountSnapshot:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        try:
            client = self._client(exchange)
            bal = client.fetch_balance()
            totals = bal.get("total", {}) or {}
            frees = bal.get("free", {}) or {}
            raw: list[tuple[str, float, float]] = []
            for sym, qty in totals.items():
                if sym == "info" or qty is None:
                    continue
                try:
                    q = float(qty)
                except (TypeError, ValueError):
                    continue
                if q <= 0:
                    continue
                try:
                    f = float(frees.get(sym) or 0.0)
                except (TypeError, ValueError):
                    f = 0.0
                raw.append((str(sym), q, f))
            # Stables d'abord (valorisation gratuite), puis quantité décroissante.
            raw.sort(key=lambda it: (it[0] not in STABLE_ASSETS, -it[1]))
            assets: list[RealAsset] = []
            priced_calls = 0
            for sym, q, f in raw:
                if sym in STABLE_ASSETS:
                    usd: float | None = q
                elif priced_calls < _MAX_PRICED_ASSETS:
                    priced_calls += 1
                    usd = self._price_usd(client, sym, q)
                else:
                    usd = None
                assets.append(RealAsset(asset=sym, total=q, free=f, usd_value=usd))
            assets.sort(
                key=lambda a: (a.usd_value is None, -(a.usd_value or 0.0), a.asset)
            )
            valued = [a.usd_value for a in assets if a.usd_value is not None]
            return RealAccountSnapshot(
                exchange=exchange,
                ok=True,
                ts_utc=ts,
                assets=tuple(assets),
                total_usd=round(sum(valued), 2) if valued else 0.0,
                unpriced=sum(1 for a in assets if a.usd_value is None),
            )
        except Exception as exc:  # une source en panne ne casse jamais les autres
            log.debug("[Compte1] %s illisible: %s", exchange, exc)
            return RealAccountSnapshot(
                exchange=exchange, ok=False, ts_utc=ts, error=str(exc)[:160]
            )

    @staticmethod
    def _price_usd(client: Any, asset: str, qty: float) -> float | None:
        for quote in ("USDT", "USDC"):
            try:
                ticker = client.fetch_ticker(f"{asset}/{quote}")
                last = ticker.get("last") or ticker.get("close")
                if last:
                    return round(qty * float(last), 2)
            except Exception:
                continue
        return None


# ── Rendus ────────────────────────────────────────────────────────────────


def render_compte1_block(snaps: tuple[RealAccountSnapshot, ...]) -> str:
    """Bloc compact du rapport principal 15 min (texte brut)."""
    if not snaps:
        return ""
    lines = ["COMPTE N°1 (reel, lecture seule):"]
    for s in snaps:
        name = s.exchange.upper()
        if s.ok:
            extra = f" | {s.unpriced} sans prix" if s.unpriced else ""
            lines.append(
                f"  {name:<8} ${s.total_usd:.2f} | {len(s.assets)} actifs{extra} ✔"
            )
        else:
            lines.append(f"  {name:<8} erreur: {s.error[:60]} ✘")
    return "\n".join(lines)


def render_real_accounts_detail(
    snaps: tuple[RealAccountSnapshot, ...], cycle: int
) -> str:
    """Détail par actif pour le bot compte réel (parse_mode HTML)."""
    if not snaps:
        return ""
    dust = float(os.getenv("REAL_ACCOUNTS_DUST_USD", "0.50"))
    out = [
        f"🏦 <b>Comptes réels (API, lecture seule) — Cycle #{cycle}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for s in snaps:
        name = html.escape(s.exchange.upper())
        if not s.ok:
            out.append(f"<b>{name}</b> — ERREUR : {html.escape(s.error)}")
            out.append("")
            continue
        out.append(f"<b>{name}</b> — ${s.total_usd:.2f} USDT ({len(s.assets)} actifs)")
        dust_n, dust_usd = 0, 0.0
        for a in s.assets:
            sym = html.escape(a.asset)
            if a.usd_value is None:
                out.append(f"  {sym} : {a.total:.8g} (prix indisponible)")
            elif a.usd_value < dust:
                dust_n += 1
                dust_usd += a.usd_value
            else:
                out.append(f"  {sym} : {a.total:.8g}  (~${a.usd_value:.2f})")
        if dust_n:
            out.append(f"  + {dust_n} actif(s) &lt; ${dust:.2f} (~${dust_usd:.2f})")
        out.append("")
    return "\n".join(out).rstrip()
