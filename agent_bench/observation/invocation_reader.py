"""Lecteur strictement passif des preuves d'invocation (contrat v1).

Passif : aucun fichier créé, modifié ou verrouillé. L'observation de vie lit `/proc/locks`
(verrou noyau tenu sur l'inode du fichier de verrou) ; elle ne prend jamais de verrou, pour ne
pas perturber l'exécuteur.

Sortie, partagée avec l'interface (`display`) :
- connexion et preuve : AVAILABLE, ABSENT, ACCESS_DENIED, UNREADABLE, INCOMPLETE, INVALID ;
- activité : EN_COURS (verrou noyau tenu + contenu de verrou valide + bail non expiré),
  TERMINE (dernière enveloppe valide), INDETERMINE (tout le reste) ;
- dernier résultat scientifique, séparé ;
- `display` : GREEN seulement si identité, preuve, observation de vie et fraîcheur sont valides ;
  RED pour une fin attestée (« fin normale » ou « échec ») ; GRAY sinon ; `valid_until_utc` borne
  la durée pendant laquelle l'interface peut afficher cette couleur sans nouvelle réponse.

Relire un ancien rapport ne rajeunit jamais l'activité : `last_activity_utc` est la fin consignée.
"""
from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path

from agent_bench.observation import invocation as inv

PROC_LOCKS = Path("/proc/locks")


_TRAVERSE = getattr(os, "O_PATH", os.O_RDONLY)


