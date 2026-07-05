"""
observability/regret_scheduler.py — Évaluation multi-horizon des signaux refusés.

Pour chaque signal actionable refusé, calcule a posteriori si le trade aurait
été profitable sur 7 horizons : 5m, 15m, 30m, 1h, 4h, 12h, 24h.

Métriques par horizon :
  - return_pct     : rendement théorique si le trade avait été pris
  - direction_ok   : True si la direction du signal était correcte
  - mfe_pct        : Maximum Favorable Excursion (meilleur moment pour sortir)
  - mae_pct        : Maximum Adverse Excursion (pire moment)
  - regret_score   : [0, 1] — coût du refus
  - regret_type    : MISSED_WIN | GOOD_REFUSAL | NEUTRAL

Architecture :
  - Thread daemon background — zéro impact sur la latence du cycle de trading
  - Prix injectés via `update_price_cache()` depuis le scanner (dict thread-safe)
  - Évaluation lazy : on ne calcule un horizon que quand le prix est disponible
  - Persistance : databases/regret/regret_horizons_YYYY-MM-DD.jsonl

Usage (listener pour DecisionEventBus) :
    from observability.regret_scheduler import RegretScheduler
    scheduler = RegretScheduler()
    scheduler.start()
    bus.subscribe(scheduler.on_observation)

    # Dans la boucle scanner (pour fournir les prix futurs) :
    scheduler.update_price_cache({"BTC/USDT": 67500.0, "ETH/USDT": 3250.0})
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.json_logger import get_logger

_log = get_logger("observability.regret_scheduler")

_DEFAULT_DIR = Path(os.getenv("REGRET_HORIZONS_DIR", "databases/regret"))
_MIN_SCORE = float(os.getenv("REGRET_MIN_SCORE", "60"))
_MIN_MOVE_PCT = float(
    os.getenv("REGRET_MIN_MOVE_PCT", "0.008")
)  # 0.8% mouvement minimum

# Horizons d'évaluation en secondes
_HORIZONS: Dict[str, float] = {
    "5m": 300.0,
    "15m": 900.0,
    "30m": 1800.0,
    "1h": 3600.0,
    "4h": 14400.0,
    "12h": 43200.0,
    "24h": 86400.0,
}


# ── Structures de données ─────────────────────────────────────────────────────


@dataclass
class HorizonResult:
    """Résultat d'évaluation pour un horizon temporel."""

    horizon: str  # "5m" | "15m" | ...
    ts_eval: float  # timestamp UTC de l'évaluation
    price_at_signal: float
    price_at_eval: float
    return_pct: float  # (price_eval - price_signal) / price_signal [signé]
    direction_ok: bool  # True si le signal était dans la bonne direction
    mfe_pct: float  # Maximum Favorable Excursion (approx = max(0, return))
    mae_pct: float  # Maximum Adverse Excursion (approx = min(0, return))
    regret_score: float  # [0, 1]
    regret_type: str  # MISSED_WIN | GOOD_REFUSAL | NEUTRAL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegretCandidate:
    """Signal refusé en attente d'évaluation multi-horizon."""

    observation_id: str
    symbol: str
    side: str  # BUY | SELL
    score: float
    price_at_signal: float
    ts_signal: float
    regime: str
    first_blocker: Optional[str]
    all_blockers: List[str]
    personality_name: str

    # Horizons restant à évaluer : {horizon_name: ts_deadline}
    pending_horizons: Dict[str, float] = field(default_factory=dict)
    # Horizons évalués
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # True si tous les horizons ont été évalués
    complete: bool = False

    def __post_init__(self) -> None:
        if not self.pending_horizons:
            for name, delay in _HORIZONS.items():
                self.pending_horizons[name] = self.ts_signal + delay


@dataclass
class RegretReport:
    """Rapport complet multi-horizon pour un signal refusé."""

    observation_id: str
    ts_signal: float
    ts_iso_signal: str
    symbol: str
    side: str
    score: float
    price_at_signal: float
    regime: str
    first_blocker: Optional[str]
    all_blockers: List[str]
    personality_name: str
    horizons: Dict[str, Dict[str, Any]]

    # Métriques agrégées (sur les horizons évalués)
    missed_win_count: int = 0  # Horizons MISSED_WIN
    good_refusal_count: int = 0  # Horizons GOOD_REFUSAL
    neutral_count: int = 0
    max_regret_score: float = 0.0
    best_horizon: Optional[str] = None  # Horizon avec meilleur return
    worst_horizon: Optional[str] = None  # Horizon avec pire return

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "ts_signal": self.ts_signal,
            "ts_iso_signal": self.ts_iso_signal,
            "symbol": self.symbol,
            "side": self.side,
            "score": self.score,
            "price_at_signal": self.price_at_signal,
            "regime": self.regime,
            "first_blocker": self.first_blocker,
            "all_blockers": self.all_blockers,
            "personality_name": self.personality_name,
            "horizons": self.horizons,
            "missed_win_count": self.missed_win_count,
            "good_refusal_count": self.good_refusal_count,
            "neutral_count": self.neutral_count,
            "max_regret_score": self.max_regret_score,
            "best_horizon": self.best_horizon,
            "worst_horizon": self.worst_horizon,
        }


