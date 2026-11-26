"""Exécuteur ponctuel des agents d'observation (contrat d'invocation v1).

Une invocation par appel explicite. Aucun démon, aucun timer, aucune relance automatique.
Agents servis : ceux du registre ``agents.AGENTS`` (repository-cartographer par défaut, pour que
l'unité installée garde exactement son comportement ; les autres via ``--agent-id``).

Exclusion mutuelle : `flock(LOCK_EX | LOCK_NB)` sur `locks/<runner_id>.lock`.
- Le noyau libère le verrou à la mort du processus (arrêt brutal compris) : aucune reprise
  par renommage, aucune fenêtre où deux candidats déplacent le verrou l'un de l'autre.
- Le fichier de verrou n'est jamais supprimé : on ne peut pas retirer le verrou d'une autre
  invocation, puisque la libération est la fermeture du descripteur détenu.
- Le contenu du verrou (identités, bail) est écrit par le détenteur ; il sert au lecteur, il
  ne prouve rien seul. L'observation de vie est la présence du verrou noyau (`/proc/locks`).
- À l'acquisition, une invocation précédente restée sans enveloppe est consignée ABANDONED.

Vérifications avant verrouillage (refus explicite, rien n'est publié) :
- git disponible ; HEAD du checkout = SHA de code déclaré ; SHA analysé présent ;
- fichiers du périmètre identiques à leur blob au SHA analysé (pas seulement HEAD) ;
- profil identique au blob de la mission ;
- modules réellement exécutés identiques à leur blob au SHA de code.
Il n'existe aucun mode synthétique : les tests construisent de vrais dépôts git.

Publication : fichier caché `O_EXCL`, fsync, `os.link` vers le nom définitif (échoue si le nom
existe : aucun écrasement), fsync du dossier. Le lecteur ignore les fichiers cachés.
Atomicité ≠ durabilité : la visibilité est atomique (link) ; la durabilité après coupure
d'alimentation dépend du fsync du dossier, effectué après le link.
"""
from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

from agent_bench.observation import agents as ag
from agent_bench.observation import contract as c
from agent_bench.observation import invocation as inv
from agent_bench.observation import observability_cartographer as oc
from agent_bench.observation import provenance_auditor as pa
from agent_bench.observation import repo_architect as ra
from agent_bench.observation import repository_cartographer as rc

GIT = "git"
CODE_PACKAGE = "agent_bench/observation"
EXIT_PUBLISHED_OK = 0
EXIT_REFUSED = 2
EXIT_PUBLISHED_NOT_COMPLETED = 3
EXIT_PUBLICATION_FAILED = 4


class Refused(Exception):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class _Timeout(BaseException):
    pass


class _Interrupted(BaseException):
    pass


# --- Vérification du checkout ---------------------------------------------------------------

