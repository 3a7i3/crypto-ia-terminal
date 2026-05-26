"""
sweep_outcome_tracker.py — Mesure l'edge réel des sweeps détectés.

Principe :
  1. À chaque SweepEvent détecté, on l'enregistre avec le prix d'entrée.
  2. N bougies plus tard (horizon configurable), on enregistre l'outcome
     (continuation, reversal, RR, drawdown max).
  3. edge_stats() retourne les métriques agrégées par sweep_type, direction,
     régime — pour valider ou invalider chaque pattern.

Sans mesure → on croit à des patterns faux.
Avec mesure → on sait ce qui a un edge réel.

C'est la naissance du moteur de recherche d'edge.

Utilisation dans advisor_loop :
    # À la détection :
    sweep_tracker.register(sweep_event, entry_price=current_price, symbol=symbol)

    # Chaque cycle, pour chaque position en cours :
    sweep_tracker.tick(symbol, current_candles)

    # Périodiquement :
    stats = sweep_tracker.edge_stats()
    # → win_rate, avg_move_pct, avg_rr, best_regime, count...
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger
from quant_hedge_ai.agents.intelligence.sweep_detector import SweepEvent

_log = get_logger("sweep_outcome_tracker")

_DB_PATH = Path("databases/sweep_outcomes.sqlite")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sweep_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    sweep_type      TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    regime          TEXT    NOT NULL,
    sweep_strength  REAL    NOT NULL,
    volume_ratio    REAL    NOT NULL,
    wick_ratio      REAL    NOT NULL,
    confidence      REAL    NOT NULL,
    entry_price     REAL    NOT NULL,
    entry_ts        REAL    NOT NULL,
    -- Outcome fields (NULL tant que non résolu)
    exit_price      REAL,
    exit_ts         REAL,
    outcome         TEXT,   -- 'continuation' | 'reversal' | 'neutral'
    move_pct        REAL,   -- mouvement prix % depuis entrée
    max_adverse_pct REAL,   -- drawdown max adverse
    rr              REAL,   -- risk/reward réalisé (si on avait tradé)
    horizon_candles INTEGER,
    resolved        INTEGER DEFAULT 0
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_sweep_event_id ON sweep_outcomes (event_id);
CREATE INDEX IF NOT EXISTS idx_sweep_symbol   ON sweep_outcomes (symbol);
CREATE INDEX IF NOT EXISTS idx_sweep_resolved ON sweep_outcomes (resolved);
"""


@dataclass
class SweepOutcome:
    event_id: str
    symbol: str
    sweep_type: str
    direction: str
    regime: str
    sweep_strength: float
    volume_ratio: float
    wick_ratio: float
    confidence: float
    entry_price: float
    entry_ts: float
    exit_price: Optional[float] = None
    exit_ts: Optional[float] = None
    outcome: Optional[str] = None
    move_pct: Optional[float] = None
    max_adverse_pct: Optional[float] = None
    rr: Optional[float] = None
    horizon_candles: int = 15
    resolved: bool = False


@dataclass
class EdgeStats:
    """Statistiques d'edge pour un groupe de sweeps."""

    count: int = 0
    resolved: int = 0
    win_rate: float = 0.0
    avg_move_pct: float = 0.0
    avg_max_adverse: float = 0.0
    avg_rr: float = 0.0
    best_regime: str = ""
    by_regime: dict = field(default_factory=dict)
    by_type: dict = field(default_factory=dict)

    def summary(self) -> str:
        if self.resolved == 0:
            return "EdgeStats: pas encore de données résolues."
        return (
            f"EdgeStats: n={self.resolved} "
            f"win={self.win_rate:.0%} "
            f"avg_move={self.avg_move_pct:+.2%} "
            f"avg_rr={self.avg_rr:.2f} "
            f"best_regime={self.best_regime}"
        )


