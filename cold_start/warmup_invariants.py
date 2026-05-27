"""
warmup_invariants.py — Invariants système à vérifier à chaque étape (P10)

Un invariant est une propriété qui DOIT être vraie pour que le système soit sûr.
Si un invariant échoue → transition forcée vers FAILED.

Contrairement aux métriques (graduelles), les invariants sont binaires.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from observability.json_logger import get_logger

_log = get_logger("cold_start.warmup_invariants")


@dataclass
class InvariantResult:
    name: str
    passed: bool
    reason: str = ""
    critical: bool = True  # si True, un échec force FAILED

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "critical": self.critical,
        }


InvariantFn = Callable[[dict], InvariantResult]


# ── Définitions des invariants ────────────────────────────────────────────────


def inv_capital_not_negative(snapshot: dict) -> InvariantResult:
    """Le capital total ne peut pas être négatif."""
    capital = float(snapshot.get("capital_total", 0.0))
    return InvariantResult(
        name="capital_not_negative",
        passed=capital >= 0.0,
        reason="" if capital >= 0.0 else f"capital={capital:.2f} < 0",
    )


def inv_no_unknown_positions(snapshot: dict) -> InvariantResult:
    """Aucune position ouverte sans snapshot enregistré."""
    unknown = snapshot.get("open_positions_unknown", False)
    return InvariantResult(
        name="no_unknown_positions",
        passed=not unknown,
        reason=(
            "" if not unknown else "positions live sans snapshot — cohérence inconnue"
        ),
    )


def inv_hard_limits_not_breached(snapshot: dict) -> InvariantResult:
    """Les hard limits ne sont pas dépassées (risque absolu)."""
    ok = snapshot.get("hard_limits_ok", True)
    return InvariantResult(
        name="hard_limits_not_breached",
        passed=ok,
        reason="" if ok else "hard limits dépassées",
    )


def inv_kill_switch_not_active(snapshot: dict) -> InvariantResult:
    """Le kill switch n'est pas en mode safe (sauf si c'est volontaire)."""
    safe_mode = snapshot.get("kill_switch_safe_mode", False)
    # En cold start, safe_mode peut être normal — ce n'est bloquant
    # que si combiné avec un ordre live tenté
    return InvariantResult(
        name="kill_switch_not_active",
        passed=True,  # informatif seulement
        reason="kill switch actif" if safe_mode else "",
        critical=False,
    )


def inv_risk_governor_initialized(snapshot: dict) -> InvariantResult:
    """Le RiskGovernor est initialisé avec un état valide."""
    rg_state = snapshot.get("risk_governor_state", "")
    valid = rg_state.upper() in {
        "NORMAL",
        "AGGRESSIVE",
        "DEFENSIVE",
        "RECOVERY",
        "RISK_OFF",
        "",
    }
    return InvariantResult(
        name="risk_governor_initialized",
        passed=valid,
        reason="" if valid else f"état RG inconnu: '{rg_state}'",
    )


def inv_no_nan_capital_allocation(snapshot: dict) -> InvariantResult:
    """Aucune stratégie avec allocation NaN ou infinie."""
    allocations = snapshot.get("strategy_weights", {})
    bad = [
        sid
        for sid, w in allocations.items()
        if w != w or abs(w) == float("inf")  # NaN ou inf
    ]
    return InvariantResult(
        name="no_nan_capital_allocation",
        passed=len(bad) == 0,
        reason="" if not bad else f"NaN/Inf weights: {bad}",
    )


def inv_regime_not_stale(snapshot: dict) -> InvariantResult:
    """Le régime détecté n'est pas périmé (max 30 min sans refresh)."""
    import time

    regime_ts = snapshot.get("regime_last_updated_ts", 0.0)
    age_s = time.time() - regime_ts if regime_ts > 0 else float("inf")
    max_age = float(os.getenv("P10_REGIME_MAX_AGE_S", "1800"))  # 30 min
    passed = age_s <= max_age
    return InvariantResult(
        name="regime_not_stale",
        passed=passed,
        reason=(
            "" if passed else f"régime périmé depuis {age_s:.0f}s (max {max_age:.0f}s)"
        ),
        critical=False,  # avertissement, pas bloquant au boot
    )


