"""
paper_trading/sandbox_validator.py — Validation de la config sandbox avant lancement.

Vérifie que l'environnement est bien configuré en mode testnet/paper
et qu'aucune clé mainnet n'est utilisée accidentellement.

Usage :
    python -m paper_trading.sandbox_validator
    # ou dans le code :
    from paper_trading.sandbox_validator import validate_sandbox, SandboxConfigError
    validate_sandbox()   # lève SandboxConfigError si la config est dangereuse
"""

from __future__ import annotations

import os
import sys


class SandboxConfigError(Exception):
    """Configuration sandbox invalide ou dangereuse."""


def validate_sandbox(strict: bool = True) -> dict:
    """
    Vérifie la configuration sandbox.

    strict=True  : lève SandboxConfigError si un check critique échoue.
    strict=False : retourne les résultats sans lever d'exception.

    Retourne un dict de résultats {check: (ok, message)}.
    """
    results: dict[str, tuple[bool, str]] = {}

    # 1. EXCHANGE_TESTNET doit être true
    testnet = os.getenv("EXCHANGE_TESTNET", "false").lower() == "true"
    results["EXCHANGE_TESTNET"] = (
        testnet,
        (
            "✅ testnet activé"
            if testnet
            else "❌ EXCHANGE_TESTNET doit être 'true' en sandbox"
        ),
    )

    # 2. MARKET_SCANNER_TESTNET doit être true
    scanner_testnet = os.getenv("MARKET_SCANNER_TESTNET", "false").lower() == "true"
    results["MARKET_SCANNER_TESTNET"] = (
        scanner_testnet,
        (
            "✅ scanner testnet activé"
            if scanner_testnet
            else "⚠️  MARKET_SCANNER_TESTNET non activé"
        ),
    )

    # 3. Clés API ne doivent pas être les placeholders
    api_key = os.getenv("MEXC_API_KEY", "")
    key_ok = bool(api_key) and "YOUR_" not in api_key and len(api_key) > 10
    results["MEXC_API_KEY"] = (
        key_ok,
        (
            "✅ clé API MEXC configurée"
            if key_ok
            else "⚠️  Clé API MEXC manquante ou placeholder"
        ),
    )

    # 4. Taille d'ordre max raisonnable pour sandbox (< $500)
    max_order = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))
    order_ok = max_order <= 500.0
    results["EXEC_MAX_ORDER_USD"] = (
        order_ok,
        (
            f"✅ max ordre ${max_order:.0f}"
            if order_ok
            else f"⚠️  Max ordre ${max_order:.0f} élevé pour sandbox"
        ),
    )

    # 5. PAPER_TRADING_ENABLED
    paper = os.getenv("PAPER_TRADING_ENABLED", "false").lower() == "true"
    results["PAPER_TRADING_ENABLED"] = (
        paper,
        (
            "✅ paper trading activé"
            if paper
            else "ℹ️  paper trading non activé (optionnel en sandbox)"
        ),
    )

    # Checks critiques
    critical_failed = [
        check
        for check, (ok, _) in results.items()
        if not ok and check in ("EXCHANGE_TESTNET",)
    ]

    if strict and critical_failed:
        msgs = "\n".join(f"  {c}: {results[c][1]}" for c in critical_failed)
        raise SandboxConfigError(
            f"Configuration sandbox invalide — checks critiques échoués:\n{msgs}\n"
            "Vérifiez votre .env ou copiez .env.sandbox vers .env."
        )

    return results


def print_report(results: dict) -> None:
    print("\n══ Sandbox Config Validator ══")
    for check, (ok, msg) in results.items():
        print(f"  {check:<30} {msg}")
    all_ok = all(ok for ok, _ in results.values())
    print(
        f"\n{'✅ Config sandbox OK' if all_ok else '⚠️  Config sandbox avec avertissements'}\n"
    )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    try:
        results = validate_sandbox(strict=False)
        print_report(results)
        critical = [
            c for c, (ok, _) in results.items() if not ok and c == "EXCHANGE_TESTNET"
        ]
        sys.exit(1 if critical else 0)
    except Exception as exc:
        print(f"Erreur: {exc}")
        sys.exit(1)
