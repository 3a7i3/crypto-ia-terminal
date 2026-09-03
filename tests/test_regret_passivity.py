"""Invariants constitutionnels : les observateurs ne mutent pas la décision."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_auto_calibration_alone_cannot_enable_regret_delta(monkeypatch):
    import config.feature_flags as flags
    from quant_hedge_ai.agents.intelligence.regret_engine import RegretEngine

    monkeypatch.setenv("FEATURE_AUTO_CALIBRATION", "true")
    monkeypatch.setenv("FEATURE_REGRET_DECISION_FEEDBACK", "false")
    importlib.reload(flags)
    engine = object.__new__(RegretEngine)
    engine._compute_threshold_delta = lambda *args, **kwargs: -2
    assert engine.get_threshold_delta("sideways") == 0


def test_master_feedback_flag_defaults_to_false(monkeypatch):
    import config.feature_flags as flags

    monkeypatch.delenv("FEATURE_REGRET_DECISION_FEEDBACK", raising=False)
    importlib.reload(flags)
    assert flags.FEATURE_REGRET_DECISION_FEEDBACK is False


def test_known_threshold_setters_are_below_master_passivity_guard():
    source_path = Path(__file__).parents[1] / "core" / "advisor_loop.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    targets = {"set_adaptive_delta", "apply_regret_delta"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in targets:
            continue
        found.add(node.func.attr)
        ancestor = parents.get(node)
        guarded = False
        while ancestor is not None:
            if isinstance(ancestor, ast.If):
                condition = ast.get_source_segment(source, ancestor.test) or ""
                if "FEATURE_REGRET_DECISION_FEEDBACK" in condition:
                    guarded = True
                    break
            ancestor = parents.get(ancestor)
        assert guarded, f"{node.func.attr} is not below the constitutional guard"
    assert found == targets


def test_v2_price_feed_not_nested_under_v1_engine_guard():
    source = (Path(__file__).parents[1] / "core" / "advisor_loop.py").read_text()
    assert (
        "if _obs_regret_scheduler is not None or regret_engine is not None:" in source
    )
    assert 'source="advisor_loop_cycle_snapshot"' in source
