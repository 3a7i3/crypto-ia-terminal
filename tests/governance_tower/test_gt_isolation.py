"""GOV-TOWER-00 lot G — preuve d'isolation : aucun chemin de code vers le runtime ou une écriture.

Analyse AST de tout le paquet ``governance_tower`` : imports admis, appels
système interdits, méthodes HTTP mutatrices absentes, aucune activation de
modèle, worker ou ordonnanceur.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "governance_tower"
PY_FILES = sorted(PKG.rglob("*.py"))

ALLOWED_EXTERNAL = {
    "observability.runtime_service_contract",
    "observability.storage_contract",
}
FORBIDDEN_PREFIXES = (
    "core",
    "paper_trading",
    "financial_institute",
    "governance",  # routeur de décision runtime ; ``governance_tower`` est vérifié à part
    "observability.operator_api",
    "observability.operator",
    "lab01",
    "ccxt",
    "exchange_constraints",
    "execution_simulator",
    "capital_deployment",
    "risk",
    "signal",
    "telegram",
    "subprocess",
    "socket",
    "ctypes",
    "multiprocessing",
    "sched",
    "asyncio",
    "anthropic",
    "requests",
    "paramiko",
    "fabric",
)
STDLIB_OK = {
    "__future__", "argparse", "ast", "dataclasses", "datetime", "enum", "hashlib", "http", "http.server",
    "ipaddress", "json", "math", "os", "pathlib", "posixpath", "re", "secrets", "stat", "sys", "threading",
    "time", "types", "typing", "unicodedata", "urllib", "urllib.error", "urllib.parse", "urllib.request",
    "email", "email.message", "collections", "functools", "itertools", "io", "base64", "errno", "copy",
    "string", "textwrap", "contextlib", "abc",
}
FORBIDDEN_OS_CALLS = {"system", "popen", "spawnl", "spawnv", "execv", "execve", "fork", "kill", "remove", "unlink",
                      "rmtree", "chmod", "chown", "rename", "replace", "symlink", "rmdir", "removedirs", "truncate"}
FORBIDDEN_BUILTINS = {"eval", "exec", "compile", "__import__"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(node.module)
    return out


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_imports_are_isolated(path):
    for mod in _imports(path):
        if mod == "governance_tower" or mod.startswith("governance_tower."):
            continue
        if mod in ALLOWED_EXTERNAL:
            continue
        for prefix in FORBIDDEN_PREFIXES:
            assert not (mod == prefix or mod.startswith(prefix + ".")), f"{path.name} importe {mod}"
        assert mod in STDLIB_OK, f"{path.name}: import non revu {mod}"


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_process_or_destructive_filesystem_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in {"os", "shutil"}:
                assert fn.attr not in FORBIDDEN_OS_CALLS, f"{path.name}: appel interdit os.{fn.attr}"
            if isinstance(fn, ast.Name):
                assert fn.id not in FORBIDDEN_BUILTINS, f"{path.name}: appel interdit {fn.id}"


def test_no_mutating_http_verbs_or_runtime_commands_in_source():
    for path in PY_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in ('method="POST"', "method='POST'", '"PUT"', '"PATCH"', '"DELETE"',
                       "systemctl ", "journalctl ", "sudo ", "/home/mathieu/crypto_ai_terminal",
                       "/opt/crypto-ai-terminal"):
            if path.name == "policy.py" or path.name == "injection.py":
                continue  # motifs de détection/refus, jamais exécutés
            assert needle not in text, f"{path.name} contient {needle!r}"


def test_no_scheduler_worker_or_daemon_entrypoints():
    for path in PY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"Timer", "start_new_thread", "daemon", "every"}, path.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"Thread", "Timer"}, path.name


def test_package_identity_constants():
    import governance_tower as gt

    assert (gt.AGENT_ID, gt.CAPABILITY, gt.OPERATIONAL_AUTHORITY, gt.RUNTIME_DEPLOYED) == (
        "SENTINEL-01",
        "OBSERVE_ONLY",
        "DENIED",
        False,
    )


def test_no_systemd_or_install_artifacts_shipped():
    shipped = {p.suffix for p in PKG.rglob("*") if p.is_file()}
    assert not shipped & {".service", ".timer", ".socket", ".mount", ".sh"}
