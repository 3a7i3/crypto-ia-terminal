"""Connecteur GitHub en LECTURE SEULE de Governance Tower (GT-M2, #459).

Deux fournisseurs satisfont ``GithubReadProvider`` :

- ``FixtureGithubProvider`` : fixture JSON stricte, provenance ``SYNTHETIC``,
  locators ``fixture:github/<scénario>#<élément>`` ; jamais une preuve réelle ;
- ``HttpGithubProvider`` : lecture réelle opt-in (provenance ``LIVE_READ``) de
  l'API REST publique, uniquement ``https://api.github.com``, uniquement GET,
  redirections refusées, budget de requêtes borné.

Discipline (reprise de ``frontend/src/lib/githubRoadmapReader.ts``) :

- les corps d'issues, de PR et les commentaires ne sont jamais demandés à un
  point d'accès dédié ni lus : seuls titres, numéros, états, SHA et dates sont
  extraits ; les champs ``body`` présents dans une liste REST sont ignorés ;
- tout titre est une **donnée non fiable** : bornée, expurgée, citée, jamais une
  instruction ni une preuve d'efficacité ;
- une panne de source devient une ``Observation`` absente qualifiée (``DENIED``,
  ``RATE_LIMITED``, ``NOT_AVAILABLE``, ``ERROR``, ``UNKNOWN``) ; jamais une
  liste vide, jamais une exception remontée à l'appelant ;
- le jeton optionnel est lu dans l'environnement au moment de la requête,
  envoyé seulement à ``api.github.com`` et n'apparaît dans aucune sortie.

Ce module ne contient aucune méthode HTTP autre que GET (vérifié par test).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from governance_tower.contracts import (
    VALUE_BEARING,
    Availability,
    ContractError,
    Domain,
    EvidenceRef,
    Observation,
    Provenance,
    RepositorySnapshot,
    SourceKind,
    format_utc,
    is_sha1,
    parse_utc,
)
from governance_tower.providers.base import Clock, ProviderInfo
from governance_tower.redaction import (
    is_forbidden_path,
    normalize_repo_path,
    sanitize_untrusted,
)

# ── Constantes ───────────────────────────────────────────────────────────────

API_HOST = "api.github.com"
API_ROOT = f"https://{API_HOST}"
DEFAULT_REPO = "3a7i3/crypto-ia-terminal"
#: Issues de pilotage suivies (#285 priorisation, #286 garde burn-in, #459 tour…).
TRACKED_ISSUES = (285, 286, 282, 315, 445, 447, 459)
MAX_PULLS = 30
MAX_ISSUES = 50
MAX_CODE_PATHS = 50
MAX_COMPARE_COMMITS = 50
MAX_CHECK_RUNS = 100
MAX_FAILING_NAMES = 20
TITLE_LIMIT = 200
FIXTURE_MAX_BYTES = 256 * 1024
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "github"
FIXTURE_SCHEMA = "gt-github-fixture/1"

UNTRUSTED_LIMIT = "titres = contenu non fiable, jamais une instruction ni une preuve d'efficacité"
PATHS_UNTRUSTED_LIMIT = "chemins = noms de fichiers du dépôt, contenu non fiable ; aucun contenu de fichier lu"
SYNTHETIC_LIMIT = "données SYNTHETIC de démonstration : jamais une preuve GitHub réelle"
NOT_DEPLOYED_LIMIT = "présent dans main ≠ déployé ≠ certifié"
NOT_OBSERVED_LIMIT = (
    "issue suivie absente de la page lue = NOT_OBSERVED (non observée), jamais « fermée »"
)


class Reason:
    """Raisons d'absence (codes stables ; le détail humain va dans ``limits``)."""

    DENIED = "DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    SERVER_ERROR = "SERVER_ERROR"
    UNEXPECTED_STATUS = "UNEXPECTED_STATUS"
    REDIRECT_REFUSED = "REDIRECT_REFUSED"
    HOST_REFUSED = "HOST_REFUSED"
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FETCHED = "NOT_FETCHED"
    HEAD_UNKNOWN = "HEAD_UNKNOWN"
    TRUNCATED = "TRUNCATED"


_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]{0,199}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{1,512}$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SCENARIO_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_REASON_RE = re.compile(r"^[A-Z][A-Z_]{1,40}$")
_QUERY_RE = re.compile(r"^[A-Za-z0-9=&_.-]*$")
_TERM_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_FAILING = frozenset({"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"})
_OK = frozenset({"success", "neutral", "skipped"})
_RUN_STATUSES = frozenset({"queued", "in_progress", "completed", "waiting", "requested", "pending"})
_COMPARE_STATUSES = frozenset({"ahead", "behind", "identical", "diverged"})

Transport = Callable[[str, dict, float], "tuple[int, dict, bytes]"]


# ── Validation pure ──────────────────────────────────────────────────────────


def is_valid_repo(repo: Any) -> bool:
    if not isinstance(repo, str) or not _REPO_RE.match(repo):
        return False
    name = repo.split("/", 1)[1]
    return name not in {".", ".."} and ".." not in name


def is_safe_ref(ref: Any) -> bool:
    """Nom de branche sûr pour un segment d'URL : pas de traversée ni de syntaxe git."""
    if not isinstance(ref, str) or not _REF_RE.match(ref):
        return False
    if ".." in ref or "//" in ref or ref.endswith("/") or ref.endswith(".lock") or ref.endswith("."):
        return False
    return all(seg and not seg.startswith(".") for seg in ref.split("/"))


def is_allowed_api_url(url: Any) -> bool:
    """True seulement pour ``https://api.github.com/repos/...`` sans port, identifiant ni traversée."""
    if not isinstance(url, str) or len(url) > 2_000:
        return False
    if any(c in url for c in " \\\t\r\n%#@") or _TERM_CONTROL_RE.search(url):
        return False
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https" or parts.netloc != API_HOST or parts.hostname != API_HOST:
        return False
    if not parts.path.startswith("/repos/"):
        return False
    if any(seg in {".", ".."} for seg in parts.path.split("/")):
        return False
    return bool(_QUERY_RE.match(parts.query))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_utc(value: Any) -> bool:
    try:
        parse_utc(value)
    except ContractError:
        return False
    return True


