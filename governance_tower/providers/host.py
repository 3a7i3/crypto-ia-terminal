"""Observation hôte SANS POUVOIR (GOV-TOWER-00, mission GT-M3).

Quatre fournisseurs implémentent ``HostObservationProvider`` :

- ``NotConfiguredHostProvider`` (défaut) : aucune source, aucune valeur ;
- ``FixtureHostProvider`` : fixture JSON stricte, provenance ``SYNTHETIC`` ;
- ``SnapshotDirectoryHostProvider`` (opt-in) : copie locale des snapshots
  publiés ``runtime_service_snapshot.json`` et ``storage_snapshot.json`` ;
- ``OperatorApiHostProvider`` (opt-in) : GET des projections de l'Operator API
  via un tunnel local ou HTTPS.

GOV-TOWER-01 M2 (fixtures uniquement, aucune lecture réelle) : identité d'hôte
attendue (``HOST_MISMATCH``), monotonicité des horodatages entre deux lectures
(``NON_MONOTONIC``), type de contenu HTTP (``UNEXPECTED_CONTENT_TYPE``), ETag
consigné comme preuve s'il est sûr. Chaque refus reste borné au snapshot
concerné : les champs encore prouvés par l'autre snapshot sont conservés.

Règles : aucun shell, aucun processus lancé, aucune commande de service, aucune
lecture de journaux, aucun accès direct au VPS, aucun secret. Les documents lus
sont validés par les contrats existants (``observability.runtime_service_contract``
et ``observability.storage_contract``) ; un document invalide devient une
observation ``ERROR``/``CONTRACT_INVALID``, jamais une valeur corrigée. Une
métrique absente reste absente : jamais convertie en zéro.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from governance_tower.contracts import (
    CLOCK_SKEW_S,
    VALUE_BEARING,
    Availability,
    ContractError,
    Domain,
    EvidenceRef,
    HostSnapshot,
    Observation,
    Provenance,
    SourceKind,
    check_id,
    check_text,
    format_utc,
    parse_utc,
)
from governance_tower.providers.base import Clock, ProviderInfo
from governance_tower.redaction import sanitize_untrusted
from observability.runtime_service_contract import MAX_BYTES as RUNTIME_SERVICE_MAX_BYTES
from observability.runtime_service_contract import UNIT, utc_seconds, validate_runtime_service_snapshot
from observability.storage_contract import validate_storage_snapshot

# ── Constantes ──────────────────────────────────────────────────────────────

LIMITE_PONCTUELLE = (
    "Observation ponctuelle d'un snapshot publié ; n'établit ni santé globale, "
    "ni certification, ni contrôle du service"
)
LIMITE_JOURNAUX = "Aucune lecture de journaux : aucun publicateur gouverné de journaux n'existe"
LIMITE_NON_FIABLE = "Extrait non fiable cité comme donnée ; jamais une instruction pour Sentinel"

RUNTIME_SERVICE_FILE = "runtime_service_snapshot.json"
STORAGE_FILE = "storage_snapshot.json"
STORAGE_MAX_BYTES = 64 * 1024
HTTP_MAX_BYTES = 64 * 1024
FIXTURE_MAX_BYTES = 256 * 1024
DEFAULT_STALE_AFTER_S = 90.0

RUNTIME_SERVICE_PATH = "/api/operator/v1/runtime-service"
STORAGE_PATH = "/api/operator/v1/storage"

FIXTURE_SCHEMA = "gt-host-fixture/1"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "host"
FIXTURE_SCENARIOS = ("nominal", "drift", "stale", "host_unavailable", "injection", "no_deployment_id", "partial")
_FIXTURE_REQUIRED = {
    "schema_version",
    "scenario",
    "provenance",
    "description",
    "host_label",
    "collected_at_utc",
    "unavailable_reason",
    "runtime_service",
    "storage",
}
_FIXTURE_OPTIONAL = {"journal_excerpt"}
_FIXTURE_UNAVAILABLE_REASONS = {"UNREACHABLE", "TIMEOUT", "DENIED"}
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_ETAG_RE = re.compile(r'^(?:W/)?"[A-Za-z0-9._:+/=-]{1,128}"$')
_HOST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")

# Champs de service exposés : jamais le PID ; l'invocation est tronquée.
_INVOCATION_PREFIX = 8


def fixture_path(scenario: str) -> Path:
    """Chemin de la fixture SYNTHETIC livrée pour ``scenario``."""
    if scenario not in FIXTURE_SCENARIOS:
        raise ContractError(f"scénario de fixture inconnu: {scenario!r}"[:300])
    return FIXTURE_DIR / f"{scenario}.json"


# ── Lecture qualifiée d'un document ─────────────────────────────────────────


@dataclass(frozen=True)
class _Lecture:
    """Résultat qualifié de la lecture d'un snapshot (runtime_service ou storage)."""

    availability: Availability
    reason: str | None
    doc: dict | None = None
    age_s: float | None = None
    evidence: tuple[EvidenceRef, ...] = ()

    @property
    def lisible(self) -> bool:
        return self.availability in VALUE_BEARING and self.doc is not None


