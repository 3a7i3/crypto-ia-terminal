"""
scripts/migrate_to_structured_logger.py — Migration vanilla → StructuredLogger.

Traite les cas standard :
  - import logging
  - logger/log = logging.getLogger(...)
  - logger.debug/info/warning/error/critical(...)

Signale sans toucher les cas complexes :
  - logging.Formatter, logging.FileHandler, logging.basicConfig, etc.
  - Plusieurs variables logger dans le même fichier
  - Imports relatifs (from . import ...) qui incluent logging

Usage:
    python scripts/migrate_to_structured_logger.py [--dry-run] [path...]

    Si aucun path : scanne tout le projet (sauf .venv, __pycache__, .git).
    --dry-run : affiche les changements sans écrire.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns à détecter
# ---------------------------------------------------------------------------

# Matches: import logging
_IMPORT_LOGGING = re.compile(r"^import logging\s*$", re.MULTILINE)

# Matches: logger = logging.getLogger(...) ou log = logging.getLogger(...)
# Capture le nom de variable et le module passé à getLogger
_GET_LOGGER = re.compile(
    r"^(?P<var>\w+)\s*=\s*logging\.getLogger\((?P<arg>[^)]*)\)\s*$",
    re.MULTILINE,
)

# Patterns complexes — on ne touche pas ces fichiers
_COMPLEX_PATTERNS = [
    re.compile(p)
    for p in [
        r"logging\.Formatter",
        r"logging\.FileHandler",
        r"logging\.StreamHandler",
        r"logging\.RotatingFileHandler",
        r"logging\.basicConfig",
        r"logging\.addLevelName",
        r"logging\.setLoggerClass",
        r"logging\.Filter",
        r"logging\.Handler",
        r"class \w+\(logging\.",
        r"logging\.DEBUG\b",
        r"logging\.INFO\b",
        r"logging\.WARNING\b",
        r"logging\.ERROR\b",
        r"logging\.CRITICAL\b",
    ]
]

SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", "archives", "docs"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_module_name(var_arg: str, file_path: Path, project_root: Path) -> str:
    """Dérive un nom de module propre pour get_logger()."""
    arg = var_arg.strip().strip("\"'")
    if arg == "__name__":
        # Reconstruire depuis le chemin relatif
        try:
            rel = file_path.relative_to(project_root)
            parts = list(rel.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts)
        except ValueError:
            return file_path.stem
    return arg or file_path.stem


def _is_complex(content: str) -> list[str]:
    """Retourne la liste des patterns complexes trouvés, vide si fichier migreable."""
    found = []
    for pat in _COMPLEX_PATTERNS:
        m = pat.search(content)
        if m:
            found.append(m.group(0).strip())
    return found


def migrate_file(
    path: Path, project_root: Path, dry_run: bool = False
) -> tuple[str, str | None]:
    """
    Tente de migrer un fichier.
    Retourne (status, detail) où status ∈ {migrated, skipped, complex, no_match}.
    """
    content = path.read_text(encoding="utf-8", errors="replace")

    # Vérifier si logging.getLogger est présent
    match = _GET_LOGGER.search(content)
    if not match:
        return ("no_match", None)

    # Vérifier si déjà migré
    if "from observability.json_logger import get_logger" in content:
        return ("skipped", "already migrated")

    # Patterns complexes → ne pas toucher
    complex_hits = _is_complex(content)
    if complex_hits:
        return ("complex", ", ".join(complex_hits[:3]))

    # Plusieurs variables logger différentes ?
    all_vars = set(m.group("var") for m in _GET_LOGGER.finditer(content))
    if len(all_vars) > 1:
        return ("complex", f"multiple logger vars: {all_vars}")

    var_name = match.group("var")
    arg = match.group("arg")
    module_name = _derive_module_name(arg, path, project_root)

    # ── Construire le nouveau contenu ──────────────────────────────────────

    new_content = content

    # 1. Remplacer `import logging` par le nouvel import
    #    (seulement si présent et pas utilisé pour autre chose)
    if _IMPORT_LOGGING.search(new_content):
        new_content = _IMPORT_LOGGING.sub(
            "from observability.json_logger import get_logger", new_content, count=1
        )
    else:
        # Pas de `import logging` standalone — ajouter l'import avant la ligne getLogger
        first_gl = _GET_LOGGER.search(new_content)
        insert_pos = first_gl.start()
        new_content = (
            new_content[:insert_pos]
            + "from observability.json_logger import get_logger\n"
            + new_content[insert_pos:]
        )

    # 2. Remplacer toutes les déclarations getLogger
    new_content = _GET_LOGGER.sub(f'_log = get_logger("{module_name}")', new_content)

    # 3. Remplacer les appels logger.xxx(...) → _log.xxx(...)
    if var_name != "_log":
        levels = r"(debug|info|warning|error|critical|exception)"
        new_content = re.sub(
            rf"\b{re.escape(var_name)}\.{levels}\b",
            r"_log.\1",
            new_content,
        )

    if new_content == content:
        return ("skipped", "no changes produced")

    if not dry_run:
        path.write_text(new_content, encoding="utf-8")

    return ("migrated", f"{var_name} → _log  (module: {module_name})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def collect_files(paths: list[Path]) -> list[Path]:
    result = []
    for p in paths:
        p = p.resolve()
        if p.is_file() and p.suffix == ".py":
            result.append(p)
        elif p.is_dir():
            for f in p.rglob("*.py"):
                if not any(skip in f.parts for skip in SKIP_DIRS):
                    result.append(f.resolve())
    return sorted(set(result))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Fichiers ou dossiers à migrer")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans écrire")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.paths:
        targets = collect_files([Path(p) for p in args.paths])
    else:
        targets = collect_files([project_root])

    # Exclure ce script lui-même et json_logger
    targets = [
        f
        for f in targets
        if "migrate_to_structured_logger" not in f.name and "json_logger" not in f.name
    ]

    stats = {"migrated": 0, "skipped": 0, "complex": 0, "no_match": 0}
    complex_files: list[tuple[Path, str]] = []

    for f in targets:
        status, detail = migrate_file(f, project_root, dry_run=args.dry_run)
        stats[status] += 1
        if status == "migrated":
            rel = f.relative_to(project_root)
            prefix = "[DRY-RUN] " if args.dry_run else ""
            print(f"  {prefix}[OK] {rel}  — {detail}")
        elif status == "complex":
            complex_files.append((f, detail or ""))

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Résultat:")
    print(f"  migrated : {stats['migrated']}")
    print(f"  skipped  : {stats['skipped']}")
    print(f"  no_match : {stats['no_match']}")
    print(f"  complex  : {stats['complex']}  ← revue manuelle requise")

    if complex_files:
        print("\nFichiers complexes (non touchés) :")
        for f, detail in complex_files:
            print(f"  [!!] {f.relative_to(project_root)}  [{detail}]")


if __name__ == "__main__":
    main()
