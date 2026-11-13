"""PPL-QUIESCENCE-01 lot C1b — Advisor integration (contract C1b v0 §7).

L1: without C1b variables the module is not imported and the bootstrap is
reached unchanged.  L2, L3, B9d(iii): refusals are fatal, before any service
for configuration and lock.  L5, L7: the source
structure of the integration (order, opt-in, exit codes) and the unchanged
authority helper.  Hermetic: the Advisor is entered through ``main()`` with its
instance lock bypassed and the authority bootstrap replaced by a sentinel; no
cycle, network, exchange or notification is reached.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import signal

import advisor_loop
import pytest

from paper_trading import ppl_quiescence_c1b as c1b

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "core" / "advisor_loop.py").read_text(encoding="utf-8")
# unpatched reference, captured once (monkeypatch restores it between tests)
_REAL_C1B_PREPARE = advisor_loop._c1b_check_deps_and_prepare


class _ReachedBootstrap(Exception):
    pass


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNIVERSE_ENABLED", "false")
    for name in c1b.C1B_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(advisor_loop, "_acquire_instance_lock", lambda: None)
    monkeypatch.setattr(advisor_loop, "_release_instance_lock", lambda: None)
    monkeypatch.setattr(advisor_loop, "_check_critical_deps", lambda: None)
    monkeypatch.setattr(advisor_loop, "ADVISOR_SESSION_PRIMER", False)  # no network
    calls: list[bool] = []

    def bootstrap(enabled):
        calls.append(enabled)
        raise _ReachedBootstrap()

    monkeypatch.setattr(advisor_loop, "_bootstrap_paper_lifecycle_authority", bootstrap)
    return calls


def _paths(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "gate").mkdir()
    (tmp_path / "proofs").mkdir()
    (tmp_path / "run").mkdir()
    return {
        c1b.ENV_GATE_JOURNAL: str(tmp_path / "gate" / "gate.jsonl"),
        c1b.ENV_PROOF_DIR: str(tmp_path / "proofs"),
        c1b.ENV_IDENTITY_LOCK: str(tmp_path / "run" / "id.lock"),
    }


class _Inert:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Runtime:
    """Every runtime component is an inert class (constructors only are reached
    before the authority bootstrap sentinel)."""

    def __getattr__(self, name):
        return _Inert


def _paths_of(tmp_path: Path) -> dict[str, str]:
    return {
        c1b.ENV_GATE_JOURNAL: str(tmp_path / "gate" / "gate.jsonl"),
        c1b.ENV_PROOF_DIR: str(tmp_path / "proofs"),
        c1b.ENV_IDENTITY_LOCK: str(tmp_path / "run" / "id.lock"),
    }


def _main():
    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=_Runtime())


# --------------------------------------------------------------- L1 (off)


def test_l1_without_c1b_variables_the_bootstrap_is_reached_without_import(
    _hermetic, monkeypatch
):
    monkeypatch.delitem(sys.modules, "paper_trading.ppl_quiescence_c1b", raising=False)
    import signal

    handlers = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
    with pytest.raises(_ReachedBootstrap):
        _main()
    assert len(_hermetic) == 1
    # no C1b handler installed: SIGTERM/SIGINT dispositions unchanged
    assert (
        signal.getsignal(signal.SIGTERM),
        signal.getsignal(signal.SIGINT),
    ) == handlers
    assert "paper_trading.ppl_quiescence_c1b" not in sys.modules


def test_l1_blank_values_mean_off(_hermetic, monkeypatch):
    for name in c1b.C1B_ENV_VARS:
        monkeypatch.setenv(name, "  ")
    with pytest.raises(_ReachedBootstrap):
        _main()


# --------------------------------------------- L2, L3, B9d(iii): refusals


@pytest.mark.parametrize("missing", c1b.C1B_ENV_VARS)
def test_l3_r2_class1_partial_configuration_refuses_before_any_creation(
    _hermetic, monkeypatch, tmp_path, missing
):
    for name, value in _paths(tmp_path).items():
        if name != missing:
            monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit, match=r"\[C1b\] refus au démarrage: partial"):
        _main()
    assert _hermetic == []  # authority bootstrap never reached
    assert not (tmp_path / "logs").exists()  # nothing created by main() either


def test_b9d_iii_r2_class2_identity_lock_held_elsewhere_refuses_before_bootstrap(
    _hermetic, monkeypatch, tmp_path
):
    paths = _paths(tmp_path)
    for name, value in paths.items():
        monkeypatch.setenv(name, value)
    holder = c1b.IdentityLock.acquire(paths[c1b.ENV_IDENTITY_LOCK])
    try:
        with pytest.raises(SystemExit, match="held by another process"):
            _main()
    finally:
        holder.close()
    assert _hermetic == []


def test_l2_r2_class3_without_ppl_authority_refuses_after_bootstrap_effects_admitted(
    _hermetic, monkeypatch, tmp_path
):
    for name, value in _paths(tmp_path).items():
        monkeypatch.setenv(name, value)
    seen = []

    def legacy_bootstrap(enabled):
        seen.append(enabled)
        return SimpleNamespace(ppl_is_authoritative=False), None

    monkeypatch.setattr(
        advisor_loop, "_bootstrap_paper_lifecycle_authority", legacy_bootstrap
    )
    import signal

    before = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(SystemExit, match="requires PAPER lifecycle authority"):
            _main()
    finally:
        signal.signal(signal.SIGTERM, before)
        signal.signal(signal.SIGINT, signal.default_int_handler)
    assert len(seen) == 1  # the authority bootstrap ran before the refusal
    # admitted effects of a class-3 refusal (contract §13.2), not denied:
    assert Path(_paths_of(tmp_path)[c1b.ENV_IDENTITY_LOCK]).exists()  # class 2 lock
    assert (tmp_path / "logs").is_dir()  # created by main() before the bootstrap
    assert not any((tmp_path / "proofs").iterdir())  # no proof written by C1b
    assert not (tmp_path / "gate" / "gate.jsonl").exists()  # no gate journal


def test_b11e_manifest_error_in_the_authority_bootstrap_propagates_unchanged(
    _hermetic, monkeypatch, tmp_path
):
    """B11e on the C1b-wired Advisor path: with a valid C1b configuration, an
    ``AuthorityManifestError`` raised by the (unchanged) authority bootstrap is
    neither caught nor rewrapped by ``_c1b_bootstrap``; ``bind_wiring`` is
    never called, nothing is written by C1b (no proof, no gate journal)."""
    from paper_trading.ppl_authority_runtime import AuthorityManifestError

    for name, value in _paths(tmp_path).items():
        monkeypatch.setenv(name, value)
    error = AuthorityManifestError("injected manifest role/schema mismatch")

    def failing_bootstrap(enabled):
        raise error

    bound: list = []
    monkeypatch.setattr(
        advisor_loop, "_bootstrap_paper_lifecycle_authority", failing_bootstrap
    )
    monkeypatch.setattr(c1b, "bind_wiring", lambda *a, **k: bound.append(a))
    before = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(AuthorityManifestError) as info:
            _main()
    finally:
        signal.signal(signal.SIGTERM, before)
        signal.signal(signal.SIGINT, signal.default_int_handler)
    assert info.value is error  # same object: not rewrapped into a C1b refusal
    assert bound == []
    assert not any((tmp_path / "proofs").iterdir())
    assert not (tmp_path / "gate" / "gate.jsonl").exists()


# ---------------------------------------------------------- L7 (structure)


def _main_source() -> str:
    start = SOURCE.index("def main(")
    end = SOURCE.index("_C1B_ENV_VARS = (", start)
    return SOURCE[start:end]


def _c1b_helpers_source() -> str:
    start = SOURCE.index("_C1B_ENV_VARS = (")
    end = SOURCE.index("def _bootstrap_paper_lifecycle_authority(", start)
    return SOURCE[start:end]


def test_l7_env_names_are_the_module_constants():
    assert advisor_loop._C1B_ENV_VARS == c1b.C1B_ENV_VARS


def test_l7_order_lock_then_c1b_then_services_then_bootstrap_then_bind():
    body = _main_source()
    order = [
        "_acquire_instance_lock()",
        "_c1b_prepared = _c1b_check_deps_and_prepare()",
        "runtime = runtime or load_advisor_runtime()",
        "_c1b_bootstrap(_paper_trading_enabled, _c1b_prepared)",
        "_c1b_wiring.simulator_kwargs() if _c1b_wiring is not None else {}",
        "while True:",
        "_c1b_wiring.stop_requested",
        "_c1b_shutdown_or_exit(",
        'log.critical("[main] Sortie anormale — sys.exit(1)")',
    ]
    positions = [body.index(marker) for marker in order]
    assert positions == sorted(positions), list(zip(order, positions))
    helpers = _c1b_helpers_source()
    assert helpers.index("_check_critical_deps()") < helpers.index("prepare_from_env(")
    assert helpers.index("_bootstrap_paper_lifecycle_authority(") < helpers.index(
        "bind_wiring("
    )
    assert "sys.exit(outcome.exit_code)" in helpers


def test_l7_main_line_numbers_cited_by_tests_and_docs_are_unchanged():
    """The C1b helpers live after ``main()``; ``main()`` gains no line before
    the kill switch construction (pinned by an existing documentary test)."""
    lines = SOURCE.splitlines()
    assert "runtime.TelegramKillSwitch(" in lines[3853]


def test_l5_l7_stop_paths_notifications_and_sleep_are_c1b_only():
    body = _main_source()
    assert "_c1b_wiring.wait_stop(interval)" in body
    assert body.count("_sleep(interval)") == 1
    # crash path unchanged: no proof is written when _clean_exit is False
    assert "if _c1b_wiring is not None and _clean_exit:" in body
    # SIGTERM sends no message; SIGINT keeps the existing one
    assert "if _c1b_wiring.stop_by_sigint:" in body
    assert body.count('_telegram("Crypto AI Terminal arrete manuellement.")') == 2
    assert "_telegram" not in _c1b_helpers_source()


def test_l7_no_gate_driving_and_no_clearance_in_the_advisor_diff():
    c1b_lines = [ln for ln in _main_source().splitlines() if "_c1b" in ln]
    joined = "\n".join(c1b_lines) + _c1b_helpers_source()
    for forbidden in (".open(", "drain_barrier", "clearance", "epoch_role", ".close("):
        assert forbidden not in joined, forbidden


def test_l7_authority_helper_body_is_not_modified_by_c1b():
    start = SOURCE.index("def _bootstrap_paper_lifecycle_authority(")
    end = SOURCE.index("def _op_legacy_first_blocker(", start)
    assert "c1b" not in SOURCE[start:end].lower()
    assert "admission_gate" not in SOURCE[start:end]


# ------------------------------------------------- L5: notifications (Advisor)


def _run_main_with_signal(monkeypatch, tmp_path, sig: int, *, during_cycle: bool):
    """Run the real ``main()`` (smoke-test runtime stubs, observation mode,
    PAPER disabled) in C1b mode with the real ``prepare_from_env`` and real
    handlers; deliver ``sig`` to this process either right after preparation
    (stop before cycle 1) or from inside cycle 1.  The authority bootstrap is
    the legacy one; the wiring is a real ``C1bWiring`` around the real
    prepared object (no gate, synthetic CLAIMED_ONLY code).  Returns the
    ``_telegram`` and ``_send_email`` captures, the analyzed calls and the exit."""
    import os
    import signal
    import time as _time

    from tests.test_advisor_loop_smoke import _runtime

    from paper_trading.paper_authority import PaperLifecycleAuthority

    for name, value in _paths(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("V9_ADVISOR_ONLY", "true")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    texts: list[str] = []
    emails: list[str] = []
    analyzed: list[str] = []
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: texts.append(text))
    monkeypatch.setattr(advisor_loop, "_send_email", lambda s, b: emails.append(s))
    prepared_box: dict = {}

    def prepare():
        prepared = _REAL_C1B_PREPARE()
        prepared_box["p"] = prepared
        if not during_cycle:
            os.kill(os.getpid(), sig)  # handled by the C1b handler: flag only
        return prepared

    def bootstrap(enabled, prepared):
        wiring = c1b.C1bWiring(
            prepared=prepared,
            gate=None,
            code=c1b.CodeIdentity(code_sha="cb" * 20, worktree_state="CLEAN"),
            manifest=None,
            manifest_sha256="",
            store_root=tmp_path / "authority",
        )
        return PaperLifecycleAuthority.LEGACY_AUTHORITY, None, wiring

    def analyze(*args, **kwargs):
        analyzed.append("BTC/USDT")
        if during_cycle and len(analyzed) == 1:
            os.kill(os.getpid(), sig)  # arrives in the middle of cycle 1
        return {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=_time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        }

    monkeypatch.setattr(advisor_loop, "_c1b_check_deps_and_prepare", prepare)
    monkeypatch.setattr(advisor_loop, "_c1b_bootstrap", bootstrap)
    monkeypatch.setattr(advisor_loop, "analyze_symbol", analyze)
    handlers = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
    try:
        with pytest.raises(SystemExit) as exit_info:
            advisor_loop.main(
                ["BTC/USDT"], interval=0, max_cycles=5, runtime=_runtime()
            )
    finally:
        prepared = prepared_box.get("p")
        if prepared is not None:
            prepared.signals.restore()
            prepared.identity_lock.close()
        signal.signal(signal.SIGTERM, handlers[0])
        signal.signal(signal.SIGINT, handlers[1])
    return texts, emails, analyzed, exit_info.value.code, prepared_box["p"]


_MANUAL_STOP = "Crypto AI Terminal arrete manuellement."


def test_l5_sigterm_adds_no_notification_and_sigint_only_the_existing_one(
    monkeypatch, tmp_path
):
    """Behavioural L5 on the real Advisor loop: same boot notifications in both
    runs; SIGTERM adds none at stop; SIGINT adds exactly the existing manual
    stop message (as the legacy KeyboardInterrupt path of 87155f3a); the
    e-mails are the boot ones only, identical in both runs (none at stop).
    No simulator in this setup, so the proof outcome is NO_SIMULATOR: exit 3."""
    (tmp_path / "term").mkdir()
    (tmp_path / "int").mkdir()
    term_texts, term_emails, term_cycles, term_code, term_prep = _run_main_with_signal(
        monkeypatch, tmp_path / "term", signal.SIGTERM, during_cycle=False
    )
    int_texts, int_emails, int_cycles, int_code, int_prep = _run_main_with_signal(
        monkeypatch, tmp_path / "int", signal.SIGINT, during_cycle=False
    )
    assert term_prep.signals.signum == signal.SIGTERM
    assert int_prep.signals.signum == signal.SIGINT
    assert term_cycles == [] and int_cycles == []  # stopped at the top of cycle 1
    assert _MANUAL_STOP not in term_texts
    assert int_texts == term_texts + [_MANUAL_STOP]
    assert term_emails == int_emails  # boot e-mail only, nothing added at stop
    assert not any("arret" in e.lower() or "crash" in e.lower() for e in term_emails)
    assert term_code == 3 and int_code == 3  # NO_SIMULATOR: proof not sealed


def test_l5_signal_during_a_cycle_lets_the_cycle_complete_then_stops(
    monkeypatch, tmp_path
):
    """A signal received in the middle of cycle 1 does not interrupt it (no
    asynchronous exception): the cycle completes, the stop is taken at the top
    of cycle 2, before ``max_cycles`` (5) is reached."""
    texts, emails, analyzed, code, prepared = _run_main_with_signal(
        monkeypatch, tmp_path, signal.SIGTERM, during_cycle=True
    )
    assert prepared.signals.signum == signal.SIGTERM
    assert analyzed == ["BTC/USDT"]  # exactly one cycle, completed
    assert _MANUAL_STOP not in texts
    assert not any("arret" in e.lower() or "crash" in e.lower() for e in emails)
    assert code == 3
