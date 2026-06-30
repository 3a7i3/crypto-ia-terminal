"""
observability/decision_observation.py — Contrat d'observabilité unifié.

`DecisionObservation` est l'objet immutable qui circule dans le Decision Event Bus.
Tous les observateurs (Telegram, RejectionStore, RegretScheduler, ACE futur) reçoivent
cet objet — jamais le dict AnalysisResult brut, jamais des agents directement.

Règle constitutionnelle (ADR-0007) :
    Les observateurs lisent cet objet. Ils ne le modifient pas.
    Ils ne modifient pas le moteur de décision.

Construction :
    from observability.decision_observation import build_from_result
    obs = build_from_result(analyze_symbol_result, cycle=42)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── Labels lisibles pour les couches ──────────────────────────────────────────

_LAYER_LABELS: Dict[str, str] = {
    "authority": "Autorité",
    "meta": "Meta-Strategy",
    "meta_strategy": "Meta-Strategy",
    "gate": "Risk Gate",
    "global_risk_gate": "Risk Gate",
    "awareness": "Self-Awareness",
    "conviction": "Conviction",
    "conviction_engine": "Conviction",
    "no_trade": "No-Trade Layer",
    "no_trade_layer": "No-Trade Layer",
    "portfolio": "Portfolio Brain",
    "portfolio_brain": "Portfolio Brain",
    "cae": "Capital Alloc.",
    "capital_engine": "Capital Alloc.",
    "mistake_mem": "Mistake Memory",
    "mistake_memory": "Mistake Memory",
    "exec_override": "Exec. Override",
    "executive_override": "Exec. Override",
    "radar": "Threat Radar",
    "threat_radar": "Threat Radar",
    "arbitrator": "Arbitrator",
    "pipeline_g8d": "Pipeline (G8-D)",
}


# ── Contrat principal (frozen = immutable) ────────────────────────────────────


@dataclass(frozen=True)
class DecisionObservation:
    """
    Snapshot immutable d'un cycle de décision complet.

    Produit après `analyze_symbol()`, publié dans DecisionEventBus.
    Tous les champs sont des types simples (str, float, bool, list, dict) —
    aucune référence aux objets agents pour éviter les couplages.
    """

    # ── Identité ──────────────────────────────────────────────────────────────
    observation_id: str  # "20260629-ETHUSDT-A3F9C2" — human-readable
    packet_id: str  # UUID du DecisionPacket source
    cycle: int
    ts: float  # Unix timestamp UTC
    ts_iso: str  # ISO-8601 UTC
    engine_version: str  # e.g. "v9.1"

    # ── Signal ────────────────────────────────────────────────────────────────
    symbol: str
    side: str  # "BUY" | "SELL" | "HOLD"
    score: float  # 0-100
    score_raw: float  # score brut avant ajustements pipeline
    price: float
    regime: str
    confirmed: bool  # MTF confirmation
    strength: float  # 0.0-1.0
    actionable: bool  # signal.actionable

    # ── Décomposition du score ────────────────────────────────────────────────
    score_mtf: float  # composante MTF (0-40)
    score_regime: float  # composante régime (0-25)
    score_data_quality: float  # composante qualité données (0-15)
    score_memory: float  # composante mémoire (0-20)

    # ── Verdict final ─────────────────────────────────────────────────────────
    trade_allowed: bool
    first_blocker: Optional[str]  # e.g. "conviction"
    all_blockers: List[str]  # e.g. ["conviction", "portfolio"]
    human_verdict: str  # e.g. "REFUSÉ — Conviction + Portfolio Brain"

    # ── Layer : Authority ──────────────────────────────────────────────────────
    authority_ok: bool

    # ── Layer : Meta-Strategy ─────────────────────────────────────────────────
    meta_allowed: bool
    meta_reason: str
    personality_name: str
    personality_min_score: float

    # ── Layer : Risk Gate ─────────────────────────────────────────────────────
    gate_allowed: bool
    gate_failed: List[str]  # e.g. ["score_too_low", "mtf_not_confirmed"]

    # ── Layer : Self-Awareness ────────────────────────────────────────────────
    awareness_ok: bool
    awareness_level: Optional[
        str
    ]  # "OK" | "CAUTION" | "WARNING" | "DANGER" | "CRITICAL"

    # ── Layer : Conviction ────────────────────────────────────────────────────
    conviction_ok: bool
    conviction_level: Optional[
        str
    ]  # "SKIP" | "LOW" | "MEDIUM" | "HIGH" | "EXCEPTIONAL"
    conviction_score: Optional[float]
    conviction_size_factor: Optional[float]
    conviction_dimensions: Dict[str, float]  # {signal, mtf, regime, memory, quality}

    # ── Layer : No-Trade ─────────────────────────────────────────────────────
    notrade_ok: bool
    notrade_reason: Optional[str]
    notrade_rejection_score: float

    # ── Layer : Portfolio Brain ───────────────────────────────────────────────
    portfolio_ok: bool
    portfolio_reason: Optional[str]
    portfolio_size_factor: Optional[float]

    # ── Layer : Capital Allocation ────────────────────────────────────────────
    cae_ok: bool
    cae_size_usd: Optional[float]
    cae_kelly: Optional[float]
    cae_ev: Optional[float]

    # ── Layer : Mistake Memory ────────────────────────────────────────────────
    mistake_ok: bool
    mistake_reason: Optional[str]

    # ── Layer : Executive Override ────────────────────────────────────────────
    override_ok: bool
    override_level: Optional[str]  # "CLEAR" | "REDUCE" | "CAREFUL" | "MINIMAL" | "VETO"
    override_size_factor: Optional[float]
    override_reason: Optional[str]

    # ── Layer : Threat Radar ──────────────────────────────────────────────────
    radar_ok: bool
    radar_level: Optional[str]  # "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    radar_threat_count: int

    # ── Layer : Arbitrator ────────────────────────────────────────────────────
    arbitration_decision: Optional[str]  # "EXECUTE" | "WAIT" | "REJECT" etc.

    # ── Sizing ────────────────────────────────────────────────────────────────
    base_size_usd: float
    final_size_usd: float

    # ── Features marché (subset lean) ────────────────────────────────────────
    features: Dict[str, float]

    # ── Audit trail DecisionPacket ────────────────────────────────────────────
    state_history: List[Dict[str, Any]]
    reasoning: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation JSON-safe — utilisé par RejectionStore et RegretScheduler."""
        return {
            "observation_id": self.observation_id,
            "packet_id": self.packet_id,
            "cycle": self.cycle,
            "ts": self.ts,
            "ts_iso": self.ts_iso,
            "engine_version": self.engine_version,
            "symbol": self.symbol,
            "side": self.side,
            "score": self.score,
            "score_raw": self.score_raw,
            "price": self.price,
            "regime": self.regime,
            "confirmed": self.confirmed,
            "strength": self.strength,
            "actionable": self.actionable,
            "score_mtf": self.score_mtf,
            "score_regime": self.score_regime,
            "score_data_quality": self.score_data_quality,
            "score_memory": self.score_memory,
            "trade_allowed": self.trade_allowed,
            "first_blocker": self.first_blocker,
            "all_blockers": self.all_blockers,
            "human_verdict": self.human_verdict,
            "authority_ok": self.authority_ok,
            "meta_allowed": self.meta_allowed,
            "meta_reason": self.meta_reason,
            "personality_name": self.personality_name,
            "personality_min_score": self.personality_min_score,
            "gate_allowed": self.gate_allowed,
            "gate_failed": self.gate_failed,
            "awareness_ok": self.awareness_ok,
            "awareness_level": self.awareness_level,
            "conviction_ok": self.conviction_ok,
            "conviction_level": self.conviction_level,
            "conviction_score": self.conviction_score,
            "conviction_size_factor": self.conviction_size_factor,
            "conviction_dimensions": self.conviction_dimensions,
            "notrade_ok": self.notrade_ok,
            "notrade_reason": self.notrade_reason,
            "notrade_rejection_score": self.notrade_rejection_score,
            "portfolio_ok": self.portfolio_ok,
            "portfolio_reason": self.portfolio_reason,
            "portfolio_size_factor": self.portfolio_size_factor,
            "cae_ok": self.cae_ok,
            "cae_size_usd": self.cae_size_usd,
            "cae_kelly": self.cae_kelly,
            "cae_ev": self.cae_ev,
            "mistake_ok": self.mistake_ok,
            "mistake_reason": self.mistake_reason,
            "override_ok": self.override_ok,
            "override_level": self.override_level,
            "override_size_factor": self.override_size_factor,
            "override_reason": self.override_reason,
            "radar_ok": self.radar_ok,
            "radar_level": self.radar_level,
            "radar_threat_count": self.radar_threat_count,
            "arbitration_decision": self.arbitration_decision,
            "base_size_usd": self.base_size_usd,
            "final_size_usd": self.final_size_usd,
            "features": self.features,
            "state_history": self.state_history,
            "reasoning": self.reasoning,
        }


