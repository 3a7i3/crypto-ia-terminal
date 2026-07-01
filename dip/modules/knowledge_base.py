"""
dip/modules/knowledge_base.py — D09 Decision Knowledge Base.

Accumule les patterns et règles empiriques découverts par analyse des décisions.
Chaque pattern nécessite >= 50 observations pour être valide.
Les règles ont une confiance > 0.6 et un lift > 1.2.
Détecte les dérives (z-score > 3 sigma sur métriques glissantes).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from dip.core.store import DIPStore
from dip.core.types import KnowledgeType, TrendDirection, compute_hash, now_us

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation

_MIN_PATTERN_SUPPORT = 50  # minimum d'observations par pattern
_MIN_RULE_CONFIDENCE = 0.60
_MIN_RULE_LIFT = 1.20
_DRIFT_ZSCORE_THRESHOLD = 3.0


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class KnowledgeEntry:
    entry_id: str
    entry_type: KnowledgeType
    description: str
    frequency: float
    sample_size: int
    confidence: float
    layers_involved: tuple[str, ...]
    symbols: tuple[str, ...]
    regimes: tuple[str, ...]
    first_seen_us: int
    last_seen_us: int
    trend: TrendDirection
    hash: str


@dataclass(frozen=True)
class KnowledgeRule:
    rule_id: str
    condition: str
    conclusion: str
    confidence: float
    support: int
    lift: float
    conviction: (
        float  # P(condition) * P(not conclusion) / P(condition and not conclusion)
    )


@dataclass(frozen=True)
class PatternCluster:
    cluster_id: str
    pattern_type: str
    entries: tuple[KnowledgeEntry, ...]
    size: int


@dataclass(frozen=True)
class DriftReport:
    metric: str
    window_hours: int
    drift_detected: bool
    current_value: float
    historical_value: float
    z_score: float
    severity: str


@dataclass(frozen=True)
class SimilarDecision:
    packet_id: str
    symbol: str
    direction: str
    regime: str
    status: str
    similarity_score: float


@dataclass(frozen=True)
class KnowledgeSummary:
    total_entries: int
    total_rules: int
    total_patterns: int
    top_rejection_cause: str
    top_rejection_regime: str
    overall_approval_rate: float
    computed_at_us: int


# ── Pattern extraction ────────────────────────────────────────────────────────


class KnowledgeExtractor:
    """Extrait et accumule les patterns depuis les décisions indexées."""

    def __init__(self, store: DIPStore) -> None:
        self._store = store
        self._lock = threading.Lock()

    def update(self, obs: "DecisionObservation") -> None:
        """Met à jour la KB après chaque observation. Lightweight."""
        # On ne calcule pas les patterns à chaque observation —
        # on laisse la méthode compute() faire le travail en batch
        pass

    def compute_patterns(self, limit: int = 10_000) -> list[KnowledgeEntry]:
        """
        Calcule les patterns depuis les données stockées.
        Appelé périodiquement (ex: quotidien), pas après chaque observation.
        """
        rows = self._store.get_decisions(limit=limit)
        patterns: list[KnowledgeEntry] = []

        # Pattern: taux de rejet par (symbole, couche bloquante)
        combos: dict[tuple[str, str], dict] = {}
        for r in rows:
            sym = r.get("symbol", "?")
            layer = r.get("root_cause_layer")
            regime = r.get("regime", "?")
            status = r.get("status", "")
            if not sym or not layer:
                continue
            key = (sym, layer)
            if key not in combos:
                combos[key] = {
                    "total": 0,
                    "rejected": 0,
                    "regimes": set(),
                    "first": r.get("created_at_us", 0),
                }
            combos[key]["total"] += 1
            if status == "REJECTED":
                combos[key]["rejected"] += 1
            combos[key]["regimes"].add(regime)
            combos[key]["last"] = r.get("created_at_us", 0)

        for (sym, layer), data in combos.items():
            if data["total"] < _MIN_PATTERN_SUPPORT:
                continue
            freq = data["rejected"] / data["total"]
            if freq < 0.3:  # pattern de rejet significatif si > 30%
                continue

            entry_id = f"pat_{sym}_{layer}_{now_us()}"
            content = {"sym": sym, "layer": layer, "freq": freq}
            patterns.append(
                KnowledgeEntry(
                    entry_id=entry_id,
                    entry_type=KnowledgeType.REJECTION_CLUSTER,
                    description=f"{layer} rejette {freq:.0%} des trades {sym} (n={data['total']})",
                    frequency=round(freq, 4),
                    sample_size=data["total"],
                    confidence=min(0.95, 0.7 + data["total"] * 0.001),
                    layers_involved=(layer,),
                    symbols=(sym,),
                    regimes=tuple(data["regimes"]),
                    first_seen_us=data.get("first", 0),
                    last_seen_us=data.get("last", 0),
                    trend=TrendDirection.STABLE,
                    hash=compute_hash(content),
                )
            )

        return patterns

    def compute_rules(self, limit: int = 10_000) -> list[KnowledgeRule]:
        """Association mining simple: if regime=X and symbol=Y then rejected_by=Z."""
        rows = self._store.get_decisions(limit=limit)
        total = len(rows)
        if total < 100:
            return []

        rules: list[KnowledgeRule] = []

        # P(conclusion=REJECTED)
        p_rejected = sum(1 for r in rows if r.get("status") == "REJECTED") / total

        # Pour chaque (regime, symbol) → taux de rejet
        combos: dict[tuple[str, str], dict] = {}
        for r in rows:
            regime = r.get("regime", "?")
            sym = r.get("symbol", "?")
            status = r.get("status", "")
            key = (regime, sym)
            if key not in combos:
                combos[key] = {"total": 0, "rejected": 0, "layers": {}}
            combos[key]["total"] += 1
            if status == "REJECTED":
                combos[key]["rejected"] += 1
                layer = r.get("root_cause_layer", "?")
                combos[key]["layers"][layer] = combos[key]["layers"].get(layer, 0) + 1

        for (regime, sym), data in combos.items():
            if data["total"] < _MIN_PATTERN_SUPPORT:
                continue
            conf = data["rejected"] / data["total"]
            if conf < _MIN_RULE_CONFIDENCE:
                continue
            p_cond = data["total"] / total
            lift = conf / p_rejected if p_rejected > 0 else 1.0
            if lift < _MIN_RULE_LIFT:
                continue

            # Trouver la couche la plus fréquente
            top_layer = (
                max(data["layers"].items(), key=lambda x: x[1])[0]
                if data["layers"]
                else "unknown"
            )

            # Conviction: p_cond * (1 - p_rejected) / (p_cond - conf * p_cond)
            denom = max(0.001, p_cond * (1 - p_rejected))
            conviction = (p_cond * (1 - p_rejected)) / max(
                0.001, p_cond - conf * p_cond
            )
            conviction = round(min(10.0, conviction), 3)

            rules.append(
                KnowledgeRule(
                    rule_id=f"rule_{regime}_{sym}_{now_us()}",
                    condition=f"regime={regime} AND symbol={sym}",
                    conclusion=f"REJECTED by {top_layer}",
                    confidence=round(conf, 4),
                    support=data["total"],
                    lift=round(lift, 3),
                    conviction=conviction,
                )
            )

        return sorted(rules, key=lambda r: r.confidence, reverse=True)


# ── Drift Detector ─────────────────────────────────────────────────────────────


class DriftDetector:

    def __init__(self, store: DIPStore) -> None:
        self._store = store

    def detect(self, metric: str, window_hours: int = 168) -> DriftReport:
        """
        Compare la valeur actuelle d'une métrique à sa valeur historique.
        metric: ex "rejection_rate", "arbitrator_rate", etc.
        """
        now = now_us()
        recent_start = now - window_hours * 3_600_000_000
        historical_start = now - window_hours * 3_600_000_000 * 4  # 4x la fenêtre

        recent_rows = self._store.get_decisions(start_us=recent_start, limit=10_000)
        historical_rows = self._store.get_decisions(
            start_us=historical_start, end_us=recent_start, limit=50_000
        )

        current = self._compute_metric(metric, recent_rows)
        historical = self._compute_metric(metric, historical_rows)

        if historical == 0:
            z = 0.0
        else:
            # std estimé à 15% de la valeur historique
            std = max(0.01, historical * 0.15)
            z = (current - historical) / std

        drift_detected = abs(z) > _DRIFT_ZSCORE_THRESHOLD

        return DriftReport(
            metric=metric,
            window_hours=window_hours,
            drift_detected=drift_detected,
            current_value=round(current, 4),
            historical_value=round(historical, 4),
            z_score=round(z, 2),
            severity=(
                "CRITICAL" if abs(z) > 5 else ("WARNING" if drift_detected else "OK")
            ),
        )

    def _compute_metric(self, metric: str, rows: list[dict]) -> float:
        if not rows:
            return 0.0
        total = len(rows)
        if metric == "rejection_rate":
            return sum(1 for r in rows if r.get("status") == "REJECTED") / total
        elif metric.endswith("_rate"):
            layer = metric.replace("_rate", "").replace("_", " ").title()
            return sum(1 for r in rows if r.get("root_cause_layer") == layer) / total
        return 0.0


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionKnowledgeBase:
    """D09 — Base de connaissances accumulée."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._extractor = KnowledgeExtractor(self._store)
        self._drift = DriftDetector(self._store)
        self._lock = threading.Lock()
        self._last_compute_us = 0
        self._compute_interval_us = 3_600_000_000  # 1h

    def on_observation(self, obs: "DecisionObservation") -> None:
        self._extractor.update(obs)
        # Recalcul périodique (pas après chaque observation)
        if now_us() - self._last_compute_us > self._compute_interval_us:
            self._refresh()

    def query_patterns(
        self,
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
        layer: Optional[str] = None,
    ) -> list[KnowledgeEntry]:
        rows = self._store.get_knowledge(entry_type="REJECTION_CLUSTER")
        entries = [self._row_to_entry(r) for r in rows if r]
        if symbol:
            entries = [e for e in entries if symbol in e.symbols]
        if regime:
            entries = [e for e in entries if regime in e.regimes]
        if layer:
            entries = [e for e in entries if layer in e.layers_involved]
        return entries

    def get_rules(self, layer: Optional[str] = None) -> list[KnowledgeRule]:
        # Les règles sont calculées en mémoire depuis le store
        rules = self._extractor.compute_rules(limit=5_000)
        if layer:
            rules = [r for r in rules if layer in r.conclusion]
        return rules

    def find_similar_decisions(
        self, packet_id: str, top_k: int = 5
    ) -> list[SimilarDecision]:
        row = self._store.get_decision(packet_id)
        if not row:
            return []
        sym = row.get("symbol", "?")
        status = row.get("status", "?")
        regime = row.get("regime", "?")

        rows = self._store.get_decisions(symbol=sym, status=status, limit=100)
        similars = []
        for r in rows:
            if r["packet_id"] == packet_id:
                continue
            # Similarité simple: même symbole+statut+régime
            sim_score = 0.5
            if r.get("regime") == regime:
                sim_score += 0.3
            if r.get("root_cause_layer") == row.get("root_cause_layer"):
                sim_score += 0.2
            similars.append(
                SimilarDecision(
                    packet_id=r["packet_id"],
                    symbol=r.get("symbol", "?"),
                    direction=r.get("direction", "?"),
                    regime=r.get("regime", "?"),
                    status=r.get("status", "?"),
                    similarity_score=round(min(1.0, sim_score), 3),
                )
            )

        return sorted(similars, key=lambda s: s.similarity_score, reverse=True)[:top_k]

    def get_knowledge_summary(self) -> KnowledgeSummary:
        rows = self._store.get_decisions(limit=10_000)
        total = len(rows)
        approved = sum(1 for r in rows if r.get("status") == "APPROVED")

        # Cause de rejet la plus fréquente
        layers: dict[str, int] = {}
        regimes: dict[str, int] = {}
        for r in rows:
            if r.get("status") == "REJECTED":
                lyr = r.get("root_cause_layer", "?")
                layers[lyr] = layers.get(lyr, 0) + 1
                rg = r.get("regime", "?")
                regimes[rg] = regimes.get(rg, 0) + 1

        top_layer = max(layers.items(), key=lambda x: x[1])[0] if layers else "N/A"
        top_regime = max(regimes.items(), key=lambda x: x[1])[0] if regimes else "N/A"

        patterns = self._store.get_knowledge()

        return KnowledgeSummary(
            total_entries=len(patterns),
            total_rules=len(self._extractor.compute_rules(limit=1_000)),
            total_patterns=len(patterns),
            top_rejection_cause=top_layer,
            top_rejection_regime=top_regime,
            overall_approval_rate=round(approved / total, 4) if total > 0 else 0.0,
            computed_at_us=now_us(),
        )

    def detect_drift(self, metric: str, window_hours: int = 168) -> DriftReport:
        return self._drift.detect(metric, window_hours)

    def _refresh(self) -> None:
        with self._lock:
            if now_us() - self._last_compute_us < self._compute_interval_us:
                return
            patterns = self._extractor.compute_patterns()
            for p in patterns:
                self._store.upsert_knowledge(
                    {
                        "entry_id": p.entry_id,
                        "entry_type": p.entry_type.value,
                        "description": p.description,
                        "frequency": p.frequency,
                        "sample_size": p.sample_size,
                        "confidence": p.confidence,
                        "layers_involved": json.dumps(list(p.layers_involved)),
                        "symbols": json.dumps(list(p.symbols)),
                        "regimes": json.dumps(list(p.regimes)),
                        "first_seen_us": p.first_seen_us,
                        "last_seen_us": p.last_seen_us,
                        "trend": p.trend.value,
                    }
                )
            self._last_compute_us = now_us()

    def _row_to_entry(self, r: dict) -> Optional[KnowledgeEntry]:
        try:
            return KnowledgeEntry(
                entry_id=r["entry_id"],
                entry_type=KnowledgeType(r["entry_type"]),
                description=r["description"],
                frequency=r["frequency"],
                sample_size=r["sample_size"],
                confidence=r["confidence"],
                layers_involved=tuple(json.loads(r.get("layers_involved", "[]"))),
                symbols=tuple(json.loads(r.get("symbols", "[]"))),
                regimes=tuple(json.loads(r.get("regimes", "[]"))),
                first_seen_us=r["first_seen_us"],
                last_seen_us=r["last_seen_us"],
                trend=TrendDirection(r.get("trend", "UNKNOWN")),
                hash=r.get("hash", ""),
            )
        except Exception:
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionKnowledgeBase] = None
_engine_lock = threading.Lock()


def get_knowledge_base() -> DecisionKnowledgeBase:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionKnowledgeBase()
    return _engine
