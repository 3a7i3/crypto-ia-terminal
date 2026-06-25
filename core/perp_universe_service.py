"""
PerpUniverseService — service autonome de gestion de l'univers perp.

Thread daemon intégré à l'advisor_loop. S'active automatiquement au démarrage,
ne nécessite aucune configuration manuelle.

Cycle de vie :
  1. start()            → charge databases/perp_universe.json si existant
  2. Thread de fond     → refresh auto toutes les UNIVERSE_REFRESH_H heures
  3. drain_new_symbols() → retourne les paires fraîchement découvertes
                          (consommées par l'advisor pour créer les scanners)

Multi-quote :
  Scanne USDT, USDC, USDT1 par défaut → univers potentiel 200-400+ paires,
  top N retenus après scoring.

Variables d'env (toutes optionnelles — valeurs par défaut raisonnables) :
    UNIVERSE_ENABLED          true
    UNIVERSE_REFRESH_H        6      (heures entre rafraîchissements)
    UNIVERSE_SYNC_EVERY       12     (cycles advisor entre checks)
    UNIVERSE_TOP_N            100    (paires max retenues)
    UNIVERSE_MIN_VOL_USD      2000000
    UNIVERSE_MAX_SPREAD_PCT   0.50
    UNIVERSE_QUOTES           USDT,USDC
    UNIVERSE_EXCHANGE         mexc
    UNIVERSE_STORAGE          databases/perp_universe.json
    UNIVERSE_MIN_CHANGE_N     3      (min nouvelles paires pour notif log)
    SYMBOL_BLACKLIST          ""     (comma-sep extras, e.g. ASTEROID/USDT,STAR/USDT)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from typing import Callable, Optional

_log = logging.getLogger("core.perp_universe_service")

# Tokens confirmés rug pull / délistés ayant produit MAE≈-99.9% en paper trading.
# Liste étendue via SYMBOL_BLACKLIST env var.
_HARDCODED_BLACKLIST: frozenset[str] = frozenset(
    {
        "ASTEROID/USDT",
        "STAR/USDT",
        "UPC/USDT",
    }
)

_UNIVERSE_STORAGE_DEFAULT = os.path.join(
    os.path.dirname(__file__), "..", "databases", "perp_universe.json"
)


class PerpUniverseService:
    """
    Service autonome de découverte et mise à jour de l'univers perp.

    Intégration dans advisor_loop :
        service = PerpUniverseService()
        service.start()

        # au boot : utiliser comme symboles initiaux
        initial_symbols = service.initial_symbols()   # list[str] ou []

        # au début de chaque cycle :
        if cycle % service.sync_every == 0:
            new_syms = service.drain_new_symbols()     # créer scanners + append
    """

    def __init__(
        self,
        exchange_id: Optional[str] = None,
        on_update: Optional[Callable[[list[str]], None]] = None,
    ) -> None:
        self._exchange_id = (
            exchange_id or os.getenv("UNIVERSE_EXCHANGE", "mexc")
        ).lower()
        self._enabled = os.getenv("UNIVERSE_ENABLED", "true").lower() == "true"
        self._refresh_h = float(os.getenv("UNIVERSE_REFRESH_H", "6"))
        self._top_n = int(os.getenv("UNIVERSE_TOP_N", "100"))
        self._min_vol = float(os.getenv("UNIVERSE_MIN_VOL_USD", "2000000"))
        self._max_spread = float(os.getenv("UNIVERSE_MAX_SPREAD_PCT", "0.50"))
        self._quotes = [
            q.strip().upper()
            for q in os.getenv("UNIVERSE_QUOTES", "USDT,USDC").split(",")
            if q.strip()
        ]
        self._storage = os.path.normpath(
            os.getenv("UNIVERSE_STORAGE", _UNIVERSE_STORAGE_DEFAULT)
        )
        self.sync_every: int = int(os.getenv("UNIVERSE_SYNC_EVERY", "12"))
        self._min_change_n: int = int(os.getenv("UNIVERSE_MIN_CHANGE_N", "3"))

        self._on_update = on_update

        # Blacklist : tokens rug pull / délistés à exclure définitivement
        extra = [
            s.strip().upper()
            for s in os.getenv("SYMBOL_BLACKLIST", "").split(",")
            if s.strip()
        ]
        self._blacklist: frozenset[str] = _HARDCODED_BLACKLIST | frozenset(extra)
        if extra:
            _log.info("[Universe] Blacklist étendue: %s", ", ".join(sorted(extra)))

        # State protégé par lock
        self._lock = threading.Lock()
        self._current_symbols: list[str] = []  # univers actif
        self._pending_new: list[str] = []  # à injecter (non encore drainés)
        self._last_refresh: float = 0.0

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le service : charge le fichier existant puis lance le thread."""
        if not self._enabled:
            _log.info("[Universe] Service désactivé (UNIVERSE_ENABLED=false)")
            return

        # Chargement initial depuis fichier — immédiat, avant le thread
        self._load_from_disk()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="PerpUniverseService",
            daemon=True,
        )
        self._thread.start()
        _log.info(
            "[Universe] Service démarré — refresh toutes les %.0fh | top %d | quotes: %s",  # noqa: E501
            self._refresh_h,
            self._top_n,
            ", ".join(self._quotes),
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def initial_symbols(self) -> list[str]:
        """Retourne l'univers chargé au boot (depuis fichier ou vide)."""
        with self._lock:
            return list(self._current_symbols)

    def drain_new_symbols(self) -> list[str]:
        """
        Consomme et retourne les nouvelles paires depuis le dernier drain.
        L'advisor crée les scanners manquants et les ajoute à symbols[].
        """
        with self._lock:
            result = list(self._pending_new)
            self._pending_new.clear()
            return result

    def get_symbols(self) -> list[str]:
        """Snapshot de l'univers actif (sans consommer)."""
        with self._lock:
            return list(self._current_symbols)

    @property
    def last_refresh_ts(self) -> float:
        return self._last_refresh

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Thread interne ────────────────────────────────────────────────────────

    def _run(self) -> None:
        # Premier refresh immédiat si pas de fichier ou fichier trop vieux
        with self._lock:
            has_data = bool(self._current_symbols)

        if not has_data:
            _log.info("[Universe] Aucun fichier — premier scan immédiat")
            self._do_refresh()
        else:
            _log.info(
                "[Universe] Fichier chargé (%d symboles) — prochain refresh dans %.0fh",
                len(self._current_symbols),
                self._refresh_h,
            )

        refresh_interval_s = self._refresh_h * 3600.0

        while not self._stop_event.is_set():
            # Attente par tranches de 60s pour rester interruptible
            elapsed = time.time() - self._last_refresh
            remaining = max(0, refresh_interval_s - elapsed)
            if remaining <= 0:
                self._do_refresh()
            else:
                self._stop_event.wait(timeout=min(60.0, remaining))

    def _do_refresh(self) -> None:
        _log.info("[Universe] Rafraîchissement de l'univers perp...")
        t0 = time.perf_counter()
        try:
            from tools.perp_universe_builder import PerpUniverseBuilder

            builder = PerpUniverseBuilder(exchange_id=self._exchange_id)
            builder.MIN_VOL_USD = self._min_vol
            builder.MAX_SPREAD_PCT = self._max_spread
            builder._allowed_quotes = set(self._quotes)

            candidates = builder.discover(top_n=self._top_n)
            candidates = [
                c
                for c in candidates
                if c.symbol.upper() not in self._blacklist
                and f"{c.symbol.split('/')[0].upper()}/USDT" not in self._blacklist
            ]
            new_universe = [c.symbol for c in candidates]

            elapsed_ms = (time.perf_counter() - t0) * 1000
            _log.info(
                "[Universe] Scan OK — %d paires qualifiées en %.0fms",
                len(new_universe),
                elapsed_ms,
            )

            self._update_universe(new_universe)
            self._save_to_disk(candidates)
            self._last_refresh = time.time()

        except Exception as exc:
            _log.warning("[Universe] Refresh échoué: %s — univers inchangé", exc)

    def _update_universe(self, new_universe: list[str]) -> None:
        with self._lock:
            old_set = set(self._current_symbols)
            new_set = set(new_universe)

            # Nouvelles paires : toujours injectées, log si seuil atteint
            added = [s for s in new_universe if s not in old_set]
            if added:
                self._pending_new.extend(s for s in added if s not in self._pending_new)
                if len(added) >= self._min_change_n or not old_set:
                    _log.info(
                        "[Universe] +%d nouveaux symboles: %s",
                        len(added),
                        ", ".join(added[:10]) + ("..." if len(added) > 10 else ""),
                    )

            removed = old_set - new_set
            if removed:
                _log.info(
                    "[Universe] %d symboles sortis du top %d: %s",
                    len(removed),
                    self._top_n,
                    ", ".join(sorted(removed)[:10]),
                )

            self._current_symbols = list(new_universe)

        if self._on_update and new_universe:
            try:
                self._on_update(list(new_universe))
            except Exception as exc:
                _log.debug("[Universe] Callback on_update erreur: %s", exc)

    def _filter_blacklist(self, symbols: list[str]) -> list[str]:
        """Retire les tokens de la blacklist (match exact ou base sans quote)."""
        out = []
        removed = []
        for s in symbols:
            base = s.split("/")[0].upper()
            if s.upper() in self._blacklist or f"{base}/USDT" in self._blacklist:
                removed.append(s)
            else:
                out.append(s)
        if removed:
            _log.warning(
                "[Universe] Blacklist — %d token(s) exclus: %s",
                len(removed),
                ", ".join(removed),
            )
        return out

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        path = self._storage
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            syms = self._filter_blacklist(data.get("symbols", []))
            if syms:
                with self._lock:
                    self._current_symbols = list(syms)
                    # Toutes les paires du fichier sont "nouvelles" au boot
                    self._pending_new = list(syms)
                age_h = (time.time() - data.get("_saved_ts", 0)) / 3600
                _log.info(
                    "[Universe] Chargé depuis %s — %d symboles (âge %.1fh)",
                    path,
                    len(syms),
                    age_h,
                )
                self._last_refresh = data.get("_saved_ts", 0)
        except Exception as exc:
            _log.warning("[Universe] Lecture %s échouée: %s", path, exc)

    def _save_to_disk(self, candidates) -> None:
        path = self._storage
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        data = {
            "version": "2.0",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "_saved_ts": time.time(),
            "exchange": self._exchange_id,
            "refresh_h": self._refresh_h,
            "quotes": self._quotes,
            "top_n": self._top_n,
            "min_vol_usd": self._min_vol,
            "max_spread_pct": self._max_spread,
            "total": len(candidates),
            "symbols": [c.symbol for c in candidates],
            "candidates": [
                {
                    "rank": i + 1,
                    "symbol": c.symbol,
                    "score": c.score,
                    "vol_24h_usd": round(c.vol_24h_usd, 0),
                    "spread_pct": c.spread_pct,
                    "last_price": c.last_price,
                    **c.details,
                }
                for i, c in enumerate(candidates)
            ],
        }
        # Écriture atomique via fichier temporaire (évite corruption si crash)
        try:
            dir_ = os.path.dirname(os.path.abspath(path))
            with tempfile.NamedTemporaryFile(
                "w", dir=dir_, suffix=".tmp", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(data, tmp, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, path)
            _log.debug("[Universe] Sauvegardé → %s", path)
        except Exception as exc:
            _log.warning("[Universe] Sauvegarde échouée: %s", exc)
