# GOV-TOWER-01 — Inventaire M0, matrice de réutilisation et frontières

Mission : [#461](https://github.com/3a7i3/crypto-ia-terminal/issues/461). Base : `main` @ `191ffce`
(fusion de [#460](https://github.com/3a7i3/crypto-ia-terminal/pull/460), GOV-TOWER-00).
Garde [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) `ACTIVE_BURN_IN_IMMUTABILITY_GUARD`
active : ce document est **source seulement**, il n'autorise aucun déploiement, aucune lecture VPS
réelle ni aucun appel de modèle.

## 1. Principe

GOV-TOWER-01 **étend** Governance Tower ; rien n'est reconstruit. Le paquet reste
`governance_tower/` (stdlib seule), isolé du runtime : ses seules dépendances internes restent
`observability.runtime_service_contract` et `observability.storage_contract`
(vérifié par `tests/governance_tower/test_gt_isolation.py`).

## 2. Matrice EXISTING / REUSE / EXTEND / NEW / OUT-OF-SCOPE

| Élément | Statut | Détail |
|---|---|---|
| `contracts.py` (Availability, EvidenceRef, Observation, AgentRun…) | EXTEND | `Domain.CODE_CONTENT/COVERAGE`, 5 intentions, `Diagnostic`, `DiagnosticCode`, `DiagnosticLevel`, `CodeExcerpt` ; `SentinelAnswer.diagnostics/excerpts` ; `AgentRun` vérifie aussi les preuves citées par ces champs |
| `providers/github.py` (Fixture + HTTP, GET seul, budget) | EXTEND | `read_file`, `issue_detail`, `pull_detail`, `ci_for_sha`, `branch_head`, `budget_status` ; mêmes garde-fous (allowlist d'URL, pas de redirection, budget par question et fenêtre, quota distant persistant) |
| `providers/host.py` (snapshots publiés, Operator API loopback) | EXTEND | `expected_host_id` (HOST_MISMATCH), monotonicité (NON_MONOTONIC), Content-Type, ETag, en-têtes mal formés |
| `redaction.py`, `sentinel/injection.py` | REUSE | expurgation et détection d'instructions appliquées aux nouveaux contenus (fichiers, corps d'issue/PR) |
| `sentinel/policy.py` | EXTEND | intentions détaillées (paramètres extraits de la demande seule), comparaison croisée « même version », refus de relance de CI |
| `sentinel/tools.py` | EXTEND | outils GitHub optionnels enregistrés seulement si le fournisseur les possède |
| `sentinel/analysis.py` | EXTEND | `diagnose()` : diagnostics croisés GitHub × snapshots |
| `sentinel/reasoner.py` (déterministe) | EXTEND | phrases lisibles, extraits, cartographie ; reste le **seul** raisonneur opérationnel |
| `sentinel/llm_adapter.py` | NEW | adaptateur borné, transport hors ligne simulé seul (`GT01_LLM_LIVE = DISABLED`) |
| `coverage.py` | NEW | cartographie déclarée des domaines observables, bornés, non publiés, interdits |
| `server.py` | EXTEND | `/api/status` : raisonneur, état du modèle externe, budget GitHub (lecture seule) |
| `ui/` (panel unique) | EXTEND | cartes de diagnostic, extraits numérotés, bandeau des sources, preuves repliées, ligne de budget ; aucun menu ni bouton nouveau |
| Fixtures SYNTHETIC | EXTEND | `github_rate_limited`, `no_deployment_id`, `partial` ; fichiers, issues, PR, CI par SHA |
| Identité GitHub de Sentinel, GitHub App, PAT | OUT-OF-SCOPE | opération de Mathieu |
| Lecture VPS réelle (GT01-V) | OUT-OF-SCOPE | protocole seulement : [GT01_V_VPS_READ_PROTOCOL.md](GT01_V_VPS_READ_PROTOCOL.md) |
| Modèle externe réel (GT01-I) | OUT-OF-SCOPE | contrat seulement : [GT01_LLM_CONTRACT.md](GT01_LLM_CONTRACT.md) |
| Authentification, exposition réseau (GT01-R) | OUT-OF-SCOPE | loopback seul, inchangé |
| Machine / BabyStart / Bank, écriture, service, worker, cron, systemd | OUT-OF-SCOPE | interdits par le mandat |

## 3. Matrice des sources

La table complète est le code : `governance_tower/coverage.py` (17 domaines), consultable
dans l'interface par « Quels sont tes angles morts ? ». Résumé :

| Visibilité | Domaines |
|---|---|
| OBSERVABLE | dépôt/branche/HEAD ; état systemd de `crypto-advisor.service` ; identité de build publiée ; métadonnées des fichiers de décision |
| OBSERVABLE_BOUNDED | CI d'un SHA (≤ 100 contrôles) ; listes PR/issues (1 page) ; détail d'issue/PR (corps ≤ 3000 car., commentaires non lus) ; fichier admis (≤ 256 Kio, ≤ 200 lignes) ; arbre (chemins) ; compare (≤ 50 titres) |
| NOT_PUBLISHED | hash de configuration runtime ; CPU/mémoire/disque/réseau ; journaux ; autres services/timers/cron |
| FORBIDDEN | ledger PPL, état FIN, positions ; secrets/.env/clés ; shell, checkout runtime, exchange |

« Vue complète » = inventaire honnête des angles morts, jamais un accès root.

## 4. Décomposition et dépendances M0 → M6

```
M0 contrats/inventaire ─┬─ M1 lecteur GitHub ─┐
                        ├─ M2 snapshots hôte ─┼─ M3 diagnostics ─ M5 UI ─ M6 sécurité/E2E/rapport
                        └─ M4 adaptateur LLM ─┘
```

M1, M2 et M4 sont indépendants fonctionnellement mais partagent `contracts.py`,
`sentinel/agent.py` et `sentinel/reasoner.py`. Ils ont donc été intégrés **séquentiellement
par un seul intégrateur sur une seule branche**, sans worktrees parallèles : des branches
séparées auraient produit des conflits sur les mêmes contrats sans gain de délai.

## 5. Propriété des fichiers

| Fichiers | Mission |
|---|---|
| `contracts.py`, `coverage.py` | M0 |
| `providers/github.py`, fixtures `github/*` | M1 |
| `providers/host.py`, fixtures `host/*`, `scenarios.py` | M2 |
| `sentinel/analysis.py`, `sentinel/policy.py`, `sentinel/agent.py`, `sentinel/tools.py`, `sentinel/reasoner.py`, `__main__.py` | M3 |
| `sentinel/llm_adapter.py` | M4 |
| `ui/*`, `server.py`, `scripts/governance_tower/gt01_ui_e2e.mjs` | M5 |
| `tests/governance_tower/test_gt01_*`, `docs/governance_tower/GOV_TOWER_01_*` | M6 |

## 6. Risques

| Risque | Mesure | Reste |
|---|---|---|
| Contenu GitHub hostile (fichier, issue, PR) | texte non fiable, expurgé, cité ; détection d'instructions ; rendu `textContent` | une détection lexicale ne couvre pas toutes les formulations ; elle ne pilote aucun outil |
| Chemin sensible ou traversée | `check_content_path` refuse avant toute requête | allowlist d'extensions à maintenir |
| Réponse GitHub forgée | empreinte Git du blob recalculée, chemin et type vérifiés | ne protège pas contre un dépôt réellement compromis |
| Quota GitHub | budget par question (12) et par heure (40), quota distant mémorisé | aucun |
| Snapshot rejoué ou d'un autre hôte | NON_MONOTONIC, HOST_MISMATCH | `storage` ne publie pas `host_id` |
| Fuite vers un modèle | adaptateur hors ligne seul, faits VPS retenus par défaut | gate GT01-I non ouverte |
| Faux vert | aucun code de santé ; « ACTIVE ≠ HEALTHY » ; vérifications jamais vides | aucun |
