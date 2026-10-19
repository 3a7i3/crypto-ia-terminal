"""Descriptive PPL lifecycle statistics; no FIN reconciliation or verdict."""

from decimal import Decimal, localcontext
from typing import Any


def build_burn_in_statistics(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Consume an already validated, complete BurnInStatusSnapshot only."""
    rows = snapshot["lifecycle_history"]
    closed = [row for row in rows if row["status"] == "CLOSED"]
    counts = snapshot["lifecycle_counts"]
    if len(rows) != counts["total"] or any(
        sum(row["status"] == status for row in rows) != counts[key]
        for key, status in [
            ("closed", "CLOSED"),
            ("open", "OPEN"),
            ("unresolved", "UNRESOLVED"),
        ]
    ):
        raise ValueError("INCOMPLETE_LIFECYCLE_POPULATION")
    with localcontext() as ctx:
        inputs = [
            Decimal(str(row[key]))
            for row in closed
            for key in (
                "net_realized_pnl_usd",
                "gross_pnl_usd",
                "entry_fee_usd",
                "exit_fee_usd",
            )
        ]
        if any(not value.is_finite() for value in inputs):
            raise ValueError("NONFINITE_STATISTIC_INPUT")
        # Exact sums of decimal renderings, including cancellation across exponents.
        ctx.prec = max(
            40,
            max((v.adjusted() for v in inputs), default=0)
            - min((v.as_tuple().exponent for v in inputs), default=0)
            + len(str(len(inputs)))
            + 4,
        )

        def divide(numerator, denominator):
            with localcontext() as ratio_context:
                ratio_context.prec = 40
                return numerator / denominator

        def total(key):
            values = [Decimal(str(row[key])) for row in closed]
            if any(not value.is_finite() for value in values):
                raise ValueError("NONFINITE_STATISTIC_INPUT")
            return sum(values, Decimal(0))

        pnl = [Decimal(str(row["net_realized_pnl_usd"])) for row in closed]
        if any(not value.is_finite() for value in pnl):
            raise ValueError("NONFINITE_STATISTIC_INPUT")
        gains = [value for value in pnl if value > 0]
        losses = [value for value in pnl if value < 0]
        gain = sum(gains, Decimal(0))
        loss = -sum(losses, Decimal(0))

        def number(value):
            return None if value is None else str(value)

        metrics = {
            "net_realized_pnl_usd": number(total("net_realized_pnl_usd"))
            if closed
            else None,
            "gross_pnl_usd": number(total("gross_pnl_usd")) if closed else None,
            "closed_fees_usd": number(total("entry_fee_usd") + total("exit_fee_usd"))
            if closed
            else None,
            "win_rate_pct": number(divide(Decimal(len(gains)) * 100, len(closed)))
            if closed
            else None,
            "profit_factor": number(divide(gain, loss)) if loss else None,
            "average_gain_usd": number(divide(gain, len(gains))) if gains else None,
            "average_loss_usd": number(divide(-loss, len(losses))) if losses else None,
            "average_net_pnl_usd": number(
                divide(total("net_realized_pnl_usd"), len(closed))
            )
            if closed
            else None,
        }
    return {
        "schema_version": "1.0.0",
        "product": "BurnInDescriptiveStatistics",
        "authority": "PPL_AUTHORITY_PRESENTATION",
        "mode": "READ_ONLY",
        **{
            key: snapshot[key]
            for key in (
                "paper_epoch_id",
                "config_snapshot_hash",
                "ppl_stream_sha256",
                "last_sequence",
                "generated_at_utc",
            )
        },
        "population": {
            **snapshot["lifecycle_counts"],
            "wins": len(gains),
            "losses": len(losses),
            "breakeven": len(closed) - len(gains) - len(losses),
        },
        "metrics": metrics,
        "limitations": [
            "PPL_ONLY_NOT_FIN_RECONCILED",
            "CLOSED_ONLY_OPEN_AND_UNRESOLVED_EXCLUDED",
            "NO_CERTIFICATION_OR_FORWARD_PERFORMANCE_CLAIM",
            "ZERO_DENOMINATOR_IS_NOT_AVAILABLE",
        ],
    }