def _first_line(text: Any) -> Any:
    return text.split("\n", 1)[0] if isinstance(text, str) else text


# ── Transport par défaut (urllib, GET uniquement) ───────────────────────────


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Aucune redirection n'est suivie : le 3xx remonte tel quel et sera refusé."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class UrllibTransport:
    """Transport stdlib : GET vers ``api.github.com`` uniquement, corps borné."""

    def __init__(self, max_body_bytes: int = 1_048_576) -> None:
        self._max = max_body_bytes

    def __repr__(self) -> str:
        return "UrllibTransport()"

    def __call__(self, url: str, headers: dict, timeout: float) -> tuple[int, dict, bytes]:
        if not is_allowed_api_url(url):
            raise PermissionError("hôte ou URL refusé")
        opener = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.ProxyHandler(),
            urllib.request.HTTPSHandler(),
            _RefuseRedirect(),
            urllib.request.HTTPDefaultErrorHandler(),
            urllib.request.HTTPErrorProcessor(),
        ):
            opener.add_handler(handler)
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with opener.open(request, timeout=timeout) as resp:
                return resp.status, dict(resp.headers.items()), resp.read(self._max + 1)
        except urllib.error.HTTPError as err:
            try:
                body = err.read(self._max + 1)
            except Exception:  # corps illisible : statut seul
                body = b""
            return err.code, dict(err.headers.items()) if err.headers else {}, body
        except urllib.error.URLError as err:
            if isinstance(err.reason, TimeoutError):
                raise TimeoutError("délai dépassé") from None
            raise ConnectionError("erreur réseau") from None


# ── Résultats internes ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Ok:
    data: Any
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class _Fail:
    availability: Availability
    reason: str
    detail: str
    evidence: tuple[EvidenceRef, ...] = ()


# ── Socle commun : construction des observations ─────────────────────────────


