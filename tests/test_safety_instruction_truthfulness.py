"""O-02W-PRE-T1-A — regression tests for the safety-instruction truthfulness fixes.

Covers the three source-proven drifts from O-02W-E1 §13:
  1. GLOBAL_STATE_MACHINE.md misattributing SAFE_MODE transitions to Telegram.
  2. ExchangeMonitor's critical email instructing a nonexistent /STOP_ALL command.
  3. advisor_loop.py's /RESUME instructions with no canonical dispatcher.

Behavior-level assertions are used where the code can be exercised without
booting the full advisor loop (ExchangeMonitor). The advisor_loop.py and
GLOBAL_STATE_MACHINE.md properties are message/documentation-integrity
properties that cannot be safely exercised without booting the full advisor,
so they are checked at the source-text level, matching the pattern already
used by the repository's other advisor_loop smoke/message tests.
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


def test_advisor_loop_replacement_messages_avoid_claiming_telegram_control_path():
    # Source-level f-string literals may split across lines (interrupted by
    # a closing/opening quote pair), so tolerate that gap in the match.
    matches = re.findall(
        r'Aucune commande /RESUME ["\s]*n\'est disponible.{0,80}?via Telegram',
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert len(matches) == 3, (
        "each replacement message must explicitly state that no /RESUME "
        "command is available via Telegram, in exactly the three target "
        "locations (degraded, halted, suspended-loop)"
    )


def test_advisor_loop_on_resume_callback_unchanged_behaviorally():
    """The wording fix must not touch _on_resume's actual state mutations."""
    match = re.search(
        r"def _on_resume\(\):.*?(?=\n    def _on_close_all\(\)|\n    kill_switch = )",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    # _on_resume is defined before _on_close_all/_on_safe_mode in source order,
    # so anchor on the next top-level statement instead.
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


def test_advisor_loop_no_new_telegram_command_handler_added():
    assert "_COMMANDS" not in ADVISOR_LOOP_SRC
    assert not re.search(r'"/RESUME":\s*self\.', ADVISOR_LOOP_SRC)


def test_advisor_loop_legitimate_identifiers_preserved():
    assert "RESUME_TRADING" in ADVISOR_LOOP_SRC
    assert '"RESUME_TRADING": 600.0' in ADVISOR_LOOP_SRC
    assert "on_resume=_on_resume" in ADVISOR_LOOP_SRC


# ---------------------------------------------------------------------------
# GLOBAL_STATE_MACHINE.md — SAFE_MODE attribution
# ---------------------------------------------------------------------------


def test_state_machine_doc_no_longer_attributes_safe_mode_to_telegram():
    for line in STATE_MACHINE_DOC.splitlines():
        if "SAFE_MODE" in line and "|" in line and "Vers" not in line:
            assert "KillSwitch / Telegram" not in line, (
                f"SAFE_MODE transition row still attributes to Telegram: {line!r}"
            )


def test_state_machine_doc_names_force_safe_mode_and_force_resume():
    assert "force_safe_mode()" in STATE_MACHINE_DOC
    assert "force_resume()" in STATE_MACHINE_DOC


def test_state_machine_doc_states_no_canonical_caller_exists():
    assert "aucun appelant non-test/non-archive" in STATE_MACHINE_DOC


# ---------------------------------------------------------------------------
# supervision/exchange_monitor.py — /STOP_ALL instruction
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
