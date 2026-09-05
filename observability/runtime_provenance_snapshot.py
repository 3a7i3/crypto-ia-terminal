"""
observability/runtime_provenance_snapshot.py — S-03D: exposition runtime.

S-03C a établi ZERO defaut de provenance runtime observe, mais a conclu
S03_RUNTIME_INCONCLUSIVE : plusieurs compteurs scientifiques deja instrumentes
en memoire (DecisionObservation, DecisionEventBus, RejectionStore,
RegretScheduler, DIPObserver, BlackBox) n'etaient exposes nulle part de facon
sure, deterministe et lisible par un auditeur (humain ou IA) sans toucher au
secret de chiffrement de la BlackBox.

Ce module ne cree AUCUN nouveau compteur scientifique et n'instancie AUCUN
consommateur (RejectionStore(), RegretScheduler(), DecisionEventBus(),
DIPObserver(), BlackBox()) autre que les instances LIVE deja utilisees par le
processus advisor_loop en cours. Instancier un objet frais pour lire .stats()
produirait des zeros scientifiquement faux (compteurs d'un objet qui n'a rien
observe) — voir mission S-03D section 2.

Role de ce module : composer un instantane sanitize (JSON, borne, sans
secret) a partir des objets vivants passes en parametre, et l'ecrire de facon
atomique (tmp + os.replace, meme pattern que RegretScheduler._save_spool()).

Purement passif — ADR-0007 : ce module ne lit jamais de decision, n'ecrit
jamais dans le moteur de decision, n'influence jamais trade_allowed. Un echec
de serialisation/ecriture est avale (log + compteur interne), jamais
propage.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from observability.json_logger import get_logger

_log = get_logger("observability.runtime_provenance_snapshot")

SCHEMA_VERSION = 1

DEFAULT_SNAPSHOT_PATH = Path(
    os.getenv(
        "RUNTIME_PROVENANCE_SNAPSHOT_PATH",
        "databases/observation/runtime_provenance_snapshot.json",
    )
)

# Cadence de rafraichissement cible (mission section 10) : ~30-60s. Le
# rafraichissement est piloté par l'appelant (advisor_loop, fin de cycle) —
# ce module se contente d'ignorer les appels trop rapprochés.
DEFAULT_MIN_REFRESH_INTERVAL_S = 30.0

UNAVAILABLE = "UNAVAILABLE"

# S-03D section 6 — un seul epoch UUID d'exposition, cree une fois au premier
# instantané de ce processus. Explicitement PAS un packet_id/trace_id/
# decision_id/experiment_id : c'est un identifiant de la couche d'exposition
# elle-meme, pas une identite scientifique.
_EXPOSURE_EPOCH_ID = str(uuid.uuid4())
_PROCESS_START_MONOTONIC = time.monotonic()

# Champs dont la seule presence dans le nom suffit a faire echouer le test de
# non-fuite de secret — whitelist stricte en sortie, jamais de dump generique
# d'objet ou d'environnement (mission section 13).
_FORBIDDEN_SUBSTRINGS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "credential",
    "ssh",
    "private_key",
)


def _unavailable_block(status: str = UNAVAILABLE) -> Dict[str, Any]:
    return {"status": status}


def _decision_observation_block() -> Dict[str, Any]:
    """DecisionObservation — compteurs module-level, toujours disponibles
    (pas d'instance a construire, S-03B item 1)."""
    try:
        from observability.decision_observation import get_provenance_failure_stats

        stats = get_provenance_failure_stats()
        return {
            "status": "ACTIVE",
            "missing_packet_id": stats.get("missing_packet_id"),
            "missing_trace_id": stats.get("missing_trace_id"),
        }
    except Exception as exc:
        _log.debug("[RuntimeProvenanceSnapshot] decision_observation: %s", exc)
        return _unavailable_block()


def _event_bus_block(bus: Optional[Any]) -> Dict[str, Any]:
    if bus is None:
        return _unavailable_block()
    try:
        stats = bus.get_stats()
    except Exception as exc:
        _log.debug("[RuntimeProvenanceSnapshot] event_bus: %s", exc)
        return _unavailable_block("ERROR")
    return {
        "status": "ACTIVE",
        "observations_published": stats.get("observations_published"),
        "listener_deliveries_submitted": stats.get("listener_deliveries_submitted"),
        "listener_deliveries_succeeded": stats.get("listener_deliveries_succeeded"),
        "listener_deliveries_failed": stats.get("listener_deliveries_failed"),
        "deliveries_dropped_during_shutdown": stats.get(
            "deliveries_dropped_during_shutdown"
        ),
    }


def _rejection_store_block(store: Optional[Any]) -> Dict[str, Any]:
    if store is None:
        return _unavailable_block()
    try:
        stats = store.stats()
    except Exception as exc:
        _log.debug("[RuntimeProvenanceSnapshot] rejection_store: %s", exc)
        return _unavailable_block("ERROR")
    return {
        "status": "ACTIVE",
        "writes": stats.get("writes"),
        "errors": stats.get("errors"),
        "skipped_provenance": stats.get("skipped_provenance"),
    }


def _regret_scheduler_block(scheduler: Optional[Any]) -> Dict[str, Any]:
    if scheduler is None:
        return _unavailable_block()
    try:
        stats = scheduler.stats()
    except Exception as exc:
        _log.debug("[RuntimeProvenanceSnapshot] regret_scheduler: %s", exc)
        return _unavailable_block("ERROR")
    return {
        "status": "ACTIVE",
        "pending_candidates": stats.get("pending_candidates"),
        "horizons_evaluated": stats.get("horizons_evaluated"),
        "running": stats.get("running"),
        "skipped_invalid_provenance": stats.get("skipped_invalid_provenance"),
    }


def _dip_block(dip_observer: Optional[Any]) -> Dict[str, Any]:
    # S-03D-R1 blocker 1: absence de dip_observer signifie que le DIP n'a
    # jamais été démarré (dip.bootstrap.is_running() == False côté appelant,
    # voir core/advisor_loop.py) — jamais qu'un objet frais a été créé pour
    # l'occasion. Reporter NOT_STARTED, sans handler_count ni
    # skipped_invalid_provenance fabriqués : ces compteurs appartiendraient à
    # un singleton que ce module n'a pas le droit de créer lui-même.
    if dip_observer is None:
        return {"status": "NOT_STARTED"}
    try:
        stats = dip_observer.get_stats()
        started = bool(getattr(dip_observer, "is_started", False))
    except Exception as exc:
        _log.debug("[RuntimeProvenanceSnapshot] dip: %s", exc)
        return _unavailable_block("ERROR")
    return {
        "status": "ACTIVE" if started else "NOT_STARTED",
        "handler_count": stats.get("handler_count"),
        "skipped_invalid_provenance": stats.get("skipped_invalid_provenance"),
    }


def _black_box_block(black_box: Optional[Any]) -> Dict[str, Any]:
    if black_box is None:
        return _unavailable_block()
    try:
        write_stats = black_box.get_write_stats()
        provenance = black_box.get_provenance_stats()
    except Exception as exc:
        _log.debug("[RuntimeProvenanceSnapshot] black_box: %s", exc)
        return _unavailable_block("ERROR")
    return {
        "status": "ACTIVE",
        "write_attempts": write_stats.get("write_attempts"),
        "write_successes": write_stats.get("write_successes"),
        "write_failures": write_stats.get("write_failures"),
        "provenance": dict(provenance),
    }


@dataclass
class RuntimeProvenanceInputs:
    """Références aux instances LIVE du processus advisor_loop en cours.

    Chaque champ est optionnel — un composant absent (feature flag désactivé,
    module non chargé) doit rester `None`, jamais une instance fraîche créée
    pour l'occasion (mission section 2)."""

    decision_event_bus: Optional[Any] = None
    rejection_store: Optional[Any] = None
    regret_scheduler: Optional[Any] = None
    dip_observer: Optional[Any] = None
    black_box: Optional[Any] = None
    invocation_id: Optional[str] = None


def build_snapshot(
    inputs: RuntimeProvenanceInputs,
    now_fn: Callable[[], float] = time.time,
) -> Dict[str, Any]:
    """Compose l'instantané sanitizé. Ne lève jamais — un échec de lecture
    d'un composant se traduit par un bloc UNAVAILABLE/ERROR, jamais par une
    exception qui remonterait au cycle advisor_loop."""

    now = now_fn()
    invocation_id = inputs.invocation_id or os.getenv("INVOCATION_ID") or None

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(now),
        "process": {
            "pid": os.getpid(),
            "invocation_id": invocation_id,
            "exposure_epoch_id": _EXPOSURE_EPOCH_ID,
            "uptime_s": round(time.monotonic() - _PROCESS_START_MONOTONIC, 3),
        },
        "decision_observation": _decision_observation_block(),
        "event_bus": _event_bus_block(inputs.decision_event_bus),
        "rejection_store": _rejection_store_block(inputs.rejection_store),
        "regret_scheduler": _regret_scheduler_block(inputs.regret_scheduler),
        "dip": _dip_block(inputs.dip_observer),
        "black_box": _black_box_block(inputs.black_box),
    }


