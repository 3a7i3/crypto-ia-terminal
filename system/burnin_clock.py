"""
system/burnin_clock.py — Horloge de burn-in : source unique et persistante.

Constat opérateur (2026-08-07) : le panneau « MEXC SIM — Rapport performance »
affichait « Duree : J0.8 / 7 (session depuis restart) » alors que l'époque V4
courait depuis plusieurs semaines. Deux compteurs distincts mesuraient la même
chose, et tous les deux repartaient de zéro à chaque redémarrage du process :

  - `PerformanceTracker.days_running()` (paper_trading/mexc_simulator.py) —
    `time.time() - _start_ts`, `_start_ts` posé dans `__init__` ;
  - `PhaseAllocation.days_elapsed()` (capital_deployment/capital_throttle.py),
    affiché « Jour X / 7 » par le bot Mon Portefeuille — `started_at` posé par
    défaut à `time.time()` dans `CapitalThrottle.__init__`.

Conséquence : un burn-in de 7 jours n'était jamais atteignable dès lors que le
service redémarrait plus souvent que tous les 7 jours — le compteur *repartait*
au lieu de *continuer*. Ce module remplace les deux par une horloge unique,
ancrée sur les **données** et non sur le process : elle survit aux redémarrages
et ne repart que sur un changement d'époque explicite (ADR-0017).

Ordre de résolution du point de départ (le premier qui répond gagne) :

  1. `BURNIN_START_TS` — override opérateur (epoch secondes ou ISO 8601).
     Décision explicite, versionnée, jamais un effet de bord.
  2. État persisté (`databases/burnin_clock.json`), *si* l'époque qui y est
     inscrite est encore l'époque active. Sinon l'état est périmé et ignoré.
  3. Premier CLOSE du dataset canonique (`load_clean_trades`, loader unique
     INV-DATASET-001) — l'instant où l'époque courante a commencé à produire
     des données.
  4. `CLEAN_DATA_SINCE_ACTIVE` — borne d'époque, quand le dataset est vide
     (burn-in qui démarre, aucun trade encore fermé).

La valeur résolue est écrite dans l'état persisté avec l'époque qui l'a
produite : au redémarrage suivant, l'étape 2 la rend telle quelle.

Ce module est un **outil de mesure** (ADR-0007) : il lit, il n'écrit aucune
décision. Aucun composant décisionnel ne le consomme.

Usage :
    from system.burnin_clock import days_elapsed

    d = days_elapsed()          # jours écoulés depuis le début du burn-in

CLI d'audit :
    python3 -m system.burnin_clock
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SECONDS_PER_DAY = 86400.0

DEFAULT_STATE_PATH = Path("databases/burnin_clock.json")

# Sources possibles du point de départ, par ordre de résolution.
SOURCE_ENV = "env:BURNIN_START_TS"
SOURCE_STATE = "state_file"
SOURCE_FIRST_TRADE = "first_clean_trade"
SOURCE_EPOCH = "clean_data_since_active"
SOURCE_FALLBACK = "now_fallback"

_LOCK = threading.Lock()
# Cache process : (epoch_iso, started_at, source). Recalculé si l'époque bouge.
_CACHE: Optional[tuple[str, float, str]] = None


def state_path() -> Path:
    """Chemin de l'état persisté — surchargeable pour les tests."""
    return Path(os.getenv("BURNIN_CLOCK_STATE", str(DEFAULT_STATE_PATH)))


# ── Époque active ─────────────────────────────────────────────────────────────


def _epoch() -> datetime:
    """Borne d'époque active — importée, jamais recopiée (CLAUDE.md)."""
    from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE

    return CLEAN_DATA_SINCE_ACTIVE


def _epoch_iso() -> str:
    return _epoch().isoformat()


# ── Résolution du point de départ ─────────────────────────────────────────────


