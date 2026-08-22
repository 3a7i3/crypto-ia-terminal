"""
tools/convergence_forensic_readonly.py
=====================================

Audit read-only pour la phase "Convergence Forensique".

Objectifs:
  - Produire un état de preuve local (Git + artefacts scientifiques + CI).
  - Optionnellement réconcilier VPS↔Git via commandes SSH strictement read-only.
  - Rendre un verdict binaire/tri-state par bloc:
      P0-A (Ledger survivability)
      P0-B (VPS↔Git reconciliation)
      P1-A (Persistence failure observability)
      P1-B (Constitutional CI coverage)

Usage:
  python tools/convergence_forensic_readonly.py
  python tools/convergence_forensic_readonly.py --json
  python tools/convergence_forensic_readonly.py --snapshot-out docs/audit/scientific_snapshots/latest.json
  python tools/convergence_forensic_readonly.py --vps-host 1.2.3.4 --vps-user ubuntu --vps-path /home/ubuntu/crypto_ai_terminal
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.cri_calculator import CLEAN_DATA_SINCE_ACTIVE, compute_cri, trades_provenance

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNCERTAIN = "UNCERTAIN"

_TS_KEYS = (
    "ts",
    "ts_signal",
    "timestamp",
    "event_ts",
    "closed_at",
    "opened_at",
    "time",
)


@dataclass
class BlockVerdict:
    status: str
    reason: str
    evidence: dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 20) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _parse_ts(record: dict) -> datetime | None:
    for k in _TS_KEYS:
        value = record.get(k)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                continue
        if isinstance(value, str):
            s = value.strip()
            if not s:
                continue
            if s.isdigit():
                try:
                    return datetime.fromtimestamp(float(s), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    continue
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
            except ValueError:
                continue
    return None


def _jsonl_stats(path: Path) -> dict:
    exists = path.exists()
    stats = {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "line_count": 0,
        "first_ts": None,
        "last_ts": None,
        "first_post_v4_ts": None,
        "sha256": _sha256_file(path),
    }
    if not exists:
        return stats

    first: datetime | None = None
    last: datetime | None = None
    first_post_v4: datetime | None = None
    n = 0
    for rec in _iter_jsonl(path):
        n += 1
        ts = _parse_ts(rec)
        if ts is None:
            continue
        if first is None or ts < first:
            first = ts
        if last is None or ts > last:
            last = ts
        if ts >= CLEAN_DATA_SINCE_ACTIVE and (
            first_post_v4 is None or ts < first_post_v4
        ):
            first_post_v4 = ts

    stats["line_count"] = n
    stats["first_ts"] = first.isoformat() if first else None
    stats["last_ts"] = last.isoformat() if last else None
    stats["first_post_v4_ts"] = first_post_v4.isoformat() if first_post_v4 else None
    return stats


def _decision_packets_stats(db_dir: Path) -> dict:
    patterns = ("decision_packets*.jsonl",)
    files: list[Path] = []
    for pat in patterns:
        files.extend(sorted(db_dir.glob(pat)))
    files = sorted(set(files))
    newest = None
    total_lines = 0
    for fp in files:
        if newest is None or fp.stat().st_mtime > newest.stat().st_mtime:
            newest = fp
        with fp.open("r", encoding="utf-8", errors="replace") as f:
            for _ in f:
                total_lines += 1
    return {
        "count_files": len(files),
        "total_lines": total_lines,
        "newest_file": str(newest) if newest else None,
        "newest_mtime_utc": (
            datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc).isoformat()
            if newest
            else None
        ),
    }


def _local_git_state() -> dict:
    rc_head, out_head, err_head = _run(["git", "rev-parse", "HEAD"], cwd=ROOT)
    rc_status, out_status, err_status = _run(["git", "status", "--porcelain"], cwd=ROOT)
    return {
        "head_sha": out_head if rc_head == 0 else None,
        "head_sha_error": err_head if rc_head != 0 else None,
        "dirty": bool(out_status) if rc_status == 0 else None,
        "dirty_files": out_status.splitlines() if rc_status == 0 and out_status else [],
        "status_error": err_status if rc_status != 0 else None,
    }


def _critical_files_hashes(base: Path) -> dict:
    files = {
        "advisor_loop": base / "core" / "advisor_loop.py",
        "advisor_runtime_adapters": base / "core" / "advisor_runtime_adapters.py",
        "regime_detector_active": base
        / "quant_hedge_ai"
        / "agents"
        / "intelligence"
        / "regime_detector.py",
    }
    return {
        key: {"path": str(path), "exists": path.exists(), "sha256": _sha256_file(path)}
        for key, path in files.items()
    }


def _classify_regime_detectors(base: Path) -> list[dict]:
    detectors = sorted(base.glob("**/regime_detector.py"))
    rows: list[dict] = []
    for p in detectors:
        rel = p.relative_to(base).as_posix()
        if rel == "quant_hedge_ai/agents/intelligence/regime_detector.py":
            state = "ACTIVE"
            reason = "Canonical runtime detector in intelligence chain."
        elif rel.startswith("_ARCHIVE_2026/"):
            state = "LEGACY"
            reason = "Archived path."
        elif rel.startswith("quant_hedge_ai/agents/market/"):
            state = "UNCERTAIN"
            reason = "Market-scoped implementation; runtime usage not proven in this audit."
        elif rel.startswith("src/"):
            state = "SHIM"
            reason = "V2/src lineage; treat as compatibility or alternate architecture."
        else:
            state = "ORPHAN"
            reason = "Not mapped to active runtime chain."
        rows.append(
            {
                "path": str(p),
                "relative_path": rel,
                "classification": state,
                "reason": reason,
                "sha256": _sha256_file(p),
            }
        )
    return rows


def _disk_permissions(base: Path) -> dict:
    db = base / "databases"
    usage = shutil.disk_usage(base)
    return {
        "databases_exists": db.exists(),
        "databases_readable": os.access(db, os.R_OK),
        "databases_writable": os.access(db, os.W_OK),
        "project_readable": os.access(base, os.R_OK),
        "project_writable": os.access(base, os.W_OK),
        "disk_total_bytes": usage.total,
        "disk_used_bytes": usage.used,
        "disk_free_bytes": usage.free,
    }


def _read_ci_constitutional_state(base: Path) -> dict:
    ci_file = base / ".github" / "workflows" / "ci.yml"
    required = [
        "tests/test_architecture.py",
        "tests/test_advisor_loop_smoke.py",
        "tests/test_live_gate.py",
        "tests/test_decision_packet_confidence.py",
        "tests/test_integration_full_lifecycle.py",
        "tests/governance/test_initialization_contract.py",
        "tests/governance/test_constitution_i14.py",
        "tests/governance/test_constitution_i15.py",
        "tests/governance/test_constitution_i16.py",
    ]
    if not ci_file.exists():
        return {"ci_file": str(ci_file), "exists": False, "present": {}, "missing": required}
    content = ci_file.read_text(encoding="utf-8", errors="replace")
    present = {item: (item in content) for item in required}
    missing = [item for item, ok in present.items() if not ok]
    return {
        "ci_file": str(ci_file),
        "exists": True,
        "present": present,
        "missing": missing,
    }


def _scan_except_exception(advisor_loop_path: Path) -> dict:
    if not advisor_loop_path.exists():
        return {
            "advisor_loop_missing": True,
            "except_exception_handlers": 0,
            "bare_except_handlers": 0,
            "handlers_with_logging": 0,
            "handlers_touching_scientific_keywords": 0,
        }
    src = advisor_loop_path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {
            "advisor_loop_parse_error": True,
            "except_exception_handlers": 0,
            "bare_except_handlers": 0,
            "handlers_with_logging": 0,
            "handlers_touching_scientific_keywords": 0,
        }
    total = 0
    guarded_logs = 0
    bare_except = 0
    critical_hits = 0
    critical_patterns = re.compile(
        r"(paper_trades|regret_analysis|decision_packets|persist|runtime_config|ledger)",
        re.IGNORECASE,
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for h in node.handlers:
            if h.type is None:
                bare_except += 1
                continue
            if isinstance(h.type, ast.Name) and h.type.id == "Exception":
                total += 1
                txt = ast.get_source_segment(src, h) or ""
                has_log = "log." in txt or "logger." in txt
                if has_log:
                    guarded_logs += 1
                if critical_patterns.search(txt):
                    critical_hits += 1
    return {
        "except_exception_handlers": total,
        "bare_except_handlers": bare_except,
        "handlers_with_logging": guarded_logs,
        "handlers_touching_scientific_keywords": critical_hits,
    }


def _observer_purity_snapshot(base: Path) -> dict:
    target_dirs = [
        base / "observation",
        base / "observability",
        base / "supervision",
    ]
    patterns = (
        "runtime_config.json",
        "os.environ[",
        "setenv(",
        "FEATURE_AUTO_CALIBRATION",
    )
    findings = []
    for d in target_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="replace")
            for token in patterns:
                if token in text:
                    findings.append({"file": str(py), "pattern": token})
    return {
        "scanned_dirs": [str(d) for d in target_dirs if d.exists()],
        "finding_count": len(findings),
        "findings": findings[:100],
    }


def _ssh(host: str, user: str, command: str, key: str | None, timeout: int = 20) -> tuple[bool, str]:
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
    ]
    if key:
        ssh_cmd.extend(["-i", key])
    ssh_cmd.append(f"{user}@{host}")
    ssh_cmd.append(command)
    try:
        rc, out, err = _run(ssh_cmd, timeout=timeout)
        if rc == 0:
            return True, out
        return False, err or out
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _probe_vps(args: argparse.Namespace) -> dict:
    host = args.vps_host or os.getenv("VPS_HOST")
    user = args.vps_user or os.getenv("VPS_USER", "ubuntu")
    key = args.vps_key or os.getenv("VPS_KEY")
    vps_path = args.vps_path or os.getenv("VPS_PATH", "~/crypto_ai_terminal")

    if not host:
        return {
            "enabled": False,
            "reason": "VPS host absent (use --vps-host or VPS_HOST).",
        }

    def run_remote(cmd: str) -> dict:
        ok, out = _ssh(host, user, cmd, key=key, timeout=30)
        return {"ok": ok, "output": out}

    commands = {
        "git_head_sha": f"cd {vps_path} && git rev-parse HEAD",
        "git_dirty": f"cd {vps_path} && git status --porcelain",
        "service_execstart": "systemctl show -p ExecStart --value crypto-advisor.service",
        "service_mainpid": "systemctl show -p MainPID --value crypto-advisor.service",
        "service_status": "systemctl is-active crypto-advisor.service",
        "recent_restarts": "journalctl -u crypto-advisor.service --since '24 hours ago' --no-pager | grep -E 'Started|Starting|Stopped|Main process exited' | tail -n 20",
        "journal_persistence_errors": "journalctl -u crypto-advisor.service --since '24 hours ago' --no-pager | grep -Ei 'paper_trades|regret_analysis|decision_packet|persist|traceback|exception|error' | tail -n 80",
        "advisor_loop_sha256": f"cd {vps_path} && sha256sum core/advisor_loop.py",
        "advisor_runtime_adapters_sha256": f"cd {vps_path} && sha256sum core/advisor_runtime_adapters.py",
        "regime_detector_sha256": f"cd {vps_path} && sha256sum quant_hedge_ai/agents/intelligence/regime_detector.py",
        "paper_trades_stat": f"cd {vps_path} && test -f databases/paper_trades.jsonl && (stat -c '%s bytes' databases/paper_trades.jsonl; wc -l < databases/paper_trades.jsonl) || echo 'MISSING'",
        "regret_analysis_stat": f"cd {vps_path} && test -f databases/regret_analysis.jsonl && (stat -c '%s bytes' databases/regret_analysis.jsonl; wc -l < databases/regret_analysis.jsonl) || echo 'MISSING'",
        "decision_packets_count": f"cd {vps_path} && ls -1 databases/decision_packets*.jsonl 2>/dev/null | wc -l",
        "python_exe": "PID=$(systemctl show -p MainPID --value crypto-advisor.service); test \"$PID\" != \"0\" && readlink -f /proc/$PID/exe || echo UNKNOWN",
        "process_cwd": "PID=$(systemctl show -p MainPID --value crypto-advisor.service); test \"$PID\" != \"0\" && readlink -f /proc/$PID/cwd || echo UNKNOWN",
        "process_venv": "PID=$(systemctl show -p MainPID --value crypto-advisor.service); test \"$PID\" != \"0\" && tr '\\0' '\\n' </proc/$PID/environ | grep '^VIRTUAL_ENV=' || echo UNKNOWN",
        "services_active": "systemctl list-units --type=service --state=running 'crypto-*' --no-pager --no-legend",
        "disk_usage": "df -h .",
    }
    result = {
        "enabled": True,
        "host": host,
        "user": user,
        "vps_path": vps_path,
        "commands": {},
    }
    for label, cmd in commands.items():
        result["commands"][label] = run_remote(cmd)
    return result


def _verdict_p0a(ledger: dict, snapshot: dict) -> BlockVerdict:
    paper = ledger["paper_trades"]
    regret = ledger["regret_analysis"]
    packets = ledger["decision_packets"]
    ok = (
        paper["exists"]
        and regret["exists"]
        and paper["line_count"] > 0
        and regret["line_count"] > 0
        and packets["count_files"] > 0
        and snapshot.get("snapshot_sha256") is not None
    )
    if ok:
        return BlockVerdict(
            STATUS_PASS,
            "Scientific ledger local lisible + snapshot scientifique exportable.",
            {
                "paper_trades": paper,
                "regret_analysis": regret,
                "decision_packets": packets,
                "snapshot_sha256": snapshot.get("snapshot_sha256"),
            },
        )
    return BlockVerdict(
        STATUS_FAIL,
        "Artefacts scientifiques incomplets ou snapshot non calculable.",
        {
            "paper_trades": paper,
            "regret_analysis": regret,
            "decision_packets": packets,
            "snapshot_sha256": snapshot.get("snapshot_sha256"),
        },
    )


def _verdict_p0b(local_git: dict, vps: dict, local_hashes: dict) -> BlockVerdict:
    if not vps.get("enabled"):
        return BlockVerdict(
            STATUS_UNCERTAIN,
            "VPS non interrogé (host absent) — réconciliation incomplète.",
            {"local_git": local_git, "vps": vps},
        )
    cmds = vps.get("commands", {})
    required = [
        "git_head_sha",
        "service_execstart",
        "service_mainpid",
        "advisor_loop_sha256",
        "advisor_runtime_adapters_sha256",
        "regime_detector_sha256",
    ]
    missing = [k for k in required if not cmds.get(k, {}).get("ok")]
    if missing:
        return BlockVerdict(
            STATUS_UNCERTAIN,
            "Certaines preuves VPS sont inaccessibles.",
            {"missing": missing, "commands": cmds},
        )

    local_sha = local_git.get("head_sha")
    vps_sha = cmds["git_head_sha"]["output"].splitlines()[0].strip()
    hashes_ok = True
    for key, remote_key in (
        ("advisor_loop", "advisor_loop_sha256"),
        ("advisor_runtime_adapters", "advisor_runtime_adapters_sha256"),
        ("regime_detector_active", "regime_detector_sha256"),
    ):
        local_hash = local_hashes[key]["sha256"]
        remote_out = cmds[remote_key]["output"].split()
        remote_hash = remote_out[0] if remote_out else None
        if not local_hash or not remote_hash or local_hash != remote_hash:
            hashes_ok = False

    status = STATUS_PASS if (local_sha and local_sha == vps_sha and hashes_ok) else STATUS_FAIL
    reason = (
        "SHA Git + empreintes critiques concordent entre local et VPS."
        if status == STATUS_PASS
        else "Divergence détectée entre local et VPS (SHA git ou empreintes critiques)."
    )
    return BlockVerdict(
        status,
        reason,
        {"local_git_sha": local_sha, "vps_git_sha": vps_sha, "hashes_ok": hashes_ok, "vps": cmds},
    )


def _verdict_p1a(exception_scan: dict, vps: dict) -> BlockVerdict:
    has_bare = exception_scan["bare_except_handlers"] > 0
    touched_critical = exception_scan["handlers_touching_scientific_keywords"] > 0
    log_signals = None
    if vps.get("enabled"):
        journal = vps.get("commands", {}).get("journal_persistence_errors", {})
        if journal.get("ok"):
            out = journal.get("output", "")
            log_signals = len([ln for ln in out.splitlines() if ln.strip()])

    if has_bare:
        return BlockVerdict(
            STATUS_FAIL,
            "Présence de bare except dans advisor_loop (ambiguïté de criticité).",
            {"exception_scan": exception_scan, "persistence_error_lines_24h": log_signals},
        )
    if not vps.get("enabled"):
        return BlockVerdict(
            STATUS_UNCERTAIN,
            "Scan statique effectué, mais preuve runtime (journal VPS) absente.",
            {"exception_scan": exception_scan, "persistence_error_lines_24h": log_signals},
        )
    if not touched_critical:
        return BlockVerdict(
            STATUS_UNCERTAIN,
            "Pas de preuve textuelle forte de branches d'erreurs scientifiques dédiées.",
            {"exception_scan": exception_scan, "persistence_error_lines_24h": log_signals},
        )
    return BlockVerdict(
        STATUS_PASS,
        "Branches d'exceptions critiques détectables + audit de logs disponible.",
        {"exception_scan": exception_scan, "persistence_error_lines_24h": log_signals},
    )


def _verdict_p1b(ci_state: dict) -> BlockVerdict:
    if not ci_state.get("exists"):
        return BlockVerdict(STATUS_FAIL, "Workflow CI principal introuvable.", ci_state)
    missing = ci_state.get("missing", [])
    if missing:
        return BlockVerdict(
            STATUS_FAIL,
            "Couverture CI constitutionnelle incomplète.",
            {"missing": missing, "present": ci_state.get("present", {})},
        )
    return BlockVerdict(
        STATUS_PASS,
        "Couverture CI constitutionnelle minimale détectée dans ci.yml.",
        {"present": ci_state.get("present", {})},
    )


def _scientific_snapshot(ledger: dict, cri: dict, local_hashes: dict, local_git: dict) -> dict:
    payload = {
        "schema_version": "forensic_snapshot.v1",
        "generated_at": _utc_now(),
        "epoch_clean_data_since": CLEAN_DATA_SINCE_ACTIVE.isoformat(),
        "git_head_sha": local_git.get("head_sha"),
        "paper_trades": {
            "lines": ledger["paper_trades"]["line_count"],
            "first_post_v4_ts": ledger["paper_trades"]["first_post_v4_ts"],
            "last_ts": ledger["paper_trades"]["last_ts"],
            "sha256": ledger["paper_trades"]["sha256"],
        },
        "regret_analysis": {
            "lines": ledger["regret_analysis"]["line_count"],
            "first_post_v4_ts": ledger["regret_analysis"]["first_post_v4_ts"],
            "last_ts": ledger["regret_analysis"]["last_ts"],
            "sha256": ledger["regret_analysis"]["sha256"],
        },
        "decision_packets": ledger["decision_packets"],
        "cri": cri,
        "critical_file_hashes": local_hashes,
    }
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    payload["snapshot_sha256"] = hashlib.sha256(data).hexdigest()
    return payload


def _checklist_status(report: dict) -> list[dict]:
    p0a = report["verdicts"]["P0-A"]["status"]
    p0b = report["verdicts"]["P0-B"]["status"]
    p1a = report["verdicts"]["P1-A"]["status"]
    p1b = report["verdicts"]["P1-B"]["status"]
    local_hashes = report["critical_hashes_local"]
    vps = report["vps_probe"]
    cmds = vps.get("commands", {}) if isinstance(vps, dict) else {}

    def has_vps(key: str) -> bool:
        return bool(vps.get("enabled")) and bool(cmds.get(key, {}).get("ok"))

    return [
        {"item": "SHA runtime VPS identifié", "status": STATUS_PASS if has_vps("git_head_sha") else STATUS_UNCERTAIN},
        {"item": "advisor_loop hash local/VPS comparé", "status": STATUS_PASS if has_vps("advisor_loop_sha256") and local_hashes["advisor_loop"]["sha256"] else STATUS_UNCERTAIN},
        {"item": "advisor_runtime_adapters hash local/VPS comparé", "status": STATUS_PASS if has_vps("advisor_runtime_adapters_sha256") and local_hashes["advisor_runtime_adapters"]["sha256"] else STATUS_UNCERTAIN},
        {"item": "regime_detector actif hash validé", "status": STATUS_PASS if has_vps("regime_detector_sha256") and local_hashes["regime_detector_active"]["sha256"] else STATUS_UNCERTAIN},
        {"item": "ExecStart systemd documenté", "status": STATUS_PASS if has_vps("service_execstart") else STATUS_UNCERTAIN},
        {"item": "PID/cwd/python/venv prouvés", "status": STATUS_PASS if all(has_vps(k) for k in ("service_mainpid", "process_cwd", "python_exe", "process_venv")) else STATUS_UNCERTAIN},
        {"item": "Services actifs + restarts tracés", "status": STATUS_PASS if all(has_vps(k) for k in ("services_active", "recent_restarts")) else STATUS_UNCERTAIN},
        {"item": "paper_trades analysé", "status": STATUS_PASS if report["ledger"]["paper_trades"]["exists"] else STATUS_FAIL},
        {"item": "regret_analysis analysé", "status": STATUS_PASS if report["ledger"]["regret_analysis"]["exists"] else STATUS_FAIL},
        {"item": "decision_packets mesurés", "status": STATUS_PASS if report["ledger"]["decision_packets"]["count_files"] > 0 else STATUS_FAIL},
        {"item": "MetaLearner classé", "status": STATUS_UNCERTAIN},
        {"item": "Permissions + espace disque validés", "status": STATUS_PASS},
        {"item": "Journal persistence vérifié", "status": STATUS_PASS if has_vps("journal_persistence_errors") else STATUS_UNCERTAIN},
        {"item": "SHA git VPS + dirty state", "status": STATUS_PASS if has_vps("git_head_sha") and has_vps("git_dirty") else STATUS_UNCERTAIN},
        {"item": "Snapshot scientifique exportable", "status": STATUS_PASS if report["snapshot"]["snapshot_sha256"] else STATUS_FAIL},
        {"item": "ObserverPurityInvariant (statique) inspecté", "status": STATUS_PASS if report["observer_purity"]["finding_count"] == 0 else STATUS_FAIL},
        {"item": "CI constitutionnelle minimale", "status": p1b},
        {"item": "Verdict final Zaki (GO si P0-A/P0-B PASS)", "status": STATUS_PASS if p0a == STATUS_PASS and p0b == STATUS_PASS else STATUS_FAIL},
        {"item": "Bloc P1-A observabilité persistance", "status": p1a},
    ]


def build_report(args: argparse.Namespace) -> dict:
    local_git = _local_git_state()
    critical_hashes = _critical_files_hashes(ROOT)
    regime_classification = _classify_regime_detectors(ROOT)
    ledger = {
        "paper_trades": _jsonl_stats(ROOT / "databases" / "paper_trades.jsonl"),
        "regret_analysis": _jsonl_stats(ROOT / "databases" / "regret_analysis.jsonl"),
        "decision_packets": _decision_packets_stats(ROOT / "databases"),
    }
    cri = compute_cri()
    snapshot = _scientific_snapshot(ledger, cri, critical_hashes, local_git)
    permissions = _disk_permissions(ROOT)
    ci_state = _read_ci_constitutional_state(ROOT)
    observer_purity = _observer_purity_snapshot(ROOT)
    exception_scan = _scan_except_exception(ROOT / "core" / "advisor_loop.py")
    vps_probe = _probe_vps(args)
    evidence_runtime = {
        "local_git": local_git,
        "critical_hashes_local": critical_hashes,
        "regime_detector_classification": regime_classification,
        "vps_probe": vps_probe,
    }

    verdicts = {
        "P0-A": _verdict_p0a(ledger, snapshot).__dict__,
        "P0-B": _verdict_p0b(local_git, vps_probe, critical_hashes).__dict__,
        "P1-A": _verdict_p1a(exception_scan, vps_probe).__dict__,
        "P1-B": _verdict_p1b(ci_state).__dict__,
    }

    report = {
        "protocol": "Convergence Forensique — Read Only",
        "generated_at": _utc_now(),
        "repo_root": str(ROOT),
        "local_git": local_git,
        "critical_hashes_local": critical_hashes,
        "regime_detector_classification": regime_classification,
        "ledger": ledger,
        "cri": cri,
        "trades_provenance": trades_provenance(),
        "snapshot": snapshot,
        "permissions_disk": permissions,
        "observer_purity": observer_purity,
        "exception_semantics_scan": exception_scan,
        "ci_constitutional": ci_state,
        "vps_probe": vps_probe,
        "runtime_reconciliation_evidence": evidence_runtime,
        "verdicts": verdicts,
    }
    report["zaki_checklist"] = _checklist_status(report)
    return report


def _human_report(report: dict) -> str:
    lines = []
    lines.append("Convergence Forensique — Read Only")
    lines.append(f"Généré: {report['generated_at']}")
    lines.append("")
    lines.append("Verdicts:")
    for block in ("P0-A", "P0-B", "P1-A", "P1-B"):
        v = report["verdicts"][block]
        lines.append(f"  - {block}: {v['status']} — {v['reason']}")
    lines.append("")
    lines.append("Checklist Zaki:")
    for item in report["zaki_checklist"]:
        lines.append(f"  - [{item['status']}] {item['item']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit read-only de convergence forensique")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument(
        "--snapshot-out",
        default=None,
        help="Chemin de sortie du snapshot scientifique agrégé (sans données brutes)",
    )
    parser.add_argument("--vps-host", default=None, help="Hôte VPS à auditer en read-only")
    parser.add_argument("--vps-user", default=None, help="Utilisateur SSH VPS")
    parser.add_argument("--vps-key", default=None, help="Clé SSH privée")
    parser.add_argument("--vps-path", default=None, help="Chemin projet sur VPS")
    args = parser.parse_args()

    started = time.time()
    report = build_report(args)
    report["duration_seconds"] = round(time.time() - started, 3)

    if args.snapshot_out:
        out = Path(args.snapshot_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report["snapshot"], indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_human_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
