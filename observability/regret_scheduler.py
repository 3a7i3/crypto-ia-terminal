"""
observability/regret_scheduler.py — Évaluation multi-horizon des signaux refusés.

Pour chaque signal actionable refusé, mesure si sa direction était favorable
ou défavorable à 7 horizons : 5m, 15m, 30m, 1h, 4h, 12h, 24h.

Cette mesure endpoint n'est PAS la preuve qu'un trade exécutable aurait été
rentable : frais, spread, slippage, funding, liquidité, latence et trajectoire
TP/SL ne sont pas modélisés.

Métriques par horizon :
  - return_pct     : rendement théorique si le trade avait été pris
  - direction_ok   : True si la direction du signal était correcte
  - favorable_endpoint_pct : partie favorable du rendement au point final
  - adverse_endpoint_pct   : partie défavorable du rendement au point final
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
from dataclasses import asdict, dataclass, field, fields
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
_SCHEMA_VERSION = 2
_DATASET_VERSION = "regret-v2"

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
    ts_eval: float  # timestamp UTC du calcul
    expected_eval_ts: float
    eval_delay_s: float
    price_at_signal: float
    price_at_eval: float
    price_source: str
    price_observed_ts: float
    price_age_s: float
    return_pct: float  # (price_eval - price_signal) / price_signal [signé]
    direction_ok: bool  # True si le signal était dans la bonne direction
    favorable_endpoint_pct: float
    adverse_endpoint_pct: float
    # Aliases historiques : même valeur endpoint, jamais une vraie excursion.
    mfe_pct: float
    mae_pct: float
    regret_score: float  # [0, 1]
    regret_type: str  # MISSED_WIN | GOOD_REFUSAL | NEUTRAL
    status: str = "EVALUATED"
    metric_semantics: str = "endpoint_only"
    classification_semantics: str = "directional_observation_not_executable_pnl"

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
    packet_id: str = ""
    trace_id: str = ""
    experiment_id: Optional[str] = None
    cycle: int = 0
    engine_version: str = "unknown"

    # Horizons restant à évaluer : {horizon_name: ts_deadline}
    pending_horizons: Dict[str, float] = field(default_factory=dict)
    # Horizons évalués
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # État explicite de chaque horizon.
    horizon_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # True si tous les horizons ont été évalués
    complete: bool = False

    def __post_init__(self) -> None:
        if not self.pending_horizons:
            for name, delay in _HORIZONS.items():
                self.pending_horizons[name] = self.ts_signal + delay
        for name, delay in _HORIZONS.items():
            expected = self.ts_signal + delay
            if name in self.results:
                status = "EVALUATED"
            elif name in self.pending_horizons:
                status = "PENDING"
            else:
                status = "DROPPED"
            self.horizon_states.setdefault(
                name,
                {
                    "status": status,
                    "expected_eval_ts": expected,
                    "status_reason": None,
                },
            )


@dataclass(frozen=True)
class PriceObservation:
    """Prix reçu par le scheduler; observed_ts est l'heure de réception locale."""

    price: float
    observed_ts: float
    source: str


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
    *,
    ts_eval: Optional[float] = None,
    expected_eval_ts: Optional[float] = None,
    price_source: str = "unknown",
    price_observed_ts: Optional[float] = None,
) -> HorizonResult:
    """Calcule un rendement directionnel au point final (pas une excursion)."""
    evaluated_at = time.time() if ts_eval is None else ts_eval
    expected_at = (
        candidate.ts_signal + _HORIZONS[horizon]
        if expected_eval_ts is None
        else expected_eval_ts
    )
    observed_at = evaluated_at if price_observed_ts is None else price_observed_ts
    p0 = candidate.price_at_signal
    p1 = price_now

    if p0 <= 0:
        return HorizonResult(
            horizon=horizon,
            ts_eval=evaluated_at,
            expected_eval_ts=expected_at,
            eval_delay_s=max(0.0, evaluated_at - expected_at),
            price_at_signal=p0,
            price_at_eval=p1,
            price_source=price_source,
            price_observed_ts=observed_at,
            price_age_s=max(0.0, evaluated_at - observed_at),
            return_pct=0.0,
            direction_ok=False,
            favorable_endpoint_pct=0.0,
            adverse_endpoint_pct=0.0,
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

    favorable_endpoint = max(0.0, potential_return)
    adverse_endpoint = min(0.0, potential_return)

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
        ts_eval=evaluated_at,
        expected_eval_ts=expected_at,
        eval_delay_s=max(0.0, evaluated_at - expected_at),
        price_at_signal=p0,
        price_at_eval=p1,
        price_source=price_source,
        price_observed_ts=observed_at,
        price_age_s=max(0.0, evaluated_at - observed_at),
        return_pct=round(potential_return, 6),
        direction_ok=direction_ok,
        favorable_endpoint_pct=round(favorable_endpoint, 6),
        adverse_endpoint_pct=round(adverse_endpoint, 6),
        mfe_pct=round(favorable_endpoint, 6),
        mae_pct=round(adverse_endpoint, 6),
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
        self._price_cache: Dict[str, PriceObservation] = {}
        self._lock = threading.Lock()
        self._price_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._eval_count = 0
        # S-03B-R1: observations à provenance invalide (packet_id vide ou
        # provenance_valid=False) — jamais promues en RegretCandidate,
        # comptées séparément pour S-03C. Miroir de
        # RejectionStore._skipped_provenance_count.
        self._skipped_invalid_provenance = 0
        # Spool : la file des candidats survit aux restarts (2026-07-21 :
        # file en mémoire seule → chaque restart coûtait jusqu'à ~24 h de
        # couverture regret). Rechargée ici, réécrite au plus 1×/poll.
        self._spool_path = self._dir / "pending_spool.json"
        self._persisted_evidence: Dict[str, Dict[str, Any]] = {}
        self._dirty = False
        self._load_persisted_evidence()
        self._load_spool()

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
        self._save_spool()

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

        # S-03B-R1: garde de provenance — miroir de RejectionStore.on_observation.
        # AVANT (blocker MASTER S-03B-R1 §2) : une observation à packet_id vide
        # ou provenance_valid=False pouvait quand même devenir un
        # RegretCandidate (packet_id="" silencieusement toléré), violant
        # "packet_id = identité canonique de jointure inter-systèmes".
        # APRÈS : sautée explicitement, jamais promue en candidat — vérifie
        # packet_id nu (pas seulement provenance_valid) pour rester robuste à
        # une construction manuelle/historique où provenance_valid
        # défaudrait à True. Ne modifie ni la math Regret, ni les horizons,
        # ni le seuil de score.
        if not getattr(obs, "packet_id", "") or not getattr(
            obs, "provenance_valid", True
        ):
            with self._lock:
                self._skipped_invalid_provenance += 1
            _log.warning(
                "[RegretScheduler] Skip — provenance invalide (packet_id=%r, "
                "observation_id=%s)",
                getattr(obs, "packet_id", ""),
                getattr(obs, "observation_id", ""),
            )
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
            packet_id=str(getattr(obs, "packet_id", "") or ""),
            trace_id=str(getattr(obs, "trace_id", "") or ""),
            experiment_id=getattr(obs, "experiment_id", None),
            cycle=int(getattr(obs, "cycle", 0) or 0),
            engine_version=str(getattr(obs, "engine_version", "unknown") or "unknown"),
        )

        with self._lock:
            if obs.observation_id in self._candidates:
                return
            self._reconcile_candidate(candidate)
            if candidate.complete:
                return
            self._candidates[obs.observation_id] = candidate
            self._dirty = True
            _log.debug(
                "[RegretScheduler] Candidat: %s %s score=%.0f blocker=%s",
                obs.symbol,
                obs.side,
                obs.score,
                obs.first_blocker,
            )

    # ── Prix courant ──────────────────────────────────────────────────────────

    def update_price_cache(
        self,
        prices: Dict[str, float],
        *,
        source: str = "advisor_loop_price_cache",
        observed_at: Optional[float] = None,
    ) -> None:
        """
        Met à jour le cache de prix depuis le scanner.

        Appelé depuis le thread advisor_loop — thread-safe via _price_lock.
        """
        received_at = time.time() if observed_at is None else observed_at
        with self._price_lock:
            for symbol, price in prices.items():
                if price and price > 0:
                    self._price_cache[symbol] = PriceObservation(
                        price=float(price), observed_ts=received_at, source=source
                    )

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
            price_obs = prices.get(candidate.symbol)

            # Évalue les horizons dont la deadline est passée
            newly_evaluated: list[str] = []
            dropped: list[str] = []
            for horizon, deadline in list(candidate.pending_horizons.items()):
                if now < deadline:
                    continue
                # Validité : un horizon trop en retard (restart, prix absent)
                # est ABANDONNÉ — l'évaluer avec un prix hors-fenêtre
                # fausserait la mesure.
                tolerance = max(600.0, 0.5 * _HORIZONS[horizon])
                if now - deadline > tolerance:
                    reason = (
                        "missing_price_beyond_tolerance"
                        if price_obs is None
                        else "evaluation_late_beyond_tolerance"
                    )
                    candidate.horizon_states[horizon] = {
                        "status": "DROPPED",
                        "expected_eval_ts": deadline,
                        "ts_eval": now,
                        "status_reason": reason,
                    }
                    if self._persist_horizon(candidate, horizon):
                        dropped.append(horizon)
                    continue
                if price_obs is None:
                    candidate.horizon_states[horizon] = {
                        "status": "MISSING_PRICE",
                        "expected_eval_ts": deadline,
                        "ts_eval": now,
                        "status_reason": "price_unavailable_at_poll",
                    }
                    self._dirty = True
                    continue
                result = _compute_horizon(
                    candidate,
                    horizon,
                    price_obs.price,
                    ts_eval=now,
                    expected_eval_ts=deadline,
                    price_source=price_obs.source,
                    price_observed_ts=price_obs.observed_ts,
                )
                candidate.results[horizon] = result.to_dict()
                candidate.horizon_states[horizon] = {
                    "status": "EVALUATED",
                    "expected_eval_ts": deadline,
                    "ts_eval": now,
                    "status_reason": None,
                }
                if self._persist_horizon(candidate, horizon):
                    newly_evaluated.append(horizon)
                else:
                    candidate.results.pop(horizon, None)
                    candidate.horizon_states[horizon] = {
                        "status": "PENDING",
                        "expected_eval_ts": deadline,
                        "status_reason": "persistence_failed_retry_required",
                    }

            for h in dropped:
                del candidate.pending_horizons[h]
                self._dirty = True
                _log.debug(
                    "[RegretScheduler] %s +%s abandonné (hors tolérance)",
                    candidate.symbol,
                    h,
                )

            for h in newly_evaluated:
                del candidate.pending_horizons[h]
                self._dirty = True
                self._eval_count += 1
                _log.debug(
                    "[RegretScheduler] %s %s +%s → %s (%.2f%%)",
                    candidate.symbol,
                    candidate.side,
                    h,
                    candidate.results[h]["regret_type"],
                    candidate.results[h]["return_pct"] * 100,
                )

            # Chaque horizon terminal est déjà durable. Le spool ne conserve
            # que le travail restant.
            if not candidate.pending_horizons:
                candidate.complete = True
                completed.append(candidate.observation_id)

        # Supprimer les candidats complets
        if completed:
            with self._lock:
                for obs_id in completed:
                    self._candidates.pop(obs_id, None)
                self._dirty = True

        if self._dirty:
            self._save_spool()

    # ── Spool (persistance de la file — survit aux restarts) ────────────────

    def _save_spool(self) -> None:
        """Écrit la file des candidats incomplets (atomique tmp+replace)."""
        try:
            with self._lock:
                payload = [
                    asdict(c) for c in self._candidates.values() if not c.complete
                ]
            tmp = self._spool_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._spool_path)
            # Ne pas effacer une modification arrivée pendant l'I/O.
            with self._lock:
                current = [
                    asdict(c) for c in self._candidates.values() if not c.complete
                ]
                self._dirty = current != payload
        except Exception as exc:
            self._dirty = True
            _log.warning("[RegretScheduler] spool non écrit: %s", exc)

    def _load_spool(self) -> None:
        """Recharge la file persistée au boot (corruption = ignorée, jamais fatale)."""
        if not self._spool_path.exists():
            return
        try:
            raw = json.loads(self._spool_path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(RegretCandidate)}
            restored = 0
            with self._lock:
                for d in raw:
                    if not isinstance(d, dict) or d.get("complete"):
                        continue
                    cand = RegretCandidate(**{k: v for k, v in d.items() if k in known})
                    self._reconcile_candidate(cand)
                    if cand.complete:
                        continue
                    self._candidates.setdefault(cand.observation_id, cand)
                    restored += 1
            if restored:
                _log.info(
                    "[RegretScheduler] %d candidat(s) restauré(s) du spool", restored
                )
        except Exception as exc:
            _log.warning("[RegretScheduler] spool illisible (ignoré): %s", exc)

    @staticmethod
    def _evidence_id(observation_id: str, horizon: str) -> str:
        return f"{observation_id}:{horizon}"

    def _load_persisted_evidence(self) -> None:
        """Indexe les preuves v2 pour garantir l'idempotence après restart."""
        for path in sorted(self._dir.glob("regret_horizons_*.jsonl")):
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            record = json.loads(line)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if record.get("record_type") == "HORIZON_EVIDENCE":
                            evidence_id = record.get("evidence_id")
                            if evidence_id:
                                self._persisted_evidence.setdefault(evidence_id, record)
                        else:
                            # Compatibilité avec les anciens agrégats regret-v2.
                            obs_id = record.get("observation_id")
                            for horizon, result in record.get("horizons", {}).items():
                                if obs_id:
                                    evidence_id = self._evidence_id(obs_id, horizon)
                                    self._persisted_evidence.setdefault(
                                        evidence_id,
                                        {
                                            "evidence_id": evidence_id,
                                            "observation_id": obs_id,
                                            "horizon": horizon,
                                            "horizon_status": "EVALUATED",
                                            "result": result,
                                        },
                                    )
            except OSError as exc:
                _log.warning(
                    "[RegretScheduler] index evidence impossible %s: %s", path, exc
                )

    def _reconcile_candidate(self, candidate: RegretCandidate) -> None:
        """Applique au spool les preuves déjà durables, sans réévaluation."""
        for horizon in list(candidate.pending_horizons):
            evidence = self._persisted_evidence.get(
                self._evidence_id(candidate.observation_id, horizon)
            )
            if evidence is None:
                continue
            status = evidence.get("horizon_status", "EVALUATED")
            if status == "EVALUATED" and isinstance(evidence.get("result"), dict):
                candidate.results[horizon] = evidence["result"]
            candidate.horizon_states[horizon] = {
                "status": status,
                "expected_eval_ts": evidence.get("expected_eval_ts"),
                "ts_eval": evidence.get("ts_eval"),
                "status_reason": evidence.get("status_reason"),
            }
            candidate.pending_horizons.pop(horizon, None)
        candidate.complete = not candidate.pending_horizons

    def _persist_horizon(self, candidate: RegretCandidate, horizon: str) -> bool:
        """Persiste une preuve terminale unique ``observation_id + horizon``."""
        evidence_id = self._evidence_id(candidate.observation_id, horizon)
        if evidence_id in self._persisted_evidence:
            return True
        state = candidate.horizon_states[horizon]
        result = candidate.results.get(horizon)
        ts_eval = state.get("ts_eval") or (result or {}).get("ts_eval") or time.time()
        record = {
            "schema_version": _SCHEMA_VERSION,
            "dataset_version": _DATASET_VERSION,
            "record_type": "HORIZON_EVIDENCE",
            "evidence_id": evidence_id,
            "observation_id": candidate.observation_id,
            "packet_id": candidate.packet_id,
            "trace_id": candidate.trace_id,
            "experiment_id": candidate.experiment_id,
            "cycle": candidate.cycle,
            "engine_version": candidate.engine_version,
            "ts_signal": candidate.ts_signal,
            "ts_iso_signal": datetime.fromtimestamp(
                candidate.ts_signal, tz=timezone.utc
            ).isoformat(),
            "symbol": candidate.symbol,
            "side": candidate.side,
            "score": candidate.score,
            "price_at_signal": candidate.price_at_signal,
            "regime": candidate.regime,
            "first_blocker": candidate.first_blocker,
            "all_blockers": candidate.all_blockers,
            "personality_name": candidate.personality_name,
            "horizon": horizon,
            "horizon_status": state["status"],
            "status_reason": state.get("status_reason"),
            "expected_eval_ts": state.get("expected_eval_ts"),
            "ts_eval": ts_eval,
            "result": result,
            # Uniquement pour faciliter la lecture par les consommateurs v2
            # antérieurs; la ligne reste une preuve mono-horizon.
            "horizons": {horizon: result} if result is not None else {},
        }
        try:
            today = datetime.fromtimestamp(ts_eval, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )
            path = self._dir / f"regret_horizons_{today}.jsonl"
            line = json.dumps(record, ensure_ascii=False, default=str)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._persisted_evidence[evidence_id] = record
            return True
        except Exception as exc:
            _log.error(
                "[RegretScheduler] Erreur persistance %s: %s",
                evidence_id,
                exc,
            )
            return False

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            pending = len(self._candidates)
            skipped_invalid_provenance = self._skipped_invalid_provenance
        return {
            "pending_candidates": pending,
            "horizons_evaluated": self._eval_count,
            "running": self._running,
            "skipped_invalid_provenance": skipped_invalid_provenance,
        }

    def layer_performance(self) -> Dict[str, Dict[str, Any]]:
        """
        Analyse les observations directionnelles par couche bloquante aujourd'hui.

        Les taux ont des dénominateurs explicites : horizons évalués ou décisions
        uniques. Ils ne sont jamais horizons/décisions.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._dir / f"regret_horizons_{today}.jsonl"
        if not path.exists():
            return {}

        layer_stats: Dict[str, Dict[str, Any]] = {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("record_type") == "HORIZON_EVIDENCE":
                        horizon_rows = (
                            [record]
                            if record.get("horizon_status") == "EVALUATED"
                            else []
                        )
                    else:
                        horizon_rows = [
                            {"result": result}
                            for result in record.get("horizons", {}).values()
                            if isinstance(result, dict)
                        ]
                    for blocker in record.get("all_blockers", []):
                        if blocker not in layer_stats:
                            layer_stats[blocker] = {
                                "missed_win_horizons": 0,
                                "good_refusal_horizons": 0,
                                "evaluated_horizons": 0,
                                "decision_ids": set(),
                                "missed_decision_ids": set(),
                            }
                        stats = layer_stats[blocker]
                        obs_id = record.get("observation_id")
                        if obs_id:
                            stats["decision_ids"].add(obs_id)
                        for row in horizon_rows:
                            regret_type = (row.get("result") or {}).get("regret_type")
                            stats["evaluated_horizons"] += 1
                            if regret_type == "MISSED_WIN":
                                stats["missed_win_horizons"] += 1
                                if obs_id:
                                    stats["missed_decision_ids"].add(obs_id)
                            elif regret_type == "GOOD_REFUSAL":
                                stats["good_refusal_horizons"] += 1
        except Exception as exc:
            _log.error("[RegretScheduler] layer_performance: %s", exc)

        result: Dict[str, Dict[str, Any]] = {}
        for layer, s in layer_stats.items():
            evaluated = s["evaluated_horizons"]
            decisions = len(s["decision_ids"])
            missed = s["missed_win_horizons"]
            missed_decisions = len(s["missed_decision_ids"])
            result[layer] = {
                "total_rejections": decisions,
                "evaluated_horizons": evaluated,
                "missed_win_horizons": missed,
                "good_refusal_horizons": s["good_refusal_horizons"],
                "missed_horizon_rate": (
                    round(missed / evaluated, 3) if evaluated else 0.0
                ),
                "decisions_with_missed_win": missed_decisions,
                "missed_decision_rate": (
                    round(missed_decisions / decisions, 3) if decisions else 0.0
                ),
            }
        return dict(sorted(result.items(), key=lambda x: -x[1]["missed_horizon_rate"]))
