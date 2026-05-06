"""
tracker.py — Générateur de notes Obsidian + dashboard

Lit logs/trades.jsonl et produit :
  - obsidian_vault/03_Trades/<date>_<symbol>.md  (1 note par trade exit)
  - obsidian_vault/06_Dashboard/dashboard.md      (KPIs globaux)

Usage:
    python tracker_system/tracker.py
    python tracker_system/tracker.py --vault /chemin/vers/vault
    python tracker_system/tracker.py --config tracker_system/dashboard_thresholds.json
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


# OBSIDIAN_VAULT_PATH env var overrides the default; --vault CLI arg overrides both.
_vault_env = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
DEFAULT_VAULT = Path(_vault_env) if _vault_env else Path("obsidian_vault")
DEFAULT_CONFIG = Path(__file__).with_name("dashboard_thresholds.json")


DEFAULT_THRESHOLDS = {
    "edge": {
        "min_mfe_for_exit_review_pct": 1.0,
        "poor_efficiency_pct": 50.0,
        "review_efficiency_pct": 65.0,
        "min_expectancy_pct": 0.15,
        "max_drawdown_hard_pct": 4.0,
        "max_drawdown_review_pct": 2.5,
        "min_capture_ratio": 0.75,
    },
    "regime": {
        "range_avoid_avg_pnl_pct": 0.10,
        "strong_regime_avg_pnl_pct": 0.50,
        "strong_regime_winrate_pct": 55.0,
    },
}


REGIME_META = {
    "bull": ("Bull Trend", "[BULL]"),
    "bullish": ("Bull Trend", "[BULL]"),
    "range": ("Range", "[RANGE]"),
    "sideways": ("Range", "[RANGE]"),
    "bear": ("Bear", "[BEAR]"),
    "bearish": ("Bear", "[BEAR]"),
}


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _equity_curve_label(total_pnl: float, max_dd: float) -> str:
    if total_pnl <= 0:
        return "📉 (fragile)"
    if max_dd <= 0.05:
        return "📈 (stable)"
    if max_dd <= 0.10:
        return "📈 (volatile)"
    return "📉 (sous pression)"


def _regime_title(regime: str) -> tuple[str, str]:
    key = str(regime or "unknown").strip().lower()
    return REGIME_META.get(key, (str(regime or "Unknown").title(), "[INFO]"))


def _merge_thresholds(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_thresholds(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_dashboard_thresholds(config_path: Path | None = None) -> dict:
    path = config_path or DEFAULT_CONFIG
    thresholds = _merge_thresholds(DEFAULT_THRESHOLDS, {})
    if not path.exists():
        return thresholds

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[Tracker] Config illisible, fallback par défaut: {path} ({exc})")
        return thresholds

    if not isinstance(raw, dict):
        print(f"[Tracker] Config invalide, fallback par défaut: {path}")
        return thresholds
    return _merge_thresholds(thresholds, raw)


def _edge_diagnostics(
    avg_eff: float,
    avg_mfe: float,
    avg_captured: float,
    expectancy_pct: float,
    max_dd: float,
    thresholds: dict,
) -> tuple[list[str], list[str], list[str]]:
    diagnostics: list[str] = []
    focus: list[str] = []
    lessons: list[str] = []

    edge_cfg = thresholds["edge"]
    min_mfe_for_exit_review = float(edge_cfg["min_mfe_for_exit_review_pct"])
    poor_efficiency = float(edge_cfg["poor_efficiency_pct"])
    review_efficiency = float(edge_cfg["review_efficiency_pct"])
    min_expectancy = float(edge_cfg["min_expectancy_pct"])
    max_drawdown_hard = float(edge_cfg["max_drawdown_hard_pct"]) / 100
    max_drawdown_review = float(edge_cfg["max_drawdown_review_pct"]) / 100
    min_capture_ratio = float(edge_cfg["min_capture_ratio"])

    if avg_mfe >= min_mfe_for_exit_review and avg_eff < poor_efficiency:
        diagnostics.append("- edge mal monétisé: sorties trop tôt pour un standard prop firm")
        focus.append("- laisser courir les winners quand le MFE valide le setup")
        lessons.append("- trailing à tester sur les winners")
    elif avg_mfe >= min_mfe_for_exit_review and avg_eff < review_efficiency:
        diagnostics.append("- capture partielle de l'edge: sorties encore trop prudentes")
        focus.append("- améliorer les exits sur les setups qui respirent")
    elif avg_mfe > 0:
        diagnostics.append("- capture de l'edge propre")

    if expectancy_pct < 0:
        diagnostics.append("- expectancy négative: setup non finançable en environnement prop")
        focus.append("- couper les setups à expectancy négative")
    elif expectancy_pct < min_expectancy:
        diagnostics.append("- expectancy trop fine pour scaler sereinement")
        focus.append("- monter la qualité de sélection avant d'augmenter le risque")
    else:
        lessons.append("- expectancy exploitable si le process reste discipliné")

    if max_dd >= max_drawdown_hard:
        diagnostics.append("- drawdown trop élevé pour un cadre prop strict")
        focus.append("- réduire la variance avant tout scaling")
    elif max_dd >= max_drawdown_review:
        diagnostics.append("- drawdown sous contrôle mais encore trop large pour accélérer")

    if avg_captured > 0 and avg_captured < min_capture_ratio * avg_mfe:
        lessons.append("- TP trop court en tendance")
    if not lessons:
        lessons.append("- SL correct")

    return diagnostics, focus, lessons


def _regime_diagnostics(regime_stats: list[dict], thresholds: dict) -> tuple[list[str], list[str], list[str]]:
    diagnostics: list[str] = []
    focus: list[str] = []
    problems: list[str] = []

    regime_cfg = thresholds["regime"]
    range_avoid_avg_pnl = float(regime_cfg["range_avoid_avg_pnl_pct"])
    strong_regime_avg_pnl = float(regime_cfg["strong_regime_avg_pnl_pct"])
    strong_regime_winrate = float(regime_cfg["strong_regime_winrate_pct"])

    if not regime_stats:
        return diagnostics, focus, problems

    weak_sorted = sorted(regime_stats, key=lambda item: (item["avg_pct"], item["win_rate"]))
    best_sorted = sorted(regime_stats, key=lambda item: (item["avg_pct"], item["win_rate"]), reverse=True)

    weakest = weak_sorted[0]
    strongest = best_sorted[0]

    if weakest["name"] == "Range" and weakest["avg_pct"] <= range_avoid_avg_pnl:
        diagnostics.append("- éviter range faible")
        focus.append("- filtrer range")
        problems.append("- performance faible en range")
    elif weakest["avg_pct"] < 0:
        diagnostics.append(f"- réduire l'exposition en {weakest['name'].lower()}")
        focus.append(f"- ne trader {weakest['name'].lower()} que sur signal premium")
        problems.append(f"- sous-performance en {weakest['name'].lower()}")

    if strongest["avg_pct"] >= strong_regime_avg_pnl and strongest["win_rate"] >= strong_regime_winrate:
        diagnostics.append(f"- concentrer le risque sur {strongest['name'].lower()}")
        focus.append(f"- prioriser {strongest['name'].lower()} quand le marché est lisible")

    if strongest["name"] == weakest["name"] and len(regime_stats) == 1:
        diagnostics.append("- échantillon régime encore trop étroit")

    return diagnostics, focus, problems


# ── Lecture logs ──────────────────────────────────────────────────────────────

def load_exits(log_file: Path = Path("logs/trades.jsonl")) -> list[dict]:
    trades = []
    if not log_file.exists():
        return trades
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line.strip())
                if ev.get("type") == "exit":
                    trades.append(ev)
            except Exception:
                continue
    return trades


# ── Note par trade ────────────────────────────────────────────────────────────

def create_trade_note(trade: dict, vault: Path) -> None:
    ts  = trade.get("timestamp", "unknown")
    sym = trade["symbol"].replace("/", "")
    # Inclut l'heure (HHmm) pour différencier plusieurs trades du même symbole le même jour
    date_str = ts[:10] if len(ts) >= 10 else "unknown"
    time_str = ts[11:16].replace(":", "") if len(ts) >= 16 else "0000"

    note_dir = vault / "03_Trades"
    note_dir.mkdir(parents=True, exist_ok=True)

    base     = f"{date_str}T{time_str}_{sym}"
    filename = f"{base}.md"
    path     = note_dir / filename
    # Si collision (même seconde), ajoute un suffixe incrémental
    idx = 1
    while path.exists():
        filename = f"{base}_{idx}.md"
        path     = note_dir / filename
        idx     += 1

    pnl_usd = trade.get("pnl_usd", 0)
    pnl_pct = trade.get("pnl_pct", 0)
    mfe     = trade.get("mfe", 0)
    mae     = trade.get("mae", 0)
    win     = "WIN" if trade.get("win") else "LOSS"

    efficiency = ""
    if mfe and mfe > 0:
        captured = pnl_pct / mfe * 100 if pnl_pct > 0 else 0
        efficiency = f"{captured:.0f}% du MFE capturé"

    content = f"""# Trade {trade['symbol']} — {date_str} [{win}]

