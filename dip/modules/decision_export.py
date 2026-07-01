"""
dip/modules/decision_export.py — D13 Export Engine.

Génère des rapports exportables depuis les données DIP.
Formats: JSON, CSV, Markdown (texte structuré).
PDF et LaTeX: structure produite, rendu délégué à l'opérateur.

Tous les exports sont read-only. Aucun effet sur le moteur de trading.
"""

from __future__ import annotations

import csv
import io
import json
import threading
from dataclasses import dataclass
from typing import Optional

from dip.core.store import DIPStore
from dip.core.types import TimeRange, now_us
from dip.modules.causal_tree import get_causal_tree_engine
from dip.modules.decision_graph import get_graph_engine

# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExportOptions:
    include_graphs: bool = True
    include_causal_trees: bool = True
    include_heatmaps: bool = False
    include_sankey: bool = False
    include_counterfactuals: bool = False
    include_alerts: bool = True
    max_decisions: int = 1000
    time_range_hours: int = 168


@dataclass(frozen=True)
class ExportResult:
    export_id: str
    format: str
    filename: str
    content: str
    size_bytes: int
    decision_count: int
    created_at_us: int


@dataclass(frozen=True)
class ReportSection:
    title: str
    content: str


@dataclass(frozen=True)
class DIPReport:
    report_id: str
    title: str
    time_range: TimeRange
    sections: tuple[ReportSection, ...]
    created_at_us: int
    decision_count: int
    approval_rate: float
    top_rejection_layer: str


# ── Formatters ────────────────────────────────────────────────────────────────


class JSONExporter:

    @staticmethod
    def export(rows: list[dict], options: ExportOptions) -> str:
        data = {
            "exported_at": now_us(),
            "decision_count": len(rows),
            "decisions": rows,
        }
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)


class CSVExporter:

    _COLUMNS = [
        "packet_id",
        "symbol",
        "direction",
        "regime",
        "status",
        "root_cause_layer",
        "explainability_score",
        "explainability_grade",
        "created_at_us",
    ]

    @staticmethod
    def export(rows: list[dict]) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf, fieldnames=CSVExporter._COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in CSVExporter._COLUMNS})
        return buf.getvalue()


class MarkdownExporter:

    @staticmethod
    def export(report: DIPReport) -> str:
        lines = [
            f"# {report.title}",
            f"",
            f"**Généré le:** {_fmt_ts(report.created_at_us)}",
            f"**Décisions analysées:** {report.decision_count}",
            f"**Taux d'approbation:** {report.approval_rate:.1%}",
            f"**Principale couche bloquante:** {report.top_rejection_layer}",
            f"",
        ]
        for section in report.sections:
            lines.append(f"## {section.title}")
            lines.append(section.content)
            lines.append("")
        return "\n".join(lines)