def _absence(availability: Availability, reason: str, evidence: tuple[EvidenceRef, ...] = ()) -> _Lecture:
    return _Lecture(availability, reason, None, None, evidence)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _charger_json_strict(raw: bytes) -> Any:
    """JSON strict : clés dupliquées et constantes NaN/Infinity refusées."""

    def paires(items: list[tuple[str, Any]]) -> dict:
        resultat: dict = {}
        for cle, valeur in items:
            if cle in resultat:
                raise ValueError("DUPLICATE_KEY")
            resultat[cle] = valeur
        return resultat

    def constante(_valeur: str) -> Any:
        raise ValueError("INVALID_CONSTANT")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=paires, parse_constant=constante)


def _evaluer_fraicheur(doc: dict, now_s: float, stale_after_s: float) -> tuple[Availability, str | None, float | None]:
    """Fraîcheur depuis l'horodatage du snapshot et l'horloge injectée."""
    generated = utc_seconds(doc.get("generated_at_utc"))
    observed = utc_seconds(doc.get("observed_at_utc"))
    if generated is None or observed is None or not math.isfinite(now_s):
        return Availability.ERROR, "CONTRACT_INVALID", None
    if generated - now_s > CLOCK_SKEW_S:
        return Availability.ERROR, "FUTURE_TIMESTAMP", None
    age = max(0.0, now_s - observed)
    if age > stale_after_s:
        return Availability.STALE, None, age
    return Availability.AVAILABLE, None, age


def _source_sha(nom: str, doc: dict) -> str | None:
    if nom != "runtime_service":
        return None
    deployment = doc.get("deployment")
    if isinstance(deployment, dict) and deployment.get("status") == "PRESENT":
        return deployment.get("source_code_sha")
    return None


def _qualifier(
    nom: str,
    doc: Any,
    raw_sha: str,
    *,
    now_s: float,
    stale_after_s: float,
    transport: bool,
    preuve: Callable[..., EvidenceRef],
) -> _Lecture:
    """Valide ``doc`` avec le contrat existant puis qualifie sa fraîcheur."""
    valide = validate_runtime_service_snapshot if nom == "runtime_service" else validate_storage_snapshot
    if not isinstance(doc, dict) or not valide(doc, transport=transport):
        return _absence(Availability.ERROR, "CONTRACT_INVALID", (preuve(content_sha256=raw_sha),))
    availability, reason, age = _evaluer_fraicheur(doc, now_s, stale_after_s)
    if transport and availability is Availability.AVAILABLE:
        # Fraîcheur calculée par le serveur au moment de sa lecture.
        age = float(doc["snapshot_age_s"])
        if doc["freshness_classification"] == "STALE" or age > stale_after_s:
            availability = Availability.STALE
    if availability not in VALUE_BEARING:
        return _absence(availability, reason or "CONTRACT_INVALID", (preuve(content_sha256=raw_sha),))
    ev = preuve(
        content_sha256=raw_sha,
        observed_at_utc=doc["observed_at_utc"],
        source_sha=_source_sha(nom, doc),
    )
    return _Lecture(availability, None, doc, age, (ev,))


# ── Construction des observations ───────────────────────────────────────────


