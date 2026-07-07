"""
reports/live_observer_report.py -- Observer certification report generator.

Generates a complete report from the live observer validation suite.
Usable as a module or standalone script.

Usage:
  python reports/live_observer_report.py
  python reports/live_observer_report.py --live
  python reports/live_observer_report.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.live_observer_validator import (  # noqa: E402,F401
    LiveCheckResult,
    certify,
    load_history,
    run_suite,
    save_history,
)

# ── Core report builder ────────────────────────────────────────────────────────


def generate_report(live_mode: bool = False) -> dict[str, Any]:
    """Run the full IV-LIVE suite and return a structured report dict."""
    results = run_suite(live_mode=live_mode)
    cert = certify(results, iv_all_pass=True, live_mode=live_mode)
    save_history(results, cert)
    history = load_history()

    return {
        "meta": {
            "report_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "live_mode": live_mode,
            "reference": "docs/dip/observer_certification_standard_v1.md",
        },
        "certification": cert,
        "checks": [
            {
                "check_id": r.check_id,
                "name": r.name,
                "status": r.status,
                "score": r.score,
                "duration_ms": r.duration_ms,
                "details": r.details,
                "metrics": r.metrics,
                "error": r.error,
                "skip_reason": r.skip_reason,
            }
            for r in results
        ],
        "history_summary": {
            "total_runs": len(history),
            "last_run": history[-1]["generated_at"] if history else None,
            "last_level": history[-1]["level"] if history else None,
            "level2_runs": sum(1 for h in history if h["level"] >= 2),
            "level3_runs": sum(1 for h in history if h["level"] >= 3),
            "revoked_runs": sum(1 for h in history if h.get("revoked")),
        },
        "scientific_lineage": _build_lineage(cert),
    }


def _build_lineage(cert: dict[str, Any]) -> dict[str, Any]:
    """Summarize what the current certification level enables scientifically."""
    level = cert["level"]
    return {
        "current_level": level,
        "level_name": cert["level_name"],
        "s1_authorized": level >= 3,
        "hypothesis_testing_authorized": level >= 4,
        "calibration_authorized": False,  # requires CRI >= 90 in addition
        "gates_unlocked": _gates_for_level(level),
        "gates_locked": _gates_for_level(3 - min(level, 3)) if level < 3 else [],
        "next_gate": _next_gate(level, cert),
    }


def _gates_for_level(level: int) -> list[str]:
    gates = {
        0: [],
        1: ["IV-001..010 software validation"],
        2: ["IV-LIVE synthetic instrumentation", "FEATURE_DIP activation"],
        3: ["S1 scientific validation", "H1-H6 hypothesis testing"],
        4: ["ACE calibration", "Real trading (Phase 2)"],
    }
    all_gates: list[str] = []
    for lvl in range(1, level + 1):
        all_gates.extend(gates.get(lvl, []))
    return all_gates


def _next_gate(level: int, cert: dict[str, Any]) -> str:
    if level == 0:
        return "IV-001..010 software validation (tools/instrumentation_validator.py)"
    if level == 1:
        return f"III >= 95 (actuel: {cert['iii']:.1f}) + correction checks FAIL"
    if level == 2:
        return (
            f"FEATURE_DIP=true sur VPS + N>={50} decisions + "
            f"OCS >= 90 (actuel: {cert['ocs']:.1f})"
        )
    if level == 3:
        return "DatasetCertifier >= 80 + CRI >= 90 + N >= 500 trades"
    return "Completed"


# ── Text formatter ─────────────────────────────────────────────────────────────


def format_text_report(report: dict[str, Any]) -> str:
    lines = []
    meta = report["meta"]
    cert = report["certification"]
    hist = report["history_summary"]
    lineage = report["scientific_lineage"]

    lines.append("=" * 72)
    lines.append("LIVE OBSERVER CERTIFICATION REPORT")
    lines.append(f"Generated: {meta['generated_at'][:19]} UTC")
    lines.append(f"Mode:      {'PRODUCTION' if meta['live_mode'] else 'SYNTHETIC'}")
    lines.append(f"Reference: {meta['reference']}")
    lines.append("=" * 72)
    lines.append("")

    # Certification
    lines.append("CERTIFICATION")
    lines.append("-" * 40)
    level_icons = {0: "[!!]", 1: "[L1]", 2: "[L2]", 3: "[L3]", 4: "[L4]"}
    icon = level_icons.get(cert["level"], "[??]")
    lines.append(f"  Level:    {icon} {cert['level_name']}")
    lines.append(f"  III:      {cert['iii']:.1f}/100  (seuil Level 2: >=95)")
    lines.append(f"  OCS:      {cert['ocs']:.1f}/100  (seuil Level 3: >=90)")
    lines.append(f"  Decision: {cert['decision']}")
    lines.append("")

    # Sub-scores
    sub = cert["sub_scores"]
    lines.append("INSTRUMENTATION INTEGRITY INDEX (III) SUB-SCORES")
    lines.append("-" * 40)
    for key, val in sub.items():
        if key != "iii":
            name = key.replace("sub_", "").replace("_", " ").capitalize()
            bar = "#" * int(val / 5) + "." * (20 - int(val / 5))
            lines.append(f"  {name:<15} [{bar}] {val:.0f}%")
    lines.append("")

    # Checks
    lines.append("IV-LIVE CHECKS")
    lines.append("-" * 40)
    status_icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}
    for chk in report["checks"]:
        icon = status_icon.get(chk["status"], "[???]")
        score_str = f"  score={chk['score']:.0f}%" if chk["status"] == "FAIL" else ""
        lines.append(
            f"  {icon} {chk['check_id']:<16}  {chk['name']:<36} "
            f"{chk['duration_ms']:>5.0f}ms{score_str}"
        )
        if chk["status"] == "FAIL":
            lines.append(f"           {chk['details']}")
            if chk["error"]:
                lines.append(f"           ERROR: {chk['error']}")
    lines.append("")

    # History summary
    lines.append("CERTIFICATION HISTORY")
    lines.append("-" * 40)
    lines.append(f"  Total runs:   {hist['total_runs']}")
    lines.append(f"  Level 2 runs: {hist['level2_runs']}")
    lines.append(f"  Level 3 runs: {hist['level3_runs']}")
    lines.append(f"  Revoked:      {hist['revoked_runs']}")
    if hist["last_run"]:
        lines.append(
            f"  Last run:     {hist['last_run'][:19]} UTC  (Level {hist['last_level']})"
        )
    lines.append("")

    # Scientific lineage
    lines.append("SCIENTIFIC LINEAGE")
    lines.append("-" * 40)
    lines.append(f"  S1 authorized:      {'YES' if lineage['s1_authorized'] else 'NO'}")
    lines.append(
        "  H1-H6 authorized:   "
        f"{'YES' if lineage['hypothesis_testing_authorized'] else 'NO'}"
    )
    lines.append(
        f"  ACE authorized:     {'YES' if lineage['calibration_authorized'] else 'NO'}"
    )
    lines.append(f"  Next gate:          {lineage['next_gate']}")
    if lineage["gates_unlocked"]:
        lines.append("  Unlocked gates:")
        for gate in lineage["gates_unlocked"]:
            lines.append(f"    + {gate}")
    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Observer Certification Report Generator"
    )
    parser.add_argument("--live", action="store_true", help="Use production DIPStore")
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output JSON"
    )
    args = parser.parse_args()

    report = generate_report(live_mode=args.live)

    if args.json_output:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(format_text_report(report))

    cert_level = report["certification"]["level"]
    return 0 if cert_level >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
