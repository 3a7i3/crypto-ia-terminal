"""Contrat expérimental pur : hypothèses prospectives, jamais config PAPER."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any


class ProtocolError(ValueError):
    """Protocole invalide ; aucune valeur implicite n'est autorisée."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def amount(value: Any) -> Decimal:
    if not isinstance(value, str) or len(value) > 32:
        raise ProtocolError("Montant décimal attendu sous forme de chaîne")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ProtocolError("Montant invalide") from exc
    if not result.is_finite() or result < 0 or abs(result.as_tuple().exponent) > 18:
        raise ProtocolError("Montant négatif ou non fini")
    return result


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def validate_protocol(doc: dict) -> dict:
    if set(doc) != {"schema", "mission", "status", "activation_allowed", "capital_usdt",
                    "arms", "controls", "temporal", "cost_grid", "shock_fractions",
                    "stopping_proposals", "statistical_plan", "protected_epoch"}:
        raise ProtocolError("Champs du protocole inconnus ou manquants")
    if (doc["schema"] != "paper-stress-401.v1" or doc["mission"] != "#401"
            or doc["status"] != "PROPOSED_OFFLINE_ONLY"
            or doc["activation_allowed"] is not False):
        raise ProtocolError("Aucune autorité d'activation admise")
    if amount(doc["capital_usdt"]) <= 0:
        raise ProtocolError("Capital Research positif requis")
    expected = [("A", "10", 2), ("B", "50", 4), ("C", "100", 5)]
    if doc["arms"] != [dict(id=i, notional_usdt=n, max_positions=p) for i, n, p in expected]:
        raise ProtocolError("Bras hypothétiques #401 attendus")
    if doc["controls"] != {"position_caps": [2, 4, 5], "notionals_usdt": ["10", "50", "100"],
                            "design": "FULL_3_BY_3_FIXED_OTHER_FACTORS"}:
        raise ProtocolError("Contrôles factoriels requis")
    if doc["protected_epoch"] != "BURN-IN-EPOCH-01-20260926T064144Z":
        raise ProtocolError("Référence protégée incorrecte")
    if doc["temporal"] != {"timeout_multipliers": ["0.5", "1", "2"],
                           "utc_windows": [[0, 24], [0, 8], [8, 16], [16, 24]],
                           "baseline_timeout_seconds": None,
                           "strategy_policy": "EXISTING_FROZEN_STRATEGIES_ONLY"}:
        raise ProtocolError("Plan temporel séparé requis")
    grid = doc["cost_grid"]
    if set(grid) != {"fee_bps", "slippage_bps", "spread_bps"}:
        raise ProtocolError("Modèle de coût incomplet")
    for values in grid.values():
        if not isinstance(values, list) or not values:
            raise ProtocolError("Grille vide")
        for value in values:
            if amount(value) > 10000:
                raise ProtocolError("Coût supérieur à 100%")
    if not doc["shock_fractions"]:
        raise ProtocolError("Stress absent")
    for value in doc["shock_fractions"]:
        if amount(value) > 1:
            raise ProtocolError("Choc hors [0,1]")
    stops = doc["stopping_proposals"]
    if set(stops) != {"loss_fraction", "mtm_drawdown_fraction", "exposure_fraction",
                      "single_symbol_fraction", "max_missing_decisions", "max_stale_marks"}:
        raise ProtocolError("Arrêts incomplets")
    for key in ("loss_fraction", "mtm_drawdown_fraction", "exposure_fraction", "single_symbol_fraction"):
        if not 0 < amount(stops[key]) <= 1:
            raise ProtocolError("Limite hors (0,1]")
    for key in ("max_missing_decisions", "max_stale_marks"):
        if type(stops[key]) is not int or stops[key] != 0:
            raise ProtocolError("Données manquantes/stale : arrêt fail-closed")
    if doc["statistical_plan"] != {
        "unit": "UTC_DAY_CLUSTER_ALL_SYMBOLS", "bootstrap_seed": 401,
        "bootstrap_replicates": 2000, "confidence_level": "0.95",
        "minimum_day_clusters_proposed": 30, "oos_fraction": "0.30",
        "purge": "MAX_HOLDING_HORIZON", "claims": "DESCRIPTIVE_UNTIL_POWER_REVIEW"}:
        raise ProtocolError("Plan statistique non reconnu")
    return doc


def require_code_sha(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ProtocolError("SHA Git complet requis")
    return value


def strict_json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError("Clé JSON dupliquée")
            result[key] = value
        return result

    def reject(value):
        raise ProtocolError(f"Constante JSON interdite : {value}")

    try:
        doc = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("JSON strict invalide") from exc
    if not isinstance(doc, dict):
        raise ProtocolError("Objet JSON requis")
    return doc
