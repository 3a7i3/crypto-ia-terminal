"""
warmup_report.py — Rapport de démarrage (P10)

Génère un rapport structuré de la session de warmup :
  - historique des transitions
  - métriques clés à chaque état
  - résultats des invariants
  - verdict final (LIVE_READY / FAILED)
  - durée totale et bottlenecks

Persisté dans databases/cold_start_reports/report_<ts>.json
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cold_start.warmup_metrics import WarmupMetrics
from cold_start.warmup_signer import sign_report, verify_report
from cold_start.warmup_state_machine import WarmupState
from observability.json_logger import get_logger

_log = get_logger("cold_start.warmup_report")


@dataclass
class WarmupReport:
    """Rapport complet d'une session de warmup."""

    session_id: str
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    final_state: WarmupState = WarmupState.BOOTING

    # Transitions tracées
    state_transitions: list[dict] = field(default_factory=list)

    # Invariants par état
    invariant_results: dict[str, dict] = field(default_factory=dict)

    # Métriques finales
    final_metrics: Optional[WarmupMetrics] = None

    # Contexte
    scenario_id: Optional[str] = None  # si lancé depuis un scénario de test
    failure_reason: str = ""

    # ── API ──────────────────────────────────────────────────────────────────

    @property
    def duration_s(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at

    @property
    def succeeded(self) -> bool:
        return self.final_state == WarmupState.LIVE_READY

    def record_transition(
        self,
        from_state: WarmupState,
        to_state: WarmupState,
        confidence: float,
        metrics_snapshot: Optional[dict] = None,
    ) -> None:
        self.state_transitions.append(
            {
                "from": from_state.name,
                "to": to_state.name,
                "at": round(time.time(), 3),
                "confidence": round(confidence, 3),
                "metrics": metrics_snapshot or {},
            }
        )

    def record_invariants(self, state_name: str, summary: dict) -> None:
        self.invariant_results[state_name] = summary

    def finalize(
        self,
        final_state: WarmupState,
        final_metrics: Optional[WarmupMetrics] = None,
        failure_reason: str = "",
    ) -> None:
        self.finished_at = time.time()
        self.final_state = final_state
        self.final_metrics = final_metrics
        self.failure_reason = failure_reason
        _log.info(
            "[WarmupReport] session=%s état=%s durée=%.1fs score=%.3f",
            self.session_id,
            final_state.name,
            self.duration_s,
            final_metrics.warmup_score if final_metrics else 0.0,
        )

    def bottleneck_state(self) -> Optional[str]:
        """L'état où le système a passé le plus de temps."""
        if not self.state_transitions:
            return None
        durations: dict[str, float] = {}
        for i, t in enumerate(self.state_transitions):
            state = t["from"]
            if i + 1 < len(self.state_transitions):
                dur = self.state_transitions[i + 1]["at"] - t["at"]
            else:
                dur = time.time() - t["at"]
            durations[state] = durations.get(state, 0.0) + dur
        return max(durations, key=durations.get)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at": round(self.started_at, 3),
            "finished_at": round(self.finished_at, 3) if self.finished_at else None,
            "duration_s": round(self.duration_s, 1),
            "final_state": self.final_state.name,
            "succeeded": self.succeeded,
            "failure_reason": self.failure_reason,
            "bottleneck": self.bottleneck_state(),
            "state_transitions": self.state_transitions,
            "invariant_results": self.invariant_results,
            "final_metrics": (
                self.final_metrics.to_dict() if self.final_metrics else None
            ),
            "scenario_id": self.scenario_id,
        }

    def to_signed_dict(self) -> dict:
        """Retourne le rapport avec signature HMAC (champ 'hmac_signature')."""
        return sign_report(self.to_dict())

    def is_signature_valid(self, signed_dict: dict) -> bool:
        """Vérifie l'intégrité d'un rapport signé."""
        return verify_report(signed_dict)

    def save(self) -> Path:
        """Persiste le rapport signé sur disque. Retourne le chemin.

        Le répertoire est résolu à l'appel (pas au chargement du module)
        via COLD_START_REPORT_DIR, pour que monkeypatch.setenv fonctionne
        réellement dans les tests — un défaut lié à l'import ne réagit
        jamais à un changement d'env var fait après coup.
        """
        report_dir = Path(
            os.getenv("COLD_START_REPORT_DIR", "databases/cold_start_reports")
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = int(self.started_at)
        path = report_dir / f"report_{ts}_{self.session_id[:8]}.json"
        try:
            signed = self.to_signed_dict()
            path.write_text(
                json.dumps(signed, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _log.info("[WarmupReport] sauvegardé (signé): %s", path)
        except Exception as exc:
            _log.warning("[WarmupReport] sauvegarde échouée: %s", exc)
        return path

    def archive_to_black_box(self, black_box_path: Optional[str] = None) -> None:
        """Archive le verdict de warmup dans la BlackBox (append-only).

        Le chemin est résolu à l'appel (pas au chargement du module) via
        BLACK_BOX_PATH, pour que monkeypatch.setenv fonctionne réellement
        dans les tests — un défaut lié à l'import ne réagit jamais à un
        changement d'env var fait après coup.
        """
        bb = Path(
            black_box_path or os.getenv("BLACK_BOX_PATH", "databases/black_box.jsonl")
        )
        try:
            bb.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "event": "WARMUP_COMPLETE",
                "session_id": self.session_id,
                "scenario_id": self.scenario_id,
                "final_state": self.final_state.name,
                "succeeded": self.succeeded,
                "duration_s": round(self.duration_s, 1),
                "warmup_score": (
                    round(self.final_metrics.warmup_score, 4)
                    if self.final_metrics
                    else None
                ),
                "failure_reason": self.failure_reason,
                "ts": round(time.time(), 3),
            }
            with open(bb, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            _log.warning("[WarmupReport] archivage BlackBox échoué: %s", exc)

    def print_summary(self) -> str:
        """Résumé humain lisible."""
        lines = [
            f"═══ Cold Start Report ══════════════════",
            f"Session  : {self.session_id}",
            f"Durée    : {self.duration_s:.1f}s",
            "Résultat : "
            + ("✅ LIVE_READY" if self.succeeded else "❌ " + self.final_state.name),
        ]
        if self.final_metrics:
            m = self.final_metrics
            lines += [
                f"Score    : {m.warmup_score:.3f} (seuil 0.85)",
                f"Données  : {m.symbols_ready}/{m.symbols_total} symboles",
                f"Régime   : {m.regime_stability:.2f}",
                f"Shadow   : {m.shadow_cycles_completed} cycles",
            ]
        if self.failure_reason:
            lines.append(f"Échec    : {self.failure_reason}")
        if bn := self.bottleneck_state():
            lines.append(f"Bottleneck: {bn}")
        lines.append("════════════════════════════════════════")
        return "\n".join(lines)
