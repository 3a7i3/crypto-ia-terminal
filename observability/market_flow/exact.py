"""Exact decimal arithmetic, independent of the ambient ``decimal`` context.

Accepted inputs are decimal texts of at most 30+30 digits, so one product has
at most 120 digits and sums add only a few more. Every arithmetic section runs
under ``EXACT``: 1000 digits of precision and the traps ``Inexact`` and
``Rounded`` armed. A result is therefore either exact or an exception; it is
never silently rounded and never labelled EXACT after a rounding.
"""

from decimal import (
    Clamped, Context, DivisionByZero, Inexact, InvalidOperation, Overflow, Rounded, Subnormal,
    Underflow, localcontext,
)
from functools import wraps

EXACT = Context(
    prec=1000, Emax=999999, Emin=-999999, rounding="ROUND_HALF_EVEN", capitals=1, clamp=0,
    flags=[],
    traps=[Inexact, Rounded, InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal, Clamped],
)


def exact(fn):
    """Run ``fn`` under the exact context (the caller's context is restored)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with localcontext(EXACT):
            return fn(*args, **kwargs)

    return wrapper