## Setup
- Signal : {trade.get('signal_type', '?')}
- Régime : {trade.get('regime', '?')}
- Direction : {trade.get('direction', '?').upper()}
- Score : {trade.get('score', '?')}
- Confidence : {trade.get('confidence', '?')}

## Entrée
- Prix : {trade.get('entry_price', '?')}
- Taille : ${trade.get('size_usd', '?')}

## Résultat
- PnL : {pnl_usd:+.4f}$ ({pnl_pct*100:+.2f}%)
- Win/Loss : {win}
- Exit : {trade.get('exit_reason', '?')}
- Durée : {trade.get('duration_minutes', '?')} min

## Analyse
- MFE : {mfe*100:+.2f}%
- MAE : {mae*100:+.2f}%
- Efficacité exit : {efficiency}

### Ce qui était correct
-

### Erreurs
-

## Leçon
-

## Action
- Ce que je change :
"""
    path.write_text(content, encoding="utf-8")
    print(f"[Tracker] Note créée : {filename}")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def update_dashboard(trades: list[dict], vault: Path, thresholds: dict | None = None) -> None:
    dash_dir = vault / "06_Dashboard"
    dash_dir.mkdir(parents=True, exist_ok=True)

    if not trades:
        return

    thresholds = thresholds or load_dashboard_thresholds()

    wins   = [t for t in trades if t.get("win")]
    losses = [t for t in trades if not t.get("win")]

    total_pnl  = sum(t.get("pnl_usd", 0) for t in trades)
    total      = len(trades)
    win_rate   = len(wins) / total * 100 if total else 0

    win_pcts = [t.get("pnl_pct", 0) for t in wins]
    loss_pcts = [t.get("pnl_pct", 0) for t in losses]
    avg_win_pct = sum(win_pcts) / len(win_pcts) * 100 if win_pcts else 0
    avg_loss_pct = sum(loss_pcts) / len(loss_pcts) * 100 if loss_pcts else 0
    expectancy_pct = (win_rate / 100 * avg_win_pct) + ((1 - win_rate / 100) * avg_loss_pct)

    # Drawdown simple depuis equity curve
    equity = 0.0
    peak   = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t.get("pnl_usd", 0)
        peak    = max(peak, equity)
        dd      = (peak - equity) / peak if peak > 0 else 0.0
        max_dd  = max(max_dd, dd)

    # MFE/MAE moyens
    mfe_vals = [t["mfe"] for t in trades if "mfe" in t]
    mae_vals = [abs(t["mae"]) for t in trades if "mae" in t]
    avg_mfe  = sum(mfe_vals) / len(mfe_vals) * 100 if mfe_vals else 0
    avg_mae  = sum(mae_vals) / len(mae_vals) * 100 if mae_vals else 0

    captured_vals = [t.get("pnl_pct", 0) * 100 for t in trades if t.get("pnl_pct", 0) > 0]
    avg_captured = sum(captured_vals) / len(captured_vals) if captured_vals else 0

    durations = [t.get("duration_minutes", 0) for t in trades if t.get("duration_minutes") is not None]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Efficacité exit
    effs = []
    for t in trades:
        mfe = t.get("mfe", 0)
        pnl = t.get("pnl_pct", 0)
        if mfe > 0 and pnl > 0:
            effs.append(pnl / mfe * 100)
    avg_eff = sum(effs) / len(effs) if effs else 0

    # Par régime
    by_regime: dict[str, list] = defaultdict(list)
    for t in trades:
        by_regime[t.get("regime", "unknown")].append(t)

    regime_blocks = []
    regime_stats = []
    for regime, regime_trades in sorted(by_regime.items()):
        label, icon = _regime_title(regime)
        regime_wins = [t for t in regime_trades if t.get("win")]
        regime_win_rate = len(regime_wins) / len(regime_trades) * 100 if regime_trades else 0
        regime_avg_pct = sum(t.get("pnl_pct", 0) for t in regime_trades) / len(regime_trades) * 100 if regime_trades else 0
        regime_stats.append({
            "name": label,
            "win_rate": regime_win_rate,
            "avg_pct": regime_avg_pct,
        })
        regime_blocks.append(
            f"### {icon} {label}\n"
            f"- Winrate: {regime_win_rate:.0f}%\n"
            f"- Avg PnL: {_fmt_pct(regime_avg_pct)}"
        )

    edge_diagnostics, edge_focus, edge_lessons = _edge_diagnostics(
        avg_eff=avg_eff,
        avg_mfe=avg_mfe,
        avg_captured=avg_captured,
        expectancy_pct=expectancy_pct,
        max_dd=max_dd,
        thresholds=thresholds,
    )
    regime_diagnostics, regime_focus, regime_problems = _regime_diagnostics(regime_stats, thresholds=thresholds)

    problem_lines = list(dict.fromkeys(edge_diagnostics + regime_problems))
    focus_lines = list(dict.fromkeys(edge_focus + regime_focus))
    lesson_lines = list(dict.fromkeys(edge_lessons))

    if avg_mae <= abs(avg_loss_pct) and losses and "- SL correct" not in lesson_lines:
        lesson_lines.append("- SL correct")

    if not edge_diagnostics:
        edge_diagnostics.append("- edge exploité de façon correcte")
    if not regime_diagnostics:
        regime_diagnostics.append("- aucun régime à exclure pour l'instant")
    if not problem_lines:
        problem_lines.append("- aucun problème critique détecté")
    if not focus_lines:
        focus_lines.append("- maintenir discipline d'execution")
    if not lesson_lines:
        lesson_lines.append("- continuer à accumuler des données")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = f"""# 📊 Trading Dashboard

