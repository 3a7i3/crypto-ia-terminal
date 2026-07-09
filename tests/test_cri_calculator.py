"""
tests/test_cri_calculator.py — Calibration Readiness Index (ADR-0011).

Cas synthétiques uniquement — jamais contre les données réelles (le CRI
doit être calculable/testable indépendamment de tout dataset en production).
"""

from __future__ import annotations

import json

from tools.cri_calculator import (
    CLEAN_DATA_SINCE_V2,
    balance_score,
    compute_cri,
    coverage_score,
    drift_score,
    load_clean_regrets,
    load_clean_trades,
    n_score,
)

_AFTER = CLEAN_DATA_SINCE_V2.timestamp() + 3600  # 1h après la borne
_BEFORE = CLEAN_DATA_SINCE_V2.timestamp() - 3600  # 1h avant la borne


def _close(ts: float, pnl_usd: float, score: float, regime: str = "sideways") -> dict:
    return {
        "event": "CLOSE",
        "ts": ts,
        "pnl_usd": pnl_usd,
        "score": score,
        "regime": regime,
    }


def _regret(ts: float, score: float, regime: str = "sideways") -> dict:
    return {"ts_signal": ts, "score": score, "regime": regime}


class TestNScore:
    def test_zero_trades(self):
        assert n_score(0) == 0.0

    def test_half_target(self):
        assert n_score(250) == 50.0

    def test_at_target(self):
        assert n_score(500) == 100.0

    def test_capped_above_target(self):
        assert n_score(1000) == 100.0


class TestCleanDataSinceFilter:
    def test_trades_before_cutoff_excluded(self, tmp_path):
        path = tmp_path / "paper_trades.jsonl"
        path.write_text(
            json.dumps(_close(_BEFORE, 1.0, 70))
            + "\n"
            + json.dumps(_close(_AFTER, 1.0, 70))
            + "\n",
            encoding="utf-8",
        )
        trades = load_clean_trades(path)
        assert len(trades) == 1
        assert trades[0]["ts"] == _AFTER

    def test_regrets_before_cutoff_excluded(self, tmp_path):
        path = tmp_path / "regret_analysis.jsonl"
        path.write_text(
            json.dumps(_regret(_BEFORE, 70))
            + "\n"
            + json.dumps(_regret(_AFTER, 70))
            + "\n",
            encoding="utf-8",
        )
        regrets = load_clean_regrets(path)
        assert len(regrets) == 1

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_clean_trades(tmp_path / "absent.jsonl") == []

    def test_malformed_line_skipped_not_fatal(self, tmp_path):
        path = tmp_path / "paper_trades.jsonl"
        path.write_text(
            "{not valid json\n" + json.dumps(_close(_AFTER, 1.0, 70)) + "\n",
            encoding="utf-8",
        )
        trades = load_clean_trades(path)
        assert len(trades) == 1


class TestScoreBinBoundaries:
    def test_boundaries_via_coverage_grid(self):
        # Une observation par bin exact, meme regime -> 5 cellules distinctes
        trades = [
            _close(_AFTER, 1.0, 49),  # <50
            _close(_AFTER, 1.0, 50),  # 50-59
            _close(_AFTER, 1.0, 59),  # 50-59
            _close(_AFTER, 1.0, 60),  # 60-69
            _close(_AFTER, 1.0, 69),  # 60-69
            _close(_AFTER, 1.0, 70),  # 70-79
            _close(_AFTER, 1.0, 79),  # 70-79
            _close(_AFTER, 1.0, 80),  # 80+
            _close(_AFTER, 1.0, 100),  # 80+
        ]
        # Aucune cellule n'atteint 5 observations -> coverage_score = 0
        assert coverage_score(trades, []) == 0.0


class TestCoverageScore:
    def test_no_data_returns_zero(self):
        assert coverage_score([], []) == 0.0

    def test_single_regime_fully_covered(self):
        # 1 regime x 5 bins, chaque cellule >= 5 observations -> 100%
        trades = []
        for score in [45, 55, 65, 75, 90]:
            trades.extend(_close(_AFTER, 1.0, score) for _ in range(5))
        assert coverage_score(trades, []) == 100.0

    def test_single_regime_partially_covered(self):
        # 1 regime x 5 bins, seul 1 bin atteint le seuil -> 1/5 = 20%
        trades = [_close(_AFTER, 1.0, 45) for _ in range(5)]
        trades.append(_close(_AFTER, 1.0, 55))  # sous le seuil (1 < 5)
        assert coverage_score(trades, []) == 20.0

    def test_regrets_contribute_to_coverage(self):
        trades = [_close(_AFTER, 1.0, 45) for _ in range(3)]
        regrets = [_regret(_AFTER, 45) for _ in range(2)]
        # 3 + 2 = 5 observations dans la meme cellule -> couverte
        assert coverage_score(trades, regrets) == 20.0

    def test_second_regime_expands_denominator(self):
        # 2 regimes observes -> denominateur = 2*5 = 10 cellules
        trades = [_close(_AFTER, 1.0, 45, regime="sideways") for _ in range(5)]
        trades += [_close(_AFTER, 1.0, 45, regime="bull_trend") for _ in range(5)]
        # 2 cellules couvertes sur 10 -> 20%
        assert coverage_score(trades, []) == 20.0

    def test_unrecognized_regime_still_counted(self):
        """Un regime absent des taxonomies theoriques (ex. flash_crash) est
        neanmoins compte — c'est exactement le point de l'ADR-0011."""
        trades = [_close(_AFTER, 1.0, 45, regime="flash_crash") for _ in range(5)]
        assert coverage_score(trades, []) == 20.0  # 1 cellule / 5 bins


