"""S4-a — SA9 (operational isolation).

The verifier and the projection import no Radar engine module, no network, process,
file or clock facility; at run time they open no file and no socket. They write
nothing. A valid projection is never an admission nor a runtime authorization.
"""
from __future__ import annotations

import ast
import builtins
import socket
import subprocess
import sys

import pytest

from observability.radar_projection import contract as pc
from observability.radar_projection.projection import project
from tests.radar_projection._exports import BATCH, ROOT, export

PACKAGE = ROOT / "observability" / "radar_projection"
ALLOWED_IMPORTS = {"__future__", "copy", "re", "observability.radar_selection.fixture"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__"}


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name, node.level if hasattr(node, "level") else 0
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node.level


@pytest.mark.parametrize("name", ["contract.py", "verifier.py", "projection.py", "__init__.py"])
def test_SA9_only_allowed_imports(name):
    for module, level in _imports(PACKAGE / name):
        if level:  # relative import inside the package
            continue
        assert module in ALLOWED_IMPORTS, (name, module)


@pytest.mark.parametrize("name", ["contract.py", "verifier.py", "projection.py"])
def test_SA9_no_file_exec_or_dynamic_import_call(name):
    tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls & FORBIDDEN_NAMES


def test_SA9_the_engine_is_never_loaded():
    code = ("import sys;import observability.radar_projection.projection as p;"
            "import observability.radar_projection.verifier as v;"
            "bad=[m for m in sys.modules if m.startswith('observability.') and m not in "
            "('observability','observability.radar_selection','observability.radar_selection.fixture',"
            "'observability.radar_selection.contract','observability.radar_projection',"
            "'observability.radar_projection.contract','observability.radar_projection.verifier',"
            "'observability.radar_projection.projection')];"
            "net=[m for m in ('socket','ssl','http','urllib.request','requests','subprocess','asyncio') "
            "if m in sys.modules and m not in ORIG];"
            "print(bad, net)")
    code = "import sys;ORIG=set(sys.modules);" + code
    env = {"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"}
    proc = subprocess.run([sys.executable, "-I", "-c", f"import sys;sys.path.insert(0,{str(ROOT)!r});" + code],
                          capture_output=True, text=True, env=env, cwd=ROOT, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[] []"


def test_SA9_no_file_and_no_socket_at_run_time(monkeypatch):
    raw = export(BATCH)

    def deny(*a, **k):
        raise AssertionError("I/O attempted")

    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    p = project(raw)
    assert p["authority"]["projection_status"] == pc.PROJECTION_STATUS


def test_SA9_projection_authorises_nothing():
    for source in ("r0_syn_04_incoherent", BATCH):
        p = project(export(source))
        a = p["authority"]
        assert a["execution_authority"] is False and a["collection_authority"] is False
        assert a["experiment_authority"] is False
        assert a["proposal_status"] == "PROPOSED_NOT_AUTHORIZED"
        assert a["admission"] == "NONE" and a["deep_observation_jobs"] == []
        assert a["projection_status"] == "PRESENTATION_ONLY_NOT_AN_ADMISSION_NOT_A_RUNTIME_AUTHORIZATION"
        assert all(v == "DISABLED" for k, v in p["evidence"]["mode"].items() if k != "evidence")
        assert all(c["status"] == "PROPOSED_NOT_AUTHORIZED" for c in p["candidates"])
        assert p["integrity"]["producer_authenticity"] == "NOT_PROVEN"


def test_SA9_no_api_route_and_no_frontend_in_this_change():
    app = (ROOT / "observability" / "operator_api" / "app.py").read_text(encoding="utf-8")
    assert "radar_projection" not in app and "radar-projection" not in app
