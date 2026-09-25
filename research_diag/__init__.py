"""Offline factual diagnostics for RL-DIAG-01."""

from .factual import (
    DiagnosticError,
    FactualAttributionResult,
    diagnose_factual_dataset,
)

__all__ = [
    "DiagnosticError",
    "FactualAttributionResult",
    "diagnose_factual_dataset",
]
