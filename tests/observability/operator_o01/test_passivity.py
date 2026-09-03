"""Mission §31: passive modules must have no import-time filesystem or
network side effects, and nothing here may reach into the strategy/risk/
execution engine or a protected S-02B.1 file.
"""

import ast
import importlib
import pathlib
import sys

import pytest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "observability" / "operator"

PROTECTED_IMPORT_PREFIXES = (
    "config.feature_flags",
    "core.advisor_loop",
    "quant_hedge_ai.agents.intelligence.mistake_memory",
    "quant_hedge_ai.ai_evolution.strategy_memory",
    "tracker_system.meta_learner",
    "tracker_system.meta_memory",
)

FORBIDDEN_CALL_NAMES = {"open", "socket", "urlopen"}


def _module_files():
    return sorted(PACKAGE_ROOT.rglob("*.py"))


@pytest.mark.parametrize("module_path", _module_files(), ids=lambda p: str(p.relative_to(PACKAGE_ROOT)))
def test_no_protected_file_imports(module_path):
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for prefix in PROTECTED_IMPORT_PREFIXES:
        assert not any(name == prefix or name.startswith(prefix + ".") for name in imported), (
            f"{module_path} imports protected surface {prefix}"
        )


@pytest.mark.parametrize("module_path", _module_files(), ids=lambda p: str(p.relative_to(PACKAGE_ROOT)))
def test_no_top_level_filesystem_or_network_calls(module_path):
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    for node in tree.body:  # only module (import-time) level statements
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                assert name not in FORBIDDEN_CALL_NAMES, f"{module_path}: top-level call to {name!r}"


def test_package_imports_without_error_and_without_new_files(tmp_path, monkeypatch):
    before = set(pathlib.Path(".").rglob("*"))
    for mod in list(sys.modules):
        if mod.startswith("observability.operator"):
            del sys.modules[mod]
    importlib.import_module("observability.operator")
    importlib.import_module("observability.operator.canonical_registry")
    after = set(pathlib.Path(".").rglob("*"))
    assert before == after
