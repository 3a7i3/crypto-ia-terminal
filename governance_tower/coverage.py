"""Cartographie déclarée de la couverture de Sentinel (GOV-TOWER-01 M0/M2).

« Vue complète » signifie ici un inventaire honnête des domaines observables et
de leurs angles morts, jamais un accès root ni des données non admises. Cette
table est **déclarative** (revue humaine, versionnée) : elle décrit ce que les
fournisseurs du code savent lire, pas ce qui a été lu. Une ligne ``OBSERVABLE``
ne prouve aucune lecture ; l'état réel d'une source vient de ``SourceStatus``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from governance_tower.contracts import ContractError, check_text

COVERAGE_SCHEMA = "gt-coverage/1"
COVERAGE_LOCATOR = "reference:gt-coverage-matrix/1"


class Visibility(str, Enum):
    OBSERVABLE = "OBSERVABLE"  # lu par un fournisseur admis, avec ses limites
    OBSERVABLE_BOUNDED = "OBSERVABLE_BOUNDED"  # lu partiellement (page, extrait, plafond)
    NOT_PUBLISHED = "NOT_PUBLISHED"  # aucune source gouvernée ne le publie : angle mort
    FORBIDDEN = "FORBIDDEN"  # jamais lu par conception (secret, données d'autorité, runtime brut)


@dataclass(frozen=True)
class CoverageEntry:
    domain: str
    source: str  # GITHUB | HOST | —
    visibility: Visibility
    provider: str
    endpoint: str
    fields: str
    freshness: str
    limits: str

    def __post_init__(self) -> None:
        if not isinstance(self.visibility, Visibility):
            raise ContractError("CoverageEntry: visibilité hors vocabulaire")
        for name in ("domain", "source", "provider", "endpoint", "fields", "freshness", "limits"):
            check_text(getattr(self, name), name, 300)


_G, _H, _N = "GITHUB", "HOST", "—"

COVERAGE: tuple[CoverageEntry, ...] = (
    CoverageEntry("Dépôt, branche par défaut, HEAD", _G, Visibility.OBSERVABLE, "HttpGithubProvider",
                  "GET /repos/{repo}, /branches/{branch}", "branche, SHA, date, 1re ligne du message",
                  "à la question ; âge affiché, STALE > 300 s", "titre non fiable ; présent dans main ≠ déployé"),
    CoverageEntry("CI d'un SHA exact", _G, Visibility.OBSERVABLE_BOUNDED, "HttpGithubProvider",
                  "GET /commits/{sha}/check-runs?per_page=100", "nom, statut, conclusion",
                  "à la question", "> 100 contrôles ⇒ UNKNOWN ; statuts « commit status » non lus"),
    CoverageEntry("PR et issues ouvertes (liste)", _G, Visibility.OBSERVABLE_BOUNDED, "HttpGithubProvider",
                  "GET /pulls, /issues (1 page)", "numéro, titre, draft, SHA, date",
                  "à la question", "une page (30 PR, 50 issues) ; absence de la page ≠ fermée"),
    CoverageEntry("Issue ou PR nommée (détail)", _G, Visibility.OBSERVABLE_BOUNDED, "HttpGithubProvider",
                  "GET /issues/{n}, /pulls/{n}", "état, étiquettes, dates, SHA, corps ≤ 3000 car.",
                  "à la question", "corps non fiable et expurgé ; commentaires non lus"),
    CoverageEntry("Contenu d'un fichier admis", _G, Visibility.OBSERVABLE_BOUNDED, "HttpGithubProvider",
                  "GET /contents/{path}?ref={sha}", "extrait ≤ 200 lignes, empreinte Git vérifiée",
                  "immuable (SHA)", "texte allowlisté ≤ 256 Kio ; chemins sensibles et clés privées refusés"),
    CoverageEntry("Arborescence (chemins)", _G, Visibility.OBSERVABLE_BOUNDED, "HttpGithubProvider",
                  "GET /git/trees/{sha}?recursive=1", "chemins seulement", "immuable (SHA)",
                  "arbre tronqué par GitHub signalé ; 50 chemins listés"),
    CoverageEntry("Commits entre deux SHA", _G, Visibility.OBSERVABLE_BOUNDED, "HttpGithubProvider",
                  "GET /compare/{base}...{head}", "statut, ahead/behind, total, 50 titres",
                  "à la question", "liste partielle signalée ; réponse > 1 Mio ⇒ NOT_COMPARABLE"),
    CoverageEntry("État systemd de crypto-advisor.service", _H, Visibility.OBSERVABLE, "OperatorApiHostProvider",
                  "GET /api/operator/v1/runtime-service", "load/active/sub state, NRestarts, démarrage",
                  "publicateur du snapshot ; STALE > 90 s", "ACTIVE ≠ HEALTHY ; aucun PID exposé"),
    CoverageEntry("Identité de build déployée", _H, Visibility.OBSERVABLE, "OperatorApiHostProvider",
                  "GET /api/operator/v1/runtime-service (deployment)", "SHA source, empreinte d'artefact",
                  "publicateur du snapshot", "absente ⇒ NO_DEPLOYED_BUILD_ID ; déclarée par le publicateur"),
    CoverageEntry("Fichiers de décision (métadonnées)", _H, Visibility.OBSERVABLE, "OperatorApiHostProvider",
                  "GET /api/operator/v1/storage", "nombre, octets, dernière modification",
                  "publicateur du snapshot ; STALE > 90 s", "aucun contenu lu ; pas de host_id publié"),
    CoverageEntry("Hash de configuration runtime", _H, Visibility.NOT_PUBLISHED, "—", "—", "—", "—",
                  "référence #286 déclarée seulement : non vérifiable par Sentinel"),
    CoverageEntry("CPU, mémoire, disque, réseau", _H, Visibility.NOT_PUBLISHED, "—", "—", "—", "—",
                  "aucun snapshot gouverné ne les publie"),
    CoverageEntry("Journaux (journald, applicatifs)", _H, Visibility.NOT_PUBLISHED, "—", "—", "—", "—",
                  "aucun publicateur gouverné de journaux"),
    CoverageEntry("Autres services, timers, cron", _H, Visibility.NOT_PUBLISHED, "—", "—", "—", "—",
                  "seul crypto-advisor.service est publié"),
    CoverageEntry("Ledger PPL, état FIN, positions", _N, Visibility.FORBIDDEN, "—", "—", "—", "—",
                  "autorités PPL/FIN : hors périmètre de Sentinel"),
    CoverageEntry("Secrets, .env, clés, jetons", _N, Visibility.FORBIDDEN, "—", "—", "—", "—",
                  "jamais lus, jamais cités, jamais transmis"),
    CoverageEntry("Shell, checkout runtime, exchange", _N, Visibility.FORBIDDEN, "—", "—", "—", "—",
                  "aucun outil d'action ; garde #286 active"),
)


def coverage_rows() -> list[dict[str, str]]:
    return [
        {
            "domain": e.domain,
            "source": e.source,
            "visibility": e.visibility.value,
            "provider": e.provider,
            "endpoint": e.endpoint,
            "fields": e.fields,
            "freshness": e.freshness,
            "limits": e.limits,
        }
        for e in COVERAGE
    ]


__all__ = ["COVERAGE", "COVERAGE_LOCATOR", "COVERAGE_SCHEMA", "CoverageEntry", "Visibility", "coverage_rows"]