def _open_dir(root: Path, *parts):
    """Ouvre root/parts… en refusant tout lien symbolique, à chaque niveau (racine comprise).

    Les niveaux intermédiaires sont ouverts en `O_PATH` : le compte lecteur n'a besoin que du droit
    de traverser (`x`) le dossier des rapports, pas de le lister. Seul le dernier niveau est ouvert
    en lecture (énumération ou lecture des fichiers).
    """
    last = len(parts)
    fd = os.open(root, (os.O_RDONLY if last == 0 else _TRAVERSE) | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for i, part in enumerate(parts, 1):
            mode = os.O_RDONLY if i == last else _TRAVERSE
            nfd = os.open(part, mode | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nfd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_at(dfd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("NOT_REGULAR")
        if st.st_size > inv.MAX_PROOF_BYTES:
            raise ValueError("TOO_LARGE")
        data = os.read(fd, inv.MAX_PROOF_BYTES + 1)
        if len(data) > inv.MAX_PROOF_BYTES:
            raise ValueError("TOO_LARGE")
        return data, st
    finally:
        os.close(fd)


def _err_kind(exc):
    if isinstance(exc, PermissionError):
        return "ACCESS_DENIED", "accès refusé"
    if isinstance(exc, FileNotFoundError):
        return "ABSENT", "absent"
    if isinstance(exc, OSError) and exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return "UNREADABLE", "lien symbolique ou chemin non conforme refusé"
    return "UNREADABLE", type(exc).__name__


def flock_holders(st, proc_locks: Path = PROC_LOCKS):
    """PIDs détenant un FLOCK WRITE sur l'inode `st`, d'après /proc/locks. None si illisible."""
    try:
        text = proc_locks.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    want = (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
    pids = set()
    for line in text.splitlines():
        parts = line.split()
        if "->" in parts:      # verrou en attente, pas tenu
            continue
        if len(parts) < 6 or parts[1] != "FLOCK" or parts[3] != "WRITE":
            continue
        try:
            maj, mnr, ino = parts[5].split(":")
            key = (int(maj, 16), int(mnr, 16), int(ino))
            pid = int(parts[4])
        except ValueError:
            continue
        if key == want:
            pids.add(pid)
    return pids


def read_lock(reports: Path, *, agent_id, runner_id, mission_id, now_ts, proc_locks: Path = PROC_LOCKS):
    """Activité en cours attestée ou non. Ne lève pas."""
    try:
        dfd = _open_dir(reports, "locks")
    except OSError as exc:
        kind, why = _err_kind(exc)
        return {"activity": "INDETERMINE", "life_observed": False,
                "reason": "aucun verrou" if kind == "ABSENT" else f"verrous illisibles ({why})"}
    try:
        try:
            raw, st = _read_at(dfd, f"{runner_id}.lock")
        except (OSError, ValueError) as exc:
            if isinstance(exc, FileNotFoundError):
                return {"activity": "INDETERMINE", "life_observed": False, "reason": "aucun verrou"}
            return {"activity": "INDETERMINE", "life_observed": False, "reason": f"verrou illisible ({type(exc).__name__})"}
    finally:
        os.close(dfd)
    holders = flock_holders(st, proc_locks)
    if holders is None:
        return {"activity": "INDETERMINE", "life_observed": False,
                "reason": "vie du processus non attestable (/proc/locks illisible)"}
    if not holders:
        return {"activity": "INDETERMINE", "life_observed": False,
                "reason": "aucun processus ne détient le verrou"}
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else None
    except ValueError:
        data = None
    ok, why = inv.validate_lock(data, agent_id=agent_id, runner_id=runner_id, mission_id=mission_id,
                                now_ts=now_ts)
    if not ok:
        return {"activity": "INDETERMINE", "life_observed": True, "reason": f"verrou tenu mais invalide : {why}"}
    if data["pid"] not in holders:
        return {"activity": "INDETERMINE", "life_observed": True,
                "reason": "le processus détenteur n'est pas celui déclaré dans le verrou"}
    return {"activity": "EN_COURS", "life_observed": True, "reason": "verrou noyau tenu, bail valide",
            "invocation_id": data["invocation_id"], "started_utc": data["started_utc"],
            "lease_until_utc": data["lease_until_utc"]}


def _list_bounded(dfd):
    """Énumère au plus MAX_DIR_ENTRIES entrées ; au-delà, refus explicite (pas de troncature muette)."""
    names = []
    with os.scandir(dfd) as it:
        for e in it:
            if len(names) >= inv.MAX_DIR_ENTRIES:
                raise OverflowError
            names.append(e.name)
    return names


def _display(out, now_ts):
    """Contrat d'affichage partagé avec l'interface."""
    ttl = inv.utc_iso(now_ts + inv.DISPLAY_TTL_S)
    if out["activity"] == "EN_COURS" and out["life_observed"] and out["connection"] in ("AVAILABLE", "ABSENT"):
        lease = inv.parse_utc(out["lease_until_utc"]) or now_ts
        return {"light": "GREEN", "label": "Actif", "reason": "exécution en cours attestée",
                "valid_until_utc": inv.utc_iso(min(lease, now_ts + inv.DISPLAY_TTL_S))}
    if out["activity"] == "EN_COURS":
        return {"light": "GRAY", "label": "Non attesté",
                "reason": f"exécution signalée mais preuve {out['connection']}", "valid_until_utc": None}
    if out["activity"] == "TERMINE":
        failed = out["last_state"] in inv.FAILED_STATES
        label = "Inactif · échec" if failed else "Inactif · fin normale"
        if out["mission_overdue"]:
            label += " · aucune mission depuis plus de 36 h"
        return {"light": "RED", "label": label, "reason": f"dernière invocation {out['last_state']}",
                "valid_until_utc": ttl}
    return {"light": "GRAY", "label": "Non attesté",
            "reason": out["activity_reason"] or out["connection_reason"] or "état non attestable",
            "valid_until_utc": None}


def read_status(reports: Path, *, mission_id: str, agent_id: str, runner_id: str, now_ts: float,
                expected_profile_blob=None, proc_locks: Path = PROC_LOCKS):
    """Résumé pour Système. Ne lève pas : toute erreur devient un état explicite."""
    out = {"contract": inv.INVOCATION_CONTRACT, "agent_id": agent_id, "runner_id": runner_id,
           "mission_id": mission_id, "server_observed_at_utc": inv.utc_iso(now_ts),
           "connection": None, "connection_reason": None,
           "activity": "INDETERMINE", "activity_reason": None, "life_observed": False,
           "lease_until_utc": None, "last_activity_utc": None, "last_mission_age_s": None,
           "mission_overdue": False, "last_result": None, "last_state": None, "invocation_id": None,
           "display": None}

    lock = read_lock(reports, agent_id=agent_id, runner_id=runner_id, mission_id=mission_id,
                     now_ts=now_ts, proc_locks=proc_locks)
    out["activity_reason"] = lock["reason"]
    out["life_observed"] = lock["life_observed"]
    if lock["activity"] == "EN_COURS":
        out["activity"] = "EN_COURS"
        out["lease_until_utc"] = lock["lease_until_utc"]
        out["last_activity_utc"] = lock["started_utc"]
        out["invocation_id"] = lock["invocation_id"]

    def done(conn, why):
        out["connection"], out["connection_reason"] = conn, why
        out["display"] = _display(out, now_ts)
        return out

    try:
        dfd = _open_dir(reports, "runs", mission_id)
    except OSError as exc:
        kind, why = _err_kind(exc)
        return done(kind, "aucune invocation consignée" if kind == "ABSENT" else f"dossier de preuves : {why}")
    try:
        try:
            names = _list_bounded(dfd)
        except OverflowError:
            return done("UNREADABLE", f"plus de {inv.MAX_DIR_ENTRIES} entrées : énumération refusée")
        except OSError as exc:
            return done(*_err_kind(exc))
        candidates = sorted(n for n in names if inv.NAME_RE.match(n))
        if not candidates:
            return done("ABSENT", "aucune invocation consignée")
        latest = candidates[-1]
        try:
            raw, _ = _read_at(dfd, latest)
            env = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as exc:
            kind, why = _err_kind(exc) if isinstance(exc, OSError) else ("INVALID", f"fichier illisible ({exc})")
            return done(kind if kind != "ABSENT" else "UNREADABLE", why)
    finally:
        os.close(dfd)

    verdict, reason = inv.validate_envelope(env, agent_id=agent_id, runner_id=runner_id,
                                            mission_id=mission_id, now_ts=now_ts,
                                            expected_profile_blob=expected_profile_blob)
    if verdict == "VALID" and inv.file_name(env) != latest:
        verdict, reason = "INVALID", "nom de fichier incohérent avec l'enveloppe"
    if verdict != "VALID":
        out["last_state"] = None
        return done("INCOMPLETE" if verdict == "INCOMPLETE" else "INVALID", f"{verdict}: {reason}")

    out["last_state"] = env["state"]
    out["last_result"] = env["result_status"]
    ended = inv.parse_utc(env["ended_utc"])
    out["last_mission_age_s"] = max(0, int(now_ts - ended))
    out["mission_overdue"] = now_ts - ended > inv.ABSENCE_WINDOW_S
    if out["activity"] != "EN_COURS":
        out["activity"] = "TERMINE"
        out["activity_reason"] = f"dernière invocation {env['state']} ({lock['reason']})"
        out["last_activity_utc"] = env["ended_utc"]
        out["invocation_id"] = env["invocation_id"]
    return done("AVAILABLE", "dernière preuve valide")


HISTORY_MAX_ITEMS = 20


def _report_summary(env):
    """Résumé d'affichage d'un rapport : compteurs et libellés, jamais de contenu de fichier.

    Forme commune à tous les agents ; `chain` n'existe que pour une chaîne de provenance
    (Data Provenance Auditor), avec le nombre de maillons par niveau de preuve.
    """
    ct = ((env.get("report") or {}).get("content")) or {}
    out = {
        "seen": {"sources": len(ct.get("sources") or ct.get("sources_consulted") or []),
                 "imports": len(ct.get("imports") or []), "calls": len(ct.get("calls") or [])},
        "found": sorted({f.get("code") for f in ct.get("findings") or [] if f.get("code")}),
        "not_concluded": [{"path": u.get("path"), "line": u.get("line"),
                           "reason": u.get("reason") or u.get("code")}
                          for u in (ct.get("unknowns") or [])],
        "write_templates": len(ct.get("write_templates") or []),
        "limits": len(ct.get("limits") or []),
        "errors": [e.get("code") for e in ct.get("errors") or []],
    }
    chain = ct.get("chain")
    if isinstance(chain, list):
        levels: dict = {}
        for link in chain:
            lv = link.get("level") if isinstance(link, dict) else None
            levels[lv if isinstance(lv, str) else "UNKNOWN"] = levels.get(lv if isinstance(lv, str) else "UNKNOWN", 0) + 1
        hops = [{"hop": str(h.get("hop"))[:40], "level": str(h.get("level"))[:16]}
                for h in chain[:12] if isinstance(h, dict)]
        out["chain"] = {"links": len(chain), "levels": dict(sorted(levels.items())), "hops": hops,
                        "inferred": len(ct.get("inferred_links") or []),
                        "runtime_required": len(ct.get("runtime_measurements_required") or [])}
    return out


def read_history(reports: Path, *, mission_id: str, agent_id: str, runner_id: str, now_ts: float,
                 expected_profile_blob=None, max_items: int = HISTORY_MAX_ITEMS):
    """Historique des invocations publiées, plus récentes d'abord. Ne lève pas.

    Chaque entrée garde son verdict : une enveloppe invalide reste visible comme telle.
    """
    out = {"contract": inv.INVOCATION_CONTRACT, "agent_id": agent_id, "mission_id": mission_id,
           "server_observed_at_utc": inv.utc_iso(now_ts), "connection": None,
           "connection_reason": None, "total": None, "items": []}
    try:
        dfd = _open_dir(reports, "runs", mission_id)
    except OSError as exc:
        kind, why = _err_kind(exc)
        out["connection"], out["connection_reason"] = kind, why
        if kind == "ABSENT":
            out["connection_reason"], out["total"] = "aucune invocation consignée", 0
        return out
    try:
        try:
            names = _list_bounded(dfd)
        except OverflowError:
            out["connection"] = "UNREADABLE"
            out["connection_reason"] = f"plus de {inv.MAX_DIR_ENTRIES} entrées : énumération refusée"
            return out
        except OSError as exc:
            out["connection"], out["connection_reason"] = _err_kind(exc)
            return out
        candidates = sorted((n for n in names if inv.NAME_RE.match(n)), reverse=True)
        out["total"] = len(candidates)
        for name in candidates[:max_items]:
            item = {"verdict": None, "reason": None}
            try:
                raw, _ = _read_at(dfd, name)
                env = json.loads(raw.decode("utf-8"))
            except (OSError, ValueError) as exc:
                item.update(verdict="UNREADABLE", reason=_err_kind(exc)[1] if isinstance(exc, OSError)
                            else "fichier illisible")
                out["items"].append(item)
                continue
            verdict, reason = inv.validate_envelope(env, agent_id=agent_id, runner_id=runner_id,
                                                    mission_id=mission_id, now_ts=now_ts,
                                                    expected_profile_blob=expected_profile_blob)
            if verdict == "VALID" and inv.file_name(env) != name:
                verdict, reason = "INVALID", "nom de fichier incohérent avec l'enveloppe"
            item.update(verdict=verdict, reason=reason)
            if verdict == "VALID":
                item.update(invocation_id=env["invocation_id"], started_utc=env["started_utc"],
                            ended_utc=env["ended_utc"], state=env["state"],
                            result_status=env["result_status"], analysed_sha=env["analysed_sha"],
                            content_sha256=env["content_sha256"], summary=_report_summary(env))
            out["items"].append(item)
    finally:
        os.close(dfd)
    out["connection"], out["connection_reason"] = "AVAILABLE", "historique lu"
    return out
