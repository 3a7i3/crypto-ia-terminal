"""
observability/rejection_store.py — Persistance atomique des signaux refusés.

Chaque signal actionable refusé est enregistré en JSONL avec contexte complet.
Utilisable par la Phase 4 (ACE) pour analyser le coût des refus par couche.

Fichiers : databases/rejections/rejections_YYYY-MM-DD.jsonl
Rotation  : quotidienne automatique (UTC)
Écriture  : flush explicite + os.fsync() — zéro perte silencieuse
Validation: champs obligatoires vérifiés avant écriture

Usage (listener pour DecisionEventBus) :
    from observability.rejection_store import RejectionStore
    store = RejectionStore()
    bus.subscribe(store.on_observation)
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.json_logger import get_logger

_log = get_logger("observability.rejection_store")

_DEFAULT_DIR = Path(os.getenv("REJECTION_STORE_DIR", "databases/rejections"))
_SCHEMA_VERSION = 1
_REQUIRED_FIELDS = {"observation_id", "symbol", "side", "score", "price", "ts"}


# ── Schéma du record de rejet ─────────────────────────────────────────────────


@dataclass
class RejectionRecord:
    """
    Enregistrement complet d'un signal refusé.

    Conçu pour être exploitable directement par la Phase 4 (ACE) :
    - tous les facteurs de blocage avec raison textuelle
    - décomposition du score
    - contexte marché (features lean)
    - référence vers le DecisionPacket (packet_id)
    """

    schema_version: int = _SCHEMA_VERSION

    # ── Identité ──────────────────────────────────────────────────────────────
    observation_id: str = ""  # "20260629-ETHUSDT-A3F9C2"
    packet_id: str = ""  # UUID du DecisionPacket
    ts: float = 0.0  # Unix timestamp UTC
    ts_iso: str = ""  # ISO-8601 UTC
    cycle: int = 0
    engine_version: str = "unknown"

    # ── Signal ────────────────────────────────────────────────────────────────
    symbol: str = ""
    side: str = ""  # "BUY" | "SELL"
    score: float = 0.0
    score_raw: float = 0.0
    price: float = 0.0
    regime: str = ""
    confirmed: bool = False
    strength: float = 0.0

    # ── Score décomposé ───────────────────────────────────────────────────────
    score_mtf: float = 0.0
    score_regime: float = 0.0
    score_data_quality: float = 0.0
    score_memory: float = 0.0

    # ── Conviction ────────────────────────────────────────────────────────────
    conviction_level: Optional[str] = None
    conviction_score: Optional[float] = None
    conviction_size_factor: Optional[float] = None

    # ── Blockers ──────────────────────────────────────────────────────────────
    first_blocker: Optional[str] = None
    all_blockers: List[str] = field(default_factory=list)
    blocker_count: int = 0
    human_verdict: str = ""

    # ── Détail par couche (raisons textuelles) ────────────────────────────────
    gate_failed: List[str] = field(default_factory=list)
    notrade_reason: Optional[str] = None
    notrade_rejection_score: float = 0.0
    portfolio_reason: Optional[str] = None
    portfolio_size_factor: Optional[float] = None
    mistake_reason: Optional[str] = None
    override_level: Optional[str] = None
    override_reason: Optional[str] = None
    radar_level: Optional[str] = None
    radar_threat_count: int = 0
    meta_reason: str = ""
    awareness_level: Optional[str] = None
    arbitration_decision: Optional[str] = None

    # ── Sizing ────────────────────────────────────────────────────────────────
    base_size_usd: float = 0.0
    cae_kelly: Optional[float] = None
    cae_ev: Optional[float] = None

    # ── Personnalité ──────────────────────────────────────────────────────────
    personality_name: str = ""

    # ── Features marché (subset lean) ────────────────────────────────────────
    features: Dict[str, float] = field(default_factory=dict)

    # ── Regret (renseigné a posteriori par RegretScheduler) ──────────────────
    regret_evaluated: bool = False
    regret_type: Optional[str] = None  # "MISSED_WIN" | "GOOD_REFUSAL" | "NEUTRAL"
    regret_horizons: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _from_observation(obs: Any) -> RejectionRecord:
    """Construit un RejectionRecord depuis une DecisionObservation."""
    # Features lean : on garde uniquement les plus utiles pour l'analyse
    _LEAN_FEATURES = {
        "rsi",
        "atr_ratio",
        "atr_pct",
        "volume_ratio",
        "ema_spread",
        "macd",
        "bb_width",
        "momentum",
        "volatility",
    }
    features_lean = {k: v for k, v in obs.features.items() if k in _LEAN_FEATURES}

    return RejectionRecord(
        schema_version=_SCHEMA_VERSION,
        observation_id=obs.observation_id,
        packet_id=obs.packet_id,
        ts=obs.ts,
        ts_iso=obs.ts_iso,
        cycle=obs.cycle,
        engine_version=obs.engine_version,
        symbol=obs.symbol,
        side=obs.side,
        score=obs.score,
        score_raw=obs.score_raw,
        price=obs.price,
        regime=obs.regime,
        confirmed=obs.confirmed,
        strength=obs.strength,
        score_mtf=obs.score_mtf,
        score_regime=obs.score_regime,
        score_data_quality=obs.score_data_quality,
        score_memory=obs.score_memory,
        conviction_level=obs.conviction_level,
        conviction_score=obs.conviction_score,
        conviction_size_factor=obs.conviction_size_factor,
        first_blocker=obs.first_blocker,
        all_blockers=list(obs.all_blockers),
        blocker_count=len(obs.all_blockers),
        human_verdict=obs.human_verdict,
        gate_failed=list(obs.gate_failed),
        notrade_reason=obs.notrade_reason,
        notrade_rejection_score=obs.notrade_rejection_score,
        portfolio_reason=obs.portfolio_reason,
        portfolio_size_factor=obs.portfolio_size_factor,
        mistake_reason=obs.mistake_reason,
        override_level=obs.override_level,
        override_reason=obs.override_reason,
        radar_level=obs.radar_level,
        radar_threat_count=obs.radar_threat_count,
        meta_reason=obs.meta_reason,
        awareness_level=obs.awareness_level,
        arbitration_decision=obs.arbitration_decision,
        base_size_usd=obs.base_size_usd,
        cae_kelly=obs.cae_kelly,
        cae_ev=obs.cae_ev,
        personality_name=obs.personality_name,
        features=features_lean,
    )


def _validate(record: RejectionRecord) -> bool:
    """Valide les champs obligatoires. Retourne False si le record est invalide."""
    d = record.to_dict()
    missing = _REQUIRED_FIELDS - set(d.keys())
    if missing:
        _log.error("[RejectionStore] Champs manquants: %s", missing)
        return False
    if not record.symbol or record.price <= 0:
        _log.error(
            "[RejectionStore] Symbol vide ou prix nul: %s %s",
            record.symbol,
            record.price,
        )
        return False
    return True


# ── RejectionStore ────────────────────────────────────────────────────────────


class RejectionStore:
    """
    Persistance JSONL atomique des signaux refusés.

    Thread-safe via lock interne.
    Écriture robuste avec flush + fsync.
    Rotation quotidienne automatique (UTC).
    """

    def __init__(self, store_dir: Path = _DEFAULT_DIR) -> None:
        self._dir = Path(store_dir)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.error(
                "[RejectionStore] Impossible de créer le répertoire %s: %s",
                self._dir,
                exc,
            )
        self._lock = threading.Lock()
        self._current_date: str = ""
        self._path: Optional[Path] = None
        self._write_count = 0
        self._error_count = 0

    def _get_path(self) -> Path:
        """Chemin du fichier courant, rotation si changement de date UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._current_date:
            self._current_date = today
            self._path = self._dir / f"rejections_{today}.jsonl"
            _log.info("[RejectionStore] Fichier courant: %s", self._path)
        return self._path  # type: ignore[return-value]

    def persist(self, record: RejectionRecord) -> bool:
        """
        Écrit un RejectionRecord en JSONL atomique.

        Retourne True si succès, False si échec (jamais d'exception propagée).
        Utilisé pour l'écriture directe (sans event bus).
        """
        if not _validate(record):
            return False

        with self._lock:
            try:
                path = self._get_path()
                line = json.dumps(record.to_dict(), ensure_ascii=False, default=str)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                self._write_count += 1
                _log.debug(
                    "[RejectionStore] Persisté: %s %s blocker=%s",
                    record.symbol,
                    record.side,
                    record.first_blocker,
                )
                return True
            except OSError as exc:
                self._error_count += 1
                _log.error("[RejectionStore] Erreur écriture: %s", exc)
                return False
            except Exception as exc:
                self._error_count += 1
                _log.error("[RejectionStore] Erreur inattendue: %s", exc)
                return False

    def on_observation(self, obs: Any) -> None:
        """
        Listener pour DecisionEventBus.

        Persiste uniquement les observations de signaux actionnables refusés.
        Les HOLD et les non-actionnables sont ignorés.
        """
        # Filtre : uniquement les refus de signaux actionnables
        if not obs.actionable:
            return
        if obs.trade_allowed:
            return
        if obs.side not in ("BUY", "SELL", "LONG", "SHORT"):
            return

        record = _from_observation(obs)
        self.persist(record)

    def stats(self) -> Dict[str, int]:
        return {
            "writes": self._write_count,
            "errors": self._error_count,
        }

    def count_today(self) -> int:
        """Nombre de rejets persistés aujourd'hui (comptage lignes fichier)."""
        try:
            path = self._get_path()
            if not path.exists():
                return 0
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
