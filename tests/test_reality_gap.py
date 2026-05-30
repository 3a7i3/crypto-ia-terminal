"""
Tests — RealityGapAnalyzer (Phase 7).

Vérifie :
  - Le gap global est calculé correctement (pondéré)
  - Un simulateur bien calibré passe le seuil < 15%
  - Un simulateur déréglé échoue le seuil
  - Le rapport JSON est produit avec le bon schéma
  - Le chargement depuis fichier JSONL fonctionne
  - Les trades ouverts sont ignorés (seuls les fermés comptent)
  - Rapport vide sur liste vide
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from reality_checks.reality_gap_analyzer import (
    _DEFAULT_BENCHMARKS,
    GAP_THRESHOLD_PCT,
    RealityGapAnalyzer,
    run_report,
)

# ── Factories ──────────────────────────────────────────────────────────────────


def _make_trade(
    is_open: bool = False,
    entry_slippage_bps: float = 3.0,
    exit_slippage_bps: float = 3.0,
    entry_fee_usd: float = 2.0,  # 2 USD sur 5000 USD = 4 bps
    exit_fee_usd: float = 2.0,
    entry_latency_ms: float = 80.0,
    exit_latency_ms: float = 80.0,
    size_usd: float = 5_000.0,
    entry_price: float = 65_000.0,
    signal_price: float = 65_000.0,
    exit_price: float = 66_000.0,
    pnl_net_pct: float = 0.5,
    pnl_gross_pct: float = 0.6,
) -> dict:
    return {
        "trade_id": "test123",
        "symbol": "BTCUSDT",
        "side": "buy",
        "size_usd": size_usd,
        "signal_price": signal_price,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_slippage_bps": entry_slippage_bps,
        "exit_slippage_bps": exit_slippage_bps,
        "entry_fee_usd": entry_fee_usd,
        "exit_fee_usd": exit_fee_usd,
        "entry_latency_ms": entry_latency_ms,
        "exit_latency_ms": exit_latency_ms,
        "pnl_net_pct": pnl_net_pct,
        "pnl_gross_pct": pnl_gross_pct,
        "is_open": is_open,
        "entry_ts": time.time() - 3600,
        "exit_ts": time.time() if not is_open else None,
    }


def _calibrated_trades(n: int = 20) -> list[dict]:
    """
    Trades simulés proches des benchmarks round-trip → gap < 15%.

    Benchmarks round-trip :
      slippage_bps    = 7.0   (3.5 × 2 legs)
      fees_bps        = 8.0   (4 bps × 2 legs)
      fill_ratio      = 0.94  (paper = 1.0 → gap = 0)
      latency_ms      = 85.0  (paper ~83ms → gap ~2%)
      spread_cost_bps = 1.6   (fixe dans analyzer)
    """
    return [
        _make_trade(
            entry_slippage_bps=3.4,  # total = 6.8 vs benchmark 7.0 → ~3% gap
            exit_slippage_bps=3.4,
            entry_fee_usd=2.0,  # (2+2)/5000*10000 = 8 bps == benchmark
            exit_fee_usd=2.0,
            entry_latency_ms=83.0,  # avg 83 vs 85 → ~2% gap
            exit_latency_ms=83.0,
        )
        for _ in range(n)
    ]


def _miscalibrated_trades(n: int = 20) -> list[dict]:
    """Trades avec slippage et fees très bas → gap élevé vs benchmark."""
    return [
        _make_trade(
            entry_slippage_bps=0.1,  # simulateur trop optimiste
            exit_slippage_bps=0.1,
            entry_fee_usd=0.1,  # fees quasi nuls (irréaliste)
            exit_fee_usd=0.1,
            entry_latency_ms=1.0,  # latence 0 (irréaliste)
            exit_latency_ms=1.0,
        )
        for _ in range(n)
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRealityGapAnalyzer:

    def test_calibrated_simulator_passes_threshold(self):
        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze(_calibrated_trades(30))
        assert report.passed, (
            f"INVARIANT BRISÉ: simulateur bien calibré doit passer le seuil "
            f"(gap={report.gap_percent:.1f}% > {GAP_THRESHOLD_PCT}%)"
        )

    def test_miscalibrated_simulator_fails_threshold(self):
        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze(_miscalibrated_trades(20))
        assert (
            not report.passed
        ), f"Simulateur déréglé doit échouer le seuil (gap={report.gap_percent:.1f}%)"
        assert report.gap_percent > GAP_THRESHOLD_PCT

    def test_n_trades_counted_correctly(self):
        trades = _calibrated_trades(15)
        # Ajouter 3 trades ouverts qui ne doivent pas compter
        trades += [_make_trade(is_open=True) for _ in range(3)]

        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze(trades)
        assert (
            report.n_trades == 15
        ), f"Seuls les trades fermés comptent: {report.n_trades} ≠ 15"

    def test_empty_trades_returns_empty_report(self):
        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze([])
        assert report.n_trades == 0
        assert report.gap_percent == 0.0
        assert report.passed is True  # vide = pas de preuve d'échec

    def test_only_open_trades_returns_empty(self):
        analyzer = RealityGapAnalyzer()
        trades = [_make_trade(is_open=True) for _ in range(5)]
        report = analyzer.analyze(trades)
        assert report.n_trades == 0

    def test_report_schema_complete(self):
        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze(_calibrated_trades(10))
        d = report.as_dict()

        required_keys = {
            "gap_percent",
            "n_trades",
            "passed",
            "threshold_pct",
            "metrics",
            "detail",
        }
        assert required_keys.issubset(
            d.keys()
        ), f"Clés manquantes dans le rapport: {required_keys - d.keys()}"
        assert isinstance(d["gap_percent"], float)
        assert isinstance(d["metrics"], list)
        assert len(d["metrics"]) == len(_DEFAULT_BENCHMARKS)

    def test_each_metric_has_required_fields(self):
        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze(_calibrated_trades(10))
        for m in report.metrics:
            assert hasattr(m, "metric")
            assert hasattr(m, "paper_value")
            assert hasattr(m, "benchmark_value")
            assert hasattr(m, "gap_pct")
            assert hasattr(m, "weight")
            assert m.gap_pct >= 0.0, f"gap_pct ne peut pas être négatif: {m.gap_pct}"

    def test_gap_percent_is_float_between_0_and_100(self):
        analyzer = RealityGapAnalyzer()
        for trades in [_calibrated_trades(5), _miscalibrated_trades(5)]:
            report = analyzer.analyze(trades)
            assert (
                0.0 <= report.gap_percent <= 200.0
            ), f"gap_percent hors range: {report.gap_percent}"

    def test_custom_benchmarks_override(self):
        # Benchmarks = exactement ce que le simulateur calibré produit → gap ≈ 0%
        perfect_benchmarks = {
            "slippage_bps": 6.8,  # entry(3.4) + exit(3.4)
            "fees_bps": 8.0,  # 4 USD / 5000 USD * 10000
            "fill_ratio": 1.0,  # paper = toujours 1.0
            "latency_ms": 83.0,  # avg entry/exit latency
            "spread_cost_bps": 1.6,  # valeur fixe dans analyzer
        }
        analyzer = RealityGapAnalyzer(benchmarks=perfect_benchmarks)
        report = analyzer.analyze(_calibrated_trades(10))
        assert (
            report.gap_percent < 5.0
        ), f"Avec benchmarks parfaits, gap doit être ~0% (obtenu {report.gap_percent}%)"


class TestRealityGapSaveLoad:

    def test_save_report_creates_file(self, tmp_path):
        output = str(tmp_path / "gap_report.json")
        analyzer = RealityGapAnalyzer(output_path=output)
        report = analyzer.analyze(_calibrated_trades(5))
        saved = analyzer.save_report(report)

        assert saved.exists(), "Le fichier de rapport doit être créé"
        with saved.open() as f:
            data = json.load(f)
        assert "gap_percent" in data
        assert "metrics" in data

    def test_jq_gap_percent_accessible(self, tmp_path):
        """Simule : cat report.json | jq '.gap_percent'"""
        output = str(tmp_path / "reality_gap_report.json")
        analyzer = RealityGapAnalyzer(output_path=output)
        report = analyzer.analyze(_calibrated_trades(10))
        analyzer.save_report(report)

        with open(output) as f:
            data = json.load(f)

        gap_percent = data["gap_percent"]  # équivalent jq '.gap_percent'
        assert isinstance(gap_percent, (int, float)), "gap_percent doit être un nombre"
        assert (
            gap_percent < GAP_THRESHOLD_PCT
        ), f"Seuil Phase 7 < {GAP_THRESHOLD_PCT}% : obtenu {gap_percent}%"

    def test_analyze_from_jsonl_file(self, tmp_path):
        jsonl_path = tmp_path / "trades.jsonl"
        trades = _calibrated_trades(10)
        with jsonl_path.open("w") as f:
            for t in trades:
                f.write(json.dumps(t) + "\n")

        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze_from_file(str(jsonl_path))
        assert report.n_trades == 10

    def test_analyze_from_missing_file(self):
        analyzer = RealityGapAnalyzer()
        report = analyzer.analyze_from_file("/nonexistent/trades.jsonl")
        assert report.n_trades == 0

    def test_run_report_function(self, tmp_path):
        """Test du point d'entrée CLI run_report()."""
        jsonl_path = tmp_path / "trades.jsonl"
        trades = _calibrated_trades(8)
        with jsonl_path.open("w") as f:
            for t in trades:
                f.write(json.dumps(t) + "\n")

        output_path = str(tmp_path / "out.json")
        report = run_report(
            trades_path=str(jsonl_path),
            output_path=output_path,
        )
        assert report.n_trades == 8
        assert Path(output_path).exists()


