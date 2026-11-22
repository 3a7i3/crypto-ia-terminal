"""Fixtures du contrat d'invocation : vrais dépôts git, vrais processus. Aucun VPS, aucun réseau."""
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from agent_bench.observation import contract as c

REPO = Path(__file__).resolve().parents[2]
ZONE_MISSION = REPO / "docs" / "agents" / "observation" / "examples" / "cartographer_zone_mission.json"
RUNNER = "obs-repo-cartographer-ro-01"
AGENT = "repository-cartographer"
GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "LC_ALL": "C",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@invalid",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@invalid",
           "GIT_AUTHOR_DATE": "2026-11-22T00:00:00Z", "GIT_COMMITTER_DATE": "2026-11-22T00:00:00Z"}


def git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=GIT_ENV)
    return out.stdout.decode().strip()


class GitEnv:
    """Checkout git réel : modules exécutés + périmètre + profil, commités une fois."""

    def __init__(self, root: Path):
        base = json.loads(ZONE_MISSION.read_text(encoding="utf-8"))
        self.root, self.checkout, self.reports = root, root / "checkout", root / "reports"
        files = list(base["scope"]["read_paths"]) + [base["profile"]["source_path"], "agent_bench/__init__.py"]
        files += [f"agent_bench/observation/{p.name}" for p in sorted((REPO / "agent_bench/observation").glob("*.py"))]
        for rel in files:
            dst = self.checkout / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, dst)
        git(self.checkout, "init", "-q", "-b", "main")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "checkout de banc")
        self.sha = git(self.checkout, "rev-parse", "HEAD")
        m = json.loads(json.dumps(base))
        m["analyzed_ref"] = {"kind": "GIT_COMMIT", "sha": self.sha}
        m["mission_id"] = c.compute_mission_id(m)
        self.mission = m
        self.reports.mkdir()

    def kwargs(self, **over):
        kw = {"mission": self.mission, "checkout": self.checkout, "reports": self.reports, "runner_id": RUNNER,
              "code_sha": self.sha, "analysed_sha": self.sha}
        kw.update(over)
        return kw

    def runs_dir(self):
        return self.reports / "runs" / self.mission["mission_id"]


@pytest.fixture()
def genv(tmp_path):
    return GitEnv(tmp_path)


HOLDER = textwrap.dedent("""
    import fcntl, json, os, sys
    path, content = sys.argv[1], json.loads(sys.argv[2])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o640)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if content is not None:
        if content.get("pid") == "SELF":
            content["pid"] = os.getpid()
        os.ftruncate(fd, 0); os.pwrite(fd, json.dumps(content).encode(), 0); os.fsync(fd)
    print("ready", flush=True)
    sys.stdin.read()
""")


class Holder:
    """Processus réel qui détient le flock du runner (simule un exécuteur en cours)."""

    def __init__(self, reports: Path, content):
        self.proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(reports / "locks" / f"{RUNNER}.lock"),
                                      json.dumps(content)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        assert self.proc.stdout.readline().strip() == b"ready"

    @property
    def pid(self):
        return self.proc.pid

    def kill(self):
        self.proc.kill()
        self.proc.wait(10)

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(10)


@pytest.fixture()
def holders():
    made = []

    def make(reports, content):
        h = Holder(reports, content)
        made.append(h)
        return h
    yield make
    for h in made:
        if h.proc.poll() is None:
            h.kill()


def lock_content(mission, now, **over):
    from agent_bench.observation import invocation as inv
    body = {"contract": inv.LOCK_CONTRACT, "agent_id": AGENT, "runner_id": RUNNER, "mission_id": mission,
            "invocation_id": "a" * 32, "pid": "SELF", "started_utc": inv.utc_iso(now - 5),
            "lease_until_utc": inv.utc_iso(now + 300)}
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


def wait_until(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False
