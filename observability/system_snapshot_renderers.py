from __future__ import annotations

from observability.system_snapshot import (
    PipelineStageStatus,
    SystemSnapshot,
    reason_label,
)


def _icon(ok: bool) -> str:
    return "✔" if ok else "✘"


def _pipeline_status_text(status: PipelineStageStatus) -> str:
    return {
        PipelineStageStatus.OK: "OK",
        PipelineStageStatus.WAIT: "WAIT",
        PipelineStageStatus.FAILED: "FAILED",
        PipelineStageStatus.SKIPPED: "SKIPPED",
        PipelineStageStatus.READY: "READY",
    }[status]


def render_ai_decision_block(snapshot: SystemSnapshot) -> str:
    d = snapshot.ai_decision
    reason_txt = d.reason_text or reason_label(d.reason_code)
    hi = ""
    if d.highest_candidate_symbol:
        hi = (
            f"\n  Highest candidate: {d.highest_candidate_symbol}"
            f" ({d.highest_candidate_score:.0f}/100)"
            f"\n  Required: {d.required_score:.0f}/100"
        )
        # Vérité du gate : seuil par régime sur score packet — peut refuser
        # un candidat pourtant affiché au-dessus de required_score.
        if d.gate_reason:
            hi += f"\n  Gate: {d.gate_reason}"
    return (
        "AI DECISION:\n"
        f"  Decision ID: #{d.decision_id}\n"
        f"  Decision Engine: {d.state.value}\n"
        f"  Confidence: {d.confidence_pct}%\n"
        f"  Reason: {d.reason_code.value} — {reason_txt}\n"
        f"  Blocking module: {d.blocking_module}\n"
        f"  Next evaluation: {d.next_evaluation_sec}s{hi}\n"
        f"  Brain Score: {d.brain_score_pct}%"
    )


def render_health_block(snapshot: SystemSnapshot) -> str:
    h = snapshot.health
    return (
        "HEALTH:\n"
        f"  API {_icon(h.api)}  DB {_icon(h.database)}  TG {_icon(h.telegram)}\n"
        f"  Market {_icon(h.market)}  Strategy {_icon(h.strategy)}"
    )


def render_pipeline_block(snapshot: SystemSnapshot) -> str:
    lines = ["PIPELINE:"]
    for s in snapshot.pipeline:
        status_txt = _pipeline_status_text(s.status)
        lines.append(
            f"  {s.name:<18} {status_txt:<7} {s.duration_ms:>6.1f}ms  {s.message}"
        )
    return "\n".join(lines)


def render_block_stats_block(snapshot: SystemSnapshot) -> str:
    bs = snapshot.block_stats

    def _fmt(section: tuple[tuple[str, int], ...]) -> str:
        if not section:
            return "none"
        return " | ".join(f"{k}:{v}" for k, v in section)

    return (
        "BLOCK STATS:\n"
        f"  Cycle: {_fmt(bs.current_cycle)}\n"
        f"  Session: {_fmt(bs.session)}\n"
        f"  Lifetime: {_fmt(bs.lifetime)}"
    )


def render_quant_overview_block(snapshot: SystemSnapshot) -> str:
    p = snapshot.portfolio
    return (
        "PORTFOLIO BRAIN:\n"
        f"  Paper Equity: ${p.paper_equity:.2f} | Paper Cash: ${p.paper_cash:.2f}\n"
        f"  Portfolio Exposure: {p.portfolio_exposure_pct:.1f}% | "
        f"Free Cash: ${p.free_cash:.2f}\n"
        f"  Positions: {p.open_positions} | Corr risk: {p.correlation_risk_pct:.1f}%\n"
        f"  Open PnL: {p.open_pnl_usd:+.2f}$"
    )


def render_real_account_block(snapshot: SystemSnapshot, mode_label: str) -> str:
    a = snapshot.api_account
    p = snapshot.portfolio
    assets = " | ".join(f"{sym}:{qty:.6g}" for sym, qty in a.api_assets) or "N/A"
    sign = "+" if p.session_pnl_usd >= 0 else ""
    return (
        f"📊 <b>Statut Compte Réel — Cycle #{snapshot.meta.cycle}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 API Equity : <b>${a.api_equity_usdt:.4f} USDT</b>\n"
        f"💵 API Free Cash : <b>${a.api_free_cash_usdt:.4f} USDT</b>\n"
        f"📂 API Positions : <b>{a.api_positions}</b>\n"
        f"⚙️ Mode : <b>{mode_label}</b>\n"
        f"📈 Paper Equity (machine) : <b>${p.paper_equity:.2f} USDT</b>\n"
        f"🔄 PnL depuis ce redémarrage : <b>{sign}{p.session_pnl_usd:.2f}$</b>\n"
        f"💼 API Assets : <b>{assets}</b>"
    )


def render_heartbeat(snapshot: SystemSnapshot, ram_mb: int) -> str:
    d = snapshot.ai_decision
    return (
        f"[ALIVE] Cycle {snapshot.meta.cycle}\n"
        f"Regime: {snapshot.market.regime} | Decision: {d.state.value}\n"
        f"Paper Equity: ${snapshot.portfolio.paper_equity:,.2f} | "
        f"Paper Cash: ${snapshot.portfolio.paper_cash:,.2f} | "
        f"Pos: {snapshot.portfolio.open_positions}\n"
        f"Reason: {d.reason_code.value} {d.reason_text}\n"
        f"Brain Score: {d.brain_score_pct}%\n"
        f"RAM: {ram_mb}MB"
    )
