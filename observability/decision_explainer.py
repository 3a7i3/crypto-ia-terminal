"""
observability/decision_explainer.py — Formatteur Telegram du pipeline décisionnel.

Transforme une DecisionObservation en message Telegram structuré, hiérarchisé
et exhaustif. Un opérateur comprend la décision complète en < 10 secondes.

Format :
  ━━ SIGNAL: ETH/USDT — Cycle 42 ━━━━━━━━
  📈 BUY | Score: 78/100 ████░ | Prix: $3,250
  Régime: bull | Conviction: HIGH(82) ×0.6 | Perso: momentum

  ⛔ REFUSÉ — Conviction + Portfolio Brain

  ━━ PIPELINE (12 couches) ━━━━━━━━━━━━━━
  ✅ authority      can_trade OK
  ✅ meta           momentum_following score≥60
  ✅ gate           score=78≥60 MTF✓ régime OK
  ⛔ conviction     MEDIUM(55) bloque — size_factor=0.0
  ✅ no_trade       OK spread/vol OK
  ✅ awareness      OK (CAUTION)
  ⛔ portfolio      BLOQUÉ — exposition 38%>35%
  ✅ capital        $45 kelly=0.12 ev=+0.018
  ✅ mistake_mem    0 erreurs similaires
  ✅ exec_override  CLEAR ×1.0
  ✅ threat_radar   aucune menace

  ━━ SIZING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Base: $50 | Conv: ×0.0 | PB: OK | Final: $0

  ━━ SCORES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  MTF: 32/40 | Régime: 20/25 | Data: 12/15 | Mem: 14/20

Règle : ce module ne lève jamais d'exception en production.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation

# Limite Telegram
_MAX_CHARS = 4000

_SIDE_ICON = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸", "LONG": "📈", "SHORT": "📉"}
_REGIME_FR = {
    "bull_trend": "bull",
    "TREND_BULL": "bull",
    "bear_trend": "bear",
    "TREND_BEAR": "bear",
    "sideways": "range",
    "RANGE": "range",
    "high_volatility_regime": "volat",
    "VOLATILE": "volat",
    "flash_crash": "KRACH",
    "unknown": "?",
    "UNKNOWN": "?",
}
_SEP = "━" * 32


def _bar(score: float, width: int = 5) -> str:
    filled = round(max(0.0, min(100.0, score)) / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_price(p: float) -> str:
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:.4g}"
    return f"${p:.6g}"


def _score_label(s: float) -> str:
    if s >= 85:
        return "FORT"
    if s >= 70:
        return "BON"
    if s >= 55:
        return "MOYEN"
    if s >= 40:
        return "FAIBLE"
    return "TRES FAIBLE"


def _layer_line(ok: bool, label: str, detail: str) -> str:
    icon = "✅" if ok else "⛔"
    return f"{icon} {label:<14} {detail}"


def explain(obs: "DecisionObservation", cycle: int) -> str:
    """
    Produit le message Telegram complet pour une DecisionObservation.

    Garanti de retourner une chaîne non vide, même en cas d'erreur interne.
    Tronque à _MAX_CHARS si nécessaire.
    """
    try:
        return _explain_safe(obs, cycle)
    except Exception as exc:
        return (
            f"⚠️ SIGNAL {obs.symbol} — Cycle {cycle}\n"
            f"Verdict: {obs.human_verdict}\n"
            f"[Explainer erreur: {exc}]"
        )


def _explain_safe(obs: "DecisionObservation", cycle: int) -> str:
    lines: list[str] = []

    # ── En-tête ──────────────────────────────────────────────────────────────
    icon = _SIDE_ICON.get(obs.side, "?")
    regime_short = _REGIME_FR.get(obs.regime, obs.regime[:5])
    bar = _bar(obs.score)
    score_lbl = _score_label(obs.score)
    lines.append(f"{_SEP[:20]} {obs.symbol} — C{cycle}")
    lines.append(
        f"{icon} {obs.side} | Score: {obs.score:.0f}/100 {bar} {score_lbl}"
        f" | {_fmt_price(obs.price)}"
    )

    # Contexte signal
    ctx_parts = [f"Régime: {regime_short}"]
    if obs.conviction_level and obs.conviction_score is not None:
        sf = (
            f" ×{obs.conviction_size_factor:.1f}"
            if obs.conviction_size_factor is not None
            else ""
        )
        ctx_parts.append(
            f"Conv: {obs.conviction_level}({obs.conviction_score:.0f}){sf}"
        )
    ctx_parts.append(f"Perso: {obs.personality_name}")
    if obs.confirmed:
        ctx_parts.append("MTF✓")
    lines.append("  ".join(ctx_parts))

    # ── Verdict principal ──────────────────────────────────────────────────────
    lines.append("")
    if obs.trade_allowed:
        lines.append(f"✅ AUTORISÉ — taille finale ${obs.final_size_usd:.0f}")
    elif obs.all_blockers:
        lines.append(f"⛔ {obs.human_verdict}")
    elif not obs.actionable:
        lines.append(f"⏸ NON ACTIONABLE (signal HOLD ou score < seuil)")
    else:
        lines.append("⛔ REFUSÉ")

    # ── Pipeline — 12 couches ─────────────────────────────────────────────────
    lines.append("")
    lines.append(f"{_SEP[:16]} PIPELINE")

    # Authority
    lines.append(
        _layer_line(
            obs.authority_ok,
            "authority",
            "can_trade OK" if obs.authority_ok else "BLOQUÉ — RSM",
        )
    )

    # Meta-Strategy
    meta_detail = (
        f"{obs.personality_name} OK"
        if obs.meta_allowed
        else f"BLOQUÉ — {obs.meta_reason[:40]}"
    )
    lines.append(_layer_line(obs.meta_allowed, "meta", meta_detail))

    # Gate
    if obs.gate_allowed:
        mtf = "✓" if obs.confirmed else "✗"
        gate_detail = f"score={obs.score:.0f}≥{obs.personality_min_score:.0f} MTF{mtf}"
    else:
        failed_str = " | ".join(obs.gate_failed[:3]) if obs.gate_failed else "?"
        gate_detail = f"BLOQUÉ — {failed_str}"
    lines.append(_layer_line(obs.gate_allowed, "gate", gate_detail))

    # Conviction
    if obs.conviction_level is None:
        conv_detail = "non configurée"
        conv_ok = True
    elif obs.conviction_ok:
        sf_str = (
            f" ×{obs.conviction_size_factor:.1f}"
            if obs.conviction_size_factor is not None
            else ""
        )
        conv_detail = f"{obs.conviction_level}({obs.conviction_score:.0f}){sf_str}"
    else:
        sf_str = (
            f" size_factor={obs.conviction_size_factor:.1f}"
            if obs.conviction_size_factor is not None
            else ""
        )
        conv_detail = (
            f"BLOQUÉ — {obs.conviction_level}({obs.conviction_score:.0f}){sf_str}"
        )
    lines.append(_layer_line(obs.conviction_ok, "conviction", conv_detail))

    # No-Trade
    if obs.notrade_ok:
        nt_detail = f"OK (rej_score={obs.notrade_rejection_score:.0f})"
    else:
        nt_detail = f"BLOQUÉ — {(obs.notrade_reason or '?')[:40]}"
    lines.append(_layer_line(obs.notrade_ok, "no_trade", nt_detail))

    # Self-Awareness
    aw_lvl = obs.awareness_level or "N/A"
    aw_detail = f"OK ({aw_lvl})" if obs.awareness_ok else f"BLOQUÉ ({aw_lvl})"
    lines.append(_layer_line(obs.awareness_ok, "awareness", aw_detail))

    # Portfolio Brain
    if obs.portfolio_ok:
        pb_sf_str = (
            f"×{obs.portfolio_size_factor:.2f}"
            if obs.portfolio_size_factor is not None and obs.portfolio_size_factor < 1.0
            else "OK"
        )
        pb_detail = pb_sf_str
    else:
        pb_detail = f"BLOQUÉ — {(obs.portfolio_reason or '?')[:40]}"
    lines.append(_layer_line(obs.portfolio_ok, "portfolio", pb_detail))

    # Capital Allocation
    if obs.cae_ok and obs.cae_size_usd is not None:
        cae_parts = [f"${obs.cae_size_usd:.0f}"]
        if obs.cae_kelly is not None:
            cae_parts.append(f"kelly={obs.cae_kelly:.3f}")
        if obs.cae_ev is not None:
            sign = "+" if obs.cae_ev >= 0 else ""
            cae_parts.append(f"ev={sign}{obs.cae_ev:.4f}")
        cae_detail = " ".join(cae_parts)
    elif not obs.cae_ok:
        cae_detail = "BLOQUÉ — allocation refusée"
    else:
        cae_detail = "non configurée"
    lines.append(_layer_line(obs.cae_ok, "capital", cae_detail))

    # Mistake Memory
    mm_detail = (
        "OK" if obs.mistake_ok else f"BLOQUÉ — {(obs.mistake_reason or '?')[:40]}"
    )
    lines.append(_layer_line(obs.mistake_ok, "mistake_mem", mm_detail))

    # Executive Override
    if obs.override_ok:
        eo_parts = [obs.override_level or "CLEAR"]
        if obs.override_size_factor is not None and obs.override_size_factor < 1.0:
            eo_parts.append(f"×{obs.override_size_factor:.1f}")
        eo_detail = " ".join(eo_parts)
    else:
        eo_detail = f"VETO — {(obs.override_reason or '?')[:35]}"
    lines.append(_layer_line(obs.override_ok, "exec_override", eo_detail))

    # Threat Radar
    if obs.radar_ok:
        r_detail = (
            "aucune menace"
            if obs.radar_threat_count == 0
            else f"OK ({obs.radar_threat_count} menace(s) {obs.radar_level})"
        )
    else:
        r_detail = f"BLOQUÉ — {obs.radar_threat_count} menace(s) {obs.radar_level}"
    lines.append(_layer_line(obs.radar_ok, "threat_radar", r_detail))

    # Arbitrator (si disponible)
    if obs.arbitration_decision:
        arb_ok = obs.arbitration_decision in ("EXECUTE", "EXECUTE_REDUCED", "WAIT")
        arb_detail = obs.arbitration_decision
        lines.append(_layer_line(arb_ok, "arbitrator", arb_detail))

    # ── Sizing ────────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"{_SEP[:16]} SIZING")
    sizing_parts = [f"Base: ${obs.base_size_usd:.0f}"]
    if obs.conviction_size_factor is not None:
        sizing_parts.append(f"Conv: ×{obs.conviction_size_factor:.1f}")
    if obs.portfolio_size_factor is not None and obs.portfolio_size_factor < 1.0:
        sizing_parts.append(f"PB: ×{obs.portfolio_size_factor:.2f}")
    sizing_parts.append(f"Final: ${obs.final_size_usd:.0f}")
    lines.append(" | ".join(sizing_parts))

    # ── Scores décomposés ─────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"{_SEP[:16]} SCORES")
    lines.append(
        f"MTF: {obs.score_mtf:.1f}/40 | Régime: {obs.score_regime:.1f}/25"
        f" | Data: {obs.score_data_quality:.1f}/15 | Mém: {obs.score_memory:.1f}/20"
    )

    # Conviction dimensions si disponibles
    if obs.conviction_dimensions:
        dim_parts = [f"{k[:3]}={v:.1f}" for k, v in obs.conviction_dimensions.items()]
        lines.append("Dim conv: " + " ".join(dim_parts[:5]))

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"ID: {obs.observation_id}")

    text = "\n".join(lines)
    if len(text) > _MAX_CHARS:
        text = text[: _MAX_CHARS - 4] + "\n..."
    return text
