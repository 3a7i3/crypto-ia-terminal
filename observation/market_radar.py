"""
observation/market_radar.py — Radar de marché global R1 (ADR-0016, phase R1).

Classe les ~3200 paires du pouls (market_observer) et produit la shortlist
des meilleures candidates « tradables » : liquidité, coût de transaction,
activité, fiabilité des données. STRICTEMENT PASSIF : lit le store
d'observation, écrit une shortlist dans le même store — jamais lu par le
chemin de décision. Le passage réel d'un palier de l'univers TRADÉ reste
une décision opérateur par ADR (paliers 100-200 → 500 → 1000, cf ADR-0016
§O3).

Anti-spam Telegram (exigence opérateur 2026-07-15) : le radar n'écrit
JAMAIS par symbole — un seul digest par exécution, et uniquement si
RADAR_TELEGRAM_DIGEST=true (défaut false ; utilise INTEL_BOT_TOKEN +
INTEL_BOT_CHAT_ID, même canal que le rapport 6h).

Scoring — mêmes références que tools/perp_universe_builder.py (aucun
indicateur nouveau, gel scientifique) :
  liquidité 40 % (volume quote médian, échelle log 500k$ → 500M$)
  spread    30 % (médian ; 0.01 % parfait, 0.30 % nul)
  activité  20 % (range intrajournalier réalisé, réf 3 %)
  fiabilité 10 % (présence de la paire dans les ticks de la fenêtre)

Filtres durs : volume < RADAR_MIN_QUOTE_VOL_USD, spread médian >
RADAR_MAX_SPREAD_PCT, présence < 50 %, quote hors RADAR_QUOTES,
tokens à levier (3L/3S/…), SYMBOL_BLACKLIST.

Usage :
  python observation/market_radar.py --run             # calcule + stocke
  python observation/market_radar.py --digest [DATE]   # relit un digest
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from observation.market_observer import day_file, obs_dir, read_day

# Références de scoring — alignées sur PerpUniverseBuilder (pas de nouveau
# barème, seulement la même grille appliquée au store d'observation).
_VOL_FLOOR = float(os.getenv("RADAR_MIN_QUOTE_VOL_USD", "500000"))
_VOL_REF = 500_000_000.0
_SPREAD_PERFECT = 0.01
_SPREAD_MAX_SCORE = 0.30
_RANGE_REF_PCT = 3.0
_MAX_SPREAD = float(os.getenv("RADAR_MAX_SPREAD_PCT", "0.50"))
_MIN_PRESENCE = 0.50
_TOP_N = int(os.getenv("RADAR_TOP_N", "200"))

_LEVERAGED_RE = re.compile(r"\d[LS]$")

WEIGHTS = {"liquidity": 0.40, "spread": 0.30, "activity": 0.20, "reliability": 0.10}


def _f(value, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v == v else default


def _allowed_quotes() -> frozenset[str]:
    return frozenset(
        q.strip().upper()
        for q in os.getenv("RADAR_QUOTES", "USDT,USDC").split(",")
        if q.strip()
    )


def _blacklist() -> frozenset[str]:
    return frozenset(
        s.strip().upper()
        for s in os.getenv("SYMBOL_BLACKLIST", "").split(",")
        if s.strip()
    )


def split_symbol(sym: str) -> tuple[str, str]:
    """'BTC/USDT' ou 'BTC/USDT:USDT' (swap) → (base, quote)."""
    core = sym.split(":", 1)[0]
    if "/" not in core:
        return core, ""
    base, quote = core.split("/", 1)
    return base, quote.upper()


def is_eligible_symbol(sym: str) -> bool:
    base, quote = split_symbol(sym)
    if quote not in _allowed_quotes():
        return False
    if _LEVERAGED_RE.search(base):
        return False
    if sym.split(":", 1)[0].upper() in _blacklist():
        return False
    return True


# ── Agrégation de la fenêtre d'observation ─────────────────────────────────────


def aggregate_pairs(records: list[dict]) -> dict[tuple[str, str], dict]:
    """Records du pouls → stats par (symbol, marché) sur la fenêtre."""
    ticks = sorted({_f(r.get("ts")) for r in records if _f(r.get("ts")) > 0})
    n_ticks = max(1, len(ticks))
    pairs: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (str(r.get("sym", "?")), str(r.get("mkt", "?")))
        d = pairs.setdefault(key, {"qv": [], "sp": [], "last": [], "chg": 0.0})
        d["qv"].append(_f(r.get("qv")))
        if r.get("sp") is not None:
            d["sp"].append(_f(r.get("sp")))
        d["last"].append(_f(r.get("last")))
        d["chg"] = _f(r.get("chg"))  # dernier vu = plus récent (fichiers triés)

    out: dict[tuple[str, str], dict] = {}
    for key, d in pairs.items():
        lasts = [x for x in d["last"] if x > 0]
        if not lasts:
            continue
        last_med = statistics.median(lasts)
        range_pct = (
            (max(lasts) - min(lasts)) / last_med * 100.0 if last_med > 0 else 0.0
        )
        out[key] = {
            "qv_med": statistics.median(d["qv"]) if d["qv"] else 0.0,
            "sp_med": statistics.median(d["sp"]) if d["sp"] else None,
            "range_pct": round(range_pct, 4),
            "chg_24h": d["chg"],
            "presence": min(1.0, len(lasts) / n_ticks),
        }
    return out


# ── Scores (0-100) ─────────────────────────────────────────────────────────────


def score_liquidity(qv_med: float) -> float:
    if qv_med <= _VOL_FLOOR:
        return 0.0
    return min(
        100.0,
        100.0 * math.log10(qv_med / _VOL_FLOOR) / math.log10(_VOL_REF / _VOL_FLOOR),
    )


def score_spread(sp_med: float | None) -> float:
    if sp_med is None:
        return 0.0
    if sp_med <= _SPREAD_PERFECT:
        return 100.0
    if sp_med >= _SPREAD_MAX_SCORE:
        return 0.0
    return 100.0 * (_SPREAD_MAX_SCORE - sp_med) / (_SPREAD_MAX_SCORE - _SPREAD_PERFECT)


def score_activity(range_pct: float) -> float:
    return min(100.0, 100.0 * range_pct / _RANGE_REF_PCT)


def rank_universe(
    aggregated: dict[tuple[str, str], dict], top_n: int = _TOP_N
) -> list[dict]:
    """Filtres durs + score composite → shortlist triée."""
    ranked: list[dict] = []
    for (sym, mkt), st in aggregated.items():
        if not is_eligible_symbol(sym):
            continue
        if st["qv_med"] < _VOL_FLOOR:
            continue
        if st["sp_med"] is None or st["sp_med"] > _MAX_SPREAD:
            continue
        if st["presence"] < _MIN_PRESENCE:
            continue
        scores = {
            "liquidity": round(score_liquidity(st["qv_med"]), 1),
            "spread": round(score_spread(st["sp_med"]), 1),
            "activity": round(score_activity(st["range_pct"]), 1),
            "reliability": round(st["presence"] * 100.0, 1),
        }
        composite = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
        ranked.append(
            {
                "sym": sym,
                "mkt": mkt,
                "score": round(composite, 2),
                "scores": scores,
                "qv_med": round(st["qv_med"], 2),
                "sp_med": st["sp_med"],
                "range_pct": st["range_pct"],
                "chg_24h": st["chg_24h"],
            }
        )
    ranked.sort(key=lambda e: e["score"], reverse=True)
    return ranked[:top_n]


# ── Persistance + diff jour précédent ──────────────────────────────────────────


def shortlist_path(directory: Path, day: str) -> Path:
    return directory / f"radar_shortlist_{day}.json"


def load_shortlist_syms(directory: Path, day: str) -> set[str]:
    path = shortlist_path(directory, day)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {e["sym"] for e in data.get("shortlist", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return set()


def run_radar(directory: Path | None = None, now: float | None = None) -> dict:
    """Fenêtre 24h du pouls → shortlist du jour, stockée en JSON."""
    directory = directory or obs_dir()
    now = now or time.time()
    since = now - 24 * 3600.0

    records: list[dict] = []
    for offset in (86400.0, 0.0):  # fichier d'hier puis d'aujourd'hui
        for r in read_day(day_file(directory, now - offset)):
            if _f(r.get("ts")) >= since:
                records.append(r)

    aggregated = aggregate_pairs(records)
    shortlist = rank_universe(aggregated)

    today = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
    yesterday = (
        datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    prev_syms = load_shortlist_syms(directory, yesterday)
    cur_syms = {e["sym"] for e in shortlist}

    payload = {
        "generated_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "window_h": 24,
        "n_observed_pairs": len(aggregated),
        "n_shortlist": len(shortlist),
        "params": {
            "min_quote_vol_usd": _VOL_FLOOR,
            "max_spread_pct": _MAX_SPREAD,
            "top_n": _TOP_N,
            "quotes": sorted(_allowed_quotes()),
        },
        "entries": sorted(cur_syms - prev_syms) if prev_syms else [],
        "exits": sorted(prev_syms - cur_syms) if prev_syms else [],
        "shortlist": shortlist,
    }
    path = shortlist_path(directory, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    payload["file"] = str(path)
    return payload


# ── Digest (un seul message, jamais par symbole) ───────────────────────────────


def render_digest(payload: dict, top: int = 15) -> str:
    shortlist = payload.get("shortlist", [])
    by_mkt: dict[str, int] = {}
    for e in shortlist:
        by_mkt[e["mkt"]] = by_mkt.get(e["mkt"], 0) + 1
    lines = [
        "RADAR MARCHÉ R1 — shortlist du jour",
        f"{payload.get('n_shortlist', 0)} paires retenues sur "
        f"{payload.get('n_observed_pairs', 0)} observées "
        f"({', '.join(f'{m}={n}' for m, n in sorted(by_mkt.items()))})",
    ]
    entries, exits = payload.get("entries", []), payload.get("exits", [])
    if entries or exits:
        lines.append(f"Entrées: {len(entries)} | Sorties: {len(exits)}")
        if entries:
            lines.append("  + " + ", ".join(entries[:10]))
        if exits:
            lines.append("  - " + ", ".join(exits[:10]))
    lines.append(f"Top {min(top, len(shortlist))}:")
    for e in shortlist[:top]:
        lines.append(
            f"  {e['sym']:<16} {e['mkt']:<4} score={e['score']:>5.1f}"
            f" vol=${e['qv_med'] / 1e6:>7.1f}M"
            f" sp={e['sp_med']:.3f}% chg={e['chg_24h']:+.1f}%"
        )
    lines.append(
        "(radar passif — la sélection tradée reste l'univers épinglé ADR-0015)"
    )
    return "\n".join(lines)


def send_telegram_digest(text: str) -> bool:
    """Un seul message, canal Intel — seulement si RADAR_TELEGRAM_DIGEST=true."""
    if os.getenv("RADAR_TELEGRAM_DIGEST", "false").lower() != "true":
        return False
    token = os.getenv("INTEL_BOT_TOKEN", "")
    chat = os.getenv("INTEL_BOT_CHAT_ID", "")
    if not token or not chat:
        return False
    import urllib.request

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 — https
            return resp.status == 200
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Radar de marché global R1 — shortlist passive (ADR-0016)"
    )
    parser.add_argument("--run", action="store_true", help="calcule et stocke")
    parser.add_argument(
        "--digest",
        nargs="?",
        const="today",
        default=None,
        help="affiche le digest d'un jour (YYYY-MM-DD)",
    )
    parser.add_argument("--top", type=int, default=15, help="taille du top affiché")
    args = parser.parse_args(argv)

    directory = obs_dir()

    if args.run:
        payload = run_radar(directory)
        digest = render_digest(payload, top=args.top)
        print(digest)
        sent = send_telegram_digest(digest)
        tg = "oui" if sent else "non"
        print(f"[radar] shortlist -> {payload['file']} | telegram={tg}")
        return 0

    day = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if args.digest in (None, "today")
        else args.digest
    )
    path = shortlist_path(directory, day)
    if not path.exists():
        print(f"Aucune shortlist pour {day} ({path})")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(render_digest(payload, top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
