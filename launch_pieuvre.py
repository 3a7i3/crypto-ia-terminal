"""
Lanceur CLI de la Pieuvre Géante.

Usage:
    python launch_pieuvre.py                  # boucle continue
    python launch_pieuvre.py --scan-once      # un seul scan, rapport + exit
    python launch_pieuvre.py --auto-fix       # active les corrections automatiques sûres
    python launch_pieuvre.py --dashboard      # affiche le dashboard en temps réel
    python launch_pieuvre.py --report         # affiche le rapport des incidents passés
    python launch_pieuvre.py --path /autre    # spécifie un autre répertoire
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pieuvre.launcher")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="🐙 La Pieuvre Géante — surveillance auto-évolutive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Répertoire racine du projet à surveiller (défaut: .)",
    )
    parser.add_argument(
        "--scan-once",
        action="store_true",
        help="Exécute un seul cycle de scan, affiche le rapport et quitte",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Active les corrections automatiques sûres (bare except → except Exception)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Affiche le dashboard terminal rafraîchi toutes les 5s",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Affiche le rapport des incidents passés et quitte",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Sortie JSON (compatible CI/CD)",
    )
    return parser.parse_args()


def print_report(repo_path: Path, as_json: bool = False) -> None:
    from pieuvre.incidents.store import IncidentStore

    store = IncidentStore(repo_path / "pieuvre" / "incidents" / "history.json")
    incidents = store.all()

    if as_json:
        print(
            json.dumps([i.to_dict() for i in incidents], indent=2, ensure_ascii=False)
        )
        return

    if not incidents:
        print("🐙 Aucun incident enregistré.")
        return

    total_force = store.total_strength_gained()
    resolved = store.resolved()
    pending = store.pending()
    immunities = store.all_immunity_patterns()

    print(f"\n🐙 RAPPORT PIEUVRE — {len(incidents)} incidents total\n")
    print(f"  ✅ Résolus    : {len(resolved)}")
    print(f"  ⏳ En attente : {len(pending)}")
    print(f"  💪 Force gagnée: +{total_force:.3f}x")
    print(f"  🛡️  Immunités  : {len(immunities)} patterns")

    if immunities:
        print(f"\n  Patterns immunisés: {', '.join(sorted(immunities)[:10])}")

    recurring = store.recurring_rules(min_count=2)
    if recurring:
        print(f"\n  🔁 Patterns récurrents:")
        for rule, count in sorted(recurring.items(), key=lambda x: -x[1]):
            print(f"     {rule}: {count}x")

    print(f"\n  Derniers incidents:")
    for inc in sorted(incidents, key=lambda i: i.timestamp, reverse=True)[:5]:
        resolved_str = "✅" if inc.resolved_at else "⏳"
        print(
            f"  {resolved_str} [{inc.severity.value.upper():<8}] {inc.timestamp.strftime('%Y-%m-%d %H:%M')} "
            f"— {inc.message[:60]}"
        )


async def run_scan_once(repo_path: Path, auto_fix: bool, as_json: bool) -> int:
    """Un seul cycle, retourne le code de sortie (0=ok, 1=findings HIGH+)."""
    from pieuvre import PieuvreGigante

    pieuvre = PieuvreGigante(repo_path=str(repo_path), auto_fix=auto_fix)
    all_findings = await pieuvre._run_all_tentacles()

    if as_json:
        print(
            json.dumps(
                [f.to_dict() for f in all_findings],
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not all_findings:
            print("🟢 Aucun finding — tout est sain.")
        else:
            from pieuvre.incidents.models import Severity

            sev_order = {
                Severity.CRITICAL: 0,
                Severity.HIGH: 1,
                Severity.MEDIUM: 2,
                Severity.LOW: 3,
            }
            all_findings.sort(key=lambda f: sev_order.get(f.severity, 9))

            for f in all_findings:
                icon = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🔵",
                }.get(f.severity.value, "⚪")
                print(
                    f"{icon} [{f.severity.value.upper():<8}] {f.file}:{f.line} [{f.rule}] {f.message}"
                )

            high_count = sum(
                1 for f in all_findings if f.severity.value in ("high", "critical")
            )
            print(
                f"\n📊 Total: {len(all_findings)} findings dont {high_count} HIGH/CRITICAL"
            )

    has_critical = any(f.severity.value in ("high", "critical") for f in all_findings)
    return 1 if has_critical else 0


async def run_continuous(repo_path: Path, auto_fix: bool, with_dashboard: bool) -> None:
    from pieuvre import PieuvreGigante
    from pieuvre.dashboard import TableauDeBord

    pieuvre = PieuvreGigante(repo_path=str(repo_path), auto_fix=auto_fix)

    tasks = [asyncio.create_task(pieuvre.run(), name="pieuvre_brain")]

    if with_dashboard:
        board = TableauDeBord(pieuvre)
        tasks.append(
            asyncio.create_task(board.run_loop(refresh_seconds=5.0), name="dashboard")
        )

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\n🐙 Pieuvre arrêtée par l'utilisateur.")
        for task in tasks:
            task.cancel()


def main() -> None:
    args = parse_args()
    repo_path = Path(args.path).resolve()

    if not repo_path.exists():
        print(f"❌ Répertoire introuvable: {repo_path}")
        sys.exit(2)

    if args.report:
        print_report(repo_path, as_json=args.json)
        sys.exit(0)

    if args.scan_once:
        code = asyncio.run(run_scan_once(repo_path, args.auto_fix, args.json))
        sys.exit(code)

    # Mode continu
    asyncio.run(run_continuous(repo_path, args.auto_fix, args.dashboard))


if __name__ == "__main__":
    main()
