"""D-7 — Provenance PAPER vs REEL/API dans les panneaux Portfolio Telegram.

O-02B / O-02B-R1 (remediation bornee) : les panneaux ne changent aucune
formule ni source de verite, mais doivent rendre impossible la confusion
entre performance PAPER (KPIs, positions, trades, equity paper) et l'etat
de capital renvoye par get_balances().

MASTER O-02B-R1 : get_balances() N'EST PAS toujours REAL/API — sous
PAPER_TRADING_ENABLED=true, ExecutionEngine.fetch_available_capital()
retourne le solde WalletSync PAPER, quel que soit le nom de la variable
cote advisor_loop ("real_capital"). La provenance doit donc etre
explicitement declaree par get_balance_provenance() (domaine fini PAPER /
REAL_API / TESTNET_API / UNKNOWN), jamais devinee par le formatteur, et
jamais REAL_API par defaut (fail closed).
"""

from types import SimpleNamespace

import pytest

from capital_deployment.command_center_bot import (
    CommandCenterBot,
    CommandDataProvider,
    _fmt_balance,
    _fmt_history,
    _fmt_kpis,
    _fmt_perf,
    _fmt_pnl,
    _fmt_positions,
    _fmt_rapport,
    _fmt_recap,
    _fmt_status,
    _fmt_trades,
    _HELP_TEXT,
)


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


def test_kpis_panel_labeled_paper():
    p = CommandDataProvider(get_kpis=lambda: _kpis(), get_phase=lambda: "F-01")

    text = _fmt_kpis(p)

    assert "KPIs PAPER" in text


def test_status_panel_labels_performance_as_paper():
    p = CommandDataProvider(get_kpis=lambda: _kpis(), get_phase=lambda: "F-01")

    text = _fmt_status(p)

    assert "PERFORMANCE PAPER" in text


def test_positions_panel_labeled_paper():
    p = CommandDataProvider(
        get_positions=lambda: [
            {"symbol": "BTC/USDT", "side": "long", "entry": 100, "current": 101}
        ]
    )

    text = _fmt_positions(p)

    assert "POSITIONS PAPER" in text


def test_trades_panel_labeled_paper():
    p = CommandDataProvider(
        get_trades=lambda: [{"symbol": "BTC/USDT", "side": "long", "pnl": 1.5, "ts": 0}]
    )

    text = _fmt_trades(p)

    assert "TRADES PAPER" in text


def test_history_panel_labeled_paper():
    p = CommandDataProvider(
        get_trades=lambda: [{"symbol": "BTC/USDT", "side": "long", "pnl": 1.5, "ts": 0}]
    )

    text = _fmt_history(p)

    assert "HISTORIQUE PAPER" in text


def test_perf_panel_labeled_paper():
    p = CommandDataProvider(
        get_trades=lambda: [
            {"symbol": "BTC/USDT", "side": "long", "pnl": 1.5, "ts": 0},
            {"symbol": "ETH/USDT", "side": "long", "pnl": -0.5, "ts": 0},
        ]
    )

    text = _fmt_perf(p)

    assert "PnL CUMULATIF PAPER" in text


def test_recap_panel_labeled_paper():
    import time

    p = CommandDataProvider(
        get_trades=lambda: [
            {"symbol": "BTC/USDT", "side": "long", "pnl": 1.5, "ts": time.time()}
        ]
    )

    text = _fmt_recap(p, days=7)

    assert "RECAP PAPER" in text


# ── Provenance de get_balances() (D-7/R1) : jamais devinee ─────────────────


def test_balance_panel_paper_provenance():
    p = CommandDataProvider(
        get_balances=lambda: {"spot": 10.0, "futures": 0.0},
        get_balance_provenance=lambda: "PAPER",
    )

    text = _fmt_balance(p)

    assert "WALLET MACHINE PAPER" in text
    assert "RÉEL" not in text


def test_balance_panel_real_api_provenance():
    p = CommandDataProvider(
        get_balances=lambda: {"spot": 250.0, "futures": 0.0},
        get_balance_provenance=lambda: "REAL_API",
    )

    text = _fmt_balance(p)

    assert "RÉEL / API" in text


def test_balance_panel_testnet_provenance():
    p = CommandDataProvider(
        get_balances=lambda: {"spot": 250.0, "futures": 0.0},
        get_balance_provenance=lambda: "TESTNET_API",
    )

    text = _fmt_balance(p)

    assert "TESTNET" in text
    assert "RÉEL / API" not in text


def test_balance_panel_unknown_provenance_is_conservative():
    """Sans provenance declaree, jamais REAL_API par defaut (fail closed)."""
    p = CommandDataProvider(get_balances=lambda: {"spot": 250.0, "futures": 0.0})

    text = _fmt_balance(p)

    assert "RÉEL" not in text
    assert "PAPER" not in text  # pas davantage suppose PAPER que REAL_API
    assert "NON CERTIFIÉE" in text


def test_balance_panel_unrecognized_provenance_code_is_conservative():
    p = CommandDataProvider(
        get_balances=lambda: {"spot": 250.0, "futures": 0.0},
        get_balance_provenance=lambda: "SOMETHING_ELSE",
    )

    text = _fmt_balance(p)

    assert "RÉEL" not in text
    assert "NON CERTIFIÉE" in text


