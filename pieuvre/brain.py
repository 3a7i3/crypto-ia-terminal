"""
La Pieuvre Géante — cerveau central du système de surveillance auto-évolutif.

Machine à états:

    DORMANT ──start()──► ACTIVE ──critique──► ALERTE ──traité──► RECOVERY
                 ▲                                                    │
                 │                                               délai écoulé
                 │                                                    │
                 └──────────── REGROWTH ◄────────────────────────────┘
                              (+force, +immunité, +génération)

La Pieuvre devient plus forte à chaque incident résolu:
  - LOW      → +2% de force, récupération  60s
  - MEDIUM   → +5% de force, récupération 300s
  - HIGH     → +10% de force, récupération 900s
  - CRITICAL → +20% de force, récupération 1800s

La force accumulée réduit le temps de récupération (max -60%)
et augmente la fréquence des scans.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from pathlib import Path

from observability.json_logger import get_logger
from pieuvre.incidents.models import (
    _SEV_ORDER,
    Finding,
    Incident,
    IncidentType,
    Severity,
)
from pieuvre.incidents.store import IncidentStore
from pieuvre.tentacles.audit_commits import AuditCommitsTentacle
from pieuvre.tentacles.evolution import EvolutionTentacle
from pieuvre.tentacles.guerison import GuerisonTentacle
from pieuvre.tentacles.memoire import MemoireTentacle
from pieuvre.tentacles.performance import PerformanceTentacle
from pieuvre.tentacles.resilience import ResilienceTentacle
from pieuvre.tentacles.securite import SecuriteTentacle
from pieuvre.tentacles.surveillance import SurveillanceTentacle

_log = get_logger("pieuvre.brain")


def _bus_emit(event) -> None:
    """Émet un event sur l'EventBus global — silencieux si non dispo."""
    try:
        from event_bus.bus import EventBus

        EventBus.get().emit(event)
    except Exception:
        pass


# Intervalle de base entre les cycles ACTIVE (réduit quand force augmente)
_BASE_CYCLE_INTERVAL = 60.0
_ALERT_INTERVAL = 8.0
_RECOVERY_CHECK_INTERVAL = 20.0


class BrainState(Enum):
    DORMANT = "dormant"
    ACTIVE = "actif"
    ALERT = "alerte"
    RECOVERY = "recuperation"
    REGROWTH = "croissance"


