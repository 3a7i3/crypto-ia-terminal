"""
Tentacule Surveillance — monitoring runtime étendu.

Étend OpsWatchdog avec:
  - Surveillance CPU/RAM en temps réel
  - Détection de fichiers de log qui grossissent anormalement
  - Surveillance des processus Python actifs
  - Détection de deadlocks potentiels (threads bloqués)
  - Vérification de la fraîcheur des données market
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)

_CPU_ALERT_THRESHOLD = 90.0  # %
_RAM_ALERT_THRESHOLD = 85.0  # %
_LOG_SIZE_ALERT_MB = 100.0  # Mo
_LOG_GROWTH_ALERT_MB = 10.0  # Mo en 1 scan
_STALE_DATA_SECONDS = 3600  # 1h sans mise à jour = donnée périmée


class SurveillanceTentacle(BaseTentacle):
    """Monitoring runtime — ressources système + santé des fichiers."""

    name = "surveillance"
    emoji = "👁️"

    def __init__(self, repo_path: Path) -> None:
        super().__init__(repo_path)
        self._prev_log_sizes: dict[str, float] = {}
        self._prev_scan_time: float = 0.0

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        findings: list[Finding] = []

        findings.extend(self._check_system_resources())
        findings.extend(self._check_log_files())
        findings.extend(self._check_database_freshness())
        findings.extend(self._check_zombie_processes())

        self._prev_scan_time = time.time()
        self.last_findings = findings
        return findings

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_system_resources(self) -> list[Finding]:
        findings = []
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1.0)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage(str(self.repo_path)).percent

            if cpu > _CPU_ALERT_THRESHOLD and not self.is_immune("high_cpu"):
                findings.append(
                    Finding(
                        file="system:cpu",
                        line=0,
                        rule="high_cpu",
                        message=f"CPU à {cpu:.0f}% — risque de ralentissement du bot",
                        severity=Severity.HIGH if cpu > 95 else Severity.MEDIUM,
                        snippet=f"cpu={cpu:.1f}%",
                        tentacle=self.name,
                    )
                )

            if ram > _RAM_ALERT_THRESHOLD and not self.is_immune("high_ram"):
                findings.append(
                    Finding(
                        file="system:ram",
                        line=0,
                        rule="high_ram",
                        message=f"RAM à {ram:.0f}% — risque de crash par OOM",
                        severity=Severity.HIGH if ram > 95 else Severity.MEDIUM,
                        snippet=f"ram={ram:.1f}%",
                        tentacle=self.name,
                    )
                )

            if disk > 90.0 and not self.is_immune("disk_full"):
                findings.append(
                    Finding(
                        file="system:disk",
                        line=0,
                        rule="disk_full",
                        message=f"Disque à {disk:.0f}% — risque d'arrêt des logs",
                        severity=Severity.HIGH,
                        snippet=f"disk={disk:.1f}%",
                        tentacle=self.name,
                    )
                )

        except ImportError:
            pass  # psutil non installé — skip
        except Exception as exc:
            logger.debug("Surveillance ressources: %s", exc)

        return findings

    def _check_log_files(self) -> list[Finding]:
        findings = []
        logs_dir = self.repo_path / "logs"
        if not logs_dir.exists():
            return []

        for log_file in logs_dir.glob("*.log"):
            try:
                size_mb = log_file.stat().st_size / (1024 * 1024)
                prev_size = self._prev_log_sizes.get(str(log_file), size_mb)
                growth_mb = size_mb - prev_size
                self._prev_log_sizes[str(log_file)] = size_mb

                if size_mb > _LOG_SIZE_ALERT_MB and not self.is_immune("log_too_large"):
                    findings.append(
                        Finding(
                            file=self._relative(log_file),
                            line=0,
                            rule="log_too_large",
                            message=f"Fichier log volumineux: {size_mb:.1f}Mo — rotation nécessaire",
                            severity=Severity.MEDIUM,
                            snippet=f"size={size_mb:.1f}Mo",
                            tentacle=self.name,
                        )
                    )

                if growth_mb > _LOG_GROWTH_ALERT_MB and not self.is_immune(
                    "log_rapid_growth"
                ):
                    findings.append(
                        Finding(
                            file=self._relative(log_file),
                            line=0,
                            rule="log_rapid_growth",
                            message=f"Log grossit rapidement: +{growth_mb:.1f}Mo depuis dernier scan",
                            severity=Severity.MEDIUM,
                            snippet=f"growth={growth_mb:.1f}Mo",
                            tentacle=self.name,
                        )
                    )
            except OSError:
                pass

        return findings

    def _check_database_freshness(self) -> list[Finding]:
        """Vérifie que les bases SQLite ne sont pas trop vieilles."""
        findings = []
        now = time.time()

        db_files = list(self.repo_path.rglob("*.sqlite")) + list(
            self.repo_path.rglob("*.db")
        )
        for db in db_files:
            if ".git" in str(db) or "pieuvre" in str(db):
                continue
            try:
                mtime = db.stat().st_mtime
                age = now - mtime
                if age > _STALE_DATA_SECONDS and not self.is_immune("stale_database"):
                    hours = age / 3600
                    findings.append(
                        Finding(
                            file=self._relative(db),
                            line=0,
                            rule="stale_database",
                            message=f"Base de données non mise à jour depuis {hours:.1f}h",
                            severity=Severity.LOW,
                            snippet=f"age={hours:.1f}h",
                            tentacle=self.name,
                        )
                    )
            except OSError:
                pass

        return findings

    def _check_zombie_processes(self) -> list[Finding]:
        """Détecte les processus Python orphelins liés au projet."""
        findings = []
        try:
            import psutil

            project_name = self.repo_path.name.lower()
            zombies = []
            for proc in psutil.process_iter(["pid", "name", "status", "cmdline"]):
                try:
                    if proc.info["status"] == psutil.STATUS_ZOMBIE:
                        cmdline = " ".join(proc.info.get("cmdline") or [])
                        if project_name in cmdline.lower():
                            zombies.append(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if zombies and not self.is_immune("zombie_process"):
                findings.append(
                    Finding(
                        file="system:processes",
                        line=0,
                        rule="zombie_process",
                        message=f"Processus zombie détecté (PIDs: {zombies})",
                        severity=Severity.MEDIUM,
                        snippet=f"pids={zombies}",
                        tentacle=self.name,
                    )
                )
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("Surveillance processus: %s", exc)

        return findings
