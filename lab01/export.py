"""Export de rapports nettoyés vers un emplacement lisible par l'observateur.

`runs` reste privé (0700). Ce module copie, après contrôle, une liste blanche de
fichiers vers `reports` (dossiers 0755, fichiers 0644). Il n'a accès ni au jeton ni
à la production ; il refuse tout ce qui n'est pas SYNTHETIC, chaîné et propre.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from lab01 import PROVENANCE
from lab01.events import canonical, sha256_hex, verify_chain

ID_RE = re.compile(r"^LAB01-[a-z_]+-[0-9a-f]{12}$")
ALLOWED_FILES = (
    "result.json",
    "events.jsonl",
    "manifest.json",
)  # packet.json, bars.json exclus
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_EXPERIMENTS = 200
# Chaînes interdites dans un rapport exporté : chemins de production, jeton, secret.
FORBIDDEN_STRINGS = re.compile(
    r"(/home/|/opt/crypto|/srv/claude-audit|/srv/lab01/token|Bearer\s|API[_-]?(KEY|SECRET)|"
    r"BEGIN [A-Z ]*PRIVATE KEY)",
    re.IGNORECASE,
)
MANIFEST_DROP = (
    "platform",
    "git_head",
)  # informations d'hôte non nécessaires à l'observateur


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _read_regular(path: Path) -> bytes:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"NOT_REGULAR_FILE:{path.name}")
    if st.st_size > MAX_FILE_BYTES:
        raise ValueError(f"FILE_TOO_LARGE:{path.name}")
    return path.read_bytes()


def _check(exp_dir: Path) -> dict[str, bytes]:
    """Renvoie les octets à exporter ou lève ValueError (motif lisible)."""
    out: dict[str, bytes] = {}
    for name in ALLOWED_FILES:
        out[name] = _read_regular(exp_dir / name)
    events = [json.loads(x) for x in out["events.jsonl"].decode().splitlines() if x]
    if not events or not verify_chain(events):
        raise ValueError("EVENT_CHAIN_INVALID")
    if any(e.get("experiment_id") != exp_dir.name for e in events):
        raise ValueError("EXPERIMENT_ID_MISMATCH")
    result = json.loads(out["result.json"])
    if (
        result.get("provenance") != PROVENANCE
        or result.get("experiment_id") != exp_dir.name
    ):
        raise ValueError("RESULT_PROVENANCE_OR_ID_INVALID")
    manifest = json.loads(out["manifest.json"])
    for doc in (events, result, manifest):
        for text in _strings(doc):
            if FORBIDDEN_STRINGS.search(text):
                raise ValueError("FORBIDDEN_STRING_PRESENT")
    for key in MANIFEST_DROP:
        manifest.pop(key, None)
    out["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    return out


def _write(path: Path, data: bytes, mode: int) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def export_reports(src, dst) -> dict:
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    os.chmod(dst, 0o755)
    exported, rejected, files = [], [], {}
    dirs = (
        sorted(p for p in src.iterdir() if ID_RE.match(p.name)) if src.is_dir() else []
    )
    for exp_dir in dirs[:MAX_EXPERIMENTS]:
        if exp_dir.is_symlink() or not exp_dir.is_dir():
            rejected.append(
                {"experiment_id": exp_dir.name, "reason": "NOT_A_DIRECTORY"}
            )
            continue
        try:
            data = _check(exp_dir)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            rejected.append({"experiment_id": exp_dir.name, "reason": str(exc)})
            continue
        target = dst / exp_dir.name
        target.mkdir(exist_ok=True)
        os.chmod(target, 0o755)
        for name, blob in data.items():
            _write(target / name, blob, 0o644)
            files[f"{exp_dir.name}/{name}"] = sha256_hex(
                blob.decode("utf-8", "replace")
            )
        exported.append(exp_dir.name)
    index = {
        "schema": "lab01.export/1",
        "provenance": PROVENANCE,
        "exported": exported,
        "rejected": rejected,
        "files_sha256": files,
        "excluded_by_design": [
            "packet.json",
            "bars.json",
            "manifest.platform",
            "manifest.git_head",
        ],
    }
    index["digest"] = sha256_hex(
        canonical({k: index[k] for k in ("exported", "files_sha256")})
    )
    _write(
        dst / "EXPORT.json",
        (json.dumps(index, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )
    return index