class TestDriftScore:
    def test_too_few_samples_returns_zero(self):
        trades = [_close(_AFTER, 1.0, 70) for _ in range(10)]  # < 2*MIN_PSI_SAMPLE
        assert drift_score(trades) == 0.0

    def test_identical_distribution_no_drift(self):
        # Memes scores repetes dans les deux moities -> PSI ~ 0 -> score ~ 100
        trades = [_close(_AFTER, 1.0, 70) for _ in range(40)]
        assert drift_score(trades) > 95.0

    def test_shifted_distribution_detects_drift(self):
        # Premiere moitie autour de 40, seconde autour de 90 -> forte divergence
        trades = [_close(_AFTER, 1.0, 40) for _ in range(20)]
        trades += [_close(_AFTER, 1.0, 95) for _ in range(20)]
        assert drift_score(trades) < 50.0


class TestBalanceScore:
    def test_zero_trades(self):
        assert balance_score([]) == 0.0

    def test_far_from_target(self):
        trades = [_close(_AFTER, 1.0, 70) for _ in range(3)]
        trades += [_close(_AFTER, -1.0, 70) for _ in range(3)]
        assert balance_score(trades) == 2.0  # min(3,3,150)=3 -> 100*3/150

    def test_at_target_both_sides(self):
        trades = [_close(_AFTER, 1.0, 70) for _ in range(150)]
        trades += [_close(_AFTER, -1.0, 70) for _ in range(150)]
        assert balance_score(trades) == 100.0

    def test_capped_by_smaller_side(self):
        # 200 winners, 150 losers -> plafonne a min(200,150,150)=150 -> 100%
        trades = [_close(_AFTER, 1.0, 70) for _ in range(200)]
        trades += [_close(_AFTER, -1.0, 70) for _ in range(150)]
        assert balance_score(trades) == 100.0

    def test_net_pnl_used_not_gross(self):
        """pnl_usd=0 compte comme gagnant (>=0), coherent avec
        mexc_simulator.py (wins = pnl_usd >= 0)."""
        trades = [_close(_AFTER, 0.0, 70), _close(_AFTER, -1.0, 70)]
        # 1 win (pnl=0), 1 loss -> min(1,1,150)=1 -> 100*1/150
        assert balance_score(trades) == 100.0 * 1 / 150


class TestComputeCriIntegration:
    def test_empty_dataset_zero_cri(self, tmp_path):
        trades_path = tmp_path / "paper_trades.jsonl"
        regret_path = tmp_path / "regret_analysis.jsonl"
        trades_path.write_text("", encoding="utf-8")
        regret_path.write_text("", encoding="utf-8")
        result = compute_cri(trades_path, regret_path)
        assert result["cri"] == 0.0
        assert result["gate_ready"] is False
        assert result["n_clean"] == 0

    def test_result_shape(self, tmp_path):
        trades_path = tmp_path / "paper_trades.jsonl"
        regret_path = tmp_path / "regret_analysis.jsonl"
        trades_path.write_text(
            json.dumps(_close(_AFTER, 1.0, 70)) + "\n", encoding="utf-8"
        )
        regret_path.write_text("", encoding="utf-8")
        result = compute_cri(trades_path, regret_path)
        assert set(result["sub_scores"]) == {
            "n_score",
            "coverage_score",
            "drift_score",
            "balance_score",
        }
        assert result["weights"] == {
            "n": 25.0,
            "coverage": 25.0,
            "drift": 25.0,
            "balance": 25.0,
        }
        assert result["clean_data_since"] == CLEAN_DATA_SINCE_V2.isoformat()

    def test_weights_sum_to_100(self):
        from tools.cri_calculator import WEIGHTS

        assert sum(WEIGHTS.values()) == 100.0

    def test_cri_never_exceeds_100(self, tmp_path):
        trades_path = tmp_path / "paper_trades.jsonl"
        regret_path = tmp_path / "regret_analysis.jsonl"
        lines = []
        for score in [45, 55, 65, 75, 90]:
            for _ in range(200):
                lines.append(json.dumps(_close(_AFTER, 1.0, score)))
        trades_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        regret_path.write_text("", encoding="utf-8")
        result = compute_cri(trades_path, regret_path)
        assert result["cri"] <= 100.0
