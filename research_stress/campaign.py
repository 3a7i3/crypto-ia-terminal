"""Rapport déterministe en mémoire ; aucune écriture ni découverte runtime."""
from __future__ import annotations

import hashlib
import itertools
import statistics
from decimal import Context, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from research_replay import replay_factual_dataset

from .protocol import amount, canonical, decimal_text, digest, require_code_sha, validate_protocol


MISSING_EVIDENCE = [
    "POPULATION_COMPLETE_DECISIONS_ADMISSIONS_REJECTIONS",
    "CERTIFIED_SYNCHRONIZED_MARKET_PRICE_PATHS",
    "SPREAD_DEPTH_LIQUIDITY_EXECUTABILITY",
    "FROZEN_STRATEGY_AND_TIMEOUT_BINDING",
    "CAUSAL_REGIMES_AND_CHRONOLOGICAL_OOS",
    "INDEPENDENT_CLUSTER_SAMPLE_AND_POWER",
]


def _distribution(values: list[float]) -> dict:
    if not values:
        return {"status": "NOT_AVAILABLE", "n": 0, "values": [], "mean": None,
                "median": None, "minimum": None, "maximum": None}
    return {"status": "DESCRIPTIVE_ONLY", "n": len(values), "values": values,
            "mean": statistics.mean(values), "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)}


def risk_envelopes(protocol: dict) -> list[dict]:
    """Stress analytique LONG sans levier ; pas de fills ni modèle de marché."""
    validate_protocol(protocol)
    rows = []
    # Le contexte Decimal de l'appelant ne doit pas changer les résultats.
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):

        capital = amount(protocol["capital_usdt"])
        for notional, cap in itertools.product(protocol["controls"]["notionals_usdt"],
                                                protocol["controls"]["position_caps"]):
            exposure = amount(notional) * cap
            scenarios = []
            for fee, slip, spread, shock in itertools.product(
                protocol["cost_grid"]["fee_bps"], protocol["cost_grid"]["slippage_bps"],
                protocol["cost_grid"]["spread_bps"], protocol["shock_fractions"]
            ):
                # Coûts sur notionnel fixe à chaque jambe. Demi-spread/jambe.
                costs = exposure * (2 * amount(fee) + 2 * amount(slip) + amount(spread)) / 10000
                loss = exposure * amount(shock) + costs
                scenarios.append({
                    "fee_bps_per_leg": fee, "slippage_bps_per_leg": slip,
                    "spread_bps_round_trip": spread, "adverse_fraction": shock,
                    "correlation_assumption": "COMMON_ADVERSE_SHOCK_ALL_POSITIONS",
                    "cost_usdt": decimal_text(costs), "loss_usdt": decimal_text(loss),
                    "loss_fraction_capital": decimal_text(loss / capital),
                    "breaches_proposed_loss_stop": loss / capital >= amount(
                        protocol["stopping_proposals"]["loss_fraction"]),
                    "cash_after_reserved_principal_and_costs_usdt": decimal_text(capital - exposure - costs),
                })
            rows.append({
                "notional_usdt": notional, "max_positions": cap,
                "arm_ids": [a["id"] for a in protocol["arms"]
                            if a["notional_usdt"] == notional and a["max_positions"] == cap],
                "kind": "COUNTERFACTUAL_ANALYTIC_ENVELOPE",
                "max_notional_usdt": decimal_text(exposure),
                "max_exposure_fraction": decimal_text(exposure / capital),
                "breaches_proposed_exposure_stop": exposure / capital > amount(
                    protocol["stopping_proposals"]["exposure_fraction"]),
                "all_same_symbol_breaches_concentration_stop": exposure / capital > amount(
                    protocol["stopping_proposals"]["single_symbol_fraction"]),
                "all_same_symbol_concentration_fraction": decimal_text(exposure / capital),
                "equal_distinct_symbol_concentration_fraction": decimal_text(amount(notional) / capital),
                "scenarios": scenarios,
                "limitations": ["FULL_CAP_LONG_UNLEVERED_FIXED_NOTIONAL_ASSUMPTION",
                                 "NO_EXECUTION_OR_ADMISSION_RECONSTRUCTION",
                                 "NO_LIQUIDITY_CERTIFICATION_OR_SHORT_LOSS_BOUND",
                                 "STOP_IS_TESTED_AFTER_SHOCK_NOT_GUARANTEED_FILL"],
            })
    return rows


