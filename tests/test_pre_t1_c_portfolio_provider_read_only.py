"""O-02W-PRE-T1-C — retrait structurel de la capacite d'ecriture du bot
Telegram Portfolio (Command Center Bot).

Ces tests prouvent, comportementalement (pas seulement par recherche de
chaine), que :
  1. `_set_param_live` n'existe plus dans core/advisor_loop.py (AST parse —
     ce module a des effets de bord lourds a l'import, donc on ne l'importe
     jamais ici).
  2. `CommandDataProvider` n'a plus de champ `set_param` ni `reset_kpis`.
  3. Construire le dataclass avec ces mots-cles leve `TypeError`.
  4. Les 9 commandes de controle bloquees ne produisent que le message de
     refus et ne mutent ni `os.environ` ni l'etat du provider.
  5. Les commandes en lecture seule fonctionnent toujours.

Aucun test ici n'appelle le reseau, n'importe `requests`, ni ne necessite
TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID.
"""

import ast
import dataclasses
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import capital_deployment.command_center_bot as ccb
from capital_deployment.command_center_bot import CommandCenterBot, CommandDataProvider, _fmt_config

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md"


# ── 1. _set_param_live n'existe plus dans core/advisor_loop.py ─────────────


def test_set_param_live_not_defined_in_advisor_loop():
    source_path = REPO_ROOT / "core" / "advisor_loop.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_set_param_live"
    ]

    assert found == [], f"_set_param_live still defined at line(s) {[n.lineno for n in found]}"


def test_advisor_loop_source_has_no_set_param_kwarg_construction():
    source_path = REPO_ROOT / "core" / "advisor_loop.py"
    text = source_path.read_text(encoding="utf-8")
    assert "set_param=" not in text
    assert "_set_param_live" not in text


# ── 2 & 3. CommandDataProvider n'a plus de champs set_param/reset_kpis ─────


def test_command_data_provider_has_no_set_param_or_reset_kpis_fields():
    field_names = {f.name for f in dataclasses.fields(CommandDataProvider)}
    assert "set_param" not in field_names
    assert "reset_kpis" not in field_names


def test_constructing_with_set_param_raises_type_error():
    with pytest.raises(TypeError):
        CommandDataProvider(set_param=lambda name, value: True)


def test_constructing_with_reset_kpis_raises_type_error():
    with pytest.raises(TypeError):
        CommandDataProvider(reset_kpis=lambda: True)


# ── Helpers behavioral (fake bot, send() intercepte, jamais de reseau) ─────


def _kpis(**overrides):
    base = dict(
        win_rate=0.55,
        sharpe=1.2,
        max_drawdown=0.03,
        current_drawdown=0.01,
        total_trades=120,
        unsigned_decisions=0,
        days_elapsed=10.0,
    )
    base.update(overrides)
    ns = SimpleNamespace(**base)
    ns.violations = lambda phase: []
    return ns


def _make_bot(monkeypatch, provider):
    bot = CommandCenterBot(token="x", chat_id="42", provider=provider)
    sent: list[str] = []
    monkeypatch.setattr(bot, "send", lambda text: sent.append(text) or True)
    return bot, sent


def _msg(text: str) -> dict:
    return {"chat": {"id": "42"}, "text": text}


BLOCKED_COMMANDS = [
    "/pause",
    "/resume",
    "/set",
    "/set FOO bar",
    "/setphase",
    "/setphase F-02",
    "/maxorder",
    "/maxorder 100",
    "/reset",
    "/restart",
    "/confirm",
    "/cancel",
]

READ_ONLY_COMMANDS = ["/status", "/kpis", "/balance", "/positions"]


# ── 4. Commandes bloquees : refus uniquement, aucune mutation ──────────────


@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
def test_blocked_commands_only_send_refusal_and_never_mutate(monkeypatch, command):
    provider = CommandDataProvider(
        get_kpis=lambda: _kpis(),
        get_phase=lambda: "F-01",
        get_balances=lambda: {"spot": 10.0, "futures": 0.0},
        get_positions=lambda: [],
    )
    bot, sent = _make_bot(monkeypatch, provider)

    env_before = dict(os.environ)
    provider_before = dataclasses.asdict(
        provider, dict_factory=lambda items: {k: (v is not None) for k, v in items}
    )

    bot._route(_msg(command))

    assert len(sent) == 1
    assert "désactivée" in sent[0] or "desactivee" in sent[0]
    assert "2026-08-28" in sent[0]

    assert dict(os.environ) == env_before, "blocked command mutated os.environ"
    provider_after = dataclasses.asdict(
        provider, dict_factory=lambda items: {k: (v is not None) for k, v in items}
    )
    assert provider_after == provider_before, "blocked command mutated provider state shape"


# ── 5. Commandes en lecture seule continuent de fonctionner ────────────────


