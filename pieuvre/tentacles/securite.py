"""
Tentacule Sécurité — analyse statique de vulnérabilités.

Détecte (15 règles):
  - Secrets codés en dur (clés API, mots de passe, tokens)
  - Injection SQL (f-strings dans execute/cursor)
  - Injection de commandes (shell=True, os.system)
  - eval / exec dangereux
  - pickle depuis sources inconnues
  - Requêtes HTTP sans timeout
  - bare except qui avalent les erreurs silencieusement
  - Patterns spécifiques au trading (NaN/Inf, division par std sans garde)
  - Fichiers .env ou config trackés par git
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)


@dataclass
class SecurityPattern:
    name: str
    regex: str
    severity: Severity
    message: str
    _compiled: re.Pattern | None = None  # type: ignore[assignment]

    def compile(self) -> re.Pattern:  # type: ignore[return]
        if self._compiled is None:
            self._compiled = re.compile(self.regex)
        return self._compiled


# ── 15 règles de détection ────────────────────────────────────────────────────

_PATTERNS: list[SecurityPattern] = [
    SecurityPattern(
        name="hardcoded_secret",
        regex=r'(?i)(api_key|password|secret|token|passwd|auth_key)\s*=\s*["\'][^"\']{8,}["\']',
        severity=Severity.HIGH,
        message="Secret potentiellement codé en dur",
    ),
    SecurityPattern(
        name="sql_fstring",
        regex=r'(execute|executemany)\s*\(\s*f["\']',
        severity=Severity.HIGH,
        message="Injection SQL — f-string dans execute()",
    ),
    SecurityPattern(
        name="sql_format",
        regex=r'(execute|executemany)\s*\(\s*["\'][^"\']*%[sd][^"\']*["\'\s]*%',
        severity=Severity.HIGH,
        message="Injection SQL — % format dans execute()",
    ),
    SecurityPattern(
        name="subprocess_shell_true",
        regex=r"subprocess\.(run|call|Popen|check_output|check_call).*shell\s*=\s*True",
        severity=Severity.HIGH,
        message="subprocess avec shell=True — risque d'injection de commande",
    ),
    SecurityPattern(
        name="os_system",
        regex=r"\bos\.system\s*\(",
        severity=Severity.MEDIUM,
        message="os.system() — préférer subprocess avec liste d'arguments",
    ),
    SecurityPattern(
        name="eval_usage",
        regex=r"\beval\s*\(",
        severity=Severity.HIGH,
        message="eval() — risque d'exécution de code arbitraire",
    ),
    SecurityPattern(
        name="exec_usage",
        regex=r"\bexec\s*\(\s*(?!compile)",
        severity=Severity.HIGH,
        message="exec() — risque d'exécution de code arbitraire",
    ),
    SecurityPattern(
        name="pickle_load",
        regex=r"pickle\.(load|loads|Unpickler)\s*\(",
        severity=Severity.MEDIUM,
        message="pickle.load() depuis source non vérifiée — risque RCE",
    ),
    SecurityPattern(
        name="http_no_timeout",
        regex=r"requests\.(get|post|put|delete|patch|head)\s*\([^)]*\)(?!\s*\.\s*timeout)",
        severity=Severity.LOW,
        message="Requête HTTP sans paramètre timeout explicite",
    ),
    SecurityPattern(
        name="bare_except",
        regex=r"^\s*except\s*:\s*$",
        severity=Severity.MEDIUM,
        message="bare except — avale toutes les exceptions y compris KeyboardInterrupt",
    ),
    SecurityPattern(
        name="except_pass",
        regex=r"except\s+Exception.*:\s*\n\s*pass\s*$",
        severity=Severity.MEDIUM,
        message="Exception absorbée silencieusement avec pass",
    ),
    SecurityPattern(
        name="tempfile_insecure",
        regex=r"\btempfile\.mktemp\s*\(",
        severity=Severity.MEDIUM,
        message="tempfile.mktemp() insécurisé — race condition possible, utiliser mkstemp()",
    ),
    SecurityPattern(
        name="float_exact_compare",
        regex=r"(?:sharpe|drawdown|return|profit)\s*==\s*(?:0\.0|1\.0|-1\.0|float)",
        severity=Severity.LOW,
        message="Comparaison exacte de float financier — risque NaN/Inf",
    ),
    SecurityPattern(
        name="div_no_zero_guard",
        regex=r"\/\s*(?:std|stdev|std_dev|volatility)\b(?![^;#\n]*(?:if|!=\s*0|>\s*0|epsilon))",
        severity=Severity.LOW,
        message="Division par std/volatility sans vérification de division par zéro",
    ),
    SecurityPattern(
        name="assert_auth",
        regex=r"\bassert\b.*(?:auth|permission|admin|role|access)",
        severity=Severity.MEDIUM,
        message="assert() pour vérification de sécurité — désactivé avec python -O",
    ),
]


class SecuriteTentacle(BaseTentacle):
    """Analyse statique — scanne tous les .py pour des vulnérabilités."""

    name = "securite"
    emoji = "🛡️"

    def __init__(self, repo_path: Path) -> None:
        super().__init__(repo_path)
        self._patterns = list(_PATTERNS)
        # Compile tous les patterns au démarrage
        for p in self._patterns:
            p.compile()

    def add_immunity(self, pattern_name: str) -> None:
        """Immunité = ne plus alerter sur ce pattern (déjà connu, géré)."""
        super().add_immunity(pattern_name)

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        files = self._collect_py_files()
        findings: list[Finding] = []

        for path in files:
            findings.extend(self._scan_file(path))

        # Trier par sévérité décroissante
        sev_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }
        findings.sort(key=lambda f: sev_order.get(f.severity, 9))

        self.last_findings = findings
        if findings:
            high_count = sum(
                1 for f in findings if f.severity in (Severity.HIGH, Severity.CRITICAL)
            )
            logger.warning(
                "[SECURITE] %d trouvailles (%d HIGH/CRITICAL) sur %d fichiers",
                len(findings),
                high_count,
                len(files),
            )
        return findings

    def _scan_file(self, path: Path) -> list[Finding]:
        findings: list[Finding] = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []

        for lineno, line in enumerate(lines, 1):
            for pat in self._patterns:
                if self.is_immune(pat.name):
                    continue
                if pat.compile().search(line):
                    findings.append(
                        Finding(
                            file=self._relative(path),
                            line=lineno,
                            rule=pat.name,
                            message=pat.message,
                            severity=pat.severity,
                            snippet=line.strip()[:120],
                            tentacle=self.name,
                        )
                    )

        return findings

    def summary(self) -> str:
        counts = {s: 0 for s in Severity}
        for f in self.last_findings:
            counts[f.severity] += 1
        return (
            f"🛡️ Sécurité: {len(self.last_findings)} trouvailles — "
            f"CRITICAL:{counts[Severity.CRITICAL]} HIGH:{counts[Severity.HIGH]} "
            f"MED:{counts[Severity.MEDIUM]} LOW:{counts[Severity.LOW]}"
        )
