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


def _exclusion_reason(record: dict) -> Optional[str]:
    """Motif d'exclusion d'un événement CLOSE, ou None s'il est canonique."""
    ts = _event_ts(record)
    if ts is None:
        return "ts_absent_ou_illisible"
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

    Filtres appliqués, dans l'ordre :
      1. `event == "CLOSE"`
      2. horodatage >= `CLEAN_DATA_SINCE_ACTIVE` (borne d'époque, ADR-0017)
      3. hors fixtures de test (prix < 500 ET score == 0)
      4. hors artefacts de restauration (durée == 0 ET score == 0 ET régime inconnu)

    `path=None` → `default_trades_path()`. Aucun appelant ne doit reconstruire
    ces filtres : tout KPI calculé sur une autre population que celle-ci est,
    par construction, incomparable aux autres outils du dépôt.
    """
    target = default_trades_path() if path is None else path
    return [
        d
        for d in _read_jsonl(target)
        if d.get("event") == "CLOSE" and _exclusion_reason(d) is None
    ]


def trades_provenance(path: Optional[Path] = None) -> dict:
    """Provenance du dataset chargé — à joindre à toute décision (INV-DATASET-001).

    Rend explicite CE QUI a été lu et CE QUI a été écarté, pour qu'un rapport
    ne puisse pas citer un N sans que sa population soit reconstituable.
    """
    target = default_trades_path() if path is None else path
    closes = [d for d in _read_jsonl(target) if d.get("event") == "CLOSE"]

    excluded: dict[str, int] = {}
    kept = 0
    for record in closes:
        reason = _exclusion_reason(record)
        if reason is None:
            kept += 1
        else:
            excluded[reason] = excluded.get(reason, 0) + 1

    return {
        "loader": "tools.cri_calculator.load_clean_trades",
        "source_path": str(target),
        "clean_data_since": CLEAN_DATA_SINCE_ACTIVE.isoformat(),
        "close_events_total": len(closes),
        "n_canonical": kept,
        "excluded_by_reason": excluded,
    }


def load_clean_regrets(path: Optional[Path] = None) -> list[dict]:
    """Regrets filtrés par CLEAN_DATA_SINCE_ACTIVE.

    `path=None` → SOURCE CANONIQUE (MC-001 / ADR-0018 : regret-v2 via
    tools.regret_repository, jamais un chemin en dur). Un chemin explicite lit
    un fichier plat historique (compat tests / override d'audit)."""
    if path is None:
        from tools.regret_repository import read_canonical_regrets

        return read_canonical_regrets(since=CLEAN_DATA_SINCE_ACTIVE)
    regrets = []
    for d in _read_jsonl(path):
        ts = _event_ts(d)
        if ts is None or ts < CLEAN_DATA_SINCE_ACTIVE:
            continue
        regrets.append(d)
    return regrets


def n_score(n_clean: int) -> float:
    return min(100.0, 100.0 * n_clean / N_TARGET)


def coverage_score(trades: list[dict], regrets: list[dict]) -> float:
    """% des cellules (régime observé x score_bin) avec >= 5 observations.

    Grille fondée sur les régimes RÉELLEMENT observés dans le dataset —
    pas une taxonomie théorique (au moins 3 coexistent dans le code, dont
    une exclut le régime flash_crash pourtant observé en production —
    voir ADR-0011)."""
    cells: dict[tuple[str, str], int] = defaultdict(int)
    observed_regimes: set[str] = set()

    for r in trades:
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
    """100 x (1 - PSI) entre 1ere et 2eme moitie du dataset propre.

    Retourne 0.0 (pas 100.0) si l'echantillon est trop petit pour un PSI
    significatif — cohérent avec un N_score déjà bas à ce stade."""
    scores = [float(t["score"]) for t in trades if t.get("score") is not None]
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

    result = {
        "cri": round(cri, 2),
        "gate_ready": cri >= 90.0,
        "n_clean": len(trades),
        "n_regrets_clean": len(regrets),
        "clean_data_since": CLEAN_DATA_SINCE_ACTIVE.isoformat(),
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
        result["regret_fresh"] = f["fresh"]
        result["validity"] = "OK" if f["fresh"] else "PARTIAL"
        if not f["fresh"]:
            result["warnings"] = [
                "DATASET REGRET PÉRIMÉ (dernier événement "
                f"{f['last_event_utc']}) — CRI PARTIELLEMENT CENSURÉ, "
                "ne pas comparer dans le temps"
            ]
    else:
        result["regret_source"] = "explicit_path"
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
