"""
trade_analysis/selection.py — Moteur de selection dynamique des symboles.

Repond a la question :
  "Quels symboles l'observatoire LMI doit-il regarder en priorite ?"

Classe et filtre l'univers observable selon trois axes, tous lus depuis
des sources DEJA produites par la couche d'observation (lecture seule) :

  1. Market cap (proxy)  : qv_med du radar_shortlist (volume quote 24h)
  2. Volatilite          : range_pct du radar_shortlist
  3. Win / loss          : is_win agrege depuis paper_trades.jsonl

Strictement passif (ADR-0007) : ce module NE decide RIEN sur le trading.
Il ne fait que choisir quels symboles seront OBSERVES par le LMI.

Aucune donnee n'est copiee : les fichiers sources restent la propriete
de la couche d'observation et du paper trading.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

OBS_DIR = Path(os.getenv("OBS_DIR", "databases/observation"))
PAPER_TRADE_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))


def normalize_symbol(raw: str) -> str:
    """
    Normalise vers le format interne 'BTCUSDT'.

    Gere les notations CCXT :
      'BTC/USDT'        -> 'BTCUSDT'
      'BTC_USDT'        -> 'BTCUSDT'
      'BTC/USDT:USDT'   -> 'BTCUSDT'  (suffixe settle des swaps, ignore)
      'BTCUSDT:USDT'    -> 'BTCUSDT'

    Le suffixe ':<settle>' est retire : sans cela le meme marche apparait
    en double ('BTCUSDT:USDT' vs 'BTCUSDT') et le connecteur WebSocket ne
    sait pas souscrire au symbole.
    """
    base = raw.split(":", 1)[0]
    return base.replace("/", "").replace("_", "").upper()


@dataclass
class SymbolCandidate:
    """Un symbole candidat a l'observation, avec ses metriques de selection."""

    symbol: str
    market_cap_proxy: float  # qv_med — volume quote 24h (USD)
    volatility: float  # range_pct — amplitude 24h (%)
    radar_score: float  # score composite radar
    n_trades: int  # trades fermes (paper) sur ce symbole
    wins: int
    losses: int

    @property
    def win_rate(self) -> Optional[float]:
        """Taux de reussite [0,1], None si aucun trade ferme."""
        decided = self.wins + self.losses
        if decided == 0:
            return None
        return self.wins / decided

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "market_cap_proxy": round(self.market_cap_proxy, 2),
            "volatility": round(self.volatility, 4),
            "radar_score": round(self.radar_score, 2),
            "n_trades": self.n_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4) if self.win_rate is not None else None,
        }