def build_report(protocol: dict, *, research_code_sha: str,
                 dataset_path: Path | None = None,
                 input_class: str = "NO_DATASET") -> dict:
    """Réutilise RL-REPLAY uniquement sur une copie immuable explicitement fournie.

    input_class est une déclaration de provenance, jamais une certification.
    Un dataset PPL valide ne prouve pas la disponibilité de trajectoires marché.
    """
    validate_protocol(protocol)
    require_code_sha(research_code_sha)
    if input_class not in {"NO_DATASET", "SYNTHETIC_TEST_ONLY", "DECLARED_IMMUTABLE_RESEARCH_COPY"}:
        raise ValueError("Classe d'entrée non reconnue")
    if (dataset_path is None) != (input_class == "NO_DATASET"):
        raise ValueError("Classe d'entrée incohérente avec le dataset")
    baseline = {"status": "NOT_AVAILABLE", "reason": "NO_DATASET_BYTES_AVAILABLE"}
    if dataset_path is not None:
        replay = replay_factual_dataset(dataset_path, replay_code_sha=research_code_sha)
        closed = [r for r in replay.lifecycle if r.resolution_status == "CLOSED"]
        baseline = {
            "status": "VALIDATED_FACTUAL_REPLAY_NOT_EXTERNAL_CERTIFICATION",
            "replay": replay.as_dict(),
            "net_pnl_distribution_usdt": _distribution([r.net_realized_pnl for r in closed]),
            "gross_pnl_distribution_usdt": _distribution([r.gross_pnl for r in closed]),
            "fees_distribution_usdt": _distribution([r.entry_fee + r.exit_fee for r in closed]),
            "closed_duration_seconds_distribution": _distribution([r.resolved_at - r.opened_at for r in closed]),
            "decision_population": {"status": "NOT_AVAILABLE", "value": None,
                                    "reason": "OPEN_IDS_ARE_NOT_ALL_DECISIONS"},
            "empirical_correlation": {"status": "NOT_AVAILABLE", "value": None},
            "additional_metrics": {name: {"status": "NOT_AVAILABLE", "value": None}
                                   for name in ("mean_time_weighted_exposure", "maximum_mtm_exposure",
                                                "slippage", "regime_coverage", "oos_performance",
                                                "effective_independent_sample_size")},
            "uncertainty_intervals": {"status": "NOT_AVAILABLE", "value": None,
                                      "reason": "CLUSTER_AND_REGIME_EVIDENCE_REQUIRED"},
        }
    identity = {
        "schema": "paper-stress-401.report.v1", "research_code_sha": research_code_sha,
        "protocol_sha256": digest(protocol), "input_class": input_class,
        "upstream_replay_id": baseline.get("replay", {}).get("research_run_id"),
        "method": "FACTUAL_REUSE_PLUS_ANALYTIC_ENVELOPES_V1",
    }
    report = {
        "identity": identity, "report_id": digest(identity),
        "readiness": "INSUFFICIENT_EVIDENCE", "activation_allowed": False,
        "factual_baseline": baseline, "risk_envelopes": risk_envelopes(protocol),
        "comparisons": {factor: {"status": "INSUFFICIENT_EVIDENCE", "results": None,
                                  "missing_evidence": MISSING_EVIDENCE}
                        for factor in ("joint_A_B_C_performance", "position_count", "sizing",
                                       "holding_horizon", "activity_windows", "strategy_robustness")},
        "governance": {
            "same_epoch_feedback": "NO_SOURCE_WRITE_OR_ACTIVATION_API",
            "production_runtime_state": "NOT_OBSERVED",
            "certification": "SOURCE_BOUNDARY_ONLY_NOT_RUNTIME_CERTIFICATION",
            "protected_epoch": protocol["protected_epoch"],
        },
    }
    return {"manifest": {"schema": "paper-stress-401.envelope.v1",
                         "report_id": report["report_id"],
                         "report_sha256": hashlib.sha256(canonical(report)).hexdigest(),
                         "protocol_sha256": digest(protocol)}, "report": report}


def verify_report(envelope: dict, protocol: dict) -> None:
    """Vérifie contenu, identité ET recalcul analytique, pas seulement un hash."""
    report = envelope["report"]
    expected_manifest = {"schema": "paper-stress-401.envelope.v1",
                         "report_id": digest(report["identity"]),
                         "report_sha256": digest(report), "protocol_sha256": digest(protocol)}
    if (envelope["manifest"] != expected_manifest
            or report["report_id"] != expected_manifest["report_id"]
            or report["identity"]["protocol_sha256"] != digest(protocol)
            or report["risk_envelopes"] != risk_envelopes(protocol)
            or report["activation_allowed"] is not False
            or report["readiness"] != "INSUFFICIENT_EVIDENCE"):
        raise ValueError("Rapport altéré ou incohérent")
