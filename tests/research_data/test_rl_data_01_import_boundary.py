"""RL-DATA-01 — preuve de la frontiere d'import one-way PAPER -> Research.

Research peut lire des FAITS PAPER immuables, mais ne doit dependre d'aucun
module d'autorite runtime PAPER. Le module
`paper_trading.ppl_authority_runtime` construit l'autorite d'epoque PAPER et
tire transitivement la compatibilite legacy PPL et la machinerie de recovery
au redemarrage : Research n'a aucune raison scientifique d'en dependre.

Ces tests couvrent la frontiere reelle (graphe d'import statique + import
runtime isole), jamais la simple presence d'un commentaire.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import research_data

_FORBIDDEN_RUNTIME_MODULES = (
    "paper_trading.ppl_authority_runtime",
    "paper_trading.ppl_recovery",
    "paper_trading.ppl_compatibility",
    "advisor_loop",
)

_RESEARCH_SOURCES = tuple(
    sorted(Path(research_data.__file__).parent.glob("*.py"))
) + (Path(__file__).resolve().parents[2] / "scripts" / "rl_data_01_export.py",)


def _imported_module_names(source: Path) -> set[str]:
    """Noms de modules absolus importes par `source` (statique, via AST)."""

    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # import relatif -> interne a research_data
                continue
            if node.module:
                names.add(node.module)
                names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


@pytest.mark.parametrize("source", _RESEARCH_SOURCES, ids=lambda p: p.name)
def test_research_data_never_imports_paper_runtime_authority(source):
    imported = _imported_module_names(source)
    for forbidden in _FORBIDDEN_RUNTIME_MODULES:
        assert forbidden not in imported, (
            f"{source.name} importe le module runtime PAPER {forbidden!r} : "
            "RL-DATA-01 exige une frontiere one-way sans dependance runtime"
        )


def test_research_data_import_graph_has_no_runtime_authority_symbol():
    """Aucun symbole d'autorite runtime ne doit etre reference dans research_data."""

    for source in _RESEARCH_SOURCES:
        text = source.read_text(encoding="utf-8")
        for symbol in ("load_authority_manifest", "AuthorityManifestError"):
            assert symbol not in text, (
                f"{source.name} reference le symbole runtime {symbol!r}"
            )


def test_importing_research_data_does_not_load_runtime_authority_module():
    """Import runtime isole : le module d'autorite ne doit jamais etre charge."""

    probe = (
        "import sys;"
        "import research_data, research_data.operator, research_data.paper_exporter;"
        "loaded=[m for m in sys.modules if m in "
        f"{list(_FORBIDDEN_RUNTIME_MODULES)!r}];"
        "print(','.join(sorted(loaded)))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(Path(research_data.__file__).parent.parent),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.stdout.strip() == "", (
        "importer research_data charge des modules runtime PAPER : "
        f"{completed.stdout.strip()}"
    )


def test_research_data_never_constructs_durable_event_store():
    """Aucune construction du store, aucun load_epoch, aucun append, aucun lock."""

    for source in _RESEARCH_SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name != "DurableEventStore", (
                f"{source.name} construit un DurableEventStore"
            )
            # `append` nu est une primitive list Python ; seules les methodes
            # propres au store durable sont interdites.
            assert name not in {"load_epoch", "append_event", "acquire_lock"}, (
                f"{source.name} appelle {name!r} sur le store durable PPL"
            )
