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
   — fait échouer toute session pytest si databases/ ou cache/ a changé,
   peu importe la cause.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent
_SCIENTIFIC_DATA_ROOTS = [_REPO_ROOT / "databases", _REPO_ROOT / "cache"]

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


def pytest_sessionstart(session: pytest.Session) -> None:
    # type: ignore[attr-defined]
    session.config._scientific_data_before = _snapshot_scientific_data()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    before = getattr(session.config, "_scientific_data_before", None)
    if before is None:
        return
    after = _snapshot_scientific_data()
    if before == after:
        return

    changed = sorted(p for p in (set(before) & set(after)) if before[p] != after[p])
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))

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
    if changed:
        lines.append("Fichiers modifiés :")
        lines += [f"  - {p}" for p in changed]
    if added:
        lines.append("Fichiers ajoutés :")
        lines += [f"  - {p}" for p in added]
    if removed:
        lines.append("Fichiers supprimés :")
        lines += [f"  - {p}" for p in removed]
    lines += ["=" * 78, ""]

    print("\n".join(lines), file=sys.stderr)
    session.exitstatus = 1
