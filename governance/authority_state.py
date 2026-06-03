"""
governance/authority_state.py — État canonique G2 de l'autorité de trading.

Hiérarchie des niveaux (du plus restrictif au plus permissif) :

    EMERGENCY   →  Arrêt total immédiat. Zéro exchange I/O.
    SAFE_MODE   →  Blocage trading. Lecture exchange possible.
    RESTRICTED  →  Trading suspendu. Positions existantes monitorées.
    WARNING     →  Trading autorisé, taille réduite (50%). Surveillance accrue.
    CLEAR       →  Fonctionnement nominal. Trading plein.

Adapters vers les états existants :
    - RuntimeStateMachine (quant_hedge_ai) :
        NORMAL    → CLEAR
        DEGRADED  → WARNING
        CRITICAL  → RESTRICTED
        SAFE_MODE → SAFE_MODE
        RECOVERY  → RESTRICTED
    - StateManager (system) :
        TRADING   → CLEAR
        READY     → WARNING
        RISK_OFF  → RESTRICTED
        DEGRADED  → RESTRICTED
        RECOVERY  → RESTRICTED
        PANIC     → EMERGENCY
        SHUTDOWN  → EMERGENCY

Usage:
    from governance.authority_state import AuthorityLevel, TRADING_POLICY

    level = AuthorityLevel.WARNING
    policy = TRADING_POLICY[level]
    if policy.can_trade:
        # authorised, apply policy.size_factor
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuthorityLevel(str, Enum):
    """
    Niveau d'autorité unique — source de vérité G2.

    Ordonné du plus restrictif (0) au plus permissif (4).
    Comparaison de niveaux : AuthorityLevel.CLEAR > AuthorityLevel.WARNING
    """

    EMERGENCY = "EMERGENCY"  # 0 — arrêt total, zéro I/O exchange
    SAFE_MODE = "SAFE_MODE"  # 1 — blocage trading, lecture possible
    RESTRICTED = "RESTRICTED"  # 2 — trading suspendu, monitoring actif
    WARNING = "WARNING"  # 3 — trading réduit, surveillance accrue
    CLEAR = "CLEAR"  # 4 — nominal

    # Ordre pour comparaisons (plus petit = plus restrictif)
    _ignore_ = ["_ORDER"]

    def severity(self) -> int:
        """Retourne le niveau de sévérité (0=max, 4=min)."""
        return _SEVERITY[self]

    def is_more_restrictive_than(self, other: "AuthorityLevel") -> bool:
        return self.severity() < other.severity()

    def __lt__(self, other: "AuthorityLevel") -> bool:
        return self.severity() < other.severity()

    def __le__(self, other: "AuthorityLevel") -> bool:
        return self.severity() <= other.severity()

    def __gt__(self, other: "AuthorityLevel") -> bool:
        return self.severity() > other.severity()

    def __ge__(self, other: "AuthorityLevel") -> bool:
        return self.severity() >= other.severity()


_SEVERITY: dict[AuthorityLevel, int] = {
    AuthorityLevel.EMERGENCY: 0,
    AuthorityLevel.SAFE_MODE: 1,
    AuthorityLevel.RESTRICTED: 2,
    AuthorityLevel.WARNING: 3,
    AuthorityLevel.CLEAR: 4,
}


@dataclass(frozen=True)
class TradingPolicy:
    """Règles d'exécution associées à un niveau d'autorité."""

    can_trade: bool
    can_fetch_data: bool
    can_place_orders: bool
    size_factor: float  # multiplicateur appliqué à l'allocation nominale
    description: str


TRADING_POLICY: dict[AuthorityLevel, TradingPolicy] = {
    AuthorityLevel.CLEAR: TradingPolicy(
        can_trade=True,
        can_fetch_data=True,
        can_place_orders=True,
        size_factor=1.0,
        description="Fonctionnement nominal. Trading plein.",
    ),
    AuthorityLevel.WARNING: TradingPolicy(
        can_trade=True,
        can_fetch_data=True,
        can_place_orders=True,
        size_factor=0.5,
        description="Surveillance accrue. Taille réduite à 50%.",
    ),
    AuthorityLevel.RESTRICTED: TradingPolicy(
        can_trade=False,
        can_fetch_data=True,
        can_place_orders=False,
        size_factor=0.0,
        description="Trading suspendu. Positions existantes monitorées.",
    ),
    AuthorityLevel.SAFE_MODE: TradingPolicy(
        can_trade=False,
        can_fetch_data=True,
        can_place_orders=False,
        size_factor=0.0,
        description="Blocage total trading. Lecture exchange possible.",
    ),
    AuthorityLevel.EMERGENCY: TradingPolicy(
        can_trade=False,
        can_fetch_data=False,
        can_place_orders=False,
        size_factor=0.0,
        description="Arrêt total immédiat. Zéro exchange I/O.",
    ),
}


# ---------------------------------------------------------------------------
# Adapters — traduction depuis les états legacy
# ---------------------------------------------------------------------------


def from_runtime_state(runtime_state_value: str) -> AuthorityLevel:
    """
    Traduit un SystemState de RuntimeStateMachine (quant_hedge_ai) vers AuthorityLevel.

    RuntimeStateMachine states: NORMAL, DEGRADED, CRITICAL, SAFE_MODE, RECOVERY
    """
    _MAP = {
        "NORMAL": AuthorityLevel.CLEAR,
        "DEGRADED": AuthorityLevel.WARNING,
        "CRITICAL": AuthorityLevel.RESTRICTED,
        "SAFE_MODE": AuthorityLevel.SAFE_MODE,
        "RECOVERY": AuthorityLevel.RESTRICTED,
    }
    return _MAP.get(runtime_state_value.upper(), AuthorityLevel.SAFE_MODE)


def from_system_state(system_state_value: str) -> AuthorityLevel:
    """
    Traduit un SystemState de system/state_manager vers AuthorityLevel.

    StateManager states: BOOTING, SYNCING, READY, TRADING, RISK_OFF,
                         DEGRADED, RECOVERY, SHUTDOWN, PANIC
    """
    _MAP = {
        "BOOTING": AuthorityLevel.RESTRICTED,
        "SYNCING": AuthorityLevel.RESTRICTED,
        "READY": AuthorityLevel.WARNING,
        "TRADING": AuthorityLevel.CLEAR,
        "RISK_OFF": AuthorityLevel.RESTRICTED,
        "DEGRADED": AuthorityLevel.RESTRICTED,
        "RECOVERY": AuthorityLevel.RESTRICTED,
        "SHUTDOWN": AuthorityLevel.EMERGENCY,
        "PANIC": AuthorityLevel.EMERGENCY,
    }
    return _MAP.get(system_state_value.upper(), AuthorityLevel.SAFE_MODE)