def _git(checkout: Path, *args, input_bytes=None):
    try:
        out = subprocess.run([GIT, "-C", str(checkout), *args], capture_output=True, timeout=30,
                             input=input_bytes, check=False,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C",
                                  "GIT_CONFIG_NOSYSTEM": "1", "HOME": "/nonexistent",
                                  "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                                      "GIT_CONFIG_VALUE_0": str(checkout)})
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("GIT_UNAVAILABLE", type(exc).__name__) from exc
    return out


def _blob_at(checkout, sha, rel):
    out = _git(checkout, "rev-parse", "--verify", "--quiet", f"{sha}:{rel}")
    return out.stdout.decode().strip() if out.returncode == 0 else None


def _hash_file(checkout, path: Path):
    out = _git(checkout, "hash-object", "--no-filters", "--", str(path))
    if out.returncode != 0:
        raise Refused("GIT_UNAVAILABLE", "hash-object")
    return out.stdout.decode().strip()


def executed_module_files():
    """Fichiers des modules du paquet réellement chargés par ce processus."""
    files = {}
    for name, mod in sorted(sys.modules.items()):
        if not (name == "agent_bench.observation" or name.startswith("agent_bench.observation.")):
            continue
        f = getattr(mod, "__file__", None)
        if f:
            p = Path(f).resolve()
            files[f"{CODE_PACKAGE}/{p.name}"] = p
    return files


def verify_checkout(checkout: Path, *, code_sha, analysed_sha, mission, analysed_tree: Path | None = None,
                    allow_absent=frozenset()):
    """Retourne le bloc `verification` ou lève Refused. Lecture seule.

    `analysed_tree` : arbre distinct, extrait au SHA analysé (suivi de main). Sans lui, la zone
    est lue dans le checkout de code, comme pour une mission figée.
    """
    if not (checkout / ".git").exists():
        raise Refused("HEAD_UNVERIFIABLE", "checkout sans dépôt git")
    head = _git(checkout, "rev-parse", "--verify", "HEAD^{commit}")
    if head.returncode != 0:
        raise Refused("HEAD_UNVERIFIABLE", "HEAD illisible")
    head_sha = head.stdout.decode().strip()
    if head_sha != code_sha:
        raise Refused("CHECKOUT_SHA_MISMATCH", f"HEAD {head_sha} ≠ code {code_sha}")
    zone = checkout
    if analysed_tree is not None:
        zone = Path(analysed_tree)
        if not (zone / ".git").exists():
            raise Refused("ANALYSED_TREE_UNVERIFIABLE", "arbre analysé sans dépôt git")
        th = _git(zone, "rev-parse", "--verify", "HEAD^{commit}")
        if th.returncode != 0 or th.stdout.decode().strip() != analysed_sha:
            raise Refused("ANALYSED_TREE_SHA_MISMATCH", analysed_sha)
    if _git(zone, "cat-file", "-e", f"{analysed_sha}^{{commit}}").returncode != 0:
        raise Refused("ANALYSED_SHA_UNAVAILABLE", analysed_sha)
    scope = {}
    for rel in mission["scope"]["read_paths"]:
        if rel.endswith("/"):
            raise Refused("SCOPE_DIRECTORY_UNSUPPORTED", rel)
        expected = _blob_at(zone, analysed_sha, rel)
        path = zone / rel
        if expected is None and rel in allow_absent and not os.path.lexists(path):
            continue  # fichier supprimé par le diff analysé : absent au SHA analysé et sur disque
        if expected is None:
            raise Refused("SCOPE_ABSENT_AT_ANALYSED_SHA", rel)
        if path.is_symlink() or not path.is_file():
            raise Refused("CHECKOUT_MODIFIED", f"{rel} absent ou lien")
        if _hash_file(zone, path) != expected:
            raise Refused("CHECKOUT_MODIFIED", f"{rel} diffère du SHA analysé")
        scope[rel] = expected

    prof = mission["profile"]
    ppath = checkout / prof["source_path"]
    if ppath.is_symlink() or not ppath.is_file() or _hash_file(checkout, ppath) != prof["blob_sha1"]:
        raise Refused("PROFILE_MISMATCH", prof["source_path"])

    if not scope:
        raise Refused("SCOPE_EMPTY_AT_ANALYSED_SHA", "aucun fichier du périmètre présent")
    modules = {}
    for rel, path in executed_module_files().items():
        expected = _blob_at(checkout, code_sha, rel)
        actual = _hash_file(checkout, path)
        if expected is None or expected != actual:
            raise Refused("CODE_MISMATCH", f"{rel} exécuté ≠ {code_sha}")
        modules[rel] = actual
    if not modules:
        raise Refused("CODE_MISMATCH", "aucun module vérifiable")
    return {"checkout_head": head_sha, "executed_modules": modules, "scope_blobs": scope,
            "profile_source_path": prof["source_path"], "profile_blob_sha1": prof["blob_sha1"]}


def git_diff(zone: Path, base_sha, analysed_sha, paths):
    """Diff unifié base → analysé, limité aux chemins. Même commande pour préparer et vérifier."""
    if _git(zone, "cat-file", "-e", f"{base_sha}^{{commit}}").returncode != 0:
        raise Refused("BASE_SHA_UNAVAILABLE", base_sha)
    out = _git(zone, "diff", "--no-ext-diff", "--no-color", "--no-renames", "--unified=3",
               base_sha, analysed_sha, "--", *paths)
    if out.returncode != 0:
        raise Refused("GIT_UNAVAILABLE", "diff")
    return out.stdout


def changed_paths(zone: Path, base_sha, analysed_sha):
    out = _git(zone, "diff", "--no-ext-diff", "--no-renames", "--name-only", base_sha, analysed_sha)
    if out.returncode != 0:
        raise Refused("GIT_UNAVAILABLE", "diff --name-only")
    return sorted({ln for ln in out.stdout.decode().splitlines() if ln})


def _analyse(mission, zone: Path, checkout: Path, diff, clock):
    kind = mission["question"]["kind"]

    def ns():  # horloge en nanosecondes des analyseurs
        return int(clock() * 1e9)

    if kind == "REPOSITORY_MAP":
        return rc.audit_zone(mission, zone, checkout, clock=ns)
    if kind == "DATASET_PROVENANCE_CHAIN":
        return pa.audit(mission, zone, checkout, clock=ns)
    if kind == "METRIC_SURFACE_MAP":
        return oc.audit_surface(mission, zone, checkout, clock=ns)
    if kind == "CHANGE_IMPACT":
        return ra.audit_change(mission, zone, checkout, diff, clock=ns)
    raise Refused("AGENT_NOT_QUALIFIED", kind)


# --- Verrou ---------------------------------------------------------------------------------

def _open_dir(root: Path, *parts, create=False):
    """Ouvre root/parts… sans suivre aucun lien symbolique (à chaque niveau)."""
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, 0o750, dir_fd=fd)
                except FileExistsError:
                    pass
            nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nfd
        return fd
    except BaseException:
        os.close(fd)
        raise


