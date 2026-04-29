"""
Tentacule Performance — profiling mémoire et CPU du projet en cours d'exécution.

Surveille:
  - Consommation mémoire RSS du process courant et tendance
  - Temps d'import des modules clés (détecte les imports lents)
  - Taille des fichiers JSON de state (scoreboard, strategy_memory) — drift de taille
  - Fuite mémoire détectée par croissance monotone sur N scans consécutifs
"""

from __future__ import annotations

import importlib
import logging
import time
from collections import deque
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)

_RAM_LEAK_WINDOW = 5  # scans consécutifs pour déclarer une fuite
_RAM_LEAK_GROWTH_MB = 50.0  # croissance totale sur la fenêtre pour alerter
_IMPORT_SLOW_SECONDS = 2.0  # seuil d'import trop lent
_JSON_STATE_GROWTH_MB = 20.0  # croissance d'un fichier JSON d'état entre scans


class PerformanceTentacle(BaseTentacle):
    """Profiling performance — détecte fuites et dégradations."""

    name = "performance"
    emoji = "⚡"

    def __init__(self, repo_path: Path) -> None:
        super().__init__(repo_path)
        self._ram_history: deque[float] = deque(maxlen=_RAM_LEAK_WINDOW)
        self._prev_json_sizes: dict[str, float] = {}
        self._import_times_cache: dict[str, float] = {}

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        findings: list[Finding] = []

        findings.extend(self._check_ram_leak())
        findings.extend(self._check_json_state_growth())
        findings.extend(self._check_slow_imports())

        self.last_findings = findings
        return findings

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_ram_leak(self) -> list[Finding]:
        findings = []
        try:
            import os

            import psutil

            proc = psutil.Process(os.getpid())
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            self._ram_history.append(rss_mb)

            if len(self._ram_history) == _RAM_LEAK_WINDOW:
                growth = self._ram_history[-1] - self._ram_history[0]
                all_growing = all(
                    self._ram_history[i] <= self._ram_history[i + 1]
                    for i in range(len(self._ram_history) - 1)
                )
                if all_growing and growth > _RAM_LEAK_GROWTH_MB:
                    if not self.is_immune("ram_leak"):
                        findings.append(
                            Finding(
                                file="system:memory",
                                line=0,
                                rule="ram_leak",
                                message=(
                                    f"Fuite mémoire probable: +{growth:.0f}Mo sur "
                                    f"{_RAM_LEAK_WINDOW} scans consécutifs (actuel: {rss_mb:.0f}Mo)"
                                ),
                                severity=Severity.HIGH,
                                snippet=f"rss={rss_mb:.0f}Mo growth={growth:.0f}Mo",
                                tentacle=self.name,
                            )
                        )
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("check_ram_leak: %s", exc)
        return findings

    def _check_json_state_growth(self) -> list[Finding]:
        """Détecte les fichiers JSON d'état qui grossissent anormalement."""
        findings = []
        json_files = (
            list(self.repo_path.rglob("strategy_scoreboard.json"))
            + list(self.repo_path.rglob("strategy_memory.json"))
            + list(self.repo_path.rglob("state.json"))
        )
        for jf in json_files:
            if ".git" in str(jf) or "pieuvre" in str(jf):
                continue
            try:
                size_mb = jf.stat().st_size / (1024 * 1024)
                key = str(jf)
                prev = self._prev_json_sizes.get(key, size_mb)
                growth = size_mb - prev
                self._prev_json_sizes[key] = size_mb

                if growth > _JSON_STATE_GROWTH_MB and not self.is_immune(
                    "json_state_growth"
                ):
                    findings.append(
                        Finding(
                            file=self._relative(jf),
                            line=0,
                            rule="json_state_growth",
                            message=(
                                f"Fichier d'état JSON grossit vite: +{growth:.1f}Mo "
                                f"(total {size_mb:.1f}Mo) — risque de ralentissement"
                            ),
                            severity=Severity.MEDIUM,
                            snippet=f"size={size_mb:.1f}Mo delta={growth:+.1f}Mo",
                            tentacle=self.name,
                        )
                    )
            except OSError:
                pass
        return findings

    def _check_slow_imports(self) -> list[Finding]:
        """Mesure le temps d'import des modules clés une seule fois."""
        findings = []
        key_modules = [
            "quant_hedge_ai.agents.quant.backtest_lab",
            "quant_hedge_ai.agents.strategy.genetic_optimizer",
            "quant_hedge_ai.agents.market.market_scanner",
        ]
        for mod in key_modules:
            if mod in self._import_times_cache:
                continue  # déjà mesuré
            t0 = time.perf_counter()
            try:
                importlib.import_module(mod)
                elapsed = time.perf_counter() - t0
                self._import_times_cache[mod] = elapsed
                if elapsed > _IMPORT_SLOW_SECONDS and not self.is_immune("slow_import"):
                    findings.append(
                        Finding(
                            file=mod.replace(".", "/") + ".py",
                            line=0,
                            rule="slow_import",
                            message=f"Import lent: {mod} → {elapsed:.2f}s (seuil {_IMPORT_SLOW_SECONDS}s)",
                            severity=Severity.LOW,
                            snippet=f"import_time={elapsed:.2f}s",
                            tentacle=self.name,
                        )
                    )
            except Exception:
                self._import_times_cache[mod] = -1.0  # marqué comme échoué

        return findings

    def current_ram_mb(self) -> float:
        try:
            import os

            import psutil

            return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0
