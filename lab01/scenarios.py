"""Scénarios déterministes et critères de réussite explicites."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from lab01.risk import RiskLimits
from lab01.strategy import SignalConfig


@dataclass(frozen=True)
class DataSpec:
    seed: int
    n_bars: int = 80
    start_price: float = 100.0
    drift_bps: float = 0.0
    vol_bps: float = 15.0
    shocks: tuple[tuple[int, float], ...] = ()


@dataclass(frozen=True)
class Expect:
    final_state: str
    risk_reason_code: str  # "APPROVED" ou code de rejet
    required_events: tuple[str, ...]
    forbidden_events: tuple[str, ...] = ()
    pnl_expected: bool = False
    error_code: str | None = None


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    data: DataSpec
    signal: SignalConfig = field(default_factory=SignalConfig)
    risk: RiskLimits = field(default_factory=RiskLimits)
    exec_seed: int = 7
    fault_on_orders: tuple[int, ...] = ()  # indices d'ordre (1 = entrée)
    expect: Expect = None  # type: ignore[assignment]

    def config_dict(self) -> dict:
        return asdict(self)


_BASE = DataSpec(seed=11, shocks=((40, 60.0),))

SCENARIOS: dict[str, Scenario] = {
    "accepted_closed": Scenario(
        name="accepted_closed",
        title="Décision acceptée puis simulation clôturée",
        data=_BASE,
        expect=Expect(
            final_state="POSTMORTEM_ANALYZED",
            risk_reason_code="APPROVED",
            required_events=(
                "SIGNAL_EMITTED",
                "RISK_EVALUATED",
                "ORDER_FILLED",
                "POSITION_OPENED",
                "POSITION_CLOSED",
            ),
            forbidden_events=("EXECUTION_ERROR", "RISK_REJECTED"),
            pnl_expected=True,
        ),
    ),
    "risk_rejected": Scenario(
        name="risk_rejected",
        title="Rejet par le risque (volatilité au-dessus du plafond)",
        data=DataSpec(seed=11, vol_bps=150.0),
        expect=Expect(
            final_state="REJECTED",
            risk_reason_code="VOLATILITY_ABOVE_LIMIT",
            required_events=("SIGNAL_EMITTED", "RISK_EVALUATED", "RISK_REJECTED"),
            forbidden_events=("ORDER_SUBMITTED", "ORDER_FILLED", "POSITION_OPENED"),
        ),
    ),
    "execution_error": Scenario(
        name="execution_error",
        title="Erreur d'exécution simulée, visible et traçable",
        data=_BASE,
        fault_on_orders=(1,),
        expect=Expect(
            final_state="FAILED",
            risk_reason_code="APPROVED",
            required_events=(
                "SIGNAL_EMITTED",
                "RISK_EVALUATED",
                "ORDER_SUBMITTED",
                "EXECUTION_ERROR",
            ),
            forbidden_events=("ORDER_FILLED", "POSITION_OPENED", "POSITION_CLOSED"),
            error_code="SIMULATED_EXCHANGE_TIMEOUT",
        ),
    ),
}