class _GithubReaderBase:
    info: ProviderInfo
    repo: str

    def __init__(self, repo: str, clock: Clock) -> None:
        if not is_valid_repo(repo):
            raise ContractError("dépôt GitHub invalide : forme owner/name attendue")
        if not callable(clock):
            raise ContractError("horloge invalide")
        self.repo = repo
        self._clock = clock
        self._collected = format_utc(clock())

    # Points d'extension des sources ------------------------------------------------

    def _begin_call(self) -> None:
        self._collected = format_utc(self._clock())

    def _extra_limits(self) -> tuple[str, ...]:
        return ()

    def _read_head(self) -> _Ok | _Fail:
        raise NotImplementedError

    def _read_ci(self, head_sha: str) -> _Ok | _Fail:
        raise NotImplementedError

    def _read_pulls(self) -> _Ok | _Fail:
        raise NotImplementedError

    def _read_issues(self) -> _Ok | _Fail:
        raise NotImplementedError

    def _read_tree(self, head_sha: str) -> _Ok | _Fail:
        raise NotImplementedError

    def _read_compare(self, base_sha: str, head_sha: str) -> _Ok | _Fail:
        raise NotImplementedError

    # Aides ------------------------------------------------------------------------

    def _limits(self, *items: str) -> tuple[str, ...]:
        return tuple(items) + self._extra_limits()

    def _absent(self, obs_id: str, domain: Domain, subject: str, fail: _Fail) -> Observation:
        return Observation.absent(
            obs_id,
            domain,
            subject,
            fail.availability,
            fail.reason,
            fail.evidence,
            self._limits(fail.detail),
        )

    def _guard(self, obs_id: str, domain: Domain, subject: str, build: Callable[[], Observation]) -> Observation:
        """Toute violation de contrat pendant la construction devient ERROR/INVALID_RESPONSE."""
        try:
            return build()
        except (ContractError, KeyError, TypeError, ValueError):
            return self._absent(
                obs_id,
                domain,
                subject,
                _Fail(Availability.ERROR, Reason.INVALID_RESPONSE, "réponse hors contrat : valeur refusée"),
            )

    @staticmethod
    def _title(raw: Any) -> dict[str, Any]:
        cleaned = sanitize_untrusted(_first_line(raw), limit=TITLE_LIMIT)
        return {
            "title": cleaned.text,
            "title_redacted": cleaned.redactions > 0,
            "title_truncated": cleaned.truncated,
        }

    # Méthodes du Protocol ---------------------------------------------------------

    def repository_snapshot(self) -> RepositorySnapshot:
        self._begin_call()
        subject_repo = f"Dépôt {self.repo}"
        head = self._read_head()
        observations: list[Observation] = []
        if isinstance(head, _Fail):
            observations.append(self._absent("gh-repository", Domain.REPOSITORY, subject_repo, head))
        else:
            observations.append(
                self._guard("gh-repository", Domain.REPOSITORY, subject_repo, lambda: self._repo_obs(head))
            )
        repo_obs = observations[0]
        if repo_obs.availability in VALUE_BEARING:
            head_sha = repo_obs.value["head_sha"]
            branch = repo_obs.value["default_branch"]
            ci = self._read_ci(head_sha)
            subject_ci = f"CI du HEAD {head_sha[:12]} ({branch})"
            observations.append(
                self._absent("gh-ci", Domain.CI, subject_ci, ci)
                if isinstance(ci, _Fail)
                else self._guard("gh-ci", Domain.CI, subject_ci, lambda: self._ci_obs(head_sha, ci))
            )
            pulls = self._read_pulls()
            observations.append(
                self._absent("gh-pull-requests", Domain.PULL_REQUESTS, "PR ouvertes", pulls)
                if isinstance(pulls, _Fail)
                else self._guard(
                    "gh-pull-requests", Domain.PULL_REQUESTS, "PR ouvertes", lambda: self._pulls_obs(pulls)
                )
            )
            issues = self._read_issues()
            observations.append(
                self._absent("gh-issues", Domain.ISSUES, "Issues ouvertes", issues)
                if isinstance(issues, _Fail)
                else self._guard("gh-issues", Domain.ISSUES, "Issues ouvertes", lambda: self._issues_obs(issues))
            )
            return RepositorySnapshot(
                self.repo, self._collected, Availability.AVAILABLE, tuple(observations), branch, head_sha
            )
        not_read = "dépôt ou HEAD non lus : source non interrogée"
        observations.append(
            self._absent(
                "gh-ci",
                Domain.CI,
                "CI du HEAD",
                _Fail(Availability.UNKNOWN, Reason.HEAD_UNKNOWN, "HEAD inconnu : CI non lisible"),
            )
        )
        for obs_id, domain, subject in (
            ("gh-pull-requests", Domain.PULL_REQUESTS, "PR ouvertes"),
            ("gh-issues", Domain.ISSUES, "Issues ouvertes"),
        ):
            observations.append(
                self._absent(obs_id, domain, subject, _Fail(Availability.UNKNOWN, Reason.NOT_FETCHED, not_read))
            )
        return RepositorySnapshot(self.repo, self._collected, repo_obs.availability, tuple(observations))

    def locate_code(self, terms: tuple[str, ...]) -> Observation:
        self._begin_call()
        subject = "Localisation de code (chemins seulement)"
        clean = _validate_terms(terms)
        if clean is None:
            return self._absent(
                "gh-code",
                Domain.CODE,
                subject,
                _Fail(Availability.ERROR, Reason.INVALID_INPUT, "termes refusés : 1 à 10 termes de 2 à 80 caractères"),
            )
        head = self._read_head()
        if isinstance(head, _Fail):
            return self._absent("gh-code", Domain.CODE, subject, head)
        head_sha = head.data["head_sha"]
        tree = self._read_tree(head_sha)
        if isinstance(tree, _Fail):
            return self._absent("gh-code", Domain.CODE, subject, tree)
        return self._guard(
            "gh-code", Domain.CODE, subject, lambda: self._code_obs(head_sha, clean, head.evidence + tree.evidence, tree)
        )

    def compare_commits(self, base_sha: str, head_sha: str) -> Observation:
        self._begin_call()
        if not (is_sha1(base_sha) and is_sha1(head_sha)):
            return self._absent(
                "gh-compare",
                Domain.REPOSITORY,
                "Comparaison de commits",
                _Fail(Availability.ERROR, Reason.INVALID_INPUT, "SHA refusé : 40 caractères hexadécimaux minuscules"),
            )
        subject = f"Commits de {head_sha[:12]} absents de {base_sha[:12]}"
        res = self._read_compare(base_sha, head_sha)
        if isinstance(res, _Fail):
            return self._absent("gh-compare", Domain.REPOSITORY, subject, res)
        return self._guard(
            "gh-compare", Domain.REPOSITORY, subject, lambda: self._compare_obs(base_sha, head_sha, res)
        )

    # Construction des valeurs -----------------------------------------------------

    def _repo_obs(self, head: _Ok) -> Observation:
        d = head.data
        value = {
            "repo": self.repo,
            "default_branch": d["default_branch"],
            "head_sha": d["head_sha"],
            "head_committed_at_utc": d["head_committed_at_utc"],
            **{f"head_{k}": v for k, v in self._title(d["head_title"]).items()},
        }
        return Observation(
            "gh-repository",
            Domain.REPOSITORY,
            f"Dépôt {self.repo}",
            Availability.AVAILABLE,
            value,
            None,
            head.evidence,
            self._limits(UNTRUSTED_LIMIT, NOT_DEPLOYED_LIMIT),
            untrusted_content=True,
        )

    def _ci_obs(self, head_sha: str, res: _Ok) -> Observation:
        runs = res.data["runs"]
        total = res.data["total_count"]
        subject = f"CI du HEAD {head_sha[:12]}"
        if total != len(runs):
            return self._absent(
                "gh-ci",
                Domain.CI,
                subject,
                _Fail(Availability.UNKNOWN, Reason.TRUNCATED, "contrôles incomplets pour ce HEAD : statut inconnu", res.evidence),
            )
        failing, pending, ok = [], [], 0
        for name, status, conclusion in runs:
            if status != "completed":
                pending.append(name)
            elif conclusion in _FAILING:
                failing.append(name)
            elif conclusion in _OK:
                ok += 1
            else:
                return self._absent(
                    "gh-ci",
                    Domain.CI,
                    subject,
                    _Fail(Availability.ERROR, Reason.INVALID_RESPONSE, "conclusion de contrôle inconnue", res.evidence),
                )
        status = "FAILURE" if failing else "PENDING" if pending else "SUCCESS" if ok else "NONE"
        value = {
            "head_sha": head_sha,
            "status": status,
            "total": total,
            "succeeded": ok,
            "failed": len(failing),
            "pending": len(pending),
            "failing_names": [sanitize_untrusted(n, limit=100).text for n in failing[:MAX_FAILING_NAMES]],
        }
        return Observation(
            "gh-ci",
            Domain.CI,
            subject,
            Availability.AVAILABLE,
            value,
            None,
            res.evidence,
            self._limits(
                "CI verte = contrôles du HEAD réussis, jamais une preuve de déploiement ni d'efficacité",
                "noms de contrôles = contenu non fiable",
            ),
            untrusted_content=True,
        )

    def _pulls_obs(self, res: _Ok) -> Observation:
        items = [
            {
                "number": p["number"],
                **self._title(p["title"]),
                "draft": p["draft"],
                "head_sha": p["head_sha"],
                "updated_at_utc": p["updated_at_utc"],
            }
            for p in res.data[:MAX_PULLS]
        ]
        limits = [UNTRUSTED_LIMIT, f"une seule page lue (≤ {MAX_PULLS} PR, triées par mise à jour)"]
        if len(res.data) >= MAX_PULLS:
            limits.append("page pleine : d'autres PR ouvertes peuvent exister (non observées)")
        return Observation(
            "gh-pull-requests",
            Domain.PULL_REQUESTS,
            "PR ouvertes",
            Availability.AVAILABLE,
            {"open_on_page": len(items), "items": items},
            None,
            res.evidence,
            self._limits(*limits),
            untrusted_content=True,
        )

    def _issues_obs(self, res: _Ok) -> Observation:
        kept = res.data[:MAX_ISSUES]
        items = [
            {"number": i["number"], **self._title(i["title"]), "updated_at_utc": i["updated_at_utc"]} for i in kept
        ]
        seen = {i["number"] for i in kept}
        tracked = [
            {"number": n, "status": "OBSERVED_OPEN" if n in seen else "NOT_OBSERVED"} for n in TRACKED_ISSUES
        ]
        limits = [UNTRUSTED_LIMIT, NOT_OBSERVED_LIMIT, f"une seule page lue (≤ {MAX_ISSUES} issues hors PR)"]
        if len(res.data) >= MAX_ISSUES:
            limits.append("page pleine : d'autres issues ouvertes peuvent exister (non observées)")
        return Observation(
            "gh-issues",
            Domain.ISSUES,
            "Issues ouvertes",
            Availability.AVAILABLE,
            {"open_on_page": len(items), "items": items, "tracked": tracked},
            None,
            res.evidence,
            self._limits(*limits),
            untrusted_content=True,
        )

    def _code_obs(
        self, head_sha: str, terms: tuple[str, ...], evidence: tuple[EvidenceRef, ...], tree: _Ok
    ) -> Observation:
        lowered = [t.lower() for t in terms]
        matches: list[tuple[int, str, str]] = []
        forbidden = 0
        for path, kind in tree.data["paths"]:
            norm = normalize_repo_path(path)
            if norm is None:
                continue
            hits = sum(1 for t in lowered if t in norm.lower())
            if not hits:
                continue
            if is_forbidden_path(norm):
                forbidden += 1
                continue
            matches.append((-hits, norm, kind))
        matches.sort()
        listed = [
            {"path": sanitize_untrusted(p, limit=400).text, "type": kind} for _, p, kind in matches[:MAX_CODE_PATHS]
        ]
        limits = [PATHS_UNTRUSTED_LIMIT, "chemins interdits (secrets, clés, .env) exclus"]
        if tree.data["truncated"]:
            limits.append("arbre tronqué par GitHub : correspondances incomplètes")
        if len(matches) > MAX_CODE_PATHS:
            limits.append(f"{len(matches)} correspondances ; seules les {MAX_CODE_PATHS} premières sont listées")
        value = {
            "head_sha": head_sha,
            "terms": [sanitize_untrusted(t, limit=80).text for t in terms],
            "paths": listed,
            "match_count": len(matches),
            "returned": len(listed),
            "forbidden_excluded": forbidden,
            "tree_truncated": tree.data["truncated"],
        }
        return Observation(
            "gh-code",
            Domain.CODE,
            "Localisation de code (chemins seulement)",
            Availability.AVAILABLE,
            value,
            None,
            evidence,
            self._limits(*limits),
            untrusted_content=True,
        )

    def _compare_obs(self, base_sha: str, head_sha: str, res: _Ok) -> Observation:
        d = res.data
        commits = [{"sha": sha, **self._title(msg)} for sha, msg in d["commits"][:MAX_COMPARE_COMMITS]]
        limits = [NOT_DEPLOYED_LIMIT, UNTRUSTED_LIMIT]
        if len(commits) < d["total_commits"]:
            limits.append(
                f"liste partielle : {len(commits)} commits listés sur {d['total_commits']} (ordre chronologique)"
            )
        value = {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": d["status"],
            "ahead_by": d["ahead_by"],
            "behind_by": d["behind_by"],
            "total_commits": d["total_commits"],
            "commits": commits,
            "commits_returned": len(commits),
        }
        return Observation(
            "gh-compare",
            Domain.REPOSITORY,
            f"Commits de {head_sha[:12]} absents de {base_sha[:12]}",
            Availability.AVAILABLE,
            value,
            None,
            res.evidence,
            self._limits(*limits),
            untrusted_content=True,
        )