# ── Builder — construit depuis le dict retourné par analyze_symbol() ──────────


def build_from_result(
    result: Dict[str, Any],
    cycle: int,
    *,
    engine_version: str = "unknown",
) -> DecisionObservation:
    """
    Construit une DecisionObservation depuis le dict retourné par analyze_symbol().

    Robuste : chaque accès utilise getattr/get avec un défaut sûr.
    Ne lève jamais d'exception — retourne une observation dégradée en cas d'erreur.
    """
    sig = result.get("signal")
    gate = result.get("gate") or result.get("gate_result")
    dp = result.get("decision_packet")
    conviction = result.get("conviction")
    ntv = result.get("no_trade_verdict")
    pbv = result.get("pb_verdict")
    alloc = result.get("allocation")
    mmchk = result.get("mm_check")
    eov = result.get("eo_verdict")
    radar = result.get("radar_report")
    aw = result.get("awareness_state")
    pers = result.get("personality")
    arb = result.get("arbitration_result")

    # ── Signal de base ────────────────────────────────────────────────────────
    symbol = getattr(sig, "symbol", result.get("symbol", "UNKNOWN"))
    side = getattr(sig, "signal", "HOLD")
    score = float(getattr(sig, "score", 0))
    price = float(result.get("prix", 0.0))
    regime = str(getattr(sig, "regime", result.get("regime", "unknown")))
    confirmed = bool(getattr(sig, "confirmed", False))
    strength = float(getattr(sig, "strength", 0.0))
    actionable = bool(getattr(sig, "actionable", False))
    comps: Dict[str, Any] = getattr(sig, "components", {}) or {}

    # ── Blockers ──────────────────────────────────────────────────────────────
    blockers_raw = result.get("blockers", "")
    all_blockers: List[str] = (
        [b.strip() for b in blockers_raw.split(",") if b.strip()]
        if blockers_raw
        else []
    )
    first_blocker: Optional[str] = all_blockers[0] if all_blockers else None

    # ── Verdict humain ────────────────────────────────────────────────────────
    if result.get("trade_allowed"):
        human_verdict = "AUTORISÉ"
    elif all_blockers:
        labels = [_LAYER_LABELS.get(b, b) for b in all_blockers]
        human_verdict = f"REFUSÉ — {' + '.join(labels)}"
    elif not actionable:
        human_verdict = "NON ACTIONABLE"
    else:
        human_verdict = "REFUSÉ"

    # ── Identity ──────────────────────────────────────────────────────────────
    packet_id = (
        str(dp.packet_id) if dp and hasattr(dp, "packet_id") else str(uuid.uuid4())
    )
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    sym_short = symbol.replace("/USDT", "").replace("/", "")[:8]
    short = packet_id.replace("-", "")[-6:].upper()
    obs_id = f"{date_str}-{sym_short}-{short}"

    now = time.time()
    ts_iso = datetime.now(timezone.utc).isoformat()

    # ── Personality ───────────────────────────────────────────────────────────
    pers_name = str(pers.name) if pers and hasattr(pers, "name") else "unknown"
    pers_min_score = (
        float(pers.min_score) if pers and hasattr(pers, "min_score") else 0.0
    )

    # ── Gate ──────────────────────────────────────────────────────────────────
    gate_allowed = bool(gate.allowed) if gate and hasattr(gate, "allowed") else True
    gate_failed: List[str] = (
        list(gate.failed) if gate and hasattr(gate, "failed") else []
    )

    # ── Self-Awareness ────────────────────────────────────────────────────────
    aw_level_val: Optional[int] = None
    aw_level_name: Optional[str] = None
    if aw and hasattr(aw, "level"):
        lvl = aw.level
        aw_level_name = lvl.name if hasattr(lvl, "name") else str(lvl)
        aw_level_val = lvl.value if hasattr(lvl, "value") else 0
    awareness_ok = (aw is None) or (aw_level_val is not None and aw_level_val <= 2)

    # ── Conviction ────────────────────────────────────────────────────────────
    conv_ok = True if conviction is None else not conviction.blocks_trade()
    conv_level: Optional[str] = None
    conv_score: Optional[float] = None
    conv_sf: Optional[float] = None
    conv_dims: Dict[str, float] = {}
    if conviction is not None:
        conv_level = (
            getattr(conviction.level, "value", str(conviction.level))
            if hasattr(conviction, "level")
            else None
        )
        conv_score = float(getattr(conviction, "score", 0))
        conv_sf = float(getattr(conviction, "size_factor", 1.0))
        raw_dims = getattr(conviction, "dimensions", {}) or {}
        conv_dims = {
            k: float(v) for k, v in raw_dims.items() if isinstance(v, (int, float))
        }

    # ── No-Trade ──────────────────────────────────────────────────────────────
    notrade_ok = True if ntv is None else bool(ntv)
    notrade_reason: Optional[str] = None
    notrade_rej_score = 0.0
    if ntv is not None:
        notrade_rej_score = float(getattr(ntv, "rejection_score", 0.0))
        if not bool(ntv):
            notrade_reason = str(getattr(ntv, "reason", ""))

    # ── Portfolio Brain ───────────────────────────────────────────────────────
    pb_ok = True if pbv is None else bool(pbv.allowed)
    pb_reason: Optional[str] = None
    pb_sf: Optional[float] = None
    if pbv is not None:
        pb_sf = float(getattr(pbv, "size_factor", 1.0))
        if not pbv.allowed:
            pb_reason = str(getattr(pbv, "reason", ""))

    # ── Capital Allocation ────────────────────────────────────────────────────
    cae_ok = True if alloc is None else bool(alloc)
    cae_size: Optional[float] = None
    cae_kelly: Optional[float] = None
    cae_ev: Optional[float] = None
    if alloc is not None:
        cae_size = float(getattr(alloc, "size_usd", 0.0))
        cae_kelly = float(getattr(alloc, "kelly_fraction", 0.0))
        cae_ev = float(getattr(alloc, "ev_score", 0.0))

    # ── Mistake Memory ────────────────────────────────────────────────────────
    mm_ok = True if mmchk is None else not bool(getattr(mmchk, "blocked", False))
    mm_reason: Optional[str] = None
    if mmchk is not None and getattr(mmchk, "blocked", False):
        mm_reason = str(getattr(mmchk, "reason", ""))

    # ── Executive Override ────────────────────────────────────────────────────
    eo_ok = True if eov is None else bool(eov)
    eo_level: Optional[str] = None
    eo_sf: Optional[float] = None
    eo_reason: Optional[str] = None
    if eov is not None:
        if hasattr(eov, "level"):
            eo_level = getattr(eov.level, "name", str(eov.level))
        eo_sf = float(getattr(eov, "size_factor", 1.0))
        if not bool(eov):
            eo_reason = str(getattr(eov, "reason", ""))

    # ── Threat Radar ─────────────────────────────────────────────────────────
    radar_ok = True if radar is None else bool(radar.trade_allowed)
    radar_level: Optional[str] = None
    radar_n = 0
    if radar is not None:
        if hasattr(radar, "max_level"):
            radar_level = getattr(radar.max_level, "name", str(radar.max_level))
        radar_n = len(radar.threats) if hasattr(radar, "threats") else 0

    # ── Arbitrator ────────────────────────────────────────────────────────────
    arb_decision: Optional[str] = None
    if arb is not None and hasattr(arb, "decision"):
        arb_decision = getattr(arb.decision, "value", str(arb.decision))

    # ── Features (subset numérique uniquement) ────────────────────────────────
    raw_features: Dict[str, Any] = result.get("features") or {}
    features_clean = {
        k: float(v)
        for k, v in raw_features.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }

    # ── Audit trail ──────────────────────────────────────────────────────────
    state_history: List[Dict[str, Any]] = []
    reasoning_list: List[Dict[str, Any]] = []
    if dp is not None:
        try:
            state_history = [t.to_dict() for t in dp.state_history]
            reasoning_list = [r.to_dict() for r in dp.reasoning]
        except Exception:
            pass

    return DecisionObservation(
        observation_id=obs_id,
        packet_id=packet_id,
        cycle=cycle,
        ts=now,
        ts_iso=ts_iso,
        engine_version=engine_version,
        symbol=symbol,
        side=side,
        score=score,
        score_raw=float(getattr(sig, "confidence_raw", score) if sig else score),
        price=price,
        regime=regime,
        confirmed=confirmed,
        strength=strength,
        actionable=actionable,
        score_mtf=float(comps.get("mtf", 0.0)),
        score_regime=float(comps.get("regime", 0.0)),
        score_data_quality=float(comps.get("data_quality", 0.0)),
        score_memory=float(comps.get("memory", 0.0)),
        trade_allowed=bool(result.get("trade_allowed", False)),
        first_blocker=first_blocker,
        all_blockers=list(all_blockers),
        human_verdict=human_verdict,
        authority_ok=bool(result.get("_authority_ok", "authority" not in all_blockers)),
        meta_allowed=bool(result.get("meta_allowed", True)),
        meta_reason=str(result.get("meta_reason", "OK")),
        personality_name=pers_name,
        personality_min_score=pers_min_score,
        gate_allowed=gate_allowed,
        gate_failed=gate_failed,
        awareness_ok=awareness_ok,
        awareness_level=aw_level_name,
        conviction_ok=conv_ok,
        conviction_level=conv_level,
        conviction_score=conv_score,
        conviction_size_factor=conv_sf,
        conviction_dimensions=conv_dims,
        notrade_ok=notrade_ok,
        notrade_reason=notrade_reason,
        notrade_rejection_score=notrade_rej_score,
        portfolio_ok=pb_ok,
        portfolio_reason=pb_reason,
        portfolio_size_factor=pb_sf,
        cae_ok=cae_ok,
        cae_size_usd=cae_size,
        cae_kelly=cae_kelly,
        cae_ev=cae_ev,
        mistake_ok=mm_ok,
        mistake_reason=mm_reason,
        override_ok=eo_ok,
        override_level=eo_level,
        override_size_factor=eo_sf,
        override_reason=eo_reason,
        radar_ok=radar_ok,
        radar_level=radar_level,
        radar_threat_count=radar_n,
        arbitration_decision=arb_decision,
        base_size_usd=float(result.get("order_size", 0.0)),
        final_size_usd=float(result.get("order_size", 0.0)),
        features=features_clean,
        state_history=state_history,
        reasoning=reasoning_list,
    )
