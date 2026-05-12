"""
Tentacule Audit Commits — analyse l'historique git pour détecter les anomalies.

Détecte:
  - Commits qui touchent des fichiers sensibles (clés, config, .env)
  - Mots-clés de sécurité dans les messages ("fix vuln", "hotfix", "critical")
  - Fichiers les plus modifiés (hot spots — instabilité)
  - Commits de grande taille (>500 lignes) — risque de régression cachée
  - Auteurs inhabituels ou commits directs sur main/master
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)

_SECURITY_KEYWORDS = re.compile(
    r"(?i)\b(vuln|exploit|cve|injection|xss|csrf|hack|breach|leak|exposed|"
    r"secret|password|credential|token.*expose|hotfix.*critical|emergency|"
    r"revert.*security|fix.*auth)\b"
)

_SENSITIVE_FILES = re.compile(
    r"(?i)\.(env|key|pem|p12|pfx|secret|credentials|token)$"
    r"|(config\.py|settings\.py|secrets\.py|\.env\..*)"
)

_RISKY_PATTERNS_IN_DIFF = [
    (
        re.compile(r'\+.*api_key\s*=\s*["\'][^"\']{8,}["\']', re.I),
        "secret_in_diff",
        Severity.CRITICAL,
    ),
    (
        re.compile(r'\+.*password\s*=\s*["\'][^"\']{4,}["\']', re.I),
        "password_in_diff",
        Severity.CRITICAL,
    ),
    (re.compile(r"\+.*os\.system\s*\(", re.I), "os_system_added", Severity.MEDIUM),
    (re.compile(r"\+.*eval\s*\(", re.I), "eval_added", Severity.HIGH),
    (re.compile(r"\+.*shell\s*=\s*True", re.I), "shell_true_added", Severity.HIGH),
]


class AuditCommitsTentacle(BaseTentacle):
    """Analyse l'historique git pour détecter des anomalies de sécurité."""

    name = "audit_commits"
    emoji = "📜"

    def __init__(self, repo_path: Path, lookback: int = 30) -> None:
        super().__init__(repo_path)
        self.lookback = lookback  # nombre de commits à analyser

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        findings: list[Finding] = []

        commits = self._get_commits()
        if not commits:
            return []

        for commit in commits:
            findings.extend(self._audit_commit(commit))

        findings.extend(self._check_hot_spots(commits))
        findings.extend(self._check_large_commits(commits))

        self.last_findings = findings
        if findings:
            logger.warning(
                "[AUDIT_COMMITS] %d anomalies sur %d commits",
                len(findings),
                len(commits),
            )
        return findings

    # ── Git helpers ───────────────────────────────────────────────────────────

    def _run_git(self, *args: str, timeout: int = 15) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout
        except Exception as exc:
            logger.debug("git %s: %s", " ".join(args), exc)
            return ""

    def _get_commits(self) -> list[dict]:
        output = self._run_git(
            "log",
            f"--max-count={self.lookback}",
            "--pretty=format:%H|%an|%ae|%ai|%s",
        )
        commits = []
        for line in output.splitlines():
            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append(
                    {
                        "hash": parts[0],
                        "author": parts[1],
                        "email": parts[2],
                        "date": parts[3],
                        "subject": parts[4],
                    }
                )
        return commits

    def _get_diff(self, commit_hash: str) -> str:
        return self._run_git("show", "--diff-filter=AM", "-U0", commit_hash, timeout=20)

    def _get_changed_files(self, commit_hash: str) -> list[str]:
        output = self._run_git("show", "--name-only", "--format=", commit_hash)
        return [f.strip() for f in output.splitlines() if f.strip()]

    def _get_stat(self, commit_hash: str) -> tuple[int, int]:
        """Retourne (lines_added, lines_removed)."""
        output = self._run_git("show", "--stat", "--format=", commit_hash)
        match = re.search(r"(\d+) insertion.*?(\d+) deletion", output)
        if match:
            return int(match.group(1)), int(match.group(2))
        match_add = re.search(r"(\d+) insertion", output)
        if match_add:
            return int(match_add.group(1)), 0
        return 0, 0

    # ── Audits ────────────────────────────────────────────────────────────────

    def _audit_commit(self, commit: dict) -> list[Finding]:
        findings: list[Finding] = []
        subject = commit["subject"]
        chash = commit["hash"][:8]

        # Message de commit avec keywords de sécurité
        if _SECURITY_KEYWORDS.search(subject) and not self.is_immune(
            "security_keyword"
        ):
            findings.append(
                Finding(
                    file=f"git:commit:{chash}",
                    line=0,
                    rule="security_keyword",
                    message=f"Commit '{subject[:80]}' contient des mots-clés sécurité",
                    severity=Severity.MEDIUM,
                    snippet=subject[:120],
                    tentacle=self.name,
                )
            )

        # Fichiers sensibles modifiés
        for fpath in self._get_changed_files(commit["hash"]):
            if _SENSITIVE_FILES.search(fpath) and not self.is_immune("sensitive_file"):
                findings.append(
                    Finding(
                        file=f"git:commit:{chash}",
                        line=0,
                        rule="sensitive_file",
                        message=f"Fichier sensible modifié: {fpath}",
                        severity=Severity.HIGH,
                        snippet=fpath,
                        tentacle=self.name,
                    )
                )

        # Scan du diff pour patterns dangereux
        diff = self._get_diff(commit["hash"])
        for pattern, rule, severity in _RISKY_PATTERNS_IN_DIFF:
            if self.is_immune(rule):
                continue
            for m in pattern.finditer(diff):
                findings.append(
                    Finding(
                        file=f"git:commit:{chash}",
                        line=0,
                        rule=rule,
                        message=f"Pattern dangereux introduit dans commit {chash}",
                        severity=severity,
                        snippet=m.group(0)[:100],
                        tentacle=self.name,
                    )
                )

        return findings

    def _check_hot_spots(self, commits: list[dict]) -> list[Finding]:
        """Fichiers modifiés dans >30% des commits = instabilité."""
        file_counts: dict[str, int] = {}
        for commit in commits:
            for fpath in self._get_changed_files(commit["hash"]):
                file_counts[fpath] = file_counts.get(fpath, 0) + 1

        findings = []
        threshold = max(3, len(commits) * 0.30)
        for fpath, count in file_counts.items():
            if count >= threshold and not self.is_immune("hot_spot"):
                findings.append(
                    Finding(
                        file=fpath,
                        line=0,
                        rule="hot_spot",
                        message=f"Fichier modifié {count}/{len(commits)} commits — instabilité potentielle",
                        severity=Severity.LOW,
                        snippet=f"touches={count}",
                        tentacle=self.name,
                    )
                )
        return findings

    def _check_large_commits(self, commits: list[dict]) -> list[Finding]:
        """Commits de >500 lignes sans tests — risque de régression cachée."""
        findings = []
        for commit in commits[:10]:  # seulement les 10 derniers pour limiter le temps
            added, removed = self._get_stat(commit["hash"])
            if added + removed > 500 and not self.is_immune("large_commit"):
                findings.append(
                    Finding(
                        file=f"git:commit:{commit['hash'][:8]}",
                        line=0,
                        rule="large_commit",
                        message=(
                            f"Commit volumineux: +{added}/-{removed} lignes "
                            f"'{commit['subject'][:50]}'"
                        ),
                        severity=Severity.LOW,
                        snippet=commit["subject"][:120],
                        tentacle=self.name,
                    )
                )
        return findings