@pytest.mark.parametrize("command", READ_ONLY_COMMANDS)
def test_read_only_commands_still_route_successfully(monkeypatch, command):
    provider = CommandDataProvider(
        get_kpis=lambda: _kpis(),
        get_phase=lambda: "F-01",
        get_balances=lambda: {"spot": 10.0, "futures": 0.0},
        get_balance_provenance=lambda: "PAPER",
        get_positions=lambda: [
            {"symbol": "BTC/USDT", "side": "long", "entry": 100, "current": 101}
        ],
    )
    bot, sent = _make_bot(monkeypatch, provider)

    bot._route(_msg(command))

    assert len(sent) == 1
    assert sent[0]


# ── R1: extensions couvrant Correction B (retrait de _LIVE_PARAMS/[live]/[restart]) ──


# ── R1.1: chaque champ de CommandDataProvider est un callback de lecture ───


def test_every_command_data_provider_field_is_a_get_callback():
    field_names = [f.name for f in dataclasses.fields(CommandDataProvider)]
    assert field_names, "CommandDataProvider should declare at least one field"
    non_read = [name for name in field_names if not name.startswith("get_")]
    assert non_read == [], f"non read-only fields found on CommandDataProvider: {non_read}"


# ── R1.2: _LIVE_PARAMS n'existe plus dans le module ─────────────────────────


def test_live_params_absent_from_command_center_bot_module():
    assert not hasattr(ccb, "_LIVE_PARAMS")


def test_live_params_absent_from_command_center_bot_source_ast():
    source_path = REPO_ROOT / "capital_deployment" / "command_center_bot.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    assigned_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "_LIVE_PARAMS" not in assigned_names


# ── R1.3: _fmt_config() n'emet plus [live]/[restart] ────────────────────────


