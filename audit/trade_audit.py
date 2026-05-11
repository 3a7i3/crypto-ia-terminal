"""
Trade Audit — Analyse détaillée de chaque trade
Explique pourquoi et comment le trade s'est déroulé
"""

from typing import Any
from tracker_system.storage.loader import load_jsonl


class TradeAudit:
    def __init__(self, entry_event: dict[str, Any], exit_event: dict[str, Any]):
        self.entry = entry_event
        self.exit = exit_event

    def get_duration_hours(self) -> float:
        """Durée du trade en heures."""
        duration_min = float(self.exit.get("duration_min", 0.0))
        return duration_min / 60.0

    def get_price_action(self) -> dict[str, Any]:
        """Analyse l'action des prix."""
        entry_price = float(self.entry.get("entry_price", 0.0))
        exit_price = float(self.exit.get("exit_price", entry_price))
        mfe = float(self.exit.get("mfe", 0.0))
        mae = float(self.exit.get("mae", 0.0))

        path = self.exit.get("price_path", [entry_price])
        max_path = max(float(p) for p in path) if path else entry_price
        min_path = min(float(p) for p in path) if path else entry_price

        return {
            "entry_price": entry_price,
            "exit_price": exit_price,
            "max_price": max_path,
            "min_price": min_path,
            "mfe": mfe,
            "mae": mae,
            "price_swing": max_path - min_path,
        }

    def was_lucky(self) -> bool:
        """Était-ce lucky ou skilled?"""
        mfe = float(self.exit.get("mfe", 0.0))
        pnl_pct = float(self.exit.get("pnl_pct", 0.0))

        if pnl_pct > 0 and mfe > pnl_pct * 1.5:
            return True
        return False

    def was_mistake(self) -> bool:
        """Le trade était-il une erreur?"""
        mae = float(self.exit.get("mae", 0.0))
        pnl_pct = float(self.exit.get("pnl_pct", 0.0))
        float(self.exit.get("mfe", 0.0))

        if pnl_pct > 0 and mae < pnl_pct * -0.5:
            return True
        return False

    def get_quality_label(self) -> str:
        """Qualité du trade."""
        pnl = float(self.exit.get("pnl_pct", 0.0))
        float(self.exit.get("mfe", 0.0))
        float(self.exit.get("mae", 0.0))

        if pnl > 0:
            if self.was_lucky():
                return "LUCKY"
            else:
                return "SKILLED"
        elif pnl == 0:
            return "BREAKEVEN"
        else:
            if self.was_mistake():
                return "MISTAKE"
            else:
                return "UNLUCKY"

    def generate_narrative(self) -> str:
        """Génère description du trade."""
        symbol = self.entry.get("symbol", "?")
        side = self.entry.get("side", "?")
        entry_price = float(self.entry.get("entry_price", 0.0))
        exit_price = float(self.exit.get("exit_price", entry_price))
        pnl_pct = float(self.exit.get("pnl_pct", 0.0))
        pnl_usd = float(self.exit.get("pnl_usd", 0.0))
        regime = self.exit.get("regime", "unknown")
        exit_reason = self.exit.get("exit_reason", "?")
        duration = self.get_duration_hours()

        quality = self.get_quality_label()
        price_action = self.get_price_action()

        narrative = f"""
{symbol} {side} Trade Analysis
{'-' * 50}

Entry:        {entry_price:.8f}
Exit:         {exit_price:.8f}
PnL:          {pnl_pct:+.2%} (${pnl_usd:+.2f})
Duration:     {duration:.1f} hours
Regime:       {regime}
Quality:      {quality}

Price Action:
  Max:        {price_action['max_price']:.8f}
  Min:        {price_action['min_price']:.8f}
  Swing:      {price_action['price_swing']:.8f}
  MFE:        {price_action['mfe']:+.2%}
  MAE:        {price_action['mae']:+.2%}

Exit Reason:  {exit_reason}

Analysis:
"""
        if quality == "SKILLED":
            narrative += "  - Trade was well-executed\n"
            narrative += f"  - Exited near peak (MFE={price_action['mfe']:.2%})\n"
        elif quality == "LUCKY":
            narrative += "  - Trade was lucky (caught a spike)\n"
            narrative += f"  - Could have lost much more (MAE={price_action['mae']:.2%})\n"
        elif quality == "MISTAKE":
            narrative += "  - Trade recovered from near-loss\n"
            narrative += f"  - Got stopped at wrong level (MAE={price_action['mae']:.2%})\n"
        elif quality == "UNLUCKY":
            narrative += "  - Trade had wrong direction initially\n"
            narrative += f"  - Lost despite recovery attempt (MFE={price_action['mfe']:.2%})\n"

        return narrative

    def as_dict(self) -> dict[str, Any]:
        """Export as dict."""
        return {
            "symbol": self.entry.get("symbol"),
            "side": self.entry.get("side"),
            "entry_price": float(self.entry.get("entry_price", 0.0)),
            "exit_price": float(self.exit.get("exit_price", 0.0)),
            "pnl_pct": float(self.exit.get("pnl_pct", 0.0)),
            "pnl_usd": float(self.exit.get("pnl_usd", 0.0)),
            "mfe": float(self.exit.get("mfe", 0.0)),
            "mae": float(self.exit.get("mae", 0.0)),
            "duration_hours": self.get_duration_hours(),
            "quality": self.get_quality_label(),
            "regime": self.exit.get("regime"),
        }


def audit_all_trades(log_file) -> list[TradeAudit]:
    """Audit tous les trades du log."""
    events = load_jsonl(log_file)
    entries = {}

    audits = []
    for event in events:
        if event.get("type") == "entry":
            entries[event.get("id")] = event
        elif event.get("type") == "exit":
            event_id = event.get("id")
            if event_id in entries:
                audit = TradeAudit(entries[event_id], event)
                audits.append(audit)

    return audits
