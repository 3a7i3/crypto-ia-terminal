"""
tools/cri_calculator.py — Calibration Readiness Index (CRI).

Définition gelée par ADR-0011 (2026-07-05), AVANT que le dataset propre
n'atteigne un effectif significatif — condition nécessaire à un
pré-enregistrement honnête.

CRI = (w1·N_score + w2·coverage_score + w3·drift_score + w4·balance_score) / 100
Poids : w1=w2=w3=w4=25 (égalité faute de justification empirique d'en
privilégier un — voir ADR-0011). Gate : CRI >= 90/100 (CLAUDE.md).

Lecture seule sur databases/paper_trades.jsonl et databases/regret_analysis.jsonl,
filtrés par CLEAN_DATA_SINCE = 2026-06-25 (ADR-0011, remplace la consigne
du 2026-06-21 par inclusion stricte).

Usage : python3 tools/cri_calculator.py [--trades PATH] [--regrets PATH]
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CLEAN_DATA_SINCE = datetime(2026, 6, 25, tzinfo=timezone.utc)

N_TARGET = 500
BALANCE_TARGET = 150
MIN_CELL_OBSERVATIONS = 5
MIN_PSI_SAMPLE = 10

WEIGHTS = {"n": 25.0, "coverage": 25.0, "drift": 25.0, "balance": 25.0}

SCORE_BIN_LABELS = ["<50", "50-59", "60-69", "70-79", "80+"]

DEFAULT_TRADES_PATH = Path("databases/paper_trades.jsonl")
DEFAULT_REGRET_PATH = Path("databases/regret_analysis.jsonl")


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


def load_clean_trades(path: Path = DEFAULT_TRADES_PATH) -> list[dict]:
    """CLOSE events, filtrés par CLEAN_DATA_SINCE (ADR-0011)."""
    trades = []
    for d in _read_jsonl(path):
        if d.get("event") != "CLOSE":
            continue
        ts = _event_ts(d)
        if ts is None or ts < CLEAN_DATA_SINCE:
            continue
        trades.append(d)
    return trades


def load_clean_regrets(path: Path = DEFAULT_REGRET_PATH) -> list[dict]:
    """Regrets filtrés par CLEAN_DATA_SINCE (ADR-0011)."""
    regrets = []
    for d in _read_jsonl(path):
        ts = _event_ts(d)
        if ts is None or ts < CLEAN_DATA_SINCE:
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
    trades_path: Path = DEFAULT_TRADES_PATH,
    regret_path: Path = DEFAULT_REGRET_PATH,
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

    return {
        "cri": round(cri, 2),
        "gate_ready": cri >= 90.0,
        "n_clean": len(trades),
        "n_regrets_clean": len(regrets),
        "clean_data_since": CLEAN_DATA_SINCE.isoformat(),
        "sub_scores": {k: round(v, 2) for k, v in scores.items()},
        "weights": WEIGHTS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES_PATH)
    parser.add_argument("--regrets", type=Path, default=DEFAULT_REGRET_PATH)
    args = parser.parse_args()

    result = compute_cri(args.trades, args.regrets)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
