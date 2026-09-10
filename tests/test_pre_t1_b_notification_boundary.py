"""O-02W-PRE-T1-B — regression tests proving the two non-functional
`TelegramNotifier().send(...)` call expressions (finding 4 of
docs/contracts/O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md) were removed
without repair or rerouting, and that the surrounding safety mechanisms
(SelfAwareness CRITICAL transition, PositionManager liquidation defense)
are behaviorally unchanged.

No token, chat-id, or secret is needed by any test here. No test contacts
Telegram or an exchange — network calls are actively guarded against via
monkeypatched `urllib.request.urlopen`.
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SELF_AWARENESS_PATH = (
    REPO_ROOT / "quant_hedge_ai" / "agents" / "intelligence" / "self_awareness_engine.py"
)
POSITION_MANAGER_PATH = (
    REPO_ROOT / "quant_hedge_ai" / "agents" / "execution" / "position_manager.py"
)
SELF_AWARENESS_SRC = SELF_AWARENESS_PATH.read_text(encoding="utf-8")
POSITION_MANAGER_SRC = POSITION_MANAGER_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AST helpers — prove absence at the syntax-tree level, not just string search
# ---------------------------------------------------------------------------


def _find_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _find_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node


def _constructs_telegram_notifier(tree: ast.AST) -> bool:
    for call in _find_calls(tree):
        func = call.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "TelegramNotifier":
            return True
    return False


def _calls_send_on_telegram_notifier(tree: ast.AST) -> bool:
    """Detect `TelegramNotifier().send(...)` or `<x>.send(...)` chained off
    a TelegramNotifier construction, walking the call chain."""
    for call in _find_calls(tree):
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == "send":
            # Walk the value being called .send() on, looking for a
            # TelegramNotifier(...) construction anywhere in that subtree.
            for sub in ast.walk(func.value):
                if isinstance(sub, ast.Call):
                    subfunc = sub.func
                    subname = (
                        subfunc.id
                        if isinstance(subfunc, ast.Name)
                        else getattr(subfunc, "attr", None)
                    )
                    if subname == "TelegramNotifier":
                        return True
    return False


def _imports_telegram_notifier(tree: ast.AST) -> bool:
    for imp in _find_imports(tree):
        if isinstance(imp, ast.ImportFrom):
            if imp.module and "telegram_notifier" in imp.module:
                return True
            if any(alias.name == "TelegramNotifier" for alias in imp.names):
                return True
        if isinstance(imp, ast.Import):
            if any("telegram_notifier" in alias.name for alias in imp.names):
                return True
    return False


@pytest.mark.parametrize(
    "path,src",
    [
        (SELF_AWARENESS_PATH, SELF_AWARENESS_SRC),
        (POSITION_MANAGER_PATH, POSITION_MANAGER_SRC),
    ],
)
def test_no_telegram_notifier_construction(path, src):
    tree = ast.parse(src, filename=str(path))
    assert not _constructs_telegram_notifier(tree), (
        f"{path.name} still constructs TelegramNotifier(...)"
    )


@pytest.mark.parametrize(
    "path,src",
    [
        (SELF_AWARENESS_PATH, SELF_AWARENESS_SRC),
        (POSITION_MANAGER_PATH, POSITION_MANAGER_SRC),
    ],
)
def test_no_send_call_on_telegram_notifier(path, src):
    tree = ast.parse(src, filename=str(path))
    assert not _calls_send_on_telegram_notifier(tree), (
        f"{path.name} still calls .send(...) chained off TelegramNotifier(...)"
    )


@pytest.mark.parametrize(
    "path,src",
    [
        (SELF_AWARENESS_PATH, SELF_AWARENESS_SRC),
        (POSITION_MANAGER_PATH, POSITION_MANAGER_SRC),
    ],
)
def test_no_telegram_notifier_import(path, src):
    tree = ast.parse(src, filename=str(path))
    assert not _imports_telegram_notifier(tree), (
        f"{path.name} still imports TelegramNotifier / telegram_notifier"
    )
    assert "TelegramNotifier" not in src, (
        f"{path.name} still references the TelegramNotifier identifier"
    )


def test_self_awareness_no_resume_presented_as_telegram_command():
    for lineno, line in enumerate(SELF_AWARENESS_SRC.splitlines(), start=1):
        if "/RESUME" in line:
            raise AssertionError(
                f"self_awareness_engine.py:{lineno} still presents /RESUME as "
                f"a Telegram command: {line!r}"
            )


def test_operator_resume_docstring_does_not_assert_telegram_command():
    match = re.search(
        r"def operator_resume\(.*?\)\s*->\s*None:\s*\"\"\"(.*?)\"\"\"",
        SELF_AWARENESS_SRC,
        re.DOTALL,
    )
    assert match, "operator_resume() docstring not found"
    docstring = match.group(1)
    assert "/RESUME" not in docstring
    assert "Telegram" not in docstring or "Aucune commande Telegram" in docstring


def test_self_awareness_send_telegram_critical_removed():
    assert "_send_telegram_critical" not in SELF_AWARENESS_SRC


def test_position_manager_alerte_telegram_comment_corrected():
    assert "Alerte Telegram" not in POSITION_MANAGER_SRC
    match = re.search(
        r"_check_liquidation_defense\(self, pos: Position\) -> None:(.*?)"
        r"# Fermeture d'urgence",
        POSITION_MANAGER_SRC,
        re.DOTALL,
    )
    assert match, "_check_liquidation_defense body not found"
    body = match.group(1)
    assert "Avertissement local" in body
    assert "aucune notification externe" in body


# ---------------------------------------------------------------------------
# Behavioral — SelfAwarenessEngine CRITICAL transition
# ---------------------------------------------------------------------------


def _block_network(monkeypatch):
    """Fail the test loudly if anything attempts an HTTP/socket call."""
    import socket
    import urllib.request

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "network call attempted during a test that must stay fully local"
        )

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)


def test_self_awareness_critical_transition_preserves_safety_state(monkeypatch):
    _block_network(monkeypatch)
    from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
        DangerLevel,
        DriftSignal,
        SelfAwarenessEngine,
    )

    # _apply_level() itself never invokes on_level_change (only evaluate()
    # does, on a level transition) — no callback is constructed or
    # asserted here; callback behavior is covered separately by
    # test_self_awareness_critical_transition_invokes_level_change_callback.
    engine = SelfAwarenessEngine()

    drifts = [
        DriftSignal(
            dimension="infra",
            metric="latency_ms",
            value=5000.0,
            baseline=200.0,
            severity=DangerLevel.CRITICAL,
            message="latence critique",
        )
    ]

    before = time.time()
    engine._apply_level(DangerLevel.CRITICAL, drifts)
    after = time.time()

    state = engine._state
    assert state.size_factor == 0.0
    assert state.safe_mode is True
    assert state.halt_until > after
    # halt_until must reflect CRITICAL_HALT_SECONDS, not an arbitrary value.
    assert state.halt_until <= before + SelfAwarenessEngine.CRITICAL_HALT_SECONDS + 5
    assert state.halt_until >= before + SelfAwarenessEngine.CRITICAL_HALT_SECONDS - 5


def test_self_awareness_critical_transition_logs_critical(monkeypatch):
    _block_network(monkeypatch)
    import logging

    from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
        DangerLevel,
        DriftSignal,
        SelfAwarenessEngine,
    )

    engine = SelfAwarenessEngine()
    drifts = [
        DriftSignal(
            dimension="infra",
            metric="latency_ms",
            value=5000.0,
            baseline=200.0,
            severity=DangerLevel.CRITICAL,
            message="latence critique",
        )
    ]
    # StructuredLogger sets propagate=False on its category loggers (see
    # observability/json_logger.py::StructuredLogger._get_logger), so
    # caplog's root-attached handler never sees these records — attach a
    # handler directly to the category logger instead.
    logger_name = "sys.quant_hedge_ai.agents.intelligence.self_awareness_engine.incidents"
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    target_logger = logging.getLogger(logger_name)
    target_logger.addHandler(handler)
    try:
        engine._apply_level(DangerLevel.CRITICAL, drifts)
    finally:
        target_logger.removeHandler(handler)

    assert any(
        "CRITICAL" in record.getMessage()
        and "halt critique interne" in record.getMessage()
        for record in records
    ), "expected the honest local critical log line to remain present"
    assert not any(
        "kill switch" in record.getMessage() for record in records
    ), "CRITICAL log must not claim a kill switch was triggered"


def test_self_awareness_critical_transition_invokes_level_change_callback(monkeypatch):
    """Exercise the same public path advisor_loop.py wires
    (on_level_change=_on_awareness_change) via evaluate(), proving the
    callback still fires on a real CRITICAL level transition.

    Natural latency alone classifies as DANGER, not CRITICAL, in
    _check_infra_drift() — so this test isolates causality by
    monkeypatching the three other drift detectors to report no drift
    and the infra detector to report exactly one DangerLevel.CRITICAL
    DriftSignal, then drives the real, public evaluate() path.
    """
    _block_network(monkeypatch)
    from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
        DangerLevel,
        DriftSignal,
        SelfAwarenessEngine,
    )

    callback_calls = []
    engine = SelfAwarenessEngine(on_level_change=lambda state: callback_calls.append(state))

    # Enough trades to clear evaluate()'s initial data-guard
    # (len(self._trades) >= max(3, RECENT_WINDOW // 2)).
    for _ in range(SelfAwarenessEngine.RECENT_WINDOW + 5):
        engine.record_trade(
            pnl_pct=0.01,
            sharpe=1.0,
            regime="trend",
            personality="default",
            latency_ms=50.0,
            slippage_pct=0.0,
        )

    critical_signal = DriftSignal(
        dimension="infra",
        metric="synthetic_critical",
        value=1.0,
        baseline=0.0,
        severity=DangerLevel.CRITICAL,
        message="synthetic CRITICAL drift for test isolation",
    )
    monkeypatch.setattr(engine, "_check_performance_drift", lambda: [])
    monkeypatch.setattr(engine, "_check_behavioral_drift", lambda: [])
    monkeypatch.setattr(engine, "_check_market_mismatch", lambda: [])
    monkeypatch.setattr(engine, "_check_infra_drift", lambda: [critical_signal])

    before = time.time()
    state = engine.evaluate()
    after = time.time()

    assert state.level == DangerLevel.CRITICAL
    assert len(callback_calls) == 1
    assert callback_calls[0] is engine._state
    assert state.size_factor == 0.0
    assert state.safe_mode is True
    assert state.halt_until <= before + SelfAwarenessEngine.CRITICAL_HALT_SECONDS + 5
    assert state.halt_until >= after + SelfAwarenessEngine.CRITICAL_HALT_SECONDS - 5


def test_self_awareness_on_level_change_still_wired_in_advisor_loop():
    """core/advisor_loop.py must still construct SelfAwarenessEngine with
    on_level_change — this mission does not touch that file or its
    callback wiring."""
    advisor_loop_src = (REPO_ROOT / "core" / "advisor_loop.py").read_text(
        encoding="utf-8"
    )
    assert "SelfAwarenessEngine(on_level_change=_on_awareness_change)" in advisor_loop_src


# ---------------------------------------------------------------------------
# Behavioral — PositionManager liquidation defense
# ---------------------------------------------------------------------------


def _make_position(entry_price: float, leverage: int, current_price: float):
    from quant_hedge_ai.agents.execution.position_manager import Position, PositionSide

    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=entry_price,
        size_usd=1000.0,
        qty=1000.0 / entry_price,
        leverage=leverage,
    )
    pos.update_price(current_price)
    return pos


def test_position_manager_warning_zone_logs_locally_and_does_not_close(monkeypatch):
    _block_network(monkeypatch)
    import logging

    from quant_hedge_ai.agents.execution.position_manager import PositionManager

    # leverage=10 -> liquidation_price = entry * 0.905; at current=entry,
    # distance = (entry - 0.905*entry)/entry = 0.095, inside (0.08, 0.15).
    pos = _make_position(entry_price=100.0, leverage=10, current_price=100.0)
    dist = pos.liquidation_distance_pct()
    assert 0.08 < dist < 0.15, f"test setup must land in the warning zone, got {dist}"

    pm = PositionManager(paper_mode=True)
    # StructuredLogger sets propagate=False on its category loggers (see
    # observability/json_logger.py::StructuredLogger._get_logger), so
    # caplog's root-attached handler never sees these records — attach a
    # handler directly to the category logger instead.
    logger_name = "sys.quant_hedge_ai.agents.execution.position_manager.runtime"
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    target_logger = logging.getLogger(logger_name)
    target_logger.addHandler(handler)
    try:
        pm._check_liquidation_defense(pos)
    finally:
        target_logger.removeHandler(handler)

    assert any(
        "ALERTE LIQUIDATION" in record.getMessage() for record in records
    ), "expected the local liquidation warning log to remain present"
    assert pos.closed is False, "warning zone must not prematurely close the position"


def test_position_manager_below_liq_defense_pct_closes_with_liquidation_def(monkeypatch):
    _block_network(monkeypatch)
    from quant_hedge_ai.agents.execution.position_manager import (
        CloseReason,
        PositionManager,
    )

    # leverage=10 -> liquidation_price = 90.5; current=97 ->
    # distance = (97 - 90.5) / 97 ≈ 0.06701, below the default 0.08
    # liq_defense_pct threshold.
    pos = _make_position(entry_price=100.0, leverage=10, current_price=97.0)
    dist = pos.liquidation_distance_pct()
    assert dist < pos.liq_defense_pct, (
        f"test setup must be below liq_defense_pct, got dist={dist} "
        f"threshold={pos.liq_defense_pct}"
    )

    pm = PositionManager(paper_mode=True)
    pm._check_liquidation_defense(pos)

    assert pos.closed is True
    assert pos.close_reason == CloseReason.LIQUIDATION_DEF.value


def test_position_manager_liq_defense_pct_and_thresholds_unchanged():
    # Default env-driven threshold must still be 0.08 (8%) unless overridden
    # by PM_LIQ_DEFENSE_PCT — this mission must not change it.
    import os

    expected = float(os.getenv("PM_LIQ_DEFENSE_PCT", "0.08"))
    pos = _make_position(entry_price=100.0, leverage=10, current_price=100.0)
    assert pos.liq_defense_pct == expected


def test_position_manager_no_new_notifier_wiring():
    for forbidden in ("OpsNotifier", "send_alert", "NOTIFIER", "MultiNotifier"):
        assert forbidden not in POSITION_MANAGER_SRC, (
            f"position_manager.py must not gain new notifier wiring: {forbidden!r}"
        )


def test_self_awareness_no_new_notifier_wiring():
    for forbidden in ("OpsNotifier", "send_alert", "NOTIFIER", "MultiNotifier"):
        assert forbidden not in SELF_AWARENESS_SRC, (
            f"self_awareness_engine.py must not gain new notifier wiring: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# No Telegram surface reintroduced
# ---------------------------------------------------------------------------


def test_no_telegram_api_url_in_either_module():
    for path, src in ((SELF_AWARENESS_PATH, SELF_AWARENESS_SRC), (POSITION_MANAGER_PATH, POSITION_MANAGER_SRC)):
        assert "api.telegram.org" not in src, f"{path.name} references the Telegram API URL"


def test_no_new_telegram_env_var_in_either_module():
    for path, src in ((SELF_AWARENESS_PATH, SELF_AWARENESS_SRC), (POSITION_MANAGER_PATH, POSITION_MANAGER_SRC)):
        assert not re.search(r"TELEGRAM_\w+", src), (
            f"{path.name} references a TELEGRAM_* environment variable"
        )


# ---------------------------------------------------------------------------
# O-02W-PRE-T1-B-R1 — evidence-honest CRITICAL transition certification
# ---------------------------------------------------------------------------


def test_module_docstring_no_longer_claims_kill_switch_or_telegram_at_level4():
    assert "kill switch + Telegram critique" not in SELF_AWARENESS_SRC
    assert "NIVEAU 4" in SELF_AWARENESS_SRC
    match = re.search(r"NIVEAU 4.*", SELF_AWARENESS_SRC)
    assert match, "NIVEAU 4 line not found in module docstring"
    line = match.group(0)
    assert "kill switch" not in line
    assert "Telegram" not in line


def test_critical_log_no_longer_claims_kill_switch_triggered():
    assert "kill switch déclenché" not in SELF_AWARENESS_SRC
    assert "halt critique interne activé" in SELF_AWARENESS_SRC


def test_operator_resume_log_does_not_assert_unproven_operator_origin():
    assert "RESUME opérateur" not in SELF_AWARENESS_SRC
    assert "operator_resume invoqué" in SELF_AWARENESS_SRC


def test_operator_resume_method_name_unchanged_as_compatibility_identifier():
    """operator_resume() is a compatibility identifier — its name must not
    be renamed even though its docstring/log wording was corrected."""
    assert "def operator_resume(" in SELF_AWARENESS_SRC


def test_no_pytest_skip_in_critical_callback_test():
    """The CRITICAL-callback test must produce a real pass/fail, not a
    skip that could mask absent proof."""
    source_path = Path(__file__)
    src = source_path.read_text(encoding="utf-8")
    match = re.search(
        r"def test_self_awareness_critical_transition_invokes_level_change_callback"
        r"\(.*?\n(?=def |\Z)",
        src,
        re.DOTALL,
    )
    assert match, "target test function not found in this file"
    body = match.group(0)
    assert "pytest.skip" not in body
