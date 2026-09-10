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
    # Auto and named source-proven call-site paths must be named explicitly.
    assert "report_error()" in STATE_MACHINE_DOC
    assert "request_safe_mode(" in STATE_MACHINE_DOC
    assert "core/invariants.py" in STATE_MACHINE_DOC
    # The doc must not overclaim "no call site at all" for the class - it
    # must scope the "no call site" statement to the specific force_*
    # convenience methods, since request_safe_mode()/report_error() do have
    # SOURCE_PROVEN call sites elsewhere.
    assert "instance jetable" in STATE_MACHINE_DOC
    assert "aucun site d'appel non-test/non-archive" in STATE_MACHINE_DOC


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
    body = _operator_resume_event_body_flat()
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


def test_state_machine_doc_distinguishes_source_proven_call_sites_from_wired_callbacks():
    """R1.2: the doc must bound its claim to call-site *presence*, not
    observed production execution — replaces the R1.1 test that required
    the overclaiming phrase "Chemins source-prouvés invoqués en production".
    """
    assert (
        "Sites d'appel explicites présents dans le code runtime "
        "non-test/non-archive" in STATE_MACHINE_DOC
    )
    assert (
        "Callbacks enregistrés (câblage `SOURCE_PROVEN`), sans site d'appel "
        "invoquant le callback trouvé" in STATE_MACHINE_DOC
    )


def test_state_machine_doc_does_not_classify_kill_switch_callbacks_as_call_sites():
    # Locate the "explicit call sites" clause specifically and confirm the
    # four kill-switch callbacks are not listed inside it as call sites.
    match = re.search(
        r"Sites d'appel explicites présents dans le code runtime "
        r"non-test/non-archive\*\*.*?(?=\*\*Callbacks enregistrés)",
        STATE_MACHINE_DOC,
        re.DOTALL,
    )
    assert match, "explicit-call-sites clause not found"
    call_site_clause = match.group(0)
    for callback in ("_on_stop_all", "_on_close_all", "_on_safe_mode"):
        assert callback not in call_site_clause, (
            f"{callback} must not be classified as a source-proven call site"
        )


def test_state_machine_doc_rejects_overclaim_phrases():
    """None of the observed-execution overclaims from R1/R1.1 may remain."""
    for phrase in (
        "invoqués en production",
        "invoquée en production",
        "appelé en production",
        "appelants runtime de production",
        "appelant runtime de production",
        "code mort",
        "inatteignable",
    ):
        assert phrase not in STATE_MACHINE_DOC, (
            f"overclaiming phrase still present: {phrase!r}"
        )


def test_state_machine_doc_uses_source_proven_runtime_unknown_framework():
    assert "SOURCE_PROVEN" in STATE_MACHINE_DOC
    assert "RUNTIME_UNKNOWN" in STATE_MACHINE_DOC
    # The legend must explicitly state that call-site presence proves only
    # source reachability, not deployment/execution.
    assert "ne sont prouvés par aucune inspection de dépôt" in STATE_MACHINE_DOC


def test_state_machine_doc_callback_registration_not_equated_to_invocation():
    assert (
        "Ne jamais décrire l'enregistrement d'un callback" in STATE_MACHINE_DOC
    )
    assert "comme un site d'appel de ce callback" in STATE_MACHINE_DOC


def test_state_machine_doc_on_close_all_has_no_invoker_found_bounded_claim():
    """R1.2 Correction B: _on_close_all's non-invocation must be phrased as
    'no invoker found' (RUNTIME_UNKNOWN), not as an absolute 'dead code /
    unreachable' claim.
    """
    match = re.search(
        r"`on_close_all` est enregistré au constructeur.*?exécution réelle "
        r"reste `RUNTIME_UNKNOWN`, sans que cela constitue une preuve "
        r"d'impossibilité absolue\.",
        STATE_MACHINE_DOC,
        re.DOTALL,
    )
    assert match, "_on_close_all bounded-claim sentence not found"
    clause = match.group(0)
    assert "aucune méthode de `KillSwitchHardened` n'invoque ce callback stocké" in clause
    assert "aucun site d'appel non-test/non-archive invoquant `_on_close_all`" in clause
    assert "code mort" not in clause
    assert "inatteignable" not in clause


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


# ---------------------------------------------------------------------------
# O-02W-PRE-T1-A-R1.3 — the BlackBox OPERATOR_RESUME event must not
# self-contradict (it fires because _on_resume was just invoked, so it
# cannot also assert no caller is known), and static comments must use
# bounded "no call site found" language rather than a claim of knowledge
# about deployed production execution.
# ---------------------------------------------------------------------------


def _flatten_comment(text: str) -> str:
    """Join wrapped `#`-prefixed comment lines into one contiguous string,
    so a multi-word phrase spanning a line wrap can be matched literally."""
    lines = [line.split("#", 1)[-1].strip() for line in text.splitlines()]
    return " ".join(line for line in lines if line)


