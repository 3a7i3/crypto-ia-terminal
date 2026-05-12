"""
setup_binance.py — CLI interactif pour configurer les clés API Binance.
=======================================================================
Guide l'utilisateur pas à pas pour choisir un mode (paper / testnet / futures_demo / live),
saisir les clés, les tester, puis les persister dans un fichier .env.

Usage :
    python -m quant_hedge_ai.setup_binance
    # ou :
    python quant_hedge_ai/setup_binance.py

Sécurité :
  - Les clés ne sont jamais affichées en clair dans les logs.
  - Les clés ne sont JAMAIS hardcodées dans le code.
  - Le fichier .env est créé/mis à jour (mode append protégé).
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FILE = Path(".env")

# ── Palette CLI ──────────────────────────────────────────────────────────────

_BOLD  = "\033[1m"
_GREEN = "\033[92m"
_CYAN  = "\033[96m"
_RED   = "\033[91m"
_YELL  = "\033[93m"
_RESET = "\033[0m"


def _print(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{_RESET}" if color else msg)


def _section(title: str) -> None:
    print(f"\n{_BOLD}{'─'*60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {title}{_RESET}")
    print(f"{_BOLD}{'─'*60}{_RESET}")


def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
    full_prompt = f"  {prompt}"
    if default:
        full_prompt += f" [{default}]"
    full_prompt += " : "
    if secret:
        val = getpass.getpass(full_prompt)
    else:
        val = input(full_prompt).strip()
    return val if val else default


def _confirm(prompt: str) -> bool:
    resp = input(f"  {prompt} [o/N] : ").strip().lower()
    return resp in ("o", "oui", "y", "yes")


# ── Lecture / écriture .env ──────────────────────────────────────────────────

def _read_env() -> dict[str, str]:
    """Lit le fichier .env et retourne un dict clé→valeur."""
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _write_env(updates: dict[str, str]) -> None:
    """Met à jour (ou crée) le fichier .env avec les nouvelles valeurs."""
    existing = _read_env()
    merged   = {**existing, **updates}

    lines = ["# Binance Connector — généré par setup_binance.py", ""]
    for k, v in merged.items():
        lines.append(f'{k}="{v}"')

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _print(f"\n  ✅  .env mis à jour → {ENV_FILE.absolute()}", _GREEN)


# ── Test de connexion ─────────────────────────────────────────────────────────

def _test_connection(env_updates: dict[str, str]) -> bool:
    """Applique les variables d'env temporairement et teste la connexion."""
    # Injecter temporairement dans l'environnement du process
    old = {}
    for k, v in env_updates.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        # Import ici pour prendre les nouvelles vars d'env en compte
        from quant_hedge_ai.binance_connector import BinanceConnector
        bc     = BinanceConnector()
        result = bc.test_connection()
        if result.get("status") == "ok":
            _print(
                f"\n  ✅  Connexion réussie ! mode={result['mode']}  "
                f"balance={result['balance_usdt']:.2f} USDT  lat={result['latency_ms']}ms",
                _GREEN,
            )
            return True
        else:
            _print(f"\n  ❌  Connexion échouée : {result.get('error', '?')}", _RED)
            return False
    except Exception as exc:
        _print(f"\n  ❌  Erreur lors du test : {exc}", _RED)
        return False
    finally:
        # Restaurer les variables d'env
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── Assistants par mode ───────────────────────────────────────────────────────

def _setup_paper() -> dict[str, str]:
    """Mode paper — aucune clé nécessaire."""
    _print("\n  Mode PAPER sélectionné — aucune clé API requise.", _CYAN)
    capital = _ask("Capital initial simulé (USDT)", default="10000")
    try:
        float(capital)
    except ValueError:
        capital = "10000"
    return {
        "BINANCE_MODE":         "paper",
        "PAPER_INITIAL_CAPITAL": capital,
        "BINANCE_TESTNET":       "false",
    }


