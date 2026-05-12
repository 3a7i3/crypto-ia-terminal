"""
Tableau de bord terminal de la Pieuvre Géante.

Affiche en temps réel:
  - État de la machine à états (ACTIF / ALERTE / RECOVERY / REGROWTH)
  - Barre de force cumulative
  - Grille des 8 tentacules (actif/pausé, nb findings, nb scans)
  - 10 derniers findings HIGH/CRITICAL
  - Compteurs d'incidents et d'immunités

Utilise rich si disponible, sinon fallback ANSI simple.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pieuvre.brain import PieuvreGigante

_USE_RICH = False
try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _USE_RICH = True
    _console = Console()
except ImportError:
    pass

_STATE_COLORS = {
    "actif": "\033[92m",  # vert
    "alerte": "\033[91m",  # rouge
    "recuperation": "\033[93m",  # jaune
    "croissance": "\033[94m",  # bleu
    "dormant": "\033[90m",  # gris
}
_RESET = "\033[0m"
_BOLD = "\033[1m"


class TableauDeBord:
    """Affiche l'état de la Pieuvre dans le terminal."""

    def __init__(self, pieuvre: "PieuvreGigante") -> None:
        self._pieuvre = pieuvre

    def render(self) -> None:
        if _USE_RICH:
            self._render_rich()
        else:
            self._render_ansi()

    # ── Rich rendering ────────────────────────────────────────────────────────

    def _render_rich(self) -> None:
        status = self._pieuvre.status()
        _console.clear()

        # En-tête état
        state = status["state"]
        force = status["force"]
        gen = status["generation"]
        cycle = status["cycle"]
        now = datetime.now().strftime("%H:%M:%S")

        state_emoji = {
            "actif": "🟢",
            "alerte": "🔴",
            "recuperation": "🟡",
            "croissance": "🔵",
            "dormant": "⚫",
        }.get(state, "❓")

        bars = min(40, int((force - 1.0) * 20))
        force_bar = "█" * bars + "░" * (40 - bars)

        header = (
            f"🐙 [bold cyan]PIEUVRE GÉANTE[/bold cyan]  {state_emoji} [bold]{state.upper()}[/bold]  "
            f"⏰ {now}  |  Force [{force_bar}] [bold yellow]{force:.4f}x[/bold yellow]  "
            f"|  Gén. [bold]{gen}[/bold]  |  Cycle [bold]{cycle}[/bold]"
        )
        _console.print(Panel(header, style="bold"))

        # Stats incidents
        _console.print(
            f"  📊 Incidents: [bold]{status['incidents_total']}[/bold] total  "
            f"✅ {status['incidents_resolved']} résolus  "
            f"⏳ {status['incidents_pending']} en attente  "
            f"🛡️ {len(self._pieuvre.store.all_immunity_patterns())} immunités"
        )

        # Grille des tentacules
        table = Table(title="Tentacules", box=box.ROUNDED, expand=False)
        table.add_column("Nom", style="cyan")
        table.add_column("État", justify="center")
        table.add_column("Findings", justify="right")
        table.add_column("Scans", justify="right")

        for t in status["tentacles"]:
            active_str = "🟢 actif" if t["active"] else "⏸️ pause"
            findings_str = str(t["findings"])
            if t["findings"] > 0:
                findings_str = f"[bold red]{t['findings']}[/bold red]"
            table.add_row(
                f"{t['emoji']} {t['name']}",
                active_str,
                findings_str,
                str(t["scans"]),
            )

        _console.print(table)

        # Derniers findings HIGH/CRITICAL
        all_findings = []
        for t in self._pieuvre.tentacles:
            all_findings.extend(
                f for f in t.last_findings if f.severity.value in ("high", "critical")
            )
        if all_findings:
            _console.print("\n[bold red]⚠️  Findings HIGH/CRITICAL:[/bold red]")
            for f in all_findings[-10:]:
                _console.print(
                    f"  [{f.severity.value.upper()}] [cyan]{f.file}:{f.line}[/cyan] "
                    f"— {f.rule} — {f.message[:80]}"
                )

    # ── ANSI fallback ─────────────────────────────────────────────────────────

    def _render_ansi(self) -> None:
        status = self._pieuvre.status()
        os.system("cls" if sys.platform == "win32" else "clear")

        state = status["state"]
        force = status["force"]
        color = _STATE_COLORS.get(state, "")
        now = datetime.now().strftime("%H:%M:%S")

        bars = min(30, int((force - 1.0) * 15))
        bar_str = "█" * bars + "░" * (30 - bars)

        print(
            f"{_BOLD}🐙 PIEUVRE GÉANTE{_RESET} — {color}{_BOLD}{state.upper()}{_RESET} — {now}"
        )
        print(
            f"  Force: [{bar_str}] {force:.4f}x  |  Gén. {status['generation']}  |  Cycle {status['cycle']}"
        )
        print(
            f"  Incidents: {status['incidents_total']} | Résolus: {status['incidents_resolved']} | "
            f"Immunités: {len(self._pieuvre.store.all_immunity_patterns())}"
        )
        print()

        # Grille tentacules
        print(f"{'Tentacule':<20} {'État':<10} {'Findings':>9} {'Scans':>7}")
        print("─" * 50)
        for t in status["tentacles"]:
            active_str = "actif" if t["active"] else "pause"
            findings = t["findings"]
            color_f = "\033[91m" if findings > 0 else ""
            print(
                f"  {t['emoji']} {t['name']:<17} {active_str:<10} "
                f"{color_f}{findings:>9}{_RESET} {t['scans']:>7}"
            )

        # Findings HIGH/CRITICAL
        all_findings = []
        for t in self._pieuvre.tentacles:
            all_findings.extend(
                f for f in t.last_findings if f.severity.value in ("high", "critical")
            )
        if all_findings:
            print(f"\n{_BOLD}\033[91m⚠️  Findings HIGH/CRITICAL:{_RESET}")
            for f in all_findings[-8:]:
                print(
                    f"  [{f.severity.value.upper():<8}] {f.file}:{f.line} — {f.message[:70]}"
                )

    # ── Mode continu ──────────────────────────────────────────────────────────

    async def run_loop(self, refresh_seconds: float = 5.0) -> None:
        """Boucle d'affichage asynchrone — tourne en parallèle avec la Pieuvre."""
        import asyncio

        while True:
            try:
                self.render()
            except Exception:
                pass
            await asyncio.sleep(refresh_seconds)
