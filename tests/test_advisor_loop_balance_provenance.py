"""D-7/R2 — provenance wiring reelle utilisee par CommandCenterBot.

MASTER O-02B-R2 : les tests de formatteur (tests/capital_deployment/) qui
injectent la provenance manuellement ne peuvent pas detecter un defaut de
cablage cote advisor_loop (ex R1 : reference a une variable locale
`_paper_trading_enabled` dont le defaut et l'ensemble truthy divergent de
ceux d'ExecutionEngine.fetch_available_capital()). Ce module teste
directement `core.advisor_loop._balance_provenance_from_mode`, la fonction
pure que `_get_balance_provenance_for_bot()` appelle reellement — donc tout
regression de cablage (nom mal lu, mauvais defaut, mauvais ensemble
truthy) fait echouer ces tests.
"""

from core import advisor_loop


def test_paper_true_yields_paper(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")

    assert advisor_loop._balance_provenance_from_mode("live") == "PAPER"


def test_paper_numeric_one_yields_paper(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "1")

    assert advisor_loop._balance_provenance_from_mode("live") == "PAPER"


def test_paper_yes_yields_paper(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "yes")

    assert advisor_loop._balance_provenance_from_mode("live") == "PAPER"


def test_paper_on_yields_paper(monkeypatch):
    """MASTER R2 : "on" fait partie de l'ensemble truthy d'ExecutionEngine
    mais PAS de celui de la variable `_paper_trading_enabled` d'advisor_loop
    — la regression exacte que R1 a laissee passer."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "on")

    assert advisor_loop._balance_provenance_from_mode("live") == "PAPER"


def test_paper_disabled_with_uppercase_variant_still_paper(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "TRUE")

    assert advisor_loop._balance_provenance_from_mode(None) == "PAPER"


def test_default_env_is_paper_when_unset(monkeypatch):
    """Meme defaut ("true") que ExecutionEngine.fetch_available_capital()."""
    monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)

    assert advisor_loop._balance_provenance_from_mode("live") == "PAPER"


def test_live_mode_yields_real_api_when_paper_disabled(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")

    assert advisor_loop._balance_provenance_from_mode("live") == "REAL_API"


def test_testnet_mode_yields_testnet_api_when_paper_disabled(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")

    assert advisor_loop._balance_provenance_from_mode("testnet") == "TESTNET_API"


def test_paper_mode_string_is_still_paper_when_paper_disabled(monkeypatch):
    """PAPER_TRADING_ENABLED=false mais exec_engine._mode == "paper"
    (pas de cle API configuree) -> toujours PAPER, jamais REAL_API."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")

    assert advisor_loop._balance_provenance_from_mode("paper") == "PAPER"


def test_unrecognized_mode_fails_closed_to_unknown(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")

    assert advisor_loop._balance_provenance_from_mode("something_else") == "UNKNOWN"
    assert advisor_loop._balance_provenance_from_mode(None) == "UNKNOWN"


def test_advisor_loop_source_wires_provenance_through_the_pure_helper():
    """`_get_balance_provenance_for_bot` lives inside `main()` as a closure
    over `exec_engine` and can't be called without running the full
    bootstrap. We assert directly on its source body that it delegates to
    `_balance_provenance_from_mode` (unit-tested above) instead of
    re-deriving provenance from some other divergent local — the exact
    class of bug R1 shipped: reading `_paper_trading_enabled`, a variable
    with a different default and truthy set than
    ExecutionEngine.fetch_available_capital()."""
    import inspect
    import re

    source = inspect.getsource(advisor_loop.main)
    match = re.search(
        r"def _get_balance_provenance_for_bot\(\).*?\n\n",
        source,
        re.DOTALL,
    )
    assert match, "_get_balance_provenance_for_bot not found in advisor_loop.main source"
    body = match.group(0)

    assert "_balance_provenance_from_mode(" in body
    assert "_paper_trading_enabled" not in body
