"""
risk_dashboard_api.py — Risk Dashboard temps réel (Idée #2).

Expose un serveur FastAPI minimal avec :
  GET /snapshot          → état complet du portefeuille
  GET /equity_curve      → courbe d'équité (200 derniers points)
  GET /drawdown          → drawdown courant + max
  GET /pnl_by_strategy   → PnL par stratégie
  GET /pnl_by_regime     → PnL par régime
  GET /rolling_sharpe    → Sharpe rolling 30 trades
  GET /rolling_winrate   → Winrate rolling 30 trades
  GET /mae_mfe           → Max Adverse / Favorable Excursion
  GET /exposure          → exposition totale et par symbole

Peut tourner en arrière-plan :
    api = RiskDashboardAPI(paper_engine)
    api.run_background(port=8765)

Ou en serveur bloquant :
    uvicorn.run(api.app, host="0.0.0.0", port=8765)
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Any

logger = logging.getLogger(__name__)


def _make_app(paper_engine, shadow_engine=None):
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError("fastapi requis : pip install fastapi uvicorn")

    app = FastAPI(title="Risk Dashboard", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _equity_to_drawdown(curve: list[dict]) -> dict:
        if not curve:
            return {"current_dd": 0.0, "max_dd": 0.0, "peak": 0.0}
        values = [p["value"] for p in curve]
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        current_dd = (peak - values[-1]) / peak if peak > 0 else 0.0
        return {
            "current_dd": round(current_dd, 6),
            "current_dd_pct": round(current_dd * 100, 3),
            "max_dd": round(max_dd, 6),
            "max_dd_pct": round(max_dd * 100, 3),
            "peak": round(peak, 2),
        }

    def _rolling_sharpe(trades: list[dict], window: int = 30) -> float:
        sells = [t for t in trades if t.get("action") == "SELL"][-window:]
        if len(sells) < 5:
            return 0.0
        returns = [t.get("pnl", 0.0) for t in sells]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        return round((mean / std) * math.sqrt(252), 4)

    def _rolling_winrate(trades: list[dict], window: int = 30) -> float:
        sells = [t for t in trades if t.get("action") == "SELL"][-window:]
        if not sells:
            return 0.0
        wins = sum(1 for t in sells if t.get("pnl", 0.0) > 0)
        return round(wins / len(sells), 4)

    def _pnl_by_key(trades: list[dict], key: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for t in trades:
            k = t.get(key, "unknown")
            result[k] = round(result.get(k, 0.0) + t.get("pnl", 0.0), 4)
        return result

    def _mae_mfe(trades: list[dict]) -> dict:
        maes = [t.get("pnl", 0.0) for t in trades if t.get("pnl", 0.0) < 0]
        mfes = [t.get("pnl", 0.0) for t in trades if t.get("pnl", 0.0) > 0]
        return {
            "max_adverse_excursion": round(min(maes, default=0.0), 4),
            "max_favorable_excursion": round(max(mfes, default=0.0), 4),
            "avg_adverse_excursion": round(
                sum(maes) / len(maes) if maes else 0.0, 4
            ),
            "avg_favorable_excursion": round(
                sum(mfes) / len(mfes) if mfes else 0.0, 4
            ),
        }

    # ── Endpoints ──────────────────────────────────────────────────────────────

    @app.get("/snapshot")
    def snapshot() -> dict[str, Any]:
        snap = paper_engine.snapshot()
        ec = snap.get("equity_curve", [])
        dd = _equity_to_drawdown(ec)
        return {**snap, "drawdown": dd}

    @app.get("/equity_curve")
    def equity_curve() -> dict:
        return {"equity_curve": paper_engine.equity_curve[-200:]}

    @app.get("/drawdown")
    def drawdown() -> dict:
        return _equity_to_drawdown(paper_engine.equity_curve)

    @app.get("/pnl_by_strategy")
    def pnl_by_strategy() -> dict:
        trades = paper_engine.trade_history
        return {"pnl_by_strategy": _pnl_by_key(trades, "strategy_name")}

    @app.get("/pnl_by_regime")
    def pnl_by_regime() -> dict:
        trades = paper_engine.trade_history
        return {"pnl_by_regime": _pnl_by_key(trades, "regime")}

    @app.get("/rolling_sharpe")
    def rolling_sharpe(window: int = 30) -> dict:
        return {
            "rolling_sharpe": _rolling_sharpe(paper_engine.trade_history, window),
            "window": window,
        }

    @app.get("/rolling_winrate")
    def rolling_winrate(window: int = 30) -> dict:
        return {
            "rolling_winrate": _rolling_winrate(paper_engine.trade_history, window),
            "window": window,
        }

    @app.get("/mae_mfe")
    def mae_mfe() -> dict:
        return _mae_mfe(paper_engine.trade_history)

    @app.get("/exposure")
    def exposure() -> dict:
        positions = {
            k: round(v, 6)
            for k, v in paper_engine.positions.items()
            if v > 0
        }
        return {
            "n_open_positions": len(positions),
            "positions": positions,
            "balance": round(paper_engine.balance, 2),
        }

    @app.get("/shadow_stats")
    def shadow_stats() -> dict:
        if shadow_engine is None:
            return {"enabled": False}
        return {"enabled": True, **shadow_engine.stats()}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


class RiskDashboardAPI:
    """
    Wrapper autour de l'app FastAPI.

    Usage:
        api = RiskDashboardAPI(paper_engine)
        api.run_background(port=8765)     # non-bloquant
        # ou
        api.run(port=8765)                # bloquant
    """

    def __init__(self, paper_engine, shadow_engine=None) -> None:
        self.app = _make_app(paper_engine, shadow_engine)
        self._server_thread: threading.Thread | None = None

    def run(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        try:
            import uvicorn
        except ImportError:
            raise ImportError("uvicorn requis : pip install uvicorn")
        logger.info("[RiskDashboard] Démarrage sur http://%s:%d", host, port)
        uvicorn.run(self.app, host=host, port=port, log_level="warning")

    def run_background(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        def _target():
            try:
                import uvicorn
                uvicorn.run(
                    self.app, host=host, port=port,
                    log_level="warning", access_log=False
                )
            except Exception as exc:
                logger.error("[RiskDashboard] Erreur serveur: %s", exc)

        self._server_thread = threading.Thread(
            target=_target, daemon=True, name="RiskDashboard"
        )
        self._server_thread.start()
        logger.info("[RiskDashboard] Background démarré sur http://%s:%d", host, port)
