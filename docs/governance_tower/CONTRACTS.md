# Governance Tower — Contrats de données (GOV-TOWER-00, lot B)

Source : [`governance_tower/contracts.py`](../../governance_tower/contracts.py), schéma `gt-contracts/1`.
Tests : `tests/governance_tower/test_gt_contracts.py`.

## Règles transverses

| Règle | Mise en œuvre |
|---|---|
| UNKNOWN ≠ 0 | `Observation` : seules `AVAILABLE` et `STALE` portent une valeur ; toute autre disponibilité exige `value=None` et une `reason` |
| DENIED ≠ EMPTY | 401/403 → `DENIED` ; une liste vide n'est produite que si la source a réellement répondu vide |
| STALE ≠ CURRENT | `STALE` exige `freshness_age_s` mesuré |
| Pas de preuve, pas de constat | `AVAILABLE` exige ≥ 1 `EvidenceRef` ; `Statement` `OBSERVED` exige des `evidence_ids` présents dans le run |
| Fixture ≠ preuve | `SYNTHETIC` ⇔ locator `fixture:` ; `SYNTHETIC` et `LIVE_READ` jamais mélangés (snapshot, run, instance Sentinel) |
| UTC explicite | `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` ; horodatage observé > collecte + 120 s refusé |
| Fermeture | vocabulaires `Enum` ; `from_dict` refuse les champs inconnus ; chaînes, listes et valeurs JSON bornées (64 Kio) ; NaN/Infinity refusés |
| Aucune autorité | `Finding.status = CANDIDATE_ONLY` ; `MissionProposal.authority = NONE`, `execution = NOT_EXECUTED`, périmètre interdit par défaut non retirable ; `AgentRun` : `SENTINEL-01` / `OBSERVE_ONLY` / `DENIED` immuables |

## Vocabulaires

- `Availability` : `AVAILABLE`, `STALE`, `NOT_AVAILABLE`, `DENIED`, `RATE_LIMITED`, `ERROR`, `UNKNOWN`.
- `Provenance` : `SYNTHETIC`, `LIVE_READ`, `DECLARED_REFERENCE` (référence documentaire, ex. #286).
- `ClaimStatus` : `OBSERVED`, `INFERRED`, `PROPOSED`, `NOT_PROVEN`.
- `DiscrepancyClass` : `ALIGNED`, `EXPECTED_PINNED_RUNTIME`, `POSSIBLE_DRIFT`, `STALE`, `INSUFFICIENT_EVIDENCE`, `VIOLATION_PROVEN` (jamais produit par l'analyse actuelle faute de preuve d'origine).
- `Severity` : `INFO`, `NOTICE`, `WARNING`, `CRITICAL`, toujours accompagnée de `severity_reason`.
- `Domain` : `repository`, `ci`, `pull_requests`, `issues`, `code`, `host_service`, `host_storage`, `host_deployment`, `reference`.

## Objets

| Objet | Rôle | Invariants principaux |
|---|---|---|
| `EvidenceRef` | où, quand, quelle source | locator `https://github.com/`, `https://api.github.com/`, `snapshot:`, `reference:` ou `fixture:` ; SHA-1/SHA-256 validés |
| `Observation` | une mesure qualifiée | voir règles ; `untrusted_content=True` pour tout texte externe |
| `RepositorySnapshot` | dépôt, branche, HEAD, observations | dépôt indisponible ⇒ `head_sha=None` |
| `HostSnapshot` | hôte, observations, SHA déployé | hôte indisponible ⇒ pas de SHA, raison obligatoire |
| `PinnedReference` | epoch/runtime/config gelés déclarés (#286) | preuve `DECLARED_REFERENCE` ; chargée depuis `pinned_references.json` |
| `Discrepancy` | comparaison GitHub ↔ runtime | classes conclusives exigent les deux valeurs et des preuves |
| `Finding` | constat candidat | `CANDIDATE_ONLY` ; `OBSERVED` exige des preuves |
| `MissionProposal` | proposition documentée | aucune autorité, jamais exécutée |
| `SentinelAnswer` | sortie structurée | constats, incertitudes, écarts, constats candidats, propositions, refus, citations non fiables |
| `AgentRun` | trace complète d'une question | preuves citées ⊆ preuves du run ; mode `DEMO` sans `LIVE_READ` et inversement ; `cost=None` (jamais inventé) |

## Fournisseurs

Interfaces dans [`providers/base.py`](../../governance_tower/providers/base.py) :
`GithubReadProvider` (`repository_snapshot`, `locate_code`, `compare_commits`) et
`HostObservationProvider` (`host_snapshot`). Aucune méthode d'écriture n'existe.
Les snapshots hôte réels sont validés par les contrats gouvernés existants
`observability.runtime_service_contract` et `observability.storage_contract`.
