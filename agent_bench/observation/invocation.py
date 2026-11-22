"""Contrat d'invocation versionné `cat.observation.invocation.v1` et lecteur de preuves.

Une invocation est publiée comme un seul fichier JSON : l'enveloppe contient le rapport
scellé. Un fichier incomplet ou absent n'est jamais une preuve. Ce module ne lance aucune
mission et n'écrit aucun service : il valide, classe et résume.

Distinctions (ne pas les confondre) :
- qualification du profil (agent_id, profile.blob_sha1) ;
- identité du runner (runner_id) ;
- état d'exécution (COMPLETED, FAILED, TIMEOUT, INTERRUPTED, ABANDONED) ;
- résultat scientifique du rapport (COMPLETE, PARTIAL, BLOCKED, FAILED).

Un code de sortie 0 ne prouve pas la validité du rapport : seul le recalcul des empreintes
et la cohérence des identités le font.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from agent_bench.observation import contract as c

INVOCATION_CONTRACT = "cat.observation.invocation.v1"
CONTRACT_VERSION = 1

EXECUTION_STATES = ("COMPLETED", "FAILED", "TIMEOUT", "INTERRUPTED", "ABANDONED")
TERMINAL_STATES = EXECUTION_STATES
RESULT_STATUSES = ("COMPLETE", "PARTIAL", "BLOCKED", "FAILED")

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

# Lecture : bornes de taille (un fichier de preuve est petit ; le rapport de zone fait ~330 Ko).
MAX_PROOF_BYTES = 2 * 1024 * 1024
MAX_FILES_LISTED = 50
MAX_PROOF_AGE_S = 15 * 60
CLOCK_SKEW_S = 60

ENVELOPE_KEYS = {
    "contract", "contract_version", "invocation_id", "agent_id", "runner_id", "mission_id",
    "profile_blob_sha1", "code_sha", "analysed_sha", "started_utc", "ended_utc", "state",
    "exit_code", "interruption_reason", "result_status", "report_sha256", "content_sha256",
    "limits", "report",
}


def parse_utc(v):
    """Date UTC ISO 8601 se terminant par Z, ou None."""
    if not isinstance(v, str) or not UTC_RE.match(v):
        return None
    try:
        return datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() + (
            float("0" + v[19:-1]) if "." in v else 0.0)
    except ValueError:
        return None


def utc_now_iso(ts=None):
    ts = datetime.now(timezone.utc).timestamp() if ts is None else ts
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_envelope(*, invocation_id, agent_id, runner_id, mission, code_sha, analysed_sha,
                  started_utc, ended_utc, state, exit_code, interruption_reason, report,
                  limits):
    """Construit l'enveloppe. `report` est le rapport scellé (ou None si aucune sortie)."""
    if state not in EXECUTION_STATES:
        raise ValueError("state")
    rep = report or {}
    content = rep.get("content") or {}
    return {
        "contract": INVOCATION_CONTRACT,
        "contract_version": CONTRACT_VERSION,
        "invocation_id": invocation_id,
        "agent_id": agent_id,
        "runner_id": runner_id,
        "mission_id": mission["mission_id"],
        "profile_blob_sha1": mission["profile"]["blob_sha1"],
        "code_sha": code_sha,
        "analysed_sha": analysed_sha,
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "state": state,
        "exit_code": exit_code,
        "interruption_reason": interruption_reason,
        "result_status": content.get("status") if report else None,
        "report_sha256": rep.get("report_sha256"),
        "content_sha256": rep.get("content_sha256"),
        "limits": limits,
        "report": report,
    }


