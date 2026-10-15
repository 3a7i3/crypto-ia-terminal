"""Politique de rétention : lister par défaut, ne supprimer que sur demande explicite."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ID_RE = re.compile(r"^LAB01-[a-z_]+-[0-9a-f]{12}$")


def dir_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file() and not p.is_symlink():
            total += p.stat().st_size
    return total


def prune(out, *, keep: int = 20, apply: bool = False) -> dict:
    """Conserve les `keep` expériences les plus récentes ; le reste est listé.

    Rien n'est supprimé sans `apply=True`. Aucun lien symbolique n'est suivi ; seuls les
    dossiers nommés comme une expérience sont concernés (jamais `_logs` ni les rapports).
    """
    if keep < 1:
        raise ValueError("KEEP_MUST_BE_POSITIVE")
    root = Path(out)
    exps = [
        p
        for p in root.iterdir()
        if ID_RE.match(p.name) and p.is_dir() and not p.is_symlink()
    ]
    exps.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    kept, old = exps[:keep], exps[keep:]
    removed = []
    if apply:
        for p in old:
            shutil.rmtree(p)
            removed.append(p.name)
    return {
        "dry_run": not apply,
        "keep": keep,
        "kept": [p.name for p in kept],
        "candidates": [p.name for p in old],
        "removed": removed,
        "bytes_total": dir_bytes(root),
    }
