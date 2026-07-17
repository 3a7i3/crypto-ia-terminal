"""
core/topk_scheduler.py — Ordonnanceur rotation top-K (paliers 500-1000, ADR-0017).

Étage B du design docs/design/scanner-500-paires.md : au lieu d'analyser
TOUT l'univers à chaque cycle (~1,10 s/paire mesuré → 18 min à 1000 paires),
le moteur analyse K paires par cycle, choisies par priorité :

  1. paires avec position ouverte (toujours — suivi de position d'abord) ;
  2. paires « chaudes » du pouls (plus forts mouvements 24h, ADR-0016) ;
  3. rotation round-robin du reste — chaque paire de l'univers est
     revisitée au plus tous les ceil(n/k_libre) cycles (revisite BORNÉE).

Ce module change l'ORDONNANCEMENT, jamais l'analyse : chaque paire
sélectionnée passe par le pipeline de décision complet (gates, seuils,
portfolio — inchangés). Le pouls DÉSIGNE des candidats à analyser, il
n'autorise aucun trade (ADR-0007).

Activation : SCANNER_TOPK_ENABLED=true + SCANNER_TOPK_K (défaut 70).
Défaut : DÉSACTIVÉ — comportement historique strictement identique.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_LATEST_TICK_PATH = Path("databases/observation/latest_tick.json")


def hot_symbols_from_latest(
    universe: list[str], n: int, path: Path = _LATEST_TICK_PATH
) -> list[str]:
    """Top n de l'univers par |variation 24h| du dernier tick du pouls.

    Fail-safe : fichier absent/corrompu → liste vide (le round-robin couvre).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pairs = data.get("pairs", {})
    except Exception:
        return []
    uni = set(universe)
    scored = [
        (abs(float(info.get("chg", 0) or 0)), sym)
        for sym, info in pairs.items()
        if sym in uni
    ]
    scored.sort(reverse=True)
    return [sym for _chg, sym in scored[:n]]


class TopKScheduler:
    """Sélectionne les K paires du cycle. État : un curseur round-robin."""

    def __init__(self, universe: list[str], k: int) -> None:
        self._universe = list(universe)
        self._uni_set = set(universe)
        self.k = max(1, int(k))
        self._cursor = 0

    def select(
        self,
        open_symbols: set[str] | None = None,
        hot_symbols: list[str] | None = None,
    ) -> list[str]:
        """Priorité positions > chaudes > round-robin. Toujours ⊆ univers
        (les scanners du moteur n'existent que pour l'univers du boot)."""
        k = min(self.k, len(self._universe))
        chosen: list[str] = []
        seen: set[str] = set()

        def _add(sym: str) -> None:
            if sym in self._uni_set and sym not in seen:
                seen.add(sym)
                chosen.append(sym)

        for sym in sorted(open_symbols or ()):
            _add(sym)
        for sym in hot_symbols or ():
            if len(chosen) >= k:
                break
            _add(sym)

        # Round-robin borné : on avance le curseur du nombre de cases
        # VISITÉES (déjà choisies comprises) — équité de revisite garantie.
        n = len(self._universe)
        visited = 0
        while len(chosen) < k and visited < n:
            _add(self._universe[(self._cursor + visited) % n])
            visited += 1
        self._cursor = (self._cursor + visited) % n if n else 0
        return chosen


def scheduler_from_env(universe: list[str]) -> TopKScheduler | None:
    """Instancie l'ordonnanceur si SCANNER_TOPK_ENABLED=true, sinon None."""
    if os.getenv("SCANNER_TOPK_ENABLED", "false").lower() != "true":
        return None
    k = int(os.getenv("SCANNER_TOPK_K", "70"))
    return TopKScheduler(universe=universe, k=k)