def _obs_service(rs: _Lecture) -> Observation:
    if not rs.lisible:
        return Observation.absent(
            "host.service", Domain.HOST_SERVICE, UNIT, rs.availability, rs.reason or "UNKNOWN",
            rs.evidence, (LIMITE_PONCTUELLE,),
        )
    s = rs.doc["service"]
    invocation = s.get("invocation_id")
    valeur = {
        "host_id": sanitize_untrusted(rs.doc["host_id"]).text,
        "generated_at_utc": rs.doc["generated_at_utc"],
        "observed_at_utc": rs.doc["observed_at_utc"],
        "unit": s["unit"],
        "query_status": s["query_status"],
        "load_state": s["load_state"],
        "active_state": s["active_state"],
        "sub_state": s["sub_state"],
        "restart_count": s["restart_count"],
        "exec_main_started_at_utc": s["exec_main_started_at_utc"],
        "invocation_id_prefix": invocation[:_INVOCATION_PREFIX] if isinstance(invocation, str) else None,
    }
    return Observation(
        "host.service", Domain.HOST_SERVICE, UNIT, rs.availability, valeur, None, rs.evidence,
        (LIMITE_PONCTUELLE,), freshness_age_s=rs.age_s,
    )


def _obs_deployment(rs: _Lecture) -> Observation:
    if not rs.lisible:
        return Observation.absent(
            "host.deployment", Domain.HOST_DEPLOYMENT, "deployment", rs.availability, rs.reason or "UNKNOWN",
            rs.evidence, (LIMITE_PONCTUELLE,),
        )
    d = rs.doc["deployment"]
    if d["status"] != "PRESENT":
        # La raison du contrat est conservée telle quelle (UNKNOWN ≠ SHA).
        return Observation.absent(
            "host.deployment", Domain.HOST_DEPLOYMENT, "deployment", Availability.NOT_AVAILABLE, d["reason"],
            rs.evidence, (LIMITE_PONCTUELLE,),
        )
    valeur = {
        "source_code_sha": d["source_code_sha"],
        "artifact_sha256": d["artifact_sha256"],
        "evidence_ref": sanitize_untrusted(d["evidence_ref"]).text,
        "observed_at_utc": d["observed_at_utc"],
    }
    return Observation(
        "host.deployment", Domain.HOST_DEPLOYMENT, "deployment", rs.availability, valeur, None, rs.evidence,
        (LIMITE_PONCTUELLE,), freshness_age_s=rs.age_s,
    )


def _obs_storage(st: _Lecture) -> Observation:
    sujet = "decision_packet_logs"
    if not st.lisible:
        return Observation.absent(
            "host.storage", Domain.HOST_STORAGE, sujet, st.availability, st.reason or "UNKNOWN",
            st.evidence, (LIMITE_PONCTUELLE,),
        )
    doc = st.doc
    if doc["source_status"] != "PRESENT":
        # Métriques None dans le contrat : observation absente, jamais 0.
        return Observation.absent(
            "host.storage", Domain.HOST_STORAGE, sujet, Availability.NOT_AVAILABLE, doc["source_status"],
            st.evidence, (LIMITE_PONCTUELLE,),
        )
    valeur = {
        "generated_at_utc": doc["generated_at_utc"],
        "observed_at_utc": doc["observed_at_utc"],
        "source_status": doc["source_status"],
        "matched_file_count": doc["matched_file_count"],
        "total_bytes": doc["total_bytes"],
        "latest_file_modified_at_utc": doc["latest_file_modified_at_utc"],
    }
    return Observation(
        "host.storage", Domain.HOST_STORAGE, sujet, st.availability, valeur, None, st.evidence,
        (LIMITE_PONCTUELLE,), freshness_age_s=st.age_s,
    )


def _obs_journaux() -> Observation:
    return Observation.absent(
        "host.journaux", Domain.HOST_SERVICE, "journaux", Availability.NOT_AVAILABLE,
        "NO_GOVERNED_LOG_PUBLISHER", (), (LIMITE_PONCTUELLE, LIMITE_JOURNAUX),
    )


def _assembler(
    host_label: str,
    collected_at: str,
    rs: _Lecture,
    st: _Lecture,
    extra: tuple[Observation, ...] = (),
) -> HostSnapshot:
    observations = (_obs_service(rs), _obs_deployment(rs), _obs_storage(st), _obs_journaux()) + extra
    if rs.lisible:
        d = rs.doc["deployment"]
        sha = d["source_code_sha"] if d["status"] == "PRESENT" else None
        return HostSnapshot(host_label, collected_at, rs.availability, observations, sha, None)
    return HostSnapshot(host_label, collected_at, rs.availability, observations, None, rs.reason or "UNKNOWN")


