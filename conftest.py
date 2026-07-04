"""
conftest.py (root) — fixtures partagées pour toute la suite de tests.

Isolation recorder:
  Chaque test obtient un PaperTradeRecorder pointant vers un fichier
  temporaire (tmp_path). Cela évite que les tests écrivent dans
  databases/paper_trades.jsonl (le journal de production).

Isolation black box:
  Chaque test qui archive un WarmupReport (ColdStartManager._finalize)
  écrit vers un fichier temporaire au lieu de databases/black_box.jsonl
  (le journal tamper-evident de production).

Scientific Data Guard:
  Aucun test ne doit modifier databases/ ou cache/ (données scientifiques
  de production — burn-in, regret, décisions, snapshots). Ce garde-fou
  calcule un hash SHA256 de chaque fichier avant et après la session
  pytest complète et fait échouer la session si un seul octet a changé,
  qu'un fichier a été ajouté ou supprimé. C'est ce mécanisme, pas une
  isolation au cas par cas, qui aurait détecté immédiatement la
  contamination de regret_analysis.jsonl et black_box.jsonl.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent
_SCIENTIFIC_DATA_ROOTS = [_REPO_ROOT / "databases", _REPO_ROOT / "cache"]


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
def _isolate_black_box(monkeypatch, tmp_path):
    """Redirect WarmupReport/WarmupStateMachine archival to tmp_path.

    Prevents test runs (ColdStartManager, WarmupReport, WarmupStateMachine)
    from polluting databases/black_box.jsonl, databases/cold_start_reports/
    and cache/startup/warmup_state.json. Applied automatically to every test.

    Note: warmup_state_machine._STATE_PERSIST_PATH is a plain module-level
    Path (not a function default), so it must be overridden via
    monkeypatch.setattr on the module object — monkeypatch.setenv alone
    would not work here either, since the Path is already resolved once at
    import time either way.
    """
    monkeypatch.setenv("BLACK_BOX_PATH", str(tmp_path / "black_box_test.jsonl"))
    monkeypatch.setenv("COLD_START_REPORT_DIR", str(tmp_path / "cold_start_reports"))

    import cold_start.warmup_state_machine as _wsm

    monkeypatch.setattr(
        _wsm, "_STATE_PERSIST_PATH", tmp_path / "warmup_state_test.json"
    )


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
        "isolé). Voir conftest.py § Isolation recorder / Isolation black box",
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
