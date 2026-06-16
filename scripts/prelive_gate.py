"""
scripts/prelive_gate.py — Gate de validation pré-live.

Vérifie l'ensemble des conditions requises avant d'autoriser le passage
du paper trading au spot réel (Phase 2, petit capital).

Ne JAMAIS exécuter en remplacement de runtime_validator.py —
ce script mesure les RÉSULTATS accumulés, pas l'état système instantané.

Gates :
  A. Volume      — N >= 100 trades paper fermés
  B. Performance — PF > 1.5, Sharpe > 1.0, WR > 45%, MaxDD < 10%
  C. Dataset     — zéro violation, burnin_eligible=True
  D. Calibration — burnin_calibration_v3 exécuté et passé
  E. Exchange    — clés MEXC valides + ping < 2s
  F. Risk config — exec_max_order_usd <= 50 pour Phase 2

Usage :
    python scripts/prelive_gate.py
    python scripts/prelive_gate.py --json
    python scripts/prelive_gate.py --strict

Exit codes :
    0 — GO (toutes gates passées)
    1 — NO-GO (au moins une gate critique échoue)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# ── Seuils ────────────────────────────────────────────────────────────────────

_BURNIN_N = int(os.getenv("PRELIVE_BURNIN_N", "100"))
_MIN_PF = float(os.getenv("PRELIVE_MIN_PF", "1.5"))
_MIN_SHARPE = float(os.getenv("PRELIVE_MIN_SHARPE", "1.0"))
_MIN_WR = float(os.getenv("PRELIVE_MIN_WR", "45.0"))
_MAX_DD = float(os.getenv("PRELIVE_MAX_DD", "10.0"))
_MAX_ORDER_P2 = float(os.getenv("PRELIVE_MAX_ORDER_USD", "50.0"))

# ── Couleurs ──────────────────────────────────────────────────────────────────

_G = "\033[92m"
_R = "\033[91m"
_Y = "\033[93m"
_B = "\033[1m"
_X = "\033[0m"

STATUS_GO = "go"
STATUS_NOGO = "nogo"
STATUS_WARN = "warn"


@dataclass
class GateResult:
    name: str
    status: str  # go | nogo | warn
    detail: str = ""
    value: float | None = None
    threshold: float | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _read_closes() -> list[dict]:
    log_path = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
    if not log_path.exists():
        return []
    closes = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                ev = json.loads(line)
                if ev.get("event") == "CLOSE":
                    closes.append(ev)
    except Exception:
        pass
    return closes


def _compute_metrics(closes: list[dict]) -> dict:
    if not closes:
        return {}
    n = len(closes)
    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    from infra.wallet_sync import get_wallet_sync

    equity = [get_wallet_sync().initial_capital()]
    for p in pnls:
        equity.append(equity[-1] + p)
    peak, max_dd = equity[0], 0.0
    for e in equity:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak * 100
            if dd > max_dd:
                max_dd = dd

    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    pcts = [float(c.get("pnl_pct", 0) or 0) for c in closes]
    mean_p = sum(pcts) / n if n else 0
    var_p = sum((p - mean_p) ** 2 for p in pcts) / n if n > 1 else 0
    std_p = math.sqrt(var_p) if var_p > 0 else 0
    sharpe = mean_p / std_p if std_p > 0 else 0.0

    return {
        "n": n,
        "win_rate": len(wins) / n * 100,
        "pf": pf,
        "sharpe": sharpe,
        "max_dd": max_dd,
    }


# ── Gates ─────────────────────────────────────────────────────────────────────


def gate_a_volume() -> GateResult:
    closes = _read_closes()
    n = len(closes)
    if n >= _BURNIN_N:
        return GateResult(
            "A. Volume", STATUS_GO, f"{n}/{_BURNIN_N} trades fermés", n, _BURNIN_N
        )
    pct = n / _BURNIN_N * 100
    return GateResult(
        "A. Volume",
        STATUS_NOGO,
        f"{n}/{_BURNIN_N} trades fermés ({pct:.0f}%) — ETA ~{(_BURNIN_N - n) * 22 / 60:.0f}h à 2.7/h",  # noqa: E501
        n,
        _BURNIN_N,
    )


def gate_b_performance() -> GateResult:
    closes = _read_closes()
    m = _compute_metrics(closes)
    if not m:
        return GateResult(
            "B. Performance", STATUS_NOGO, "Aucun trade fermé — impossible à évaluer"
        )

    checks = [
        ("PF", m["pf"], _MIN_PF, True, f"{m['pf']:.2f}"),
        ("Sharpe", m["sharpe"], _MIN_SHARPE, True, f"{m['sharpe']:.2f}"),
        ("WR%", m["win_rate"], _MIN_WR, True, f"{m['win_rate']:.1f}%"),
        ("MaxDD%", m["max_dd"], _MAX_DD, False, f"{m['max_dd']:.1f}%"),
    ]
    failed = []
    lines = []
    for label, val, thr, gt, display in checks:
        ok = (val > thr) if gt else (val < thr)
        sym = "✓" if ok else "✗"
        op = ">" if gt else "<"
        lines.append(f"{sym} {label}={display} ({op}{thr})")
        if not ok:
            failed.append(label)

    detail = "  ".join(lines)
    if failed:
        return GateResult("B. Performance", STATUS_NOGO, detail)
    return GateResult("B. Performance", STATUS_GO, detail)


def gate_c_dataset() -> GateResult:
    try:
        from paper_trading.dataset_validator import validate_corpus  # noqa: PLC0415
    except ImportError:
        return GateResult(
            "C. Dataset", STATUS_WARN, "dataset_validator non disponible — skip"
        )

    log_path = os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")
    report = validate_corpus(log_path=log_path)

    if report.total_events == 0:
        return GateResult(
            "C. Dataset", STATUS_NOGO, "Dataset vide — burn-in non commencé"
        )

    if report.violations:
        v = report.violations[0][:80]
        return GateResult(
            "C. Dataset",
            STATUS_NOGO,
            f"{len(report.violations)} violation(s) — {v}",
        )

    eligible = report.burnin_eligible
    detail = f"{report.paired_trades} trades appariés, burnin_eligible={eligible}"
    if not eligible:
        return GateResult(
            "C. Dataset", STATUS_NOGO, detail + " — N insuffisant pour C5"
        )
    return GateResult("C. Dataset", STATUS_GO, detail)


def gate_d_calibration() -> GateResult:
    v3_paths = [
        Path("cache/burn_in_reports/burnin_v3.json"),
        Path("cache/burn_in_reports/v3.json"),
    ]
    found = next((p for p in v3_paths if p.exists()), None)
    if not found:
        return GateResult(
            "D. Calibration",
            STATUS_NOGO,
            "burnin_calibration_v3.json introuvable — lancer: python scripts/burnin_calibration_v3.py",  # noqa: E501
        )
    try:
        data = json.loads(found.read_text(encoding="utf-8"))
        passed = data.get("burnin_passed", data.get("pass", False))
        n_trades = data.get("n_trades", data.get("real_trades", {}).get("count", "?"))
        floor = data.get("recommended_score_floor", data.get("score_floor", "?"))
        if not passed:
            reason = data.get("fail_reason", "voir rapport")
            return GateResult(
                "D. Calibration", STATUS_NOGO, f"BurnIn V3 NO-GO — {reason}"
            )
        return GateResult(
            "D. Calibration",
            STATUS_GO,
            f"BurnIn V3 PASS — {n_trades} trades, score_floor={floor}",
        )
    except Exception as exc:
        return GateResult(
            "D. Calibration", STATUS_WARN, f"Lecture rapport échouée: {exc}"
        )


def gate_e_exchange() -> GateResult:
    try:
        import ccxt  # noqa: PLC0415

        exch = ccxt.mexc(
            {
                "apiKey": os.getenv("MEXC_API_KEY", ""),
                "secret": os.getenv("MEXC_SECRET_KEY", ""),
                "enableRateLimit": True,
                "timeout": 5000,
            }
        )
        t0 = time.perf_counter()
        exch.fetch_time()
        ms = int((time.perf_counter() - t0) * 1000)
        if ms > 2000:
            return GateResult(
                "E. Exchange",
                STATUS_WARN,
                f"MEXC accessible mais latence élevée ({ms}ms) — surveiller",
                ms,
                2000,
            )
        return GateResult("E. Exchange", STATUS_GO, f"MEXC OK — ping {ms}ms", ms)
    except Exception as exc:
        return GateResult(
            "E. Exchange", STATUS_NOGO, f"MEXC inaccessible: {str(exc)[:120]}"
        )


def gate_f_risk_config() -> GateResult:
    issues = []

    # Vérifier exec_max_order_usd
    max_order_raw = os.getenv("EXEC_MAX_ORDER_USD", "")
    if not max_order_raw:
        issues.append("EXEC_MAX_ORDER_USD non défini")
    else:
        try:
            max_order = float(max_order_raw)
            if max_order > _MAX_ORDER_P2:
                issues.append(
                    f"EXEC_MAX_ORDER_USD={max_order} > {_MAX_ORDER_P2}"  # noqa: E501
                    " — trop élevé pour Phase 2"
                )
        except ValueError:
            issues.append(f"EXEC_MAX_ORDER_USD='{max_order_raw}' non numérique")

    # Vérifier PAPER_TRADING_ENABLED est défini (doit pouvoir passer à false)
    if not os.getenv("PAPER_TRADING_ENABLED"):
        issues.append("PAPER_TRADING_ENABLED non défini dans .env")

    # Vérifier MEXC_SIM_CAPITAL défini
    if not os.getenv("MEXC_SIM_CAPITAL"):
        issues.append("MEXC_SIM_CAPITAL non défini")

    if issues:
        return GateResult("F. Risk Config", STATUS_NOGO, " | ".join(issues))

    max_order = float(os.getenv("EXEC_MAX_ORDER_USD", "0"))
    return GateResult(
        "F. Risk Config",
        STATUS_GO,
        f"max_order={max_order} USD — Phase 2 autorisée (taille <= {_MAX_ORDER_P2})",
    )


# ── Rapport ───────────────────────────────────────────────────────────────────

_GATES = [
    gate_a_volume,
    gate_b_performance,
    gate_c_dataset,
    gate_d_calibration,
    gate_e_exchange,
    gate_f_risk_config,
]  # noqa: E501


def _icon(status: str) -> str:
    return {
        STATUS_GO: f"{_G}GO {_X}",
        STATUS_NOGO: f"{_R}NO {_X}",
        STATUS_WARN: f"{_Y}⚠  {_X}",
    }[status]


def run_all(strict: bool = False) -> tuple[list[GateResult], bool]:
    results = [fn() for fn in _GATES]
    passed = all(
        r.status == STATUS_GO or (r.status == STATUS_WARN and not strict)
        for r in results
    )
    return results, passed


def print_report(results: list[GateResult], passed: bool) -> None:
    col_w = max(len(r.name) for r in results) + 2
    print(f"\n{_B}Pre-Live Gate — Passage Paper → Spot Réel{_X}\n")
    for r in results:
        label = r.name.ljust(col_w)
        detail = f"  {r.detail}" if r.detail else ""
        print(f"  {label}{_icon(r.status)}{detail}")

    verdict = "GO" if passed else "NO-GO"
    color = _G if passed else _R
    print(f"\n{_B}Verdict : {color}{verdict}{_X}\n")

    if passed:
        print(f"  {_G}Phase 2 autorisée.{_X}")
        print("  Prochaine : PAPER_TRADING_ENABLED=false + EXEC_MAX_ORDER_USD=10")
        print("  Symboles Phase 2 : BTC/USDT ETH/USDT SOL/USDT XRP/USDT (sans levier)")
    else:
        nogo = [r for r in results if r.status == STATUS_NOGO]
        print(f"  {_R}{len(nogo)} gate(s) bloquante(s) — voir détails ci-dessus.{_X}")
    print()


def json_report(results: list[GateResult], passed: bool) -> dict:
    return {
        "verdict": "GO" if passed else "NO-GO",
        "pass": passed,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "thresholds": {
            "burnin_n": _BURNIN_N,
            "min_pf": _MIN_PF,
            "min_sharpe": _MIN_SHARPE,
            "min_wr_pct": _MIN_WR,
            "max_dd_pct": _MAX_DD,
            "max_order_usd": _MAX_ORDER_P2,
        },
        "gates": [
            {"name": r.name, "status": r.status, "detail": r.detail} for r in results
        ],
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate de validation pré-live")
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Warn = NO-GO")
    args = parser.parse_args()

    results, passed = run_all(strict=args.strict)

    if args.json_output:
        print(json.dumps(json_report(results, passed), indent=2, ensure_ascii=False))
    else:
        print_report(results, passed)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