class PieuvreGigante:
    """Système de surveillance auto-évolutif à 8 tentacules."""

    def __init__(
        self,
        repo_path: str = ".",
        auto_fix: bool = False,
        notifier=None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.auto_fix = auto_fix
        self._notifier = notifier

        self.state = BrainState.DORMANT
        self.force: float = 1.0
        self.generation: int = 0
        self._cycle_count: int = 0
        self._running: bool = False
        self._active_incident: Incident | None = None

        store_path = self.repo_path / "pieuvre" / "incidents" / "history.json"
        self.store = IncidentStore(store_path)

        # Restaure la force accumulée depuis les incidents passés
        self.force = 1.0 + self.store.total_strength_gained()

        # 8 tentacules spécialisées
        self._guerison = GuerisonTentacle(self.repo_path)
        self._memoire = MemoireTentacle(self.repo_path, self.store)
        self.tentacles = [
            SecuriteTentacle(self.repo_path),
            AuditCommitsTentacle(self.repo_path),
            SurveillanceTentacle(self.repo_path),
            EvolutionTentacle(self.repo_path, auto_fix=auto_fix),
            self._memoire,
            self._guerison,
            PerformanceTentacle(self.repo_path),
            ResilienceTentacle(self.repo_path),
        ]

        # Charge les immunités acquises lors des incidents passés
        known_immunities = self.store.all_immunity_patterns()
        for t in self.tentacles:
            t.load_immunities(known_immunities)

        _log.info(
            "Pieuvre initialisée — force=%.3f, génération=%d, incidents passés=%d, immunités=%d",
            self.force,
            self.generation,
            len(self.store.all()),
            len(known_immunities),
        )

    # ── Boucle principale ─────────────────────────────────────────────────────

    async def run(self) -> None:
        """Démarre la Pieuvre — tourne jusqu'à stop() ou CTRL+C."""
        self._running = True
        self.state = BrainState.ACTIVE
        self.generation = max(1, self.generation + 1)

        self._print_awakening()

        try:
            while self._running:
                await self._tick()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self.state = BrainState.DORMANT
            _log.info("Pieuvre endormie après %d cycles.", self._cycle_count)

    def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        self._cycle_count += 1

        if self.state == BrainState.ACTIVE:
            await self._active_cycle()

        elif self.state == BrainState.ALERT:
            await self._alert_cycle()
            await asyncio.sleep(_ALERT_INTERVAL)

        elif self.state == BrainState.RECOVERY:
            if self._guerison.is_healed():
                self.state = BrainState.REGROWTH
            else:
                bar = self._guerison.render_recovery_bar()
                _log.info("[RECOVERY] %s", bar)
                await asyncio.sleep(_RECOVERY_CHECK_INTERVAL)

        elif self.state == BrainState.REGROWTH:
            await self._regrowth_cycle()

    # ── Cycles d'état ─────────────────────────────────────────────────────────

    async def _active_cycle(self) -> None:
        _log.info(
            "[ACTIF] Cycle %d | force=%.3f | génération=%d | incidents=%d",
            self._cycle_count,
            self.force,
            self.generation,
            len(self.store.all()),
        )

        all_findings = await self._run_all_tentacles()

        # Cherche le finding le plus grave
        worst = self._worst_finding(all_findings)
        if worst and worst.severity in (Severity.HIGH, Severity.CRITICAL):
            await self._enter_alert(worst, all_findings)
            return

        # Cycle sain — ajuste l'intervalle selon la force
        interval = _BASE_CYCLE_INTERVAL / max(0.5, self.force)
        await asyncio.sleep(interval)

    async def _alert_cycle(self) -> None:
        if self._active_incident is None:
            self.state = BrainState.ACTIVE
            return

        inc = self._active_incident
        _log.warning(
            "[ALERTE] %s | sévérité=%s | module=%s",
            inc.message[:80],
            inc.severity.value,
            inc.module,
        )

        # Extrait leçons et immunités
        inc.lessons = self._memoire.extract_lessons(inc.findings)
        inc.immunity_patterns = self._memoire.extract_immunity_patterns(inc.findings)

        # Démarre la guérison
        actual_secs = self._guerison.start_recovery(inc, self.force)

        # Sauvegarde l'incident (non résolu)
        self.store.save(inc)

        # Pause tous les tentacules non-guérison
        for t in self.tentacles:
            if t is not self._guerison:
                t.pause()

        # Notification si disponible
        if self._notifier:
            try:
                self._notifier.info(
                    f"🐙 Pieuvre ALERTE\n"
                    f"Sévérité: {inc.severity.value.upper()}\n"
                    f"Module: {inc.module}\n"
                    f"Message: {inc.message[:100]}\n"
                    f"Récupération: {actual_secs:.0f}s",
                    key="pieuvre_alert",
                )
            except Exception:
                pass

        self.state = BrainState.RECOVERY

    async def _enter_alert(self, worst: Finding, all_findings: list[Finding]) -> None:
        inc = Incident(
            type=(
                IncidentType.CODE_VULN
                if worst.tentacle == "securite"
                else IncidentType.SECURITY
            ),
            severity=worst.severity,
            module=worst.file,
            message=f"{worst.rule}: {worst.message}",
            findings=all_findings,
        )
        self._active_incident = inc
        self.state = BrainState.ALERT
        _log.error(
            "[PIEUVRE] Incident déclenché — %s:%d — %s",
            worst.file,
            worst.line,
            worst.message,
        )
        from event_bus.events import IncidentStartedEvent, SecurityAlertEvent

        _bus_emit(
            IncidentStartedEvent(
                incident_id=inc.id,
                severity=worst.severity.value,
                module=worst.file,
                message=inc.message[:200],
            )
        )
        _bus_emit(
            SecurityAlertEvent(
                severity=worst.severity.value,
                rule=worst.rule,
                file=worst.file,
                line=worst.line,
                message=worst.message[:200],
                tentacle=worst.tentacle,
            )
        )

    async def _regrowth_cycle(self) -> None:
        """Consolidation mémoire + gain de force + réveil renforcé."""
        if self._active_incident:
            inc = self._active_incident
            inc.resolve()

            old_force = self.force
            self.force += inc.strength_gained
            self.store.save(inc)

            # Injecte les nouvelles immunités dans tous les tentacules
            for pattern in inc.immunity_patterns:
                for t in self.tentacles:
                    t.add_immunity(pattern)

            _log.info(
                "[REGROWTH] Incident %s résolu. Force: %.3f → %.3f (+%.3f) | "
                "Immunités injectées: %s",
                inc.id,
                old_force,
                self.force,
                inc.strength_gained,
                inc.immunity_patterns,
            )

            if self._notifier:
                try:
                    self._notifier.info(
                        f"🐙 Pieuvre RENFORCÉE\n"
                        f"Force: {old_force:.3f} → {self.force:.3f}\n"
                        f"Nouvelles immunités: {', '.join(inc.immunity_patterns[:5])}\n"
                        f"Génération: {self.generation + 1}",
                        key="pieuvre_regrowth",
                    )
                except Exception:
                    pass

            self._active_incident = None
            self._guerison.complete_recovery()
            from event_bus.events import IncidentResolvedEvent

            _bus_emit(
                IncidentResolvedEvent(
                    incident_id=inc.id,
                    severity=inc.severity.value,
                    strength_gained=inc.strength_gained,
                    new_force=self.force,
                    immunity_patterns=inc.immunity_patterns[:10],
                )
            )

        # Reprend tous les tentacules
        for t in self.tentacles:
            t.resume()

        self.generation += 1
        self.state = BrainState.ACTIVE
        self._print_regrowth()
        from event_bus.events import PieuvreRegrowthEvent

        _bus_emit(
            PieuvreRegrowthEvent(
                generation=self.generation,
                total_force=self.force,
                total_immunities=len(self.store.all_immunity_patterns()),
            )
        )

    # ── Orchestration des tentacules ──────────────────────────────────────────

    async def _run_all_tentacles(self) -> list[Finding]:
        """Lance les 8 tentacules actives en parallèle via asyncio.to_thread."""
        active = [t for t in self.tentacles if t.active]
        if not active:
            return []

        tasks = [
            asyncio.create_task(asyncio.to_thread(t.scan), name=t.name) for t in active
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_findings: list[Finding] = []
        for tentacle, result in zip(active, results):
            if isinstance(result, Exception):
                _log.warning("Tentacule %s erreur: %s", tentacle.name, result)
            elif isinstance(result, list):
                tentacle.last_findings = result
                all_findings.extend(result)
                if result:
                    _log.debug(
                        "%s %s: %d finding(s)",
                        tentacle.emoji,
                        tentacle.name,
                        len(result),
                    )

        return all_findings

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _worst_finding(findings: list[Finding]) -> Finding | None:
        if not findings:
            return None
        return max(
            findings,
            key=lambda f: (
                _SEV_ORDER.index(f.severity) if f.severity in _SEV_ORDER else -1
            ),
        )

    def status(self) -> dict:
        return {
            "state": self.state.value,
            "force": round(self.force, 4),
            "generation": self.generation,
            "cycle": self._cycle_count,
            "incidents_total": len(self.store.all()),
            "incidents_resolved": len(self.store.resolved()),
            "incidents_pending": len(self.store.pending()),
            "tentacles": [
                {
                    "name": t.name,
                    "emoji": t.emoji,
                    "active": t.active,
                    "findings": len(t.last_findings),
                    "scans": t._scan_count,
                }
                for t in self.tentacles
            ],
        }

    # ── Affichage ─────────────────────────────────────────────────────────────

    def _print_awakening(self) -> None:
        past = len(self.store.all())
        immunities = len(self.store.all_immunity_patterns())
        print(
            f"""
╔═══════════════════════════════════════════════════════════════╗
║             🐙  LA PIEUVRE GÉANTE S'ÉVEILLE  🐙              ║
╠═══════════════════════════════════════════════════════════════╣
║  8 tentacules déployées sur: {str(self.repo_path)[:30]:<30} ║
╠═══════════════════════════════════════════════════════════════╣
║  Force          : {self.force:>8.3f}x                                ║
║  Génération     : {self.generation:>8}                                ║
║  Incidents passés: {past:>7}                                ║
║  Immunités actives: {immunities:>6}                                ║
╠═══════════════════════════════════════════════════════════════╣
║  🛡️  Sécurité        📜 Audit Commits   👁️  Surveillance      ║
║  🧬  Évolution       🧠 Mémoire         💊 Guérison           ║
║  ⚡  Performance     🏗️  Résilience                            ║
╚═══════════════════════════════════════════════════════════════╝
"""
        )

    def _print_regrowth(self) -> None:
        bars = min(40, int((self.force - 1.0) * 20))
        bar_str = "█" * bars + "░" * (40 - bars)
        print(
            f"""
┌──────────────────────────────────────────────────┐
│  🐙 REGROWTH — Génération {self.generation:>3} activée              │
│  Force: [{bar_str}] {self.force:.4f}x  │
│  Immunités: {len(self.store.all_immunity_patterns())} patterns absorbés                  │
└──────────────────────────────────────────────────┘
"""
        )
