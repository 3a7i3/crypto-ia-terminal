"""Reference arithmetic for #546: assumptions in, conditional bounds out.

Offline design only. No clock reads, I/O, transport, price, publisher or authority.
Intervals are inclusive integer nanoseconds; caller evidence is not certified.
"""

from dataclasses import dataclass


def integer(value, *, nonnegative=False):
    if type(value) is not int:
        raise TypeError("EXACT_INTEGER_REQUIRED")
    if nonnegative and value < 0:
        raise ValueError("NONNEGATIVE_REQUIRED")
    return value


@dataclass(frozen=True)
class Span:
    lo: int
    hi: int

    def __post_init__(self):
        integer(self.lo)
        integer(self.hi)
        if self.lo > self.hi:
            raise ValueError("REVERSED_INTERVAL")


@dataclass(frozen=True)
class Window:
    scale: str
    span: Span

    def __post_init__(self):
        if not isinstance(self.scale, str) or not self.scale.strip():
            raise ValueError("EXPLICIT_COMMON_SCALE_REQUIRED")
        if self.scale.strip().upper() in ("UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE"):
            raise ValueError("UNQUALIFIED_SCALE")
        if type(self.span) is not Span:
            raise TypeError("SPAN_REQUIRED")


def chrony_point_bound_ns(system_offset_ns, root_dispersion_ns, root_delay_ns):
    """Conditional 4.2 formula, rounded outwards; no continuity guarantee."""
    if any(x is None for x in (system_offset_ns, root_dispersion_ns, root_delay_ns)):
        return None
    integer(system_offset_ns)
    integer(root_dispersion_ns, nonnegative=True)
    integer(root_delay_ns, nonnegative=True)
    return abs(system_offset_ns) + root_dispersion_ns + (root_delay_ns + 1) // 2


def grow_bound_ns(initial_ns, elapsed_ns, max_rate_ppb):
    """Requires an independently justified rate bound; never a default rate."""
    if any(x is None for x in (initial_ns, elapsed_ns, max_rate_ppb)):
        return None
    for value in (initial_ns, elapsed_ns, max_rate_ppb):
        integer(value, nonnegative=True)
    growth = (elapsed_ns * max_rate_ppb + 999999999) // 1000000000
    return initial_ns + growth


def event_window(native_ns, *, offset, quantization, event_to_stamp_lag, scale):
    """o=source-common; label=native+q-o; event=label-lag.

    The lag covers event-to-label delay only. Do not add cache residence again
    when the native timestamp already dates the cached book event.
    """
    if native_ns is not None:
        integer(native_ns)
    for span in (offset, quantization, event_to_stamp_lag):
        if span is not None and type(span) is not Span:
            raise TypeError("SPAN_OR_UNKNOWN_REQUIRED")
    if event_to_stamp_lag is not None and event_to_stamp_lag.lo < 0:
        raise ValueError("NEGATIVE_EVENT_TO_LABEL_LAG")
    if any(
        x is None for x in (native_ns, offset, quantization, event_to_stamp_lag, scale)
    ):
        return None
    return Window(
        scale,
        Span(
            native_ns + quantization.lo - offset.hi - event_to_stamp_lag.hi,
            native_ns + quantization.hi - offset.lo - event_to_stamp_lag.lo,
        ),
    )


def _pair(a, b):
    if a is None or b is None:
        return None
    if type(a) is not Window or type(b) is not Window:
        raise TypeError("WINDOW_OR_UNKNOWN_REQUIRED")
    if a.scale != b.scale:
        raise ValueError("DIFFERENT_COMMON_SCALES")
    return a.span, b.span


def age_window(now, event):
    pair = _pair(now, event)
    if pair is None:
        return None
    n, e = pair
    return Span(n.lo - e.hi, n.hi - e.lo)


def separation_window(a, b):
    pair = _pair(a, b)
    if pair is None:
        return None
    x, y = pair
    return Span(
        max(0, x.lo - y.hi, y.lo - x.hi), max(abs(x.lo - y.hi), abs(x.hi - y.lo))
    )


def classify_age(age, *, max_age_ns):
    integer(max_age_ns, nonnegative=True)
    if age is None:
        return "UNRESOLVED"
    if type(age) is not Span:
        raise TypeError("SPAN_REQUIRED")
    if age.hi < 0:
        return "FUTURE"
    if age.lo < 0:
        return "FUTURE_NOT_EXCLUDED"
    if age.lo > max_age_ns:
        return "STALE"
    if age.hi > max_age_ns:
        return "STALE_NOT_EXCLUDED"
    return "WITHIN_ASSUMPTIONS"


def classify_separation(gap, *, max_gap_ns):
    integer(max_gap_ns, nonnegative=True)
    if gap is None:
        return "UNRESOLVED"
    if type(gap) is not Span or gap.lo < 0:
        raise ValueError("NONNEGATIVE_SEPARATION_REQUIRED")
    if gap.lo > max_gap_ns:
        return "EXCEEDS_ASSUMPTIONS"
    if gap.hi > max_gap_ns:
        return "GAP_NOT_EXCLUDED"
    return "WITHIN_ASSUMPTIONS"
