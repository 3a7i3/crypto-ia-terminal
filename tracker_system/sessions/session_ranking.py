from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tracker_system.sessions.session_analyzer import SessionAnalyzer
from tracker_system.sessions.session_manager import SESSIONS_ROOT, load_session_trades
from tracker_system.sessions.session_scoring import SessionScoring

_RANKING_DB_FILE = SESSIONS_ROOT / "ranking.json"


def _load_db() -> list[dict]:
    if not _RANKING_DB_FILE.exists():
        return []
    try:
        return json.loads(_RANKING_DB_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_db(db: list[dict]) -> None:
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    _RANKING_DB_FILE.write_text(json.dumps(db, indent=2, default=str), encoding="utf-8")


def register_session(session_dir: Path) -> dict[str, Any]:
    """Enregistre une session dans le leaderboard et retourne son entrée."""
    trades = load_session_trades(session_dir)
    analysis = SessionAnalyzer().analyze(trades)
    scoring = SessionScoring().score(analysis, trades)

    metadata_file = session_dir / "session_metadata.json"
    metadata: dict = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    entry: dict[str, Any] = {
        "session_id": session_dir.name,
        "start_time": metadata.get("start_time"),
        "mode": metadata.get("mode", "unknown"),
        "market": metadata.get("market", "unknown"),
        "system_version": metadata.get("system_version", "unknown"),
        "trades": analysis.get("summary", {}).get("trades", 0),
        "winrate": analysis.get("summary", {}).get("winrate", 0.0),
        "expectancy": analysis.get("expectancy", {}).get("value", 0.0),
        "profit_factor": analysis.get("profit_factor", 0.0),
        "quality_score": scoring.get("quality_score", 0.0),
        "label": scoring.get("label", "unknown"),
        "confidence": scoring.get("confidence", {}).get("value", 0.0),
        "regime_coverage": scoring.get("regime_coverage", {}).get("value", 0.0),
        "failure_causes": scoring.get("failure_analysis", {}).get("root_causes", []),
        "session_dna": scoring.get("session_dna", {}),
        "market_fingerprint": scoring.get("market_fingerprint", {}),
    }

    db = _load_db()
    # Upsert par session_id
    existing_ids = [r["session_id"] for r in db]
    if entry["session_id"] in existing_ids:
        db = [entry if r["session_id"] == entry["session_id"] else r for r in db]
    else:
        db.append(entry)

    db.sort(key=lambda r: r.get("quality_score", 0.0), reverse=True)
    _save_db(db)

    # Persiste aussi le scoring dans la session
    scoring_path = session_dir / "scoring.json"
    scoring_path.write_text(
        json.dumps(scoring, indent=2, default=str), encoding="utf-8"
    )

    return entry


def get_leaderboard(top_n: int = 20) -> list[dict]:
    """Retourne les meilleures sessions triées par quality_score."""
    return _load_db()[:top_n]


def get_top_by(field: str, top_n: int = 10, descending: bool = True) -> list[dict]:
    """Top N sessions sur un KPI arbitraire."""
    db = _load_db()
    return sorted(
        [r for r in db if field in r],
        key=lambda r: r.get(field, 0.0),
        reverse=descending,
    )[:top_n]


def get_session_rank(session_id: str) -> dict[str, Any]:
    """Rang et percentile d'une session dans le leaderboard."""
    db = _load_db()
    ids = [r["session_id"] for r in db]
    if session_id not in ids:
        return {"error": f"session '{session_id}' non trouvée dans le ranking"}
    rank = ids.index(session_id) + 1
    percentile = round((1 - (rank - 1) / max(len(db), 1)) * 100, 1)
    return {
        "session_id": session_id,
        "rank": rank,
        "total_sessions": len(db),
        "percentile": percentile,
    }


def rebuild_leaderboard() -> int:
    """Reconstruit le leaderboard depuis tous les répertoires sessions/ existants."""
    if not SESSIONS_ROOT.exists():
        return 0
    count = 0
    for session_dir in sorted(SESSIONS_ROOT.iterdir()):
        if not session_dir.is_dir() or not session_dir.name.startswith("session_"):
            continue
        try:
            register_session(session_dir)
            count += 1
        except Exception:
            pass
    return count
