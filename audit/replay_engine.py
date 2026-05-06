"""
Replay Engine — Rejoint les trades avec traçage complet
Montre exactement ce qui s'est passé tick par tick
"""

from typing import Any
from tracker_system.engine.exit_engine import ExitEngine
from tracker_system.engine.exit_factory import build_exit_engine
from meta_learning.decision_engine import DecisionEngine


class TradeReplay:
    def __init__(
        self,
        entry_event: dict[str, Any],
        exit_event: dict[str, Any],
        decision_engine: DecisionEngine | None = None,
    ):
        self.entry = entry_event
        self.exit = exit_event
        self.decision_engine = decision_engine

    def replay_with_trace(self) -> dict[str, Any]:
        """Rejoint le trade avec traçage complet."""
        path = [float(p) for p in self.exit.get("price_path", [])]
        entry_price = float(self.entry.get("entry_price", 0.0))
        regime = self.entry.get("regime")

        engine = build_exit_engine(regime, self.entry.get("confidence"))

        trace = []
        position = {
            "entry_price": entry_price,
            "side": self.entry.get("side", "BUY"),
            "max_price": entry_price,
            "min_price": entry_price,
        }

        for i, price in enumerate(path):
            position["max_price"] = max(position["max_price"], float(price))
            position["min_price"] = min(position["min_price"], float(price))

            exit_reason = engine.check_exit(position, float(price), {"regime": regime})

            trace.append({
                "tick": i,
                "price": float(price),
                "max": position["max_price"],
                "min": position["min_price"],
                "exit_triggered": exit_reason,
            })

            if exit_reason:
                break

        return {
            "symbol": self.entry.get("symbol"),
            "regime": regime,
            "entry_price": entry_price,
            "exit_reason_recorded": self.exit.get("exit_reason"),
            "path_length": len(path),
            "trace": trace,
            "total_ticks": len(trace),
        }

    def get_alternative_exits(self, tp_values: list[float] | None = None, sl_values: list[float] | None = None) -> list[dict[str, Any]]:
        """Teste exit alternatives."""
        if tp_values is None:
            tp_values = [0.01, 0.015, 0.02, 0.025, 0.03]
        if sl_values is None:
            sl_values = [0.005, 0.01, 0.015]

        entry_price = float(self.entry.get("entry_price", 0.0))
        path = [float(p) for p in self.exit.get("price_path", [])]

        alternatives = []
        for tp in tp_values:
            for sl in sl_values:
                from tracker_system.engine.exit_engine import ExitEngine
                from tracker_system.engine.rules.tp_sl import TPSLRule

                engine = ExitEngine([TPSLRule(tp=tp, sl=sl)])
                reason, exit_price = engine.check_path(
                    {
                        "entry_price": entry_price,
                        "side": self.entry.get("side", "BUY"),
                        "max_price": entry_price,
                        "min_price": entry_price,
                    },
                    path,
                )

                if reason:
                    pnl_pct = (float(exit_price) - entry_price) / entry_price
                    alternatives.append({
                        "tp": tp,
                        "sl": sl,
                        "exit_price": float(exit_price),
                        "pnl_pct": pnl_pct,
                        "reason": reason,
                    })

        return sorted(alternatives, key=lambda x: x["pnl_pct"], reverse=True)

    def analyze_mfe_mae(self) -> dict[str, Any]:
        """Analyse MFE vs MAE."""
        entry_price = float(self.entry.get("entry_price", 0.0))
        actual_pnl = float(self.exit.get("pnl_pct", 0.0))
        mfe = float(self.exit.get("mfe", 0.0))
        mae = float(self.exit.get("mae", 0.0))
        path = self.exit.get("price_path", [])

        if not path:
            return {}

        unrealized_gains = mfe
        unrealized_losses = mae
        realized_gain = actual_pnl if actual_pnl > 0 else 0.0
        realized_loss = actual_pnl if actual_pnl < 0 else 0.0

        return {
            "unrealized_gains": unrealized_gains,
            "unrealized_losses": unrealized_losses,
            "realized_gain": realized_gain,
            "realized_loss": realized_loss,
            "pnl_ratio": realized_gain / abs(realized_loss) if realized_loss < 0 else 0.0,
            "capture_ratio": actual_pnl / mfe if mfe > 0 else 0.0,
        }


class ReplayEngine:
    def __init__(self, audits: list):
        self.audits = audits

    def replay_all(self, decision_engine: DecisionEngine | None = None) -> list[dict[str, Any]]:
        """Rejoint tous les trades."""
        replays = []
        for audit in self.audits:
            replay = TradeReplay(audit.entry, audit.exit, decision_engine)
            replays.append(replay.replay_with_trace())
        return replays

    def get_decision_quality_report(self) -> dict[str, Any]:
        """Rapport sur qualité des décisions."""
        qualities = {"SKILLED": 0, "LUCKY": 0, "MISTAKE": 0, "UNLUCKY": 0, "BREAKEVEN": 0}

        for audit in self.audits:
            quality = audit.get_quality_label()
            qualities[quality] += 1

        total = len(self.audits)
        return {
            "total_trades": total,
            "breakdown": {k: f"{v/total:.1%}" for k, v in qualities.items()},
            "skilled_ratio": (qualities["SKILLED"] + qualities["LUCKY"]) / total if total else 0.0,
        }