def _fmt_ts(us: int) -> str:
    import datetime

    dt = datetime.datetime.fromtimestamp(us / 1_000_000, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ── Report Builder ─────────────────────────────────────────────────────────────


class ReportBuilder:

    def __init__(self, store: DIPStore) -> None:
        self._store = store

    def build(self, time_range: TimeRange, options: ExportOptions) -> DIPReport:
        rows = self._store.get_decisions(
            start_us=time_range.start_us,
            end_us=time_range.end_us,
            limit=options.max_decisions,
        )
        total = len(rows)
        approved = sum(1 for r in rows if r.get("status") == "APPROVED")
        approval_rate = approved / total if total > 0 else 0.0

        # Top rejection layer
        layers: dict[str, int] = {}
        for r in rows:
            lyr = r.get("root_cause_layer")
            if lyr:
                layers[lyr] = layers.get(lyr, 0) + 1
        top_layer = max(layers.items(), key=lambda x: x[1])[0] if layers else "N/A"

        sections = [
            self._section_summary(rows, approved, approval_rate, top_layer),
            self._section_by_status(rows),
            self._section_by_layer(layers),
            self._section_by_regime(rows),
        ]

        if options.include_alerts:
            active_alerts = self._store.get_active_alerts()
            sections.append(self._section_alerts(active_alerts))

        return DIPReport(
            report_id=f"report_{now_us()}",
            title=f"Rapport DIP — {_fmt_ts(time_range.start_us)} → {_fmt_ts(time_range.end_us)}",
            time_range=time_range,
            sections=tuple(sections),
            created_at_us=now_us(),
            decision_count=total,
            approval_rate=round(approval_rate, 4),
            top_rejection_layer=top_layer,
        )

    def _section_summary(
        self, rows: list[dict], approved: int, rate: float, top_layer: str
    ) -> ReportSection:
        total = len(rows)
        rejected = total - approved
        lines = [
            f"- Total décisions: **{total}**",
            f"- Approuvées: **{approved}** ({rate:.1%})",
            f"- Rejetées: **{rejected}** ({1-rate:.1%})",
            f"- Principale couche bloquante: **{top_layer}**",
        ]
        return ReportSection("Résumé exécutif", "\n".join(lines))

    def _section_by_status(self, rows: list[dict]) -> ReportSection:
        statuses: dict[str, int] = {}
        for r in rows:
            s = r.get("status", "?")
            statuses[s] = statuses.get(s, 0) + 1
        lines = [f"- {s}: {c}" for s, c in sorted(statuses.items())]
        return ReportSection("Distribution par statut", "\n".join(lines))

    def _section_by_layer(self, layers: dict[str, int]) -> ReportSection:
        sorted_layers = sorted(layers.items(), key=lambda x: x[1], reverse=True)
        lines = [f"- {lyr}: {c} rejets" for lyr, c in sorted_layers]
        return ReportSection(
            "Rejets par couche", "\n".join(lines) if lines else "Aucun rejet enregistré"
        )

    def _section_by_regime(self, rows: list[dict]) -> ReportSection:
        regimes: dict[str, dict] = {}
        for r in rows:
            rg = r.get("regime", "?")
            if rg not in regimes:
                regimes[rg] = {"total": 0, "rejected": 0}
            regimes[rg]["total"] += 1
            if r.get("status") == "REJECTED":
                regimes[rg]["rejected"] += 1
        lines = []
        for rg, data in sorted(regimes.items()):
            rate = data["rejected"] / data["total"]
            lines.append(f"- {rg}: {data['total']} décisions, {rate:.0%} rejet")
        return ReportSection(
            "Performance par régime", "\n".join(lines) if lines else "Aucune donnée"
        )

    def _section_alerts(self, alerts: list[dict]) -> ReportSection:
        if not alerts:
            return ReportSection("Alertes actives", "Aucune alerte active.")
        lines = [
            f"- [{a.get('severity','?')}] {a.get('title','?')}: {a.get('description','')}"
            for a in alerts[:20]
        ]
        return ReportSection("Alertes actives", "\n".join(lines))


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionExportEngine:
    """D13 — Moteur d'export et de génération de rapports."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._report_builder = ReportBuilder(self._store)

    def export_json(
        self, hours: int = 168, options: Optional[ExportOptions] = None
    ) -> ExportResult:
        opts = options or ExportOptions(time_range_hours=hours)
        tr = TimeRange.last_hours(hours)
        rows = self._store.get_decisions(start_us=tr.start_us, limit=opts.max_decisions)
        content = JSONExporter.export(rows, opts)
        return ExportResult(
            export_id=f"exp_json_{now_us()}",
            format="json",
            filename=f"dip_export_{now_us()}.json",
            content=content,
            size_bytes=len(content.encode("utf-8")),
            decision_count=len(rows),
            created_at_us=now_us(),
        )

    def export_csv(self, hours: int = 168, max_rows: int = 10_000) -> ExportResult:
        tr = TimeRange.last_hours(hours)
        rows = self._store.get_decisions(start_us=tr.start_us, limit=max_rows)
        content = CSVExporter.export(rows)
        return ExportResult(
            export_id=f"exp_csv_{now_us()}",
            format="csv",
            filename=f"dip_export_{now_us()}.csv",
            content=content,
            size_bytes=len(content.encode("utf-8")),
            decision_count=len(rows),
            created_at_us=now_us(),
        )

    def export_markdown(
        self, hours: int = 168, options: Optional[ExportOptions] = None
    ) -> ExportResult:
        opts = options or ExportOptions(time_range_hours=hours)
        tr = TimeRange.last_hours(hours)
        report = self._report_builder.build(tr, opts)
        content = MarkdownExporter.export(report)
        return ExportResult(
            export_id=f"exp_md_{now_us()}",
            format="markdown",
            filename=f"dip_report_{now_us()}.md",
            content=content,
            size_bytes=len(content.encode("utf-8")),
            decision_count=report.decision_count,
            created_at_us=now_us(),
        )

    def generate_report(
        self, hours: int = 168, options: Optional[ExportOptions] = None
    ) -> DIPReport:
        opts = options or ExportOptions(time_range_hours=hours)
        tr = TimeRange.last_hours(hours)
        return self._report_builder.build(tr, opts)

    def export_packet(self, packet_id: str) -> ExportResult:
        """Export complet d'une seule décision avec tout le contexte DIP."""
        row = self._store.get_decision(packet_id)
        if not row:
            return ExportResult(
                export_id=f"exp_empty_{now_us()}",
                format="json",
                filename=f"dip_{packet_id}.json",
                content=json.dumps({"error": "not found"}),
                size_bytes=20,
                decision_count=0,
                created_at_us=now_us(),
            )

        graph_engine = get_graph_engine()
        causal_engine = get_causal_tree_engine()

        graph = graph_engine.get_graph(packet_id)
        causal = causal_engine.build_causal_tree(packet_id)
        audit = self._store.get_audit_trail(packet_id)
        cfs = self._store.get_counterfactuals(packet_id)

        data = {
            "packet_id": packet_id,
            "decision": row,
            "graph": json.loads(row.get("graph_json") or "{}"),
            "causal_tree": {
                "root_cause_type": (
                    causal.root_cause.cause_type.value if causal else None
                ),
                "root_cause_layer": (
                    causal.root_cause.causal_node.layer if causal else None
                ),
                "description": causal.description if causal else None,
            },
            "audit_trail": audit,
            "counterfactuals": cfs,
        }
        content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        return ExportResult(
            export_id=f"exp_packet_{packet_id[:8]}_{now_us()}",
            format="json",
            filename=f"dip_packet_{packet_id[:8]}.json",
            content=content,
            size_bytes=len(content.encode("utf-8")),
            decision_count=1,
            created_at_us=now_us(),
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionExportEngine] = None
_engine_lock = threading.Lock()


def get_export_engine() -> DecisionExportEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionExportEngine()
    return _engine
