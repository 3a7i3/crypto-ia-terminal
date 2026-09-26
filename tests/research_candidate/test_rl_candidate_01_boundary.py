from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "research_candidate"

FORBIDDEN_IMPORT_PREFIXES = (
    "ccxt",
    "requests",
    "urllib",
    "httpx",
    "socket",
    "subprocess",
    "core.advisor_loop",
    "paper_trading.mexc_simulator",
    "paper_trading.ppl_authority_runtime",
    "quant_hedge_ai.agents.execution",
)

FORBIDDEN_CALL_NAMES = {
    "create_order",
    "place_market_order",
    "commit_open",
    "commit_close",
    "start",
    "stop",
    "restart",
    "systemctl",
}


def _modules() -> list[Path]:
    return sorted(ROOT.glob("*.py"))


def test_research_candidate_has_no_runtime_network_or_execution_imports() -> None:
    violations: list[tuple[str, int, str]] = []

    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")

            for name in names:
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append((str(path), node.lineno, name))

    assert not violations


def test_research_candidate_has_no_runtime_execution_calls() -> None:
    violations: list[tuple[str, int, str]] = []

    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue

            if name in FORBIDDEN_CALL_NAMES:
                violations.append((str(path), node.lineno, name))

    assert not violations


def test_research_candidate_identity_does_not_read_environment() -> None:
    violations: list[tuple[str, int, str]] = []

    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                root = node.value
                if isinstance(root, ast.Name) and root.id == "os":
                    violations.append((str(path), node.lineno, node.attr))

            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getenv"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            ):
                violations.append((str(path), node.lineno, "getenv"))

    assert not violations
