"""
observation/market_observer.py — Pouls du marché MEXC complet (spot + perp).

Couche d'OBSERVATION strictement passive (ADR-0016) :
  - processus SÉPARÉ du moteur — zéro import moteur, zéro écriture dans ses
    stores, API publique MEXC uniquement (aucune clé, aucun ordre possible) ;
  - écrit dans databases/observation/market_pulse_YYYY-MM-DD.jsonl.gz —
    répertoire que le chemin de décision ne lit jamais (corollaire ADR-0007 :
    le RegretEngine live alimente les deltas du gate via l'ATE, cette couche
    ne doit donc JAMAIS y être branchée) ;
  - garde-fou disque : saute l'écriture si l'espace libre passe sous
    OBS_MIN_FREE_DISK_GB (le VPS était à 92% au moment de l'ADR).

Enregistrement compact (1 par paire par tick) :
  {"ts", "sym", "mkt" ("spot"|"swap"), "last", "bid", "ask",
   "sp" (spread %), "qv" (volume quote 24h), "chg" (variation 24h %)}

Env :
  OBS_DIR                défaut databases/observation
  OBS_MIN_FREE_DISK_GB   défaut 1.5   (garde-fou disque)
  OBS_RETENTION_DAYS     défaut 45    (purge des .jsonl.gz plus anciens)
  OBS_EXCHANGE           défaut mexc

Usage :
  python observation/market_observer.py --once            # un tick
  python observation/market_observer.py --interval 900    # boucle
  python observation/market_observer.py --summary [DATE]  # lecture d'un jour
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKET_TYPES = ("spot", "swap")


def obs_exchanges() -> list[str]:
    """Exchanges observés (OBS_EXCHANGES, séparés par des virgules).

    Extension multi-exchange (2026-07-19, demande opérateur) : chaque
    enregistrement porte son champ "ex" — les sources ne sont JAMAIS
    fusionnées (leçon des « prix doubles » de l'époque Binance+MEXC).
    """
    raw = os.getenv("OBS_EXCHANGES", "mexc")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def primary_exchange() -> str:
    """Exchange PRIMAIRE — le seul que lisent radar/horizons/rejeu/top-K.

    L'univers tradé est MEXC : tout consommateur existant reste verrouillé
    dessus. Les autres sources ne servent qu'aux lectures croisées futures
    (validation de volumes, divergences), toujours groupées par "ex"."""
    return os.getenv("OBS_PRIMARY_EXCHANGE", "mexc").lower()


def is_primary_record(record: dict) -> bool:
    """Un record appartient-il à l'exchange primaire ?

    Les records historiques (avant multi-exchange) n'ont pas de champ
    "ex" — ils sont MEXC par construction, donc primaires."""
    ex = record.get("ex")
    return ex is None or ex == primary_exchange()


def _f(value, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v == v else default  # NaN → default


def obs_dir() -> Path:
    return Path(os.getenv("OBS_DIR", "databases/observation"))


def free_disk_gb(path: Path) -> float:
    probe = (
        path if path.exists() else path.parent if path.parent.exists() else Path(".")
    )
    return shutil.disk_usage(probe).free / 1e9


def build_record(
    ts: float, symbol: str, market: str, raw: dict, ex: str | None = None
) -> dict | None:
    """Ticker ccxt → enregistrement compact. None si le ticker est inutilisable.

    `ex` = exchange source ; absent/None = MEXC (records historiques).
    La clé logique d'un enregistrement est (ex, sym, mkt) — jamais (sym)
    seul : deux exchanges ne partagent jamais une ligne."""
    last = _f(raw.get("last"))
    if last <= 0:
        return None
    bid = _f(raw.get("bid"))
    ask = _f(raw.get("ask"))
    spread = round((ask - bid) / ask * 100.0, 4) if ask > 0 and bid > 0 else None
    qv = _f(raw.get("quoteVolume"))
    if qv <= 0:
        qv = _f(raw.get("baseVolume")) * last
    rec = {
        "ts": round(ts, 1),
        "sym": symbol,
        "mkt": market,
        "last": last,
        "bid": bid if bid > 0 else None,
        "ask": ask if ask > 0 else None,
        "sp": spread,
        "qv": round(qv, 2),
        "chg": round(_f(raw.get("percentage")), 4),
    }
    if ex is not None:
        rec["ex"] = ex
    return rec


def day_file(directory: Path, ts: float) -> Path:
    day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return directory / f"market_pulse_{day}.jsonl.gz"


def append_records(path: Path, records: list[dict]) -> int:
    """Ajoute les enregistrements au fichier gzip du jour. Retourne les octets écrits.

    gzip en mode append crée des membres successifs — le module gzip les
    relit de façon transparente comme un flux unique.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "\n".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records
        )
        + "\n"
    ).encode("utf-8")
    with gzip.open(path, "ab") as fh:
        fh.write(payload)
    return len(payload)


