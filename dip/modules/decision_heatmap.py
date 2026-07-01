"""
dip/modules/decision_heatmap.py — D05 Decision Heatmap Engine.

Matrices de chaleur montrant les patterns d'approbation/rejet
selon deux axes (symbole × couche, régime × couche, heure × couche).

Seuils: hot spot > 80% rejet, cold spot < 10% rejet.
Minimum 10 décisions par cellule avant de la considérer valide.
Cache TTL 1h (régénérable).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import (
    HeatmapType,
    InsightType,
    Severity,
    TimeRange,
    TrendDirection,
    now_us,
)

# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HeatmapAxes:
    x_label: str
    x_values: tuple[str, ...]
    y_label: str
    y_values: tuple[str, ...]


@dataclass(frozen=True)
class HeatmapCell:
    x_value: str
    y_value: str
    value: float  # taux de rejet [0,1]
    count: int
    rejected: int
    approved: int
    trend: TrendDirection
    z_score: float
    is_hot_spot: bool
    is_cold_spot: bool
    is_insufficient_data: bool


@dataclass(frozen=True)
class HeatmapInsight:
    insight_type: InsightType
    description: str
    severity: Severity
    cell_x: str
    cell_y: str
    confidence: float


@dataclass(frozen=True)
class HeatmapMatrix:
    heatmap_id: str
    heatmap_type: HeatmapType
    axes: HeatmapAxes
    cells: tuple[HeatmapCell, ...]
    insights: tuple[HeatmapInsight, ...]
    generated_at_us: int
    time_range: TimeRange
    total_decisions: int


@dataclass(frozen=True)
class HeatmapComparison:
    period1: TimeRange
    period2: TimeRange
    changed_cells: tuple[tuple[str, str, float, float], ...]  # (x, y, delta, z_score)
    biggest_increase: Optional[tuple[str, str, float]]
    biggest_decrease: Optional[tuple[str, str, float]]


# ── Builder ───────────────────────────────────────────────────────────────────

_HOT_THRESHOLD = 0.80
_COLD_THRESHOLD = 0.10
_MIN_CELL_COUNT = 10

# Couches du pipeline dans l'ordre d'affichage
_LAYER_DISPLAY_NAMES = [
    "Authority",
    "MetaStrategy",
    "Gate",
    "SelfAwareness",
    "ConvictionEngine",
    "NoTradeLayer",
    "PortfolioBrain",
    "CapitalAllocation",
    "MistakeMemory",
    "ExecutiveOverride",
    "ThreatRadar",
    "Arbitrator",
]


class HeatmapBuilder:

    @staticmethod
    def build_symbol_layer(
        rows: list[dict],
        time_range: TimeRange,
    ) -> HeatmapMatrix:
        """Matrice: symbole (Y) × couche (X)."""
        symbols = sorted({r.get("symbol", "?") for r in rows if r.get("symbol")})
        layers = _LAYER_DISPLAY_NAMES

        # Agréger: pour chaque (layer, symbol), compter total + rejected
        counts: dict[tuple[str, str], list[int, int]] = {}
        for r in rows:
            sym = r.get("symbol", "?")
            rl = r.get("root_cause_layer")
            status = r.get("status", "")
            if not sym or not rl:
                continue
            key = (rl, sym)
            if key not in counts:
                counts[key] = [0, 0]  # [total, rejected]
            counts[key][0] += 1
            if status == "REJECTED":
                counts[key][1] += 1

        cells = []
        all_rates = [
            counts[k][1] / counts[k][0]
            for k in counts
            if counts[k][0] >= _MIN_CELL_COUNT
        ]
        mean_rate = sum(all_rates) / len(all_rates) if all_rates else 0.5
        std_rate = (
            (sum((r - mean_rate) ** 2 for r in all_rates) / len(all_rates)) ** 0.5
            if all_rates
            else 0.1
        )

        for layer in layers:
            for sym in symbols:
                key = (layer, sym)
                c = counts.get(key, [0, 0])
                total, rejected = c[0], c[1]
                insuff = total < _MIN_CELL_COUNT
                rate = rejected / total if total > 0 else 0.0
                z = (
                    (rate - mean_rate) / std_rate
                    if std_rate > 0 and not insuff
                    else 0.0
                )

                cells.append(
                    HeatmapCell(
                        x_value=layer,
                        y_value=sym,
                        value=round(rate, 4),
                        count=total,
                        rejected=rejected,
                        approved=total - rejected,
                        trend=TrendDirection.UNKNOWN,
                        z_score=round(z, 2),
                        is_hot_spot=rate >= _HOT_THRESHOLD and not insuff,
                        is_cold_spot=rate <= _COLD_THRESHOLD and not insuff,
                        is_insufficient_data=insuff,
                    )
                )

        insights = HeatmapBuilder._generate_insights(cells)
        heatmap_id = f"hm_symbol_layer_{now_us()}"

        return HeatmapMatrix(
            heatmap_id=heatmap_id,
            heatmap_type=HeatmapType.SYMBOL_LAYER,
            axes=HeatmapAxes(
                x_label="Layer",
                x_values=tuple(layers),
                y_label="Symbol",
                y_values=tuple(symbols),
            ),
            cells=tuple(cells),
            insights=tuple(insights),
            generated_at_us=now_us(),
            time_range=time_range,
            total_decisions=len(rows),
        )

    @staticmethod
    def build_regime_layer(
        rows: list[dict],
        time_range: TimeRange,
    ) -> HeatmapMatrix:
        """Matrice: régime (Y) × couche (X)."""
        regimes = sorted({r.get("regime", "?") for r in rows if r.get("regime")})
        layers = _LAYER_DISPLAY_NAMES

        counts: dict[tuple[str, str], list[int, int]] = {}
        for r in rows:
            regime = r.get("regime", "?")
            rl = r.get("root_cause_layer")
            status = r.get("status", "")
            if not regime or not rl:
                continue
            key = (rl, regime)
            if key not in counts:
                counts[key] = [0, 0]
            counts[key][0] += 1
            if status == "REJECTED":
                counts[key][1] += 1

        all_rates = [
            counts[k][1] / counts[k][0]
            for k in counts
            if counts[k][0] >= _MIN_CELL_COUNT
        ]
        mean_rate = sum(all_rates) / len(all_rates) if all_rates else 0.5
        std_rate = (
            (sum((r - mean_rate) ** 2 for r in all_rates) / len(all_rates)) ** 0.5
            if all_rates
            else 0.1
        )

        cells = []
        for layer in layers:
            for regime in regimes:
                key = (layer, regime)
                c = counts.get(key, [0, 0])
                total, rejected = c[0], c[1]
                insuff = total < _MIN_CELL_COUNT
                rate = rejected / total if total > 0 else 0.0
                z = (
                    (rate - mean_rate) / std_rate
                    if std_rate > 0 and not insuff
                    else 0.0
                )

                cells.append(
                    HeatmapCell(
                        x_value=layer,
                        y_value=regime,
                        value=round(rate, 4),
                        count=total,
                        rejected=rejected,
                        approved=total - rejected,
                        trend=TrendDirection.UNKNOWN,
                        z_score=round(z, 2),
                        is_hot_spot=rate >= _HOT_THRESHOLD and not insuff,
                        is_cold_spot=rate <= _COLD_THRESHOLD and not insuff,
                        is_insufficient_data=insuff,
                    )
                )

        insights = HeatmapBuilder._generate_insights(cells)

        return HeatmapMatrix(
            heatmap_id=f"hm_regime_layer_{now_us()}",
            heatmap_type=HeatmapType.REGIME_LAYER,
            axes=HeatmapAxes(
                x_label="Layer",
                x_values=tuple(layers),
                y_label="Regime",
                y_values=tuple(regimes),
            ),
            cells=tuple(cells),
            insights=tuple(insights),
            generated_at_us=now_us(),
            time_range=time_range,
            total_decisions=len(rows),
        )

    @staticmethod
    def _generate_insights(cells: list[HeatmapCell]) -> list[HeatmapInsight]:
        insights = []
        for cell in cells:
            if cell.is_hot_spot:
                insights.append(
                    HeatmapInsight(
                        insight_type=InsightType.HOT_SPOT,
                        description=(
                            f"{cell.x_value} rejette {cell.value:.0%} des trades {cell.y_value} "
                            f"({cell.rejected}/{cell.count})"
                        ),
                        severity=(
                            Severity.HIGH if cell.value > 0.90 else Severity.WARNING
                        ),
                        cell_x=cell.x_value,
                        cell_y=cell.y_value,
                        confidence=min(0.95, 0.7 + cell.count * 0.005),
                    )
                )
            elif cell.is_cold_spot:
                insights.append(
                    HeatmapInsight(
                        insight_type=InsightType.COLD_SPOT,
                        description=(
                            f"{cell.x_value} approuve {(1-cell.value):.0%} des trades {cell.y_value}"
                        ),
                        severity=Severity.INFO,
                        cell_x=cell.x_value,
                        cell_y=cell.y_value,
                        confidence=min(0.90, 0.6 + cell.count * 0.005),
                    )
                )
        return insights[:20]  # max 20 insights


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionHeatmapEngine:
    """D05 — Heatmaps multi-axes des décisions."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._cache: LRUCache[HeatmapMatrix] = LRUCache(
            max_entries=100, ttl_seconds=3_600  # 1h
        )

    def generate_symbol_layer_heatmap(self, hours: int = 168) -> HeatmapMatrix:
        cache_key = f"symbol_layer_{hours}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        tr = TimeRange.last_hours(hours)
        rows = self._store.get_decisions(start_us=tr.start_us, limit=50_000)
        matrix = HeatmapBuilder.build_symbol_layer(rows, tr)
        self._cache.set(cache_key, matrix)
        return matrix

    def generate_regime_layer_heatmap(self, hours: int = 168) -> HeatmapMatrix:
        cache_key = f"regime_layer_{hours}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        tr = TimeRange.last_hours(hours)
        rows = self._store.get_decisions(start_us=tr.start_us, limit=50_000)
        matrix = HeatmapBuilder.build_regime_layer(rows, tr)
        self._cache.set(cache_key, matrix)
        return matrix

    def get_insights(self, matrix: HeatmapMatrix) -> list[HeatmapInsight]:
        return list(matrix.insights)

    def compare_periods(
        self, period1: TimeRange, period2: TimeRange
    ) -> HeatmapComparison:
        rows1 = self._store.get_decisions(
            start_us=period1.start_us, end_us=period1.end_us, limit=50_000
        )
        rows2 = self._store.get_decisions(
            start_us=period2.start_us, end_us=period2.end_us, limit=50_000
        )
        m1 = HeatmapBuilder.build_symbol_layer(rows1, period1)
        m2 = HeatmapBuilder.build_symbol_layer(rows2, period2)

        # Comparer cellule par cellule
        cells1 = {(c.x_value, c.y_value): c for c in m1.cells}
        cells2 = {(c.x_value, c.y_value): c for c in m2.cells}
        keys = set(cells1.keys()) | set(cells2.keys())

        changed = []
        for key in keys:
            c1 = cells1.get(key)
            c2 = cells2.get(key)
            v1 = c1.value if c1 else 0.0
            v2 = c2.value if c2 else 0.0
            delta = v2 - v1
            if abs(delta) > 0.05:
                z = abs(delta) / 0.1  # z-score approximatif
                changed.append((key[0], key[1], delta, round(z, 2)))

        changed.sort(key=lambda x: abs(x[2]), reverse=True)
        biggest_inc = next(((x, y, d) for x, y, d, _ in changed if d > 0), None)
        biggest_dec = next(((x, y, d) for x, y, d, _ in changed if d < 0), None)

        return HeatmapComparison(
            period1=period1,
            period2=period2,
            changed_cells=tuple(changed[:50]),
            biggest_increase=biggest_inc,
            biggest_decrease=biggest_dec,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionHeatmapEngine] = None
_engine_lock = threading.Lock()


def get_heatmap_engine() -> DecisionHeatmapEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionHeatmapEngine()
    return _engine