def validate_envelope(env, *, agent_id, runner_id, mission_id, now_ts):
    """Retourne (classe, motif). classe ∈ VALID, INVALID, INCOMPLETE, FUTURE, STALE_PROOF.

    VALID signifie : schéma, identités, chronologie, empreintes cohérents. Il ne signifie
    pas que le rapport est complet ni que le runner travaille encore.
    """
    if not isinstance(env, dict):
        return "INVALID", "enveloppe non objet"
    if set(env) != ENVELOPE_KEYS:
        missing = sorted(ENVELOPE_KEYS - set(env))
        extra = sorted(set(env) - ENVELOPE_KEYS)
        if missing:
            return "INCOMPLETE", f"champs manquants: {','.join(missing)}"
        return "INVALID", f"champs inattendus: {','.join(extra)}"
    if env["contract"] != INVOCATION_CONTRACT or env["contract_version"] != CONTRACT_VERSION:
        return "INVALID", "version de contrat inconnue"
    if not (isinstance(env["invocation_id"], str) and HEX32.match(env["invocation_id"])):
        return "INVALID", "invocation_id"
    if env["agent_id"] != agent_id:
        return "INVALID", "agent_id différent"
    if env["runner_id"] != runner_id:
        return "INVALID", "runner_id différent du runner attendu"
    if env["mission_id"] != mission_id:
        return "INVALID", "mission_id différent"
    # Une invocation ABANDONED n'a pas pu prouver ses SHA : ils restent null, jamais inventés.
    abandoned = env["state"] == "ABANDONED"
    if not (abandoned and env["profile_blob_sha1"] is None) and not (
            isinstance(env["profile_blob_sha1"], str) and re.match(r"^[0-9a-f]{40}$", env["profile_blob_sha1"])):
        return "INVALID", "empreinte de profil"
    for k in ("code_sha", "analysed_sha"):
        if abandoned and env[k] is None:
            continue
        if not (isinstance(env[k], str) and HEX40.match(env[k])):
            return "INVALID", f"{k} absent ou malformé"
    started, ended = parse_utc(env["started_utc"]), parse_utc(env["ended_utc"])
    if started is None or ended is None:
        return "INVALID", "dates UTC invalides"
    if ended < started:
        return "INVALID", "fin antérieure au début"
    if started > now_ts + CLOCK_SKEW_S or ended > now_ts + CLOCK_SKEW_S:
        return "FUTURE", "date future"
    if env["state"] not in EXECUTION_STATES:
        return "INVALID", "état d'exécution inconnu"
    if env["state"] in ("COMPLETED", "FAILED") and env["exit_code"] is None:
        return "INVALID", "code de sortie absent"
    if env["state"] in ("TIMEOUT", "INTERRUPTED", "ABANDONED") and not env["interruption_reason"]:
        return "INVALID", "motif d'interruption absent"
    rep = env["report"]
    if env["state"] == "COMPLETED":
        if not isinstance(rep, dict):
            return "INCOMPLETE", "rapport absent"
        if set(rep) != {"content", "content_sha256", "run", "report_sha256"}:
            return "INVALID", "enveloppe de rapport inattendue"
        if rep["content_sha256"] != c.sha256_json(rep["content"]):
            return "INVALID", "empreinte du contenu altérée"
        if rep["report_sha256"] != c.sha256_json({"content": rep["content"],
                                                  "content_sha256": rep["content_sha256"],
                                                  "run": rep["run"]}):
            return "INVALID", "empreinte du rapport altérée"
        if rep["content"].get("mission_id") != mission_id:
            return "INVALID", "rapport d'une autre mission"
        if rep["content"].get("status") not in RESULT_STATUSES:
            return "INVALID", "statut de résultat inconnu"
        if env["result_status"] != rep["content"]["status"]:
            return "INVALID", "résultat déclaré incohérent avec le rapport"
        if env["content_sha256"] != rep["content_sha256"] or env["report_sha256"] != rep["report_sha256"]:
            return "INVALID", "empreintes d'enveloppe incohérentes"
    else:
        if rep is not None or env["result_status"] is not None:
            return "INVALID", "rapport présent sur une invocation non terminée avec rapport"
    return "VALID", "ok"


def classify_latest(env, now_ts, *, agent_id, runner_id, mission_id):
    """Classe une enveloppe lue. Relire un ancien fichier ne modifie jamais ses dates."""
    verdict, reason = validate_envelope(env, agent_id=agent_id, runner_id=runner_id,
                                        mission_id=mission_id, now_ts=now_ts)
    if verdict == "VALID":
        return {"proof": "VALID", "reason": reason, "last_activity_utc": env["ended_utc"],
                "observed_at_utc": utc_now_iso(now_ts), "state": env["state"],
                "result_status": env["result_status"]}
    return {"proof": verdict, "reason": reason, "last_activity_utc": None,
            "observed_at_utc": utc_now_iso(now_ts), "state": None, "result_status": None}


def json_load_bounded(raw: bytes):
    if len(raw) > MAX_PROOF_BYTES:
        raise ValueError("TOO_LARGE")
    return json.loads(raw.decode("utf-8"))