Mise à jour: {now}

## 📈 Performance Globale
- PnL Total: {total_pnl:+.1f}$
- Equity Curve: {_equity_curve_label(total_pnl, max_dd)}
- Drawdown Max: -{max_dd*100:.1f}%
- Trades: {total}

## 🎯 Qualité du Système
- Winrate: {win_rate:.0f}%
- Expectancy: {_fmt_pct(expectancy_pct)} / trade
- Avg Win: {_fmt_pct(avg_win_pct)}
- Avg Loss: {_fmt_pct(avg_loss_pct)}

## ⚡ Execution
- Slippage moyen: n/d (non loggé)
- Temps moyen trade: {avg_duration:.0f} min

## 🧠 Edge
- MFE moyen: {_fmt_pct(avg_mfe)}
- Profit capturé: {_fmt_pct(avg_captured)}
- Efficiency: {avg_eff:.0f}%

👉 Diagnostic:
{chr(10).join(edge_diagnostics)}

## 📊 Par Régime
{chr(10).join(regime_blocks) if regime_blocks else "- Pas encore de donnees"}

👉 Diagnostic:
{chr(10).join(regime_diagnostics)}

## ⚠️ Problemes Actuels
{chr(10).join(problem_lines)}

## 🎯 Focus Actuel
{chr(10).join(dict.fromkeys(focus_lines))}

## 🧠 Dernières Leçons
{chr(10).join(dict.fromkeys(lesson_lines))}

## 🧩 Architecture
- MVP = execution simple (signal + logging)
- tracker_system = analyse, dashboard, optimisation
- Obsidian = visualisation et mémoire de travail
"""
    (dash_dir / "dashboard.md").write_text(content, encoding="utf-8")
    print(f"[Tracker] Dashboard mis à jour ({total} trades)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Tracker — notes Obsidian + dashboard")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="Chemin vers le vault Obsidian")
    parser.add_argument("--log",   default="logs/trades.jsonl", help="Fichier de trades")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Fichier JSON de seuils dashboard")
    args = parser.parse_args()

    vault    = Path(args.vault)
    log_file = Path(args.log)
    config_file = Path(args.config)
    thresholds = load_dashboard_thresholds(config_file)

    trades = load_exits(log_file)
    print(f"[Tracker] {len(trades)} exits trouvés")

    for t in trades:
        create_trade_note(t, vault)

    update_dashboard(trades, vault, thresholds=thresholds)


if __name__ == "__main__":
    main()