def read_day(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def prune_old_files(directory: Path, retention_days: int, now: float) -> list[str]:
    """Supprime les market_pulse_*.jsonl.gz plus vieux que la rétention."""
    cutoff = datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(
        days=retention_days
    )
    removed: list[str] = []
    for fp in glob.glob(str(directory / "market_pulse_*.jsonl.gz")):
        name = Path(fp).name
        try:
            day = datetime.strptime(
                name.replace("market_pulse_", "").replace(".jsonl.gz", ""),
                "%Y-%m-%d",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if day < cutoff:
            Path(fp).unlink(missing_ok=True)
            removed.append(name)
    return removed


# ── Collecte (seule partie réseau — API publique, aucune clé) ─────────────────


def _make_client(market_type: str, exchange_id: str | None = None):
    import ccxt  # import local — les tests n'en ont pas besoin

    exchange_id = exchange_id or os.getenv("OBS_EXCHANGE", "mexc")
    klass = getattr(ccxt, exchange_id)
    return klass({"enableRateLimit": True, "options": {"defaultType": market_type}})


def snapshot_once(directory: Path | None = None) -> dict:
    """Un tick complet : 2 fetch_tickers (spot+swap) → fichier gzip du jour.

    Retourne un résumé {counts, bytes_written, skipped_disk, file}.
    """
    directory = directory or obs_dir()
    now = time.time()
    min_free = float(os.getenv("OBS_MIN_FREE_DISK_GB", "1.5"))
    retention = int(os.getenv("OBS_RETENTION_DAYS", "45"))

    free_gb = free_disk_gb(directory)
    if free_gb < min_free:
        return {
            "counts": {},
            "bytes_written": 0,
            "skipped_disk": True,
            "free_gb": round(free_gb, 2),
            "file": None,
        }

    records: list[dict] = []
    counts: dict[str, int] = {}
    for ex in obs_exchanges():
        for market in MARKET_TYPES:
            # Un échec (ex, marché) n'annule jamais le tick des autres
            # sources — ex : kucoin n'a pas de swap sous cet id ccxt.
            try:
                client = _make_client(market, exchange_id=ex)
                tickers = client.fetch_tickers()
            except Exception:
                counts[f"{ex}:{market}"] = -1  # source en échec, visible
                continue
            n = 0
            for sym, raw in tickers.items():
                rec = build_record(now, sym, market, raw or {}, ex=ex)
                if rec is not None:
                    records.append(rec)
                    n += 1
            counts[f"{ex}:{market}"] = n

    path = day_file(directory, now)
    written = append_records(path, records) if records else 0
    if records:
        write_latest_tick(directory, now, records)
    pruned = prune_old_files(directory, retention, now)
    return {
        "counts": counts,
        "bytes_written": written,
        "skipped_disk": False,
        "free_gb": round(free_gb, 2),
        "file": str(path),
        "pruned": pruned,
    }


def write_latest_tick(directory: Path, now: float, records: list[dict]) -> None:
    """Sidecar compact du DERNIER tick — lu par l'ordonnanceur top-K du
    moteur (core/topk_scheduler.py, ADR-0017 paliers 2-3) pour désigner les
    paires « chaudes » à analyser en priorité. Écriture atomique
    (tmp + replace) : jamais de lecture déchirée côté moteur. Le pouls
    reste passif : il DÉSIGNE des candidats à analyser, il n'autorise rien."""
    payload = {
        "ts": round(now, 1),
        # PRIMAIRE uniquement (verrou anti-prix-doubles) : le top-K du
        # moteur ne doit jamais voir deux sources pour un même symbole.
        "pairs": {
            r["sym"]: {"chg": r.get("chg"), "mkt": r.get("mkt")}
            for r in records
            if r.get("mkt") == "spot" and is_primary_record(r)
        },
    }
    tmp = directory / "latest_tick.json.tmp"
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, directory / "latest_tick.json")


# ── Résumé lecture (audit rapide) ──────────────────────────────────────────────


def summarize_day(directory: Path, day: str) -> str:
    path = directory / f"market_pulse_{day}.jsonl.gz"
    records = read_day(path)
    if not records:
        return f"Aucune donnée pour {day} ({path})"
    ticks = sorted({r["ts"] for r in records})
    by_mkt: dict[str, set] = {}
    for r in records:
        key = f"{r.get('ex', 'mexc')}:{r.get('mkt', '?')}"
        by_mkt.setdefault(key, set()).add(r.get("sym"))
    # Top movers sur le PRIMAIRE uniquement — sinon chaque pump apparaît
    # en double/triple (une fois par exchange).
    top = sorted(
        (r for r in records if r["ts"] == ticks[-1] and is_primary_record(r)),
        key=lambda r: abs(_f(r.get("chg"))),
        reverse=True,
    )[:5]
    lines = [
        f"POULS MARCHÉ — {day}",
        f"  {len(records)} observations | {len(ticks)} tick(s)"
        f" | paires: " + ", ".join(f"{m}={len(s)}" for m, s in sorted(by_mkt.items())),
        "  Top variations 24h (dernier tick):",
    ]
    for r in top:
        lines.append(
            f"    {r['sym']:<18} {r.get('mkt', '?'):<4} {_f(r.get('chg')):+8.2f}%"
            f"  vol24h=${_f(r.get('qv')):,.0f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pouls du marché MEXC complet — observation passive (ADR-0016)"
    )
    parser.add_argument("--once", action="store_true", help="un tick puis sortie")
    parser.add_argument("--interval", type=float, default=0.0, help="boucle (secondes)")
    parser.add_argument(
        "--summary",
        nargs="?",
        const="today",
        default=None,
        help="résumé d'un jour (YYYY-MM-DD, défaut aujourd'hui)",
    )
    args = parser.parse_args(argv)

    directory = obs_dir()

    if args.summary is not None:
        day = (
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if args.summary == "today"
            else args.summary
        )
        print(summarize_day(directory, day))
        return 0

    if args.once or args.interval <= 0:
        summary = snapshot_once(directory)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if not summary["skipped_disk"] else 1

    while True:  # pragma: no cover — boucle opérationnelle (systemd timer préféré)
        summary = snapshot_once(directory)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        time.sleep(max(60.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
