"""
tools/cri_calculator.py — Calibration Readiness Index (CRI).

Définition gelée par ADR-0011 (2026-07-05), AVANT que le dataset propre
n'atteigne un effectif significatif — condition nécessaire à un
pré-enregistrement honnête.

CRI = (w1·N_score + w2·coverage_score + w3·drift_score + w4·balance_score) / 100
Poids : w1=w2=w3=w4=25 (égalité faute de justification empirique d'en
privilégier un — voir ADR-0011). Gate : CRI >= 90/100 (CLAUDE.md).

Lecture seule sur databases/paper_trades.jsonl et le contrat MC-001 regret-v2,
filtrés par CLEAN_DATA_SINCE_ACTIVE (addendum ADR-0012, 2026-07-09 — restart
SEC-01 réellement effectif ; v2/01:16Z reposait sur un déploiement
silencieusement partiel, SEC-01 jamais chargé — voir addendum). Remplace
v1/2026-06-25 et v2 par inclusion stricte. Borne importée depuis
scripts/data_quality.py — source unique, plus de copie locale
(dette notée en T2, soldée avec ADR-0012).

Usage : python3 tools/cri_calculator.py [--trades PATH] [--regrets PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Racine du repo sur sys.path — permet `python3 tools/cri_calculator.py`
# en invocation directe (même convention que scripts/prelive_gate.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE  # noqa: E402

N_TARGET = 500
BALANCE_TARGET = 150
MIN_CELL_OBSERVATIONS = 5
MIN_PSI_SAMPLE = 10

WEIGHTS = {"n": 25.0, "coverage": 25.0, "drift": 25.0, "balance": 25.0}


SCORE_BIN_LABELS = ["<50", "50-59", "60-69", "70-79", "80+"]


class ScientificDatasetUnavailableError(RuntimeError):
    """The canonical scientific population cannot be identified honestly."""


def _active_ppl_epoch_id() -> Optional[str]:
    """Return the exact authoritative PPL epoch used as scientific population."""

    from paper_trading.paper_authority import (
        PaperLifecycleAuthority,
        resolve_paper_lifecycle_authority,
    )

    authority = resolve_paper_lifecycle_authority(os.environ)
    if authority is not PaperLifecycleAuthority.PPL_AUTHORITY:
        return None

    epoch_id = str(os.getenv("PPL_AUTHORITY_EPOCH_ID", "") or "").strip()
    if not epoch_id:
        raise ScientificDatasetUnavailableError(
            "PPL_AUTHORITY scientific dataset requires PPL_AUTHORITY_EPOCH_ID"
        )
    return epoch_id


def _missing_evidence_fields(record: dict) -> set[str]:
    raw = record.get("missing_evidence_fields")
    if not raw:
        return set()
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(",") if item.strip()}
    if isinstance(raw, (list, tuple, set)):
        return {str(item).strip() for item in raw if str(item).strip()}
    return {str(raw).strip()}


def _trade_has_decision_metadata(record: dict) -> bool:
    """Whether score/regime are evidenced enough for coverage/drift metrics."""

    if str(record.get("source_authority") or "") == "PPL":
        missing = _missing_evidence_fields(record)
        if "score" in missing or "regime" in missing:
            return False
    return record.get("score") is not None and record.get("regime") is not None

DEFAULT_TRADES_PATH = Path("databases/paper_trades.jsonl")
# Override CLI historique uniquement. ``path=None`` utilise regret_repository.
DEFAULT_REGRET_PATH = Path("databases/regret_analysis.jsonl")

# ── Filtres de qualité absorbés depuis scripts/burnin_calibration_v3.py ───────
# (INV-DATASET-001, 2026-07-28 : ce module est le loader unique des paper
# trades. Ces deux filtres n'existaient que dans burnin_calibration_v3 ; les
# rapatrier ici évite qu'un outil voie une population que l'autre ignore.)
#
# Mesure d'impact au moment de l'absorption, sur le corpus VPS du 2026-07-28
# (649 CLOSE, dont 106 post-borne V4) :
#   - fixtures de test  : 18 exclusions sur le corpus entier, 0 post-borne V4
#   - restore artifacts :  0 exclusion  sur le corpus entier, 0 post-borne V4
# Les deux filtres sont donc un NO-OP sur le dataset canonique actuel : leur
# ajout ne déplace ni N ni le CRI. Ils restent en défense en profondeur pour
# les époques antérieures et pour tout outil lisant hors borne.

# Trades réels : prix BTC >> 1000. Les fixtures des anciens tests unitaires
# utilisaient un prix 101-102 sans score de pipeline.
_REAL_TRADE_PRICE_FLOOR = 500.0

# Artefacts de restauration : MexcSimulator._restore_positions() reclôturait
# instantanément les positions ouvertes au redémarrage, avant le correctif de
# la session 2026-06-07. Prix réel, mais durée nulle et aucun contexte pipeline.
_RESTORE_ARTIFACT_REGIME = "unknown"


def _score_bin(score: float) -> str:
    if score < 50:
        return "<50"
    if score < 60:
        return "50-59"
    if score < 70:
        return "60-69"
    if score < 80:
        return "70-79"
    return "80+"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _event_ts(record: dict) -> Optional[datetime]:
    ts = record.get("ts") or record.get("ts_signal")
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_trades_path() -> Path:
    """Chemin canonique du journal de paper trades.

    Résolu ici et nulle part ailleurs : `PAPER_TRADE_LOG` était lu
    indépendamment par burnin_calibration_v3 et prelive_gate, tandis que ce
    module utilisait un chemin en dur — trois résolutions pour une seule
    source de vérité (INV-DATASET-001).
    """
    return Path(os.getenv("PAPER_TRADE_LOG", str(DEFAULT_TRADES_PATH)))


def _exclusion_reason(
    record: dict,
    *,
    ppl_epoch_id: Optional[str],
) -> Optional[str]:
    """Motif d'exclusion d'un CLOSE sous le contrat de population actif."""

    ts = _event_ts(record)
    if ts is None:
        return "ts_absent_ou_illisible"

    source_authority = str(record.get("source_authority") or "")
    record_epoch = str(record.get("paper_epoch_id") or "")

    if ppl_epoch_id is not None:
        if source_authority != "PPL":
            return "legacy_outside_ppl_epoch"
        if record_epoch != ppl_epoch_id:
            return "ppl_wrong_epoch"
        if (
            str(record.get("evidence_status") or "").upper() == "UNRESOLVED"
            or record.get("pnl_usd") is None
        ):
            return "ppl_unresolved_outcome"
        # Epoch identity is the experiment boundary under PPL. Historical
        # price/score fixture heuristics must never reinterpret a provenance-
        # bound PPL trade as synthetic evidence.
        return None

    # Legacy scientific population remains exactly the historical clean-window
    # contract. Once PPL rows exist in the compatibility journal, they are not
    # silently mixed back into that Legacy population.
    if source_authority == "PPL":
        return "ppl_outside_legacy_population"

    if ts < CLEAN_DATA_SINCE_ACTIVE:
        return "anterieur_borne_canonique"

    price = _safe_float(record.get("price")) or _safe_float(record.get("exit_price"))
    score = _safe_float(record.get("score"))
    if price < _REAL_TRADE_PRICE_FLOOR and score == 0:
        return "fixture_de_test"

    duration = _safe_float(record.get("duration_s"), default=-1.0)
    regime = record.get("regime") or _RESTORE_ARTIFACT_REGIME
    if duration == 0.0 and score == 0 and regime == _RESTORE_ARTIFACT_REGIME:
        return "artefact_de_restauration"

    return None


def load_clean_trades(path: Optional[Path] = None) -> list[dict]:
    """Dataset canonique des paper trades — LOADER UNIQUE (INV-DATASET-001).

    LEGACY/PPL_SHADOW conservent le contrat historique CLEAN_DATA_SINCE +
    heuristiques de qualité.

    Sous PPL_AUTHORITY, l'identité scientifique est stricte : uniquement les
    CLOSE projetés par PPL pour l'exact PPL_AUTHORITY_EPOCH_ID. Les lignes
    Legacy, les autres epochs et les outcomes UNRESOLVED sont exclus. Les
    heuristiques historiques prix/score ne s'appliquent jamais à une ligne PPL
    provenance-bound.
    """

    target = default_trades_path() if path is None else path
    ppl_epoch_id = _active_ppl_epoch_id()
    return [
        d
        for d in _read_jsonl(target)
        if d.get("event") == "CLOSE"
        and _exclusion_reason(d, ppl_epoch_id=ppl_epoch_id) is None
    ]


def trades_provenance(path: Optional[Path] = None) -> dict:
    """Provenance exacte de la population scientifique effectivement mesurée."""

    target = default_trades_path() if path is None else path
    ppl_epoch_id = _active_ppl_epoch_id()
    closes = [d for d in _read_jsonl(target) if d.get("event") == "CLOSE"]

    excluded: dict[str, int] = {}
    kept_records: list[dict] = []
    for record in closes:
        reason = _exclusion_reason(record, ppl_epoch_id=ppl_epoch_id)
        if reason is None:
            kept_records.append(record)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1

    return {
        "loader": "tools.cri_calculator.load_clean_trades",
        "source_path": str(target),
        "population_mode": "PPL_EPOCH" if ppl_epoch_id is not None else "LEGACY_CLEAN_WINDOW",
        "source_authority": "PPL" if ppl_epoch_id is not None else "LEGACY_COMPATIBLE",
        "paper_epoch_id": ppl_epoch_id,
        "clean_data_since": (
            None if ppl_epoch_id is not None else CLEAN_DATA_SINCE_ACTIVE.isoformat()
        ),
        "close_events_total": len(closes),
        "n_canonical": len(kept_records),
        "decision_metadata_complete": sum(
            1 for record in kept_records if _trade_has_decision_metadata(record)
        ),
        "excluded_by_reason": excluded,
    }


def load_clean_regrets(path: Optional[Path] = None) -> list[dict]:
    """Load regret evidence under the same scientific-epoch contract.

    In PPL_AUTHORITY, regret observations are usable only when they explicitly
    carry source_authority=PPL and the exact authoritative paper_epoch_id.
    Existing regret-v2 rows without that provenance remain valid historical
    evidence but are not silently attributed to F-00.
    """

    ppl_epoch_id = _active_ppl_epoch_id()
    if path is None:
        from tools.regret_repository import read_canonical_regrets

        rows = read_canonical_regrets(
            since=None if ppl_epoch_id is not None else CLEAN_DATA_SINCE_ACTIVE
        )
    else:
        rows = []
        for d in _read_jsonl(path):
            ts = _event_ts(d)
            if ts is None:
                continue
            if ppl_epoch_id is None and ts < CLEAN_DATA_SINCE_ACTIVE:
                continue
            rows.append(d)

    if ppl_epoch_id is None:
        return rows

    return [
        row
        for row in rows
        if str(row.get("source_authority") or "") == "PPL"
        and str(row.get("paper_epoch_id") or "") == ppl_epoch_id
    ]


def n_score(n_clean: int) -> float:
    return min(100.0, 100.0 * n_clean / N_TARGET)


def coverage_score(trades: list[dict], regrets: list[dict]) -> float:
    """% des cellules (régime observé x score_bin) avec >= 5 observations.

    Les trades PPL à métadonnées de décision partielles comptent pour le
    lifecycle/PnL, mais jamais pour une cellule score/régime qu'ils ne prouvent
    pas. Les regrets doivent déjà avoir été filtrés par epoch par le loader.
    """

    cells: dict[tuple[str, str], int] = defaultdict(int)
    observed_regimes: set[str] = set()

    for r in trades:
        if not _trade_has_decision_metadata(r):
            continue
        regime = r.get("regime")
        score = r.get("score")
        if regime is None or score is None:
            continue
        observed_regimes.add(regime)
        cells[(regime, _score_bin(float(score)))] += 1

    for r in regrets:
        regime = r.get("regime")
        score = r.get("score")
        if regime is None or score is None:
            continue
        observed_regimes.add(regime)
        cells[(regime, _score_bin(float(score)))] += 1

    if not observed_regimes:
        return 0.0

    total_cells = len(observed_regimes) * len(SCORE_BIN_LABELS)
    covered = sum(1 for count in cells.values() if count >= MIN_CELL_OBSERVATIONS)
    return 100.0 * covered / total_cells


def _psi(expected: list[float], actual: list[float], bins: int = 5) -> float:
    """Population Stability Index entre deux distributions."""
    if not expected or not actual:
        return 0.0
    all_vals = expected + actual
    lo, hi = min(all_vals), max(all_vals)
    if hi == lo:
        return 0.0

    def _hist(vals: list[float]) -> list[float]:
        counts = [0] * bins
        for v in vals:
            idx = int((v - lo) / (hi - lo) * bins)
            idx = min(bins - 1, max(0, idx))
            counts[idx] += 1
        total = len(vals)
        return [max(c, 1e-6) / total for c in counts]

    e_hist = _hist(expected)
    a_hist = _hist(actual)
    return sum((a - e) * math.log(a / e) for e, a in zip(e_hist, a_hist))


def drift_score(trades: list[dict]) -> float:
    """Score de drift uniquement sur les scores réellement attribués."""

    scores = [
        float(t["score"])
        for t in trades
        if _trade_has_decision_metadata(t) and t.get("score") is not None
    ]
    n = len(scores)
    if n < 2 * MIN_PSI_SAMPLE:
        return 0.0
    mid = n // 2
    psi = _psi(scores[:mid], scores[mid:])
    return max(0.0, min(100.0, 100.0 * (1.0 - psi)))


def balance_score(trades: list[dict]) -> float:
    wins = sum(1 for t in trades if (t.get("pnl_usd") or 0) >= 0)
    losses = sum(1 for t in trades if (t.get("pnl_usd") or 0) < 0)
    return 100.0 * min(wins, losses, BALANCE_TARGET) / BALANCE_TARGET


def compute_cri(
    trades_path: Optional[Path] = None,
    regret_path: Optional[Path] = None,
) -> dict:
    trades = load_clean_trades(trades_path)
    regrets = load_clean_regrets(regret_path)

    scores = {
        "n_score": n_score(len(trades)),
        "coverage_score": coverage_score(trades, regrets),
        "drift_score": drift_score(trades),
        "balance_score": balance_score(trades),
    }

    cri = (
        WEIGHTS["n"] * scores["n_score"]
        + WEIGHTS["coverage"] * scores["coverage_score"]
        + WEIGHTS["drift"] * scores["drift_score"]
        + WEIGHTS["balance"] * scores["balance_score"]
    ) / 100.0

    provenance = trades_provenance(trades_path)
    result = {
        "cri": round(cri, 2),
        "gate_ready": cri >= 90.0,
        "n_clean": len(trades),
        "n_regrets_clean": len(regrets),
        "dataset_population_mode": provenance["population_mode"],
        "paper_epoch_id": provenance["paper_epoch_id"],
        "clean_data_since": provenance["clean_data_since"],
        "decision_metadata_complete": provenance["decision_metadata_complete"],
        "sub_scores": {k: round(v, 2) for k, v in scores.items()},
        "weights": WEIGHTS,
    }

    # MC-001 : traçabilité + validité. La source canonique doit être FRAÎCHE ;
    # sinon le CRI est partiellement censuré (leçon rupture 2026-07-10).
    if regret_path is None:
        from tools.regret_repository import freshness

        f = freshness()
        result["regret_source"] = "canonical:" + f["dataset_version"]
        result["canonical_horizon"] = f["canonical_horizon"]
        result["regret_last_event"] = f["last_event_utc"]
        result["regret_last_canonical_evaluated"] = f["last_canonical_evaluated_utc"]
        result["regret_fresh"] = f["fresh"]
        warnings = []
        if provenance["population_mode"] == "PPL_EPOCH" and not regrets:
            warnings.append(
                "REGRET_EPOCH_ATTRIBUTION_UNAVAILABLE — aucune preuve regret-v2 "
                "n'est attribuable à l'epoch PPL actif; coverage CRI reste censurée"
            )
        if not f["fresh"]:
            warnings.append(
                "DATASET REGRET PÉRIMÉ (dernière évaluation canonique "
                f"{f['last_canonical_evaluated_utc']}) — CRI PARTIELLEMENT "
                "CENSURÉ, ne pas comparer dans le temps"
            )
        result["validity"] = "PARTIAL" if warnings else "OK"
        if warnings:
            result["warnings"] = warnings
    else:
        result["regret_source"] = "explicit_path"
        if provenance["population_mode"] == "PPL_EPOCH" and not regrets:
            result["validity"] = "PARTIAL"
            result["warnings"] = [
                "REGRET_EPOCH_ATTRIBUTION_UNAVAILABLE — chemin explicite sans "
                "preuve regret attribuable à l'epoch PPL actif"
            ]
        else:
            result["validity"] = "OK"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trades",
        type=Path,
        default=None,
        help="chemin explicite (défaut : PAPER_TRADE_LOG, sinon databases/)",
    )
    parser.add_argument(
        "--regrets",
        type=Path,
        default=None,
        help="chemin explicite (défaut : source canonique MC-001)",
    )
    parser.add_argument(
        "--provenance",
        action="store_true",
        help="joindre la provenance du dataset au rapport (INV-DATASET-001)",
    )
    args = parser.parse_args()

    result = compute_cri(args.trades, args.regrets)
    if args.provenance:
        result["trades_provenance"] = trades_provenance(args.trades)
    if result.get("validity") == "PARTIAL":
        print("⚠️  VALIDITÉ PARTIELLE :", result["warnings"][0], file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())