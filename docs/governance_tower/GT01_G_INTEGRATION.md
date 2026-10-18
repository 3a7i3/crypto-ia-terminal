# GT01-G-INTEGRATION-01 — Backend Sentinel avec l'identité GitHub App

Parent : GOV-TOWER-01 (#461). État : `IMPLEMENTED_SOURCE`, `TESTED_LOCAL` (transport factice,
contrat statique), `NOT_RUN` (aucune exécution authentifiée). Garde #286 active ; #315 et
#445 n'accordent aucune autorité.

## Écart corrigé

`HttpGithubProvider` (PR #462) envoyait des GET anonymes et ajoutait `GT_GITHUB_TOKEN` s'il
était présent et bien formé. Ce mode ne prouve pas que le jeton vient de l'App Sentinel, et
un jeton absent ou mal formé donnait une requête sans `Authorization`. Il reste disponible
sous le nom `OPTIONAL_TOKEN` (défaut), déclaré « non attesté ».

## Mode strict `APP_INSTALLATION`

| Règle | Effet si non satisfaite |
|---|---|
| `GT_SENTINEL_INSTALLATION_TOKEN` = jeton d'installation (`ghs_…`) | `AUTH_MISSING`, aucune requête |
| `GT_SENTINEL_APP_SLUG` = `crypto-ai-sentinel-observer` | `AUTH_IDENTITY_MISMATCH`, aucune requête |
| `GET /installation/repositories?per_page=100` : `total_count` entier JSON strict égal à 1 (ni booléen, ni `1.0`, ni `"1"`), seul dépôt `3a7i3/crypto-ia-terminal` | `AUTH_UNATTESTED`, aucune lecture ; pas de relance avec le même jeton |
| attestation impossible : `NETWORK`, `TIMEOUT`, `TRANSPORT_ERROR`, `SERVER_ERROR` (5xx) | `NOT_AVAILABLE` avec la raison d'origine, aucune lecture, **non mis en cache** : nouvel essai à la question suivante, dans les budgets (absence de preuve ≠ refus, R1) |
| chaque requête porte `Authorization` | jeton disparu en cours de route : `AUTH_MISSING`, rien n'est émis |
| `GT_GITHUB_TOKEN` | jamais lu en mode strict (aucun repli) |
| 401 sur une lecture | attestation à refaire au prochain appel |

L'attestation est liée à l'empreinte SHA-256 du jeton, gardée en mémoire ; ni le jeton ni
son empreinte n'apparaissent dans une sortie. `/installation/repositories` est la seule URL
admise hors `/repos/`, comparée exactement. Chaque `EvidenceRef` porte `auth APP_INSTALLATION`.

**Limite.** Un jeton d'installation seul ne révèle pas, en GET, quelle App l'a émis
(`GITHUB_TOKEN` est aussi un jeton `ghs_` d'installation). L'identité de l'App est donc
`DECLARED` par l'étape qui a créé le jeton (sorties `app-slug` / `installation-id` de
`actions/create-github-app-token`, obtenues avec la clé privée) et par le câblage du
workflow, vérifié par test statique. Le périmètre d'installation est `VERIFIED`.

## Chaîne d'exécution

| Élément | Fichier |
|---|---|
| Workflow manuel | `.github/workflows/gt01-g-integration-sentinel-backend.yml` |
| Runner borné | `scripts/governance_tower/gt01_g_integration_run.py` |
| Tests | `tests/governance_tower/test_gt01_g_app_auth.py`, `test_gt01_g_integration.py` |

`environnement approuvé → create-github-app-token (v3.2.0, épinglée) → jeton temporaire →
backend du checkout main (github.sha) en mode strict → question examine_repository → GET
allowlistés (≤ 12) → EvidenceRef / AgentRun → rapport JSON + Markdown ≤ 64 Kio → révocation
par le post-step de l'action`.

Piège de bootstrap : le job est gardé par `github.ref == 'refs/heads/main'` et n'extrait
que `github.sha` ; aucun autre ref, aucune installation de paquet, aucun `inputs`. Le
workflow n'existe sur `main` qu'après fusion : le code d'une PR non fusionnée ne reçoit
jamais le jeton ni la clé.

## Contrôles du rapport

| Contrôle | Classe |
|---|---|
| backend importé depuis le checkout, `GITHUB_SHA` valide | VERIFIED |
| slug et installation de l'App | DECLARED |
| périmètre d'installation = ce seul dépôt | VERIFIED |
| AgentRun `LIVE_READ`, `OBSERVE_ONLY`, autorité `DENIED`, aucun refus | VERIFIED |
| toutes les preuves GitHub : `LIVE_READ`, HTTP 200, `auth APP_INSTALLATION` | VERIFIED |
| HEAD de main observé = checkout (sinon `CHECKOUT_DIVERGES_FROM_MAIN`) | VERIFIED |
| requêtes ≤ budget par question, aucun outil en échec | VERIFIED |
| observation hôte | NOT_VERIFIABLE (aucun VPS dans ce job) |
| révocation du jeton | NOT_VERIFIABLE (post-step, après le script) |

Le rapport est refusé, jamais tronqué, s'il contient le jeton, un motif de jeton GitHub ou
de clé privée, ou dépasse 64 Kio. Verdict attendu : `GT01_G_INTEGRATION_VERIFIED`.

## Environnement

Le job réutilise l'environnement protégé existant `sentinel-github-identity-smoke` (même
variable `SENTINEL_APP_CLIENT_ID`, même secret `SENTINEL_APP_PRIVATE_KEY`), sans le
modifier. Sa configuration actuelle (réviseurs, branches) n'a pas été relue. Un
environnement dédié est possible ; il demanderait une configuration par l'opérateur.

## Lancement (décision de l'opérateur, après revue et fusion)

*Actions → GT01-G-INTEGRATION Sentinel backend (GitHub App) → Run workflow* sur `main`,
puis approbation de l'environnement. Un run réussi prouve la chaîne pour ce SHA à cet
instant ; il ne prouve ni déploiement de Governance Tower, ni accès VPS, ni certification.
