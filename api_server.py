"""
api_server.py — Backend JSON pour le dashboard React.
Port 8000 — lit depuis les fichiers JSONL/JSON existants.

Usage:
    python -m uvicorn api_server:app --port 8000 --reload
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

BASE = Path(__file__).parent
BLACK_BOX = BASE / "databases" / "black_box.jsonl"
CYCLE_LOG = BASE / "databases" / "cycle_data.jsonl"
SNAPSHOT = BASE / "databases" / "live_snapshot.json"
TRADES = BASE / "logs" / "trades.jsonl"
AUDIT = BASE / "logs" / "execution_audit" / "audit.jsonl"
MISTAKE_MEMORY = BASE / "databases" / "mistake_memory.jsonl"
STRATEGY_RANKING = BASE / "databases" / "strategy_ranking.json"
MULTI_EXCHANGE = BASE / "databases" / "multi_exchange_snapshot.json"
EXP_001 = BASE / "experiments" / "EXP-001.yaml"

app = FastAPI(title="CryptoAI API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── I/O helpers ───────────────────────────────────────────────────────────────


def read_jsonl(path: Path, max_lines: int = 5000) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out: list[dict] = []
    for line in lines[-max_lines:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Mapping helpers ───────────────────────────────────────────────────────────

_REGIME_MAP: dict[str, str] = {
    "bull_trend": "TREND_BULL",
    "trend_bull": "TREND_BULL",
    "bullish": "TREND_BULL",
    "bear_trend": "TREND_BEAR",
    "trend_bear": "TREND_BEAR",
    "bearish": "TREND_BEAR",
    "volatile": "VOLATILE",
    "volatility": "VOLATILE",
    "sideways": "RANGE",
    "range": "RANGE",
}


def map_regime(r: str) -> str:
    return _REGIME_MAP.get((r or "").lower(), "UNKNOWN")


_CONVICTION_MAP: dict[str, str] = {
    "very_high": "VERY_HIGH",
    "very high": "VERY_HIGH",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "minimal": "SKIP",
    "skip": "SKIP",
    "unknown": "SKIP",
}


def map_conviction(c: str) -> str:
    return _CONVICTION_MAP.get((c or "").lower(), "SKIP")


def map_signal(s: dict) -> str:
    if not s.get("gate_allowed", True):
        return "block"
    score = s.get("score", 0)
    signal = (s.get("signal", "") or "").upper()
    if signal in ("BUY", "SELL") or score >= 70:
        return "trade"
    if score >= 50:
        return "watch"
    return "hold"


# ── Module health (from file existence) ───────────────────────────────────────

_MODULES = [
    ("SignalEngine", "quant_hedge_ai/agents/execution/signal_engine.py", 0),
    ("ExecutionEngine", "quant_hedge_ai/agents/execution/execution_engine.py", 0),
    ("PositionManager", "quant_hedge_ai/agents/execution/position_manager.py", 0),
    ("PortfolioBrain", "quant_hedge_ai/agents/risk/portfolio_brain.py", 0),
    ("RiskGate", "quant_hedge_ai/agents/risk/global_risk_gate.py", 0),
    ("ConvictionEngine", "quant_hedge_ai/agents/intelligence/conviction_engine.py", 0),
    ("MetaStrategy", "quant_hedge_ai/agents/intelligence/meta_strategy_engine.py", 0),
    ("BlackBox", "databases/black_box.jsonl", 1000),
    ("MistakeMemory", "databases/mistake_memory.jsonl", 0),
    ("WatchdogVPS", "watchdog_vps.py", 0),
    ("CycleData", "databases/cycle_data.jsonl", 1000),
    ("StrategyRanking", "databases/strategy_ranking.json", 100),
]


def build_modules() -> list[dict]:
    result = []
    now_ms = time.time() * 1000
    for name, fpath, min_bytes in _MODULES:
        p = BASE / fpath
        if not p.exists():
            status, last_ms = "offline", 0
        elif min_bytes > 0 and p.stat().st_size < min_bytes:
            status, last_ms = "warn", 0
        else:
            mtime_ms = p.stat().st_mtime * 1000
            last_ms = int(now_ms - mtime_ms)
            status = "ok"
        result.append({"name": name, "status": status, "last_tick_ms": last_ms})
    return result


# ── /api/snapshot ─────────────────────────────────────────────────────────────


@app.get("/api/snapshot")
def get_snapshot() -> dict:
    snap = read_json(SNAPSHOT)
    trades = read_jsonl(TRADES, max_lines=500)

    exits = [t for t in trades if t.get("type") == "exit"]

    # PnL du jour UTC
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_exits = [t for t in exits if str(t.get("logged_at", "")).startswith(today)]
    daily_pnl = round(sum(t.get("pnl_usd", 0) for t in day_exits), 4)

    # Win rate sur les 100 derniers trades
    last100 = exits[-100:]
    wins = sum(1 for t in last100 if t.get("win"))
    win_rate = round(wins / len(last100) * 100, 1) if last100 else 0.0

    # Symboles avec champs normalisés
    symbols = []
    for s in snap.get("symbols", []):
        symbols.append(
            {
                "symbol": s.get("symbol", ""),
                "prix": s.get("prix", 0),
                "score": s.get("score", 0),
                "regime": map_regime(s.get("regime", "")),
                "signal_kind": map_signal(s),
                "gate_allowed": s.get("gate_allowed", False),
                "actionable": s.get("actionable", False),
                "conviction": map_conviction(s.get("conviction_level", "")),
                "indicators": {
                    "rsi": s.get("rsi"),
                    "bb_pct": s.get("bb_pct"),
                    "atr": s.get("atr_ratio"),
                    "macd_bull": s.get("macd_bullish", False),
                    "ema_bull": s.get("ema_bullish", False),
                    "squeeze": s.get("bb_squeeze", False),
                },
            }
        )

    return {
        "capital_usd": snap.get("capital", 0),
        "daily_pnl": daily_pnl,
        "open_positions": len(snap.get("positions", [])),
        "win_rate_7d": win_rate,
        "mode": "testnet",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "cycle": snap.get("cycle", 0),
        "safe_mode": snap.get("safe_mode", False),
        "n_symbols": snap.get("n_symbols", 0),
        "n_actionable": snap.get("n_actionable", 0),
        "cycle_duration_ms": snap.get("cycle_duration_ms", 0),
        "refusal_breakdown": snap.get("refusal_breakdown", {}),
        "regime_distribution": snap.get("regime_distribution", {}),
        "exchange": snap.get("exchange", {}),
        "symbols": symbols,
        "positions": snap.get("positions", []),
        "modules": build_modules(),
    }


# ── /api/decisions ────────────────────────────────────────────────────────────


@app.get("/api/decisions")
def get_decisions() -> dict:
    records = read_jsonl(BLACK_BOX, max_lines=5000)
    decisions = [
        r for r in records if r.get("decision_type") not in ("SYSTEM_EVENT", None)
    ][-300:]

    result = []
    for d in reversed(decisions):
        dt = d.get("decision_type", "")
        if dt in ("TRADE_EXECUTED", "BUY", "SELL"):
            state = "EXECUTED"
        elif dt == "POSITION_CLOSED":
            state = "CLOSED"
        elif dt == "TRADE_REFUSED":
            state = "REJECTED"
        elif dt == "HOLD":
            state = "CREATED"
        else:
            state = "CREATED"

        refused = d.get("refused_by", [])
        reason = (d.get("reason") or (refused[0] if refused else ""))[:100]

        result.append(
            {
                "id": f"bb-{d.get('cycle',0)}-{d.get('symbol','')}",
                "symbol": d.get("symbol", ""),
                "state": state,
                "decision_type": dt,
                "score": d.get("score", 0),
                "conviction": map_conviction(d.get("conviction_level", "")),
                "regime": map_regime(d.get("regime", "")),
                "rejection_reason": reason if state == "REJECTED" else None,
                "created_at": datetime.fromtimestamp(
                    d.get("ts", 0), tz=timezone.utc
                ).strftime("%H:%M:%S"),
                "duration_ms": 0,
            }
        )

    return {"decisions": result}


# ── /api/trades ───────────────────────────────────────────────────────────────


@app.get("/api/trades")
def get_trades() -> dict:
    records = read_jsonl(TRADES, max_lines=500)
    entries = {r["id"]: r for r in records if r.get("type") == "entry"}
    exits = [r for r in records if r.get("type") == "exit"]

    closed = []
    for ex in reversed(exits[-100:]):
        eid = ex.get("id", "")
        entry = entries.get(eid, {})
        pnl_pct = ex.get("pnl_pct", 0)
        pnl_usd = ex.get("pnl_usd", 0)
        win = ex.get("win", pnl_usd > 0)

        # R-multiple: pnl_pct / atr_pct
        atr_pct = entry.get("atr_pct") or ex.get("atr_pct") or 0.02
        r_mult = round(pnl_pct / atr_pct, 2) if atr_pct else 0.0

        # Postmortem basé sur confidence + win
        conf = ex.get("confidence") or entry.get("confidence") or 0
        if conf >= 0.7:
            pm = "VALIDATED" if win else "UNLUCKY"
        else:
            pm = "LUCKY" if win else "MISTAKE"

        # Sparkline depuis price_path
        price_path = ex.get("price_path", [])
        if len(price_path) >= 2:
            e0 = price_path[0]
            size = ex.get("size", 1) or 1
            series = [round((p - e0) * size, 4) for p in price_path]
        else:
            series = [0.0, round(pnl_usd, 4)]

        regime_raw = ex.get("regime") or entry.get("regime", "")
        conv_raw = (
            ex.get("conviction_level")
            or entry.get("conviction_level")
            or ex.get("confidence_level", "")
        )

        closed.append(
            {
                "id": eid,
                "symbol": ex.get("symbol", ""),
                "side": "long" if ex.get("direction", "long") == "long" else "short",
                "pnl_usd": round(pnl_usd, 4),
                "pnl_pct": round(pnl_pct * 100, 4),
                "r_multiple": r_mult,
                "regime": map_regime(regime_raw),
                "conviction": map_conviction(conv_raw),
                "postmortem": pm,
                "duration_ms": int(ex.get("duration_min", 0) * 60_000),
                "closed_at": (ex.get("logged_at") or "")[:16].replace("T", " "),
                "pnl_series": series,
            }
        )

    # Positions ouvertes depuis snapshot
    snap = read_json(SNAPSHOT)
    open_pos = []
    for p in snap.get("positions", []):
        open_pos.append(
            {
                "id": p.get("id", p.get("symbol", "")),
                "symbol": p.get("symbol", ""),
                "side": p.get("direction", "long"),
                "size": p.get("size", 0),
                "entry_price": p.get("entry_price", 0),
                "current_price": p.get("current_price", p.get("entry_price", 0)),
                "pnl_usd": p.get("pnl_usd", 0),
                "pnl_pct": p.get("pnl_pct", 0),
                "sl_price": p.get("stop_loss"),
                "tp_price": p.get("take_profit"),
                "regime": map_regime(p.get("regime", "")),
                "conviction": map_conviction(p.get("conviction_level", "")),
                "subaccount": p.get("subaccount", "main"),
                "opened_at": (p.get("opened_at") or p.get("logged_at") or "")[:16],
                "pnl_series": [0, p.get("pnl_usd", 0)],
            }
        )

    return {"closed": closed, "open": open_pos}


# ── /api/health ───────────────────────────────────────────────────────────────


# ── /api/scientific — tableau de bord EXP-001 (read-only) ───────────────────


def _parse_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml  # PyYAML optional; endpoint degrades gracefully if absent

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        return {}
    except Exception:
        return {}


def _gate_status(current: int, required: int) -> str:
    if current >= required:
        return "PASSED"
    if current > 0:
        return "IN_PROGRESS"
    return "LOCKED"


@app.get("/api/scientific")
def get_scientific() -> dict:
    exp = _parse_yaml(EXP_001)

    # Progress — same source and logic as /api/trades
    records = read_jsonl(TRADES, max_lines=500)
    exits = [r for r in records if r.get("type") == "exit"]
    n_closed = len(exits)
    wins = [t for t in exits if t.get("win", t.get("pnl_usd", 0) > 0)]
    losers = [t for t in exits if not t.get("win", t.get("pnl_usd", 0) > 0)]
    wr = round(len(wins) / n_closed * 100, 1) if n_closed else 0.0
    gross_profit = sum(t.get("pnl_usd", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl_usd", 0) for t in losers))
    pf = (
        round(gross_profit / gross_loss, 3)
        if gross_loss > 0
        else (999.0 if gross_profit > 0 else 0.0)
    )
    pnl_paper = round(sum(t.get("pnl_usd", 0) for t in exits), 4)

    manifest = exp.get("dataset_manifest") or {}
    ctx = exp.get("context") or {}

    experiment = {
        "id": exp.get("id", "EXP-001"),
        "title": exp.get("title", ""),
        "status": exp.get("status", ""),
        "objective": (exp.get("objective") or "").strip(),
        "dataset_uuid": manifest.get("uuid", ""),
        "date_start": ctx.get("date_start", ""),
        "date_end": ctx.get("date_end"),
        "engine_version": ctx.get("engine_version", ""),
        "hypotheses": [str(h) for h in (exp.get("hypotheses_testées") or [])],
    }

    # Seuils Règle du statisticien (CLAUDE.md)
    gates = [
        {
            "id": "n_dip_gate",
            "label": "Gate analyse DIP (N≥50)",
            "required": 50,
            "current": n_closed,
            "status": _gate_status(n_closed, 50),
        },
        {
            "id": "n_total",
            "label": "Trades totaux",
            "required": 500,
            "current": n_closed,
            "status": _gate_status(n_closed, 500),
        },
        {
            "id": "n_winners",
            "label": "Winners",
            "required": 150,
            "current": len(wins),
            "status": _gate_status(len(wins), 150),
        },
        {
            "id": "n_losers",
            "label": "Losers",
            "required": 150,
            "current": len(losers),
            "status": _gate_status(len(losers), 150),
        },
        {
            "id": "n_market_regime",
            "label": "Par régime de marché",
            "required": 50,
            "current": 0,
            "status": "LOCKED",
        },
        {
            "id": "n_blocking_layer",
            "label": "Par couche bloqueuse",
            "required": 30,
            "current": 0,
            "status": "LOCKED",
        },
        {
            "id": "cri",
            "label": "CRI ≥ 90/100",
            "required": 90,
            "current": 0,
            "status": "LOCKED",
        },
    ]

    return {
        "experiment": experiment,
        "progress": {
            "n_closed": n_closed,
            "n_required": 50,
            "n_calibration": 500,
            "wr": wr,
            "pf": pf,
            "pnl_paper": pnl_paper,
        },
        "gates": gates,
        "hypotheses": [],
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ts": time.time()}


# ── /api/raw/* — fichiers bruts pour vps_data_sync.py (PC local) ─────────────


@app.get("/api/raw/snapshot")
def raw_snapshot() -> dict:
    return read_json(SNAPSHOT)


@app.get("/api/raw/blackbox")
def raw_blackbox(n: int = 1000) -> dict:
    return {"lines": read_jsonl(BLACK_BOX, max_lines=n)}


@app.get("/api/raw/trades")
def raw_trades(n: int = 500) -> dict:
    return {"lines": read_jsonl(TRADES, max_lines=n)}


@app.get("/api/raw/audit")
def raw_audit(n: int = 500) -> dict:
    return {"lines": read_jsonl(AUDIT, max_lines=n)}


@app.get("/api/raw/cycles")
def raw_cycles(n: int = 1000) -> dict:
    return {"lines": read_jsonl(CYCLE_LOG, max_lines=n)}


@app.get("/api/raw/strategy_ranking")
def raw_strategy_ranking() -> dict:
    return read_json(STRATEGY_RANKING)


@app.get("/api/raw/mistake_memory")
def raw_mistake_memory(n: int = 500) -> dict:
    return {"lines": read_jsonl(MISTAKE_MEMORY, max_lines=n)}


@app.get("/api/raw/multi_exchange")
def raw_multi_exchange() -> dict:
    return read_json(MULTI_EXCHANGE)
