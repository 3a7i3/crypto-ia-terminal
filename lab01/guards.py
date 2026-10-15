"""Garde-fous du LAB : réseau sortant, secrets, chemins de production.

Défense en profondeur dans le processus. L'application réelle de la règle
« réseau sortant refusé » est celle de l'OS (unité systemd, namespace réseau) ;
ces gardes la complètent et la rendent testable hors hôte.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
from collections.abc import Iterator
from pathlib import Path

FORBIDDEN_ENV_PATTERN = re.compile(
    r"(API[_-]?KEY|API[_-]?SECRET|SECRET[_-]?KEY|PASSPHRASE|MEXC|BINANCE|BYBIT|OKX|"
    r"KUCOIN|EXCHANGE|PRIVATE[_-]?KEY|TELEGRAM[_-]?(BOT[_-]?)?TOKEN)",
    re.IGNORECASE,
)
# Préfixes de production : jamais utilisés comme sortie du LAB.
FORBIDDEN_PATH_PREFIXES = (
    "/home/mathieu/crypto_ai_terminal",
    "/opt/crypto-ai-terminal/operator",
    "/srv/claude-audit",
)
FORBIDDEN_PATH_PARTS = ("databases", "burn_in", "ppl", "fin_capture")


class LabGuardError(RuntimeError):
    """Violation d'un garde-fou : le LAB refuse de s'exécuter."""


def forbidden_env_names(environ: dict[str, str] | None = None) -> list[str]:
    """Noms (jamais les valeurs) des variables ressemblant à un secret exchange."""
    env = os.environ if environ is None else environ
    return sorted(k for k in env if FORBIDDEN_ENV_PATTERN.search(k))


def assert_clean_environment(environ: dict[str, str] | None = None) -> None:
    names = forbidden_env_names(environ)
    if names:
        raise LabGuardError(
            "ENV_SECRET_LIKE_VARIABLES_PRESENT: "
            + ",".join(names)
            + " (noms seulement ; les valeurs ne sont jamais lues)"
        )


def assert_safe_output_dir(path: str | os.PathLike) -> Path:
    p = Path(path).expanduser().resolve()
    s = str(p)
    for prefix in FORBIDDEN_PATH_PREFIXES:
        if s == prefix or s.startswith(prefix + "/"):
            raise LabGuardError(f"OUTPUT_DIR_IN_PRODUCTION_TREE: {prefix}")
    parts = {x.lower() for x in p.parts}
    for bad in FORBIDDEN_PATH_PARTS:
        if bad in parts:
            raise LabGuardError(f"OUTPUT_DIR_COMPONENT_FORBIDDEN: {bad}")
    return p


class NetworkDenied(OSError):
    """Tentative de connexion réseau pendant une simulation."""


@contextlib.contextmanager
def deny_network() -> Iterator[None]:
    """Refuse toute résolution/connexion non locale-fichier dans le processus."""
    originals = (
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.getaddrinfo,
        socket.create_connection,
    )

    def _deny(*_a, **_k):
        raise NetworkDenied("NETWORK_DENIED_DURING_SIMULATION")

    socket.socket.connect = _deny  # type: ignore[method-assign]
    socket.socket.connect_ex = _deny  # type: ignore[method-assign]
    socket.getaddrinfo = _deny  # type: ignore[assignment]
    socket.create_connection = _deny  # type: ignore[assignment]
    try:
        yield
    finally:
        (
            socket.socket.connect,
            socket.socket.connect_ex,
            socket.getaddrinfo,
            socket.create_connection,
        ) = originals  # type: ignore[assignment]
