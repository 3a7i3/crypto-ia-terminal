#!/usr/bin/python3 -I
"""Applicateur root du programmateur — Repository Cartographer SEULEMENT (P6-GOV-02).

Exception d'écriture unique (opérateur 2026-11-22 07:23Z, ratifiée P6-GOV-01 le 2026-11-26).
Déclenché par cat-obs-schedule.path quand l'API dépose /srv/cat-obs/schedule/requests/
repository-cartographer.request. Remplace la version bash (lien symbolique sur l'état, R1) et
la version #601 (trois agents, R2).

Règles :
- les décisions se prennent sur le DESCRIPTEUR ouvert (O_NOFOLLOW, O_NONBLOCK, fstat) : fichier
  régulier, un seul lien, propriétaire = utilisateur de l'API, taille ≤ 64, non exécutable ;
- contenu ASCII strict, exactement un mot de {10min, 1h, off} ; il n'est jamais exécuté ;
- la demande est consommée (unlinkat relatif au dossier), qu'elle soit acceptée ou refusée ;
- toute écriture (drop-in du timer, états publiés) se fait dans un dossier appartenant à root et
  non inscriptible par un tiers, via un temporaire O_EXCL puis rename atomique ;
- le DPA et le Market Observer ne peuvent être que LUS : leur état est republié depuis leurs
  drop-ins existants, qui ne sont jamais modifiés.

Sans argument : applique la demande du cartographe s'il y en a une, puis republie les trois états.
`--publish-only` : republie les trois états sans rien appliquer (installation, vérification).
"""
from __future__ import annotations

import errno
import grp
import json
import os
import pwd
import secrets
import stat
import subprocess
import sys
import syslog
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

AGENT = "repository-cartographer"
REQUEST_NAME = AGENT + ".request"
MAX_REQUEST = 64
RHYTHMS = {"10min": "*:0/10", "1h": "hourly", "off": None}
# Lecture seule : rythme publié à partir du drop-in existant de chaque timer.
TIMERS = {
    "repository-cartographer": ("cat-obs-cartographer", {"*:0/10": "10min", "hourly": "1h"}),
    "data-provenance-auditor": ("cat-obs-dpa", {"*:5/10": "10min", "*:30": "1h"}),
    "market-observer": ("cat-obs-market", {"*:3/10": "10min", "*:45": "1h"}),
}


class Refused(Exception):
    pass


@dataclass
class Config:
    root: str = "/srv/cat-obs/schedule"
    units: str = "/etc/systemd/system"
    request_owner_uid: int = -1
    state_gid: int = -1
    expected_dir_uid: int = 0
    systemctl: list = field(default_factory=lambda: ["/usr/bin/systemctl"])
    log: object = None

    @property
    def requests(self) -> str:
        return os.path.join(self.root, "requests")

    @property
    def state(self) -> str:
        return os.path.join(self.root, "state")


