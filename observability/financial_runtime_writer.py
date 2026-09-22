"""FIN-02R4 — governed passive runtime activation source boundary.

R4 wires the already-certified R1/R2/R3 chain into a bounded process-local
observer.  It owns no trading authority, starts no thread and constructs no
simulator, PPL authority runtime or exchange client.

Activation is deliberately OFF by default.  Runtime enablement requires an
explicit governed environment envelope and remains a separate operator action.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from financial_institute.models import ValuationObservation
from financial_institute.reconciliation import (
    ExternalFinancialObservation,
    ReconciliationPolicy,
)
from financial_institute.runtime_provenance import (
    FinancialRuntimeSemanticInputs,
)
from observability.financial_capture import (
    capture_coherent_financial_boundary,
)
from observability.financial_paths import (
    resolve_financial_reconciliation_path,
)
from observability.financial_producer import (
    PassiveFinancialProducerStatus,
    run_passive_financial_producer,
)


FIN02_RUNTIME_ENABLED_ENV = "FIN02_RUNTIME_ENABLED"
FIN02_RECONCILIATION_CODE_SHA_ENV = "FIN02_RECONCILIATION_CODE_SHA"
FIN02_CONTEXT_EVIDENCE_REF_ENV = "FIN02_CONTEXT_EVIDENCE_REF"
FIN02_EXPERIMENT_ID_ENV = "FIN02_EXPERIMENT_ID"
FIN02_VENUE_ENV = "FIN02_VENUE"
FIN02_MARKET_TYPE_ENV = "FIN02_MARKET_TYPE"
FIN02_STRATEGY_ID_ENV = "FIN02_STRATEGY_ID"
FIN02_STRATEGY_VERSION_ENV = "FIN02_STRATEGY_VERSION"

FIN02_MIN_REFRESH_INTERVAL_S_ENV = "FIN02_MIN_REFRESH_INTERVAL_S"
FIN02_MAX_MARK_AGE_S_ENV = "FIN02_MAX_MARK_AGE_S"
FIN02_ABSOLUTE_TOLERANCE_ENV = "FIN02_ABSOLUTE_TOLERANCE"
FIN02_RELATIVE_TOLERANCE_ENV = "FIN02_RELATIVE_TOLERANCE"
FIN02_RECONCILIATION_STALE_AFTER_S_ENV = (
    "FIN02_RECONCILIATION_STALE_AFTER_S"
)

DEFAULT_FIN02_MIN_REFRESH_INTERVAL_S = 30.0
DEFAULT_FIN02_MAX_MARK_AGE_S = Decimal("30")
DEFAULT_FIN02_ABSOLUTE_TOLERANCE = Decimal("0.000000000001")
DEFAULT_FIN02_RELATIVE_TOLERANCE = Decimal("0")
DEFAULT_FIN02_RECONCILIATION_STALE_AFTER_S = Decimal("90")

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


class FinancialRuntimeRefreshStatus(str, Enum):
    WRITTEN = "WRITTEN"
    SKIPPED_CADENCE = "SKIPPED_CADENCE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class FinancialRuntimeRefreshResult:
    status: FinancialRuntimeRefreshStatus
    artifact_path: str
    capture_id: str = ""
    runtime_provenance_id: str = ""
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is FinancialRuntimeRefreshStatus.WRITTEN


@dataclass(frozen=True)
class FinancialRuntimeActivationConfig:
    semantic_inputs: FinancialRuntimeSemanticInputs
    artifact_path: Path
    min_refresh_interval_s: float
    max_mark_age_s: Decimal
    reconciliation_policy: ReconciliationPolicy


def _optional_text(environ: Mapping[str, str], name: str) -> Optional[str]:
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _required_text(environ: Mapping[str, str], name: str) -> str:
    value = _optional_text(environ, name)
    if value is None:
        raise ValueError(f"{name} is required when FIN02 runtime is enabled")
    return value


def _decimal_env(
    environ: Mapping[str, str],
    name: str,
    default: Decimal,
) -> Decimal:
    raw = environ.get(name)
    return default if raw is None else Decimal(raw.strip())


def _float_env(
    environ: Mapping[str, str],
    name: str,
    default: float,
) -> float:
    raw = environ.get(name)
    return default if raw is None else float(raw.strip())


def load_financial_runtime_activation_config(
    environ: Mapping[str, str] | None = None,
) -> FinancialRuntimeActivationConfig | None:
    """Resolve explicit R4 activation evidence.

    Disabled is the safe default.  When enabled, semantic provenance fields are
    mandatory and never inferred from the current process, Git tree or epoch
    name.
    """

    source = os.environ if environ is None else environ
    enabled = source.get(FIN02_RUNTIME_ENABLED_ENV, "").strip().lower()
    if enabled in _FALSE_VALUES:
        return None
    if enabled not in _TRUE_VALUES:
        raise ValueError(
            "FIN02_RUNTIME_ENABLED must be one of "
            "true/false, 1/0, yes/no or on/off"
        )

    semantic_inputs = FinancialRuntimeSemanticInputs(
        reconciliation_code_sha=_required_text(
            source,
            FIN02_RECONCILIATION_CODE_SHA_ENV,
        ),
        context_evidence_ref=_required_text(
            source,
            FIN02_CONTEXT_EVIDENCE_REF_ENV,
        ),
        experiment_id=_required_text(source, FIN02_EXPERIMENT_ID_ENV),
        venue=_required_text(source, FIN02_VENUE_ENV),
        market_type=_required_text(source, FIN02_MARKET_TYPE_ENV),
        strategy_id=_optional_text(source, FIN02_STRATEGY_ID_ENV),
        strategy_version=_optional_text(
            source,
            FIN02_STRATEGY_VERSION_ENV,
        ),
    )

    min_interval = _float_env(
        source,
        FIN02_MIN_REFRESH_INTERVAL_S_ENV,
        DEFAULT_FIN02_MIN_REFRESH_INTERVAL_S,
    )
    if not math.isfinite(min_interval) or min_interval < 0:
        raise ValueError(
            "FIN02 minimum refresh interval must be finite and >= 0"
        )

    max_mark_age = _decimal_env(
        source,
        FIN02_MAX_MARK_AGE_S_ENV,
        DEFAULT_FIN02_MAX_MARK_AGE_S,
    )
    if max_mark_age < 0:
        raise ValueError("FIN02 max mark age must be >= 0")

    policy = ReconciliationPolicy(
        absolute_tolerance=_decimal_env(
            source,
            FIN02_ABSOLUTE_TOLERANCE_ENV,
            DEFAULT_FIN02_ABSOLUTE_TOLERANCE,
        ),
        relative_tolerance=_decimal_env(
            source,
            FIN02_RELATIVE_TOLERANCE_ENV,
            DEFAULT_FIN02_RELATIVE_TOLERANCE,
        ),
        stale_after_s=_decimal_env(
            source,
            FIN02_RECONCILIATION_STALE_AFTER_S_ENV,
            DEFAULT_FIN02_RECONCILIATION_STALE_AFTER_S,
        ),
    )

    return FinancialRuntimeActivationConfig(
        semantic_inputs=semantic_inputs,
        artifact_path=resolve_financial_reconciliation_path(source),
        min_refresh_interval_s=min_interval,
        max_mark_age_s=max_mark_age,
        reconciliation_policy=policy,
    )


class FinancialReconciliationRuntimeWriter:
    """Bounded, fail-passive end-of-cycle caller for the certified R1-R3 chain."""

    def __init__(
        self,
        config: FinancialRuntimeActivationConfig,
        *,
        wall_time_fn: Callable[[], float] = time.time,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._wall_time_fn = wall_time_fn
        self._monotonic_fn = monotonic_fn
        self._last_attempt_monotonic: Optional[float] = None

    @property
    def artifact_path(self) -> Path:
        return self._config.artifact_path

    @property
    def min_refresh_interval_s(self) -> float:
        return self._config.min_refresh_interval_s

    def maybe_refresh(
        self,
        simulator: Any,
        *,
        valuation_observations: Sequence[ValuationObservation] = (),
        external: Optional[ExternalFinancialObservation] = None,
        force: bool = False,
    ) -> FinancialRuntimeRefreshResult:
        """Attempt at most one refresh per eligible cadence window.

        The cadence advances on every eligible attempt, including failure.  A
        broken observational target therefore cannot create a tight retry loop
        or a post-delay catch-up burst.
        """

        path_text = str(self._config.artifact_path)
        try:
            now_mono = float(self._monotonic_fn())
            if (
                not force
                and self._last_attempt_monotonic is not None
                and now_mono - self._last_attempt_monotonic
                < self._config.min_refresh_interval_s
            ):
                return FinancialRuntimeRefreshResult(
                    status=FinancialRuntimeRefreshStatus.SKIPPED_CADENCE,
                    artifact_path=path_text,
                )

            self._last_attempt_monotonic = now_mono
            observed_at = Decimal(str(self._wall_time_fn()))
            capture = capture_coherent_financial_boundary(
                simulator,
                captured_at=observed_at,
                semantic_inputs=self._config.semantic_inputs,
                valuation_observations=valuation_observations,
            )
            produced = run_passive_financial_producer(
                capture,
                policy=self._config.reconciliation_policy,
                generated_at=observed_at,
                max_mark_age_s=self._config.max_mark_age_s,
                artifact_path=self._config.artifact_path,
                external=external,
            )
        except Exception as exc:
            return FinancialRuntimeRefreshResult(
                status=FinancialRuntimeRefreshStatus.FAILED,
                artifact_path=path_text,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        if produced.status is PassiveFinancialProducerStatus.FAILED:
            return FinancialRuntimeRefreshResult(
                status=FinancialRuntimeRefreshStatus.FAILED,
                artifact_path=produced.artifact_path,
                capture_id=produced.capture_id,
                runtime_provenance_id=produced.runtime_provenance_id,
                error_type=produced.error_type,
                error_message=produced.error_message,
            )

        return FinancialRuntimeRefreshResult(
            status=FinancialRuntimeRefreshStatus.WRITTEN,
            artifact_path=produced.artifact_path,
            capture_id=produced.capture_id,
            runtime_provenance_id=produced.runtime_provenance_id,
        )


def build_financial_runtime_writer_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    wall_time_fn: Callable[[], float] = time.time,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> FinancialReconciliationRuntimeWriter | None:
    """Build the R4 observer only after an explicit activation envelope."""

    config = load_financial_runtime_activation_config(environ)
    if config is None:
        return None
    return FinancialReconciliationRuntimeWriter(
        config,
        wall_time_fn=wall_time_fn,
        monotonic_fn=monotonic_fn,
    )


__all__ = [
    "DEFAULT_FIN02_ABSOLUTE_TOLERANCE",
    "DEFAULT_FIN02_MAX_MARK_AGE_S",
    "DEFAULT_FIN02_MIN_REFRESH_INTERVAL_S",
    "DEFAULT_FIN02_RECONCILIATION_STALE_AFTER_S",
    "DEFAULT_FIN02_RELATIVE_TOLERANCE",
    "FIN02_RUNTIME_ENABLED_ENV",
    "FinancialReconciliationRuntimeWriter",
    "FinancialRuntimeActivationConfig",
    "FinancialRuntimeRefreshResult",
    "FinancialRuntimeRefreshStatus",
    "build_financial_runtime_writer_from_env",
    "load_financial_runtime_activation_config",
]
