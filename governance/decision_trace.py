"""
governance/decision_trace.py — G4 : Traçabilité des Décisions.

Formatte un DecisionPacket en une explication lisible par un humain.

Répond à la question : "Pourquoi cet ordre ?"

Usage:
    from governance.decision_trace import explain_decision, format_decision_chain

    # Explication complète d'un DecisionPacket
    text = explain_decision(packet)
    print(text)

    # Résumé court pour logs/dashboard
    summary = format_decision_chain(packet)

Exemple de sortie :

    ═══════════════════════════════════════════════════
      BTCUSDT │ LONG │ APPROVED
    ═══════════════════════════════════════════════════
      Signal Engine      │ confidence    +0.80
      Conviction Engine  │ conviction    HIGH (75%)
      Portfolio Brain    │ allocation    1.7% capital
      Risk Gate          │ risk_score    0.31  ✓ PASS
      Order Sizer        │ size_factor   0.85x
    ───────────────────────────────────────────────────
      Final Score        │ 0.72
      Regime             │ TREND_BULL
      R/R                │ 2.4x  (SL: 41200 / TP: 43800)
    ═══════════════════════════════════════════════════
      Sources : SignalEngine, PortfolioBrain, RiskGate
    ═══════════════════════════════════════════════════
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Évite l'import circulaire au runtime tout en permettant le type-check
    from core.decision_packet import DecisionPacket


def explain_decision(packet: "DecisionPacket") -> str:
    """
    Retourne une explication complète et lisible d'un DecisionPacket.

    Conforme à Constitution Article 5 :
    tout ordre exécuté doit pouvoir répondre à 'Pourquoi ?'
    """
    lines = [
        "═══════════════════════════════════════════════════",
        f"  {packet.symbol} │ {packet.side.value} │ {packet.lifecycle_state.value}",
        "═══════════════════════════════════════════════════",
    ]

    # Raisonnements par agent (source_agents + add_reasoning history)
    if hasattr(packet, "reasoning_chain") and packet.reasoning_chain:
        for entry in packet.reasoning_chain:
            agent = getattr(entry, "agent", "?")
            label = getattr(entry, "label", "")
            impact = getattr(entry, "confidence_impact", 0.0)
            sign = "+" if impact >= 0 else ""
            lines.append(f"  {agent:<22} │ {label:<14} {sign}{impact:.2f}")
    else:
        # Fallback : infos structurées disponibles directement sur le packet
        lines.append(
            f"  {'SignalEngine':<22} │ {'confidence':<14} {packet.confidence:+.2f}"
        )
        conviction = getattr(packet, "conviction", None)
        if conviction is not None:
            lines.append(
                f"  {'ConvictionEngine':<22} │ {'conviction':<14} {conviction.value}"
            )
        alloc = getattr(packet, "allocation_pct", None)
        if alloc is not None:
            lines.append(
                f"  {'PortfolioBrain':<22} │ {'allocation':<14} {alloc:.1%} capital"
            )

    # Risk gate
    lines.append("─" * 51)
    veto = getattr(packet, "veto", False)
    risk_score = getattr(packet, "risk_score", None)
    if veto:
        veto_reason = getattr(packet, "veto_reason", "unknown")
        lines.append(f"  {'RiskGate':<22} │ {'VETOED':<14} ✗ {veto_reason}")
    elif risk_score is not None:
        gate = (
            "✓ PASS"
            if risk_score < 0.6
            else "⚠ WARN" if risk_score < 0.85 else "✗ FAIL"
        )
        lines.append(
            f"  {'RiskGate':<22} │ {'risk_score':<14} {risk_score:.2f}  {gate}"
        )

    # Synthèse
    lines.append("─" * 51)
    lines.append(f"  {'Final confidence':<22} │ {packet.confidence:.2f}")
    regime = getattr(packet, "regime", None)
    if regime is not None:
        lines.append(f"  {'Regime':<22} │ {regime.value}")

    # Prix & R/R
    entry = getattr(packet, "entry_price", None)
    sl = getattr(packet, "stop_loss", None)
    tp = getattr(packet, "take_profit", None)
    r_mult = getattr(packet, "r_multiple", None)
    if entry and sl and tp:
        lines.append(
            f"  {'R/R':<22} │ {r_mult or '?'}x  " f"(SL: {sl:.0f} / TP: {tp:.0f})"
        )

    # Sources
    sources = getattr(packet, "source_agents", [])
    lines.append("═" * 51)
    if sources:
        lines.append(f"  Sources : {', '.join(sources)}")
    lines.append("═" * 51)

    # Lifecycle history
    history = getattr(packet, "state_history", [])
    if history:
        lines.append("  Lifecycle :")
        for t in history:
            from_s = getattr(t, "from_state", "?")
            to_s = getattr(t, "to_state", "?")
            reason = getattr(t, "reason", "")
            ts = getattr(t, "timestamp", None)
            ts_str = f" @ {ts:.3f}" if isinstance(ts, float) else ""
            lines.append(f"    {from_s} → {to_s}  [{reason}]{ts_str}")
        lines.append("═" * 51)

    return "\n".join(lines)


def format_decision_chain(packet: "DecisionPacket") -> str:
    """
    Résumé court sur une ligne pour logs et alertes.

    Exemple :
        [BTCUSDT] LONG | confidence=0.72 | APPROVED | risk=0.31 | alloc=1.7%
    """
    parts = [
        f"[{packet.symbol}]",
        packet.side.value,
        f"confidence={packet.confidence:.2f}",
        packet.lifecycle_state.value,
    ]
    risk_score = getattr(packet, "risk_score", None)
    if risk_score is not None:
        parts.append(f"risk={risk_score:.2f}")
    alloc = getattr(packet, "allocation_pct", None)
    if alloc is not None:
        parts.append(f"alloc={alloc:.1%}")
    veto = getattr(packet, "veto", False)
    if veto:
        veto_reason = getattr(packet, "veto_reason", "unknown")
        parts.append(f"VETOED({veto_reason})")
    return " | ".join(parts)


def format_rejection_reason(packet: "DecisionPacket") -> str:
    """
    Explique pourquoi un packet a été rejeté ou vétoé.
    Utilisé pour les alertes et les logs d'audit.
    """
    veto = getattr(packet, "veto", False)
    if veto:
        return f"VETOED: {getattr(packet, 'veto_reason', 'no reason')}"

    state = packet.lifecycle_state.value
    if state == "REJECTED":
        history = getattr(packet, "state_history", [])
        last = history[-1] if history else None
        if last:
            return f"REJECTED at {getattr(last, 'to_state', '?')}: {getattr(last, 'reason', 'no reason')}"
        return "REJECTED: no history"

    return f"Terminal state: {state}"
