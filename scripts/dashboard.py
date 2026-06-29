#!/usr/bin/env python3
"""
scripts/dashboard.py — Tableau de bord unifié crypto-advisor.

Agrège en une seule vue :
  - Infrastructure (health_check)
  - Dataset (data_quality)
  - Performance (perf check allégé)
  - Trading (métriques depuis paper_trades.jsonl)
  - Hypothèses (statuts depuis hypothesis_registry.yaml)

Usage :
    python3 scripts/dashboard.py [--jsonl path] [--json]
"""
from __future__ import annotations

import json as _json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

W = 68


def _section(title: str) -> None:
    print(f"\n  {'─'*W}")
    print(f"  {title}")
    print(f"  {'─'*W}")


def _row(label: str, value: str, ok: bool | None = None) -> None:
    icon = ""
    if ok is True:
        icon = "✅"
    elif ok is False:
        icon = "❌"
    elif ok is None:
        icon = "  "
    print(f"  {icon} {label:<28} {value}")


# ── Infrastructure ────────────────────────────────────────────────────────────


def _check_infra() -> dict:
    try:
        import scripts.health_check as hc

        pid = hc._read_pid()
        if pid is None:
            return {"pid": None, "status": "NON ACTIF", "ok": False}

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return {"pid": pid, "status": "PID MORT", "ok": False}
        except PermissionError:
            pass

        proc = hc._check_process(pid)
        log = hc._check_log_activity()
        fd_warnings = hc._fd_inheritance_risk(proc)

        return {
            "pid": pid,
            "status": proc.get("status", "?"),
            "uptime_h": proc.get("uptime_h", "?"),
            "mem_mb": proc.get("mem_rss_mb", "?"),
            "cpu_pct": proc.get("cpu_pct", "?"),
            "fd_count": proc.get("fd_count", "?"),
            "fd_warnings": len(fd_warnings),
            "log_lag_s": log.get("lag_s"),
            "ok": proc.get("ok", False),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _print_infra(d: dict) -> None:
    _section("INFRASTRUCTURE")
    ok = d.get("ok", False)
    _row("Service", f"PID {d.get('pid', '?')} — {d.get('status', '?')}", ok)
    if ok:
        _row("Uptime", f"{d.get('uptime_h', '?')} h", None)
        mem = d.get("mem_mb", 0)
        _row(
            "Mémoire RSS",
            f"{mem} MB",
            mem < 1500 if isinstance(mem, (int, float)) else None,
        )
        cpu = d.get("cpu_pct", 0)
        _row("CPU", f"{cpu} %", cpu < 80 if isinstance(cpu, (int, float)) else None)
        fds = d.get("fd_count", 0)
        _row(
            "FD ouverts", str(fds), fds < 100 if isinstance(fds, (int, float)) else None
        )
        _row("FD warnings", str(d.get("fd_warnings", 0)), d.get("fd_warnings", 0) == 0)
        lag = d.get("log_lag_s")
        if lag is not None:
            _row("Log lag", f"{lag:.0f}s", lag < 600)
    else:
        _row("Erreur", d.get("error", d.get("status", "?")), False)


# ── Dataset ───────────────────────────────────────────────────────────────────


def _check_dataset(jsonl_path: str | None) -> dict:
    try:
        from contextlib import redirect_stdout
        from io import StringIO

        import scripts.data_quality as dq

        buf = StringIO()
        path = jsonl_path or str(ROOT / "databases" / "paper_trades.jsonl")
        with redirect_stdout(buf):
            exit_code = dq.main(jsonl_path=path)
        output = buf.getvalue()

        # Extraire quelques métriques depuis l'output
        n_closed = 0
        total_pnl = 0.0
        for line in output.splitlines():
            if "Trades fermés" in line:
                try:
                    n_closed = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
            if "PnL total" in line:
                try:
                    total_pnl = float(line.split(":")[-1].strip().replace("$", ""))
                except ValueError:
                    pass

        return {
            "exit_code": exit_code,
            "ok": exit_code == 0,
            "n_closed": n_closed,
            "total_pnl": total_pnl,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "exit_code": 2}


def _print_dataset(d: dict) -> None:
    _section("DATASET")
    _row("Intégrité", "PASS" if d.get("ok") else "FAIL", d.get("ok"))
    _row("Trades fermés", str(d.get("n_closed", "?")), None)
    pnl = d.get("total_pnl", 0.0)
    if isinstance(pnl, float):
        _row("PnL total", f"{pnl:+.2f} $", None)


# ── Trading metrics ───────────────────────────────────────────────────────────


def _check_trading(jsonl_path: str | None) -> dict:
    try:
        from datetime import datetime, timezone

        from analysis.base import full_metrics, load_trades

        path = jsonl_path or str(ROOT / "databases" / "paper_trades.jsonl")
        trades = load_trades(path)
        clean_since = datetime(2026, 6, 25, tzinfo=timezone.utc)
        clean = [
            t
            for t in trades
            if t.opened_at
            and datetime.fromtimestamp(t.opened_at, tz=timezone.utc) >= clean_since
        ]
        pnls = [t.pnl_usd for t in clean]
        m = full_metrics(pnls)
        return {"ok": True, "n": len(clean), "total": len(trades), **m}
    except FileNotFoundError:
        return {"ok": False, "n": 0, "total": 0, "error": "paper_trades.jsonl absent"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _print_trading(d: dict) -> None:
    _section("TRADING (données propres post-2026-06-25)")
    n = d.get("n", 0)
    _row("Trades propres", f"{n} / {d.get('total', 0)} total", n > 0)
    if n > 0:
        pf_val = d.get("profit_factor")
        _row("Profit Factor", str(pf_val), isinstance(pf_val, float) and pf_val > 1.0)
        wr = d.get("win_rate")
        _row("Win Rate", f"{wr:.1%}" if wr else "?", isinstance(wr, float) and wr > 0.5)
        exp = d.get("expectancy_usd")
        _row(
            "Expectancy",
            f"{exp:+.4f} $/trade" if exp else "?",
            isinstance(exp, float) and exp > 0,
        )
        dd = d.get("max_drawdown_usd", 0.0)
        _row("Max Drawdown", f"{dd:.2f} $", isinstance(dd, float) and dd < 30)
        sharpe = d.get("sharpe")
        _row("Sharpe", str(sharpe), isinstance(sharpe, float) and sharpe > 0)
        kelly = d.get("kelly_fraction")
        _row("Kelly", str(kelly), None)
    else:
        _row("Statut", "En attente de trades propres", None)


# ── Hypothèses ────────────────────────────────────────────────────────────────


def _check_hypotheses() -> dict:
    registry = ROOT / "analysis" / "hypothesis_registry.yaml"
    if not registry.exists():
        return {"ok": False, "error": "hypothesis_registry.yaml absent"}
    try:
        import yaml  # type: ignore[import]

        data = yaml.safe_load(registry.read_text())
        return {"ok": True, "hypotheses": data.get("hypotheses", [])}
    except ImportError:
        # yaml non installé — lecture manuelle des statuts
        content = registry.read_text()
        entries = []
        current_id = None
        current_status = None
        for line in content.splitlines():
            if line.strip().startswith("- id:"):
                if current_id:
                    entries.append({"id": current_id, "status": current_status or "?"})
                current_id = line.split(":")[-1].strip()
                current_status = None
            elif "status:" in line and not line.strip().startswith("#"):
                current_status = line.split(":")[-1].strip()
        if current_id:
            entries.append({"id": current_id, "status": current_status or "?"})
        return {"ok": True, "hypotheses": entries}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _print_hypotheses(d: dict) -> None:
    _section("HYPOTHÈSES SCIENTIFIQUES")
    if not d.get("ok"):
        _row("Registre", d.get("error", "?"), False)
        return
    for h in d.get("hypotheses", []):
        hid = h.get("id", "?")
        status = h.get("status", "?")
        ok = (
            True if status == "Confirmed" else (False if status == "Rejected" else None)
        )
        desc = h.get("description", "")
        short_desc = desc.strip().split("\n")[0][:40] if desc else ""
        _row(f"{hid}", f"{status}  {short_desc}", ok)


# ── Main ──────────────────────────────────────────────────────────────────────


def main(jsonl_path: str | None = None, as_json: bool = False) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    infra = _check_infra()
    dataset = _check_dataset(jsonl_path)
    trading = _check_trading(jsonl_path)
    hypotheses = _check_hypotheses()

    if as_json:
        print(
            _json.dumps(
                {
                    "timestamp": ts,
                    "infra": infra,
                    "dataset": dataset,
                    "trading": trading,
                    "hypotheses": hypotheses,
                },
                indent=2,
                default=str,
            )
        )
        return

    print(f"\n{'='*W}")
    print(f"  DASHBOARD — crypto-advisor  {ts}")
    print(f"{'='*W}")

    _print_infra(infra)
    _print_dataset(dataset)
    _print_trading(trading)
    _print_hypotheses(hypotheses)

    # Résumé global
    checks = [
        infra.get("ok"),
        dataset.get("ok"),
        trading.get("ok", trading.get("n", 0) >= 0),
    ]
    all_ok = all(checks)
    print(f"\n  {'='*W}")
    icon = "🟢 SYSTÈME OPÉRATIONNEL" if all_ok else "🟡 ATTENTION REQUISE"
    print(f"  {icon}")
    print(f"  {'='*W}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dashboard crypto-advisor")
    parser.add_argument("--jsonl", help="Chemin vers paper_trades.jsonl")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()
    main(jsonl_path=args.jsonl, as_json=args.json)
