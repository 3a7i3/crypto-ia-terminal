"""
trade_analysis/integrations/radar_adapter.py — Formatage LMI pour Telegram.

Transforme le detail d'un symbole (issu du sidecar) en message texte
lisible pour la commande /lmi du bot radar. Pur texte, aucune dependance.
"""

from __future__ import annotations

from pathlib import Path

from trade_analysis.integrations.dashboard_adapter import lmi_symbol, lmi_table

_STATE_EMOJI = {
    "accumulation": "\U0001f7e2",  # green
    "distribution": "\U0001f534",  # red
    "absorption_buy": "\U0001f7e1",
    "absorption_sell": "\U0001f7e1",
    "fragility_up": "\U0001f7e0",
    "fragility_down": "\U0001f7e0",
    "compression": "\U0001f535",
    "expansion": "⚡",
    "exhaustion_buy": "\U0001f7e3",
    "exhaustion_sell": "\U0001f7e3",
    "vacuum_up": "\U0001f300",
    "vacuum_down": "\U0001f300",
    "conflict": "⚔️",
    "quiet": "⚪",
}


def _bar(pct: float, width: int = 10) -> str:
    filled = int(round(pct / 100.0 * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _fmt_usd(v: float) -> str:
    v = float(v or 0.0)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f}k"
    return f"{v:.0f}"


def format_lmi_message(symbol: str, path: Path | None = None) -> str:
    """Message /lmi <symbol>. Retourne un texte pret pour Telegram."""
    detail = lmi_symbol(symbol, path)
    if detail is None:
        return (
            f"\U0001f30a LMI — {symbol.upper()}\n\n"
            "Aucune donnee live pour ce symbole.\n"
            "Il n'est pas dans la watchlist de l'observatoire, "
            "ou l'observatoire n'est pas actif."
        )

    s = detail["summary"]
    liq = detail["liquidity"]
    state = s["state"]
    emoji = _STATE_EMOJI.get(state, "⚪")
    bp = float(s["buy_pressure"])
    sp = float(s["sell_pressure"])

    consumed = liq["consumed_usd"]
    removed = liq["removed_usd"]
    added = liq["added_usd"]
    liq_total = consumed + removed + added

    def pct(x: float) -> str:
        return f"{x / liq_total * 100:.0f}%" if liq_total > 0 else "—"

    stale = " (stale)" if s["stale"] else ""

    lines = [
        "\U0001f30a LIVE MARKET INTERACTION",
        f"{symbol.upper()}{stale}",
        "━" * 16,
        "",
        "STATE",
        f"{emoji} {state.upper()}   ({s['state_confidence'] * 100:.0f}%)",
        "",
        "MARKET PRESSURE",
        f"BUY   {_bar(bp)} {bp:.0f}",
        f"SELL  {_bar(sp)} {sp:.0f}",
        "",
        "EXECUTED FLOW",
        f"BUY   {_fmt_usd(s['executed_buy_usd'])}",
        f"SELL  {_fmt_usd(s['executed_sell_usd'])}",
        "",
        "LIQUIDITY",
        f"Consumed  {_fmt_usd(consumed)}  {pct(consumed)}",
        f"Removed   {_fmt_usd(removed)}  {pct(removed)}",
        f"Added     {_fmt_usd(added)}  {pct(added)}",
        "",
        "MARKET RESPONSE",
        f"Resistance  {s['resistance']:.0f}",
        f"Fragility   {s['fragility']:.2f}",
        "",
        "⚠️ Research observation",
        "Not a trading signal",
    ]
    return "\n".join(lines)


def format_lmi_overview(path: Path | None = None, top: int = 10) -> str:
    """Message /lmi (sans argument) : vue d'ensemble des symboles observes."""
    table = lmi_table(path)
    rows = table["data"][:top]
    if not rows:
        return (
            "\U0001f30a LMI OBSERVATORY\n\n"
            "Aucun symbole observe actuellement.\n"
            "L'observatoire n'est pas actif ou aucune watchlist."
        )
    lines = ["\U0001f30a LMI OBSERVATORY", "━" * 16, ""]
    for r in rows:
        emoji = _STATE_EMOJI.get(r["state"], "⚪")
        lines.append(
            f"{emoji} {r['symbol']:<10} {r['state'].upper():<14} "
            f"P{int(r['buy_pressure']):>3}"
        )
    lines += ["", f"{len(table['data'])} symboles — /lmi <SYM> pour le detail"]
    return "\n".join(lines)
