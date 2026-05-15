#!/usr/bin/env python3
"""
reporter.py  --  Rapport quotidien / hebdomadaire automatique.

Enrichissements v2 :
  - Section ALERTS en tete (cycles critiques, hubs non couverts, dette haute, maturite faible)
  - Fraicheur des donnees (warn si JSON > 24h)
  - Mode --check : sortie CI (exit 0 = OK, exit 1 = alertes critiques)

Consomme :
  - inventory.json       <- scanner.py
  - test_coverage.json   <- test_scanner.py
  - dep_graph.json       <- dep_mapper.py
  - maturity.json        <- maturity.py
  - debt_map.json        <- debt_map.py
  - roadmap_state.json   <- roadmap_state.py

Usage :
  python project_os/reporter.py                    # rapport daily (stdout)
  python project_os/reporter.py --weekly           # rapport hebdo
  python project_os/reporter.py --file             # ecrit reports/YYYY-MM-DD_daily.md
  python project_os/reporter.py --json             # sortie JSON structuree
  python project_os/reporter.py --check            # mode CI: exit 1 si alertes critiques
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path.cwd()
PROJECT_OS = ROOT / "project_os"
REPORTS = ROOT / "reports"

# Seuils d'alerte
ALERT_MATURITY_MIN = 2.0  # sous ce score global -> alerte
ALERT_DEBT_SCORE_MAX = 100  # au-dessus -> alerte
ALERT_COVERAGE_MIN = 25.0  # sous ce % -> alerte
ALERT_JSON_STALE_H = 24  # JSON plus vieux que N heures -> warning


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load(name: str) -> Optional[Any]:
    path = PROJECT_OS / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _file_age_hours(name: str) -> Optional[float]:
    path = PROJECT_OS / name
    if not path.exists():
        return None
    age_sec = time.time() - path.stat().st_mtime
    return round(age_sec / 3600, 1)


def _freshness_warnings() -> list[str]:
    warnings = []
    for fname in [
        "inventory.json",
        "test_coverage.json",
        "dep_graph.json",
        "maturity.json",
        "debt_map.json",
    ]:
        age = _file_age_hours(fname)
        if age is None:
            warnings.append(f"MISSING: {fname} — run the corresponding scanner")
        elif age > ALERT_JSON_STALE_H:
            warnings.append(f"STALE ({age}h): {fname} — re-run to refresh")
    return warnings


# ---------------------------------------------------------------------------
# Alert detection
# ---------------------------------------------------------------------------


def _collect_alerts(
    dep_graph: Optional[dict],
    coverage: Optional[dict],
    maturity: Optional[dict],
    debt: Optional[dict],
    state: Optional[dict],
) -> list[dict[str, str]]:
    """Return list of {level: CRITICAL|WARNING, msg: str}."""
    alerts: list[dict[str, str]] = []

    # Cycles critiques
    if dep_graph:
        cycles = dep_graph.get("cycles", [])
        critical_cycles = [c for c in cycles if c.get("severity") == "CRITICAL"]
        if critical_cycles:
            for c in critical_cycles:
                alerts.append(
                    {
                        "level": "CRITICAL",
                        "msg": f"Cycle critique: {' -> '.join(c['members'])}",
                    }
                )
        elif cycles:
            for c in cycles:
                alerts.append(
                    {
                        "level": "WARNING",
                        "msg": f"Cycle: {' -> '.join(c['members'])}",
                    }
                )

    # Hubs non couverts
    if coverage:
        uncovered_hubs = coverage.get("uncovered_hubs", [])
        if uncovered_hubs:
            top = uncovered_hubs[0]
            alerts.append(
                {
                    "level": "WARNING",
                    "msg": (
                        f"Hub critique sans tests: {top['path']}"
                        f" ({top['dependants']} dependants) — {len(uncovered_hubs)} total"
                    ),
                }
            )

    # Maturite globale
    if maturity:
        overall = maturity.get("summary", {}).get("overall", 5.0)
        if overall < ALERT_MATURITY_MIN:
            alerts.append(
                {
                    "level": "CRITICAL",
                    "msg": f"Maturite globale trop faible: {overall}/5 (seuil: {ALERT_MATURITY_MIN})",
                }
            )

    # Dette technique
    if debt:
        score = debt.get("summary", {}).get("total_score", 0)
        high_sev = debt.get("summary", {}).get("high_severity", 0)
        if score > ALERT_DEBT_SCORE_MAX:
            alerts.append(
                {
                    "level": "WARNING",
                    "msg": f"Score dette eleve: {score} (seuil: {ALERT_DEBT_SCORE_MAX}) — {high_sev} haute severite",
                }
            )

    # Couverture tests
    if coverage:
        pct = coverage.get("summary", {}).get("coverage_pct", 100.0)
        if pct < ALERT_COVERAGE_MIN:
            alerts.append(
                {
                    "level": "WARNING",
                    "msg": f"Couverture tests faible: {pct}% (seuil: {ALERT_COVERAGE_MIN}%)",
                }
            )

    # Bloqueurs roadmap actifs
    if state:
        active_blockers = [
            b for b in state.get("blockers", []) if not b.get("resolved")
        ]
        if active_blockers:
            alerts.append(
                {
                    "level": "CRITICAL",
                    "msg": f"{len(active_blockers)} bloqueur(s) actif(s): {active_blockers[0]['reason']}",
                }
            )

    return alerts


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_alerts(alerts: list[dict], freshness_warns: list[str]) -> list[str]:
    if not alerts and not freshness_warns:
        return ["## Alerts", "", "Aucune alerte. Tout est OK.", ""]

    lines = ["## Alerts", ""]
    critical = [a for a in alerts if a["level"] == "CRITICAL"]
    warnings = [a for a in alerts if a["level"] == "WARNING"]

    if critical:
        lines.append(f"**CRITICAL ({len(critical)}) :**")
        for a in critical:
            lines.append(f"- [CRIT] {a['msg']}")
        lines.append("")
    if warnings:
        lines.append(f"**WARNING ({len(warnings)}) :**")
        for a in warnings:
            lines.append(f"- [WARN] {a['msg']}")
        lines.append("")
    if freshness_warns:
        lines.append("**Fraicheur des donnees :**")
        for w in freshness_warns:
            lines.append(f"- {w}")
        lines.append("")
    return lines


def _section_phase(state: dict) -> list[str]:
    lines = [
        "## Phase",
        "",
        f"**Phase courante :** {state.get('current_phase', '?')}",
        "",
        "| ID | Phase | Statut | Gate |",
        "|----|-------|--------|:----:|",
    ]
    for p in state.get("phases", []):
        gate = "OK" if p.get("gate_met") else "-"
        lines.append(f"| {p['id']} | {p['name']} | {p['status']} | {gate} |")
    actions = state.get("next_actions", [])
    if actions:
        lines += ["", "**Prochaines actions :**", ""]
        for i, a in enumerate(actions[:5], 1):
            lines.append(f"{i}. {a}")
    return lines


def _section_modules(inventory: list) -> list[str]:
    total = len(inventory)
    by_pkg: dict[str, int] = {}
    for r in inventory:
        pkg = r.get("package", "?")
        by_pkg[pkg] = by_pkg.get(pkg, 0) + 1
    lines = [
        "## Modules",
        "",
        f"**Total :** {total} modules dans {len(by_pkg)} packages",
        "",
        "| Package | Modules |",
        "|---------|--------:|",
    ]
    for pkg, cnt in sorted(by_pkg.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"| {pkg} | {cnt} |")
    return lines


def _section_coverage(coverage: dict) -> list[str]:
    s = coverage.get("summary", {})
    total = s.get("total_modules", 0)
    pct = s.get("coverage_pct", 0)
    orphans = s.get("orphan_test_files", 0)
    variants = s.get("total_parametrize_variants", 0)
    lines = [
        "## Test Coverage",
        "",
        f"| Statut | Modules |",
        "|--------|--------:|",
        f"| COVERED (>=5 tests) | {s.get('covered', 0)} |",
        f"| PARTIAL (1-4 tests) | {s.get('partial', 0)} |",
        f"| UNCOVERED | {s.get('uncovered', 0)} |",
        f"| **Coverage** | **{pct}%** |",
        "",
        f"**Tests :** {s.get('total_test_functions', 0)} fonctions (+{variants} variantes parametrize)",
        f"**Orphan test files :** {orphans}",
    ]
    # Top uncovered hubs
    hubs = coverage.get("uncovered_hubs", [])[:5]
    if hubs:
        lines += ["", "**Top hubs non couverts :**", ""]
        for h in hubs:
            lines.append(f"- `{h['path']}` ({h['dependants']} dependants)")
    return lines


def _section_maturity(maturity: dict) -> list[str]:
    domains = maturity.get("domains", [])
    overall = maturity.get("summary", {}).get("overall", "?")
    lines = [
        "## Maturity",
        "",
        f"**Score global :** {overall}/5",
        "",
        "| Domaine | Niveau | Prochain objectif |",
        "|---------|:------:|-------------------|",
    ]
    for d in domains:
        nxt = (d.get("next_goal") or "Atteint")[:50]
        lines.append(f"| {d['domain']} | {d['level']} | {nxt} |")
    return lines


def _section_debt(debt: dict) -> list[str]:
    items = sorted(
        debt.get("debt_items", []),
        key=lambda x: -x.get("priority_score", 0),
    )
    s = debt.get("summary", {})
    lines = [
        "## Technical Debt",
        "",
        f"**Score total :** {s.get('total_score', '?')}  "
        f"| Hautes severite : {s.get('high_severity', '?')}",
        "",
        "| ID | Dette | Score | Statut |",
        "|----|-------|:-----:|--------|",
    ]
    for it in items[:5]:
        lines.append(
            f"| {it['id']} | {it['name'][:40]} | {it.get('priority_score', '?')} | {it['status']} |"
        )
    return lines


def _section_graph(dep_graph: dict) -> list[str]:
    cycles = dep_graph.get("cycles", [])
    hubs = dep_graph.get("hubs", [])
    lazy = dep_graph.get("lazy_cycle_candidates", [])
    meta = dep_graph.get("metadata", {})
    lines = [
        "## Dependency Graph",
        "",
        f"**Fichiers :** {meta.get('total_files', '?')}  "
        f"| **Packages :** {meta.get('total_packages', '?')}",
        "",
    ]
    if cycles:
        lines.append(f"**Cycles ({len(cycles)}) :**")
        for c in cycles:
            tag = "[CRIT]" if c.get("severity") == "CRITICAL" else "[WARN]"
            lines.append(f"- {tag} `{' -> '.join(c['members'])}`")
    else:
        lines.append("**Cycles :** aucun (top-level imports)")
    if lazy:
        lines.append(
            f"\n**Lazy pseudo-cycles ({len(lazy)}) :** non bloquants, par design"
        )
        for lc in lazy:
            lines.append(f"- [lazy] {lc}")
    if hubs:
        lines += [
            "",
            "**Top hubs :**",
            "",
            "| Module | In | Out | Coupling |",
            "|--------|---:|----:|--------:|",
        ]
        for h in hubs[:5]:
            lines.append(
                f"| {h['module']} | {h['dependants']} | {h['dependencies']} | {h['coupling_score']} |"
            )
    return lines


def _section_weekly_gate() -> list[str]:
    return [
        "## Weekly Gate Check — P1",
        "",
        "Criteres de sortie :",
        "",
        "- [ ] 100% modules critiques references (inventory.json)",
        "- [ ] Etat quotidien reproductible (reporter.py --file OK)",
        "- [ ] dep_graph.json : 0 cycles CRITICAL",
        "- [ ] maturity.json : score global > 2.0/5",
        "- [ ] debt_map.json : dettes hautes avec action definie",
        "- [ ] test_coverage.json : coverage > 25%",
        "",
        "> Si tous cochees : `python project_os/roadmap_state.py --advance`",
    ]


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------


def build_report(is_weekly: bool = False) -> tuple[str, list[dict], bool]:
    """Returns (markdown, alerts, has_critical)."""
    state = _load("roadmap_state.json") or {}
    inventory = _load("inventory.json") or []
    coverage = _load("test_coverage.json") or {}
    maturity = _load("maturity.json") or {}
    debt = _load("debt_map.json") or {}
    dep_graph = _load("dep_graph.json") or {}
    wf_state = _load("walk_forward_state.json") or {}

    alerts = _collect_alerts(dep_graph, coverage, maturity, debt, state)
    if wf_state:
        try:
            from walk_forward.reporter import build_alerts as _wf_alerts

            alerts += _wf_alerts(wf_state)
        except ImportError:
            pass
    freshness = _freshness_warnings()
    has_critical = any(a["level"] == "CRITICAL" for a in alerts)

    period = "Weekly" if is_weekly else "Daily"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    sections: list[list[str]] = [
        [f"# {period} Report -- {ts}", ""],
        _section_alerts(alerts, freshness),
    ]
    if state:
        sections.append(_section_phase(state))
    if inventory:
        sections.append(_section_modules(inventory))
    if coverage:
        sections.append(_section_coverage(coverage))
    if maturity:
        sections.append(_section_maturity(maturity))
    if debt:
        sections.append(_section_debt(debt))
    if dep_graph:
        sections.append(_section_graph(dep_graph))
    if wf_state:
        try:
            from walk_forward.reporter import build_section as _wf_section

            sections.append(_wf_section(wf_state))
        except ImportError:
            pass
    if is_weekly:
        sections.append(_section_weekly_gate())

    lines: list[str] = []
    for section in sections:
        lines.extend(section)
        lines.append("")

    return "\n".join(lines), alerts, has_critical


def build_json_report(is_weekly: bool = False) -> dict[str, Any]:
    state = _load("roadmap_state.json") or {}
    coverage = _load("test_coverage.json") or {}
    maturity = _load("maturity.json") or {}
    debt = _load("debt_map.json") or {}
    dep_graph = _load("dep_graph.json") or {}

    alerts = _collect_alerts(dep_graph, coverage, maturity, debt, state)
    freshness = _freshness_warnings()

    return {
        "generated_at": datetime.now().isoformat(),
        "type": "weekly" if is_weekly else "daily",
        "phase": state.get("current_phase"),
        "has_critical": any(a["level"] == "CRITICAL" for a in alerts),
        "alerts": alerts,
        "freshness_warnings": freshness,
        "blockers": [b for b in state.get("blockers", []) if not b.get("resolved")],
        "next_actions": state.get("next_actions", []),
        "coverage_summary": coverage.get("summary", {}),
        "maturity_overall": maturity.get("summary", {}).get("overall"),
        "debt_total_score": debt.get("summary", {}).get("total_score"),
        "cycles": dep_graph.get("cycles", []),
        "top_hubs": dep_graph.get("hubs", [])[:5],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    args = sys.argv[1:]
    is_weekly = "--weekly" in args
    write_file = "--file" in args
    json_out = "--json" in args
    check_mode = "--check" in args

    if json_out:
        report = build_json_report(is_weekly)
        print(json.dumps(report, indent=2))
        if check_mode and report.get("has_critical"):
            sys.exit(1)
        return

    markdown, alerts, has_critical = build_report(is_weekly)

    if check_mode:
        # CI mode: concise output only
        critical = [a for a in alerts if a["level"] == "CRITICAL"]
        warnings = [a for a in alerts if a["level"] == "WARNING"]
        if has_critical:
            print(f"FAIL — {len(critical)} critical alert(s):")
            for a in critical:
                print(f"  [CRIT] {a['msg']}")
            sys.exit(1)
        else:
            print(
                f"OK — 0 critical | {len(warnings)} warning(s)"
                + (f": {warnings[0]['msg']}" if warnings else "")
            )
            sys.exit(0)

    if write_file:
        suffix = "weekly" if is_weekly else "daily"
        fname = f"{datetime.now().strftime('%Y-%m-%d')}_{suffix}.md"
        out_path = REPORTS / fname
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        # Brief stdout summary
        critical = [a for a in alerts if a["level"] == "CRITICAL"]
        warnings = [a for a in alerts if a["level"] == "WARNING"]
        status = "FAIL" if has_critical else "OK"
        print(f"[{status}] {fname}")
        if critical:
            for a in critical:
                print(f"  [CRIT] {a['msg']}")
        if warnings:
            print(f"  {len(warnings)} warning(s)")
        print(f"-> {out_path}")
        return

    print(markdown)


if __name__ == "__main__":
    main()