class RunnerLock:
    """flock exclusif non bloquant. Libéré à la fermeture ou à la mort du processus."""

    def __init__(self, reports: Path, runner_id: str):
        self.reports, self.runner_id, self.fd = reports, runner_id, None

    def acquire(self):
        dfd = _open_dir(self.reports, "locks", create=True)
        try:
            fd = os.open(f"{self.runner_id}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o640, dir_fd=dfd)
        finally:
            os.close(dfd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise Refused("ALREADY_RUNNING", self.runner_id) from exc
            raise
        self.fd = fd
        return self

    def previous(self):
        try:
            raw = os.pread(self.fd, inv.MAX_PROOF_BYTES, 0)
            return json.loads(raw.decode("utf-8")) if raw.strip() else None
        except (ValueError, OSError):
            return None

    def write(self, body: dict):
        data = json.dumps(body, sort_keys=True).encode()
        os.ftruncate(self.fd, 0)
        os.pwrite(self.fd, data, 0)
        os.fsync(self.fd)

    def release(self):
        if self.fd is not None:
            os.close(self.fd)  # libère le flock ; le fichier n'est jamais supprimé
            self.fd = None


# --- Publication ----------------------------------------------------------------------------

def publish(reports: Path, envelope: dict):
    """Publication atomique sans écrasement. Retourne le nom publié. Lève Refused."""
    name = inv.file_name(envelope)
    if not inv.NAME_RE.match(name):
        raise Refused("NAME_INVALID", name)
    dfd = _open_dir(reports, "runs", envelope["mission_id"], create=True)
    tmp = f".{name}.partial"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640,
                     dir_fd=dfd)
        try:
            os.write(fd, json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd, follow_symlinks=False)
        except FileExistsError as exc:
            raise Refused("NAME_EXISTS", name) from exc
        os.fsync(dfd)  # durabilité de l'entrée de dossier
        return name
    finally:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except FileNotFoundError:
            pass
        os.fsync(dfd)
        os.close(dfd)


def _cleanup_partials(reports: Path, mission_id: str):
    """Sous verrou : retire les fichiers `.partial` laissés par un arrêt brutal."""
    try:
        dfd = _open_dir(reports, "runs", mission_id)
    except FileNotFoundError:
        return 0
    removed = 0
    try:
        with os.scandir(dfd) as it:
            for i, e in enumerate(it):
                if i >= inv.MAX_DIR_ENTRIES:
                    raise Refused("REPORTS_DIR_OVERFLOW", f"plus de {inv.MAX_DIR_ENTRIES} entrées")
                if e.name.startswith(".") and e.name.endswith(".partial"):
                    os.unlink(e.name, dir_fd=dfd)
                    removed += 1
    finally:
        os.close(dfd)
    return removed


def _published_ids(reports: Path, mission_id: str):
    try:
        dfd = _open_dir(reports, "runs", mission_id)
    except FileNotFoundError:
        return set()
    try:
        out = set()
        with os.scandir(dfd) as it:
            for i, e in enumerate(it):
                if i >= inv.MAX_DIR_ENTRIES:
                    raise Refused("REPORTS_DIR_OVERFLOW", f"plus de {inv.MAX_DIR_ENTRIES} entrées")
                m = inv.NAME_RE.match(e.name)
                if m:
                    out.add(m.group(2))
        return out
    finally:
        os.close(dfd)


def _abandoned_envelope(prev, *, agent_id, runner_id, now):
    env = {k: None for k in inv.ENVELOPE_KEYS}
    env.update({"contract": inv.INVOCATION_CONTRACT, "contract_version": inv.CONTRACT_VERSION,
                "invocation_id": prev["invocation_id"], "agent_id": agent_id, "runner_id": runner_id,
                "mission_id": prev["mission_id"], "started_utc": prev["started_utc"],
                "ended_utc": inv.utc_iso(max(now, inv.parse_utc(prev["started_utc"]) or now)),
                "state": "ABANDONED",
                "interruption_reason": "verrou libéré sans enveloppe : arrêt brutal de l'invocation"})
    return env


# --- Invocation -----------------------------------------------------------------------------

def run_once(*, mission, checkout: Path, reports: Path, runner_id, agent_id="repository-cartographer",
             code_sha, analysed_sha, max_run_s=None, clock=time.time, lease_s=inv.MAX_LEASE_S,
             analysed_tree: Path | None = None):
    """Exécute une invocation et retourne (enveloppe, nom publié).

    Refus avant verrouillage : Refused, rien n'est publié.
    Après verrouillage : une enveloppe est toujours publiée (COMPLETED, FAILED, TIMEOUT ou
    INTERRUPTED), sauf échec de publication, signalé par Refused("PUBLICATION_FAILED").
    """
    if not (isinstance(code_sha, str) and inv.HEX40.match(code_sha)):
        raise Refused("CODE_SHA_INVALID")
    if not (isinstance(analysed_sha, str) and inv.HEX40.match(analysed_sha)):
        raise Refused("ANALYSED_SHA_INVALID")
    if not inv.ID_RE.match(runner_id):
        raise Refused("RUNNER_ID_INVALID")
    try:
        c.validate_mission(mission)
    except c.MissionRejected as exc:
        raise Refused("MISSION_REJECTED", exc.code) from exc
    spec = ag.AGENTS.get(agent_id)
    if spec is None or mission["agent_id"] != agent_id or mission["question"]["kind"] != spec.question_kind:
        raise Refused("AGENT_NOT_QUALIFIED", mission["agent_id"])
    if mission["budget"]["max_files"] > spec.max_files:
        raise Refused("LIMIT_INVALID", f"max_files > {spec.max_files}")
    if mission["analyzed_ref"] != {"kind": "GIT_COMMIT", "sha": analysed_sha}:
        raise Refused("ANALYSED_REF_MISMATCH")
    # Bornes : un argument ne peut que les abaisser.
    budget_s = mission["budget"]["max_wall_ms"] / 1000
    max_run_s = min(inv.MAX_RUN_S, budget_s, max_run_s if max_run_s is not None else inv.MAX_RUN_S)
    if max_run_s <= 0:
        raise Refused("LIMIT_INVALID")
    is_change = spec.question_kind == "CHANGE_IMPACT"
    verification = verify_checkout(checkout, code_sha=code_sha, analysed_sha=analysed_sha, mission=mission,
                                   analysed_tree=analysed_tree,
                                   allow_absent=frozenset(mission["scope"]["read_paths"]) if is_change else frozenset())
    diff = None
    if is_change:
        q = mission["question"]
        diff = git_diff(analysed_tree or checkout, q["base_sha"], analysed_sha, q["changed_paths"])
        if inv.hashlib_sha256(diff) != q["diff_sha256"]:
            raise Refused("DIFF_FINGERPRINT_MISMATCH", q["change_id"])

    lock = RunnerLock(reports, runner_id).acquire()
    try:
        now = clock()
        prev = lock.previous()
        # Préparation de la publication avant toute exécution : un dossier de preuves non sûr
        # (lien symbolique, type inattendu, droits) refuse l'invocation au lieu de l'exécuter.
        try:
            if isinstance(prev, dict) and isinstance(prev.get("invocation_id"), str) \
                    and inv.HEX32.match(prev["invocation_id"]) and isinstance(prev.get("mission_id"), str) \
                    and inv.parse_utc(prev.get("started_utc")) is not None \
                    and prev["invocation_id"] not in _published_ids(reports, prev["mission_id"]):
                publish(reports, _abandoned_envelope(prev, agent_id=agent_id, runner_id=runner_id, now=now))
            _cleanup_partials(reports, mission["mission_id"])
        except OSError as exc:
            raise Refused("PUBLICATION_FAILED", f"dossier de preuves non sûr ({type(exc).__name__})") from exc

        # SIGTERM est bloqué AVANT que le verrou ne devienne lisible (EN_COURS) et jusqu'à
        # l'installation du gestionnaire : un SIGTERM reçu dans cette fenêtre reste en attente
        # puis est délivré au déblocage, dans le try, et devient INTERRUPTED (jamais une mort
        # silencieuse avec verrou écrit et aucune enveloppe).
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
        try:
            invocation_id = secrets.token_hex(16)
            started_ts = clock()
            lock.write(inv.make_lock(agent_id=agent_id, runner_id=runner_id, mission_id=mission["mission_id"],
                                     invocation_id=invocation_id, pid=os.getpid(), now=started_ts,
                                     lease_s=min(lease_s, inv.MAX_LEASE_S)))
            limits = {"max_files": mission["budget"]["max_files"], "max_run_s": max_run_s,
                      "max_bytes": mission["budget"]["max_bytes"], "lease_s": min(lease_s, inv.MAX_LEASE_S)}
            report, state, exit_code, reason = None, "FAILED", 1, None

            def _alarm(_s, _f):
                raise _Timeout()

            def _term(_s, _f):
                raise _Interrupted()

            old_alarm = signal.signal(signal.SIGALRM, _alarm)
            old_term = signal.signal(signal.SIGTERM, _term)
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)  # SIGTERM en attente délivré ici
                signal.setitimer(signal.ITIMER_REAL, max_run_s)
                report = _analyse(mission, analysed_tree or checkout, checkout, diff, clock)
                state, exit_code = "COMPLETED", 0
            except _Timeout:
                state, exit_code, reason = "TIMEOUT", None, f"durée > {max_run_s} s"
            except (_Interrupted, KeyboardInterrupt):
                state, exit_code, reason = "INTERRUPTED", None, "interruption contrôlée (SIGTERM/SIGINT)"
            except Exception as exc:  # noqa: BLE001 — une panne devient FAILED, jamais un succès
                state, exit_code, reason = "FAILED", 1, type(exc).__name__
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_alarm)
                signal.signal(signal.SIGTERM, old_term)
        finally:
            # Masque initial rétabli sur tous les chemins (y compris exception avant le try interne).
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)

        env = inv.make_envelope(
            invocation_id=invocation_id, agent_id=agent_id, runner_id=runner_id, mission=mission,
            code_sha=code_sha, analysed_sha=analysed_sha, started_utc=inv.utc_iso(started_ts),
            ended_utc=inv.utc_iso(max(clock(), started_ts)), state=state, exit_code=exit_code,
            interruption_reason=reason, report=report if state == "COMPLETED" else None,
            limits=limits, verification=verification)
        try:
            name = publish(reports, env)
        except Refused:
            raise
        except OSError as exc:
            # Le contenu du verrou garde l'invocation : la suivante la consignera ABANDONED.
            raise Refused("PUBLICATION_FAILED", type(exc).__name__) from exc
        return env, name
    finally:
        lock.release()