class SweepOutcomeTracker:
    """
    Suit le devenir de chaque SweepEvent détecté.

    Thread-safe. Persistance SQLite.

    Usage :
        tracker = SweepOutcomeTracker()

        # À la détection d'un sweep :
        tracker.register(event, entry_price=price, regime="sideways")

        # À chaque cycle (pour évaluer les outcomes) :
        tracker.tick(symbol, current_price, candles_since_entry)

        # Pour mesurer l'edge :
        stats = tracker.edge_stats()
        print(stats.summary())
    """

    def __init__(
        self,
        db_path: Path = _DB_PATH,
        horizon_candles: int = 15,
    ) -> None:
        self._db_path = db_path
        self._horizon = horizon_candles
        self._lock = threading.Lock()
        self._pending: dict[str, SweepOutcome] = {}  # event_id → outcome en attente
        self._candle_counts: dict[str, int] = {}  # event_id → nb candles écoulées
        self._adverse_track: dict[str, float] = {}  # event_id → max adverse %

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._reload_pending()

    # ── Init DB ───────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            for stmt in _CREATE_INDEX.strip().split(";"):
                if stmt.strip():
                    conn.execute(stmt)

    def _connect(self):
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return _ctx()

    def _reload_pending(self) -> None:
        """Recharge les outcomes non résolus au démarrage."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT event_id, symbol, sweep_type, direction, regime,
                              sweep_strength, volume_ratio, wick_ratio, confidence,
                              entry_price, entry_ts, horizon_candles
                       FROM sweep_outcomes WHERE resolved = 0"""
                ).fetchall()
            for r in rows:
                out = SweepOutcome(
                    event_id=r[0],
                    symbol=r[1],
                    sweep_type=r[2],
                    direction=r[3],
                    regime=r[4],
                    sweep_strength=r[5],
                    volume_ratio=r[6],
                    wick_ratio=r[7],
                    confidence=r[8],
                    entry_price=r[9],
                    entry_ts=r[10],
                    horizon_candles=r[11],
                )
                self._pending[r[0]] = out
                self._candle_counts[r[0]] = 0
                self._adverse_track[r[0]] = 0.0
            if self._pending:
                _log.info("SWEEP_TRACKER_RELOAD", pending=len(self._pending))
        except Exception as exc:
            _log.error("SWEEP_TRACKER_RELOAD_FAILED", error=str(exc))

    # ── API publique ──────────────────────────────────────────────────────────

    def register(
        self,
        event: SweepEvent,
        entry_price: float,
        regime: str = "unknown",
    ) -> None:
        """Enregistre un SweepEvent pour suivi. Appelé à la détection."""
        out = SweepOutcome(
            event_id=event.event_id,
            symbol=event.symbol,
            sweep_type=event.sweep_type,
            direction=event.direction,
            regime=regime,
            sweep_strength=event.sweep_strength,
            volume_ratio=event.volume_ratio,
            wick_ratio=event.wick_ratio,
            confidence=event.confidence,
            entry_price=entry_price,
            entry_ts=time.time(),
            horizon_candles=self._horizon,
        )
        with self._lock:
            self._pending[event.event_id] = out
            self._candle_counts[event.event_id] = 0
            self._adverse_track[event.event_id] = 0.0

        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO sweep_outcomes
                       (event_id, symbol, sweep_type, direction, regime,
                        sweep_strength, volume_ratio, wick_ratio, confidence,
                        entry_price, entry_ts, horizon_candles)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        out.event_id,
                        out.symbol,
                        out.sweep_type,
                        out.direction,
                        out.regime,
                        out.sweep_strength,
                        out.volume_ratio,
                        out.wick_ratio,
                        out.confidence,
                        out.entry_price,
                        out.entry_ts,
                        out.horizon_candles,
                    ),
                )
        except Exception as exc:
            _log.error("SWEEP_REGISTER_FAILED", error=str(exc), event_id=event.event_id)

    def tick(self, symbol: str, current_price: float) -> None:
        """
        Appelé à chaque bougie pour un symbole donné.
        Résout les outcomes dont l'horizon est atteint.
        """
        with self._lock:
            to_resolve = []
            for eid, out in self._pending.items():
                if out.symbol != symbol:
                    continue
                self._candle_counts[eid] = self._candle_counts.get(eid, 0) + 1

                # Tracking adverse
                if out.direction == "long":
                    adverse_pct = (out.entry_price - current_price) / out.entry_price
                else:
                    adverse_pct = (current_price - out.entry_price) / out.entry_price
                self._adverse_track[eid] = max(
                    self._adverse_track.get(eid, 0.0), adverse_pct
                )

                if self._candle_counts[eid] >= out.horizon_candles:
                    to_resolve.append((eid, current_price))

            for eid, exit_price in to_resolve:
                self._resolve(eid, exit_price)

    def edge_stats(self, symbol: Optional[str] = None) -> EdgeStats:
        """Retourne les statistiques d'edge agrégées sur tous les sweeps résolus."""
        try:
            query = (
                "SELECT direction, sweep_type, regime, move_pct, max_adverse_pct, rr"
                " FROM sweep_outcomes WHERE resolved = 1"
            )
            params: tuple = ()
            if symbol:
                query += " AND symbol = ?"
                params = (symbol,)
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()
        except Exception as exc:
            _log.error("EDGE_STATS_FAILED", error=str(exc))
            return EdgeStats()

        if not rows:
            return EdgeStats(count=0, resolved=0)

        # Aggrégation
        wins = 0
        moves = []
        adverses = []
        rrs = []
        by_regime: dict[str, list[float]] = {}
        by_type: dict[str, list[float]] = {}

        for direction, sweep_type, regime, move_pct, adverse, rr in rows:
            # "win" = move dans la direction attendue
            if move_pct is not None:
                move = move_pct * (1 if direction == "long" else -1)
                moves.append(move)
                if move > 0:
                    wins += 1
                by_regime.setdefault(regime, []).append(move)
                by_type.setdefault(sweep_type, []).append(move)
            if adverse is not None:
                adverses.append(adverse)
            if rr is not None:
                rrs.append(rr)

        n = len(rows)
        resolved = len(moves)
        best_regime = (
            max(by_regime, key=lambda r: sum(by_regime[r]) / len(by_regime[r]))
            if by_regime
            else ""
        )

        stats = EdgeStats(
            count=n,
            resolved=resolved,
            win_rate=wins / resolved if resolved else 0.0,
            avg_move_pct=sum(moves) / resolved if resolved else 0.0,
            avg_max_adverse=sum(adverses) / len(adverses) if adverses else 0.0,
            avg_rr=sum(rrs) / len(rrs) if rrs else 0.0,
            best_regime=best_regime,
            by_regime={r: sum(v) / len(v) for r, v in by_regime.items()},
            by_type={t: sum(v) / len(v) for t, v in by_type.items()},
        )

        _log.info(
            "EDGE_STATS_COMPUTED",
            resolved=resolved,
            win_rate=round(stats.win_rate, 3),
            avg_move=round(stats.avg_move_pct, 4),
            best_regime=best_regime,
        )
        return stats

    # ── Résolution ────────────────────────────────────────────────────────────

    def _resolve(self, event_id: str, exit_price: float) -> None:
        """Résout un outcome. Appelé depuis tick() sous lock."""
        out = self._pending.pop(event_id, None)
        if out is None:
            return

        max_adverse = self._adverse_track.pop(event_id, 0.0)
        self._candle_counts.pop(event_id, None)

        # Move depuis entrée
        if out.direction == "long":
            move_pct = (exit_price - out.entry_price) / out.entry_price
        else:
            move_pct = (out.entry_price - exit_price) / out.entry_price

        # Outcome qualitatif
        if move_pct > 0.003:
            outcome = "continuation"
        elif move_pct < -0.003:
            outcome = "reversal"
        else:
            outcome = "neutral"

        # RR approximatif (si on avait pris un SL à 1% et cherché 2%)
        sl_pct = 0.01
        tp_pct = 0.02
        rr = move_pct / sl_pct if move_pct > 0 else -(abs(move_pct) / sl_pct)

        try:
            with self._connect() as conn:
                conn.execute(
                    """UPDATE sweep_outcomes
                       SET exit_price=?, exit_ts=?, outcome=?,
                           move_pct=?, max_adverse_pct=?, rr=?, resolved=1
                       WHERE event_id=?""",
                    (
                        exit_price,
                        time.time(),
                        outcome,
                        move_pct,
                        max_adverse,
                        rr,
                        event_id,
                    ),
                )
        except Exception as exc:
            _log.error("SWEEP_RESOLVE_FAILED", error=str(exc), event_id=event_id)
            return

        _log.decision(
            "SWEEP_RESOLVED",
            event_id=event_id,
            symbol=out.symbol,
            sweep_type=out.sweep_type,
            direction=out.direction,
            regime=out.regime,
            outcome=outcome,
            move_pct=round(move_pct, 4),
            max_adverse_pct=round(max_adverse, 4),
            rr=round(rr, 2),
            sweep_strength=out.sweep_strength,
            horizon_candles=out.horizon_candles,
        )