def _validate_terms(terms: Any) -> tuple[str, ...] | None:
    if isinstance(terms, str) or not isinstance(terms, (tuple, list)) or not 1 <= len(terms) <= 10:
        return None
    out = []
    for term in terms:
        if not isinstance(term, str) or _TERM_CONTROL_RE.search(term):
            return None
        stripped = term.strip()
        if not 2 <= len(stripped) <= 80:
            return None
        out.append(stripped)
    return tuple(out)


# ── Fournisseur fixture (SYNTHETIC) ──────────────────────────────────────────

_FX_TOP = {
    "schema",
    "nature",
    "scenario",
    "warning",
    "repo",
    "repository",
    "ci",
    "pull_requests",
    "issues",
    "code_tree",
    "comparisons",
}


def _fx_fail(msg: str) -> ContractError:
    return ContractError(f"fixture GitHub : {msg}")


def _fx_keys(raw: Any, keys: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict) or set(raw) != keys:
        raise _fx_fail(f"{name} : clés attendues {sorted(keys)}")
    return raw


def _fx_str(value: Any, name: str, limit: int = 2_000) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise _fx_fail(f"{name} : texte attendu")
    return value


def _fx_list(value: Any, name: str, limit: int = 1_000) -> list:
    if not isinstance(value, list) or len(value) > limit:
        raise _fx_fail(f"{name} : liste bornée attendue")
    return value


def _fx_section(raw: Any, name: str, parse: Callable[[Any], Any]) -> tuple[str, Any]:
    if not isinstance(raw, dict) or len(raw) != 1 or not ({"available", "absent"} & set(raw)):
        raise _fx_fail(f"{name} : exactement une clé 'available' ou 'absent'")
    if "absent" in raw:
        absent = _fx_keys(raw["absent"], {"availability", "reason"}, f"{name}.absent")
        try:
            availability = Availability(absent["availability"])
        except ValueError as exc:
            raise _fx_fail(f"{name}.absent : disponibilité inconnue") from exc
        if availability in VALUE_BEARING:
            raise _fx_fail(f"{name}.absent : une absence ne peut pas porter de valeur")
        reason = absent["reason"]
        if not isinstance(reason, str) or not _REASON_RE.match(reason):
            raise _fx_fail(f"{name}.absent : raison invalide")
        return "absent", (availability, reason)
    return "available", parse(raw["available"])