# --- Point d'entrée -------------------------------------------------------------------------

def _apply_rlimits(max_run_s):
    import resource
    caps = {resource.RLIMIT_CPU: int(max_run_s) + 5, resource.RLIMIT_AS: 1 << 30,
            resource.RLIMIT_NOFILE: 256, resource.RLIMIT_FSIZE: 16 << 20}
    for res, val in caps.items():
        _soft, hard = resource.getrlimit(res)
        new = val if hard == resource.RLIM_INFINITY else min(val, hard)
        resource.setrlimit(res, (new, new))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m agent_bench.observation.executor",
                                 description="Invocation ponctuelle d'un agent d'observation (lecture seule).")
    ap.add_argument("--agent-id", default="repository-cartographer", choices=sorted(ag.AGENTS))
    ap.add_argument("--mission", required=True, help="fichier JSON de mission")
    ap.add_argument("--checkout", required=True, help="checkout git en lecture seule au SHA de code")
    ap.add_argument("--reports", required=True, help="dossier des rapports (seule écriture autorisée)")
    ap.add_argument("--runner-id", required=True)
    ap.add_argument("--code-sha", required=True)
    ap.add_argument("--analysed-sha", required=True)
    ap.add_argument("--analysed-tree", default=None, help="arbre git extrait au SHA analysé (suivi de main)")
    ap.add_argument("--max-run-s", type=float, default=None, help=f"≤ {inv.MAX_RUN_S} (abaissement seulement)")
    a = ap.parse_args(argv)
    out = {"contract": inv.INVOCATION_CONTRACT}
    try:
        mission = json.loads(Path(a.mission).read_text(encoding="utf-8"))
        cap = min(inv.MAX_RUN_S, a.max_run_s if a.max_run_s is not None else inv.MAX_RUN_S)
        _apply_rlimits(cap)
        env, name = run_once(mission=mission, checkout=Path(a.checkout), reports=Path(a.reports),
                             runner_id=a.runner_id, agent_id=a.agent_id, code_sha=a.code_sha,
                             analysed_sha=a.analysed_sha,
                             max_run_s=a.max_run_s,
                             analysed_tree=Path(a.analysed_tree) if a.analysed_tree else None)
    except Refused as exc:
        out.update({"outcome": "REFUSED" if exc.code != "PUBLICATION_FAILED" else "PUBLICATION_FAILED",
                    "code": exc.code, "detail": exc.detail})
        print(json.dumps(out, ensure_ascii=False))
        return EXIT_PUBLICATION_FAILED if exc.code == "PUBLICATION_FAILED" else EXIT_REFUSED
    except (OSError, ValueError) as exc:
        out.update({"outcome": "REFUSED", "code": "CONFIGURATION_INVALID", "detail": type(exc).__name__})
        print(json.dumps(out, ensure_ascii=False))
        return EXIT_REFUSED
    out.update({"outcome": "PUBLISHED", "file": name, "invocation_id": env["invocation_id"],
                "state": env["state"], "result_status": env["result_status"],
                "content_sha256": env["content_sha256"], "code_sha": env["code_sha"],
                "analysed_sha": env["analysed_sha"]})
    print(json.dumps(out, ensure_ascii=False))
    return EXIT_PUBLISHED_OK if env["state"] == "COMPLETED" else EXIT_PUBLISHED_NOT_COMPLETED


if __name__ == "__main__":
    sys.exit(main())