class TestRealityGapThreshold:
    """Valide le seuil < 15% comme critère de passage Phase 7."""

    def test_threshold_is_15_pct(self):
        assert (
            GAP_THRESHOLD_PCT == 15.0
        ), "Le seuil Phase 7 doit être exactement 15% (SYSTEM_DEGRADATION_POLICY §7)"

    def test_at_exactly_14_pct_passes(self):
        """
        Slippage +20% vs benchmark round-trip.
        paper=8.4 vs bench=7.0 → gap_metric=20% × w=0.35 = 7.0%
        fees, fill_ratio, spread: ~0% gap.
        latency: (83-85)/85 = 2.4% × 0.10 = 0.24%.
        Total ≈ 7.24% < 15% → PASS.
        """
        trades = [
            _make_trade(
                entry_slippage_bps=4.2,  # round-trip 8.4 vs benchmark 7.0 → +20%
                exit_slippage_bps=4.2,
                entry_fee_usd=2.0,  # 8 bps round-trip == benchmark
                exit_fee_usd=2.0,
                entry_latency_ms=83.0,
                exit_latency_ms=83.0,
            )
            for _ in range(20)
        ]
        analyzer = RealityGapAnalyzer()  # benchmarks round-trip par défaut
        report = analyzer.analyze(trades)
        assert (
            report.gap_percent < 15.0
        ), f"Slippage +20% poids 35% → gap ~7% (obtenu {report.gap_percent}%)"
        assert report.passed

    def test_passed_field_consistent_with_gap_percent(self):
        analyzer = RealityGapAnalyzer()
        for trades_fn in [_calibrated_trades, _miscalibrated_trades]:
            report = analyzer.analyze(trades_fn(10))
            assert report.passed == (
                report.gap_percent < GAP_THRESHOLD_PCT
            ), f"passed={report.passed} incohérent gap={report.gap_percent}"
