"""Modèles de données pour les incidents de la Pieuvre Géante."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentType(Enum):
    CRASH = "crash"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ORDER_FAILURE = "order_failure"
    DATA_STALE = "data_stale"
    CODE_VULN = "code_vuln"
    MODULE_FAILURE = "module_failure"
    GIT_ANOMALY = "git_anomaly"
    RESILIENCE = "resilience"


# Temps de récupération proportionnel à la sévérité
RECOVERY_SECONDS: dict[Severity, float] = {
    Severity.LOW: 60.0,
    Severity.MEDIUM: 300.0,
    Severity.HIGH: 900.0,
    Severity.CRITICAL: 1800.0,
}

# Gain de force après chaque incident résolu
STRENGTH_GAIN: dict[Severity, float] = {
    Severity.LOW: 0.02,
    Severity.MEDIUM: 0.05,
    Severity.HIGH: 0.10,
    Severity.CRITICAL: 0.20,
}

_SEV_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


@dataclass
class Finding:
    """Une vulnérabilité ou anomalie détectée par un tentacule."""

    file: str
    line: int
    rule: str
    message: str
    severity: Severity
    snippet: str = ""
    tentacle: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity.value,
            "snippet": self.snippet,
            "tentacle": self.tentacle,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Finding:
        return cls(
            file=d.get("file", ""),
            line=d.get("line", 0),
            rule=d.get("rule", ""),
            message=d.get("message", ""),
            severity=Severity(d.get("severity", "low")),
            snippet=d.get("snippet", ""),
            tentacle=d.get("tentacle", ""),
        )


@dataclass
class Incident:
    """Un incident tracé par la Pieuvre — de la détection à la guérison."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: IncidentType = IncidentType.SECURITY
    severity: Severity = Severity.LOW
    module: str = "unknown"
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    recovery_seconds: float = 0.0
    strength_gained: float = 0.0
    lessons: list[str] = field(default_factory=list)
    immunity_patterns: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def required_recovery(self) -> float:
        return RECOVERY_SECONDS[self.severity]

    def strength_reward(self) -> float:
        return STRENGTH_GAIN[self.severity]

    def resolve(self) -> None:
        self.resolved_at = datetime.now()
        if self.resolved_at and self.timestamp:
            self.recovery_seconds = (self.resolved_at - self.timestamp).total_seconds()
        self.strength_gained = self.strength_reward()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "module": self.module,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "recovery_seconds": self.recovery_seconds,
            "strength_gained": self.strength_gained,
            "lessons": self.lessons,
            "immunity_patterns": self.immunity_patterns,
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Incident:
        inc = cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            type=IncidentType(d.get("type", "security")),
            severity=Severity(d.get("severity", "low")),
            module=d.get("module", "unknown"),
            message=d.get("message", ""),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            recovery_seconds=d.get("recovery_seconds", 0.0),
            strength_gained=d.get("strength_gained", 0.0),
            lessons=d.get("lessons", []),
            immunity_patterns=d.get("immunity_patterns", []),
            findings=[Finding.from_dict(f) for f in d.get("findings", [])],
        )
        if d.get("resolved_at"):
            inc.resolved_at = datetime.fromisoformat(d["resolved_at"])
        return inc
