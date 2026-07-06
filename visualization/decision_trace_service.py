"""DecisionTraceService — logique métier unique pour l'audit trail décisionnel.

Lit databases/rejections/rejections_YYYY-MM-DD.jsonl (RejectionStore) et
reconstruit, pour chaque signal évalué, la chaîne causale couche par couche
(Signal → Gate → MetaStrategy → Conviction → Portfolio → ExecOverride →
MistakeMemory → ThreatRadar → Arbitrator → DecisionPacket G8).

Point d'entrée unique consommé par deux clients :
  - tools/decision_trace.py       (CLI, affichage texte)
  - visualization/api/decision_api.py (SDOS Data API, JSON)

Aucune écriture. Lecture seule des sources canoniques (ADR-0007 — passivité).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
_REJECTIONS_DIR = _ROOT / "databases" / "rejections"

LAYER_LABELS: dict[str, str] = {
    "authority": "Authority (kernel)",
    "gate": "Gate (score/qualité)",
    "meta_strategy": "MetaStrategy (personnalité)",
    "conviction": "Conviction (niveau confiance)",
    "no_trade": "No-Trade Layer",
    "portfolio": "Portfolio Brain",
    "mistake_memory": "MistakeMemory",
    "executive_override": "Executive Override (drawdown/cap)",
    "threat_radar": "ThreatRadar",
    "arbitrator": "DecisionArbitrator",
    "decision_packet": "DecisionPacket (G8 guard)",
    "protection": "Protection (stop-loss/risk)",
}


def label_for(blocker: str) -> str:
    """Résout un identifiant de bloqueur brut (ex: 'meta_strategy(score<66)') en libellé lisible."""
    key = blocker.split("(")[0]
    label = LAYER_LABELS.get(key, blocker)
    if "(" in blocker:
        return f"{label} {blocker[len(key):]}"
    return label


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Types ──────────────────────────────────────────────────────────────────────


@dataclass
class TraceStep:
    """Un maillon de la chaîne causale — une couche de décision évaluée."""

    step: int
    name: str
    status: Optional[bool]   # True=PASS, False=BLOCK, None=non évalué
    detail: str


@dataclass
class DecisionTrace:
    """Trace causale complète d'une évaluation de signal (une entrée du RejectionStore)."""

    packet_id: str
    observation_id: str
    cycle: int
    symbol: str
    side: str
    score: float
    regime: str
    personality: str
    ts_iso: Optional[str]
    steps: list[TraceStep]
    first_blocker: Optional[str]
    all_blockers: list[str]
    trade_allowed: bool
    verdict: str
    base_size_usd: float

    @property
    def first_blocker_label(self) -> Optional[str]:
        return label_for(self.first_blocker) if self.first_blocker else None


@dataclass
class RejectionEvent:
    """Une ligne condensée pour une vue liste (Reject Analyzer / Timeline)."""

    packet_id: str
    ts_iso: Optional[str]
    cycle: int
    symbol: str
    side: str
    regime: str
    trade_allowed: bool
    first_blocker: Optional[str]
    first_blocker_label: Optional[str]


@dataclass
class RejectionsSnapshot:
    """Vue agrégée du RejectionStore — alimente le panneau Reject Analyzer."""

    ts: datetime
    days_covered: list[str]
    n_entries: int
    n_unique: int
    by_layer: dict[str, int]
    by_layer_pct: dict[str, float]
    by_regime: dict[str, int]
    by_personality: dict[str, int]
    recent: list[RejectionEvent] = field(default_factory=list)


# ── Service ────────────────────────────────────────────────────────────────────


