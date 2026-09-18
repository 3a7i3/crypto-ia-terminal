"""PPL-02E process-lifetime PAPER lifecycle authority selector.

R1 froze the single-authority boundary. R2/R3 added replay-complete durable
facts and the scientific-capital/compatibility handoff. R4 wires the explicit
PPL authority runtime.

Authority is resolved once at process bootstrap and passed explicitly to
mutation-capable components. Hot authority changes inside one process/epoch
remain forbidden.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping, Optional


PAPER_LIFECYCLE_AUTHORITY_ENV = "PAPER_LIFECYCLE_AUTHORITY"


class PaperLifecycleAuthority(str, Enum):
    """Closed vocabulary for PAPER lifecycle authority."""

    LEGACY_AUTHORITY = "LEGACY_AUTHORITY"
    PPL_SHADOW = "PPL_SHADOW"
    PPL_AUTHORITY = "PPL_AUTHORITY"

    @property
    def legacy_mutation_allowed(self) -> bool:
        """Whether legacy MexcSimulator lifecycle mutation is authoritative."""

        return self in {
            PaperLifecycleAuthority.LEGACY_AUTHORITY,
            PaperLifecycleAuthority.PPL_SHADOW,
        }

    @property
    def ppl_is_authoritative(self) -> bool:
        return self is PaperLifecycleAuthority.PPL_AUTHORITY


class PaperAuthorityConfigError(ValueError):
    """Invalid PAPER lifecycle authority configuration."""


_ALIASES = {
    "legacy": PaperLifecycleAuthority.LEGACY_AUTHORITY,
    "legacy_authority": PaperLifecycleAuthority.LEGACY_AUTHORITY,
    "LEGACY_AUTHORITY": PaperLifecycleAuthority.LEGACY_AUTHORITY,
    "shadow": PaperLifecycleAuthority.PPL_SHADOW,
    "ppl_shadow": PaperLifecycleAuthority.PPL_SHADOW,
    "PPL_SHADOW": PaperLifecycleAuthority.PPL_SHADOW,
    "ppl": PaperLifecycleAuthority.PPL_AUTHORITY,
    "ppl_authority": PaperLifecycleAuthority.PPL_AUTHORITY,
    "PPL_AUTHORITY": PaperLifecycleAuthority.PPL_AUTHORITY,
}


def parse_paper_lifecycle_authority(
    value: Optional[str],
) -> PaperLifecycleAuthority:
    """Parse one explicit authority value.

    Missing/blank configuration preserves the pre-PPL-02E runtime:
    LEGACY_AUTHORITY.  Invalid configuration fails closed instead of silently
    choosing an authority.
    """

    if value is None or not str(value).strip():
        return PaperLifecycleAuthority.LEGACY_AUTHORITY

    raw = str(value).strip()
    mode = _ALIASES.get(raw)
    if mode is None:
        mode = _ALIASES.get(raw.lower())
    if mode is None:
        allowed = ", ".join(item.value for item in PaperLifecycleAuthority)
        raise PaperAuthorityConfigError(
            f"{PAPER_LIFECYCLE_AUTHORITY_ENV}={raw!r} invalid; allowed={allowed}"
        )
    return mode


def resolve_paper_lifecycle_authority(
    environ: Mapping[str, str],
) -> PaperLifecycleAuthority:
    """Resolve authority once from an explicit environment mapping."""

    return parse_paper_lifecycle_authority(
        environ.get(PAPER_LIFECYCLE_AUTHORITY_ENV)
    )
