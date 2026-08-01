"""AccountCollector — état instantané des comptes réels (ADR-0019, Phase A).

Fonction pure ``(clients) -> enregistrement`` : aucun état partagé, aucun
cache, aucun client construit tant qu'un client est injecté.

Trois sources, **isolées** : `spot.fetch_balance`, `swap.fetch_balance` et
`spot.fetch_tickers`. L'échec de l'une est visible sur sa propre ligne et ne
casse jamais la lecture des autres (règle héritée d'OBS_EXCHANGES). Spot et
futures ne partagent jamais une ligne.

`fetch_tickers` en **un seul appel** remplace jusqu'à 60 `fetch_ticker`
unitaires et supprime la raison d'être du plafond `_MAX_PRICED_ASSETS`
(`observability/real_accounts.py:36`) : coût en baisse, couverture en hausse.

**Honnêteté de l'equity** : `equity_total_usd` est une **borne inférieure**
dès qu'un actif n'est pas valorisable ou qu'une source manque.
`equity_is_lower_bound`, `unpriced` et `assets_total` le disent explicitement
— aucune troncature silencieuse, pas de Top-6.

Affichage et historisation seulement : la base de sizing reste épinglée à
`WALLET_PAPER_CAPITAL` (ADR-0007, CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._common import SCHEMA_VERSION, STABLE_ASSETS, safe_float, source_error, utc_now_iso


@dataclass(frozen=True)
class AssetBalance:
    asset: str
    wallet: str  # "spot" | "futures"
    total: float
    free: float
    used: float
    usd_value: float | None  # None = prix introuvable → exclu du total


@dataclass(frozen=True)
class AccountRecord:
    """État instantané d'un compte. Aucun verdict, aucune alerte (OBS-I)."""

    schema_version: int
    ts_utc: str
    exchange: str
    spot_assets: tuple[AssetBalance, ...] = field(default_factory=tuple)
    futures_assets: tuple[AssetBalance, ...] = field(default_factory=tuple)
    equity_spot_usd: float = 0.0
    equity_futures_usd: float = 0.0
    equity_total_usd: float = 0.0
    margin_used_usd: float = 0.0
    margin_free_usd: float = 0.0
    unpriced: tuple[str, ...] = field(default_factory=tuple)
    assets_total: int = 0
    equity_is_lower_bound: bool = False
    sources_ok: tuple[str, ...] = field(default_factory=tuple)
    sources_failed: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def collect_account(
    spot_client: Any, swap_client: Any, exchange: str = "mexc"
) -> AccountRecord:
    """Lit soldes spot, soldes futures et marge, valorise en un `fetch_tickers`."""
    ok: list[str] = []
    failed: list[tuple[str, str]] = []

    spot_raw = _read(spot_client, "fetch_balance", "spot.fetch_balance", ok, failed)
    swap_raw = _read(swap_client, "fetch_balance", "swap.fetch_balance", ok, failed)
    tickers = _read(spot_client, "fetch_tickers", "spot.fetch_tickers", ok, failed)
    prices = _usd_prices(tickers)

    spot_assets = _wallet_assets(spot_raw, "spot", prices)
    futures_assets = _wallet_assets(swap_raw, "futures", prices)
    unpriced = tuple(
        a.asset for a in (*spot_assets, *futures_assets) if a.usd_value is None
    )
    equity_spot = _sum_usd(spot_assets)
    equity_futures = _sum_usd(futures_assets)

    return AccountRecord(
        schema_version=SCHEMA_VERSION,
        ts_utc=utc_now_iso(),
        exchange=exchange,
        spot_assets=spot_assets,
        futures_assets=futures_assets,
        equity_spot_usd=equity_spot,
        equity_futures_usd=equity_futures,
        equity_total_usd=round(equity_spot + equity_futures, 8),
        margin_used_usd=_sum_field(futures_assets, prices, "used"),
        margin_free_usd=_sum_field(futures_assets, prices, "free"),
        unpriced=unpriced,
        assets_total=len(spot_assets) + len(futures_assets),
        equity_is_lower_bound=bool(unpriced) or bool(failed),
        sources_ok=tuple(ok),
        sources_failed=tuple(failed),
    )


# ── interne ─────────────────────────────────────────────────────────────────


def _read(
    client: Any,
    method: str,
    label: str,
    ok: list[str],
    failed: list[tuple[str, str]],
) -> Any:
    """Un appel, isolé : son échec est enregistré, jamais propagé."""
    if client is None:
        failed.append((label, "NoClient: aucun client injecté"))
        return None
    try:
        result = getattr(client, method)()
    except Exception as exc:  # une source en panne ne casse jamais les autres
        failed.append((label, source_error(exc)))
        return None
    ok.append(label)
    return result


def _usd_prices(tickers: Any) -> dict[str, float]:
    """Prix USD par actif, depuis un unique `fetch_tickers`.

    Seuls les marchés cotés en USDT/USDC/USD sont retenus ; le suffixe
    `:USDT` des symboles de contrats ccxt est toléré.
    """
    prices: dict[str, float] = {}
    if not isinstance(tickers, dict):
        return prices
    for symbol, raw in tickers.items():
        if not isinstance(symbol, str) or "/" not in symbol:
            continue
        base, _, quote = symbol.partition("/")
        if quote.split(":")[0] not in ("USDT", "USDC", "USD"):
            continue
        last = None
        if isinstance(raw, dict):
            last = safe_float(raw.get("last")) or safe_float(raw.get("close"))
        if last and base not in prices:
            prices[base] = last
    return prices


def _wallet_assets(
    balance: Any, wallet: str, prices: dict[str, float]
) -> tuple[AssetBalance, ...]:
    """Soldes non nuls d'un portefeuille, valorisés puis triés par valeur."""
    if not isinstance(balance, dict):
        return ()
    totals = balance.get("total") or {}
    frees = balance.get("free") or {}
    useds = balance.get("used") or {}
    assets: list[AssetBalance] = []
    for asset, qty in (totals.items() if isinstance(totals, dict) else ()):
        if asset == "info":
            continue
        total = safe_float(qty)
        if total is None or total <= 0:
            continue
        assets.append(
            AssetBalance(
                asset=str(asset),
                wallet=wallet,
                total=total,
                free=safe_float(frees.get(asset)) or 0.0,
                used=safe_float(useds.get(asset)) or 0.0,
                usd_value=_usd_value(str(asset), total, prices),
            )
        )
    assets.sort(key=lambda a: (a.usd_value is None, -(a.usd_value or 0.0), a.asset))
    return tuple(assets)


def _usd_value(asset: str, qty: float, prices: dict[str, float]) -> float | None:
    """Stables valorisées 1:1 ; tout le reste exige un prix issu de `fetch_tickers`."""
    if asset in STABLE_ASSETS:
        return round(qty, 8)
    price = prices.get(asset)
    return round(qty * price, 8) if price else None


def _sum_usd(assets: tuple[AssetBalance, ...]) -> float:
    return round(sum(a.usd_value for a in assets if a.usd_value is not None), 8)


def _sum_field(
    assets: tuple[AssetBalance, ...], prices: dict[str, float], attr: str
) -> float:
    """Somme USD d'un champ (free/used) — actifs non valorisables exclus."""
    total = 0.0
    for asset in assets:
        value = _usd_value(asset.asset, getattr(asset, attr), prices)
        if value is not None:
            total += value
    return round(total, 8)
