# GT01-G-SMOKE-01 — Banc d'identité GitHub App de Sentinel

Parent : GOV-TOWER-01 (#461). État : `IMPLEMENTED_SOURCE`, `TESTED_LOCAL` (contrat statique),
`NOT_RUN` (aucun test authentifié lancé). Garde #286 active.

## Objet

Prouver que Sentinel lit `3a7i3/crypto-ia-terminal` avec sa propre identité GitHub App
`crypto-ai-sentinel-observer`, et non avec `GITHUB_TOKEN` ni un jeton personnel.

| Élément | Fichier |
|---|---|
| Workflow manuel | `.github/workflows/gt01-g-smoke-sentinel-identity.yml` |
| Vérificateur (stdlib, GET seul) | `scripts/governance_tower/gt01_g_smoke_identity.py` |
| Contrat statique | `tests/governance_tower/test_gt01_g_smoke_workflow.py` |

## Actions épinglées

| Action | SHA | Version | Vérification |
|---|---|---|---|
| `actions/create-github-app-token` | `bcd2ba49218906704ab6c1aa796996da409d3eb1` | v3.2.0 (2026-05-12) | tag léger sur `main` du dépôt officiel, commit de release signé, `client-id` + `permission-*` présents dans `action.yml` |
| `actions/checkout` | `34e114876b0b11c390a56381ad16ebd13914f8d5` | v4.3.1 | tag sur `releases/v4` du dépôt officiel |

v3.3.0 (2026-10-12) existe mais n'avait que cinq jours lors de la préparation ; v3.2.0 est retenue.

## Ce que le run vérifie

| Contrôle | Classe | Source |
|---|---|---|
| slug et installation de l'App | VERIFIED | sorties de l'action, obtenues de GitHub avec la clé privée |
| fiche publique de l'App | VERIFIED | `GET /apps/crypto-ai-sentinel-observer` |
| permissions configurées de l'App | DECLARED | même réponse ; toute permission ≠ `read` fait échouer le run |
| périmètre de l'installation = ce seul dépôt | VERIFIED | `GET /installation/repositories` |
| permissions demandées pour le jeton | DECLARED | entrées `permission-*` du workflow |
| refus d'écriture | NOT_VERIFIABLE | aucune écriture n'est tentée |
| HEAD exact de `main` | VERIFIED | `GET /repos/…/git/ref/heads/main` |
| empreinte de `CLAUDE.md` au HEAD | VERIFIED | blob SHA-1 recalculé = SHA GitHub ; SHA-256 publié ; comparaison au checkout ; SHA-256 attendu optionnel |
| issue #461, PR #462 | VERIFIED | `GET /repos/…/issues/461`, `GET /repos/…/pulls/462` |
| check-runs au SHA exact de la PR | VERIFIED | `GET /repos/…/commits/{sha}/check-runs` (paginé) |
| statuts de commit | NOT_VERIFIABLE | permission « Commit statuses » non demandée |

Le client refuse tout chemin hors d'une liste fermée et n'émet que des GET. Le rapport
(JSON + Markdown) va dans le résumé du job et le journal ; il est refusé s'il contient le
jeton ou un motif de clé privée. Aucun artifact n'est publié.

Seul appel non-GET : le post-step de l'action officielle révoque le jeton
(`DELETE /installation/token`), ce qui n'affecte que ce jeton.

## À configurer par l'opérateur (non fait par Claude)

1. *Settings → Environments → New environment* : `sentinel-github-identity-smoke`.
2. *Required reviewers* : ajouter `3a7i3` (approbation manuelle avant chaque run) ;
   cocher *Prevent self-review* seulement si un autre réviseur existe.
3. *Deployment branches and tags* : *Selected branches* → `main` uniquement.
4. Variable d'environnement `SENTINEL_APP_CLIENT_ID` = Client ID de l'App (non secret).
5. Secret d'environnement `SENTINEL_APP_PRIVATE_KEY` = clé privée PEM de l'App.
   Ne pas créer de secret au niveau du dépôt ou de l'organisation.

## Lancement (après revue et fusion, sur décision de l'opérateur)

GitHub n'expose un `workflow_dispatch` que si le fichier est sur la branche par défaut, et
le job est gardé par `github.ref == 'refs/heads/main'`. Lancement : *Actions →
GT01-G-SMOKE Sentinel GitHub identity → Run workflow* sur `main`, puis approbation de
l'environnement. Verdict attendu du run : `GT01_G_SMOKE_IDENTITY_VERIFIED`.
