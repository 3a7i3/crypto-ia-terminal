"""
scripts/runtime_validator.py — Certification pré-lancement pour le mode paper trading.

Vérifie que l'environnement est sain avant de démarrer advisor_loop.py.
Produit un rapport visuel par catégorie, avec un verdict PASS/FAIL final.

Usage :
    python scripts/runtime_validator.py
    python scripts/runtime_validator.py --json   # sortie machine-readable
    python scripts/runtime_validator.py --strict  # exit(1) si tout avertissement

Exit codes :
    0 — PASS (prêt à démarrer)
    1 — FAIL (au moins une vérification critique échoue)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# ── Couleurs terminal ──────────────────────────────────────────────────────────

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _ok(msg: str = "") -> str:
    return f"{_GREEN}✅{_RESET}" + (f" {msg}" if msg else "")


def _fail(msg: str = "") -> str:
    return f"{_RED}❌{_RESET}" + (f" {msg}" if msg else "")


def _warn(msg: str = "") -> str:
    return f"{_YELLOW}⚠{_RESET}" + (f" {msg}" if msg else "")


# ── Résultat d'un check ────────────────────────────────────────────────────────

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    status: str  # STATUS_OK | STATUS_WARN | STATUS_FAIL
    detail: str = ""


# ── Checks individuels ─────────────────────────────────────────────────────────


def check_configuration() -> CheckResult:
    required = [
        "MEXC_API_KEY",
        "MEXC_SECRET_KEY",
        "PAPER_TRADING_ENABLED",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        return CheckResult(
            "Configuration",
            STATUS_FAIL,
            f"Variables manquantes : {', '.join(missing)}",
        )
    paper_val = os.getenv("PAPER_TRADING_ENABLED", "").lower()
    if paper_val not in {"true", "false", "1", "0", "yes", "no"}:
        return CheckResult(
            "Configuration",
            STATUS_WARN,
            f"PAPER_TRADING_ENABLED='{paper_val}' — valeur inattendue",
        )
    return CheckResult("Configuration", STATUS_OK, f"PAPER_TRADING_ENABLED={paper_val}")


def check_exchange() -> CheckResult:
    try:
        import ccxt  # noqa: PLC0415

        exchange = ccxt.mexc(
            {
                "apiKey": os.getenv("MEXC_API_KEY", ""),
                "secret": os.getenv("MEXC_SECRET_KEY", ""),
                "enableRateLimit": True,
                "timeout": 5000,
            }
        )
        t0 = time.perf_counter()
        exchange.fetch_time()
        ms = int((time.perf_counter() - t0) * 1000)
        return CheckResult("Exchange (MEXC)", STATUS_OK, f"ping {ms}ms")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Exchange (MEXC)", STATUS_FAIL, str(exc)[:120])


def check_paper_engine() -> CheckResult:
    try:
        from paper_trading.mexc_simulator import MexcSimulator  # noqa: PLC0415

        _ = MexcSimulator.__init__
        return CheckResult("Paper Engine", STATUS_OK, "MexcSimulator importé")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Paper Engine", STATUS_FAIL, str(exc)[:120])


def check_ledger() -> CheckResult:
    db_dir = Path("databases")
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        probe = db_dir / ".write_probe"
        probe.write_text("ok")
        probe.unlink()
        jsonl = db_dir / "paper_trades.jsonl"
        exists = jsonl.exists()
        size = jsonl.stat().st_size if exists else 0
        return CheckResult(
            "Ledger",
            STATUS_OK,
            f"databases/ accessible en écriture — paper_trades.jsonl {size}B",
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Ledger", STATUS_FAIL, str(exc)[:120])


def check_dataset() -> CheckResult:
    try:
        from paper_trading.dataset_validator import validate_corpus  # noqa: PLC0415
    except ImportError as exc:
        return CheckResult(
            "Dataset", STATUS_WARN, f"dataset_validator non disponible: {exc}"
        )

    log_path = os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")
    report = validate_corpus(log_path=log_path)

    if report.total_events == 0:
        return CheckResult("Dataset", STATUS_OK, "vide — burn-in repart de zéro")

    if report.violations:
        v_summary = report.violations[0][:80]
        return CheckResult(
            "Dataset",
            STATUS_FAIL,
            f"{len(report.violations)} violation(s) — ex: {v_summary}",
        )

    eligible = "burn-in eligible" if report.burnin_eligible else "N insuffisant"
    return CheckResult(
        "Dataset",
        STATUS_OK,
        f"{report.paired_trades} trades appariés, {eligible}",
    )


def _try_import(module: str, label: str) -> CheckResult:
    try:
        __import__(module)
        return CheckResult(label, STATUS_OK, f"{module} importé")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(label, STATUS_FAIL, str(exc)[:120])


def check_decision_engine() -> CheckResult:
    return _try_import(
        "quant_hedge_ai.runtime.runtime_state_machine", "Decision Engine"
    )


def check_risk_engine() -> CheckResult:
    return _try_import("quant_hedge_ai.risk.portfolio_brain", "Risk Engine")


def check_regret_engine() -> CheckResult:
    # Regret engine peut avoir plusieurs emplacements selon la migration
    for mod in ("regret_engine", "quant_hedge_ai.decision.regret_engine"):
        try:
            __import__(mod)
            return CheckResult("Regret Engine", STATUS_OK, f"{mod} importé")
        except ImportError:
            continue
        except Exception as exc:  # noqa: BLE001
            return CheckResult("Regret Engine", STATUS_FAIL, str(exc)[:120])
    return CheckResult(
        "Regret Engine", STATUS_WARN, "module introuvable — non bloquant"
    )


# ── Rapport ────────────────────────────────────────────────────────────────────

_CHECKS = [
    check_configuration,
    check_ledger,
    check_dataset,
    check_paper_engine,
    check_exchange,
    check_decision_engine,
    check_risk_engine,
    check_regret_engine,
]


def _icon(status: str) -> str:
    return {STATUS_OK: _ok(), STATUS_WARN: _warn(), STATUS_FAIL: _fail()}[status]


def run_all(strict: bool = False) -> tuple[list[CheckResult], bool]:
    results = [fn() for fn in _CHECKS]
    passed = all(
        r.status == STATUS_OK or (r.status == STATUS_WARN and not strict)
        for r in results
    )
    return results, passed


def print_report(results: list[CheckResult], passed: bool) -> None:
    col_w = max(len(r.name) for r in results) + 2
    print(f"\n{_BOLD}Runtime Certification{_RESET}\n")
    for r in results:
        icon = _icon(r.status)
        label = r.name.ljust(col_w)
        detail = f"  {r.detail}" if r.detail else ""
        print(f"  {label}{icon}{detail}")
    verdict_color = _GREEN if passed else _RED
    verdict = "PASS" if passed else "FAIL"
    print(f"\n{_BOLD}Certification : {verdict_color}{verdict}{_RESET}\n")


def json_report(results: list[CheckResult], passed: bool) -> dict:
    return {
        "pass": passed,
        "checks": [
            {"name": r.name, "status": r.status, "detail": r.detail} for r in results
        ],
    }


# ── Entrée ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Certification pré-lancement paper trading"
    )
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Traiter les avertissements comme des échecs",
    )
    args = parser.parse_args()

    results, passed = run_all(strict=args.strict)

    if args.json_output:
        print(json.dumps(json_report(results, passed), indent=2, ensure_ascii=False))
    else:
        print_report(results, passed)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