def _fx_number(value: Any, name: str) -> int:
    if not _is_int(value) or value <= 0:
        raise _fx_fail(f"{name} : entier positif attendu")
    return value


def _fx_sha(value: Any, name: str) -> str:
    if not is_sha1(value):
        raise _fx_fail(f"{name} : SHA-1 attendu")
    return value


def _fx_utc(value: Any, name: str) -> str:
    if not _is_utc(value):
        raise _fx_fail(f"{name} : horodatage UTC attendu")
    return value


def _fx_repository(raw: Any) -> dict:
    d = _fx_keys(raw, {"default_branch", "head_sha", "head_committed_at_utc", "head_title"}, "repository")
    if not is_safe_ref(d["default_branch"]):
        raise _fx_fail("repository.default_branch : référence non sûre")
    return {
        "default_branch": d["default_branch"],
        "head_sha": _fx_sha(d["head_sha"], "repository.head_sha"),
        "head_committed_at_utc": _fx_utc(d["head_committed_at_utc"], "repository.head_committed_at_utc"),
        "head_title": _fx_str(d["head_title"], "repository.head_title"),
    }


def _fx_ci(raw: Any) -> dict:
    d = _fx_keys(raw, {"check_runs"}, "ci")
    runs = []
    for run in _fx_list(d["check_runs"], "ci.check_runs", MAX_CHECK_RUNS):
        r = _fx_keys(run, {"name", "status", "conclusion"}, "ci.check_runs[]")
        if r["status"] not in _RUN_STATUSES or not (r["conclusion"] is None or isinstance(r["conclusion"], str)):
            raise _fx_fail("ci.check_runs[] : statut/conclusion invalides")
        runs.append((_fx_str(r["name"], "ci.name", 200), r["status"], r["conclusion"]))
    return {"runs": runs, "total_count": len(runs)}


def _fx_pulls(raw: Any) -> list:
    d = _fx_keys(raw, {"items"}, "pull_requests")
    out = []
    for item in _fx_list(d["items"], "pull_requests.items", 200):
        p = _fx_keys(item, {"number", "title", "draft", "head_sha", "updated_at_utc"}, "pull_requests.items[]")
        if not isinstance(p["draft"], bool):
            raise _fx_fail("pull_requests.items[].draft : booléen attendu")
        out.append(
            {
                "number": _fx_number(p["number"], "pr.number"),
                "title": _fx_str(p["title"], "pr.title"),
                "draft": p["draft"],
                "head_sha": _fx_sha(p["head_sha"], "pr.head_sha"),
                "updated_at_utc": _fx_utc(p["updated_at_utc"], "pr.updated_at_utc"),
            }
        )
    return out


def _fx_issues(raw: Any) -> list:
    d = _fx_keys(raw, {"items"}, "issues")
    out = []
    for item in _fx_list(d["items"], "issues.items", 200):
        i = _fx_keys(item, {"number", "title", "updated_at_utc"}, "issues.items[]")
        out.append(
            {
                "number": _fx_number(i["number"], "issue.number"),
                "title": _fx_str(i["title"], "issue.title"),
                "updated_at_utc": _fx_utc(i["updated_at_utc"], "issue.updated_at_utc"),
            }
        )
    return out


def _fx_tree(raw: Any) -> dict:
    d = _fx_keys(raw, {"truncated", "paths"}, "code_tree")
    if not isinstance(d["truncated"], bool):
        raise _fx_fail("code_tree.truncated : booléen attendu")
    paths = [(_fx_str(p, "code_tree.paths[]", 400), "blob") for p in _fx_list(d["paths"], "code_tree.paths", 5_000)]
    return {"paths": paths, "truncated": d["truncated"]}


def _fx_comparisons(raw: Any) -> dict:
    d = _fx_keys(raw, {"items"}, "comparisons")
    out: dict[tuple[str, str], dict] = {}
    keys = {"base_sha", "head_sha", "status", "ahead_by", "behind_by", "total_commits", "commits"}
    for item in _fx_list(d["items"], "comparisons.items", 20):
        c = _fx_keys(item, keys, "comparisons.items[]")
        if c["status"] not in _COMPARE_STATUSES:
            raise _fx_fail("comparisons.items[].status : hors vocabulaire")
        for k in ("ahead_by", "behind_by", "total_commits"):
            if not _is_int(c[k]) or c[k] < 0:
                raise _fx_fail(f"comparisons.items[].{k} : entier positif ou nul attendu")
        commits = []
        for commit in _fx_list(c["commits"], "comparisons.commits", 250):
            cm = _fx_keys(commit, {"sha", "title"}, "comparisons.commits[]")
            commits.append((_fx_sha(cm["sha"], "commit.sha"), _fx_str(cm["title"], "commit.title")))
        if len(commits) > c["total_commits"]:
            raise _fx_fail("comparisons.items[] : plus de commits listés que total_commits")
        pair = (_fx_sha(c["base_sha"], "base_sha"), _fx_sha(c["head_sha"], "head_sha"))
        out[pair] = {
            "status": c["status"],
            "ahead_by": c["ahead_by"],
            "behind_by": c["behind_by"],
            "total_commits": c["total_commits"],
            "commits": commits,
        }
    return out


def _reject_constant(name: str) -> Any:
    raise _fx_fail(f"constante JSON non finie refusée ({name})")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _fx_fail(f"clé dupliquée {key!r}")
        out[key] = value
    return out