def _hote_absent(
    host_label: str,
    collected_at: str,
    availability: Availability,
    reason: str,
    *,
    journaux: bool = True,
) -> HostSnapshot:
    """Hôte entièrement indisponible : chaque domaine reste visible et qualifié."""
    absence = _absence(availability, reason)
    observations = (_obs_service(absence), _obs_deployment(absence), _obs_storage(absence))
    if journaux:
        observations += (_obs_journaux(),)
    return HostSnapshot(host_label, collected_at, availability, observations, None, reason)


def _collected_at(clock: Clock) -> tuple[str, float]:
    moment = clock()
    texte = format_utc(moment)
    return texte, parse_utc(texte).timestamp()


def _check_stale(stale_after_s: float) -> float:
    if isinstance(stale_after_s, bool) or not isinstance(stale_after_s, (int, float)):
        raise ContractError("stale_after_s: nombre attendu")
    value = float(stale_after_s)
    if not math.isfinite(value) or value <= 0:
        raise ContractError("stale_after_s: nombre fini strictement positif attendu")
    return value


def _check_expected_host(expected_host_id: str | None) -> str | None:
    if expected_host_id is None:
        return None
    if not isinstance(expected_host_id, str) or not _HOST_ID_RE.match(expected_host_id):
        raise ContractError("expected_host_id: identifiant d'hôte invalide")
    return expected_host_id


class _Controles:
    """Contrôles inter-lectures d'un fournisseur réel : identité d'hôte et monotonicité.

    Un document qui recule dans le temps par rapport à la lecture précédente
    (rejeu, cache inversé, document forgé) ou qui décrit un autre hôte devient
    une absence ``ERROR`` ; il ne remplace jamais la valeur prouvée précédente.
    """

    def __init__(self, expected_host_id: str | None) -> None:
        self._expected = _check_expected_host(expected_host_id)
        self._dernier_observe: dict[str, float] = {}

    def appliquer(self, nom: str, lecture: _Lecture) -> _Lecture:
        if not lecture.lisible:
            return lecture
        doc = lecture.doc
        if nom == "runtime_service" and self._expected is not None and doc["host_id"] != self._expected:
            return _absence(Availability.ERROR, "HOST_MISMATCH", lecture.evidence)
        observe = utc_seconds(doc["observed_at_utc"])
        precedent = self._dernier_observe.get(nom)
        if observe is None or (precedent is not None and observe < precedent):
            return _absence(Availability.ERROR, "NON_MONOTONIC", lecture.evidence)
        self._dernier_observe[nom] = observe
        return lecture


# ── Fournisseur par défaut : non configuré ──────────────────────────────────


class NotConfiguredHostProvider:
    """Défaut : aucune source hôte configurée ; aucune valeur, aucune lecture."""

    info = ProviderInfo(
        name="host-not-configured",
        provenance=Provenance.LIVE_READ,
        live=False,
        description="Aucune observation hôte configurée (VPS_NOT_CONFIGURED)",
    )

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def host_snapshot(self) -> HostSnapshot:
        collected_at, _ = _collected_at(self._clock)
        return _hote_absent("VPS", collected_at, Availability.NOT_AVAILABLE, "VPS_NOT_CONFIGURED", journaux=False)


# ── Fixture SYNTHETIC ───────────────────────────────────────────────────────