def _log(cfg: Config, msg: str) -> None:
    if cfg.log:
        cfg.log(msg)
    else:
        syslog.syslog(syslog.LOG_NOTICE, msg)


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _open_trusted_dir(path: str, cfg: Config) -> int:
    """Dossier réel (pas un lien), appartenant à root, non inscriptible par groupe/autres."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    st = os.fstat(fd)
    if st.st_uid != cfg.expected_dir_uid or st.st_mode & 0o022:
        os.close(fd)
        raise Refused(f"dossier non sûr : {path}")
    return fd


def safe_write(dirpath: str, name: str, data: bytes, mode: int, gid: int, cfg: Config) -> None:
    """Écriture atomique dans un dossier de confiance : O_EXCL + fchmod/fchown + fsync + rename."""
    dfd = _open_trusted_dir(dirpath, cfg)
    tmp = f".{name}.{secrets.token_hex(8)}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
        try:
            os.write(fd, data)
            if gid >= 0:
                os.fchown(fd, cfg.expected_dir_uid, gid)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
        os.fsync(dfd)
    except BaseException:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except OSError:
            pass
        raise
    finally:
        os.close(dfd)


def read_request(cfg: Config) -> str | None:
    """Renvoie le mot validé, None s'il n'y a pas de demande ; lève Refused sinon.

    La demande est toujours consommée (supprimée) une fois examinée."""
    dfd = os.open(cfg.requests, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        try:
            fd = os.open(REQUEST_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC,
                         dir_fd=dfd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            _consume(dfd, None)
            raise Refused("demande illisible ou lien symbolique" if exc.errno == errno.ELOOP else f"demande illisible ({exc.errno})")
        try:
            st = os.fstat(fd)
            try:
                if not stat.S_ISREG(st.st_mode):
                    raise Refused("demande : pas un fichier régulier")
                if st.st_nlink != 1:
                    raise Refused("demande : liens physiques multiples")
                if st.st_uid != cfg.request_owner_uid:
                    raise Refused("demande : propriétaire inattendu")
                if st.st_mode & 0o111:
                    raise Refused("demande : fichier exécutable")
                if st.st_size > MAX_REQUEST:
                    raise Refused("demande : trop volumineuse")
                raw = os.read(fd, MAX_REQUEST + 1)
                if len(raw) > MAX_REQUEST:
                    raise Refused("demande : trop volumineuse")
                try:
                    text = raw.decode("ascii")
                except UnicodeDecodeError:
                    raise Refused("demande : non ASCII") from None
                word = text[:-1] if text.endswith("\n") else text
                if word not in RHYTHMS:
                    raise Refused("demande : valeur hors liste")
                return word
            finally:
                _consume(dfd, st)
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def _consume(dfd: int, examined) -> None:
    """Supprime le nom examiné. Si le nom désigne désormais un autre objet que celui lu, on le
    supprime aussi : supprimer une entrée ne suit jamais de lien et ne touche pas sa cible."""
    try:
        os.unlink(REQUEST_NAME, dir_fd=dfd)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _drop_in_calendar(cfg: Config, unit: str) -> str | None:
    path = os.path.join(cfg.units, unit + ".timer.d", "rhythm.conf")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        text = os.read(fd, 4096).decode("ascii", "replace")
    finally:
        os.close(fd)
    values = [ln.split("=", 1)[1].strip() for ln in text.splitlines() if ln.startswith("OnCalendar=")]
    values = [v for v in values if v]
    return values[-1] if values else None


def _systemctl(cfg: Config, *args: str, check: bool = True) -> str:
    r = subprocess.run([*cfg.systemctl, *args], capture_output=True, text=True, timeout=30)
    if check and r.returncode != 0:
        raise RuntimeError(f"systemctl {' '.join(args)} : code {r.returncode}")
    return r.stdout.strip()


def _next_utc(cfg: Config, unit: str) -> str | None:
    raw = _systemctl(cfg, "show", unit + ".timer", "-p", "NextElapseUSecRealtime", "--value", check=False)
    try:
        dt = datetime.strptime(raw, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def publish_all(cfg: Config, last_request: dict | None = None) -> None:
    for agent, (unit, mapping) in TIMERS.items():
        enabled = _systemctl(cfg, "is-enabled", unit + ".timer", check=False)
        if enabled != "enabled":
            applied = "off"
        else:
            applied = mapping.get(_drop_in_calendar(cfg, unit) or "", "UNKNOWN")
        doc = {"agent_id": agent, "applied": applied, "applied_utc": _utc(),
               "next_utc": None if applied in ("off", "UNKNOWN") else _next_utc(cfg, unit),
               "writable": agent == AGENT}
        if agent == AGENT and last_request:
            doc["last_request"] = last_request
        safe_write(cfg.state, f"{agent}.json", (json.dumps(doc) + "\n").encode("ascii"), 0o640, cfg.state_gid, cfg)


def apply(cfg: Config, word: str) -> None:
    unit = TIMERS[AGENT][0]
    if word == "off":
        _systemctl(cfg, "disable", "--now", unit + ".timer")
        _systemctl(cfg, "stop", unit + ".service", check=False)
        return
    if not os.path.isfile(os.path.join(cfg.units, unit + ".timer")):
        raise Refused("timer de base absent")
    safe_write(os.path.join(cfg.units, unit + ".timer.d"), "rhythm.conf",
               f"[Timer]\nOnCalendar=\nOnCalendar={RHYTHMS[word]}\n".encode("ascii"), 0o644, -1, cfg)
    _systemctl(cfg, "daemon-reload")
    _systemctl(cfg, "enable", unit + ".timer")
    _systemctl(cfg, "restart", unit + ".timer")


def run(cfg: Config, publish_only: bool = False) -> int:
    if publish_only:
        publish_all(cfg)
        _log(cfg, "états republiés (lecture seule)")
        return 0
    try:
        word = read_request(cfg)
    except Refused as exc:
        _log(cfg, f"{AGENT} : demande refusée ({exc})")
        publish_all(cfg, {"value": None, "result": "REFUSED", "utc": _utc()})
        return 1
    if word is None:
        return 0
    try:
        apply(cfg, word)
    except (Refused, RuntimeError, OSError) as exc:
        _log(cfg, f"{AGENT} : échec d'application {word} ({exc})")
        publish_all(cfg, {"value": word, "result": "FAILED", "utc": _utc()})
        return 1
    publish_all(cfg, {"value": word, "result": "APPLIED", "utc": _utc()})
    _log(cfg, f"{AGENT} appliqué : {word}")
    return 0


def production_config() -> Config:
    owner = os.environ.get("CAT_SCHEDULE_REQUEST_OWNER", "")
    if os.geteuid() != 0 or not owner:
        raise SystemExit("cat-obs-schedule-apply : root et CAT_SCHEDULE_REQUEST_OWNER requis")
    return Config(request_owner_uid=pwd.getpwnam(owner).pw_uid, state_gid=grp.getgrnam("cat-obs-read").gr_gid)


if __name__ == "__main__":
    syslog.openlog("cat-obs-schedule")
    args = sys.argv[1:]
    if args not in ([], ["--publish-only"]):
        syslog.syslog(syslog.LOG_WARNING, "argument refusé")
        raise SystemExit(2)
    sys.exit(run(production_config(), publish_only=args == ["--publish-only"]))