def load_github_fixture(path: Path) -> dict[str, Any]:
    """Charge et valide strictement une fixture ; toute anomalie lève ``ContractError``."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise _fx_fail("fichier refusé (lien symbolique ou absent)")
    if path.stat().st_size > FIXTURE_MAX_BYTES:
        raise _fx_fail("fichier trop volumineux")
    raw_bytes = path.read_bytes()
    if len(raw_bytes) > FIXTURE_MAX_BYTES:
        raise _fx_fail("fichier trop volumineux")
    try:
        doc = json.loads(
            raw_bytes.decode("utf-8"), object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fx_fail("JSON invalide") from exc
    doc = _fx_keys(doc, _FX_TOP, "racine")
    if doc["schema"] != FIXTURE_SCHEMA or doc["nature"] != "SYNTHETIC":
        raise _fx_fail("schéma ou nature inattendus")
    if not isinstance(doc["scenario"], str) or not _SCENARIO_RE.match(doc["scenario"]):
        raise _fx_fail("scénario invalide")
    _fx_str(doc["warning"], "warning", 600)
    if not is_valid_repo(doc["repo"]):
        raise _fx_fail("repo invalide")
    return {
        "scenario": doc["scenario"],
        "repo": doc["repo"],
        "repository": _fx_section(doc["repository"], "repository", _fx_repository),
        "ci": _fx_section(doc["ci"], "ci", _fx_ci),
        "pull_requests": _fx_section(doc["pull_requests"], "pull_requests", _fx_pulls),
        "issues": _fx_section(doc["issues"], "issues", _fx_issues),
        "code_tree": _fx_section(doc["code_tree"], "code_tree", _fx_tree),
        "comparisons": _fx_section(doc["comparisons"], "comparisons", _fx_comparisons),
    }


class FixtureGithubProvider(_GithubReaderBase):
    """Lecture d'une fixture SYNTHETIC : démonstration, jamais une preuve GitHub."""

    def __init__(self, path: Path, clock: Clock) -> None:
        fixture = load_github_fixture(path)
        super().__init__(fixture["repo"], clock)
        self._fx = fixture
        self.scenario: str = fixture["scenario"]
        self.info = ProviderInfo(
            name=f"github-fixture:{self.scenario}",
            provenance=Provenance.SYNTHETIC,
            live=False,
            description="Fixture GitHub SYNTHETIC de démonstration ; aucune lecture réseau.",
        )

    @classmethod
    def scenario_named(cls, scenario: str, clock: Clock) -> "FixtureGithubProvider":
        if not isinstance(scenario, str) or not _SCENARIO_RE.match(scenario):
            raise ContractError("scénario de fixture invalide")
        return cls(FIXTURE_DIR / f"{scenario}.json", clock)

    def __repr__(self) -> str:
        return f"FixtureGithubProvider(repo={self.repo!r}, scenario={self.scenario!r})"

    def _extra_limits(self) -> tuple[str, ...]:
        return (SYNTHETIC_LIMIT,)

    def _evidence(self, element: str, source_sha: str | None = None) -> tuple[EvidenceRef, ...]:
        return (
            EvidenceRef(
                evidence_id=f"gh-fx-{self.scenario}-{element.replace(':', '-')}"[:128],
                source=SourceKind.GITHUB,
                locator=f"fixture:github/{self.scenario}#{element}",
                provenance=Provenance.SYNTHETIC,
                collected_at_utc=self._collected,
                source_sha=source_sha,
                note="Fixture SYNTHETIC : jamais une preuve GitHub réelle.",
            ),
        )

    def _section(self, name: str, source_sha: str | None = None) -> _Ok | _Fail:
        state, payload = self._fx[name]
        if state == "absent":
            availability, reason = payload
            return _Fail(availability, reason, f"source {name} absente dans la fixture {self.scenario}")
        return _Ok(payload, self._evidence(name, source_sha))

    def _read_head(self) -> _Ok | _Fail:
        state, payload = self._fx["repository"]
        return self._section("repository", payload["head_sha"] if state == "available" else None)

    def _read_ci(self, head_sha: str) -> _Ok | _Fail:
        return self._section("ci", head_sha)

    def _read_pulls(self) -> _Ok | _Fail:
        return self._section("pull_requests")

    def _read_issues(self) -> _Ok | _Fail:
        return self._section("issues")

    def _read_tree(self, head_sha: str) -> _Ok | _Fail:
        return self._section("code_tree", head_sha)

    def _read_compare(self, base_sha: str, head_sha: str) -> _Ok | _Fail:
        res = self._section("comparisons")
        if isinstance(res, _Fail):
            return res
        found = res.data.get((base_sha, head_sha))
        if found is None:
            return _Fail(Availability.NOT_AVAILABLE, Reason.NOT_FOUND, "comparaison absente de la fixture")
        element = f"compare:{base_sha[:12]}...{head_sha[:12]}"
        return _Ok(found, self._evidence(element, head_sha))


# ── Fournisseur HTTP (LIVE_READ, opt-in) ─────────────────────────────────────


