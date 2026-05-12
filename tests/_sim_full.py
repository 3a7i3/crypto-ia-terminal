"""Test end-to-end : aucun crash, logs cohérents, pas de bug silencieux."""
import json
import math
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mvp.trade_logger as tl
import tracker_system.trade_tracker as tt
import tracker_system.auto_backtester as ab
from tracker_system.trade_tracker import (
    close_position, load_positions, open_position, save_positions,
)
from tracker_system.exit_engine import (
    BreakEvenRule, ExitEngine, TPSLRule, TrailingStopRule,
)
from tracker_system.tracker import create_trade_note, load_exits, update_dashboard
from tracker_system.core.event_writer import record_entry_from_mvp, record_exit_from_mvp

# ── Fichiers isolés ───────────────────────────────────────────────────────────
TEST_LOG   = Path("logs/_sim_trades.jsonl")
TEST_STATE = Path("logs/_sim_positions.json")
TEST_VAULT = Path("logs/_sim_vault")
TEST_OPT   = Path("logs/_sim_optimizer.json")

for f in [TEST_LOG, TEST_STATE, TEST_OPT]:
    f.unlink(missing_ok=True)
shutil.rmtree(TEST_VAULT, ignore_errors=True)

tl._LOG_FILE  = TEST_LOG
tt.LOG_FILE   = TEST_LOG
tt.STATE_FILE = TEST_STATE
ab.LOG_FILE   = TEST_LOG

# ── Jeu de trades ─────────────────────────────────────────────────────────────
TRADES = [
    dict(symbol="BTC/USDT", direction="long",  signal="momentum",
         regime="bullish", entry=65000, exit_p=66300, sl=63500,  tp=67500,
         size=50, score=75, conf=0.80, atr=0.015,
         path=[65000, 65300, 65700, 66000, 66300], expected="win"),
    dict(symbol="ETH/USDT", direction="long",  signal="breakout",
         regime="bullish", entry=3000, exit_p=2940, sl=2910, tp=3150,
         size=40, score=68, conf=0.72, atr=0.018,
         path=[3000, 2985, 2960, 2940], expected="loss"),
    dict(symbol="SOL/USDT", direction="short", signal="mean_revert",
         regime="bearish", entry=150, exit_p=147, sl=153, tp=144,
         size=30, score=70, conf=0.75, atr=0.020,
         path=[150, 149, 148, 147], expected="win"),
    dict(symbol="BTC/USDT", direction="long",  signal="momentum",
         regime="range",    entry=64000, exit_p=63360, sl=62720, tp=66560,
         size=50, score=62, conf=0.65, atr=0.014,
         path=[64000, 63800, 63600, 63360], expected="loss"),
    dict(symbol="ETH/USDT", direction="short", signal="breakout",
         regime="bearish",  entry=3100, exit_p=3007, sl=3162, tp=2976,
         size=45, score=73, conf=0.78, atr=0.017,
         path=[3100, 3060, 3030, 3007], expected="win"),
]

# ── Phase 1 : 5 trades entry → exit ─────────────────────────────────────────
print("=== PHASE 1 : 5 trades entry→exit ===")
records = []
for i, t in enumerate(TRADES):
    tl.log_signal(t["symbol"], t["signal"], t["direction"],
                  t["score"], t["conf"], t["entry"], t["regime"], True)

    record_entry_from_mvp(t["symbol"], t["direction"], t["signal"], t["regime"],
                          t["entry"], t["size"], t["sl"], t["tp"],
                          t["score"], t["conf"], t["atr"], True, log_file=TEST_LOG)

    open_position(
        t["symbol"], t["direction"], t["signal"], t["regime"],
        t["entry"], t["size"], t["sl"], t["tp"],
        t["score"], t["conf"], t["atr"], True, timestamp=time.time(),
    )

    positions = load_positions()
    pos = next(p for p in positions if p["symbol"] == t["symbol"])
    pos["price_path"] = t["path"]
    rec = close_position(pos, t["exit_p"],
                         "TP" if t["expected"] == "win" else "SL",
                         write_log=False)
    positions = [p for p in positions if p["symbol"] != t["symbol"]]
    save_positions(positions)

    record_exit_from_mvp(
        t["symbol"], t["direction"], t["signal"], t["regime"],
        t["entry"], t["exit_p"], t["size"],
        rec["pnl_usd"], rec["pnl_pct"], rec["exit_reason"],
        45.0, "validated", 0.02, t["path"], log_file=TEST_LOG,
    )

    assert rec["win"] == (t["expected"] == "win"), \
        f"Trade {i+1} win incorrect: {rec['win']} vs {t['expected']}"
    records.append(rec)
    print(f"  [{i+1}] {t['symbol']} {t['direction']} {t['expected'].upper()} "
          f"pnl={rec['pnl_usd']:+.2f}$ "
          f"mfe={rec['mfe']*100:+.2f}% mae={rec['mae']*100:+.2f}%")

