"""Import == pure Python definitions only; package boundary and non-goals.

SOURCE ONLY / NON_DEPLOYED / NO RUNTIME AUTHORITY / NO AGENT EXECUTION.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "agent_economy"
PYTHON_FILES = sorted(PACKAGE_DIR.rglob("*.py"))

# Standard-library modules the pure core may import; nothing else, no repository package.
ALLOWED_IMPORTS = {
    "__future__", "collections.abc", "copy", "dataclasses", "datetime", "hashlib",
    "json", "os", "pathlib", "re", "typing", "unicodedata",
}
# ``os`` (O_CREAT|O_EXCL publication) is only permitted in the publication primitive.
OS_ALLOWED_IN = {"publication.py"}

BANNED_FILENAMES = {
    "worker.py", "runner.py", "scheduler.py", "daemon.py", "provider.py", "runtime.py",
    "github_writer.py", "bounty_registry.py", "problem_registry.py", "economy_ledger.py",
    "wallet.py", "treasury.py", "registrar.py", "governance_service.py",
}
BANNED_ATTRIBUTES = {
    "environ", "getenv", "putenv", "unsetenv", "system", "popen", "fork", "execv",
    "execve", "spawnl", "posix_spawn", "kill", "setuid", "chmod", "chown",
}
FORBIDDEN_NEW_MODULES = {
    "socket", "ssl", "subprocess", "http", "urllib.request", "sqlite3", "threading",
    "multiprocessing", "asyncio", "signal", "requests", "httpx", "aiohttp", "ftplib",
    "smtplib", "ctypes", "selectors", "shelve", "dbm", "logging", "tempfile",
}
BANNED_FRAMEWORKS = {"langchain", "crewai", "autogen", "openai", "anthropic"}
PURE_CALLS_AT_MODULE_LEVEL = {"frozenset", "compile_schema_pattern", "dict", "tuple", "set"}


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, 0) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_only_the_standard_library_and_relative_imports_are_used(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module, level in _imports(tree):
        if level:  # relative import inside agent_economy.agent_registry
            continue
        assert module in ALLOWED_IMPORTS, f"{path.name} imports {module}"
        if module == "os":
            assert path.name in OS_ALLOWED_IN, f"{path.name} must not import os"
    assert not any(name.split(".")[0] in BANNED_FRAMEWORKS for name, _ in _imports(tree))


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_environment_process_or_network_primitive_is_referenced(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in BANNED_ATTRIBUTES, f"{path.name}: .{node.attr}"
        if isinstance(node, ast.Name):
            assert node.id not in {"getenv", "environ", "eval", "exec", "__import__"}, node.id
            assert node.id != "open" or not isinstance(node.ctx, ast.Load), "no builtin open()"


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_module_level_code_is_definitions_only(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.AnnAssign)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring
        assert isinstance(node, ast.Assign), f"{path.name}: unexpected top-level {type(node).__name__}"
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            for call in ast.walk(node.value):
                if isinstance(call, ast.Call):
                    func = call.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    allowed = PURE_CALLS_AT_MODULE_LEVEL | {"compile"}
                    assert name in allowed, f"{path.name}: module-level call {name}()"


def test_no_forbidden_module_exists():
    present = {p.name for p in PYTHON_FILES}
    assert not (present & BANNED_FILENAMES)
    assert {p.name for p in (PACKAGE_DIR / "agent_registry").glob("*.py")} == {
        "__init__.py", "canonical.py", "capabilities.py", "spec.py", "events.py",
        "integrity.py", "projection.py", "publication.py",
    }
    assert not [p for p in PACKAGE_DIR.rglob("*") if p.is_dir() and p.name != "__pycache__" and p != PACKAGE_DIR / "agent_registry"]
    assert not list(PACKAGE_DIR.rglob("*.db")) and not list(PACKAGE_DIR.rglob("*.sqlite*"))


def test_no_a2_vocabulary_and_no_registrar_in_the_source():
    text = "\n".join(p.read_text(encoding="utf-8") for p in PYTHON_FILES)
    for token in ("CANDIDATE_PROBLEM\"", "VERIFIED_PROBLEM", "problem_id", "bounty_id", "AIC_BALANCE", "wallet_id"):
        assert token not in text, token
    for token in ("signature", "hmac", "private_key", "api_key", "token_bearer"):
        assert token not in text.lower(), token


_PROBE = r"""
import json, os, signal, sys
sys.dont_write_bytecode = True
sys.path.insert(0, {root!r})
WATCH_PREFIXES = ("socket.", "subprocess.", "os.system", "os.exec", "os.fork", "os.posix_spawn",
                  "os.spawn", "os.putenv", "os.unsetenv", "os.mkdir", "os.remove", "os.rename",
                  "os.rmdir", "os.truncate", "os.chmod", "os.symlink", "os.link", "shutil.",
                  "sqlite3.", "ctypes.", "urllib.", "http.", "ftplib.", "smtplib.", "_thread.",
                  "threading.")
recorded = []
def hook(event, args):
    if event.startswith(WATCH_PREFIXES):
        recorded.append(event)
    elif event == "open":
        path, mode, flags = args
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)) if isinstance(flags, int) else False
        if writing or (isinstance(mode, str) and any(c in mode for c in "wax+")):
            recorded.append(f"open-for-write:{{path}}")
sys.addaudithook(hook)
env_before = dict(os.environ)
modules_before = set(sys.modules)
signals_before = {{s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}}
cwd_before = sorted(os.listdir("."))
import agent_economy.agent_registry as registry
registry_names = sorted(n for n in dir(registry) if not n.startswith("_"))
print(json.dumps({{
    "audit": recorded,
    "env_unchanged": dict(os.environ) == env_before,
    "signals_unchanged": all(signal.getsignal(s) == h for s, h in signals_before.items()),
    "cwd_unchanged": sorted(os.listdir(".")) == cwd_before,
    "new_modules": sorted(set(sys.modules) - modules_before),
    "threads": __import__("threading").active_count() if "threading" in sys.modules else 1,
    "names": registry_names,
}}))
"""


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("import_probe")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(workdir), "SECRET_TOKEN": "must-not-be-read"}
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE.format(root=str(ROOT))],
        cwd=workdir, env=env, capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_importing_the_package_is_free_of_side_effects(probe):
    assert probe["audit"] == [], f"side-effecting audit events at import: {probe['audit']}"
    assert probe["env_unchanged"] and probe["signals_unchanged"] and probe["cwd_unchanged"]
    assert probe["threads"] == 1


def test_importing_loads_no_network_process_database_or_provider_module(probe):
    loaded = set(probe["new_modules"])
    assert not (loaded & FORBIDDEN_NEW_MODULES), loaded & FORBIDDEN_NEW_MODULES
    assert not any(m.split(".")[0] in BANNED_FRAMEWORKS for m in loaded)
    assert not any(m.split(".")[0] in {"core", "runtime", "paper_trading", "observability",
                                      "research_candidate", "research_data", "financial_institute",
                                      "capital_deployment", "supervision", "certification"} for m in loaded)


def test_the_public_surface_has_no_runtime_registrar_or_worker_entry_points(probe):
    for name in probe["names"]:
        lowered = name.lower()
        for word in ("worker", "scheduler", "daemon", "runner", "registrar", "provider", "wallet", "treasury", "bounty"):
            assert word not in lowered, name
