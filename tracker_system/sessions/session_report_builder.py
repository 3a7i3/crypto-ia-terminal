from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracker_system.sessions.session_analyzer import SessionAnalyzer
from tracker_system.sessions.session_manager import SESSIONS_ROOT, load_session_trades
from tracker_system.sessions.session_ranking import register_session
from tracker_system.sessions.session_scoring import SessionScoring
from tracker_system.sessions.session_validator import SessionValidator


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


class SessionReportBuilder:
    """Génère tous les artefacts d'une session clôturée."""

    def build(self, session_dir: Path) -> Path:
        trades = load_session_trades(session_dir)
        analysis = SessionAnalyzer().analyze(trades)
        validation = SessionValidator().validate_session(session_dir)
        scoring = SessionScoring().score(analysis, trades)

        # Écriture des artefacts JSON
        _write_json(session_dir / "metrics.json", analysis)
        _write_json(
            session_dir / "drift_report.json",
            {"events": analysis.get("drift_events", [])},
        )
        _write_json(
            session_dir / "regime_analysis.json", analysis.get("regime_matrix", {})
        )
        _write_json(session_dir / "anomaly_report.json", validation.to_dict())
        _write_json(
            session_dir / "execution_stats.json",
            {
                "trades": analysis.get("summary", {}).get("trades", 0),
                "pnl_total_usd": analysis.get("summary", {}).get("pnl_total_usd", 0.0),
                "profit_factor": analysis.get("profit_factor", 0.0),
                "trade_quality_score": analysis.get("trade_quality_score", 0.0),
            },
        )
        _write_json(session_dir / "scoring.json", scoring)

        # Enregistrement dans le leaderboard
        register_session(session_dir)

        # Rapport Markdown
        report_path = session_dir / "final_report.md"
        report_path.write_text(
            self._build_markdown(session_dir, analysis, validation, scoring),
            encoding="utf-8",
        )
        return report_path

    def _build_markdown(
        self,
        session_dir: Path,
        analysis: dict,
        validation: Any,
        scoring: dict | None = None,
    ) -> str:
        summary = analysis.get("summary", {})
        exp = analysis.get("expectancy", {})
        payoff = analysis.get("payoff_ratio", {})
        streaks = analysis.get("streaks", {})
        stability = analysis.get("signal_stability", {})
        regime_matrix = analysis.get("regime_matrix", {})
        drift_events = analysis.get("drift_events", [])

        best_regime = max(
            regime_matrix,
            key=lambda r: regime_matrix[r].get("expectancy", -999),
            default="N/A",
        )
        worst_regime = min(
            regime_matrix,
            key=lambda r: regime_matrix[r].get("expectancy", 999),
            default="N/A",
        )

        health = "BON" if validation.valid and not drift_events else "DÉGRADÉ"
        health_detail = (
            "Aucune dérive critique détectée."
            if not drift_events
            else f"{len(drift_events)} événement(s) de dérive détecté(s)."
        )

        lines = [
            f"# RAPPORT SESSION — {session_dir.name}",
            f"_Généré le {datetime.now(timezone.utc).isoformat()}_",
            "",
            "## RÉSUMÉ",
            "```",
            f"Trades          : {summary.get('trades', 0)}",
            f"Winrate         : {summary.get('winrate', 0):.1%}",
            f"Profit Factor   : {analysis.get('profit_factor', 0):.2f}",
            f"Expectancy      : {exp.get('value', 0):.4f}  [{exp.get('label', '')}]",
            f"Payoff Ratio    : {payoff.get('value', 0):.2f}  (cible >= {payoff.get('target', 1.5)})",
            f"Recovery Factor : {analysis.get('recovery_factor', 0)}",
            f"PnL Total       : {summary.get('pnl_total_usd', 0):.2f} USD",
            "```",
            "",
            "## SÉRIES",
            "```",
            f"Max win streak  : {streaks.get('max_win_streak', 0)}",
            f"Max loss streak : {streaks.get('max_loss_streak', 0)}",
            f"Avg win streak  : {streaks.get('avg_win_streak', 0):.1f}",
            f"Avg loss streak : {streaks.get('avg_loss_streak', 0):.1f}",
            "```",
            "",
            "## STABILITÉ SIGNAL",
            "```",
            f"Stability Index : {stability.get('index', 0):.4f}  [{stability.get('label', '')}]",
            "```",
            "",
            "## PERFORMANCE PAR RÉGIME",
        ]

        if regime_matrix:
            lines.append("```")
            for regime, stats in regime_matrix.items():
                lines.append(
                    f"{regime:20s} | trades={stats.get('trades', 0):3d} "
                    f"| WR={stats.get('winrate', 0):.0%} "
                    f"| PF={stats.get('profit_factor', 0)} "
                    f"| E={stats.get('expectancy', 0):.3f} "
                    f"| {stats.get('recommendation', '')}"
                )
            lines.append("```")
        else:
            lines.append("_Aucune donnée de régime._")

        lines += [
            "",
            f"Meilleur régime : **{best_regime}**",
            f"Pire régime     : **{worst_regime}**",
        ]

        if scoring:
            q = scoring.get("quality_score", 0.0)
            conf = scoring.get("confidence", {})
            cov = scoring.get("regime_coverage", {})
            failures = scoring.get("failure_analysis", {}).get("root_causes", [])
            lines += [
                "",
                "## SCORING SESSION",
                "```",
                f"Quality Score   : {q:.1f} / 100  [{scoring.get('label', '')}]",
                f"Confidence      : {conf.get('value', 0):.0%}  [{conf.get('label', '')}]",
                f"Regime Coverage : {cov.get('value', 0):.0%}  [{cov.get('label', '')}]  "
                f"({cov.get('unique_regimes', 0)}/{cov.get('total_possible', 7)} régimes)",
                "```",
            ]
            if failures:
                lines += ["", "### Causes d'échec détectées"]
                for cause in failures:
                    lines.append(f"- {cause}")

        lines += [
            "",
            "## SANTÉ SYSTÈME",
            "```",
            f"ÉTAT : {health}",
            "",
            health_detail,
        ]

        if not validation.valid:
            lines.append(f"Erreurs validation : {len(validation.errors)}")
            for e in validation.errors[:5]:
                lines.append(f"  - {e}")

        if validation.warnings:
            lines.append(f"Avertissements     : {len(validation.warnings)}")
            for w in validation.warnings[:5]:
                lines.append(f"  - {w}")

        lines.append("```")
        return "\n".join(lines) + "\n"


def build_session_report(session_dir: Path) -> Path:
    return SessionReportBuilder().build(session_dir)