# ── Phase 2 : JSONL structure et cohérence ────────────────────────────────────
print("\n=== PHASE 2 : JSONL cohérence ===")
raw_lines = TEST_LOG.read_text(encoding="utf-8").splitlines()
non_empty = [line for line in raw_lines if line.strip()]
assert len(raw_lines) == len(non_empty), "Lignes vides détectées dans le JSONL"

events = [json.loads(line) for line in non_empty]
counts = {t: sum(1 for e in events if e["type"] == t)
          for t in ["signal_detected", "entry", "exit"]}
print(f"  Counts: {counts}")
assert counts == {"signal_detected": 5, "entry": 5, "exit": 5}, \
    f"Double-write ou manque: {counts}"

for ev in events:
    assert "logged_at" in ev,  f"logged_at manquant dans {ev['type']}"
    assert "timestamp" in ev,  f"timestamp manquant dans {ev['type']}"
    for v in ev.values():
        if isinstance(v, float):
            assert not math.isnan(v), f"NaN dans {ev['type']}"
            assert not math.isinf(v), f"Inf dans {ev['type']}"
    if ev["type"] in ("signal_detected", "entry"):
        assert "price_path" not in ev, f"price_path inattendu dans {ev['type']}"
    if ev["type"] == "exit":
        assert isinstance(ev["price_path"], list)
        assert len(ev["price_path"]) <= 150, \
            f"price_path trop long: {len(ev['price_path'])}"
        assert isinstance(ev["win"], bool)
        assert (ev["pnl_usd"] > 0) == ev["win"], \
            f"win/pnl_usd incohérents: win={ev['win']} pnl={ev['pnl_usd']}"

print("  Aucun double-write, NaN/Inf absent, win cohérent, price_path ≤150")

# ── Phase 3 : MFE/MAE cohérence ──────────────────────────────────────────────
print("\n=== PHASE 3 : MFE/MAE ===")
for rec, t in zip(records, TRADES):
    path  = t["path"]
    entry = t["entry"]
    d     = t["direction"]
    if d == "long":
        exp_mfe = max((p - entry) / entry for p in path)
        exp_mae = min((p - entry) / entry for p in path)
    else:
        exp_mfe = max((entry - p) / entry for p in path)
        exp_mae = min((entry - p) / entry for p in path)

    assert abs(rec["mfe"] - round(exp_mfe, 6)) < 1e-7, \
        f"{t['symbol']} MFE incorrect: {rec['mfe']} vs {round(exp_mfe,6)}"
    assert abs(rec["mae"] - round(exp_mae, 6)) < 1e-7, \
        f"{t['symbol']} MAE incorrect: {rec['mae']} vs {round(exp_mae,6)}"
    print(f"  {t['symbol']} {d}: mfe={rec['mfe']*100:+.2f}% "
          f"mae={rec['mae']*100:+.2f}% — valeurs exactes OK")

