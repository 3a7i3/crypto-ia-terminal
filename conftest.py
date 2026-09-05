"""
conftest.py (root) — fixtures partagées pour toute la suite de tests.

Règle DS-001 (ADR-0008) : tout chemin configurable doit être résolu à
l'exécution, jamais comme défaut de signature ni constante de module figée
à l'import. Trois couches complémentaires de défense en profondeur :

1. Env vars au NIVEAU MODULE (juste en dessous) — posées AVANT tout import
   de module de test, donc avant que pytest ne collecte les fichiers de
   test. Nécessaire pour les constantes qui se figent à l'IMPORT (pas
   seulement à l'exécution d'une fixture, ce qui serait trop tard) :
   OBS_LOG_ROOT, REJECTION_STORE_DIR, COLD_START_REPORT_DIR,
   BLACK_BOX_PATH. Chemins ABSOLUS obligatoires : un thread d'arrière-plan
   peut flusher après restauration du CWD par le teardown d'une fixture.
2. Fixtures autouse patchant les attributs de module / défauts de
   signature non injectables (isolation recorder, black box, cold-start,
   gate CSV, exec trade log).
3. Scientific Data Guard (SHA256, fin de fichier) : filet de sécurité final
   — invariant exact (revue master CI-00B) :
     - chemin MODIFIÉ ou AJOUTÉ, déjà connu du baseline versionné
       (.ci/scientific_data_guard_baseline.json) : toléré, affiché,
       jamais bloquant ;
     - chemin MODIFIÉ ou AJOUTÉ, absent du baseline (contamination
       NOUVELLE) : ÉCHEC ;
     - chemin SUPPRIMÉ sous databases/ ou cache/, QUEL QU'IL SOIT
       (baselisé ou non) : ÉCHEC PAR DÉFAUT, toujours. Le baseline ne
       couvre QUE les modifications/ajouts connus, jamais les
       suppressions — aucun mécanisme de gouvernance dédié à tolérer une
       suppression de donnée scientifique n'existe à ce jour ; en créer
       un est une décision de gouvernance séparée, pas un défaut CI-00B.
   Le garde-fou ne surcharge session.exitstatus QUE pour ajouter un échec
   (contamination nouvelle ou suppression) — jamais pour en retirer un :
   le code de sortie pytest ordinaire reste la source de vérité pour les
   échecs/erreurs de tests eux-mêmes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent
_SCIENTIFIC_DATA_ROOTS = [_REPO_ROOT / "databases", _REPO_ROOT / "cache"]
_SCIENTIFIC_DATA_GUARD_BASELINE_PATH = (
    _REPO_ROOT / ".ci" / "scientific_data_guard_baseline.json"
)

# ── DS-001 — env vars au niveau module (avant toute collection pytest) ────────
# Posées ici (pas dans une fixture) pour atteindre les constantes de module
# figées à l'import de modules importés pendant la collection des tests
# (ex: observability/json_logger.py::LOG_ROOT, rejection_store.py::_DEFAULT_DIR).
# setdefault() : ne écrase pas une valeur déjà positionnée par l'environnement
# d'exécution (CI, VPS...).
os.environ.setdefault("OBS_LOG_ROOT", tempfile.mkdtemp(prefix="pytest_obs_logs_"))

_pytest_data_dir = tempfile.mkdtemp(prefix="pytest_data_")
os.environ.setdefault(
    "REJECTION_STORE_DIR", os.path.join(_pytest_data_dir, "rejections")
)
os.environ.setdefault(
    "COLD_START_REPORT_DIR", os.path.join(_pytest_data_dir, "cold_start_reports")
)
os.environ.setdefault(
    "BLACK_BOX_PATH", os.path.join(_pytest_data_dir, "black_box.jsonl")
)
os.environ.setdefault(
    # S-03B: BB_PATH est le nom canonique lu par
    # quant_hedge_ai/agents/intelligence/black_box.py::BlackBox (et, depuis
    # S-03B, par cold_start/warmup_report.py) — BLACK_BOX_PATH ci-dessus
    # n'isolait donc jamais les instances réelles de BlackBox construites
    # sans chemin explicite pendant les tests (seul cold_start/
    # warmup_invariants.py lisait BLACK_BOX_PATH). Les deux variables
    # restent posées pour ne retirer aucune isolation existante.
    "BB_PATH", os.path.join(_pytest_data_dir, "black_box.jsonl")
)
os.environ.setdefault(
    "LMI_DIR", os.path.join(tempfile.mkdtemp(prefix="pytest_lmi_"), "lmi")
)


@pytest.fixture(autouse=True)
def _isolate_paper_recorder(monkeypatch, tmp_path):
    """Redirect paper trade recorder to a per-test temp file.

    Prevents test runs from polluting databases/paper_trades.jsonl.
    Applied automatically to every test in the project.
    """
    import paper_trading.recorder as _rec

    test_log = str(tmp_path / "paper_trades_test.jsonl")
    monkeypatch.setenv("PAPER_TRADE_LOG", test_log)
    monkeypatch.setattr(_rec, "_DEFAULT_PATH", test_log)
    monkeypatch.setattr(_rec, "_recorder", None)
    yield
    monkeypatch.setattr(_rec, "_recorder", None)


@pytest.fixture(autouse=True)
def _isolate_exec_trade_log(monkeypatch, tmp_path):
    """Redirige le journal SQLite du moteur d'exécution vers tmp_path.

    ExecutionEngine.__init__ lit EXEC_TRADE_LOG à l'appel (conforme DS-001),
    mais des tests instanciant le moteur sans poser la variable écrivaient
    des trades de test dans databases/trade_log.sqlite (prouvé
    empiriquement, Sprint S4-B). Chemin absolu (tmp_path) requis.
    Applied automatically to every test in the project.
    """
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trade_log_test.sqlite"))
    yield


@pytest.fixture(autouse=True)
def _isolate_cold_start_persistence(monkeypatch, tmp_path):
    """Redirect P10 cold-start persistence to per-test temp files.

    Prevents test runs from polluting:
      - databases/black_box.jsonl        (WarmupReport.archive_to_black_box)
      - databases/cold_start_reports/    (WarmupReport.save)
      - cache/startup/warmup_state.json  (WarmupStateMachine._persist, appelé
        dès __init__ et à chaque transition — instancier ColdStartManager
        suffit à écrire sur disque)
      - cache/startup/live_ready.token   (bypass_detector.write_live_ready_token,
        appelé par ColdStartManager en atteignant LIVE_READY)

    black_box/cold_start_reports lisent leur env var À L'APPEL (corrigé,
    Sprint S3/S4) — un simple monkeypatch.setenv suffit. warmup_state_machine
    et bypass_detector figent leur chemin en constante de module à l'import
    (DS-001 variante 2) — l'attribut de module doit être patché directement.
    Applied automatically to every test in the project.
    """
    monkeypatch.setenv("BLACK_BOX_PATH", str(tmp_path / "black_box_test.jsonl"))
    monkeypatch.setenv("COLD_START_REPORT_DIR", str(tmp_path / "cold_start_reports"))

    import cold_start.bypass_detector as _bpd
    import cold_start.warmup_state_machine as _wsm

    monkeypatch.setattr(
        _wsm, "_STATE_PERSIST_PATH", tmp_path / "warmup_state_test.json"
    )
    monkeypatch.setattr(_bpd, "_TOKEN_PATH", tmp_path / "live_ready_test.token")


@pytest.fixture(autouse=True)
def _isolate_perp_universe(monkeypatch, tmp_path):
    """Redirect PerpUniverseService's storage file to a per-test temp file.

    PerpUniverseService.__init__ already reads UNIVERSE_STORAGE at call
    time (DS-001 compliant, no code fix needed) — it simply had no test
    isolation at all yet. Découvert empiriquement (find -newer) lors de
    l'intégration Sprint S4 : databases/perp_universe.json était modifié
    par tests/test_advisor_loop_smoke.py malgré monkeypatch.chdir, car son
    défaut (_UNIVERSE_STORAGE_DEFAULT) est ancré via os.path.dirname(__file__)
    — immune au chdir (DS-001 variante 3).
    Applied automatically to every test in the project.
    """
    monkeypatch.setenv("UNIVERSE_STORAGE", str(tmp_path / "perp_universe_test.json"))


@pytest.fixture(autouse=True)
def _isolate_gate_csv(monkeypatch, tmp_path):
    """Redirect GlobalRiskGate's CSV logger to a per-test temp file.

    Prevents test runs (GlobalRiskGate.check / check_packet) from polluting
    databases/gate_rejections.csv. Applied automatically to every test.

    _GATE_CSV is a plain module-level Path (not a function default), same
    situation as warmup_state_machine._STATE_PERSIST_PATH above — must be
    overridden via monkeypatch.setattr on the module object.
    """
    import quant_hedge_ai.agents.risk.global_risk_gate as _grg

    monkeypatch.setattr(_grg, "_GATE_CSV", str(tmp_path / "gate_rejections_test.csv"))


# ── Scientific Data Guard ──────────────────────────────────────────────────────


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return "UNREADABLE"
    return h.hexdigest()


def _is_ignored(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return True
    # Archives figées créées lors d'un nettoyage (regret_analysis.jsonl.bak-...,
    # cold_start_reports.bak-...) : jamais réécrites, inutile de les hacher
    # à chaque session — juste du poids mort pour le garde-fou.
    return any(".bak" in part for part in path.parts)


def _snapshot_scientific_data() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for root in _SCIENTIFIC_DATA_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or _is_ignored(path):
                continue
            snapshot[str(path)] = _hash_file(path)
    return snapshot


def _to_repo_relative(path_str: str) -> str:
    try:
        return Path(path_str).resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path_str


def _load_scientific_data_guard_baseline() -> set[str]:
    if not _SCIENTIFIC_DATA_GUARD_BASELINE_PATH.exists():
        return set()
    data = json.loads(_SCIENTIFIC_DATA_GUARD_BASELINE_PATH.read_text())
    return set(data.get("known_leaking_paths", []))


def pytest_sessionstart(session: pytest.Session) -> None:
    # type: ignore[attr-defined]
    session.config._scientific_data_before = _snapshot_scientific_data()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    before = getattr(session.config, "_scientific_data_before", None)
    if before is None:
        return
    after = _snapshot_scientific_data()

    generate_mode = os.environ.get("SCIENTIFIC_DATA_GUARD_GENERATE") == "1"

    # CI-00B.2 (revue indépendante) : le mode génération doit être évalué
    # MÊME quand before == after (diff scientifique vide) — un nettoyage
    # réussi qui ramène le diff à zéro doit pouvoir régénérer le baseline
    # à `known_leaking_paths: []`, sinon d'anciennes exemptions restent
    # gelées indéfiniment. Le raccourci `before == after: return` ne
    # s'applique donc plus qu'au mode normal (non-génération), où il reste
    # un pur raccourci sans incidence observable (aucun chemin touché =
    # aucun `new_contamination`/`known_debt`/suppression à rapporter de
    # toute façon).
    if before == after and not generate_mode:
        return

    # Un seul calcul changed/added/removed, partagé par les deux modes
    # (génération et vérification normale) : le mode génération ne doit
    # JAMAIS avoir sa propre notion de "touched" divergente de celle qui
    # décide des échecs, sous peine de pouvoir écrire une suppression dans
    # le baseline (défaut corrigé — revue indépendante CI-00B.2).
    changed = sorted(p for p in (set(before) & set(after)) if before[p] != after[p])
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    removed_rel = sorted(_to_repo_relative(p) for p in removed)

    # CI-00B : mode génération explicite du baseline (jamais implicite).
    # `SCIENTIFIC_DATA_GUARD_GENERATE=1 pytest -q tests/` réécrit le
    # baseline avec la liste actuelle des chemins MODIFIÉS/AJOUTÉS
    # uniquement — un diff visible et revu en PR, jamais un effet de bord
    # silencieux.
    #
    # CI-00B.2 (revue indépendante) : sémantique exacte —
    #   - zéro chemin modifié/ajouté/supprimé -> baseline régénéré à []
    #     (voir avant le raccourci ci-dessus) ;
    #   - chemins modifiés/ajoutés, AUCUNE suppression -> baseline
    #     régénéré avec exactement ces chemins ;
    #   - toute suppression -> ÉCHEC et le fichier baseline n'est PAS
    #     touché du tout (ni écrit, ni tronqué, ni modifié en aucune
    #     façon) ; le générer avec une suppression dans le diff n'a pas de
    #     sens, il faut d'abord la traiter séparément.
    if generate_mode:
        if removed_rel:
            print(
                "\nSCIENTIFIC DATA GUARD — suppression détectée pendant la "
                "génération du baseline : le fichier baseline N'A PAS été "
                "modifié (aucune régénération possible avec une "
                "suppression dans le diff) :\n"
                + "\n".join(f"  - {p}" for p in removed_rel)
                + "\n",
                file=sys.stderr,
            )
            session.exitstatus = 1
            return

        touched = {_to_repo_relative(p) for p in changed + added}
        _SCIENTIFIC_DATA_GUARD_BASELINE_PATH.write_text(
            json.dumps(
                {
                    "$schema": (
                        "CI-00B Scientific Data Guard baseline "
                        "(DS-001/ADR-0008). See conftest.py."
                    ),
                    "known_leaking_paths": sorted(touched),
                },
                indent=2,
            )
            + "\n"
        )
        print(
            f"\nSCIENTIFIC DATA GUARD — baseline regenerated: "
            f"{len(touched)} known path(s) (modified/added only) written "
            f"to {_SCIENTIFIC_DATA_GUARD_BASELINE_PATH}.\n",
            file=sys.stderr,
        )
        return

    baseline = _load_scientific_data_guard_baseline()
    touched_rel = {_to_repo_relative(p): p for p in changed + added}
    new_contamination = sorted(
        rel for rel in touched_rel if rel not in baseline
    )
    known_debt = sorted(rel for rel in touched_rel if rel in baseline)

    lines = [
        "",
        "=" * 78,
        "SCIENTIFIC DATA GUARD — databases/ ou cache/ modifié pendant les tests.",
        "Un test écrit dans un fichier de production (chemin par défaut non",
        "isolé). Voir conftest.py § docstring module (règle DS-001, ADR-0008)",
        "pour le motif de correction (lire le chemin depuis l'env var À L'APPEL,",
        "jamais comme valeur par défaut de signature évaluée à l'import).",
        "=" * 78,
    ]

    if new_contamination:
        lines.append("NOUVELLE contamination (absente du baseline — ÉCHEC) :")
        lines += [f"  - {p}" for p in new_contamination]
    if known_debt:
        lines.append(
            "Dette connue, baselisée (.ci/scientific_data_guard_baseline.json, "
            "tolérée, non bloquante) :"
        )
        lines += [f"  - {p}" for p in known_debt]
    if removed_rel:
        lines.append(
            "SUPPRESSION de donnée scientifique (ÉCHEC PAR DÉFAUT — jamais "
            "baselisable ; aucun mécanisme de gouvernance dédié aux "
            "suppressions n'existe à ce jour) :"
        )
        lines += [f"  - {p}" for p in removed_rel]
    lines += ["=" * 78, ""]

    print("\n".join(lines), file=sys.stderr)

    if new_contamination or removed_rel:
        session.exitstatus = 1
    # Sinon (uniquement dette connue, modifiée/ajoutée, baselisée) : on NE
    # TOUCHE PAS à session.exitstatus, qui reste le signal ordinaire de
    # réussite/échec des tests eux-mêmes (pytest_sessionfinish ne fait ici
    # qu'ajouter un échec, jamais en retirer un). Une suppression n'est
    # JAMAIS tolérée par le baseline, même si le chemin y figure comme
    # dette de modification/ajout connue : le baseline ne couvre que
    # « modifié/ajouté », jamais « supprimé » (pas de mécanisme de
    # gouvernance dédié — voir docstring module).
