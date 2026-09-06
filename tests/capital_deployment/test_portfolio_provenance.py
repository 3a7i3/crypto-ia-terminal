"""D-7 — Provenance PAPER vs REEL/API dans les panneaux Portfolio Telegram.

O-02B (remediation bornee) : les panneaux ne changent aucune formule ni
source de verite, mais doivent rendre impossible la confusion entre
performance PAPER (KPIs, positions, trades, equity paper) et etat de
capital REEL/API (get_balances()). Voir docs/architecture/... et le
rapport O-02A pour le defect D-7.
"""

from types import SimpleNamespace

from capital_deployment.command_center_bot import (
    CommandDataProvider,
    _fmt_balance,
    _fmt_history,
    _fmt_kpis,
    _fmt_pnl,
    _fmt_positions,
    _fmt_rapport,
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


def test_balance_panel_labeled_real_api():
    p = CommandDataProvider(get_balances=lambda: {"spot": 250.0, "futures": 0.0})

    text = _fmt_balance(p)

    assert "RÉEL / API" in text or "REEL / API" in text
    assert "PAPER" not in text


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


def test_pnl_panel_separates_paper_performance_from_real_account():
    """/pnl : deux populations visiblement distinctes, jamais fusionnees."""
    p = CommandDataProvider(
        get_kpis=lambda: _kpis(),
        get_balances=lambda: {"spot": 250.0, "futures": 0.0},
    )

    text = _fmt_pnl(p)

    assert "PERFORMANCE PAPER" in text
    assert "RÉEL / API" in text or "REEL / API" in text
    perf_idx = text.index("PERFORMANCE PAPER")
    real_idx = text.index("RÉEL" if "RÉEL" in text else "REEL")
    assert perf_idx < real_idx
    # Pas de PnL combine synthetique : le total de balances ne se fait pas
    # passer pour un PnL, il reste etiquete comme capital/solde du compte reel.
    assert "Capital / solde" in text


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
