"""
Tests — system/state_integrity.py + integrity_rules.py + integrity_models.py

Couverture :
  - IntegrityReport.score et severity
  - check_signal_integrity : stale_lock, future_timestamp
  - check_position_integrity : stats/snapshot mismatch, brain/manager, over_exposed
  - check_capital_integrity : zero capital, free > total, ghost exposure
  - check_temporal_integrity : stale cooldown, rate limit
  - check_order_integrity : pending sans position
  - StateSnapshot.compute_hash : déterministe, normalisé
  - StateIntegrityAudit.run : intégration complète
  - StateIntegrityAudit.blocks_trading : score < 50
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from system.integrity_models import (
    IntegrityDomain,
    IntegrityIssue,
    IntegrityLevel,
    IntegrityReport,
    IntegritySeverity,
)
from system.integrity_rules import (
    check_capital_integrity,
    check_order_integrity,
    check_position_integrity,
    check_signal_integrity,
    check_temporal_integrity,
)
from system.integrity_snapshot import StateSnapshot
from system.state_integrity import StateIntegrityAudit

# ── Helpers ────────────────────────────────────────────────────────────────────


def _clean_snap(**overrides) -> StateSnapshot:
    now = time.time()
    defaults = dict(
        captured_at=now,
        cycle=1,
        last_trade_signal={},
        last_loss_timestamps={},
        trades_this_hour={},
        open_positions_local=[],
        open_count_stats=0,
        open_pnl_usd=0.0,
        total_pnl_usd=0.0,
        win_rate=0.0,
        real_capital=4572.0,
        portfolio_free_capital=1828.0,
        portfolio_exposure_pct=0.0,
        portfolio_n_positions=0,
        pending_order_count=0,
    )
    defaults.update(overrides)
    return StateSnapshot(**defaults)


def _mock_pos_manager(open_count=0, snapshot_list=None, pnl=0.0):
    pm = MagicMock()
    pm.stats.return_value = {
        "open_count": open_count,
        "closed_count": 7,
        "total_pnl_usd": pnl,
        "win_rate": 0.0,
        "open_pnl_usd": 0.0,
    }
    pm.snapshot.return_value = snapshot_list or []
    pm.get_open.return_value = []
    return pm


def _mock_portfolio_brain(free=1828.0, exposure=0.0, n=0, capital=4572.0):
    pb = MagicMock()
    pb.portfolio_health.return_value = {
        "free_capital": free,
        "total_exposure_pct": exposure,
        "n_positions": n,
        "capital": capital,
    }
    return pb


# ── IntegrityReport ────────────────────────────────────────────────────────────


class TestIntegrityReport:
    def test_score_100_when_clean(self):
        r = IntegrityReport(cycle=1, issues=[], state_hash="abc")
        assert r.score == 100
        assert r.is_clean
        assert r.is_safe
        assert r.severity == IntegritySeverity.OK

    def test_score_decreases_by_severity(self):
        w = IntegrityIssue("r1", IntegritySeverity.WARNING, "d", "i", "o", "signal")
        d = IntegrityIssue("r2", IntegritySeverity.DEGRADED, "d", "i", "o", "capital")
        u = IntegrityIssue("r3", IntegritySeverity.UNSAFE, "d", "i", "o", "position")
        r = IntegrityReport(cycle=1, issues=[w, d, u])
        assert r.score == max(0, 100 - 5 - 15 - 30)  # = 50
        assert r.severity == IntegritySeverity.UNSAFE
        # v1.1 : is_safe=False seulement si level UNSAFE ou HALTED (score < 50)
        # score=50 → RESTRICTED → is_safe=True, mais pas is_clean
        assert r.level == IntegrityLevel.RESTRICTED
        assert r.is_safe  # score=50 est à la frontière — encore "safe" en v1.1
        assert not r.is_clean

    def test_score_floor_zero(self):
        issues = [
            IntegrityIssue(f"r{i}", IntegritySeverity.UNSAFE, "d", "i", "o", "capital")
            for i in range(5)
        ]
        r = IntegrityReport(cycle=1, issues=issues)
        assert r.score == 0

    def test_by_category(self):
        issues = [
            IntegrityIssue("r1", IntegritySeverity.WARNING, "d", "i", "o", "signal"),
            IntegrityIssue("r2", IntegritySeverity.DEGRADED, "d", "i", "o", "signal"),
            IntegrityIssue("r3", IntegritySeverity.WARNING, "d", "i", "o", "capital"),
        ]
        r = IntegrityReport(cycle=1, issues=issues)
        assert len(r.by_category["signal"]) == 2
        assert len(r.by_category["capital"]) == 1

    def test_summary_line_clean(self):
        r = IntegrityReport(cycle=5, issues=[], state_hash="deadbeef1234")
        line = r.summary_line()
        assert "CLEAN" in line
        assert "100" in line
        assert "deadbeef" in line

    def test_summary_line_with_issues(self):
        issues = [
            IntegrityIssue("r1", IntegritySeverity.DEGRADED, "d", "i", "o", "capital"),
        ]
        r = IntegrityReport(cycle=3, issues=issues, state_hash="abcd1234")
        line = r.summary_line()
        assert "DEGRADED" in line
        assert "capital(1)" in line


# ── check_signal_integrity ─────────────────────────────────────────────────────


class TestSignalIntegrity:
    def test_clean_when_no_signals(self):
        snap = _clean_snap()
        assert check_signal_integrity(snap) == []

    def test_stale_lock_no_position_no_cooldown(self):
        now = time.time()
        snap = _clean_snap(
            last_trade_signal={"SOL/USDT": "SELL"},
            last_loss_timestamps={"SOL/USDT": now - 400},  # cooldown expired (> 300s)
            open_positions_local=[],
        )
        issues = check_signal_integrity(snap)
        assert any(i.rule == "signal.stale_lock" for i in issues)

    def test_no_stale_lock_when_position_open(self):
        now = time.time()
        snap = _clean_snap(
            last_trade_signal={"SOL/USDT": "SELL"},
            last_loss_timestamps={"SOL/USDT": now - 400},
            open_positions_local=[
                {"symbol": "SOL/USDT", "side": "sell", "size_usd": 100.0}
            ],
            open_count_stats=1,
        )
        issues = check_signal_integrity(snap)
        assert not any(i.rule == "signal.stale_lock" for i in issues)

    def test_no_stale_lock_when_cooldown_active(self):
        now = time.time()
        snap = _clean_snap(
            last_trade_signal={"SOL/USDT": "SELL"},
            last_loss_timestamps={
                "SOL/USDT": now - 100
            },  # cooldown still active (< 300s)
            open_positions_local=[],
        )
        issues = check_signal_integrity(snap)
        assert not any(i.rule == "signal.stale_lock" for i in issues)

    def test_future_timestamp_is_unsafe(self):
        now = time.time()
        snap = _clean_snap(
            last_loss_timestamps={"XRP/USDT": now + 3600},
        )
        issues = check_signal_integrity(snap)
        assert any(
            i.rule == "signal.future_timestamp"
            and i.severity == IntegritySeverity.UNSAFE
            for i in issues
        )


# ── check_position_integrity ───────────────────────────────────────────────────


class TestPositionIntegrity:
    def test_clean_when_consistent(self):
        snap = _clean_snap()
        assert check_position_integrity(snap) == []

    def test_stats_snapshot_mismatch(self):
        snap = _clean_snap(
            open_count_stats=2,
            open_positions_local=[
                {"symbol": "SOL/USDT", "side": "sell", "size_usd": 100.0}
            ],
        )
        issues = check_position_integrity(snap)
        assert any(i.rule == "position.stats_snapshot_mismatch" for i in issues)

    def test_brain_manager_mismatch(self):
        snap = _clean_snap(
            open_count_stats=1,
            open_positions_local=[
                {"symbol": "SOL/USDT", "side": "sell", "size_usd": 100.0}
            ],
            portfolio_n_positions=0,
        )
        issues = check_position_integrity(snap)
        assert any(i.rule == "position.brain_manager_mismatch" for i in issues)

    def test_over_exposed_is_unsafe(self):
        snap = _clean_snap(
            real_capital=100.0,
            open_positions_local=[
                {"symbol": "BTC/USDT", "side": "buy", "size_usd": 110.0}
            ],
            open_count_stats=1,
        )
        issues = check_position_integrity(snap)
        assert any(
            i.rule == "position.over_exposed" and i.severity == IntegritySeverity.UNSAFE
            for i in issues
        )


# ── check_capital_integrity ────────────────────────────────────────────────────


class TestCapitalIntegrity:
    def test_clean_normal_state(self):
        snap = _clean_snap()
        assert check_capital_integrity(snap) == []

    def test_zero_capital_is_unsafe(self):
        snap = _clean_snap(real_capital=0.0)
        issues = check_capital_integrity(snap)
        assert any(
            i.rule == "capital.zero_or_negative"
            and i.severity == IntegritySeverity.UNSAFE
            for i in issues
        )

    def test_free_exceeds_total_is_unsafe(self):
        snap = _clean_snap(real_capital=1000.0, portfolio_free_capital=1100.0)
        issues = check_capital_integrity(snap)
        assert any(
            i.rule == "capital.free_exceeds_total"
            and i.severity == IntegritySeverity.UNSAFE
            for i in issues
        )

    def test_ghost_exposure_with_zero_positions(self):
        snap = _clean_snap(
            open_count_stats=0,
            portfolio_exposure_pct=0.15,
        )
        issues = check_capital_integrity(snap)
        assert any(i.rule == "capital.ghost_exposure" for i in issues)

    def test_no_ghost_exposure_when_positions_open(self):
        snap = _clean_snap(
            open_count_stats=1,
            portfolio_exposure_pct=0.10,
        )
        issues = check_capital_integrity(snap)
        assert not any(i.rule == "capital.ghost_exposure" for i in issues)


# ── check_temporal_integrity ───────────────────────────────────────────────────


class TestTemporalIntegrity:
    def test_clean(self):
        snap = _clean_snap()
        assert check_temporal_integrity(snap) == []

    def test_stale_cooldown_entry(self):
        now = time.time()
        snap = _clean_snap(
            last_loss_timestamps={"SOL/USDT": now - 7200},  # 2h ago
        )
        issues = check_temporal_integrity(snap)
        assert any(i.rule == "temporal.stale_cooldown_entry" for i in issues)

    def test_recent_loss_not_stale(self):
        now = time.time()
        snap = _clean_snap(
            last_loss_timestamps={"SOL/USDT": now - 1800},  # 30min ago
        )
        issues = check_temporal_integrity(snap)
        assert not any(i.rule == "temporal.stale_cooldown_entry" for i in issues)

    def test_rate_limit_hit(self):
        snap = _clean_snap(trades_this_hour={"SOL/USDT": 10})
        issues = check_temporal_integrity(snap)
        assert any(i.rule == "temporal.rate_limit_hit" for i in issues)

    def test_below_rate_limit_clean(self):
        snap = _clean_snap(trades_this_hour={"SOL/USDT": 9})
        issues = check_temporal_integrity(snap)
        assert not any(i.rule == "temporal.rate_limit_hit" for i in issues)


# ── check_order_integrity ──────────────────────────────────────────────────────


class TestOrderIntegrity:
    def test_clean(self):
        snap = _clean_snap()
        assert check_order_integrity(snap) == []

    def test_pending_without_position(self):
        snap = _clean_snap(pending_order_count=2, open_count_stats=0)
        issues = check_order_integrity(snap)
        assert any(i.rule == "order.pending_without_position" for i in issues)

    def test_pending_with_position_ok(self):
        snap = _clean_snap(pending_order_count=1, open_count_stats=1)
        issues = check_order_integrity(snap)
        assert not any(i.rule == "order.pending_without_position" for i in issues)


# ── StateSnapshot.compute_hash ─────────────────────────────────────────────────


class TestStateSnapshotHash:
    def test_identical_snapshots_same_hash(self):
        now = time.time()
        s1 = _clean_snap(captured_at=now)
        s2 = _clean_snap(captured_at=now + 1)  # timestamp différent, état identique
        assert s1.compute_hash() == s2.compute_hash()

    def test_different_state_different_hash(self):
        s1 = _clean_snap(real_capital=4572.0)
        s2 = _clean_snap(real_capital=4000.0)
        assert s1.compute_hash() != s2.compute_hash()

    def test_hash_length_16(self):
        snap = _clean_snap()
        assert len(snap.compute_hash()) == 16

    def test_position_order_irrelevant(self):
        pos_a = {"symbol": "A/USDT", "side": "buy", "size_usd": 100.0}
        pos_b = {"symbol": "B/USDT", "side": "sell", "size_usd": 200.0}
        s1 = _clean_snap(open_positions_local=[pos_a, pos_b])
        s2 = _clean_snap(open_positions_local=[pos_b, pos_a])
        assert s1.compute_hash() == s2.compute_hash()


# ── StateSnapshot.capture ──────────────────────────────────────────────────────


class TestStateSnapshotCapture:
    def test_capture_with_mocks(self):
        pm = _mock_pos_manager(
            open_count=1,
            snapshot_list=[{"symbol": "SOL/USDT", "side": "sell", "size_usd": 120.0}],
        )
        pb = _mock_portfolio_brain(free=1000.0, exposure=0.05, n=1)
        snap = StateSnapshot.capture(
            cycle=10,
            real_capital=4572.0,
            last_trade_signal={"SOL/USDT": "SELL"},
            last_loss_time={},
            trades_this_hour={"SOL/USDT": [time.time() - 60, time.time() - 30]},
            pos_manager=pm,
            portfolio_brain=pb,
        )
        assert snap.cycle == 10
        assert snap.real_capital == 4572.0
        assert snap.open_count_stats == 1
        assert snap.portfolio_free_capital == 1000.0
        assert snap.trades_this_hour["SOL/USDT"] == 2
        assert len(snap.open_positions_local) == 1

    def test_capture_tolerates_none_managers(self):
        snap = StateSnapshot.capture(
            cycle=1,
            real_capital=4572.0,
            last_trade_signal={},
            last_loss_time={},
            trades_this_hour={},
            pos_manager=None,
            portfolio_brain=None,
        )
        assert snap.real_capital == 4572.0
        assert snap.open_count_stats == 0

    def test_trades_this_hour_counts_only_recent(self):
        now = time.time()
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        snap = StateSnapshot.capture(
            cycle=1,
            real_capital=4572.0,
            last_trade_signal={},
            last_loss_time={},
            trades_this_hour={
                "SOL/USDT": [now - 7200, now - 60, now - 30]  # 1 stale, 2 recent
            },
            pos_manager=pm,
            portfolio_brain=pb,
        )
        assert snap.trades_this_hour["SOL/USDT"] == 2


# ── StateIntegrityAudit — intégration ─────────────────────────────────────────


class TestStateIntegrityAudit:
    def test_run_clean_state(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        report = audit.run(
            cycle=5,
            real_capital=4572.0,
            last_trade_signal={},
            last_loss_time={},
            trades_this_hour={},
            pos_manager=pm,
            portfolio_brain=pb,
        )
        assert report.is_clean
        assert report.score == 100

    def test_run_detects_stale_lock(self, tmp_path):
        now = time.time()
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager(open_count=0)
        pb = _mock_portfolio_brain()
        report = audit.run(
            cycle=5,
            real_capital=4572.0,
            last_trade_signal={"SOL/USDT": "SELL"},
            last_loss_time={"SOL/USDT": now - 400},
            trades_this_hour={},
            pos_manager=pm,
            portfolio_brain=pb,
        )
        assert not report.is_clean
        assert any(i.rule == "signal.stale_lock" for i in report.issues)

    def test_blocks_trading_below_threshold(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        issues = [
            IntegrityIssue(f"r{i}", IntegritySeverity.UNSAFE, "d", "i", "o", "capital")
            for i in range(3)
        ]
        report = IntegrityReport(cycle=1, issues=issues)
        assert report.score < 50
        assert audit.blocks_trading(report)

    def test_should_run_every_n(self):
        audit = StateIntegrityAudit(every_n_cycles=5)
        assert audit.should_run(5)
        assert audit.should_run(10)
        assert not audit.should_run(3)
        assert not audit.should_run(7)

    def test_persists_to_file(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        audit = StateIntegrityAudit(log_path=log_path)
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        audit.run(
            cycle=1,
            real_capital=4572.0,
            last_trade_signal={},
            last_loss_time={},
            trades_this_hour={},
            pos_manager=pm,
            portfolio_brain=pb,
        )
        assert log_path.exists()
        import json

        line = json.loads(log_path.read_text().strip())
        assert line["cycle"] == 1
        assert "score" in line

    def test_consecutive_issue_cycles_tracking(self, tmp_path):
        now = time.time()
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()

        for _ in range(3):
            audit.run(
                cycle=5,
                real_capital=4572.0,
                last_trade_signal={"SOL/USDT": "SELL"},
                last_loss_time={"SOL/USDT": now - 400},
                trades_this_hour={},
                pos_manager=pm,
                portfolio_brain=pb,
            )
        assert audit.consecutive_issue_cycles == 3

        audit.run(
            cycle=5,
            real_capital=4572.0,
            last_trade_signal={},
            last_loss_time={},
            trades_this_hour={},
            pos_manager=pm,
            portfolio_brain=pb,
        )
        assert audit.consecutive_issue_cycles == 0

    def test_telegram_summary_format(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        issues = [
            IntegrityIssue(
                "capital.ghost_exposure",
                IntegritySeverity.DEGRADED,
                "exposition fantôme détectée",
                "exposure=0",
                "exposure=15%",
                "capital",
            ),
        ]
        report = IntegrityReport(cycle=3, issues=issues)
        msg = audit.telegram_summary(report)
        assert "DEGRADED" in msg or "capital.ghost_exposure" in msg


# ── IntegrityDomain ────────────────────────────────────────────────────────────


class TestIntegrityDomain:
    def test_all_five_domains_exist(self):
        expected = {"signal", "position", "capital", "temporal", "order"}
        assert {d.value for d in IntegrityDomain} == expected

    def test_domain_values_match_categories(self):
        assert IntegrityDomain.SIGNAL.value == "signal"
        assert IntegrityDomain.CAPITAL.value == "capital"
        assert IntegrityDomain.ORDER.value == "order"


# ── IntegrityLevel ─────────────────────────────────────────────────────────────


class TestIntegrityLevel:
    def test_normal_at_100(self):
        assert IntegrityLevel.from_score(100) == IntegrityLevel.NORMAL

    def test_normal_at_80(self):
        assert IntegrityLevel.from_score(80) == IntegrityLevel.NORMAL

    def test_degraded_at_79(self):
        assert IntegrityLevel.from_score(79) == IntegrityLevel.DEGRADED

    def test_degraded_at_65(self):
        assert IntegrityLevel.from_score(65) == IntegrityLevel.DEGRADED

    def test_restricted_at_64(self):
        assert IntegrityLevel.from_score(64) == IntegrityLevel.RESTRICTED

    def test_restricted_at_50(self):
        assert IntegrityLevel.from_score(50) == IntegrityLevel.RESTRICTED

    def test_unsafe_at_49(self):
        assert IntegrityLevel.from_score(49) == IntegrityLevel.UNSAFE

    def test_unsafe_at_25(self):
        assert IntegrityLevel.from_score(25) == IntegrityLevel.UNSAFE

    def test_halted_at_24(self):
        assert IntegrityLevel.from_score(24) == IntegrityLevel.HALTED

    def test_halted_at_0(self):
        assert IntegrityLevel.from_score(0) == IntegrityLevel.HALTED


# ── IntegrityReport.level ──────────────────────────────────────────────────────


class TestIntegrityReportLevel:
    def test_normal_when_clean(self):
        r = IntegrityReport(cycle=1, issues=[], state_hash="abc")
        assert r.level == IntegrityLevel.NORMAL

    def test_halted_when_score_zero(self):
        issues = [
            IntegrityIssue(f"r{i}", IntegritySeverity.UNSAFE, "d", "i", "o", "capital")
            for i in range(5)  # 5×30 = 150 → capped at 0
        ]
        r = IntegrityReport(cycle=1, issues=issues)
        assert r.score == 0
        assert r.level == IntegrityLevel.HALTED

    def test_restricted_at_score_50(self):
        # 1 UNSAFE (−30) + 1 DEGRADED (−15) + 1 WARNING (−5) = −50 → score 50
        issues = [
            IntegrityIssue("r1", IntegritySeverity.UNSAFE, "d", "i", "o", "capital"),
            IntegrityIssue("r2", IntegritySeverity.DEGRADED, "d", "i", "o", "position"),
            IntegrityIssue("r3", IntegritySeverity.WARNING, "d", "i", "o", "signal"),
        ]
        r = IntegrityReport(cycle=1, issues=issues)
        assert r.score == 50
        assert r.level == IntegrityLevel.RESTRICTED

    def test_is_safe_false_only_for_unsafe_halted(self):
        # RESTRICTED (score=50) → is_safe=True (still above block threshold)
        issues_restricted = [
            IntegrityIssue("r1", IntegritySeverity.UNSAFE, "d", "i", "o", "capital"),
            IntegrityIssue("r2", IntegritySeverity.DEGRADED, "d", "i", "o", "position"),
            IntegrityIssue("r3", IntegritySeverity.WARNING, "d", "i", "o", "signal"),
        ]
        r = IntegrityReport(cycle=1, issues=issues_restricted)
        assert r.level == IntegrityLevel.RESTRICTED
        assert r.is_safe  # still safe at exactly 50

        # UNSAFE (score=40 → 2 UNSAFEs = −60, oh wait that's 40 → UNSAFE)
        issues_unsafe = [
            IntegrityIssue("r1", IntegritySeverity.UNSAFE, "d", "i", "o", "capital"),
            IntegrityIssue("r2", IntegritySeverity.UNSAFE, "d", "i", "o", "position"),
        ]
        r2 = IntegrityReport(cycle=1, issues=issues_unsafe)
        assert r2.score == 40
        assert r2.level == IntegrityLevel.UNSAFE
        assert not r2.is_safe


# ── IntegrityReport.primary_failure ───────────────────────────────────────────


class TestIntegrityReportPrimaryFailure:
    def test_none_when_clean(self):
        r = IntegrityReport(cycle=1, issues=[])
        assert r.primary_failure is None

    def test_returns_worst_severity(self):
        w = IntegrityIssue("r1", IntegritySeverity.WARNING, "d", "i", "o", "signal")
        u = IntegrityIssue("r2", IntegritySeverity.UNSAFE, "d", "i", "o", "capital")
        d = IntegrityIssue("r3", IntegritySeverity.DEGRADED, "d", "i", "o", "temporal")
        r = IntegrityReport(cycle=1, issues=[w, u, d])
        assert r.primary_failure == u

    def test_single_issue_is_primary(self):
        iss = IntegrityIssue("r1", IntegritySeverity.DEGRADED, "d", "i", "o", "order")
        r = IntegrityReport(cycle=1, issues=[iss])
        assert r.primary_failure == iss


# ── IntegrityReport.domain_health ─────────────────────────────────────────────


class TestIntegrityReportDomainHealth:
    def test_all_100_when_clean(self):
        r = IntegrityReport(cycle=1, issues=[])
        dh = r.domain_health
        assert all(v == 100 for v in dh.values())
        assert set(dh.keys()) == {"signal", "position", "capital", "temporal", "order"}

    def test_capital_penalized_others_intact(self):
        iss = IntegrityIssue(
            "capital.zero",
            IntegritySeverity.UNSAFE,
            "capital nul",
            "capital > 0",
            "capital=0",
            "capital",
        )
        r = IntegrityReport(cycle=1, issues=[iss])
        dh = r.domain_health
        assert dh["capital"] == 70  # 100 - 30
        assert dh["signal"] == 100
        assert dh["position"] == 100

    def test_multiple_domains_penalized_independently(self):
        issues = [
            IntegrityIssue(
                "r1", IntegritySeverity.WARNING, "d", "i", "o", "signal"
            ),  # -5
            IntegrityIssue(
                "r2", IntegritySeverity.DEGRADED, "d", "i", "o", "position"
            ),  # -15
            IntegrityIssue(
                "r3", IntegritySeverity.UNSAFE, "d", "i", "o", "capital"
            ),  # -30
        ]
        r = IntegrityReport(cycle=1, issues=issues)
        dh = r.domain_health
        assert dh["signal"] == 95
        assert dh["position"] == 85
        assert dh["capital"] == 70
        assert dh["temporal"] == 100
        assert dh["order"] == 100

    def test_domain_health_floor_zero(self):
        issues = [
            IntegrityIssue(f"r{i}", IntegritySeverity.UNSAFE, "d", "i", "o", "capital")
            for i in range(5)  # 5 × 30 = 150 → capped at 0
        ]
        r = IntegrityReport(cycle=1, issues=issues)
        assert r.domain_health["capital"] == 0


# ── Issue enrichment (trace_id / cycle_id / snapshot_hash) ────────────────────


class TestIssueEnrichment:
    def _run_with_stale_lock(self, tmp_path):
        now = time.time()
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager(open_count=0)
        pb = _mock_portfolio_brain()
        return audit.run(
            cycle=42,
            real_capital=4572.0,
            last_trade_signal={"SOL/USDT": "SELL"},
            last_loss_time={"SOL/USDT": now - 400},
            trades_this_hour={},
            pos_manager=pm,
            portfolio_brain=pb,
        )

    def test_issues_have_cycle_id(self, tmp_path):
        report = self._run_with_stale_lock(tmp_path)
        assert report.issues
        for issue in report.issues:
            assert issue.cycle_id == 42

    def test_issues_have_snapshot_hash(self, tmp_path):
        report = self._run_with_stale_lock(tmp_path)
        assert report.issues
        for issue in report.issues:
            assert len(issue.snapshot_hash) == 16  # SHA-256[:16]
            assert issue.snapshot_hash == report.state_hash

    def test_issue_snapshot_hash_matches_report_hash(self, tmp_path):
        report = self._run_with_stale_lock(tmp_path)
        for issue in report.issues:
            assert issue.snapshot_hash == report.state_hash

    def test_persisted_dict_includes_new_fields(self, tmp_path):
        import json

        log_path = tmp_path / "audit.jsonl"
        audit = StateIntegrityAudit(log_path=log_path)
        now = time.time()
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        audit.run(
            cycle=7,
            real_capital=4572.0,
            last_trade_signal={"BTC/USDT": "BUY"},
            last_loss_time={"BTC/USDT": now - 400},
            trades_this_hour={},
            pos_manager=pm,
            portfolio_brain=pb,
        )
        line = json.loads(log_path.read_text().strip())
        assert "level" in line
        assert "domain_health" in line
        assert "primary_failure" in line


# ── Integrity trend analytics ──────────────────────────────────────────────────


class TestIntegrityTrend:
    def test_rolling_score_none_before_first_audit(self):
        audit = StateIntegrityAudit()
        assert audit.integrity_score_rolling_50 is None

    def test_rolling_score_after_clean_runs(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        for c in range(3):
            audit.run(
                cycle=c,
                real_capital=4572.0,
                last_trade_signal={},
                last_loss_time={},
                trades_this_hour={},
                pos_manager=pm,
                portfolio_brain=pb,
            )
        assert audit.integrity_score_rolling_50 == 100.0

    def test_issue_frequency_zero_when_always_clean(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        for c in range(5):
            audit.run(
                cycle=c,
                real_capital=4572.0,
                last_trade_signal={},
                last_loss_time={},
                trades_this_hour={},
                pos_manager=pm,
                portfolio_brain=pb,
            )
        assert audit.integrity_issue_frequency == 0.0

    def test_issue_frequency_nonzero_when_issues(self, tmp_path):
        now = time.time()
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm_clean = _mock_pos_manager()
        pm_dirty = _mock_pos_manager(open_count=0)
        pb = _mock_portfolio_brain()

        # 2 clean + 2 dirty
        for _ in range(2):
            audit.run(
                cycle=1,
                real_capital=4572.0,
                last_trade_signal={},
                last_loss_time={},
                trades_this_hour={},
                pos_manager=pm_clean,
                portfolio_brain=pb,
            )
        for _ in range(2):
            audit.run(
                cycle=1,
                real_capital=4572.0,
                last_trade_signal={"SOL/USDT": "SELL"},
                last_loss_time={"SOL/USDT": now - 400},
                trades_this_hour={},
                pos_manager=pm_dirty,
                portfolio_brain=pb,
            )

        assert audit.integrity_issue_frequency == 0.5

    def test_score_history_max_50(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        pm = _mock_pos_manager()
        pb = _mock_portfolio_brain()
        for c in range(60):
            audit.run(
                cycle=c,
                real_capital=4572.0,
                last_trade_signal={},
                last_loss_time={},
                trades_this_hour={},
                pos_manager=pm,
                portfolio_brain=pb,
            )
        # deque maxlen=50 — doit contenir exactement 50 entrées
        assert len(audit._score_history) == 50


# ── trading_level + unsafe_reason ─────────────────────────────────────────────


class TestTradingLevel:
    def test_normal_when_clean(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        report = IntegrityReport(cycle=1, issues=[])
        assert audit.trading_level(report) == IntegrityLevel.NORMAL

    def test_halted_when_score_zero(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        issues = [
            IntegrityIssue(f"r{i}", IntegritySeverity.UNSAFE, "d", "i", "o", "capital")
            for i in range(5)
        ]
        report = IntegrityReport(cycle=1, issues=issues)
        assert audit.trading_level(report) == IntegrityLevel.HALTED

    def test_matches_report_level(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        issues = [
            IntegrityIssue("r1", IntegritySeverity.DEGRADED, "d", "i", "o", "signal")
        ]
        report = IntegrityReport(cycle=1, issues=issues)
        assert audit.trading_level(report) == report.level


class TestUnsafeReason:
    def test_none_when_safe(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        report = IntegrityReport(cycle=1, issues=[])
        assert audit.unsafe_reason(report) is None

    def test_none_when_restricted_exactly_50(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        # score 50 → RESTRICTED → still above threshold → no unsafe_reason
        issues = [
            IntegrityIssue("r1", IntegritySeverity.UNSAFE, "d", "i", "o", "capital"),
            IntegrityIssue("r2", IntegritySeverity.DEGRADED, "d", "i", "o", "position"),
            IntegrityIssue("r3", IntegritySeverity.WARNING, "d", "i", "o", "signal"),
        ]
        report = IntegrityReport(cycle=1, issues=issues)
        assert report.score == 50
        assert audit.unsafe_reason(report) is None

    def test_returns_primary_failure_rule_and_desc(self, tmp_path):
        audit = StateIntegrityAudit(log_path=tmp_path / "audit.jsonl")
        # 2 UNSAFE → score=40 → UNSAFE level → unsafe_reason non-null
        issues = [
            IntegrityIssue(
                "capital.zero_or_negative",
                IntegritySeverity.UNSAFE,
                "capital nul détecté",
                "capital > 0",
                "capital=0",
                "capital",
            ),
            IntegrityIssue(
                "position.over_exposed",
                IntegritySeverity.UNSAFE,
                "sur-exposition",
                "notional <= capital",
                "notional=200%",
                "position",
            ),
        ]
        report = IntegrityReport(cycle=1, issues=issues)
        assert report.score == 40
        reason = audit.unsafe_reason(report)
        assert reason is not None
        # Doit contenir la règle de la primary_failure
        assert report.primary_failure.rule in reason