def _iso_utc(ts: float) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def assert_no_secret_material(payload: Dict[str, Any]) -> None:
    """Garde défensive — lève si un nom de champ suspect apparaît dans le
    JSON sérialisé. Utilisée par les tests (mission section 13/19.9) et
    disponible pour un appelant prudent."""
    blob = json.dumps(payload).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in blob:
            raise ValueError(f"secret-like field detected in snapshot: {needle}")


class RuntimeProvenanceSnapshotWriter:
    """Composeur + écrivain passif, cadence bornée.

    Aucun thread de fond n'est démarré ici — l'appelant (advisor_loop,
    fin de cycle) décide quand appeler `maybe_refresh()`. C'est
    l'intégration la moins invasive disponible (mission section 10) :
    advisor_loop a déjà une frontière de fin de cycle naturelle
    (watchdog.end_cycle), pas besoin d'un thread supplémentaire.
    """

    def __init__(
        self,
        path: Path = DEFAULT_SNAPSHOT_PATH,
        min_interval_s: float = DEFAULT_MIN_REFRESH_INTERVAL_S,
    ) -> None:
        self._path = Path(path)
        self._min_interval_s = min_interval_s
        self._last_write_monotonic: float = float("-inf")
        self._lock = threading.Lock()
        self.write_errors = 0

    def maybe_refresh(
        self, inputs: RuntimeProvenanceInputs, force: bool = False
    ) -> bool:
        """Rafraîchit le fichier si la cadence minimale est écoulée.

        Retourne True si un fichier a été (tenté d')écrit, False si l'appel a
        été ignoré par cadence. Ne lève jamais.
        """
        now_mono = time.monotonic()
        with self._lock:
            if not force and (now_mono - self._last_write_monotonic) < (
                self._min_interval_s
            ):
                return False
            self._last_write_monotonic = now_mono
        try:
            snapshot = build_snapshot(inputs)
            self._write_atomic(snapshot)
        except Exception as exc:
            # PASSIF — jamais d'impact sur la boucle de décision (mission
            # section 11).
            self.write_errors += 1
            _log.warning(
                "[RuntimeProvenanceSnapshot] Écriture échouée (non bloquant): %s",
                exc,
            )
        return True

    def _write_atomic(self, snapshot: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
