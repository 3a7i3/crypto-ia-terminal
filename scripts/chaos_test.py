#!/usr/bin/env python3
# flake8: noqa: E402
"""
scripts/chaos_test.py — Simulation de pannes pour valider la résilience.

Scénarios testés (sans toucher au service live) :
  1. JSON corrompu → data_quality doit détecter et exit 2
  2. Lock périmé → preflight doit avertir, pas bloquer
  3. Variables d'environnement manquantes → preflight bloque
  4. Espace disque simulé insuffisant → preflight bloque
  5. Log inactif depuis >10min → health_check doit reporter WARNING
  6. PID mort dans lock → health_check doit reporter CRITICAL
  7. Champs OPEN absents → load_trades silencieux (trade ignoré)
  8. PnL extrême → data_quality détecte

Usage :
    python3 scripts/chaos_test.py [--verbose]

Exit 0 = tous scénarios réussis | Exit 1 = au moins un échec
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import scripts.data_quality as dq
import scripts.health_check as hc
import scripts.preflight as pf

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

W = 64
_results: list[tuple[str, bool, str]] = []


def _scenario(name: str) -> "ScenarioCtx":
    return ScenarioCtx(name)


class ScenarioCtx:
    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> "ScenarioCtx":
        if VERBOSE:
            print(f"\n  ► {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            _results.append((self.name, False, f"Exception inattendue: {exc_val}"))
            return True  # absorb
        return False

    def ok(self, detail: str = "") -> None:
        _results.append((self.name, True, detail))
        if VERBOSE:
            print(f"    ✅ {detail}")

    def fail(self, detail: str) -> None:
        _results.append((self.name, False, detail))
        if VERBOSE:
            print(f"    ❌ {detail}")


# ── Scénarios ─────────────────────────────────────────────────────────────────


def chaos_01_corrupt_json() -> None:
    with _scenario("S01 — JSON corrompu") as s:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trades.jsonl"
            p.write_text("{not valid json\n")
            result = dq.main(jsonl_path=str(p))
        if result == 2:
            s.ok(f"data_quality exit={result} (attendu 2)")
        else:
            s.fail(f"data_quality exit={result} — attendu 2")


def chaos_02_stale_lock_dead_pid() -> None:
    with _scenario("S02 — Lock périmé (PID mort)") as s:
        pf._ok = True
        pf._warnings.clear()
        pf._errors.clear()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            logs = tmp / "logs"
            logs.mkdir()
            (logs / "advisor.lock").write_text("999999999\n")
            with patch.object(pf, "ROOT", tmp):
                pf.check_stale_lock()
        if pf._ok and any("périmé" in w for w in pf._warnings):
            s.ok("Warning émis, service non bloqué")
        else:
            s.fail(f"ok={pf._ok}, warnings={pf._warnings}")


def chaos_03_missing_env() -> None:
    with _scenario("S03 — Variables d'env manquantes") as s:
        pf._ok = True
        pf._warnings.clear()
        pf._errors.clear()
        saved = {k: os.environ.pop(k, None) for k in pf.REQUIRED_ENV}
        try:
            pf.check_env()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        if not pf._ok and pf._errors:
            s.ok(f"Bloqué correctement: {pf._errors[0][:50]}")
        else:
            s.fail("preflight ne bloque pas sur env manquantes")


def chaos_04_disk_full() -> None:
    with _scenario("S04 — Disque plein (simulé)") as s:
        pf._ok = True
        pf._warnings.clear()
        pf._errors.clear()

        class _FakeDisk:
            free = 0
            total = 1_000_000_000
            used = 1_000_000_000

        with patch("shutil.disk_usage", return_value=_FakeDisk()):
            pf.check_disk()
        if not pf._ok and any("insuffisant" in e for e in pf._errors):
            s.ok("Bloqué correctement sur disque plein")
        else:
            s.fail("preflight ne bloque pas sur disque plein")


def chaos_05_inactive_log() -> None:
    with _scenario("S05 — Log inactif depuis >10min") as s:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "advisor.log"
            log.write_text("old log entry\n")
            old_time = time.time() - 700  # 700s = >10min
            os.utime(log, (old_time, old_time))
            with patch.object(hc, "LOG_FILE", log):
                info = hc._check_log_activity()
        if info["lag_s"] is not None and info["lag_s"] > 600:
            s.ok(f"Lag détecté: {info['lag_s']:.0f}s")
        else:
            s.fail(f"Lag non détecté correctement: {info}")


def chaos_06_dead_pid_health_check() -> None:
    with _scenario("S06 — PID mort dans lock (health_check)") as s:
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "advisor.lock"
            lock.write_text("999999999\n")
            log = Path(d) / "advisor.log"
            with (
                patch.object(hc, "LOCK_FILE", lock),
                patch.object(hc, "LOG_FILE", log),
            ):
                exit_code = hc.main()
        if exit_code == 2:
            s.ok("CRITICAL retourné correctement (PID mort)")
        else:
            s.fail(f"exit_code={exit_code} — attendu 2")


def chaos_07_orphan_open_ignored() -> None:
    with _scenario("S07 — OPEN sans CLOSE (trade ignoré)") as s:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trades.jsonl"
            with p.open("w") as f:
                f.write(
                    json.dumps(
                        {
                            "event": "OPEN",
                            "trade_id": "T_orphan",
                            "symbol": "X/Y",
                            "side": "BUY",
                            "entry_price": 1.0,
                        }
                    )
                    + "\n"
                )
            from analysis.base import load_trades

            trades = load_trades(str(p))
        if len(trades) == 0:
            s.ok("OPEN sans CLOSE silencieusement ignoré")
        else:
            s.fail(f"load_trades retourné {len(trades)} trade(s) inattendu(s)")


def chaos_08_extreme_pnl() -> None:
    with _scenario("S08 — PnL extrême (|pnl_pct| > 200%)") as s:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trades.jsonl"
            with p.open("w") as f:
                f.write(
                    json.dumps(
                        {
                            "event": "OPEN",
                            "trade_id": "T1",
                            "symbol": "RUG/USDT",
                            "side": "BUY",
                            "entry_price": 1.0,
                            "timestamp": 1_750_000_000.0,
                        }
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {
                            "event": "CLOSE",
                            "trade_id": "T1",
                            "symbol": "RUG/USDT",
                            "pnl_usd": -999.0,
                            "pnl_pct": -480.0,
                        }
                    )
                    + "\n"
                )
            result = dq.main(jsonl_path=str(p))
        if result == 2:
            s.ok("PnL extrême détecté (exit 2)")
        else:
            s.fail(f"exit={result} — attendu 2")


# ── Runner ────────────────────────────────────────────────────────────────────


def main() -> int:
    print(f"\n{'='*W}")
    print("  CHAOS TEST — Résilience crypto-advisor")
    print(f"{'='*W}")

    chaos_01_corrupt_json()
    chaos_02_stale_lock_dead_pid()
    chaos_03_missing_env()
    chaos_04_disk_full()
    chaos_05_inactive_log()
    chaos_06_dead_pid_health_check()
    chaos_07_orphan_open_ignored()
    chaos_08_extreme_pnl()

    print(f"\n{'─'*W}")
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)

    for name, ok, detail in _results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if not ok or VERBOSE:
            print(f"     {detail}")

    print(f"\n  Score: {passed}/{total}")
    if passed == total:
        print(f"  🟢 TOUS LES SCÉNARIOS RÉUSSIS")
    else:
        print(f"  🔴 {total - passed} SCÉNARIO(S) EN ÉCHEC")
    print(f"{'='*W}\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
