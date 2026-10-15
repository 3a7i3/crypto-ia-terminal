"""Exécution des scénarios, écriture des artefacts, vérification de reproductibilité."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from lab01 import LAB_VERSION, PROVENANCE
from lab01.events import canonical, verify_chain
from lab01.guards import assert_clean_environment, assert_safe_output_dir, deny_network

ID_RE = r"^LAB01-[a-z_]+-[0-9a-f]{12}$"


@contextlib.contextmanager
def lab_context(out_dir: Path, *, quiet: bool = True):
    """Journaux du runtime importé redirigés sous out_dir ; état global restauré."""
    prev_env = os.environ.get("OBS_LOG_ROOT")
    prev_disable = logging.root.manager.disable
    os.environ["OBS_LOG_ROOT"] = str(out_dir / "_logs")
    if quiet:
        logging.disable(logging.INFO)
    try:
        yield
    finally:
        logging.disable(prev_disable)
        if prev_env is None:
            os.environ.pop("OBS_LOG_ROOT", None)
        else:
            os.environ["OBS_LOG_ROOT"] = prev_env


def _git_head() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=Path(__file__).resolve().parent.parent,
            ).stdout.strip()
            or "UNKNOWN"
        )
    except Exception:
        return "UNKNOWN"


def run_all(
    out_dir: str | os.PathLike,
    names: list[str] | None = None,
    *,
    network_guard: bool = True,
) -> list[dict]:
    out = assert_safe_output_dir(out_dir)
    assert_clean_environment()
    out.mkdir(parents=True, exist_ok=True)
    with lab_context(out):
        return _run_all(out, names, network_guard)


def _run_all(out: Path, names, network_guard: bool) -> list[dict]:
    from lab01.engine import run_scenario  # import tardif : après bootstrap
    from lab01.scenarios import SCENARIOS

    selected = names or list(SCENARIOS)
    unknown = [n for n in selected if n not in SCENARIOS]
    if unknown:
        raise SystemExit(f"scénario inconnu : {unknown}")

    results = []
    guard = deny_network() if network_guard else _null()
    with guard:
        for name in selected:
            run = run_scenario(SCENARIOS[name])
            results.append(_write(out, run, network_guard))
    index = {
        "schema": "lab01.index/1",
        "provenance": PROVENANCE,
        "experiments": [_brief(r) for r in results],
    }
    (out / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return results


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _brief(r: dict) -> dict:
    keys = (
        "experiment_id",
        "trace_id",
        "scenario",
        "title",
        "verdict",
        "final_state",
        "risk_reason_code",
        "error_code",
        "synthetic_pnl_usd",
        "events_digest",
        "provenance",
    )
    return {k: r.get(k) for k in keys}


def _write(out: Path, run: dict, network_guard: bool) -> dict:
    r = run["result"]
    d = out / r["experiment_id"]
    d.mkdir(parents=True, exist_ok=True)
    with (d / "events.jsonl").open("w", encoding="utf-8") as fh:
        for e in run["events"]:
            fh.write(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n")
    (d / "result.json").write_text(
        json.dumps(r, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    (d / "bars.json").write_text(
        json.dumps([b.as_dict() for b in run["bars"]], sort_keys=True) + "\n"
    )
    # Le DecisionPacket réel horodate ses transitions à l'heure murale : fichier
    # fourni pour lecture, exclu de tout digest de reproductibilité.
    (d / "packet.json").write_text(
        json.dumps(run["packet"], indent=2, sort_keys=True, default=str) + "\n"
    )
    manifest = {
        "schema": "lab01.manifest/1",
        "provenance": PROVENANCE,
        "lab_version": LAB_VERSION,
        "experiment_id": r["experiment_id"],
        "trace_id": r["trace_id"],
        "code_digest": r["code_digest"],
        "config_digest": r["config_digest"],
        "seed": r["seed"],
        "exec_seed": r["exec_seed"],
        "git_head": _git_head(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "network_guard_in_process": network_guard,
        "wall_clock_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "digest_scope": "events.jsonl (horloge synthétique) ; manifest.wall_clock_utc et "
        "packet.json exclus",
    }
    (d / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return r


def verify_reproducible(names: list[str] | None = None) -> list[dict]:
    """Rejoue deux fois chaque scénario en mémoire ; compare les empreintes."""
    import tempfile

    with (
        tempfile.TemporaryDirectory(prefix="lab01-verify-") as tmp,
        lab_context(Path(tmp)),
    ):
        from lab01.engine import run_scenario
        from lab01.scenarios import SCENARIOS

        report = []
        with deny_network():
            for name in names or list(SCENARIOS):
                a, b = run_scenario(SCENARIOS[name]), run_scenario(SCENARIOS[name])
                same = a["result"]["events_digest"] == b["result"][
                    "events_digest"
                ] and canonical(a["events"]) == canonical(b["events"])
                report.append(
                    {
                        "scenario": name,
                        "reproducible": same,
                        "events_digest": a["result"]["events_digest"],
                        "chain_valid": verify_chain(a["events"]),
                        "verdict": a["result"]["verdict"],
                    }
                )
        return report


def verify_written(out_dir: str | os.PathLike) -> list[dict]:
    """Relit les journaux écrits et revérifie la chaîne (détecte l'altération)."""
    out, report = Path(out_dir), []
    for p in sorted(out.glob("LAB01-*/events.jsonl")):
        events = [json.loads(line) for line in p.read_text().splitlines() if line]
        report.append(
            {
                "experiment_id": p.parent.name,
                "chain_valid": verify_chain(events),
                "n_events": len(events),
            }
        )
    return report