def _lire_fichier_borne(path: Path, limite: int, *, dir_fd: int | None = None) -> bytes:
    """Lecture bornée d'un fichier régulier, sans suivre de lien symbolique.

    Lève ``FileNotFoundError`` si absent, ``ValueError('INVALID_PATH')`` pour un
    lien ou un fichier non régulier, ``ValueError('OUTPUT_LIMIT')`` si trop gros.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags, dir_fd=dir_fd)
    except (FileNotFoundError, PermissionError):
        raise
    except OSError as exc:  # ELOOP : lien symbolique refusé
        raise ValueError("INVALID_PATH") from exc
    with os.fdopen(fd, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("INVALID_PATH")
        raw = source.read(limite + 1)
    if len(raw) > limite:
        raise ValueError("OUTPUT_LIMIT")
    return raw


def _open_directory_no_symlinks(path: Path) -> int:
    """Traverse chaque composant via dir_fd, sans suivre de lien ni résoudre '..'."""
    absolute = path.absolute()
    if ".." in absolute.parts:
        raise OSError("INVALID_PATH")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _canonique(doc: Any) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class FixtureHostProvider:
    """Fixture JSON stricte ; provenance SYNTHETIC, jamais une preuve VPS.

    La fraîcheur est calculée contre ``collected_at_utc`` de la fixture (horloge
    fixe et déterministe) ; l'horloge injectée n'est pas utilisée pour la donnée.
    """

    info = ProviderInfo(
        name="host-fixture",
        provenance=Provenance.SYNTHETIC,
        live=False,
        description="Fixture SYNTHETIC de démonstration ; jamais une observation du VPS",
    )

    def __init__(self, path: Path, clock: Clock, *, stale_after_s: float = DEFAULT_STALE_AFTER_S) -> None:
        self._path = Path(path)
        self._clock = clock
        self._stale_after_s = _check_stale(stale_after_s)
        self._fixture = self._charger()

    def _charger(self) -> dict:
        try:
            raw = _lire_fichier_borne(self._path, FIXTURE_MAX_BYTES)
        except FileNotFoundError as exc:
            raise ContractError("fixture hôte absente") from exc
        except ValueError as exc:
            raise ContractError(f"fixture hôte refusée: {exc}") from exc
        try:
            data = _charger_json_strict(raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ContractError("fixture hôte: JSON invalide") from exc
        if not isinstance(data, dict):
            raise ContractError("fixture hôte: objet attendu")
        inconnues = set(data) - _FIXTURE_REQUIRED - _FIXTURE_OPTIONAL
        if inconnues:
            raise ContractError(f"fixture hôte: champs inconnus refusés {sorted(inconnues)}")
        manquants = _FIXTURE_REQUIRED - set(data)
        if manquants:
            raise ContractError(f"fixture hôte: champs manquants {sorted(manquants)}")
        if data["schema_version"] != FIXTURE_SCHEMA or data["provenance"] != "SYNTHETIC":
            raise ContractError("fixture hôte: schéma ou provenance non admis")
        check_id(data["scenario"], "scenario")
        check_text(data["description"], "description", 300)
        check_text(data["host_label"], "host_label", 100)
        parse_utc(data["collected_at_utc"])
        raison = data["unavailable_reason"]
        if raison is not None:
            if raison not in _FIXTURE_UNAVAILABLE_REASONS:
                raise ContractError("fixture hôte: raison d'indisponibilité hors vocabulaire")
            if data["runtime_service"] is not None or data["storage"] is not None or "journal_excerpt" in data:
                raise ContractError("fixture hôte: un hôte indisponible ne porte aucun snapshot")
        if "journal_excerpt" in data and not isinstance(data["journal_excerpt"], str):
            raise ContractError("fixture hôte: journal_excerpt textuel attendu")
        return data

    @property
    def scenario(self) -> str:
        return self._fixture["scenario"]

    def _preuve(self, element: str) -> Callable[..., EvidenceRef]:
        def fabrique(**kw: Any) -> EvidenceRef:
            return EvidenceRef(
                f"ev-fixture-{self.scenario}-{element}",
                SourceKind.HOST,
                f"fixture:host/{self.scenario}#{element}",
                Provenance.SYNTHETIC,
                self._fixture["collected_at_utc"],
                note="Fixture SYNTHETIC ; jamais une preuve VPS",
                **kw,
            )

        return fabrique

    def _lecture(self, nom: str, now_s: float) -> _Lecture:
        doc = self._fixture[nom]
        if doc is None:
            return _absence(Availability.NOT_AVAILABLE, "MISSING")
        return _qualifier(
            nom, doc, _sha256(_canonique(doc)), now_s=now_s, stale_after_s=self._stale_after_s,
            transport=False, preuve=self._preuve(nom),
        )

    def host_snapshot(self) -> HostSnapshot:
        f = self._fixture
        collected_at = f["collected_at_utc"]
        if f["unavailable_reason"] is not None:
            return _hote_absent(f["host_label"], collected_at, Availability.NOT_AVAILABLE, f["unavailable_reason"])
        now_s = parse_utc(collected_at).timestamp()
        rs = self._lecture("runtime_service", now_s)
        st = self._lecture("storage", now_s)
        extra: tuple[Observation, ...] = ()
        if "journal_excerpt" in f:
            cite = sanitize_untrusted(f["journal_excerpt"])
            ev = self._preuve("journal_excerpt")(content_sha256=_sha256(f["journal_excerpt"].encode("utf-8")))
            extra = (
                Observation(
                    "host.journal_excerpt", Domain.HOST_SERVICE, "journal_excerpt", Availability.AVAILABLE,
                    {"text": cite.text, "redactions": cite.redactions, "truncated": cite.truncated},
                    None, (ev,), (LIMITE_PONCTUELLE, LIMITE_NON_FIABLE), untrusted_content=True,
                ),
            )
        return _assembler(f["host_label"], collected_at, rs, st, extra)


# ── Répertoire local de snapshots publiés (opt-in) ──────────────────────────


class SnapshotDirectoryHostProvider:
    """Copie locale de snapshots publiés ; jamais le VPS directement.

    Lit exactement ``runtime_service_snapshot.json`` et ``storage_snapshot.json``
    dans ``directory`` et aucun autre fichier.
    """

    info = ProviderInfo(
        name="host-snapshot-directory",
        provenance=Provenance.LIVE_READ,
        live=True,
        description="Copie locale de snapshots publiés (runtime_service, storage) ; lecture seule",
    )

    def __init__(
        self,
        directory: Path,
        clock: Clock,
        *,
        host_label: str = "VPS",
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        expected_host_id: str | None = None,
    ) -> None:
        self._directory = Path(directory)
        self._clock = clock
        self._host_label = check_text(host_label, "host_label", 100)
        self._stale_after_s = _check_stale(stale_after_s)
        self._controles = _Controles(expected_host_id)

    def _preuve(self, nom: str, collected_at: str) -> Callable[..., EvidenceRef]:
        def fabrique(**kw: Any) -> EvidenceRef:
            return EvidenceRef(
                f"ev-host-{nom}", SourceKind.HOST, f"snapshot:{nom}", Provenance.LIVE_READ, collected_at,
                note="Copie locale d'un snapshot publié", **kw,
            )

        return fabrique

    def _lire(self, dir_fd: int, nom: str, fichier: str, limite: int, collected_at: str, now_s: float) -> _Lecture:
        preuve = self._preuve(nom, collected_at)
        try:
            raw = _lire_fichier_borne(Path(fichier), limite, dir_fd=dir_fd)
        except FileNotFoundError:
            return _absence(Availability.NOT_AVAILABLE, "MISSING")
        except PermissionError:
            return _absence(Availability.DENIED, "DENIED")
        except ValueError as exc:
            return _absence(Availability.ERROR, str(exc) if str(exc) in {"INVALID_PATH", "OUTPUT_LIMIT"} else "READ_ERROR")
        except OSError:
            return _absence(Availability.ERROR, "READ_ERROR")
        try:
            doc = _charger_json_strict(raw)
        except (ValueError, UnicodeError, RecursionError):
            return _absence(Availability.ERROR, "INVALID_JSON", (preuve(content_sha256=_sha256(raw)),))
        return _qualifier(
            nom, doc, _sha256(raw), now_s=now_s, stale_after_s=self._stale_after_s, transport=False, preuve=preuve,
        )

    def host_snapshot(self) -> HostSnapshot:
        collected_at, now_s = _collected_at(self._clock)
        try:
            dir_fd = _open_directory_no_symlinks(self._directory)
        except FileNotFoundError:
            return _hote_absent(self._host_label, collected_at, Availability.NOT_AVAILABLE, "SNAPSHOT_DIRECTORY_MISSING")
        except PermissionError:
            return _hote_absent(self._host_label, collected_at, Availability.DENIED, "DENIED")
        except OSError:  # lien symbolique (ELOOP) ou pas un répertoire (ENOTDIR)
            return _hote_absent(self._host_label, collected_at, Availability.ERROR, "INVALID_PATH")
        try:
            rs = self._lire(dir_fd, "runtime_service", RUNTIME_SERVICE_FILE, RUNTIME_SERVICE_MAX_BYTES, collected_at, now_s)
            st = self._lire(dir_fd, "storage", STORAGE_FILE, STORAGE_MAX_BYTES, collected_at, now_s)
        finally:
            os.close(dir_fd)
        rs = self._controles.appliquer("runtime_service", rs)
        st = self._controles.appliquer("storage", st)
        return _assembler(self._host_label, collected_at, rs, st)


# ── Operator API (opt-in, GET uniquement) ───────────────────────────────────


@dataclass(frozen=True)
class HttpReponse:
    status: int
    body: bytes
    headers: Mapping[str, str] | None = None  # en-têtes de réponse (noms insensibles à la casse)


#: ``transport(url, timeout_s, max_bytes)`` → ``HttpReponse`` ; lève ``TimeoutError``
#: en cas d'expiration et ``OSError`` si la destination est injoignable.
Transport = Callable[[str, float, int], HttpReponse]


def check_base_url(base_url: str) -> str:
    """Admet ``http://127.0.0.1:<port>``, ``http://localhost:<port>`` ou ``https://<hôte>``.

    Aucune information d'identification, requête, fragment ou chemin.
    """
    if not isinstance(base_url, str) or len(base_url) > 200 or any(c.isspace() for c in base_url):
        raise ContractError("base_url non admise")
    parts = urlsplit(base_url)
    try:
        port = parts.port
    except ValueError as exc:
        raise ContractError("base_url: port invalide") from exc
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ContractError("base_url: identifiants refusés")
    if parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ContractError("base_url: chemin, requête ou fragment refusés")
    if parts.scheme == "http":
        if parts.hostname not in {"127.0.0.1", "localhost"} or port is None:
            raise ContractError("base_url: http admis uniquement vers 127.0.0.1/localhost avec port explicite")
    elif parts.scheme == "https":
        if not parts.hostname:
            raise ContractError("base_url: hôte manquant")
    else:
        raise ContractError("base_url: schéma non admis")
    return f"{parts.scheme}://{parts.netloc}"


class _RefusRedirection(urllib.request.HTTPRedirectHandler):
    """Une redirection n'est jamais suivie : le code 3xx remonte tel quel."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport_urllib(url: str, timeout_s: float, max_bytes: int) -> HttpReponse:
    """GET sans authentification ni cookie ; redirections refusées ; corps borné."""
    handlers: list = [_RefusRedirection()]
    if urlsplit(url).scheme == "http":
        handlers.append(urllib.request.ProxyHandler({}))  # tunnel local : aucun intermédiaire
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [("Accept", "application/json"), ("User-Agent", "governance-tower-sentinel")]
    requete = urllib.request.Request(url, method="GET")
    try:
        with opener.open(requete, timeout=timeout_s) as reponse:
            return HttpReponse(reponse.status, reponse.read(max_bytes + 1), dict(reponse.headers.items()))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(max_bytes + 1)
        except OSError:
            body = b""
        finally:
            exc.close()
        return HttpReponse(exc.code, body, dict(exc.headers.items()) if exc.headers else None)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise TimeoutError("TIMEOUT") from exc
        raise ConnectionError("UNREACHABLE") from exc


