"""Exécuteur des observateurs de données runtime (famille Observation, décision 2026-11-23).

Différence avec ``executor`` : l'agent n'analyse pas un SHA du dépôt, il lit des données déjà
servies sur le VPS. Ce qui ne change pas : une invocation par appel, verrou noyau, refus avant
verrouillage, publication atomique sans écrasement, enveloppe scellée, aucune relance.

Lecture strictement bornée :
- GET seulement, vers 127.0.0.1 et des ports listés ici (API opérateur 8090, scanner 18906) ;
- chemins sous ``/api/operator/v1/`` ; réponse ≤ 2 Mio ; délai par requête ≤ 10 s ;
- aucun en-tête d'authentification, aucun secret, aucune écriture hors du dossier de l'agent.

Contrat d'enveloppe ``cat.observation.runtime-invocation.v1`` (validé par
``invocation.validate_runtime_envelope``) : mêmes champs d'identité, d'état et de sceau que v1 ;
pas de SHA analysé (rien n'est analysé dans git) ; ``verification`` porte le HEAD du checkout, les
empreintes des modules exécutés et du profil.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import signal
import sys
import time
from pathlib import Path

from agent_bench.observation import contract as c
from agent_bench.observation import executor as ex
from agent_bench.observation import invocation as inv
from agent_bench.observation import market_observer as mo

RUNTIME_MISSION_CONTRACT = "cat.observation.runtime-mission.v1"
ALLOWED_PORTS = (8090, 18906)
PATH_PREFIX = "/api/operator/v1/"
MAX_BODY = 2 * 1024 * 1024
REQUEST_TIMEOUT_S = 10
ANALYSERS = {"market-observer": mo.analyse}
MISSION_KEYS = {"contract", "agent_id", "mission_id", "domain", "profile", "sources", "thresholds", "budget"}


def mission_id_of(mission: dict) -> str:
    return c.sha256_json({k: v for k, v in mission.items() if k != "mission_id"})


def validate_mission(m) -> None:
    if not isinstance(m, dict) or set(m) != MISSION_KEYS:
        raise ex.Refused("MISSION_REJECTED", "schéma")
    if m["contract"] != RUNTIME_MISSION_CONTRACT or m["agent_id"] not in ANALYSERS:
        raise ex.Refused("MISSION_REJECTED", "contrat ou agent")
    if m["mission_id"] != mission_id_of(m):
        raise ex.Refused("MISSION_REJECTED", "mission_id")
    p = m["profile"]
    if not (isinstance(p, dict) and isinstance(p.get("source_path"), str) and inv.HEX40.match(str(p.get("blob_sha1")))):
        raise ex.Refused("MISSION_REJECTED", "profil")
    srcs = m["sources"]
    if not (isinstance(srcs, list) and 0 < len(srcs) <= 8):
        raise ex.Refused("MISSION_REJECTED", "sources")
    for s in srcs:
        if not (isinstance(s, dict) and set(s) == {"id", "port", "path"} and s["port"] in ALLOWED_PORTS
                and isinstance(s["path"], str) and s["path"].startswith(PATH_PREFIX)
                and ".." not in s["path"] and all(ch.isprintable() and ch not in " ?#" for ch in s["path"])):
            raise ex.Refused("MISSION_REJECTED", "source hors liste")
    b = m["budget"]
    if not (isinstance(b, dict) and isinstance(b.get("max_wall_ms"), int) and 0 < b["max_wall_ms"] <= inv.MAX_RUN_S * 1000):
        raise ex.Refused("MISSION_REJECTED", "budget")


def fetch(port: int, path: str):
    """GET borné vers 127.0.0.1:port. Ne lève pas : une panne est consignée."""
    out = {"http_status": None, "body": None, "bytes": None, "sha256": None, "error": None}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=REQUEST_TIMEOUT_S)
    try:
        conn.request("GET", path, headers={"Accept": "application/json", "User-Agent": "cat-obs-runtime/1"})
        r = conn.getresponse()
        raw = r.read(MAX_BODY + 1)
        out["http_status"] = r.status
        if len(raw) > MAX_BODY:
            out["error"] = "réponse trop volumineuse"
            return out
        out["bytes"], out["sha256"] = len(raw), hashlib.sha256(raw).hexdigest()
        if r.status == 200:
            out["body"] = json.loads(raw.decode("utf-8"))
    except (OSError, http.client.HTTPException) as exc:
        out["error"] = type(exc).__name__
    except ValueError:
        out["error"] = "JSON invalide"
    finally:
        conn.close()
    return out


def verify_code(checkout: Path, *, code_sha: str, mission: dict) -> dict:
    head = ex._git(checkout, "rev-parse", "HEAD")
    if head.returncode != 0 or head.stdout.decode().strip() != code_sha:
        raise ex.Refused("CHECKOUT_HEAD_MISMATCH")
    prof = mission["profile"]
    if ex._blob_at(checkout, code_sha, prof["source_path"]) != prof["blob_sha1"]:
        raise ex.Refused("PROFILE_MISMATCH")
    if ex._hash_file(checkout, checkout / prof["source_path"]) != prof["blob_sha1"]:
        raise ex.Refused("PROFILE_MODIFIED")
    modules = {}
    for rel, path in ex.executed_module_files().items():
        blob = ex._blob_at(checkout, code_sha, rel)
        if blob is None or ex._hash_file(checkout, path) != blob:
            raise ex.Refused("MODULE_MISMATCH", rel)
        modules[rel] = blob
    return {"checkout_head": code_sha, "executed_modules": modules,
            "profile_source_path": prof["source_path"], "profile_blob_sha1": prof["blob_sha1"]}


def run_once(*, mission, checkout: Path, reports: Path, runner_id, code_sha, fetcher=fetch,
             clock=time.time, verify=True):
    if not (isinstance(code_sha, str) and inv.HEX40.match(code_sha)):
        raise ex.Refused("CODE_SHA_INVALID")
    if not inv.ID_RE.match(runner_id):
        raise ex.Refused("RUNNER_ID_INVALID")
    validate_mission(mission)
    agent_id = mission["agent_id"]
    verification = verify_code(checkout, code_sha=code_sha, mission=mission) if verify else None
    max_run_s = min(inv.MAX_RUN_S, mission["budget"]["max_wall_ms"] / 1000)

    lock = ex.RunnerLock(reports, runner_id).acquire()
    try:
        now = clock()
        prev = lock.previous()
        try:
            if isinstance(prev, dict) and isinstance(prev.get("invocation_id"), str) \
                    and inv.HEX32.match(prev["invocation_id"]) and isinstance(prev.get("mission_id"), str) \
                    and inv.parse_utc(prev.get("started_utc")) is not None \
                    and prev["invocation_id"] not in ex._published_ids(reports, prev["mission_id"]):
                ex.publish(reports, ex._abandoned_envelope(prev, agent_id=agent_id, runner_id=runner_id, now=now))
            ex._cleanup_partials(reports, mission["mission_id"])
        except OSError as exc:
            raise ex.Refused("PUBLICATION_FAILED", f"dossier de preuves non sûr ({type(exc).__name__})") from exc
        invocation_id = secrets.token_hex(16)
        started_ts = clock()
        lock.write(inv.make_lock(agent_id=agent_id, runner_id=runner_id, mission_id=mission["mission_id"],
                                 invocation_id=invocation_id, pid=os.getpid(), now=started_ts,
                                 lease_s=inv.MAX_LEASE_S))
        report, state, exit_code, reason = None, "FAILED", 1, None

        def _alarm(_s, _f):
            raise ex._Timeout()

        def _term(_s, _f):
            raise ex._Interrupted()

        old_alarm, old_term = signal.signal(signal.SIGALRM, _alarm), signal.signal(signal.SIGTERM, _term)
        try:
            signal.setitimer(signal.ITIMER_REAL, max_run_s)
            responses = {s["id"]: fetcher(s["port"], s["path"]) for s in mission["sources"]}
            content = ANALYSERS[agent_id](responses, mission, int(clock() * 1000))
            report = c.seal_report(content, {"observed_at_utc": inv.utc_iso(clock()), "code_sha": code_sha})
            state, exit_code = "COMPLETED", 0
        except ex._Timeout:
            state, exit_code, reason = "TIMEOUT", None, f"durée > {max_run_s} s"
        except (ex._Interrupted, KeyboardInterrupt):
            state, exit_code, reason = "INTERRUPTED", None, "interruption contrôlée (SIGTERM/SIGINT)"
        except Exception as exc:  # noqa: BLE001 — une panne devient FAILED, jamais un succès
            state, exit_code, reason = "FAILED", 1, type(exc).__name__
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)
            signal.signal(signal.SIGTERM, old_term)
        content = (report or {}).get("content") or {}
        env = {
            "contract": inv.RUNTIME_INVOCATION_CONTRACT, "contract_version": inv.CONTRACT_VERSION,
            "invocation_id": invocation_id, "agent_id": agent_id, "runner_id": runner_id,
            "mission_id": mission["mission_id"], "profile_blob_sha1": mission["profile"]["blob_sha1"],
            "code_sha": code_sha, "started_utc": inv.utc_iso(started_ts),
            "ended_utc": inv.utc_iso(max(clock(), started_ts)), "state": state, "exit_code": exit_code,
            "interruption_reason": reason, "result_status": content.get("status") if report else None,
            "report_sha256": (report or {}).get("report_sha256"), "content_sha256": (report or {}).get("content_sha256"),
            "limits": {"max_run_s": max_run_s, "max_body_bytes": MAX_BODY, "sources": len(mission["sources"])},
            "verification": verification, "report": report if state == "COMPLETED" else None,
        }
        if state != "COMPLETED":
            env.update(result_status=None, report_sha256=None, content_sha256=None)
        try:
            name = ex.publish(reports, env)
        except ex.Refused:
            raise
        except OSError as exc:
            raise ex.Refused("PUBLICATION_FAILED", type(exc).__name__) from exc
        return env, name
    finally:
        lock.release()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m agent_bench.observation.runtime_observer",
                                 description="Invocation ponctuelle d'un observateur de données runtime (GET loopback).")
    ap.add_argument("--mission", required=True)
    ap.add_argument("--checkout", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--runner-id", required=True)
    ap.add_argument("--code-sha", required=True)
    a = ap.parse_args(argv)
    out = {"contract": inv.RUNTIME_INVOCATION_CONTRACT}
    try:
        mission = json.loads(Path(a.mission).read_text(encoding="utf-8"))
        ex._apply_rlimits(inv.MAX_RUN_S)
        env, name = run_once(mission=mission, checkout=Path(a.checkout), reports=Path(a.reports),
                             runner_id=a.runner_id, code_sha=a.code_sha)
    except ex.Refused as exc:
        out.update({"outcome": "REFUSED" if exc.code != "PUBLICATION_FAILED" else "PUBLICATION_FAILED",
                    "code": exc.code, "detail": exc.detail})
        print(json.dumps(out, ensure_ascii=False))
        return ex.EXIT_PUBLICATION_FAILED if exc.code == "PUBLICATION_FAILED" else ex.EXIT_REFUSED
    except (OSError, ValueError) as exc:
        out.update({"outcome": "REFUSED", "code": "CONFIGURATION_INVALID", "detail": type(exc).__name__})
        print(json.dumps(out, ensure_ascii=False))
        return ex.EXIT_REFUSED
    ct = (env["report"] or {}).get("content") or {}
    out.update({"outcome": "PUBLISHED", "file": name, "invocation_id": env["invocation_id"], "state": env["state"],
                "result_status": env["result_status"], "verdicts": ct.get("verdict_counts"),
                "findings": [f["code"] for f in ct.get("findings") or []], "content_sha256": env["content_sha256"]})
    print(json.dumps(out, ensure_ascii=False))
    return ex.EXIT_PUBLISHED_OK if env["state"] == "COMPLETED" else ex.EXIT_PUBLISHED_NOT_COMPLETED


if __name__ == "__main__":
    sys.exit(main())