class DecisionTraceService:
    """Source de vérité unique pour l'audit trail décisionnel (RejectionStore)."""

    def __init__(self, rejections_dir: Optional[Path] = None):
        self._dir = rejections_dir or _REJECTIONS_DIR

    def path_for_date(self, day: date) -> Path:
        return self._dir / f"rejections_{day}.jsonl"

    @staticmethod
    def _parse_line(raw: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads(raw.strip())
        except Exception:
            return None

    @staticmethod
    def _dedup(entries: list[dict]) -> list[dict]:
        """Supprime les doublons (même packet_id) — le store peut enregistrer 2×."""
        seen: set[str] = set()
        out: list[dict] = []
        for e in entries:
            pid = e.get("packet_id", "")
            if pid not in seen:
                seen.add(pid)
                out.append(e)
        return out

    def load_entries(
        self,
        day: Optional[date] = None,
        file: Optional[Path] = None,
        symbol: Optional[str] = None,
        cycle: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Charge et filtre les entrées d'un seul fichier JSONL (un jour)."""
        jsonl_path = file if file else self.path_for_date(day or date.today())
        if not jsonl_path.exists():
            return []

        sym_filter = symbol.upper() if symbol else None
        entries: list[dict] = []
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                e = self._parse_line(line)
                if e is None:
                    continue
                if sym_filter:
                    sym_clean = e.get("symbol", "").replace("/USDT", "").upper()
                    if sym_clean != sym_filter:
                        continue
                if cycle is not None and e.get("cycle") != cycle:
                    continue
                entries.append(e)

        return self._dedup(entries)

    def load_recent_entries(
        self,
        days: int = 1,
        symbol: Optional[str] = None,
        cycle: Optional[int] = None,
        end_day: Optional[date] = None,
    ) -> list[dict[str, Any]]:
        """Charge et concatène les entrées des `days` derniers jours (jusqu'à `end_day` inclus)."""
        end = end_day or date.today()
        out: list[dict] = []
        for i in range(days):
            out.extend(self.load_entries(day=end - timedelta(days=i), symbol=symbol, cycle=cycle))
        return self._dedup(out)

    # -- Trace causale par entrée -----------------------------------------------

    def build_trace(self, entry: dict[str, Any]) -> DecisionTrace:
        """Reconstruit la chaîne causale couche par couche pour une entrée du RejectionStore."""
        first_blocker = entry.get("first_blocker")
        all_blockers: list[str] = entry.get("all_blockers") or []

        def blocked_by(layer_key: str) -> bool:
            return layer_key in (first_blocker or "")

        gate_failed = entry.get("gate_failed") or []
        gate_ok = len(gate_failed) == 0

        meta_reason = entry.get("meta_reason", "OK")
        meta_ok = meta_reason == "OK" or not blocked_by("meta_strategy")

        conv_level = entry.get("conviction_level")
        conv_blocked = blocked_by("conviction") or conv_level == "SKIP"

        pb_reason = entry.get("portfolio_reason")
        eo_level = entry.get("override_level")
        mm_reason = entry.get("mistake_reason")
        radar_level = entry.get("radar_level")
        arb_decision = entry.get("arbitration_decision")
        dp_blocked = any("decision_packet" in b for b in all_blockers)
        dp_detail = next((b for b in all_blockers if "decision_packet" in b), "non évalué")

        steps = [
            TraceStep(1, "Signal", True,
                      f"score={entry.get('score', 0)} side={entry.get('side', '?')} "
                      f"regime={entry.get('regime', '?')}"),
            TraceStep(2, "Gate (seuil de score)", gate_ok,
                      f"failed={gate_failed}" if gate_failed else "toutes règles OK"),
            TraceStep(3, f"MetaStrategy ({entry.get('personality_name', 'unknown')})", meta_ok, meta_reason),
            TraceStep(4, "Conviction Engine", None if not conv_level else not conv_blocked,
                      f"level={conv_level} score={entry.get('conviction_score')}" if conv_level else "non évalué"),
            TraceStep(5, "Portfolio Brain", None if not pb_reason else not blocked_by("portfolio"),
                      pb_reason or "non évalué"),
            TraceStep(6, "Executive Override", None if not eo_level else not blocked_by("executive_override"),
                      f"level={eo_level} reason={entry.get('override_reason')}" if eo_level else "non évalué"),
            TraceStep(7, "MistakeMemory", None if not mm_reason else not blocked_by("mistake_memory"),
                      mm_reason or "non évalué"),
            TraceStep(8, "ThreatRadar", None if not radar_level else not blocked_by("threat_radar"),
                      f"level={radar_level} threats={entry.get('radar_threat_count', 0)}"),
            TraceStep(9, "DecisionArbitrator", None if not arb_decision else not blocked_by("arbitrator"),
                      arb_decision or "non évalué"),
            TraceStep(10, "DecisionPacket G8 guard", None if not dp_blocked else False, dp_detail),
        ]

        return DecisionTrace(
            packet_id=entry.get("packet_id", ""),
            observation_id=entry.get("observation_id", ""),
            cycle=entry.get("cycle", 0),
            symbol=entry.get("symbol", "?"),
            side=entry.get("side", "?"),
            score=entry.get("score", 0.0),
            regime=entry.get("regime", "?"),
            personality=entry.get("personality_name", "unknown"),
            ts_iso=entry.get("ts_iso"),
            steps=steps,
            first_blocker=first_blocker,
            all_blockers=all_blockers,
            trade_allowed=entry.get("trade_allowed", False),
            verdict=entry.get("human_verdict", "?"),
            base_size_usd=entry.get("base_size_usd", 0.0),
        )

    def find_by_packet_id(
        self, packet_id: str, days: int = 7, end_day: Optional[date] = None,
    ) -> Optional[dict[str, Any]]:
        """Recherche une entrée par packet_id sur les `days` derniers jours."""
        for entry in self.load_recent_entries(days=days, end_day=end_day):
            if entry.get("packet_id") == packet_id:
                return entry
        return None

    def trace(self, packet_id: str, days: int = 7, end_day: Optional[date] = None) -> Optional[DecisionTrace]:
        """Combine find_by_packet_id + build_trace — trace causale d'un packet donné."""
        entry = self.find_by_packet_id(packet_id, days=days, end_day=end_day)
        return self.build_trace(entry) if entry is not None else None

    # -- Agrégats -----------------------------------------------------------------

    def statistics(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Compte les bloqueurs, régimes et personnalités sur un ensemble d'entrées."""
        by_layer: Counter = Counter()
        by_regime: Counter = Counter()
        by_personality: Counter = Counter()

        for e in entries:
            for b in e.get("all_blockers") or []:
                by_layer[b.split("(")[0]] += 1
            by_regime[e.get("regime", "?")] += 1
            by_personality[e.get("personality_name", "unknown")] += 1

        n = len(entries)
        by_layer_pct = {k: round(100 * v / n, 1) for k, v in by_layer.items()} if n else {}

        return {
            "n_entries": n,
            "n_unique": len({e.get("packet_id", "") for e in entries}),
            "by_layer": dict(by_layer),
            "by_layer_pct": by_layer_pct,
            "by_regime": dict(by_regime),
            "by_personality": dict(by_personality),
        }

    def timeline(self, days: int = 1, limit: int = 50, end_day: Optional[date] = None) -> list[RejectionEvent]:
        """Les événements les plus récents du RejectionStore, du plus récent au plus ancien."""
        entries = self.load_recent_entries(days=days, end_day=end_day)
        entries.sort(key=lambda e: e.get("ts", 0), reverse=True)
        return [self._to_event(e) for e in entries[:limit]]

    def rejections(self, days: int = 1, limit: int = 20, end_day: Optional[date] = None) -> RejectionsSnapshot:
        """Vue combinée agrégats + événements récents — alimente le panneau Reject Analyzer."""
        end = end_day or date.today()
        entries = self.load_recent_entries(days=days, end_day=end)
        stats = self.statistics(entries)
        recent = self.timeline(days=days, limit=limit, end_day=end)

        return RejectionsSnapshot(
            ts=datetime.now(),
            days_covered=[str(end - timedelta(days=i)) for i in range(days)],
            n_entries=stats["n_entries"],
            n_unique=stats["n_unique"],
            by_layer=stats["by_layer"],
            by_layer_pct=stats["by_layer_pct"],
            by_regime=stats["by_regime"],
            by_personality=stats["by_personality"],
            recent=recent,
        )

    @staticmethod
    def _to_event(entry: dict[str, Any]) -> RejectionEvent:
        first_blocker = entry.get("first_blocker")
        return RejectionEvent(
            packet_id=entry.get("packet_id", ""),
            ts_iso=entry.get("ts_iso"),
            cycle=entry.get("cycle", 0),
            symbol=entry.get("symbol", "?"),
            side=entry.get("side", "?"),
            regime=entry.get("regime", "?"),
            trade_allowed=entry.get("trade_allowed", False),
            first_blocker=first_blocker,
            first_blocker_label=label_for(first_blocker) if first_blocker else None,
        )