def _setup_testnet() -> dict[str, str]:
    _section("Configuration — Spot Testnet Binance")
    _print("  Créez vos clés sur https://testnet.binance.vision → Log In with GitHub", _YELL)
    key    = _ask("BINANCE_API_KEY (testnet)", secret=True)
    secret = _ask("BINANCE_API_SECRET (testnet)", secret=True)
    return {
        "BINANCE_API_KEY":    key,
        "BINANCE_API_SECRET": secret,
        "BINANCE_TESTNET":    "true",
        "BINANCE_MODE":       "spot_testnet",
    }


def _setup_futures_demo() -> dict[str, str]:
    _section("Configuration — Futures Demo Trading Binance")
    _print("  Créez vos clés sur https://demo.binance.com → Mon Compte → Gestion des API", _YELL)
    key    = _ask("BINANCE_FUTURES_DEMO_KEY", secret=True)
    secret = _ask("BINANCE_FUTURES_DEMO_SECRET", secret=True)
    return {
        "BINANCE_FUTURES_DEMO_KEY":    key,
        "BINANCE_FUTURES_DEMO_SECRET": secret,
        "BINANCE_MODE":                "futures_demo",
        "BINANCE_TESTNET":             "false",
    }


def _setup_live() -> dict[str, str]:
    _section("Configuration — LIVE Binance (argent réel ⚠️)")
    _print(
        "  ⚠️  ATTENTION : mode LIVE — les ordres utilisent de l'argent réel.\n"
        "  Créez une clé API sur https://www.binance.com/fr/my/settings/api-management",
        _RED,
    )
    if not _confirm("Confirmer l'utilisation du mode LIVE ?"):
        _print("  Annulé.", _YELL)
        sys.exit(0)
    key    = _ask("BINANCE_LIVE_API_KEY", secret=True)
    secret = _ask("BINANCE_LIVE_API_SECRET", secret=True)
    return {
        "BINANCE_LIVE_API_KEY":    key,
        "BINANCE_LIVE_API_SECRET": secret,
        "BINANCE_TESTNET":         "false",
        "BINANCE_MODE":            "live",
    }


# ── Flux principal ────────────────────────────────────────────────────────────

def run_setup() -> None:
    """Exécute le wizard interactif de configuration Binance."""
    print(f"\n{'═'*60}")
    print(f"{_BOLD}{_CYAN}   🚀  Binance Connector — Assistant de configuration{_RESET}")
    print(f"{'═'*60}")

    # Afficher la config existante (masquée)
    existing = _read_env()
    current_mode = existing.get("BINANCE_MODE", "non configuré")
    _print(f"\n  Mode actuel : {current_mode}", _CYAN)

    _section("Choix du mode de trading")
    print(
        "  1. paper         — Simulation locale (recommandé pour débuter)\n"
        "  2. spot_testnet  — Testnet Spot Binance (argent fictif, API réelle)\n"
        "  3. futures_demo  — Futures Demo Binance (argent fictif, orderbook réel)\n"
        "  4. live          — Trading réel (⚠️ argent réel)\n"
        "  5. Quitter\n"
    )

    choice = _ask("Votre choix", default="1")

    updates: dict[str, str] = {}
    if choice == "1":
        updates = _setup_paper()
    elif choice == "2":
        updates = _setup_testnet()
    elif choice == "3":
        updates = _setup_futures_demo()
    elif choice == "4":
        updates = _setup_live()
    elif choice == "5":
        _print("\n  Au revoir !", _CYAN)
        sys.exit(0)
    else:
        _print("  Choix invalide. Lancement en mode paper.", _YELL)
        updates = _setup_paper()

    # Test de connexion
    _section("Test de connexion")
    if _confirm("Tester la connexion maintenant ?"):
        ok = _test_connection(updates)
        if not ok and choice != "1":
            if not _confirm("La connexion a échoué. Sauvegarder quand même ?"):
                _print("\n  Configuration annulée.", _YELL)
                sys.exit(1)

    # Sauvegarde
    _section("Sauvegarde")
    if _confirm(f"Sauvegarder dans {ENV_FILE} ?"):
        _write_env(updates)
        _print("\n  ✅  Configuration terminée !", _GREEN)
        _print("  Lancez votre système avec : python -m quant_hedge_ai.backtest_real", _CYAN)
    else:
        _print("\n  Configuration non sauvegardée.", _YELL)

    print()


# ── Point d'entrée ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    run_setup()