# ── Calcul des métriques ──────────────────────────────────────────────────────


def _compute_horizon(
    candidate: RegretCandidate,
    horizon: str,
    price_now: float,
) -> HorizonResult:
    """Calcule les métriques de regret pour un horizon donné."""
    p0 = candidate.price_at_signal
    p1 = price_now

    if p0 <= 0:
        return HorizonResult(
            horizon=horizon,
            ts_eval=time.time(),
            price_at_signal=p0,
            price_at_eval=p1,
            return_pct=0.0,
            direction_ok=False,
            mfe_pct=0.0,
            mae_pct=0.0,
            regret_score=0.0,
            regret_type="NEUTRAL",
        )

    raw_return = (p1 - p0) / p0

    if candidate.side in ("BUY", "LONG"):
        direction_ok = raw_return > 0
        potential_return = raw_return
    else:  # SELL / SHORT
        direction_ok = raw_return < 0
        potential_return = -raw_return

    abs_return = abs(potential_return)

    # MFE / MAE (approximés sans historique intra-horizon)
    mfe = max(0.0, potential_return)
    mae = min(0.0, potential_return)

    # Regret score
    if abs_return < _MIN_MOVE_PCT:
        regret_type = "NEUTRAL"
        regret_score = 0.0
    elif direction_ok:
        regret_type = "MISSED_WIN"
        regret_score = min(1.0, abs_return / 0.05)  # 5% = regret max
    else:
        regret_type = "GOOD_REFUSAL"
        regret_score = 0.0

    return HorizonResult(
        horizon=horizon,
        ts_eval=time.time(),
        price_at_signal=p0,
        price_at_eval=p1,
        return_pct=round(potential_return, 6),
        direction_ok=direction_ok,
        mfe_pct=round(mfe, 6),
        mae_pct=round(mae, 6),
        regret_score=round(regret_score, 4),
        regret_type=regret_type,
    )


# ── RegretScheduler ───────────────────────────────────────────────────────────


