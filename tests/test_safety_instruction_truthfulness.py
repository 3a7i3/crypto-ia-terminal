"""O-02W-PRE-T1-A / O-02W-PRE-T1-A-R1 — regression tests for the
safety-instruction truthfulness fixes.

Covers the source-proven drifts from O-02W-E1 §13 and the MASTER-review
follow-up (R1):
  1. GLOBAL_STATE_MACHINE.md misattributing SAFE_MODE transitions to Telegram
     / "commande manuelle", and misrepresenting SAFE_MODE -> NORMAL as a
     direct RuntimeStateMachine transition.
  2. ExchangeMonitor's critical email instructing a nonexistent /STOP_ALL
     command.
  3. advisor_loop.py's /RESUME instructions and adjacent prose (BlackBox
     description, kill-switch callback reasons, comments) with no canonical
     dispatcher or proven operator origin.

Behavior-level assertions are used where the code can be exercised without
booting the full advisor loop (ExchangeMonitor, RuntimeStateMachine). The
advisor_loop.py and GLOBAL_STATE_MACHINE.md wording properties are
message/documentation-integrity properties that cannot be safely exercised
without booting the full advisor, so they are checked at the source-text
level, matching the pattern already used by the repository's other
advisor_loop smoke/message tests.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADVISOR_LOOP_SRC = (REPO_ROOT / "core" / "advisor_loop.py").read_text(encoding="utf-8")
STATE_MACHINE_DOC = (REPO_ROOT / "docs" / "GLOBAL_STATE_MACHINE.md").read_text(
    encoding="utf-8"
)
EXCHANGE_MONITOR_SRC = (REPO_ROOT / "supervision" / "exchange_monitor.py").read_text(
    encoding="utf-8"
)


# ---------------------------------------------------------------------------
# RuntimeStateMachine — actual state-machine semantics (behavioral)
# ---------------------------------------------------------------------------


def _make_rsm(**kwargs):
    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

    clock = {"t": 0.0}

    def _clock():
        return clock["t"]

    rsm = RuntimeStateMachine(_clock=_clock, **kwargs)
    return rsm, clock


def test_rsm_error_threshold_transitions_to_safe_mode_automatically():
    from quant_hedge_ai.runtime.runtime_state_machine import SystemState

    rsm, clock = _make_rsm(safe_threshold=3, critical_threshold=2, degraded_threshold=1)
    for _ in range(3):
        rsm.report_error("generic")
    assert rsm.state == SystemState.SAFE_MODE


def test_rsm_named_request_safe_mode_transitions_to_safe_mode():
    from quant_hedge_ai.runtime.runtime_state_machine import SystemState

    rsm, clock = _make_rsm()
    state = rsm.request_safe_mode("self_awareness", "level=CRITICAL")
    assert state == SystemState.SAFE_MODE
    assert rsm.state == SystemState.SAFE_MODE


def test_rsm_clearing_last_named_request_transitions_to_recovery_not_normal():
    from quant_hedge_ai.runtime.runtime_state_machine import SystemState

    rsm, clock = _make_rsm()
    rsm.request_safe_mode("self_awareness", "level=CRITICAL")
    assert rsm.state == SystemState.SAFE_MODE
    state = rsm.clear_safe_mode_request("self_awareness")
    assert state == SystemState.RECOVERY
    assert rsm.state == SystemState.RECOVERY


def test_rsm_clear_all_safe_mode_requests_transitions_to_recovery_not_normal():
    from quant_hedge_ai.runtime.runtime_state_machine import SystemState

    rsm, clock = _make_rsm()
    rsm.request_safe_mode("kill_switch_stop_all", "reason_a")
    rsm.request_safe_mode("self_awareness", "reason_b")
    assert rsm.state == SystemState.SAFE_MODE
    state = rsm.clear_all_safe_mode_requests()
    assert state == SystemState.RECOVERY
    assert rsm.state == SystemState.RECOVERY


def test_rsm_stable_report_ok_transitions_recovery_to_normal():
    from quant_hedge_ai.runtime.runtime_state_machine import SystemState

    rsm, clock = _make_rsm(stability_s=60.0)
    rsm.request_safe_mode("self_awareness", "reason")
    rsm.clear_all_safe_mode_requests()
    assert rsm.state == SystemState.RECOVERY

    # Not yet stable.
    clock["t"] += 10.0
    rsm.report_ok()
    assert rsm.state == SystemState.RECOVERY

    # Stability window elapsed.
    clock["t"] += 60.0
    state = rsm.report_ok()
    assert state == SystemState.NORMAL
    assert rsm.state == SystemState.NORMAL


def test_rsm_no_direct_safe_mode_to_normal_method_exists():
    """RuntimeStateMachine has no API that jumps SAFE_MODE straight to NORMAL."""
    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

    assert not hasattr(RuntimeStateMachine, "force_resume")


# ---------------------------------------------------------------------------
# GLOBAL_STATE_MACHINE.md — SAFE_MODE attribution and transition model
# ---------------------------------------------------------------------------


def test_state_machine_doc_does_not_label_safe_mode_transitions_manual_command():
    assert "commande manuelle" not in STATE_MACHINE_DOC


def test_state_machine_doc_does_not_claim_direct_safe_mode_to_normal():
    for line in STATE_MACHINE_DOC.splitlines():
        if line.strip().startswith("| SAFE_MODE → NORMAL"):
            raise AssertionError(
                "doc must not claim SAFE_MODE -> NORMAL as a direct "
                f"RuntimeStateMachine transition row: {line!r}"
            )
    assert "SAFE_MODE → RECOVERY" in STATE_MACHINE_DOC
    assert (
        "ne définit aucune transition directe SAFE_MODE → NORMAL"
        in STATE_MACHINE_DOC
    )


def test_state_machine_doc_no_longer_attributes_safe_mode_to_telegram():
    for line in STATE_MACHINE_DOC.splitlines():
        if "SAFE_MODE" in line and "|" in line and "Vers" not in line:
            assert "KillSwitch / Telegram" not in line, (
                f"SAFE_MODE transition row still attributes to Telegram: {line!r}"
            )


def test_state_machine_doc_names_force_safe_mode_and_force_resume():
    assert "force_safe_mode()" in STATE_MACHINE_DOC
    assert "force_resume()" in STATE_MACHINE_DOC


def test_state_machine_doc_distinguishes_production_callers_from_invariant_checks():
    # Auto and named production-runtime paths must be named explicitly.
    assert "report_error()" in STATE_MACHINE_DOC
    assert "request_safe_mode(" in STATE_MACHINE_DOC
    assert "core/invariants.py" in STATE_MACHINE_DOC
    # The doc must not overclaim "no caller at all" for the class - it must
    # scope the "no caller" statement to the specific force_* convenience
    # methods, since request_safe_mode()/report_error() do have production
    # callers.
    assert "instance jetable" in STATE_MACHINE_DOC
    assert "aucun appelant runtime de production" in STATE_MACHINE_DOC


def test_state_machine_doc_does_not_conflate_killswitch_hardened_with_rsm():
    assert "Ne pas conflater les deux états" in STATE_MACHINE_DOC
    assert "RuntimeStateMachine (classe différente)" in STATE_MACHINE_DOC or (
        "classe différente" in STATE_MACHINE_DOC
    )


# ---------------------------------------------------------------------------
# advisor_loop.py — three operator-facing /RESUME instructions
# ---------------------------------------------------------------------------


def test_advisor_loop_degraded_message_does_not_instruct_resume_command():
    match = re.search(
        r'f"Mode DEGRADED.*?"\)', ADVISOR_LOOP_SRC, re.DOTALL
    )
    assert match, "degraded-state Telegram message not found"
    body = match.group(0)
    assert "Envoyez /RESUME" not in body
    assert "Envoyer /RESUME" not in body


def test_advisor_loop_halted_message_does_not_instruct_resume_command():
    match = re.search(r'f"P10-F HALTED.*?"\)', ADVISOR_LOOP_SRC, re.DOTALL)
    assert match, "halted-state Telegram message not found"
    body = match.group(0)
    assert "Envoyez /RESUME" not in body
    assert "Envoyer /RESUME" not in body


def test_advisor_loop_suspended_loop_message_does_not_instruct_resume_command():
    match = re.search(
        r'"Boucle suspendue par Kill Switch\..*?"\n?\s*\)',
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert match, "suspended-loop Telegram message not found"
    body = match.group(0)
    assert "Envoyez /RESUME" not in body
    assert "Envoyer /RESUME" not in body


def test_advisor_loop_no_operator_facing_resume_command_remains():
    """No operator-facing string anywhere in advisor_loop.py instructs /RESUME.

    The self_awareness_engine.py broken-notifier-call /RESUME string is a
    separate, out-of-scope finding (O-02W-E1 finding 4) and is intentionally
    not touched by this mission.
    """
    for lineno, line in enumerate(ADVISOR_LOOP_SRC.splitlines(), start=1):
        if "/RESUME" in line:
            assert "Envoy" not in line, (
                f"advisor_loop.py:{lineno} still instructs an operator to "
                f"send /RESUME: {line!r}"
            )


def test_advisor_loop_replacement_messages_disclose_no_documented_recovery_procedure():
    # Source-level f-string literals may split across lines (interrupted by
    # a closing/opening quote pair), so tolerate that gap in the match.
    resume_unavailable = re.findall(
        r"Aucune commande /RESUME [\"\s]*n'est disponible.{0,80}?via Telegram",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert len(resume_unavailable) == 3, (
        "each replacement message must explicitly state that no /RESUME "
        "command is available via Telegram, in exactly the three target "
        "locations (degraded, halted, suspended-loop)"
    )

    # advisor_loop.py's f-strings wrap across lines at arbitrary word
    # boundaries (interrupted by a closing/opening quote pair, optionally
    # prefixed with 'f'), so tolerate that gap between every word.
    _sep = r'[f"\s]*'
    _words = "aucune procédure de reprise opérateur n'est actuellement documentée".split(
        " "
    )
    pattern = _sep.join(re.escape(w) for w in _words)
    no_documented_procedure = re.findall(pattern, ADVISOR_LOOP_SRC, re.DOTALL | re.IGNORECASE)
    assert len(no_documented_procedure) == 3, (
        "each replacement message must disclose that no operator recovery "
        "procedure is currently documented/source-proven, not merely that "
        "Telegram lacks the command"
    )

    escalade_manuelle = re.findall(
        r"Escalade" + _sep + r"manuelle" + _sep + r"requise",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert len(escalade_manuelle) == 3, (
        "each replacement message must require manual escalation rather "
        "than implying an existing alternative control mechanism"
    )


def test_advisor_loop_replacement_messages_invent_no_control_surface():
    forbidden = (
        "bouton",
        "endpoint",
        "API route",
        "/api/",
        "shell command",
        "systemctl",
        "curl ",
    )
    for match in re.finditer(
        r'_telegram\(\s*f?"(?:Mode DEGRADED|P10-F HALTED|Boucle suspendue).*?\)',
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    ):
        body = match.group(0)
        for needle in forbidden:
            assert needle not in body, f"message invents a control surface: {needle!r}"


def test_advisor_loop_on_resume_callback_unchanged_behaviorally():
    """The wording fix must not touch _on_resume's actual state mutations."""
    match = re.search(
        r"def _on_resume\(\):(.*?)\n    kill_switch = _profile_bootstrap_step",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert match, "_on_resume() definition not found"
    body = match.group(1)
    assert "_halt_requested.clear()" in body
    assert "runtime_authority.clear_all_safe_mode_requests()" in body
    assert "OPERATOR_RESUME" in body


def test_advisor_loop_blackbox_description_claims_no_unproven_manual_origin():
    match = re.search(
        r'record_system_event\(\s*"OPERATOR_RESUME",(.*?)\)',
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert match, "OPERATOR_RESUME record_system_event call not found"
    body = match.group(1)
    assert "Resume manuel" not in body
    assert "non etablie" in body or "non établie" in body


def test_advisor_loop_kill_switch_comments_do_not_claim_telegram_thread_or_command():
    assert "thread Telegram" not in ADVISOR_LOOP_SRC
    assert "STOP_ALL telegram" not in ADVISOR_LOOP_SRC
    assert "CLOSE_ALL telegram" not in ADVISOR_LOOP_SRC
    assert "SAFE_MODE telegram" not in ADVISOR_LOOP_SRC
    assert "intervention opérateur" not in ADVISOR_LOOP_SRC


def test_advisor_loop_kill_switch_callback_reasons_are_programmatic_not_telegram():
    for reason in (
        "STOP_ALL programmatique (callback KillSwitchHardened)",
        "CLOSE_ALL programmatique (callback KillSwitchHardened)",
        "SAFE_MODE programmatique (callback KillSwitchHardened)",
    ):
        assert reason in ADVISOR_LOOP_SRC


def test_advisor_loop_no_new_telegram_command_handler_added():
    assert "_COMMANDS" not in ADVISOR_LOOP_SRC
    assert not re.search(r'"/RESUME":\s*self\.', ADVISOR_LOOP_SRC)


def test_advisor_loop_legitimate_identifiers_and_mutations_preserved():
    assert "RESUME_TRADING" in ADVISOR_LOOP_SRC
    assert '"RESUME_TRADING": 600.0' in ADVISOR_LOOP_SRC
    assert "on_resume=_on_resume" in ADVISOR_LOOP_SRC
    assert "on_stop_all=_on_stop_all" in ADVISOR_LOOP_SRC
    assert "on_close_all=_on_close_all" in ADVISOR_LOOP_SRC
    assert "on_safe_mode=_on_safe_mode" in ADVISOR_LOOP_SRC
    assert '_halt_requested.set()' in ADVISOR_LOOP_SRC
    assert 'runtime_authority.report_ok()' in ADVISOR_LOOP_SRC
    assert 'runtime_authority.report_error("cycle_exception")' in ADVISOR_LOOP_SRC


# ---------------------------------------------------------------------------
# supervision/exchange_monitor.py — /STOP_ALL instruction (unchanged this
# round; re-verified for regression)
# ---------------------------------------------------------------------------


def test_exchange_monitor_email_no_longer_instructs_stop_all():
    assert "/STOP_ALL" not in EXCHANGE_MONITOR_SRC


def test_exchange_monitor_email_replacement_avoids_claiming_telegram_control_path():
    assert "Aucune commande d'arrêt n'est disponible via Telegram" in EXCHANGE_MONITOR_SRC
    assert "escalade manuelle requise" in EXCHANGE_MONITOR_SRC


def test_exchange_monitor_thresholds_and_callbacks_unchanged(monkeypatch):
    """Behavioral check: WARN/CRITICAL thresholds and callback wiring intact."""
    from supervision.exchange_monitor import CRITICAL_AFTER, WARN_AFTER, ExchangeMonitor

    assert WARN_AFTER == 2
    assert CRITICAL_AFTER == 5

    offline_calls = []
    monitor = ExchangeMonitor(on_offline=lambda: offline_calls.append(True))

    telegram_bodies = []
    email_bodies = []
    monkeypatch.setattr(monitor, "_send_telegram", lambda text: telegram_bodies.append(text))
    monkeypatch.setattr(
        monitor, "_send_email", lambda subject, body: email_bodies.append(body)
    )

    for i in range(1, CRITICAL_AFTER + 1):
        monitor._handle_failure(i, "connection refused")

    assert offline_calls == [True]
    assert len(telegram_bodies) == 1
    assert len(email_bodies) == 1
    assert "/STOP_ALL" not in email_bodies[0]
    assert "Aucune commande d'arrêt n'est disponible via Telegram" in email_bodies[0]


def test_exchange_monitor_no_new_stop_mechanism_added():
    assert "def force_stop" not in EXCHANGE_MONITOR_SRC
    assert "_COMMANDS" not in EXCHANGE_MONITOR_SRC


# ---------------------------------------------------------------------------
# O-02W-PRE-T1-A-R1.1 — KillSwitchHardened owns no thread; callback logs are
# source-honest; the doc distinguishes invoked production paths from
# callbacks that are merely wired.
# ---------------------------------------------------------------------------


def _make_killswitch_hardened(tmp_path):
    from supervision.killswitch_hardened import KillSwitchHardened

    return KillSwitchHardened(state_path=tmp_path / "ks_state.json")


def test_killswitch_hardened_start_creates_no_thread(tmp_path):
    """KillSwitchHardened.start() is a no-op regarding thread creation."""
    import threading

    before = {t.ident for t in threading.enumerate()}
    ks = _make_killswitch_hardened(tmp_path)
    ks.start()
    after = {t.ident for t in threading.enumerate()}
    assert after == before, "KillSwitchHardened.start() must not spawn a thread"


def test_killswitch_hardened_is_thread_alive_always_false(tmp_path):
    ks = _make_killswitch_hardened(tmp_path)
    assert ks.is_thread_alive() is False
    ks.start()
    assert ks.is_thread_alive() is False


def test_killswitch_hardened_owns_no_thread_attribute():
    """Source proof: no threading.Thread is ever constructed in this class."""
    src = (REPO_ROOT / "supervision" / "killswitch_hardened.py").read_text(
        encoding="utf-8"
    )
    assert "threading.Thread(" not in src


def test_advisor_loop_no_thread_interne_claim():
    assert "thread interne du kill switch" not in ADVISOR_LOOP_SRC
    assert "thread Telegram" not in ADVISOR_LOOP_SRC


def test_advisor_loop_kill_switch_comment_describes_only_proven_facts():
    match = re.search(
        r"# Kill switch —.*?\n    _halt_requested = threading\.Event\(\)",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert match, "kill-switch comment block not found"
    block = match.group(0)
    assert "threading.Event" in block
    # Must not claim KillSwitchHardened owns/starts a worker thread.
    assert "KillSwitchHardened" in block
    assert "no-op" in block or "aucun polling" in block or "aucun thread" in block


def test_state_machine_doc_distinguishes_invoked_from_merely_wired_callbacks():
    assert "Chemins source-prouvés invoqués en production" in STATE_MACHINE_DOC
    assert (
        "Chemins source-prouvés câblés, mais NON source-prouvés invoqués en "
        "production" in STATE_MACHINE_DOC
    )


def test_state_machine_doc_does_not_classify_kill_switch_callbacks_as_invoked():
    # Locate the "invoked in production" clause specifically and confirm the
    # four kill-switch callbacks are not listed inside it.
    match = re.search(
        r"Chemins source-prouvés invoqués en production\*\*.*?(?=\*\*Chemins "
        r"source-prouvés câblés)",
        STATE_MACHINE_DOC,
        re.DOTALL,
    )
    assert match, "invoked-in-production clause not found"
    invoked_clause = match.group(0)
    for callback in ("_on_stop_all", "_on_close_all", "_on_safe_mode"):
        assert callback not in invoked_clause, (
            f"{callback} must not be classified as invoked in production"
        )


def test_state_machine_doc_no_longer_claims_stale_telegram_reason_strings_remain():
    # R1 removed the "STOP_ALL telegram" etc. reason strings from
    # advisor_loop.py; the doc must not claim they still exist in the final
    # source.
    assert "STOP_ALL telegram" not in STATE_MACHINE_DOC
    assert "CLOSE_ALL telegram" not in STATE_MACHINE_DOC
    assert "SAFE_MODE telegram" not in STATE_MACHINE_DOC
    for reason_string in ("STOP_ALL telegram", "CLOSE_ALL telegram", "SAFE_MODE telegram"):
        assert reason_string not in ADVISOR_LOOP_SRC


def test_advisor_loop_callback_logs_state_only_that_callback_was_invoked():
    for callback_log in (
        "Callback on_stop_all invoque",
        "Callback on_close_all invoque",
        "Callback on_safe_mode invoque",
    ):
        assert callback_log in ADVISOR_LOOP_SRC


def test_advisor_loop_callback_logs_do_not_claim_telegram_or_operator_origin():
    for match in re.finditer(
        r'log\.(?:critical|warning)\(\s*"\[main\] Callback on_\w+ invoque.*?"\s*\)',
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    ):
        body = match.group(0)
        assert "telegram" not in body.lower()
        assert "opérateur" not in body.lower() and "operateur" not in body.lower()
        assert "recu" not in body.lower()


def test_advisor_loop_callback_mutations_source_keys_and_wiring_unchanged():
    assert '"kill_switch_stop_all"' in ADVISOR_LOOP_SRC
    assert '"kill_switch_close_all"' in ADVISOR_LOOP_SRC
    assert '"kill_switch_safe_mode"' in ADVISOR_LOOP_SRC
    assert "on_stop_all=_on_stop_all" in ADVISOR_LOOP_SRC
    assert "on_close_all=_on_close_all" in ADVISOR_LOOP_SRC
    assert "on_safe_mode=_on_safe_mode" in ADVISOR_LOOP_SRC
    assert "on_resume=_on_resume" in ADVISOR_LOOP_SRC
    assert "OPERATOR_RESUME" in ADVISOR_LOOP_SRC
    assert '_halt_requested.set()' in ADVISOR_LOOP_SRC
    assert 'runtime_authority.request_safe_mode(' in ADVISOR_LOOP_SRC
