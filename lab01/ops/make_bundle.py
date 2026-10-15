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


if __name__ == "__main__":
    path, dig = build(Path(sys.argv[1]))
    print(dig, path)
