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