def test_balance_panel_broken_provenance_callback_is_conservative():
    def _boom():
        raise RuntimeError("mode indisponible")

    p = CommandDataProvider(
        get_balances=lambda: {"spot": 250.0, "futures": 0.0},
        get_balance_provenance=_boom,
    )

    text = _fmt_balance(p)

    assert "RÉEL" not in text
    assert "NON CERTIFIÉE" in text


# ── /pnl : deux populations, provenance declaree pour la seconde ───────────


def test_pnl_panel_separates_paper_performance_from_declared_provenance():
    p = CommandDataProvider(
        get_kpis=lambda: _kpis(),
        get_balances=lambda: {"spot": 250.0, "futures": 0.0},
        get_balance_provenance=lambda: "REAL_API",
    )

    text = _fmt_pnl(p)

    assert "PERFORMANCE PAPER" in text
    assert "RÉEL / API" in text
    perf_idx = text.index("PERFORMANCE PAPER")
    real_idx = text.index("RÉEL")
    assert perf_idx < real_idx
    # Pas de PnL combine synthetique : le total de balances ne se fait pas
    # passer pour un PnL, il reste etiquete comme capital/solde declare.
    assert "Capital / solde" in text


def test_pnl_panel_second_population_reflects_paper_provenance_not_hardcoded():
    """MASTER B1 : la 2e section de /pnl ne doit jamais etre figee sur REAL/API."""
    p = CommandDataProvider(
        get_kpis=lambda: _kpis(),
        get_balances=lambda: {"spot": 10.0, "futures": 0.0},
        get_balance_provenance=lambda: "PAPER",
    )

    text = _fmt_pnl(p)

    assert "PERFORMANCE PAPER" in text
    assert "WALLET MACHINE PAPER" in text
    assert "RÉEL / API" not in text


def test_pnl_panel_without_balances_only_shows_paper():
    p = CommandDataProvider(get_kpis=lambda: _kpis())

    text = _fmt_pnl(p)

    assert "PERFORMANCE PAPER" in text
    assert "RÉEL" not in text and "REEL" not in text


def test_automatic_report_labels_paper_sections():
    p = CommandDataProvider(
        get_phase=lambda: "F-01",
        get_kpis=lambda: _kpis(),
        get_positions=lambda: [],
        get_trades=lambda: [
            {"symbol": "BTC/USDT", "side": "long", "pnl": 1.5, "ts": 0}
        ],
    )

    text = _fmt_rapport(p)

    assert "PERFORMANCE PAPER" in text
    assert "POSITIONS PAPER" in text
    assert "DERNIERS TRADES PAPER" in text


def test_help_text_documents_telegram_as_read_only():
    assert "READ-ONLY" in _HELP_TEXT
    assert "2026-08-28" in _HELP_TEXT


def test_help_text_does_not_advertise_control_commands_as_active():
    # Les commandes d'ecriture ne doivent plus apparaitre comme des entrees
    # de menu operationnelles (une mention dans la note de desactivation
    # en prose est attendue et ne compte pas).
    menu_section = _HELP_TEXT.split("Controle :", 1)[0]
    menu_lines = [ln for ln in menu_section.splitlines() if ln.strip().startswith("/")]
    for ln in menu_lines:
        for blocked in ("/set ", "/pause", "/resume", "/setphase", "/maxorder",
                        "/reset", "/restart", "/confirm", "/cancel"):
            assert not ln.strip().startswith(blocked), ln


# ── Route-level control-command block regression (D-7 mission requirement) ─


def _bot_with_recorder(monkeypatch):
    """Bot dont send() est stubbe — pas d'appel Telegram reseau."""
    provider = CommandDataProvider(
        set_param=lambda name, val: (_ for _ in ()).throw(
            AssertionError(f"set_param must never be called via Telegram: {name}={val}")
        ),
        reset_kpis=lambda: (_ for _ in ()).throw(
            AssertionError("reset_kpis must never be called via Telegram")
        ),
    )
    bot = CommandCenterBot(token="x", chat_id="42", provider=provider)
    sent: list[str] = []
    monkeypatch.setattr(bot, "send", lambda text: sent.append(text) or True)
    return bot, sent


def _msg(text: str) -> dict:
    return {"chat": {"id": "42"}, "text": text}


@pytest.mark.parametrize(
    "command",
    [
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
    ],
)
def test_control_commands_are_blocked_and_never_mutate(monkeypatch, command):
    bot, sent = _bot_with_recorder(monkeypatch)

    bot._route(_msg(command))

    assert len(sent) == 1
    assert "désactivée" in sent[0] or "desactivee" in sent[0]
    assert "2026-08-28" in sent[0]


def test_read_only_command_still_works_alongside_blocked_ones(monkeypatch):
    provider = CommandDataProvider(get_kpis=lambda: _kpis(), get_phase=lambda: "F-01")
    bot = CommandCenterBot(token="x", chat_id="42", provider=provider)
    sent: list[str] = []
    monkeypatch.setattr(bot, "send", lambda text: sent.append(text) or True)

    bot._route(_msg("/kpis"))

    assert len(sent) == 1
    assert "KPIs PAPER" in sent[0]
