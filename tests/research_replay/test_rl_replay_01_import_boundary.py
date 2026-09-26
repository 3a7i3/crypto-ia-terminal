from __future__ import annotations

import ast
from pathlib import Path

import research_replay.factual as factual
import research_replay.publication as publication

_FORBIDDEN_IMPORT_PREFIXES = (
    "paper_trading.durable_event_store",
    "paper_trading.ppl_authority_runtime",
    "core.advisor_loop",
    "paper_trading.mexc_simulator",
    "quant_hedge_ai.agents.execution.execution_engine",
    "dip.core.store",
    "src.telegram",
    "supervision",
    "requests",
    "httpx",
    "websockets",
)


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _assert_no_forbidden_imports(path: Path) -> None:
    imports = _module_imports(path)
    violations = sorted(
        imported
        for imported in imports
        if any(
            imported == prefix or imported.startswith(prefix + ".")
            for prefix in _FORBIDDEN_IMPORT_PREFIXES
        )
    )
    assert violations == []


def _assert_no_runtime_mutation_symbols(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    forbidden_symbols = (
        "DurableEventStore",
        "PPLAuthorityRuntime",
        "MexcSimulator",
        "append_event(",
        "load_epoch(",
        "systemctl",
        "sendMessage",
        "DIPStore",
    )
    hits = [symbol for symbol in forbidden_symbols if symbol in source]
    assert hits == []


def test_factual_replay_has_no_forbidden_runtime_imports() -> None:
    _assert_no_forbidden_imports(Path(factual.__file__).resolve())


def test_publication_has_no_forbidden_runtime_imports() -> None:
    _assert_no_forbidden_imports(Path(publication.__file__).resolve())


def test_factual_replay_source_contains_no_runtime_mutation_symbols() -> None:
    _assert_no_runtime_mutation_symbols(Path(factual.__file__).resolve())


def test_publication_source_contains_no_runtime_mutation_symbols() -> None:
    _assert_no_runtime_mutation_symbols(Path(publication.__file__).resolve())
