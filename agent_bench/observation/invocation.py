"""Contrat d'invocation `cat.observation.invocation.v1` : enveloppe, verrou et règles de validation.

Une invocation est publiée comme un seul fichier JSON : l'enveloppe contient le rapport scellé
et le bloc `verification` (SHA du checkout, empreintes des modules exécutés, empreintes du
périmètre au SHA analysé). Ce module ne lance rien et n'écrit rien : il valide.

Niveaux distincts (à ne pas confondre) :
- qualification du profil : `agent_id`, `profile_blob_sha1` ;
- identité du runner : `runner_id` ;
- état d'exécution : COMPLETED, FAILED, TIMEOUT, INTERRUPTED, ABANDONED ;
- résultat scientifique : COMPLETE, PARTIAL, BLOCKED, FAILED (dans le rapport).

Les empreintes sont recalculées, mais elles ne remplacent pas les comparaisons d'identité :
un rapport correctement scellé d'un autre agent ou d'un autre SHA reste invalide.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from agent_bench.observation import contract as c

INVOCATION_CONTRACT = "cat.observation.invocation.v1"
# Observateurs de données runtime (pas de SHA analysé) : voir runtime_observer.
RUNTIME_INVOCATION_CONTRACT = "cat.observation.runtime-invocation.v1"
RUNTIME_REPORT_CONTRACT = "cat.observation.runtime-report.v1"
RUNTIME_ENVELOPE_KEYS = {
    "contract", "contract_version", "invocation_id", "agent_id", "runner_id", "mission_id",
    "profile_blob_sha1", "code_sha", "started_utc", "ended_utc", "state", "exit_code",
    "interruption_reason", "result_status", "report_sha256", "content_sha256", "limits",
    "verification", "report",
}
RUNTIME_VERIFICATION_KEYS = {"checkout_head", "executed_modules", "profile_source_path", "profile_blob_sha1"}
LOCK_CONTRACT = "cat.observation.invocation-lock.v1"
CONTRACT_VERSION = 1

EXECUTION_STATES = ("COMPLETED", "FAILED", "TIMEOUT", "INTERRUPTED", "ABANDONED")
RESULT_STATUSES = ("COMPLETE", "PARTIAL", "BLOCKED", "FAILED")
FAILED_STATES = ("FAILED", "TIMEOUT", "INTERRUPTED", "ABANDONED")

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
NAME_RE = re.compile(r"^(\d{8}T\d{6}Z)_([0-9a-f]{32})\.json$")

# Bornes (non modifiables par argument : un argument ne peut que les abaisser).
MAX_RUN_S = 120                 # durée maximale d'une invocation
MAX_LEASE_S = 600               # durée maximale d'un bail de verrou
MAX_FILES = 30                  # périmètre de mission (REPOSITORY_MAP)
# Borne de fichiers par type de question. La chaîne d'un dataset traverse plus de fichiers
# (producteur, lecteur, route, client, vue, capture) : 60, comme le budget du pilote (50) arrondi.
MAX_FILES_BY_KIND = {"REPOSITORY_MAP": MAX_FILES, "DATASET_PROVENANCE_CHAIN": 60,
                     "METRIC_SURFACE_MAP": MAX_FILES, "CHANGE_IMPACT": MAX_FILES}
MAX_PROOF_BYTES = 2 * 1024 * 1024
MAX_DIR_ENTRIES = 200           # énumération réellement bornée d'un dossier de preuves
CLOCK_SKEW_S = 60
DISPLAY_TTL_S = 90              # validité d'un affichage vert/rouge sans nouvelle réponse
ABSENCE_WINDOW_S = 36 * 3600    # règle des 36 h : dernière mission trop ancienne

ENVELOPE_KEYS = {
    "contract", "contract_version", "invocation_id", "agent_id", "runner_id", "mission_id",
    "profile_blob_sha1", "code_sha", "analysed_sha", "started_utc", "ended_utc", "state",
    "exit_code", "interruption_reason", "result_status", "report_sha256", "content_sha256",
    "limits", "verification", "report",
}
VERIFICATION_KEYS = {"checkout_head", "executed_modules", "scope_blobs", "profile_source_path",
                     "profile_blob_sha1"}
LOCK_KEYS = {"contract", "agent_id", "runner_id", "mission_id", "invocation_id", "pid",
             "started_utc", "lease_until_utc"}


def parse_utc(v):
    """Date UTC `AAAA-MM-JJThh:mm:ssZ` (seconde entière), ou None."""
    if not isinstance(v, str) or not UTC_RE.match(v):
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def utc_iso(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso(ts=None):
    return utc_iso(datetime.now(timezone.utc).timestamp() if ts is None else ts)


def stamp_of(utc_str):
    """`2026-11-22T01:02:03Z` → `20261122T010203Z`."""
    return utc_str.replace("-", "").replace(":", "")


def file_name(env):
    return f"{stamp_of(env['started_utc'])}_{env['invocation_id']}.json"


# --- Verrou -------------------------------------------------------------------------------

def make_lock(*, agent_id, runner_id, mission_id, invocation_id, pid, now, lease_s):
    lease_s = min(lease_s, MAX_LEASE_S)
    return {"contract": LOCK_CONTRACT, "agent_id": agent_id, "runner_id": runner_id,
            "mission_id": mission_id, "invocation_id": invocation_id, "pid": pid,
            "started_utc": utc_iso(now), "lease_until_utc": utc_iso(now + lease_s)}


def validate_lock(data, *, agent_id, runner_id, mission_id, now_ts):
    """Contenu du verrou : schéma, identités, chronologie, bail borné. (ok, motif)."""
    if not isinstance(data, dict):
        return False, "verrou non objet"
    if set(data) != LOCK_KEYS:
        return False, "schéma de verrou incomplet ou inattendu"
    if data["contract"] != LOCK_CONTRACT:
        return False, "contrat de verrou inconnu"
    if data["agent_id"] != agent_id:
        return False, "verrou d'un autre agent"
    if data["runner_id"] != runner_id:
        return False, "verrou d'un autre runner"
    if data["mission_id"] != mission_id:
        return False, "verrou d'une autre mission"
    if not (isinstance(data["invocation_id"], str) and HEX32.match(data["invocation_id"])):
        return False, "identifiant d'invocation absent ou malformé"
    if not (isinstance(data["pid"], int) and not isinstance(data["pid"], bool) and data["pid"] > 0):
        return False, "pid absent ou malformé"
    started, lease = parse_utc(data["started_utc"]), parse_utc(data["lease_until_utc"])
    if started is None or lease is None:
        return False, "dates de verrou invalides"
    if started > now_ts + CLOCK_SKEW_S:
        return False, "début de verrou dans le futur"
    if lease <= started:
        return False, "bail antérieur au début"
    if lease - started > MAX_LEASE_S:
        return False, f"bail excessif (> {MAX_LEASE_S} s)"
    if lease <= now_ts:
        return False, "bail expiré"
    return True, "ok"


# --- Enveloppe ----------------------------------------------------------------------------

def make_envelope(*, invocation_id, agent_id, runner_id, mission, code_sha, analysed_sha,
                  started_utc, ended_utc, state, exit_code, interruption_reason, report,
                  limits, verification):
    if state not in EXECUTION_STATES:
        raise ValueError("state")
    rep = report or {}
    content = rep.get("content") or {}
    return {
        "contract": INVOCATION_CONTRACT, "contract_version": CONTRACT_VERSION,
        "invocation_id": invocation_id, "agent_id": agent_id, "runner_id": runner_id,
        "mission_id": mission["mission_id"], "profile_blob_sha1": mission["profile"]["blob_sha1"],
        "code_sha": code_sha, "analysed_sha": analysed_sha,
        "started_utc": started_utc, "ended_utc": ended_utc, "state": state,
        "exit_code": exit_code, "interruption_reason": interruption_reason,
        "result_status": content.get("status") if report else None,
        "report_sha256": rep.get("report_sha256"), "content_sha256": rep.get("content_sha256"),
        "limits": limits, "verification": verification, "report": report,
    }


def _check_verification(env):
    v = env["verification"]
    if not isinstance(v, dict) or set(v) != VERIFICATION_KEYS:
        return "vérification absente ou incomplète"
    if v["checkout_head"] != env["code_sha"]:
        return "HEAD vérifié différent du SHA de code déclaré"
    if v["profile_blob_sha1"] != env["profile_blob_sha1"]:
        return "profil vérifié différent du profil déclaré"
    if not isinstance(v["profile_source_path"], str) or not v["profile_source_path"]:
        return "chemin de profil absent"
    for key in ("executed_modules", "scope_blobs"):
        m = v[key]
        if not isinstance(m, dict) or not m:
            return f"{key} vide"
        if not all(isinstance(k, str) and isinstance(b, str) and HEX40.match(b) for k, b in m.items()):
            return f"{key} malformé"
    return None


def validate_envelope(env, *, agent_id, runner_id, mission_id, now_ts, expected_profile_blob=None):
    """(classe, motif). classe ∈ VALID, INVALID, INCOMPLETE, FUTURE.

    VALID : schéma, identités, cohérence enveloppe/rapport/sources, chronologie, empreintes.
    Il ne dit rien d'une exécution en cours.
    """
    if not isinstance(env, dict):
        return "INVALID", "enveloppe non objet"
    if env.get("contract") == RUNTIME_INVOCATION_CONTRACT:
        return validate_runtime_envelope(env, agent_id=agent_id, runner_id=runner_id, mission_id=mission_id,
                                         now_ts=now_ts, expected_profile_blob=expected_profile_blob)
    missing, extra = ENVELOPE_KEYS - set(env), set(env) - ENVELOPE_KEYS
    if missing:
        return "INCOMPLETE", f"champs manquants: {','.join(sorted(missing))}"
    if extra:
        return "INVALID", f"champs inattendus: {','.join(sorted(extra))}"
    if env["contract"] != INVOCATION_CONTRACT or env["contract_version"] != CONTRACT_VERSION:
        return "INVALID", "version de contrat inconnue"
    if not (isinstance(env["invocation_id"], str) and HEX32.match(env["invocation_id"])):
        return "INVALID", "invocation_id"
    if env["agent_id"] != agent_id:
        return "INVALID", "agent_id différent de l'agent attendu"
    if env["runner_id"] != runner_id:
        return "INVALID", "runner_id différent du runner attendu"
    if env["mission_id"] != mission_id:
        return "INVALID", "mission_id différent de la mission attendue"
    state = env["state"]
    if state not in EXECUTION_STATES:
        return "INVALID", "état d'exécution inconnu"
    abandoned = state == "ABANDONED"
    for k in ("profile_blob_sha1", "code_sha", "analysed_sha"):
        if abandoned and env[k] is None:
            continue  # une invocation abandonnée n'a pas prouvé ses SHA : null, jamais inventé
        if not (isinstance(env[k], str) and HEX40.match(env[k])):
            return "INVALID", f"{k} absent ou malformé"
    if expected_profile_blob is not None and not abandoned and env["profile_blob_sha1"] != expected_profile_blob:
        return "INVALID", "profil différent du profil qualifié"
    started, ended = parse_utc(env["started_utc"]), parse_utc(env["ended_utc"])
    if started is None or ended is None:
        return "INVALID", "dates UTC invalides"
    if ended < started:
        return "INVALID", "fin antérieure au début"
    if started > now_ts + CLOCK_SKEW_S or ended > now_ts + CLOCK_SKEW_S:
        return "FUTURE", "date future"

    # Cohérence état d'exécution / code de sortie / motif.
    code = env["exit_code"]
    if state == "COMPLETED" and code != 0:
        return "INVALID", "COMPLETED exige un code de sortie 0"
    if state == "FAILED" and not (isinstance(code, int) and not isinstance(code, bool) and code >= 1):
        return "INVALID", "FAILED exige un code de sortie ≥ 1"
    if state in ("TIMEOUT", "INTERRUPTED", "ABANDONED") and code is not None:
        return "INVALID", "code de sortie inattendu pour une interruption"
    if state != "COMPLETED" and not env["interruption_reason"]:
        return "INVALID", "motif d'échec ou d'interruption absent"

    if abandoned:
        if any(env[k] is not None for k in ("report", "result_status", "report_sha256",
                                            "content_sha256", "verification", "limits")):
            return "INVALID", "une invocation abandonnée ne porte ni rapport ni vérification"
        return "VALID", "ok"

    lim = env["limits"]
    if not (isinstance(lim, dict) and isinstance(lim.get("max_files"), int)
            and isinstance(lim.get("max_run_s"), (int, float))):
        return "INVALID", "limites absentes"
    kind = c.QUESTION_KIND_BY_AGENT.get(env["agent_id"])
    if kind is None or lim["max_files"] > MAX_FILES_BY_KIND[kind] or lim["max_run_s"] > MAX_RUN_S:
        return "INVALID", "limites déclarées au-delà des bornes"
    why = _check_verification(env)
    if why:
        return "INVALID", why

    rep = env["report"]
    if state != "COMPLETED":
        if rep is not None or env["result_status"] is not None:
            return "INVALID", "rapport présent sur une invocation non terminée"
        return "VALID", "ok"
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
    if env["content_sha256"] != rep["content_sha256"] or env["report_sha256"] != rep["report_sha256"]:
        return "INVALID", "empreintes d'enveloppe incohérentes"
    ct = rep["content"]
    # Comparaisons d'identité : un sceau correct ne les remplace pas.
    if ct.get("agent_id") != env["agent_id"]:
        return "INVALID", "rapport d'un autre agent"
    if ct.get("mission_id") != env["mission_id"]:
        return "INVALID", "rapport d'une autre mission"
    if ct.get("analyzed_ref") != {"kind": "GIT_COMMIT", "sha": env["analysed_sha"]}:
        return "INVALID", "SHA analysé du rapport différent de l'enveloppe"
    if report_profile_path(ct) != "profile:" + env["verification"]["profile_source_path"]:
        return "INVALID", "profil du rapport incohérent"
    if ct.get("status") not in RESULT_STATUSES:
        return "INVALID", "statut de résultat inconnu"
    if env["result_status"] != ct["status"]:
        return "INVALID", "résultat déclaré incohérent avec le rapport"
    sources = {s.get("path") for s in report_sources(ct)
               if isinstance(s, dict) and not str(s.get("path", "")).startswith("profile:")}
    if not sources <= set(env["verification"]["scope_blobs"]):
        return "INVALID", "sources du rapport hors du périmètre vérifié"
    return "VALID", "ok"


def validate_runtime_envelope(env, *, agent_id, runner_id, mission_id, now_ts, expected_profile_blob=None):
    """Enveloppe d'un observateur runtime. Mêmes règles d'identité, d'état et de sceau ; pas de SHA analysé."""
    missing, extra = RUNTIME_ENVELOPE_KEYS - set(env), set(env) - RUNTIME_ENVELOPE_KEYS
    if missing:
        return "INCOMPLETE", f"champs manquants: {','.join(sorted(missing))}"
    if extra:
        return "INVALID", f"champs inattendus: {','.join(sorted(extra))}"
    if env["contract_version"] != CONTRACT_VERSION:
        return "INVALID", "version de contrat inconnue"
    if not (isinstance(env["invocation_id"], str) and HEX32.match(env["invocation_id"])):
        return "INVALID", "invocation_id"
    if env["agent_id"] != agent_id:
        return "INVALID", "agent_id différent de l'agent attendu"
    if env["runner_id"] != runner_id:
        return "INVALID", "runner_id différent du runner attendu"
    if env["mission_id"] != mission_id:
        return "INVALID", "mission_id différent de la mission attendue"
    state = env["state"]
    if state not in EXECUTION_STATES or state == "ABANDONED":
        return "INVALID", "état d'exécution inconnu"
    for k in ("profile_blob_sha1", "code_sha"):
        if not (isinstance(env[k], str) and HEX40.match(env[k])):
            return "INVALID", f"{k} absent ou malformé"
    if expected_profile_blob is not None and env["profile_blob_sha1"] != expected_profile_blob:
        return "INVALID", "profil différent du profil qualifié"
    started, ended = parse_utc(env["started_utc"]), parse_utc(env["ended_utc"])
    if started is None or ended is None:
        return "INVALID", "dates UTC invalides"
    if ended < started:
        return "INVALID", "fin antérieure au début"
    if started > now_ts + CLOCK_SKEW_S or ended > now_ts + CLOCK_SKEW_S:
        return "FUTURE", "date future"
    code = env["exit_code"]
    if state == "COMPLETED" and code != 0:
        return "INVALID", "COMPLETED exige un code de sortie 0"
    if state == "FAILED" and not (isinstance(code, int) and not isinstance(code, bool) and code >= 1):
        return "INVALID", "FAILED exige un code de sortie ≥ 1"
    if state in ("TIMEOUT", "INTERRUPTED") and code is not None:
        return "INVALID", "code de sortie inattendu pour une interruption"
    if state != "COMPLETED" and not env["interruption_reason"]:
        return "INVALID", "motif d'échec ou d'interruption absent"
    lim = env["limits"]
    if not (isinstance(lim, dict) and isinstance(lim.get("max_run_s"), (int, float)) and lim["max_run_s"] <= MAX_RUN_S):
        return "INVALID", "limites absentes ou au-delà des bornes"
    v = env["verification"]
    if not isinstance(v, dict) or set(v) != RUNTIME_VERIFICATION_KEYS:
        return "INVALID", "vérification absente ou incomplète"
    if v["checkout_head"] != env["code_sha"] or v["profile_blob_sha1"] != env["profile_blob_sha1"]:
        return "INVALID", "vérification incohérente avec l'enveloppe"
    m = v["executed_modules"]
    if not (isinstance(m, dict) and m and all(isinstance(b, str) and HEX40.match(b) for b in m.values())):
        return "INVALID", "executed_modules vide ou malformé"
    rep = env["report"]
    if state != "COMPLETED":
        if rep is not None or env["result_status"] is not None:
            return "INVALID", "rapport présent sur une invocation non terminée"
        return "VALID", "ok"
    if not isinstance(rep, dict) or set(rep) != {"content", "content_sha256", "run", "report_sha256"}:
        return "INVALID", "enveloppe de rapport inattendue"
    if rep["content_sha256"] != c.sha256_json(rep["content"]):
        return "INVALID", "empreinte du contenu altérée"
    if rep["report_sha256"] != c.sha256_json({"content": rep["content"], "content_sha256": rep["content_sha256"],
                                              "run": rep["run"]}):
        return "INVALID", "empreinte du rapport altérée"
    if env["content_sha256"] != rep["content_sha256"] or env["report_sha256"] != rep["report_sha256"]:
        return "INVALID", "empreintes d'enveloppe incohérentes"
    ct = rep["content"]
    if ct.get("contract") != RUNTIME_REPORT_CONTRACT:
        return "INVALID", "contrat de rapport inconnu"
    if ct.get("agent_id") != env["agent_id"] or ct.get("mission_id") != env["mission_id"]:
        return "INVALID", "rapport d'un autre agent ou d'une autre mission"
    if (ct.get("profile") or {}).get("path") != "profile:" + v["profile_source_path"]:
        return "INVALID", "profil du rapport incohérent"
    if ct.get("status") not in RESULT_STATUSES or env["result_status"] != ct["status"]:
        return "INVALID", "résultat déclaré incohérent avec le rapport"
    return "VALID", "ok"


def report_sources(ct):
    """Inventaire des sources lues : `sources` (cartographes, architecte) ou `sources_consulted` (DPA)."""
    for key in ("sources", "sources_consulted"):
        if isinstance(ct.get(key), list):
            return ct[key]
    return []


def report_profile_path(ct):
    """`profile:<chemin>` du profil lu. Le DPA publie la référence de mission et inventorie la lecture."""
    prof = ct.get("profile")
    if isinstance(prof, dict) and isinstance(prof.get("path"), str):
        return prof["path"]
    if isinstance(prof, dict) and isinstance(prof.get("source_path"), str):
        want = "profile:" + prof["source_path"]
        if any(isinstance(s, dict) and s.get("path") == want for s in report_sources(ct)):
            return want
    return None


def hashlib_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_load_bounded(raw: bytes):
    if len(raw) > MAX_PROOF_BYTES:
        raise ValueError("TOO_LARGE")
    return json.loads(raw.decode("utf-8"))
