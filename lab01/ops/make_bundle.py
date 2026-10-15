"""Construit le paquet LAB autonome (stdlib seule, aucune dépendance à installer).

Le paquet contient exactement le code dont dépend le cycle : aucun reste du
dépôt, aucune configuration, aucun secret. Archive déterministe + SHA-256.
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRA = (
    "core/__init__.py",
    "core/decision_packet.py",
    "core/lifecycle.py",
    "observability/__init__.py",
    "observability/json_logger.py",
)


def file_list() -> list[str]:
    lab = []
    for p in (ROOT / "lab01").rglob("*"):
        rel = p.relative_to(ROOT)
        if p.is_file() and "__pycache__" not in rel.parts and rel.parts[1] != "ops":
            if p.suffix in {".py", ".html"}:
                lab.append(rel.as_posix())
    sim = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "execution_simulator").glob("*.py")
    ]
    return sorted(set(lab + sim + list(EXTRA)))


def build(dest: Path) -> tuple[Path, str]:
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "lab01-bundle.tar.gz"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for rel in file_list():
            data = (ROOT / rel).read_bytes()
            ti = tarfile.TarInfo(rel)
            ti.size, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname, ti.mode = (
                len(data),
                0,
                0,
                0,
                "root",
                "root",
                0o644,
            )
            tar.addfile(ti, io.BytesIO(data))
    import gzip

    with out.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (dest / "lab01-bundle.tar.gz.sha256").write_text(f"{digest}  {out.name}\n")
    return out, digest


OPS = ROOT / "lab01" / "ops"
INSTALLER_FILES = (
    "lab01_ops.sh",
    "lab01_host_tests.sh",
    "host_isolation_tests.py",
    "hostprobe.py",
    "unit_props.py",
    "lab01_oom_probe.sh",
    "lab01_audit.sh",
    "systemd/lab01.slice",
    "systemd/srv-lab01-data.mount",
    "systemd/lab01-run.service",
    "systemd/lab01-export.service",
    "systemd/lab01-api.service",
)


def installer_manifest(dest: Path) -> tuple[Path, str]:
    """INSTALLER.sha256 (format `sha256sum -c`) : empreintes du code d'installation et du commit épinglé."""
    (dest / "COMMIT").write_text(
        git_head() + "\n"
    )  # épingle : verify-staging le compare à --commit
    lines = [
        f"{hashlib.sha256((OPS / rel).read_bytes()).hexdigest()}  {rel}\n"
        for rel in sorted(INSTALLER_FILES)
    ]
    lines.append(
        f"{hashlib.sha256((dest / 'COMMIT').read_bytes()).hexdigest()}  COMMIT\n"
    )
    lines.sort(key=lambda ln: ln.split("  ", 1)[1])
    path = dest / "INSTALLER.sha256"
    path.write_text("".join(lines))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    import subprocess

    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    ).stdout.strip()
    return out if len(out) == 40 else "UNKNOWN"


def write_request(dest: Path, bundle_sha: str, manifest_sha: str) -> Path:
    """Demande candidate `lab01.apply` : DONNÉES seulement, jamais un script ni une autorisation."""
    import json

    req = {
        "schema": "lab01.request/1",
        "operation": "lab01.apply",
        "not_an_authorization": True,
        "commit": git_head(),
        "bundle_sha256": bundle_sha,
        "installer_manifest_sha256": manifest_sha,
        "params": {
            "user": "lab01",
            "root": "/srv/lab01",
            "image_mb": 64,
            "port": 18090,
            "units": [u.rsplit("/", 1)[-1] for u in INSTALLER_FILES if "systemd/" in u],
        },
    }
    path = dest / "request.json"
    path.write_text(json.dumps(req, indent=2, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":
    dest = Path(sys.argv[1])
    path, dig = build(dest)
    _m, msha = installer_manifest(dest)
    write_request(dest, dig, msha)
    print(
        f"bundle_sha256={dig}\ninstaller_manifest_sha256={msha}\ncommit={git_head()}\n{path}"
    )
