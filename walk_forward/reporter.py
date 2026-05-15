"""
walk_forward/reporter.py — Integration des resultats walk-forward dans le reporting Project OS.

Pipeline :
  WalkForwardResult
      |
      +--> save_state()       --> project_os/walk_forward_state.json   (lu par project_os/reporter.py)
      |
      +--> export_jsonl()     --> reports/wf_YYYY-MM-DD_folds.jsonl    (audit fold par fold)
      |
      +--> build_markdown()   --> rapports autonomes dans reports/

Integration avec project_os/reporter.py :
  Le reporter principal charge walk_forward_state.json via _load("walk_forward_state.json").
  build_alerts(state)  -> list[dict] au format {"level": "CRITICAL|WARNING", "msg": str}
  build_section(state) -> list[str] markdown compatible avec les autres sections

Usage :
    from walk_forward.reporter import WalkForwardReporter
    reporter = WalkForwardReporter()
    reporter.save_state(result)         # ecrit project_os/walk_forward_state.json
    reporter.export_jsonl(result)       # ecrit reports/wf_YYYY-MM-DD_folds.jsonl
    reporter.write_markdown(result)     # ecrit reports/YYYY-MM-DD_walk_forward.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from walk_forward.engine import WalkForwardResult

ROOT = Path(__file__).parent.parent
PROJECT_OS = ROOT / "project_os"
REPORTS = ROOT / "reports"


class WalkForwardReporter:
    """
    Exporte un WalkForwardResult vers les differents formats du reporting Project OS.

    project_os_dir : dossier ou ecrire walk_forward_state.json (par defaut project_os/)
    reports_dir    : dossier ou ecrire les rapports Markdown et JSONL
    """

    def __init__(
        self,
        project_os_dir: Optional[Path] = None,
        reports_dir: Optional[Path] = None,
    ) -> None:
        self.project_os_dir = project_os_dir or PROJECT_OS
        self.reports_dir = reports_dir or REPORTS

    # ------------------------------------------------------------------
    # Serialisation du state
    # ------------------------------------------------------------------

    def _to_state(self, result: WalkForwardResult) -> dict[str, Any]:
        """Convertit un WalkForwardResult en dict JSON-serialisable."""
        d = result.as_dict()
        d["generated_at"] = datetime.now().isoformat()
        # Ajouter le resume des evenements de degradation
        d["degradation_events"] = [e.as_dict() for e in result.degradation_events]
        # Resume par fold (leger — sans les trades bruts)
        d["fold_summaries"] = [
            {
                "fold_index": f.fold.fold_index,
                "train_size": f.fold.train_size,
                "test_size": f.fold.test_size,
                "gap": f.fold.gap_size,
                "oos_sharpe": round(f.oos_metrics.sharpe_ratio, 4),
                "oos_win_rate": round(f.oos_metrics.win_rate, 4),
                "oos_max_dd": round(f.oos_metrics.max_drawdown_pct, 4),
                "oos_profit_factor": (
                    round(f.oos_metrics.profit_factor, 4)
                    if f.oos_metrics.profit_factor != float("inf")
                    else None
                ),
                "oos_n_trades": f.oos_metrics.n_trades,
                "is_profitable": f.oos_metrics.is_profitable,
                "overfitting_ratio": (
                    round(f.overfitting_ratio, 4)
                    if f.overfitting_ratio is not None
                    else None
                ),
                "error": f.error,
            }
            for f in result.folds
        ]
        return d

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------

    def save_state(self, result: WalkForwardResult) -> Path:
        """
        Ecrit project_os/walk_forward_state.json.
        Ce fichier est automatiquement charge par project_os/reporter.py.
        """
        self.project_os_dir.mkdir(parents=True, exist_ok=True)
        path = self.project_os_dir / "walk_forward_state.json"
        state = self._to_state(result)
        path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    def export_jsonl(self, result: WalkForwardResult, tag: str = "") -> Path:
        """
        Ecrit un JSONL avec une ligne par fold (audit complet).
        Nom : reports/wf_YYYY-MM-DD[_tag]_folds.jsonl
        """
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        suffix = f"_{tag}" if tag else ""
        path = self.reports_dir / f"wf_{date_str}{suffix}_folds.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for fold in result.folds:
                f.write(json.dumps(fold.as_dict(), ensure_ascii=False) + "\n")
        return path

    def write_markdown(self, result: WalkForwardResult, tag: str = "") -> Path:
        """
        Ecrit un rapport Markdown autonome dans reports/.
        Nom : reports/YYYY-MM-DD_walk_forward[_tag].md
        """
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        suffix = f"_{tag}" if tag else ""
        path = self.reports_dir / f"{date_str}_walk_forward{suffix}.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        state = self._to_state(result)
        lines = [f"# Walk-Forward Report — {ts}", ""]
        lines += build_section(state)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


# ------------------------------------------------------------------
# Fonctions standalone (compatibles project_os/reporter.py)
# ------------------------------------------------------------------


def build_alerts(state: dict) -> list[dict[str, str]]:
    """
    Retourne des alertes au format {"level": "CRITICAL|WARNING", "msg": str}.
    Compatible avec _collect_alerts() dans project_os/reporter.py.
    """
    alerts: list[dict[str, str]] = []

    if not state:
        return alerts

    # Evenements critiques de degradation
    for ev in state.get("degradation_events", []):
        level = "CRITICAL" if ev["severity"] == "critical" else "WARNING"
        alerts.append(
            {"level": level, "msg": f"Walk-forward {ev['metric']}: {ev['message']}"}
        )

    # is_robust = False sans evenements -> alerte generique
    if not state.get("is_robust", True) and not state.get("degradation_events"):
        alerts.append(
            {
                "level": "WARNING",
                "msg": (
                    f"Walk-forward non robuste : "
                    f"Sharpe OOS={state.get('aggregate', {}).get('sharpe_ratio', '?'):.2f}, "
                    f"{state.get('n_profitable_folds', 0)}/{state.get('n_folds', 0)} folds profitables"
                ),
            }
        )

    # Degradation critique globale
    if state.get("n_degradation_criticals", 0) > 0:
        alerts.append(
            {
                "level": "CRITICAL",
                "msg": (
                    f"Walk-forward : {state['n_degradation_criticals']} alerte(s) critique(s) "
                    "de degradation — envisager de stopper ou recalibrer la strategie"
                ),
            }
        )

    return alerts


def build_section(state: dict) -> list[str]:
    """
    Construit la section Markdown walk-forward pour project_os/reporter.py.
    Retourne une list[str] dans le meme style que les autres sections du reporter.
    """
    if not state:
        return [
            "## Walk-Forward",
            "",
            "_Aucune donnee — lancer un run walk-forward._",
            "",
        ]

    agg = state.get("aggregate", {})
    stab = state.get("stability", {})
    ts = state.get("generated_at", "?")[:16].replace("T", " ")

    robust_icon = "OK" if state.get("is_robust") else "NON"
    stable_icon = "OK" if stab.get("is_regime_stable") else "NON"

    lines = [
        "## Walk-Forward",
        "",
        f"_Genere le {ts}_",
        "",
        "### Synthese",
        "",
        f"| Metrique | Valeur |",
        f"|----------|--------|",
        f"| Folds | {state.get('n_folds', '?')} |",
        f"| Folds profitables | {state.get('n_profitable_folds', '?')} / {state.get('n_folds', '?')} ({state.get('profitable_fold_rate', 0):.0%}) |",
        f"| Sharpe OOS moyen | {state.get('mean_oos_sharpe', 0):.3f} ± {state.get('std_oos_sharpe', 0):.3f} |",
        f"| Sharpe OOS agrege | {agg.get('sharpe_ratio', 0):.3f} |",
        f"| Drawdown max OOS | {agg.get('max_drawdown_pct', 0):.2f}% |",
        f"| Win rate OOS | {agg.get('win_rate', 0):.1%} |",
        f"| Profit factor | {agg.get('profit_factor') or 'inf'} |",
        f"| Stabilite inter-regimes | {stab.get('stability_score', 0):.3f} ({stable_icon}) |",
        f"| **Robustesse globale** | **{robust_icon}** |",
        "",
    ]

    # Alertes de degradation
    events = state.get("degradation_events", [])
    if events:
        lines += ["### Alertes degradation", ""]
        for ev in events:
            icon = "[CRIT]" if ev["severity"] == "critical" else "[WARN]"
            lines.append(f"- {icon} {ev['message']}")
        lines.append("")

    # Resume par fold
    folds = state.get("fold_summaries", [])
    if folds:
        lines += [
            "### Detail par fold",
            "",
            "| Fold | Train | Test | Sharpe OOS | WR | DD | PF | Profitable | Overfitting |",
            "|------|------:|-----:|:----------:|:--:|:--:|:--:|:----------:|:-----------:|",
        ]
        for f in folds:
            pf_val = f.get("oos_profit_factor")
            pf_str = f"{pf_val:.2f}" if pf_val is not None else "inf"
            ov = f.get("overfitting_ratio")
            ov_str = f"{ov:.2f}" if ov is not None else "—"
            ok = "OK" if f.get("is_profitable") else "—"
            err = f" [ERR]" if f.get("error") else ""
            lines.append(
                f"| {f['fold_index']}{err}"
                f" | {f['train_size']}"
                f" | {f['test_size']}"
                f" | {f['oos_sharpe']:.3f}"
                f" | {f['oos_win_rate']:.1%}"
                f" | {f['oos_max_dd']:.1f}%"
                f" | {pf_str}"
                f" | {ok}"
                f" | {ov_str} |"
            )
        lines.append("")

    # Stabilite regimes
    worst = stab.get("worst_regime")
    best = stab.get("best_regime")
    if worst and best:
        lines += [
            "### Stabilite inter-regimes",
            "",
            f"| | Valeur |",
            f"|--|--------|",
            f"| Score | {stab.get('stability_score', 0):.3f} |",
            f"| CV Sharpe | {stab.get('sharpe_cv', 0):.3f} |",
            f"| Meilleur regime | {best} (Sharpe {stab.get('max_regime_sharpe', 0):.3f}) |",
            f"| Pire regime | {worst} (Sharpe {stab.get('min_regime_sharpe', 0):.3f}) |",
            "",
        ]

    return lines