class SymbolSelector:
    """
    Construit et filtre la liste des symboles a observer.

    Usage :
        selector = SymbolSelector()
        watchlist = selector.select(
            sort_by="market_cap",
            min_volatility=1.0,
            min_win_rate=0.4,
            limit=20,
        )
        symbols = [c.symbol for c in watchlist]
    """

    def __init__(
        self,
        obs_dir: Path | None = None,
        paper_trade_log: Path | None = None,
    ) -> None:
        self.obs_dir = obs_dir or OBS_DIR
        self.paper_trade_log = paper_trade_log or PAPER_TRADE_LOG

    # ------------------------------------------------------------------
    # Chargement des sources (lecture seule, tolerant aux fichiers absents)
    # ------------------------------------------------------------------

    def _latest_shortlist_file(self) -> Optional[Path]:
        if not self.obs_dir.exists():
            return None
        files = sorted(self.obs_dir.glob("radar_shortlist_*.json"))
        return files[-1] if files else None

    def load_radar(self) -> dict[str, dict]:
        """
        Retourne {symbol_normalise: {market_cap_proxy, volatility, score}}.
        Vide si aucun shortlist disponible.
        """
        path = self._latest_shortlist_file()
        if not path:
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        out: dict[str, dict] = {}
        for entry in data.get("shortlist", []):
            sym = normalize_symbol(str(entry.get("sym", "")))
            if not sym:
                continue
            out[sym] = {
                "market_cap_proxy": float(entry.get("qv_med", 0.0) or 0.0),
                "volatility": float(entry.get("range_pct", 0.0) or 0.0),
                "radar_score": float(entry.get("score", 0.0) or 0.0),
            }
        return out

    def load_win_loss(self, since_days: int = 30) -> dict[str, tuple[int, int, int]]:
        """
        Retourne {symbol_normalise: (n_trades, wins, losses)} depuis paper_trades.
        Ne compte que les evenements CLOSE avec is_win renseigne.
        """
        if not self.paper_trade_log.exists():
            return {}

        cutoff = None
        if since_days > 0:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=since_days)
            ).timestamp() * 1000.0

        stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        try:
            with open(self.paper_trade_log, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("event") != "CLOSE":
                        continue
                    is_win = rec.get("is_win")
                    if is_win is None:
                        continue
                    if cutoff is not None:
                        ts = rec.get("timestamp_ms") or rec.get("ts") or 0
                        if ts and float(ts) < cutoff:
                            continue
                    sym = normalize_symbol(str(rec.get("symbol", "")))
                    if not sym:
                        continue
                    s = stats[sym]
                    s[0] += 1
                    if is_win:
                        s[1] += 1
                    else:
                        s[2] += 1
        except OSError:
            return {}

        return {k: (v[0], v[1], v[2]) for k, v in stats.items()}

    def load_candidates(self, since_days: int = 30) -> list[SymbolCandidate]:
        """Fusionne radar + win/loss en une liste de candidats."""
        radar = self.load_radar()
        wl = self.load_win_loss(since_days)

        candidates: list[SymbolCandidate] = []
        for sym, r in radar.items():
            n, wins, losses = wl.get(sym, (0, 0, 0))
            candidates.append(
                SymbolCandidate(
                    symbol=sym,
                    market_cap_proxy=r["market_cap_proxy"],
                    volatility=r["volatility"],
                    radar_score=r["radar_score"],
                    n_trades=n,
                    wins=wins,
                    losses=losses,
                )
            )
        return candidates

    # ------------------------------------------------------------------
    # Selection / filtrage
    # ------------------------------------------------------------------

    def select(
        self,
        sort_by: str = "market_cap",
        min_volatility: Optional[float] = None,
        max_volatility: Optional[float] = None,
        min_win_rate: Optional[float] = None,
        min_trades: int = 0,
        min_market_cap: Optional[float] = None,
        limit: int = 20,
        since_days: int = 30,
        candidates: Optional[list[SymbolCandidate]] = None,
    ) -> list[SymbolCandidate]:
        """
        Filtre puis classe les candidats.

        sort_by : "market_cap" | "volatility" | "radar_score" | "win_rate"
        Les filtres None sont ignores. min_win_rate exclut les symboles
        sans trade ferme (win_rate == None) uniquement s'il est fourni.
        """
        cands = candidates if candidates is not None else self.load_candidates(
            since_days
        )

        filtered: list[SymbolCandidate] = []
        for c in cands:
            if min_market_cap is not None and c.market_cap_proxy < min_market_cap:
                continue
            if min_volatility is not None and c.volatility < min_volatility:
                continue
            if max_volatility is not None and c.volatility > max_volatility:
                continue
            if c.n_trades < min_trades:
                continue
            if min_win_rate is not None:
                wr = c.win_rate
                if wr is None or wr < min_win_rate:
                    continue
            filtered.append(c)

        key_map = {
            "market_cap": lambda c: c.market_cap_proxy,
            "volatility": lambda c: c.volatility,
            "radar_score": lambda c: c.radar_score,
            "win_rate": lambda c: (c.win_rate if c.win_rate is not None else -1.0),
        }
        key = key_map.get(sort_by, key_map["market_cap"])
        filtered.sort(key=key, reverse=True)

        return filtered[: max(0, limit)]

    def select_symbols(self, **kwargs) -> list[str]:
        """Raccourci : retourne seulement la liste des symboles selectionnes."""
        return [c.symbol for c in self.select(**kwargs)]