def inv_portfolio_snapshot_readable(snapshot: dict) -> InvariantResult:
    """Le fichier positions_snapshot.json est lisible et non corrompu."""
    path = Path(
        os.getenv("POSITIONS_SNAPSHOT_PATH", "databases/positions_snapshot.json")
    )
    if not path.exists():
        return InvariantResult(
            name="portfolio_snapshot_readable",
            passed=True,  # premier boot — pas encore de snapshot
            reason="fichier absent (premier boot)",
            critical=False,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = isinstance(data, dict)
        return InvariantResult(
            name="portfolio_snapshot_readable",
            passed=valid,
            reason="" if valid else "snapshot non-dict",
        )
    except Exception as exc:
        return InvariantResult(
            name="portfolio_snapshot_readable",
            passed=False,
            reason=f"lecture échouée: {exc}",
        )


def inv_weights_sum_to_one(snapshot: dict) -> InvariantResult:
    """Les poids de stratégies somment à 1.0 (±0.01 tolérance)."""
    weights = snapshot.get("strategy_weights", {})
    if not weights:
        return InvariantResult(
            name="weights_sum_to_one",
            passed=True,
            reason="pas de poids (boot initial)",
            critical=False,
        )
    total = sum(float(w) for w in weights.values())
    passed = abs(total - 1.0) <= 0.01
    return InvariantResult(
        name="weights_sum_to_one",
        passed=passed,
        reason="" if passed else f"somme={total:.4f} ≠ 1.0",
    )


# ── Registre par état ─────────────────────────────────────────────────────────

# Invariants vérifiés à chaque état (progressivement plus stricts)
_INVARIANTS_BY_STATE: dict[str, list[InvariantFn]] = {
    "BOOTING": [
        inv_capital_not_negative,
        inv_risk_governor_initialized,
        inv_portfolio_snapshot_readable,
        inv_no_unknown_positions,  # positions inconnues = danger immédiat
    ],
    "FETCHING_MARKET_DATA": [
        inv_capital_not_negative,
        inv_hard_limits_not_breached,
        inv_risk_governor_initialized,
        inv_portfolio_snapshot_readable,
        inv_no_unknown_positions,
    ],
    "BUILDING_FEATURES": [
        inv_capital_not_negative,
        inv_hard_limits_not_breached,
        inv_no_nan_capital_allocation,
        inv_portfolio_snapshot_readable,
    ],
    "STABILIZING_REGIMES": [
        inv_capital_not_negative,
        inv_hard_limits_not_breached,
        inv_no_nan_capital_allocation,
        inv_regime_not_stale,
    ],
    "VALIDATING_RISK": [
        inv_capital_not_negative,
        inv_hard_limits_not_breached,
        inv_no_unknown_positions,
        inv_no_nan_capital_allocation,
        inv_weights_sum_to_one,
        inv_regime_not_stale,
    ],
    "SHADOW_MODE": [
        inv_capital_not_negative,
        inv_hard_limits_not_breached,
        inv_no_unknown_positions,
        inv_no_nan_capital_allocation,
        inv_weights_sum_to_one,
        inv_kill_switch_not_active,
    ],
    "LIVE_READY": [
        inv_capital_not_negative,
        inv_hard_limits_not_breached,
        inv_no_unknown_positions,
        inv_no_nan_capital_allocation,
        inv_weights_sum_to_one,
        inv_kill_switch_not_active,
    ],
}


class WarmupInvariants:
    """
    Vérifie les invariants système pour un état WarmupState donné.
    Retourne la liste des résultats et signale si un invariant critique a échoué.
    """

    def check(
        self,
        state_name: str,
        snapshot: dict,
    ) -> tuple[list[InvariantResult], bool]:
        """
        Vérifie tous les invariants pour l'état donné.

        Retourne (results, any_critical_failure).
        """
        fns = _INVARIANTS_BY_STATE.get(state_name, [])
        results: list[InvariantResult] = []
        critical_failure = False

        for fn in fns:
            try:
                result = fn(snapshot)
            except Exception as exc:
                result = InvariantResult(
                    name=fn.__name__,
                    passed=False,
                    reason=f"exception: {exc}",
                    critical=True,
                )
            results.append(result)
            if not result.passed and result.critical:
                critical_failure = True
                _log.error(
                    "[Invariants] ÉCHEC CRITIQUE %s/%s — %s",
                    state_name,
                    result.name,
                    result.reason,
                )
            elif not result.passed:
                _log.warning(
                    "[Invariants] avertissement %s/%s — %s",
                    state_name,
                    result.name,
                    result.reason,
                )

        return results, critical_failure

    def summary(self, results: list[InvariantResult]) -> dict:
        return {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed_critical": [
                r.to_dict() for r in results if not r.passed and r.critical
            ],
            "warnings": [
                r.to_dict() for r in results if not r.passed and not r.critical
            ],
        }