def _parse_ts(raw: object) -> Optional[float]:
    """Epoch secondes ou ISO 8601 → timestamp UTC. None si illisible."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        ts = float(raw)
        return ts if ts > 0 else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        ts = float(text)
        return ts if ts > 0 else None
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _from_env() -> Optional[float]:
    return _parse_ts(os.getenv("BURNIN_START_TS", ""))


def _read_state() -> Optional[float]:
    """État persisté, seulement s'il porte l'époque active."""
    path = state_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("epoch", "")) != _epoch_iso():
        return None  # état d'une époque révolue — on le laisse être réécrit
    return _parse_ts(data.get("started_at"))


def _write_state(started_at: float, source: str) -> None:
    """Écriture best-effort — une horloge ne doit jamais casser un rapport."""
    path = state_path()
    payload = {
        "started_at": round(started_at, 3),
        "started_at_iso": datetime.fromtimestamp(
            started_at, tz=timezone.utc
        ).isoformat(),
        "epoch": _epoch_iso(),
        "source": source,
        "written_at": round(time.time(), 3),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass


def _first_clean_trade_ts() -> Optional[float]:
    """Horodatage du premier CLOSE canonique de l'époque courante."""
    try:
        from tools.cri_calculator import load_clean_trades

        trades = load_clean_trades()
    except Exception:
        return None
    stamps = [ts for ts in (_parse_ts(t.get("ts")) for t in trades) if ts]
    return min(stamps) if stamps else None


def _resolve() -> tuple[float, str]:
    """Point de départ + source, sans toucher au cache ni à l'état."""
    ts = _from_env()
    if ts:
        return ts, SOURCE_ENV

    ts = _read_state()
    if ts:
        return ts, SOURCE_STATE

    ts = _first_clean_trade_ts()
    if ts:
        return ts, SOURCE_FIRST_TRADE

    try:
        return _epoch().timestamp(), SOURCE_EPOCH
    except Exception:
        return time.time(), SOURCE_FALLBACK


# ── API publique ──────────────────────────────────────────────────────────────


def burnin_start(refresh: bool = False) -> float:
    """Timestamp UTC du début du burn-in de l'époque courante.

    Stable d'un redémarrage à l'autre : c'est tout l'intérêt du module.
    `refresh=True` force une re-résolution (usage tests / CLI d'audit).
    """
    global _CACHE
    with _LOCK:
        epoch_iso = _epoch_iso()
        if not refresh and _CACHE is not None and _CACHE[0] == epoch_iso:
            return _CACHE[1]
        started_at, source = _resolve()
        if source != SOURCE_STATE:
            _write_state(started_at, source)
        _CACHE = (epoch_iso, started_at, source)
        return started_at


def burnin_source(refresh: bool = False) -> str:
    """Source ayant fourni le point de départ (traçabilité des rapports)."""
    burnin_start(refresh=refresh)
    return _CACHE[2] if _CACHE is not None else SOURCE_FALLBACK


def days_elapsed(now: Optional[float] = None) -> float:
    """Jours écoulés depuis le début du burn-in. Jamais négatif."""
    delta = (time.time() if now is None else now) - burnin_start()
    return max(0.0, delta / SECONDS_PER_DAY)


def reset(started_at: Optional[float] = None) -> float:
    """Repose l'horloge — geste opérateur explicite (changement d'époque).

    Jamais appelé par un redémarrage : c'est précisément ce que ce module
    empêche.
    """
    global _CACHE
    with _LOCK:
        ts = float(started_at) if started_at else time.time()
        _write_state(ts, "operator_reset")
        _CACHE = (_epoch_iso(), ts, "operator_reset")
        return ts


def snapshot() -> dict:
    """Vue complète de l'horloge — pour les panneaux et l'audit."""
    started_at = burnin_start()
    return {
        "started_at": round(started_at, 3),
        "started_at_iso": datetime.fromtimestamp(
            started_at, tz=timezone.utc
        ).isoformat(),
        "epoch": _epoch_iso(),
        "source": burnin_source(),
        "days_elapsed": round(days_elapsed(), 3),
        "state_path": str(state_path()),
    }


def _main() -> int:
    print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI d'audit
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(_main())
