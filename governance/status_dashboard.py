"""
governance/status_dashboard.py — G3 : Dashboard de Gouvernance.

Affiche l'état complet du système en < 10 secondes (Constitution, Article G3).

Deux modes :
    - print_status()  : affichage terminal (CLI, debug)
    - get_status_dict(): données brutes pour intégration UI/API

Usage:
    from governance.status_dashboard import print_governance_status

    print_governance_status()

Exemple de sortie :

    ╔══════════════════════════════════════════════════╗
    ║         GOVERNANCE DASHBOARD — 2026-06-02       ║
    ╠══════════════════════════════════════════════════╣
    ║  SYSTEM STATUS : SAFE_MODE                      ║
    ║  Blocage total trading. Lecture exchange OK.    ║
    ╠══════════════════════════════════════════════════╣
    ║  SOURCES D'ARRÊT                                ║
    ║  • [SAFE_MODE] ExchangeMonitor                 ║
    ║      exchange timeout                           ║
    ║      depuis 02:31 UTC                           ║
    ║  • [WARNING]   SelfAwareness                   ║
    ║      anomaly score 0.91                         ║
    ╠══════════════════════════════════════════════════╣
    ║  POLITIQUE ACTIVE                               ║
    ║  can_trade      : ✗                             ║
    ║  can_fetch_data : ✓                             ║
    ║  size_factor    : 0.0x                          ║
    ╠══════════════════════════════════════════════════╣
    ║  DEPUIS  : 02:31:44 UTC                         ║
    ║  CHANGÉ  : 02:31:44 UTC                         ║
    ╚══════════════════════════════════════════════════╝
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from governance.authority_state import AuthorityLevel
from governance.trading_authority import AuthoritySnapshot, trading_authority

_STATUS_COLORS = {
    AuthorityLevel.CLEAR: "\033[92m",  # vert
    AuthorityLevel.WARNING: "\033[93m",  # jaune
    AuthorityLevel.RESTRICTED: "\033[33m",  # orange
    AuthorityLevel.SAFE_MODE: "\033[91m",  # rouge
    AuthorityLevel.EMERGENCY: "\033[1;91m",  # rouge gras
}
_RESET = "\033[0m"
_WIDTH = 52


def _box(text: str, width: int = _WIDTH) -> str:
    pad = width - 2 - len(text)
    return "|  " + text + " " * max(pad, 0) + "|"


def _sep(char: str = "=", width: int = _WIDTH) -> str:
    return "+" + char * (width - 2) + "+"


def format_governance_status(snapshot: AuthoritySnapshot, *, color: bool = True) -> str:
    """
    Formate le snapshot de gouvernance en texte lisible.

    Garantit un diagnostic complet en < 10 secondes (Constitution G3).
    """
    level = snapshot.current_level
    color_code = _STATUS_COLORS.get(level, "") if color else ""
    reset = _RESET if color else ""

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        _sep("="),
        _box("GOVERNANCE DASHBOARD -- " + now_str),
        _sep("="),
        _box(color_code + "SYSTEM STATUS : " + level.value + reset),
        _box(snapshot.policy.description),
        _sep("-"),
    ]

    if snapshot.active_halts:
        lines.append(_box("SOURCES D'ARRET"))
        for h in snapshot.active_halts:
            lines.append(_box("  [" + h.level.value + "] " + h.source))
            lines.append(_box("    reason : " + h.reason))
            lines.append(_box("    since  : " + h.timestamp_utc))
    else:
        lines.append(_box("SOURCES D'ARRET : aucune (nominal)"))

    lines += [
        _sep("-"),
        _box("POLITIQUE ACTIVE"),
        _box("can_trade      : " + ("YES" if snapshot.policy.can_trade else "NO")),
        _box("can_fetch_data : " + ("YES" if snapshot.policy.can_fetch_data else "NO")),
        _box("size_factor    : " + str(snapshot.policy.size_factor) + "x"),
        _sep("-"),
        _box("DEPUIS  : " + snapshot.since_utc),
        _box("CHANGE  : " + snapshot.last_change_utc),
        _sep("="),
    ]
    return "\n".join(lines)


def print_governance_status(*, color: bool = True) -> None:
    """
    Affiche le statut complet de gouvernance dans le terminal.

    Appeler à tout moment pour diagnostiquer l'état du système.
    """
    snapshot = trading_authority.status_snapshot()
    print(format_governance_status(snapshot, color=color))


def get_status_dict() -> Dict[str, Any]:
    """
    Retourne le statut sous forme de dict JSON-sérialisable.

    Pour intégration dans des APIs REST, Telegram, ou dashboards Panel/Streamlit.
    """
    snapshot = trading_authority.status_snapshot()
    return snapshot.as_dict()


def get_status_line() -> str:
    """
    Retourne une ligne de statut ultra-compacte.

    Exemple : "SAFE_MODE (ExchangeMonitor, SelfAwareness) since 02:31 UTC"
    """
    snapshot = trading_authority.status_snapshot()
    sources = [h.source for h in snapshot.active_halts]
    src_str = f" ({', '.join(sources)})" if sources else ""
    return f"{snapshot.current_level.value}{src_str} since {snapshot.since_utc}"