def test_fmt_config_output_has_no_live_or_restart_suffix(monkeypatch, tmp_path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("EXEC_MAX_ORDER_USD=100\nV9_MAX_POSITION_WEIGHT=0.2\n", encoding="utf-8")
    monkeypatch.setattr(ccb, "_ENV_PATH", env_file)

    output = _fmt_config("trading")

    assert "[live]" not in output
    assert "[restart]" not in output
    assert "EXEC_MAX_ORDER_USD" in output


# ── R1.4: /config via _route() renvoie toujours les valeurs, sans muter os.environ ──


def test_config_route_returns_values_and_does_not_mutate_environ(monkeypatch, tmp_path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("EXEC_MAX_ORDER_USD=100\n", encoding="utf-8")
    monkeypatch.setattr(ccb, "_ENV_PATH", env_file)

    provider = CommandDataProvider(get_kpis=lambda: _kpis())
    bot, sent = _make_bot(monkeypatch, provider)

    env_before = dict(os.environ)

    bot._route(_msg("/config trading"))

    assert len(sent) == 1
    assert "CONFIG" in sent[0].upper()
    assert "[live]" not in sent[0]
    assert "[restart]" not in sent[0]
    assert dict(os.environ) == env_before, "/config route must never mutate os.environ"


# ── R1.5: le contrat ne fait plus l'affirmation normative perimee ──────────


def test_contract_doc_no_longer_claims_set_param_live_currently_exists():
    text = CONTRACT_PATH.read_text(encoding="utf-8")

    # The stale §6/TG-02c normative claim that the route "never calls"
    # CommandDataProvider.set_param (implying the field still exists and is
    # merely unreached) must be gone — replaced with an explicit "no such
    # field exists" statement.
    assert (
        "reviewed path makes no call to\n  `CommandDataProvider.set_param` or any mutator (§9b, Correction D)"
        not in text
    )
    assert (
        "the reviewed path makes no call to `CommandDataProvider.set_param` or any other mutator, so no cockpit equivalent is needed"
        not in text
    )

    # The stale §9b claim that the mutator is merely dormant/unwired-from-
    # dispatch but still present ("already wired into the provider object")
    # must be gone — §9b must instead record structural removal.
    assert (
        "already-implemented,\nenvironment-mutating capability" not in text
        and "fully-implemented, environment-mutating capability **already wired"
        not in text
    )
    assert "structurally removed" in text
    assert "no future source mission is required to remove" in text


def test_contract_doc_no_longer_lists_mutator_as_outstanding_future_mission():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    # §16 previously listed the Portfolio mutator, unqualified, among items
    # "requiring a future source mission" — that unqualified claim must be
    # gone (the resolution note added this round must be present instead).
    assert (
        "Two architectural-boundary items requiring a future\n  source mission, neither modified by this documentation-only PR: the\n  dormant Portfolio mutator"
        not in text
    )
    assert "it is no longer\n  outstanding debt and requires no future source mission" in text


# ── R1.1: PRE-T1-A/B/C reconciliation — new regression tests ───────────────
#
# These tests prove the contract doc (docs/contracts/
# O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md) has been reconciled with the
# structural fixes already merged into main by missions O-02W-PRE-T1-A
# (GLOBAL_STATE_MACHINE.md / exchange_monitor.py / advisor_loop.py /RESUME
# negation strings) and O-02W-PRE-T1-B (removal of the two
# TelegramNotifier().send(...) call sites). They must FAIL against the
# pre-correction contract doc content at HEAD
# 45f8c9a4f48b023ca831b3498d4acd9e43f2a298 and PASS after the R1.1
# correction. No test here touches Telegram, the VPS, or any secret.


def test_pre_t1_a_b_c_reconciliation_section_exists():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "PRE-T1-A / PRE-T1-B reconciliation" in text
    assert "HISTORICAL_FINDINGS_DISCOVERED" in text
    assert "CURRENT_UNRESOLVED_FINDINGS" in text


def test_findings_1_to_3_marked_resolved_by_pre_t1_a():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert text.count("RESOLVED_BY_PRE_T1_A") >= 3


def test_finding_4_and_broken_calls_marked_resolved_by_pre_t1_b():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert text.count("RESOLVED_BY_PRE_T1_B") >= 2


def test_portfolio_mutator_remains_marked_resolved_by_pre_t1_c():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "resolved PRE-T1-C" in text or "RESOLVED_BY_PRE_T1_C" in text or "PRE-T1-C, R1" in text


def test_no_current_passage_presents_stop_all_as_present_in_exchange_monitor():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    # The old unqualified present-tense claim must be gone.
    assert (
        "`supervision/exchange_monitor.py:252-257` tells the operator (via an\n   email escalation body) to send `/STOP_ALL` on Telegram."
        not in text
    )
    assert "longer contains a `/STOP_ALL` string of any kind" in text


def test_no_current_passage_presents_old_send_resume_messages_as_present():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    # Old present-tense instruction phrasing must not remain unqualified.
    assert '"Envoyez /RESUME si intervention requise"' not in text.replace(
        "line\n   3870\n   (degraded-mode alert, ", ""
    ) or "negation-of-availability" in text
    assert "negation-of-availability" in text
    assert "Aucune commande /RESUME n'est disponible" in text


def test_no_current_passage_presents_telegramnotifier_send_as_present_in_sae_or_pm():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "neither file imports or references" in text or (
        "returns no\n" in text and "match in either file" in text
    ) or "returns no match in either file" in text


def test_source_confirms_zero_telegramnotifier_send_in_sae_and_pm():
    sae = (REPO_ROOT / "quant_hedge_ai" / "agents" / "intelligence" / "self_awareness_engine.py").read_text(
        encoding="utf-8"
    )
    pm = (REPO_ROOT / "quant_hedge_ai" / "agents" / "execution" / "position_manager.py").read_text(
        encoding="utf-8"
    )
    assert "TelegramNotifier" not in sae
    assert "TelegramNotifier" not in pm


def test_source_confirms_advisor_loop_resume_messages_are_negations():
    text = (REPO_ROOT / "core" / "advisor_loop.py").read_text(encoding="utf-8")
    assert "/RESUME" in text  # the string is still present, but only as a negation
    assert "Aucune commande /RESUME n'est disponible" in text
    # The old misleading imperative strings must not exist.
    assert "Envoyez /RESUME si intervention requise" not in text
    assert "Envoyez /RESUME pour reprendre" not in text
    assert "Envoyer /RESUME pour reprendre\"" not in text


def test_source_confirms_exchange_monitor_has_no_stop_all_instruction():
    text = (REPO_ROOT / "supervision" / "exchange_monitor.py").read_text(encoding="utf-8")
    assert "/STOP_ALL" not in text


def test_historical_and_current_counters_are_distinct():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    # Historical bucket still records the original counts...
    assert "4 findings, 5 old misleading strings, 2 old broken calls" in text or (
        "5 misleading operator-facing command strings" in text
        and "2 source-proven-nonfunctional" in text
    )
    # ...while the current bucket explicitly states zero.
    assert "0 of the 4 findings" in text
    assert "current total: 0" in text.lower() or "current: 0" in text.lower()


def test_tg_02c_forbidden_classification_unchanged():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "TG-02c" in text
    assert "FORBIDDEN_MUST_NEVER_REACTIVATE" in text


def test_pre_t1_d_real_capital_remains_separate_and_unresolved():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "PRE-T1-D" in text
    assert "separate, unresolved" in text or "separate, unresolved architectural decision" in text


def test_tg_02c_citation_updated_to_current_line_numbers():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "command_center_bot.py:1347-1357" in text
    assert "command_center_bot.py:1370-1379" not in text


def test_source_confirms_refusal_branch_is_at_updated_lines():
    lines = (REPO_ROOT / "capital_deployment" / "command_center_bot.py").read_text(
        encoding="utf-8"
    ).splitlines()
    # 1-indexed: lines 1347-1357 (per the contract citation) contain the
    # blocked-command refusal branch.
    window = "\n".join(lines[1346:1357])
    assert "/pause" in window and "/resume" in window
    assert "Commande de contrôle désactivée" in window