class RegretScheduler:
    """
    Scheduler background d'évaluation multi-horizon des signaux refusés.

    Thread daemon — ne bloque jamais le cycle de trading.
    Se réveille toutes les 60 secondes pour évaluer les horizons échus.
    """

    def __init__(
        self, store_dir: Path = _DEFAULT_DIR, poll_interval_s: float = 60.0
    ) -> None:
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._poll_interval = poll_interval_s
        self._candidates: Dict[str, RegretCandidate] = {}  # obs_id → candidate
        self._price_cache: Dict[str, float] = {}  # symbol → prix courant
        self._lock = threading.Lock()
        self._price_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._eval_count = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le thread daemon d'évaluation."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="regret_scheduler",
        )
        self._thread.start()
        _log.info("[RegretScheduler] Démarré (poll=%ds)", int(self._poll_interval))

    def stop(self) -> None:
        """Arrêt propre."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    # ── Listener DecisionEventBus ─────────────────────────────────────────────

    def on_observation(self, obs: Any) -> None:
        """
        Listener pour DecisionEventBus.

        Enregistre les signaux actionnables refusés avec score suffisant.
        """
        if not obs.actionable or obs.trade_allowed:
            return
        if obs.side not in ("BUY", "SELL", "LONG", "SHORT"):
            return
        if obs.score < _MIN_SCORE:
            return

        candidate = RegretCandidate(
            observation_id=obs.observation_id,
            symbol=obs.symbol,
            side=obs.side,
            score=obs.score,
            price_at_signal=obs.price,
            ts_signal=obs.ts,
            regime=obs.regime,
            first_blocker=obs.first_blocker,
            all_blockers=list(obs.all_blockers),
            personality_name=obs.personality_name,
        )

        with self._lock:
            self._candidates[obs.observation_id] = candidate
            _log.debug(
                "[RegretScheduler] Candidat: %s %s score=%.0f blocker=%s",
                obs.symbol,
                obs.side,
                obs.score,
                obs.first_blocker,
            )

    # ── Prix courant ──────────────────────────────────────────────────────────

    def update_price_cache(self, prices: Dict[str, float]) -> None:
        """
        Met à jour le cache de prix depuis le scanner.

        Appelé depuis le thread advisor_loop — thread-safe via _price_lock.
        """
        with self._price_lock:
            self._price_cache.update(prices)

    # ── Boucle d'évaluation ───────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                _log.error("[RegretScheduler] Erreur tick: %s", exc)
            time.sleep(self._poll_interval)

    def _tick(self) -> None:
        """Évalue les horizons échus pour tous les candidats."""
        now = time.time()
        completed: list[str] = []

        with self._lock:
            candidates = list(self._candidates.values())

        with self._price_lock:
            prices = dict(self._price_cache)

        for candidate in candidates:
            price_now = prices.get(candidate.symbol, 0.0)
            if price_now <= 0:
                continue

            # Évalue les horizons dont la deadline est passée
            newly_evaluated: list[str] = []
            for horizon, deadline in list(candidate.pending_horizons.items()):
                if now >= deadline:
                    result = _compute_horizon(candidate, horizon, price_now)
                    candidate.results[horizon] = result.to_dict()
                    newly_evaluated.append(horizon)

            for h in newly_evaluated:
                del candidate.pending_horizons[h]
                self._eval_count += 1
                _log.debug(
                    "[RegretScheduler] %s %s +%s → %s (%.2f%%)",
                    candidate.symbol,
                    candidate.side,
                    h,
                    candidate.results[h]["regret_type"],
                    candidate.results[h]["return_pct"] * 100,
                )

            # Si tous les horizons sont évalués → persister et marquer complet
            if not candidate.pending_horizons and candidate.results:
                candidate.complete = True
                self._persist(candidate)
                completed.append(candidate.observation_id)

        # Supprimer les candidats complets
        if completed:
            with self._lock:
                for obs_id in completed:
                    self._candidates.pop(obs_id, None)

    def _persist(self, candidate: RegretCandidate) -> None:
        """Persiste le rapport complet d'un candidat évalué."""
        # Calcul métriques agrégées
        missed = sum(
            1
            for r in candidate.results.values()
            if r.get("regret_type") == "MISSED_WIN"
        )
        good = sum(
            1
            for r in candidate.results.values()
            if r.get("regret_type") == "GOOD_REFUSAL"
        )
        neutral = sum(
            1 for r in candidate.results.values() if r.get("regret_type") == "NEUTRAL"
        )
        max_regret = max(
            (r.get("regret_score", 0.0) for r in candidate.results.values()),
            default=0.0,
        )

        # Meilleur / pire horizon
        returns = {h: r.get("return_pct", 0.0) for h, r in candidate.results.items()}
        best_h = max(returns, key=returns.get) if returns else None  # type: ignore
        worst_h = min(returns, key=returns.get) if returns else None  # type: ignore

        report = RegretReport(
            observation_id=candidate.observation_id,
            ts_signal=candidate.ts_signal,
            ts_iso_signal=datetime.fromtimestamp(
                candidate.ts_signal, tz=timezone.utc
            ).isoformat(),
            symbol=candidate.symbol,
            side=candidate.side,
            score=candidate.score,
            price_at_signal=candidate.price_at_signal,
            regime=candidate.regime,
            first_blocker=candidate.first_blocker,
            all_blockers=candidate.all_blockers,
            personality_name=candidate.personality_name,
            horizons=dict(candidate.results),
            missed_win_count=missed,
            good_refusal_count=good,
            neutral_count=neutral,
            max_regret_score=round(max_regret, 4),
            best_horizon=best_h,
            worst_horizon=worst_h,
        )

        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            path = self._dir / f"regret_horizons_{today}.jsonl"
            line = json.dumps(report.to_dict(), ensure_ascii=False, default=str)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

            log_parts = [f"MISSED_WIN={missed}", f"GOOD={good}", f"NEUTRAL={neutral}"]
            if missed > 0:
                _log.info(
                    "[RegretScheduler] RAPPORT %s %s %s [max_regret=%.2f blocker=%s]",
                    candidate.symbol,
                    candidate.side,
                    " ".join(log_parts),
                    max_regret,
                    candidate.first_blocker,
                )
        except Exception as exc:
            _log.error(
                "[RegretScheduler] Erreur persistance %s: %s",
                candidate.observation_id,
                exc,
            )

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            pending = len(self._candidates)
        return {
            "pending_candidates": pending,
            "horizons_evaluated": self._eval_count,
            "running": self._running,
        }

    def layer_performance(self) -> Dict[str, Dict[str, Any]]:
        """
        Analyse les performances par couche bloquante sur tous les fichiers du jour.

        Retourne pour chaque couche : {missed_wins, good_refusals, total, missed_rate}
        Utilisable par la Phase 4 (ACE) pour identifier les layers trop conservateurs.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._dir / f"regret_horizons_{today}.jsonl"
        if not path.exists():
            return {}

        layer_stats: Dict[str, Dict[str, int]] = {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    # Compte par blocker
                    for blocker in record.get("all_blockers", []):
                        if blocker not in layer_stats:
                            layer_stats[blocker] = {
                                "missed_wins": 0,
                                "good_refusals": 0,
                                "total": 0,
                            }
                        layer_stats[blocker]["total"] += 1
                        layer_stats[blocker]["missed_wins"] += record.get(
                            "missed_win_count", 0
                        )
                        layer_stats[blocker]["good_refusals"] += record.get(
                            "good_refusal_count", 0
                        )
        except Exception as exc:
            _log.error("[RegretScheduler] layer_performance: %s", exc)

        result: Dict[str, Dict[str, Any]] = {}
        for layer, s in layer_stats.items():
            total = s["total"]
            missed = s["missed_wins"]
            result[layer] = {
                "total_rejections": total,
                "missed_wins": missed,
                "good_refusals": s["good_refusals"],
                "missed_rate": round(missed / total, 3) if total else 0.0,
            }
        return dict(sorted(result.items(), key=lambda x: -x[1]["missed_rate"]))
