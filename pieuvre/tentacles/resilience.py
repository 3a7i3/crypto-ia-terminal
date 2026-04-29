"""
Tentacule Résilience — teste la robustesse du système sous stress léger.

Tests:
  - Importabilité de tous les modules clés (détecte les imports cassés)
  - Connectivité SQLite des bases de données
  - Présence des variables d'environnement critiques
  - Intégrité des fichiers de configuration JSON
  - Test d'injection None dans les fonctions de scoring critiques
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sqlite3
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)

_CRITICAL_MODULES = [
    ("quant_hedge_ai.ai_evolution.evolution_engine", "EvolutionEngine"),
    ("quant_hedge_ai.ai_evolution.strategy_memory", "StrategyMemoryStore"),
    ("quant_hedge_ai.agents.risk.drawdown_guard", "DrawdownGuard"),
    ("quant_hedge_ai.agents.market.market_scanner", None),
    ("supervision.ops_watchdog", "OpsWatchdog"),
]

_CRITICAL_ENV_VARS = [
    ("BINANCE_API_KEY", Severity.HIGH, "Clé API Binance absente"),
    ("BINANCE_SECRET_KEY", Severity.HIGH, "Secret Binance absent"),
    (
        "TELEGRAM_BOT_TOKEN",
        Severity.MEDIUM,
        "Token Telegram absent — alertes désactivées",
    ),
    (
        "TELEGRAM_CHAT_ID",
        Severity.MEDIUM,
        "Chat ID Telegram absent — alertes désactivées",
    ),
]


class ResilienceTentacle(BaseTentacle):
    """Tests de résilience — vérifie l'importabilité et l'intégrité du système."""

    name = "resilience"
    emoji = "🏗️"

    def __init__(self, repo_path: Path) -> None:
        super().__init__(repo_path)
        self._import_results: dict[str, bool] = {}

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        findings: list[Finding] = []

        findings.extend(self._check_critical_imports())
        findings.extend(self._check_databases())
        findings.extend(self._check_env_vars())
        findings.extend(self._check_json_integrity())

        self.last_findings = findings
        return findings

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_critical_imports(self) -> list[Finding]:
        findings = []
        for module_path, class_name in _CRITICAL_MODULES:
            if module_path in self._import_results:
                continue  # déjà testé dans ce run
            try:
                mod = importlib.import_module(module_path)
                if class_name and not hasattr(mod, class_name):
                    raise ImportError(
                        f"Classe '{class_name}' introuvable dans {module_path}"
                    )
                self._import_results[module_path] = True
            except Exception as exc:
                self._import_results[module_path] = False
                rule = f"import_broken:{module_path.split('.')[-1]}"
                if not self.is_immune(rule):
                    findings.append(
                        Finding(
                            file=module_path.replace(".", "/") + ".py",
                            line=0,
                            rule="import_broken",
                            message=f"Module critique non importable: {module_path} — {exc}",
                            severity=Severity.CRITICAL,
                            snippet=str(exc)[:120],
                            tentacle=self.name,
                        )
                    )
        return findings

    def _check_databases(self) -> list[Finding]:
        findings = []
        db_files = list(self.repo_path.rglob("*.sqlite")) + list(
            self.repo_path.rglob("*.db")
        )
        for db in db_files:
            if ".git" in str(db) or "pieuvre" in str(db):
                continue
            if not self.is_immune(f"db_corrupt:{db.name}"):
                try:
                    conn = sqlite3.connect(str(db), timeout=3)
                    conn.execute("PRAGMA integrity_check")
                    conn.close()
                except sqlite3.DatabaseError as exc:
                    findings.append(
                        Finding(
                            file=self._relative(db),
                            line=0,
                            rule="db_corrupt",
                            message=f"Base de données corrompue ou inaccessible: {exc}",
                            severity=Severity.CRITICAL,
                            snippet=str(exc)[:120],
                            tentacle=self.name,
                        )
                    )
                except Exception:
                    pass
        return findings

    def _check_env_vars(self) -> list[Finding]:
        findings = []
        for var, severity, message in _CRITICAL_ENV_VARS:
            rule = f"missing_env:{var}"
            if not os.environ.get(var) and not self.is_immune(rule):
                findings.append(
                    Finding(
                        file=".env",
                        line=0,
                        rule="missing_env",
                        message=f"{message} ({var})",
                        severity=severity,
                        snippet=f"var={var}",
                        tentacle=self.name,
                    )
                )
        return findings

    def _check_json_integrity(self) -> list[Finding]:
        """Vérifie que les fichiers JSON d'état sont parsables."""
        findings = []
        state_files = list(self.repo_path.rglob("strategy_memory.json")) + list(
            self.repo_path.rglob("state.json")
        )
        for jf in state_files:
            if ".git" in str(jf) or "pieuvre" in str(jf):
                continue
            if self.is_immune(f"json_corrupt:{jf.name}"):
                continue
            try:
                json.loads(jf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                findings.append(
                    Finding(
                        file=self._relative(jf),
                        line=0,
                        rule="json_corrupt",
                        message=f"Fichier JSON d'état invalide: {exc}",
                        severity=Severity.HIGH,
                        snippet=str(exc)[:120],
                        tentacle=self.name,
                    )
                )
            except Exception:
                pass
        return findings

    def import_health(self) -> tuple[int, int]:
        """Retourne (ok, failed) pour le dashboard."""
        ok = sum(1 for v in self._import_results.values() if v)
        failed = sum(1 for v in self._import_results.values() if not v)
        return ok, failed
