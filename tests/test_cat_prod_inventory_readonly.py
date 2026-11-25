"""S4-B-RV1: the production inventory script must never print a configuration value outside its
closed allowlist. A fake ``systemctl`` returns units whose ExecStart, Environment, drop-ins and
EnvironmentFiles all carry planted secrets; none may appear in the output."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "preprod" / "cat_prod_inventory_readonly.sh"
PLANTED = "sk-PLANTED"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("python3") is None,
                                reason="bash and python3 required")


def _fixture(tmp_path: Path) -> Path:
    api, web, d, bindir = tmp_path / "api", tmp_path / "web", tmp_path / "dropin", tmp_path / "bin"
    for p in (api / "observability" / "operator_api", web / "scripts", web / "dist", d, bindir):
        p.mkdir(parents=True)
    (api / "observability" / "operator_api" / "app.py").write_text("x = 1\n")
    (api / ".env").write_text(f"TOKEN={PLANTED}-dotenv\n")
    (web / "scripts" / "web01_local_frontend_server.mjs").write_text("//\n")
    (web / "dist" / "index.html").write_text("<html>on-disk-not-served\n")
    served = tmp_path / "refonte" / "dist"
    served.mkdir(parents=True)
    (served / "index.html").write_text("<html>served\n")
    (served / "app.js").write_text("//\n")
    srv = tmp_path / "agents" / "server"
    srv.mkdir(parents=True)
    (srv / "web01_local_frontend_server.mjs").write_text("// served server\n")
    (d / "10.conf").write_text(f"[Service]\nEnvironment=API_TOKEN={PLANTED}-dropin\nExecStart=/x --k {PLANTED}-x\n")
    fake = bindir / "systemctl"
    fake.write_text(f"""#!/bin/bash
case "$2" in
 crypto-operator-api.service) W={api}; E='{{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 -m uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090 --key={PLANTED}-argv ; ignore_errors=no }}';;
 crypto-operator-web.service) W={web}; E='{{ path=/usr/bin/env ; argv[]=/usr/bin/env node {web}/scripts/web01_local_frontend_server.mjs --s {PLANTED}-web ; ignore_errors=no }}';;
 *) W=; E=;;
esac
echo "Id=$2"; echo "ActiveState=active"; echo "WorkingDirectory=$W"; echo "ExecStart=$E"
echo 'Environment=PASSWORD={PLANTED}-env "OPENAI_KEY=a b {PLANTED}-quoted" OPERATOR_RADAR_EXPORT_PATH=/var/lib/r.json X_STALE_AFTER_S=90 BAD_PATH=/a;{PLANTED}'
[ "$2" = crypto-operator-web.service ] && echo "BindReadOnlyPaths={served}:{web}/dist:rbind {srv}/web01_local_frontend_server.mjs:{web}/scripts/web01_local_frontend_server.mjs"
echo "DropInPaths={d}/10.conf"; echo "EnvironmentFiles=/etc/secret.env (ignore_errors=no)"
""")
    fake.chmod(0o755)
    return bindir


def test_inventory_prints_no_planted_secret_and_keeps_allowlisted_facts(tmp_path):
    bindir = _fixture(tmp_path)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    run = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120, check=False)
    assert run.returncode == 0, run.stderr
    assert PLANTED not in run.stdout and "a b" not in run.stdout
    out = json.loads(run.stdout)
    api = out["units"]["crypto-operator-api.service"]
    assert api["exec_entry"] == {"module": ["uvicorn", "observability.operator_api.app:app"]}
    assert api["exec_host_port"] == {"host": "127.0.0.1", "port": "8090"}
    assert api["env_paths"] == {"OPERATOR_RADAR_EXPORT_PATH": "/var/lib/r.json"}
    assert api["env_numbers"] == {"X_STALE_AFTER_S": "90"}
    assert "PASSWORD" in api["env_names"]
    dropin = next(iter(api["dropins"].values()))
    assert dropin["directives"] == ["[Service]", "Environment", "ExecStart"]
    assert list(out["api_tree"]["files"]) == ["observability/operator_api/app.py"]
    # Served files are resolved through the unit's bind mounts, not read under WorkingDirectory.
    assert out["web_server"]["script_on_host"].endswith("agents/server/web01_local_frontend_server.mjs")
    assert out["web_server"]["script_blob"][1] == len("// served server\n")
    assert out["web_dist"]["used_on_host"].endswith("refonte/dist")
    assert sorted(out["web_dist"]["files"]) == ["app.js", "index.html"]
    assert out["web_dist"]["files"]["index.html"][1] == len("<html>served\n")