class OperatorApiHostProvider:
    """GET des projections ``runtime-service`` et ``storage`` de l'Operator API.

    Aucun en-tête d'authentification, aucun cookie, aucune redirection suivie,
    aucune autre route. La base est un tunnel local ou une URL HTTPS.
    """

    info = ProviderInfo(
        name="host-operator-api",
        provenance=Provenance.LIVE_READ,
        live=True,
        description="Projections GET-only runtime-service et storage de l'Operator API",
    )

    def __init__(
        self,
        base_url: str,
        clock: Clock,
        *,
        transport: Transport | None = None,
        timeout_s: float = 5.0,
        host_label: str = "VPS",
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        expected_host_id: str | None = None,
    ) -> None:
        self._base = check_base_url(base_url)
        self._clock = clock
        self._transport = transport or _transport_urllib
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not (0 < timeout_s <= 30):
            raise ContractError("timeout_s: valeur entre 0 et 30 s attendue")
        self._timeout_s = float(timeout_s)
        self._host_label = check_text(host_label, "host_label", 100)
        self._stale_after_s = _check_stale(stale_after_s)
        self._controles = _Controles(expected_host_id)

    def _preuve(self, nom: str, collected_at: str, etag: str | None = None) -> Callable[..., EvidenceRef]:
        note = "via Operator API" + (f" · ETag {etag}" if etag else "")

        def fabrique(**kw: Any) -> EvidenceRef:
            return EvidenceRef(
                f"ev-host-{nom}", SourceKind.HOST, f"snapshot:{nom}", Provenance.LIVE_READ, collected_at,
                note=note, **kw,
            )

        return fabrique

    @staticmethod
    def _entetes(reponse: HttpReponse) -> dict[str, str] | None:
        if reponse.headers is None:
            return None
        if not isinstance(reponse.headers, Mapping):
            raise TypeError("en-têtes hors contrat")
        return {str(k).lower(): str(v)[:300] for k, v in reponse.headers.items()}

    def _lire(self, nom: str, route: str, collected_at: str, now_s: float) -> _Lecture:
        try:
            reponse = self._transport(self._base + route, self._timeout_s, HTTP_MAX_BYTES)
        except TimeoutError:
            return _absence(Availability.NOT_AVAILABLE, "TIMEOUT")
        except OSError:
            return _absence(Availability.NOT_AVAILABLE, "UNREACHABLE")
        except Exception:  # transport défaillant : erreur qualifiée, jamais une valeur
            return _absence(Availability.ERROR, "TRANSPORT_ERROR")
        if not isinstance(reponse, HttpReponse) or not isinstance(reponse.body, bytes):
            return _absence(Availability.ERROR, "TRANSPORT_ERROR")
        try:
            entetes = self._entetes(reponse)
        except TypeError:
            return _absence(Availability.ERROR, "TRANSPORT_ERROR")
        if len(reponse.body) > HTTP_MAX_BYTES:
            return _absence(Availability.ERROR, "OUTPUT_LIMIT")
        status = reponse.status
        if 300 <= status < 400:
            return _absence(Availability.ERROR, "REDIRECT_REFUSED")
        if status in (401, 403):
            return _absence(Availability.DENIED, "DENIED")
        if status == 429:
            return _absence(Availability.RATE_LIMITED, "RATE_LIMITED")
        if status in (404, 503):
            return _absence(Availability.NOT_AVAILABLE, self._raison_http(status, reponse.body))
        if status != 200:
            return _absence(Availability.ERROR, f"HTTP_{status}")
        etag = None
        if entetes is not None:
            if entetes.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return _absence(Availability.ERROR, "UNEXPECTED_CONTENT_TYPE")
            candidat = entetes.get("etag")
            etag = candidat if candidat is not None and _ETAG_RE.match(candidat) else None
        preuve = self._preuve(nom, collected_at, etag)
        try:
            doc = _charger_json_strict(reponse.body)
        except (ValueError, UnicodeError, RecursionError):
            return _absence(Availability.ERROR, "INVALID_JSON", (preuve(content_sha256=_sha256(reponse.body)),))
        return _qualifier(
            nom, doc, _sha256(reponse.body), now_s=now_s, stale_after_s=self._stale_after_s,
            transport=True, preuve=preuve,
        )

    @staticmethod
    def _raison_http(status: int, body: bytes) -> str:
        """``HTTP_<code>`` complété du code d'erreur du serveur s'il est sûr."""
        try:
            data = _charger_json_strict(body)
        except (ValueError, UnicodeError, RecursionError):
            data = None
        code = data.get("error_code") if isinstance(data, dict) else None
        if isinstance(code, str) and _ERROR_CODE_RE.match(code):
            return f"HTTP_{status}:{code}"
        return f"HTTP_{status}"

    def host_snapshot(self) -> HostSnapshot:
        collected_at, now_s = _collected_at(self._clock)
        rs = self._controles.appliquer("runtime_service", self._lire("runtime_service", RUNTIME_SERVICE_PATH, collected_at, now_s))
        st = self._controles.appliquer("storage", self._lire("storage", STORAGE_PATH, collected_at, now_s))
        return _assembler(self._host_label, collected_at, rs, st)


__all__ = [
    "FIXTURE_SCENARIOS",
    "FixtureHostProvider",
    "HttpReponse",
    "LIMITE_PONCTUELLE",
    "NotConfiguredHostProvider",
    "OperatorApiHostProvider",
    "SnapshotDirectoryHostProvider",
    "check_base_url",
    "fixture_path",
]