# ── Phase 4 : exit_engine sur price_path réels ───────────────────────────────
print("\n=== PHASE 4 : exit_engine simulation ===")
eng = ExitEngine([
    TPSLRule(tp_override=0.02, sl_override=0.01),
    TrailingStopRule(trail_pct=0.005, activation_pct=0.01),
    BreakEvenRule(trigger_pct=0.01),
])
exits_in_log = [e for e in events if e["type"] == "exit"]
for ex in exits_in_log:
    pp = ex["price_path"]
    if not pp:
        print(f"  {ex['symbol']} — price_path vide, skip")
        continue
    pos_sim = {
        "entry_price": ex["entry_price"],
        "direction":   ex["direction"],
        "stop_loss":   ex["entry_price"] * (0.99 if ex["direction"] == "long" else 1.01),
        "take_profit": ex["entry_price"] * (1.02 if ex["direction"] == "long" else 0.98),
    }
    reason, ep = eng.check_path(pos_sim, pp)
    print(f"  {ex['symbol']} {ex['direction']}: "
          f"engine → {reason or 'HOLD'} @ {ep:.4f}")

# ── Phase 5 : tracker.py — notes Obsidian + dashboard ────────────────────────
print("\n=== PHASE 5 : notes Obsidian + dashboard ===")
TEST_VAULT.mkdir(parents=True, exist_ok=True)
loaded = load_exits(TEST_LOG)
assert len(loaded) == 5, f"load_exits: attendu 5, got {len(loaded)}"

for ex in loaded:
    create_trade_note(ex, TEST_VAULT)

update_dashboard(loaded, TEST_VAULT)

notes = list((TEST_VAULT / "03_Trades").glob("*.md"))
dash  = TEST_VAULT / "06_Dashboard" / "dashboard.md"
assert len(notes) == 5, f"attendu 5 notes, got {len(notes)}"
assert dash.exists(), "dashboard.md absent"
dash_txt = dash.read_text()
for kw in ("Winrate", "Expectancy", "MFE", "Par Régime"):
    assert kw in dash_txt, f"Mot-clé manquant dans dashboard: '{kw}'"
print(f"  {len(notes)} notes créées, dashboard complet")

# ── Phase 6 : auto_backtester ─────────────────────────────────────────────────
print("\n=== PHASE 6 : auto_backtester ===")
res = ab.run_backtest(min_trades=1, out_file=TEST_OPT, log_file=TEST_LOG)
assert res, "backtester résultat vide"
regimes = [k for k in res if not k.startswith("_")]
print(f"  Régimes: {regimes}")
for regime in regimes:
    best = res[regime].get("best", {})
    assert best.get("score") is not None, f"score absent pour {regime}"
    assert best.get("type") in ("tp_sl","trailing","hybrid"), \
        f"type inconnu pour {regime}: {best.get('type')}"
    print(f"  {regime}: best={best['type']} score={best['score']:.6f} "
          f"wr={best.get('win_rate',0):.0%}")

# ── Phase 7 : open_positions.json propre ─────────────────────────────────────
print("\n=== PHASE 7 : open_positions.json ===")
if TEST_STATE.exists():
    saved = json.loads(TEST_STATE.read_text())
    for p in saved:
        assert "price_path" not in p, "price_path persisté dans open_positions.json!"
    print(f"  {len(saved)} positions, price_path absent du fichier")
else:
    print("  Fichier vide (toutes positions fermées) — OK")

# ── Cleanup ───────────────────────────────────────────────────────────────────
for f in [TEST_LOG, TEST_STATE, TEST_OPT]:
    f.unlink(missing_ok=True)
shutil.rmtree(TEST_VAULT, ignore_errors=True)

tl._LOG_FILE  = Path("logs/trades.jsonl")
tt.LOG_FILE   = Path("logs/trades.jsonl")
tt.STATE_FILE = Path("logs/open_positions.json")
ab.LOG_FILE   = Path("logs/trades.jsonl")

print("\n=== 7/7 PHASES PASSÉES — aucun crash, logs cohérents, aucun bug silencieux ===")