class HttpGithubProvider(_GithubReaderBase):
    """Lecture réelle opt-in de l'API REST GitHub ; GET uniquement vers api.github.com."""

    def __init__(
        self,
        repo: str = DEFAULT_REPO,
        *,
        clock: Clock,
        transport: Transport | None = None,
        token_env: str = "GT_GITHUB_TOKEN",
        max_requests: int = 40,
        timeout_s: float = 10.0,
        max_body_bytes: int = 1_048_576,
    ) -> None:
        super().__init__(repo, clock)
        if not isinstance(token_env, str) or not _ENV_NAME_RE.match(token_env):
            raise ContractError("token_env : nom de variable d'environnement invalide")
        if not _is_int(max_requests) or not 1 <= max_requests <= 1_000:
            raise ContractError("max_requests : entier entre 1 et 1000 attendu")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 < timeout_s <= 60:
            raise ContractError("timeout_s : nombre dans ]0, 60] attendu")
        if not _is_int(max_body_bytes) or not 1 <= max_body_bytes <= 16 * 1_048_576:
            raise ContractError("max_body_bytes : entier entre 1 et 16 Mio attendu")
        if transport is not None and not callable(transport):
            raise ContractError("transport : appelable attendu")
        self._token_env = token_env
        self._max_requests = max_requests
        self._timeout = float(timeout_s)
        self._max_body = max_body_bytes
        self._transport: Transport = transport if transport is not None else UrllibTransport(max_body_bytes)
        self._sent = 0
        self._halt: _Fail | None = None
        self.info = ProviderInfo(
            name="github-http",
            provenance=Provenance.LIVE_READ,
            live=True,
            description="Lecture réelle opt-in de api.github.com (GET uniquement, budget borné).",
        )

    def __repr__(self) -> str:
        return f"HttpGithubProvider(repo={self.repo!r}, requests_sent={self._sent}, max_requests={self._max_requests})"

    __str__ = __repr__

    @property
    def requests_sent(self) -> int:
        return self._sent

    def _begin_call(self) -> None:
        super()._begin_call()
        self._halt = None

    # Requête GET unique -------------------------------------------------------------

    def _url(self, *segments: str, query: str = "") -> str:
        path = "/".join(urllib.parse.quote(seg, safe="/") for seg in segments)
        url = f"{API_ROOT}/repos/{self.repo}" + (f"/{path}" if path else "")
        return f"{url}?{query}" if query else url

    def _headers(self, url: str) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "governance-tower-sentinel/0.1 (read-only)",
        }
        if is_allowed_api_url(url):
            token = os.environ.get(self._token_env, "")
            if token and _TOKEN_RE.match(token):
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get(self, url: str, element: str, source_sha: str | None = None) -> _Ok | _Fail:
        """Un GET borné ; retourne le JSON décodé ou un échec qualifié, jamais d'exception."""
        if self._halt is not None:
            return _Fail(
                Availability.UNKNOWN,
                Reason.NOT_FETCHED,
                f"requête non envoyée : lecture interrompue après {self._halt.reason}",
            )
        if not is_allowed_api_url(url):
            return _Fail(Availability.ERROR, Reason.HOST_REFUSED, "URL refusée : seul https://api.github.com/repos/ est admis")
        if self._sent >= self._max_requests:
            return _Fail(
                Availability.NOT_AVAILABLE,
                Reason.BUDGET_EXCEEDED,
                f"budget de {self._max_requests} requêtes atteint : aucune requête envoyée",
            )
        self._sent += 1
        try:
            result = self._transport(url, self._headers(url), self._timeout)
        except TimeoutError:
            self._halt = _Fail(Availability.NOT_AVAILABLE, Reason.TIMEOUT, "délai dépassé")
            return self._halt
        except OSError:
            self._halt = _Fail(Availability.NOT_AVAILABLE, Reason.NETWORK, "erreur réseau")
            return self._halt
        except Exception:  # transport défaillant : jamais propagé, jamais cité
            return _Fail(Availability.ERROR, Reason.TRANSPORT_ERROR, "transport en échec")
        if (
            not isinstance(result, tuple)
            or len(result) != 3
            or not _is_int(result[0])
            or not isinstance(result[1], Mapping)
            or not isinstance(result[2], (bytes, bytearray))
        ):
            return _Fail(Availability.ERROR, Reason.INVALID_RESPONSE, "réponse de transport hors contrat")
        status, raw_headers, body = result
        headers = {str(k).lower(): str(v) for k, v in raw_headers.items()}
        evidence = (
            EvidenceRef(
                evidence_id=f"gh-live-{element}",
                source=SourceKind.GITHUB,
                locator=url,
                provenance=Provenance.LIVE_READ,
                collected_at_utc=self._collected,
                source_sha=source_sha if status == 200 else None,
                note=f"GET HTTP {status}",
            ),
        )
        failure = self._classify(status, headers, evidence)
        if failure is not None:
            return failure
        if len(body) > self._max_body:
            return _Fail(Availability.ERROR, Reason.OUTPUT_LIMIT, f"corps > {self._max_body} octets : refusé", evidence)
        try:
            data = json.loads(bytes(body).decode("utf-8"), parse_constant=_reject_json_constant)
        except Exception:
            return _Fail(Availability.ERROR, Reason.INVALID_RESPONSE, "réponse non JSON", evidence)
        return _Ok(data, evidence)

    def _classify(self, status: int, headers: Mapping[str, str], evidence: tuple[EvidenceRef, ...]) -> _Fail | None:
        if status == 200:
            return None
        if 300 <= status < 400:
            return _Fail(Availability.ERROR, Reason.REDIRECT_REFUSED, f"redirection HTTP {status} refusée", evidence)
        exhausted = headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
        if status == 429 or (status == 403 and exhausted):
            reset = headers.get("x-ratelimit-reset", "")
            detail = "quota GitHub épuisé"
            if reset.isdigit() and len(reset) <= 12:
                detail += f" (réinitialisation epoch {reset})"
            self._halt = _Fail(Availability.RATE_LIMITED, Reason.RATE_LIMITED, detail, evidence)
            return self._halt
        if status in (401, 403):
            fail = _Fail(Availability.DENIED, Reason.DENIED, f"accès refusé par GitHub (HTTP {status})", evidence)
            if status == 401:
                self._halt = fail
            return fail
        if status == 404:
            return _Fail(Availability.NOT_AVAILABLE, Reason.NOT_FOUND, "objet introuvable sur GitHub (404)", evidence)
        if 500 <= status < 600:
            return _Fail(Availability.ERROR, Reason.SERVER_ERROR, f"erreur serveur GitHub (HTTP {status})", evidence)
        return _Fail(Availability.ERROR, Reason.UNEXPECTED_STATUS, f"statut HTTP inattendu {status}", evidence)

    @staticmethod
    def _invalid(res: _Ok, detail: str = "forme de réponse inattendue") -> _Fail:
        return _Fail(Availability.ERROR, Reason.INVALID_RESPONSE, detail, res.evidence)

    # Lectures --------------------------------------------------------------------

    def _read_head(self) -> _Ok | _Fail:
        repo = self._get(self._url(), "repository")
        if isinstance(repo, _Fail):
            return repo
        branch = repo.data.get("default_branch") if isinstance(repo.data, dict) else None
        if not is_safe_ref(branch):
            return self._invalid(repo, "branche par défaut absente ou non sûre")
        res = self._get(self._url("branches", branch), "branch")
        if isinstance(res, _Fail):
            return res
        try:
            commit = res.data["commit"]
            sha = commit["sha"]
            inner = commit["commit"]
            date = inner["committer"]["date"]
            message = inner["message"]
        except (KeyError, TypeError):
            return self._invalid(res)
        if not is_sha1(sha) or not _is_utc(date) or not isinstance(message, str):
            return self._invalid(res)
        evidence = tuple(
            EvidenceRef(
                e.evidence_id, e.source, e.locator, e.provenance, e.collected_at_utc, source_sha=sha, note=e.note
            )
            for e in repo.evidence + res.evidence
        )
        return _Ok(
            {"default_branch": branch, "head_sha": sha, "head_committed_at_utc": date, "head_title": message},
            evidence,
        )

    def _read_ci(self, head_sha: str) -> _Ok | _Fail:
        if not is_sha1(head_sha):
            return _Fail(Availability.ERROR, Reason.INVALID_INPUT, "SHA du HEAD invalide")
        res = self._get(
            self._url("commits", head_sha, "check-runs", query=f"per_page={MAX_CHECK_RUNS}"), "ci", head_sha
        )
        if isinstance(res, _Fail):
            return res
        d = res.data
        if not isinstance(d, dict) or not _is_int(d.get("total_count")) or not isinstance(d.get("check_runs"), list):
            return self._invalid(res)
        runs = []
        for run in d["check_runs"]:
            if not isinstance(run, dict) or run.get("head_sha") != head_sha:
                return self._invalid(res, "contrôle ne portant pas le HEAD demandé")
            name, status, conclusion = run.get("name"), run.get("status"), run.get("conclusion")
            if not isinstance(name, str) or status not in _RUN_STATUSES:
                return self._invalid(res)
            if conclusion is not None and not isinstance(conclusion, str):
                return self._invalid(res)
            runs.append((name, status, conclusion))
        return _Ok({"runs": runs, "total_count": d["total_count"]}, res.evidence)

    def _read_pulls(self) -> _Ok | _Fail:
        res = self._get(
            self._url("pulls", query=f"state=open&per_page={MAX_PULLS}&sort=updated&direction=desc"),
            "pull-requests",
        )
        if isinstance(res, _Fail):
            return res
        if not isinstance(res.data, list):
            return self._invalid(res)
        out = []
        for p in res.data:
            # Seuls numéro, titre, draft, head.sha et date sont extraits ; ``body`` est ignoré.
            if not isinstance(p, dict) or not isinstance(p.get("head"), dict):
                return self._invalid(res)
            number, title, draft = p.get("number"), p.get("title"), p.get("draft")
            sha, updated = p["head"].get("sha"), p.get("updated_at")
            if not (_is_int(number) and number > 0 and isinstance(title, str) and isinstance(draft, bool)):
                return self._invalid(res)
            if not is_sha1(sha) or not _is_utc(updated):
                return self._invalid(res)
            out.append({"number": number, "title": title, "draft": draft, "head_sha": sha, "updated_at_utc": updated})
        return _Ok(out, res.evidence)

    def _read_issues(self) -> _Ok | _Fail:
        res = self._get(
            self._url("issues", query=f"state=open&per_page={MAX_ISSUES}&sort=updated&direction=desc"), "issues"
        )
        if isinstance(res, _Fail):
            return res
        if not isinstance(res.data, list):
            return self._invalid(res)
        out = []
        for i in res.data:
            # Seuls numéro, titre et date sont extraits ; ``body`` est ignoré.
            if not isinstance(i, dict):
                return self._invalid(res)
            if "pull_request" in i:
                continue
            number, title, updated = i.get("number"), i.get("title"), i.get("updated_at")
            if not (_is_int(number) and number > 0 and isinstance(title, str) and _is_utc(updated)):
                return self._invalid(res)
            out.append({"number": number, "title": title, "updated_at_utc": updated})
        return _Ok(out, res.evidence)

    def _read_tree(self, head_sha: str) -> _Ok | _Fail:
        if not is_sha1(head_sha):
            return _Fail(Availability.ERROR, Reason.INVALID_INPUT, "SHA du HEAD invalide")
        res = self._get(self._url("git", "trees", head_sha, query="recursive=1"), "tree", head_sha)
        if isinstance(res, _Fail):
            return res
        d = res.data
        if not isinstance(d, dict) or not isinstance(d.get("tree"), list) or not isinstance(d.get("truncated"), bool):
            return self._invalid(res)
        paths = []
        for entry in d["tree"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                return self._invalid(res)
            kind = entry.get("type")
            if kind in ("blob", "tree"):
                paths.append((entry["path"], kind))
        return _Ok({"paths": paths, "truncated": d["truncated"]}, res.evidence)

    def _read_compare(self, base_sha: str, head_sha: str) -> _Ok | _Fail:
        res = self._get(
            self._url("compare", f"{base_sha}...{head_sha}", query=f"per_page={MAX_COMPARE_COMMITS}"),
            f"compare-{base_sha[:12]}-{head_sha[:12]}",
            head_sha,
        )
        if isinstance(res, _Fail):
            return res
        d = res.data
        if not isinstance(d, dict) or d.get("status") not in _COMPARE_STATUSES:
            return self._invalid(res)
        counts = {k: d.get(k) for k in ("ahead_by", "behind_by", "total_commits")}
        if not all(_is_int(v) and v >= 0 for v in counts.values()) or not isinstance(d.get("commits"), list):
            return self._invalid(res)
        commits = []
        for c in d["commits"]:
            # Seuls SHA et première ligne du message sont extraits.
            if not isinstance(c, dict) or not is_sha1(c.get("sha")) or not isinstance(c.get("commit"), dict):
                return self._invalid(res)
            message = c["commit"].get("message")
            if not isinstance(message, str):
                return self._invalid(res)
            commits.append((c["sha"], message))
        return _Ok({"status": d["status"], **counts, "commits": commits}, res.evidence)


def _reject_json_constant(name: str) -> Any:
    raise ValueError(f"constante JSON non finie refusée ({name})")


__all__ = [
    "API_HOST",
    "DEFAULT_REPO",
    "FIXTURE_DIR",
    "TRACKED_ISSUES",
    "FixtureGithubProvider",
    "HttpGithubProvider",
    "Reason",
    "UrllibTransport",
    "is_allowed_api_url",
    "is_safe_ref",
    "is_valid_repo",
    "load_github_fixture",
]