def _operator_resume_event_body() -> str:
    # Non-greedy up to a comma followed by the call's own closing paren on
    # its own line — the description string itself may contain parentheses
    # (e.g. "(operateur, Telegram, ou autre)"), so a naive `.*?\)` stops at
    # the first inner paren instead of the call's actual end.
    match = re.search(
        r'record_system_event\(\s*"OPERATOR_RESUME",(.*?),\s*\n\s*\)',
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert match, "OPERATOR_RESUME record_system_event call not found"
    return match.group(1)


def _operator_resume_event_body_flat() -> str:
    """Same as _operator_resume_event_body(), but with the adjacent string
    literal fragments joined into one contiguous string, so a phrase
    spanning a line wrap (e.g. "non "/"etablie") can be matched literally."""
    raw = _operator_resume_event_body()
    # Strip quote characters and excess whitespace between fragments.
    return " ".join(raw.replace('"', " ").split())


def test_blackbox_event_states_on_resume_was_invoked():
    body = _operator_resume_event_body()
    assert "_on_resume" in body
    assert "invoque" in body.lower()


def test_blackbox_event_states_origin_not_established_without_inferring_one():
    body = _operator_resume_event_body_flat()
    assert "non etablie" in body or "non établie" in body
    assert "n'inferer ni origine operateur ni origine" in body or (
        "n'inférer ni origine opérateur ni origine" in body
    )


def test_blackbox_event_states_operator_resume_is_compatibility_identifier():
    body = _operator_resume_event_body()
    assert "compatibilite BlackBox" in body or "compatibilité BlackBox" in body
    assert "legacy" in body.lower() or "preuve d'action operateur" in body or (
        "preuve d'action opérateur" in body
    )


def test_blackbox_event_does_not_assert_no_known_caller():
    """The event fires because _on_resume just ran — it cannot also claim,
    inside its own description, that the callback has no known caller.
    That was the R1.3 self-contradiction: an emitted runtime event
    asserting a static "no caller found" repository-search conclusion.
    """
    body = _operator_resume_event_body()
    for forbidden in (
        "aucun appelant",
        "aucun caller",
        "aucun appelant runtime de production",
        "n'a aucun appelant",
    ):
        assert forbidden not in body, (
            f"OPERATOR_RESUME event description must not contain {forbidden!r} "
            "— a static no-caller claim cannot coexist with the event's own "
            "emission, which proves the callback was just invoked"
        )


def test_advisor_loop_no_remaining_appelant_runtime_de_production_phrase():
    for phrase in (
        "appelant runtime de production connu",
        "appelants runtime de production",
        "aucun appelant runtime de production",
    ):
        assert phrase not in ADVISOR_LOOP_SRC, (
            f"advisor_loop.py must not contain the overclaiming phrase "
            f"{phrase!r}"
        )


def test_advisor_loop_static_comments_use_bounded_call_site_language():
    """The _on_stop_all callback comment and the suspended-loop _on_resume
    explanation must state only that no non-test/non-archive call site to
    the relevant force_*() method was found — not a claim of knowledge
    about whether the callback actually ran in a deployed process.
    """
    on_stop_all_match = re.search(
        r"def _on_stop_all\(\):(.*?)\n        _halt_requested\.set\(\)",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert on_stop_all_match, "_on_stop_all comment block not found"
    on_stop_all_comment = _flatten_comment(on_stop_all_match.group(1))
    assert "site d'appel non-test/non-archive" in on_stop_all_comment
    assert "force_halt()" in on_stop_all_comment
    assert "invocation réelle en exécution reste inconnue" in on_stop_all_comment
    assert "appelant runtime de production" not in on_stop_all_comment

    suspended_loop_match = re.search(
        r"# Attendre que _halt_requested soit levé.*?procédure de reprise "
        r"opérateur n'est documentée/prouvée par le\s*\n\s*# code source pour "
        r"ce chemin\)\.",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert suspended_loop_match, "suspended-loop _on_resume comment not found"
    suspended_loop_comment = _flatten_comment(suspended_loop_match.group(0))
    assert "site d'appel non-test/non-archive" in suspended_loop_comment
    assert "force_resume()" in suspended_loop_comment
    assert "invocation réelle en exécution reste inconnue" in suspended_loop_comment
    assert "appelant runtime de production" not in suspended_loop_comment


def test_advisor_loop_on_resume_definition_comment_uses_bounded_language():
    match = re.search(
        r"def _on_resume\(\):(.*?)\n        _halt_requested\.clear\(\)",
        ADVISOR_LOOP_SRC,
        re.DOTALL,
    )
    assert match, "_on_resume definition comment block not found"
    comment = match.group(1)
    assert "site d'appel non-test/non-archive" in comment
    assert "force_resume()" in comment
    assert "appelant runtime de production" not in comment
    assert "appelant non-test/non-archive dans le code" not in comment


def test_r1_3_callback_wiring_mutations_event_identifier_and_control_flow_unchanged():
    """Nothing behavioral moved this round — only comments/event text."""
    assert "on_stop_all=_on_stop_all" in ADVISOR_LOOP_SRC
    assert "on_close_all=_on_close_all" in ADVISOR_LOOP_SRC
    assert "on_safe_mode=_on_safe_mode" in ADVISOR_LOOP_SRC
    assert "on_resume=_on_resume" in ADVISOR_LOOP_SRC
    assert '"kill_switch_stop_all"' in ADVISOR_LOOP_SRC
    assert '"kill_switch_close_all"' in ADVISOR_LOOP_SRC
    assert '"kill_switch_safe_mode"' in ADVISOR_LOOP_SRC
    assert '"OPERATOR_RESUME"' in ADVISOR_LOOP_SRC
    assert "_halt_requested.clear()" in ADVISOR_LOOP_SRC
    assert "runtime_authority.clear_all_safe_mode_requests()" in ADVISOR_LOOP_SRC
    assert "STOP_ALL programmatique (callback KillSwitchHardened)" in ADVISOR_LOOP_SRC
    assert "CLOSE_ALL programmatique (callback KillSwitchHardened)" in ADVISOR_LOOP_SRC
    assert "SAFE_MODE programmatique (callback KillSwitchHardened)" in ADVISOR_LOOP_SRC
    assert "Callback on_stop_all invoque" in ADVISOR_LOOP_SRC
    assert "Callback on_close_all invoque" in ADVISOR_LOOP_SRC
    assert "Callback on_safe_mode invoque" in ADVISOR_LOOP_SRC
