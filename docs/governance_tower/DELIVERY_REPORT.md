# Governance Tower — finalisation source après reprise (#459 / #460)

État du 2026-10-16. Reprise par Claude Code sur mandat de Mathieu, à partir du HEAD distant
`31d8295086677f1d471bce69b1f10f4adf450ac1` (revue Codex ci-dessous), vérifié identique au checkout local,
sans commit local non publié, sans worktree ni stash. Auto-revue de l'auteur, **pas une revue indépendante**.
Périmètre : `governance_tower/`, `tests/governance_tower/`, `docs/governance_tower/` ; aucun autre fichier
modifié. Garde #286 relue ACTIVE ; aucun accès VPS, déploiement, restart, écriture exchange ni fusion.

## Matrice problème → reproduction → correction → preuve

| # | Problème au HEAD 31d8295 | Reproduction | Correction minimale | Preuve |
|---|---|---|---|---|
| M1 | Budget GitHub compté sur la vie de l'instance (`_sent` ≥ 40 ⇒ refus définitif) ; `_halt` remis à zéro à chaque sous-méthode, donc un `429` n'empêchait pas la question suivante de réémettre | Sentinel + `HttpGithubProvider` (transport factice) : 8 questions, puis 2 h plus tard question 9 → `NOT_AVAILABLE` ; `429 Retry-After: 120` puis nouvelle question au même instant → 2 GET envoyés | budget **par question** (12 par défaut, rouvert seulement par `begin_investigation()` appelé par Sentinel, jamais par une sous-méthode), plafond de service glissant (40 GET / 3 600 s), blocage distant mémorisé (`Retry-After`, sinon `X-RateLimit-Reset`, sinon 60 s ; borné à 1 h) et persistant entre questions | même scénario après correction : question 9 → `AVAILABLE` ; 1 seul GET pendant le blocage ; 9 tests dédiés (`test_gt_github_provider.py`, section Budget) |
| M2 | `source_status()` renvoyait le dernier état sans âge ; un `AVAILABLE` ancien restait « Disponible » ; la bannière n'était relue qu'au chargement | horloge avancée de 300 s : statut inchangé | `SourceStatus.age_s` (contrat : fini, ≥ 0, exige `collected_at_utc`) ; `AVAILABLE` > 300 s ⇒ `STALE` « dernier état connu, périmé » ; échecs conservés tels quels ; jamais consultée ⇒ `UNKNOWN` sans âge ; bannière « consulté il y a … » et relecture GET de `/api/status` toutes les 60 s (aucune consultation de source) | `test_source_status_carries_age_and_turns_stale`, `test_failed_source_keeps_its_state_and_never_becomes_available`, `test_source_status_contract_rejects_unmeasured_or_invalid_age`, `test_status_exposes_source_age_and_audit_state` |
| M3 | `AuditLog.append()` → `False` (plafond) ignoré ; `OSError` (cible devenue lien) remontait en 500 sans réponse | `max_bytes=10` : run sans aucune mention ; lien symbolique : exception | `Sentinel._record` renvoie le run avec l'incertitude « ce run n'a pas été journalisé » (`AUDIT_CAP_REACHED` / `AUDIT_WRITE_ERROR`), refus compris ; état `audit` dans `/api/status` et la ligne de mode | 4 tests (`test_audit_*` dans `test_gt_sentinel.py`) ; aucune écriture hors cible |
| M4 | `/sample_run.json` non servi alors que `#apercu` le demande (404) ; l'aperçu, une fois servi, remplaçait l'état réel des sources dans la bannière | GET → 404 ; navigateur : bannière remplie par les sources de l'exemple | route statique fixe (`application/json`, mêmes en-têtes et CSP, aucune source consultée) ; l'aperçu ne met plus à jour la bannière ; exemple enrichi de `age_s` et toujours conforme au contrat | `test_sample_run_preview_is_served_as_synthetic_json`, `test_ui_preview_url_matches_a_served_route`, `test_preview_never_overwrites_the_source_banner`, aller-retour de contrat |

Conséquence visible assumée : en démo, la fixture hôte est datée de 12:00Z ; la bannière l'affiche donc
`STALE` (« consulté il y a … h »), ce qui est exact pour une donnée SYNTHETIC figée.

## Tests exécutés (2026-10-16, checkout local, Python 3.11.17, pytest 9.1.1, ruff 0.15.8, node 22)

- Nouveaux tests contre le code de 31d8295 (worktree séparé) : 14 échecs attendus + module Sentinel
  non importable (symboles absents) ; contre le code corrigé : tous verts.
- `pytest tests/governance_tower` en **root** : 388 passed, 1 failed —
  `test_snapshot_permission_denial_is_not_a_missing_source` (test Codex, `chmod 0` sans effet pour root) ;
  échec identique au HEAD 31d8295, donc préexistant et propre à l'environnement.
- Même suite en utilisateur **non privilégié** (`nobody`, Python 3.13.16, copie du paquet, conftest racine
  du dépôt écarté car il importe `cold_start`, hors périmètre) : **389 passed**.
- `ruff check --select E,F,W --ignore E501,E402` : PASS ; `ruff_baseline_gate.py check` : 0 nouvelle
  violation ; `node --check app.js` : PASS ; `git diff --check` : PASS.
- Navigateur (Chromium 1194, serveur local, scénario nominal, `#apercu`) : aperçu rendu, aucune réponse
  HTTP ≥ 400 observée par la page, bannière = état réel avec âge ; une erreur console 404 restante
  (favicon implicite, déjà notée).
- Suite du dépôt hors Governance Tower : SUITE_COMPLETE_PLACEHOLDER

La CI GitHub au HEAD exact de #460 fait foi ; son verdict est consigné dans la PR.

## Verdicts inchangés

Déployé = NON ; autorité opérationnelle = AUCUNE ; agent non activé ; aucune fusion. Les preuves réelles
GitHub/VPS de la revue Codex ci-dessous ne sont ni rejouées ni étendues par cette passe.

---

# Governance Tower — revue indépendante et démonstration bornée (#459 / #460)

État du 2026-10-16. Revue Codex du HEAD entrant `7d28820c7d6ac81dd23164637d660b6017db72e2`,
base `ab84ba4eb370b3adbefb43fb7d651dd0ff031ecd`. Le HEAD final exact et sa CI sont consignés dans
la synthèse courante de [#460](https://github.com/3a7i3/crypto-ia-terminal/pull/460).
Checkout local isolé, aucun checkout de production modifié. Branche distante revérifiée inchangée
avant correction ; aucune autre PR Governance Tower, commentaire, revue ou thread de #460 retourné.
Les instructions CLAUDE/DEVELOPER_ENTRYPOINT et les contrats #445, #447, #315 ont été examinés.

## Revue et corrections confirmées

| Fichier / mécanisme initial | Reproduction et impact | Correction minimale / régression |
|---|---|---|
| `sentinel/policy.py` : aucune règle pour corriger/réparer | « Corrige le service Advisor » → EXAMINE_HOST, outils de lecture appelés au lieu d'un refus ; aucun outil mutateur n'existait | refus CORRECTION_DENIED avant outil, y compris « Peux-tu corriger… » ; conservation de « Ne corrige rien » et des propositions |
| `providers/host.py` : HTTP 401/403/429 et permissions fichier confondus avec ERROR | transport 403 → ERROR, perte du diagnostic d'accès | DENIED / RATE_LIMITED distincts ; refus fichier réel local et succès partiel Stockage testés |
| `providers/host.py` : O_NOFOLLOW sur dernier composant seulement | `alias/snapshots` avec alias symlink vers un répertoire réel → lecture AVAILABLE hors chemin attendu | ouverture de chaque composant par dir_fd + O_NOFOLLOW ; symlink parent refusé |
| `redaction.py` : troncature avant rédaction | 189 caractères + espace + faux jeton `ghp_` de 36 caractères, limite 210 → fragment visible non rédigé | rédaction avant troncature ; même ordre dans la normalisation des questions |
| `providers/host.py` : evidence_ref externe recopiée brute | référence de déploiement portant un faux jeton, valide pour le contrat, exposée dans la réponse | rédaction de cette référence ; host_id également rédigé |
| `providers/github.py` : skipped/neutral incrémentaient succeeded | deux checks ignoré/neutre → deux réussites, SUCCESS | compteurs séparés ; aucun succès exécuté → NONE |
| `sentinel/policy.py` : « stockage » absent des intentions | question Stockage → HELP sans lecture | routage EXAMINE_HOST, régression dédiée |
| `providers/host.py` : dates de publication et identité hôte perdues dans la projection | réponse Service/Stockage sans generated_at_utc, identité seulement générique | restituer host_id expurgé et generated/observed, sans PID ni invocation complète |

Minimisation facultative retenue : `sentinel/audit.py` ne conserve plus d'extrait de question ; outils,
états, dates, refus et nombre de preuves suffisent à l'audit. Aucun contenu externe ajouté à ce journal.

La revue du code confirme la table fermée de quatre outils de lecture, le plan déterministe choisi
avant lecture des sources, les validations de paramètres par fournisseurs, l'absence de shell et de
méthode HTTP mutatrice. GitHub : destination api.github.com, redirections refusées, requêtes/corps
bornés, CI contrôlée au SHA demandé, absence et pagination explicites. Snapshots : contrats existants,
UTC/futur (tolérance 120 s), âge et erreurs qualifiés. Référence #286 déclarative, jamais transformée
en observation. EXPECTED_PINNED_RUNTIME reste un écart attendu. UI : loopback, Host/Origin/CSRF,
CSP et textContent ; aucune nouvelle exposition. L'absence de modèle/outils mutateurs, et non les
heuristiques de détection d'injection, porte la frontière d'exécution.

## Tests effectivement exécutés

Python 3.12.14, venv local séparé, pytest 9.1.1, plugins automatiques désactivés et environnement
assaini (`env -i`, PATH Python/Node explicite, HOME temporaire, PYTHONPATH du checkout).

- HEAD entrant : première passe 352 passed / 1 skipped (Node omis du PATH assaini) ; reproduction
  avec Node dans le PATH, dans un second worktree au HEAD exact : **353 passed**, zéro skipped.
- Après corrections : **368 passed**, zéro skipped ; un avertissement de configuration
  `asyncio_mode` car pytest-asyncio n'est pas installé dans ce venv stdlib.
- Ruff 0.15.8, sélection CI E/F/W : PASS ; baseline du dépôt : **0 nouvelle violation**.
- `node --check governance_tower/ui/app.js` : PASS ; `git diff --check` : PASS.
- Pas de pytest sur le VPS. La suite complète du dépôt et les captures navigateur de l'auteur
  ne sont pas revendiquées comme reproduites ici. Les deux contrats partagés sont inchangés.

## GitHub réel — connecteur Governance Tower

`HttpGithubProvider` avec son transport urllib réel, sans fixture ni jeton demandé.
Deux invocations bornées : budget 5 puis 6 requêtes, timeout d'inactivité 5 s par requête,
corps au plus 1 048 576 + 1 octets de détection ; **11 GET envoyés au total**.

Première question : « Quel est le dernier commit du dépôt GitHub et son état CI ? »
Collecte 20:02:16.633617Z, fin 20:02:19.203474Z : dépôt `3a7i3/crypto-ia-terminal`, branche main,
HEAD `ab84ba4eb370b3adbefb43fb7d651dd0ff031ecd`, commit daté 18:55:09Z ; CI de ce SHA :
24 checks terminés/success. Preuves : `/repos/3a7i3/crypto-ia-terminal`, `/branches/main`,
`/commits/<SHA>/check-runs?per_page=100`, `/pulls?state=open&per_page=30&sort=updated&direction=desc`,
`/issues?state=open&per_page=50&sort=updated&direction=desc` sur https://api.github.com.
Trois PR ouvertes et trente issues hors PR retenues dans la page. Une seule page demandée de chaque
liste ; couverture bornée, pas un inventaire certifié exhaustif. Corps, commentaires et code des
fichiers non analysés par ce connecteur. La recherche de code ne fournit que des chemins.

Seconde invocation : 20:04:16.975786Z–20:04:20.818689Z, même main observé, six GET.
La comparaison `116634be0d3c015cce1cfa58be7da7255414fbfd...ab84ba4eb370b3adbefb43fb7d651dd0ff031ecd`
avec per_page=50 a reçu HTTP 200 mais dépasse 1 Mio : **ERROR / OUTPUT_LIMIT**, aucun décompte
ni liste partielle inventés. Le classement runtime ne dépend pas de cette réponse refusée.
Cette CI de main est distincte de la CI de la PR #460.

## VPS réel — transport direct existant, puis copie locale des projections

Deux GET réels, ponctuels, via Desktop Commander existant sous `chatgpt-ro` sur `crypto-advisor-2`.
Budget strict : exactement deux requêtes, timeout 5 s, 65 537 octets de détection par réponse,
redirections refusées, aucun cookie/auth ajouté. Aucun collector, publisher, daemon ou fichier créé
sur le VPS. Aucun fichier decision_packets ouvert. Le répertoire privé n'a pas été ouvert ni ses
permissions changées. Le source API actif staging-src est refusé au compte : refus conservé.
Routes confirmées dans la release lisible `operator/current/observability/operator_api/app.py`
(lignes 132 et 483) ; port loopback 8090 confirmé par les seuls ExecStart de l'unité/drop-in existants,
sans lecture EnvironmentFile ni environnement du processus. Cela ne certifie pas l'identité de build
API ou Advisor. Aucun sudo, restart ou deploy exécuté.

| | Service | Stockage |
|---|---|---|
| Route | GET http://127.0.0.1:8090/api/operator/v1/runtime-service | GET http://127.0.0.1:8090/api/operator/v1/storage |
| Collecte UTC | 2026-10-16T20:02:31.079468Z | 2026-10-16T20:02:31.087417Z |
| generated = observed UTC | 2026-10-16T20:02:13.833027Z | 2026-10-16T20:02:13.683945Z |
| HTTP / taille | 200 / 800 octets | 200 / 652 octets |
| Fraîcheur à la lecture | FRESH / 17.252432823181152 s | FRESH / 17.405173778533936 s |
| Contrat | RuntimeServiceSnapshot 1.0.0 / HOST_SYSTEMD_OBSERVATION | StorageSnapshot 1.0.0 / FILESYSTEM_METADATA_OBSERVATION |
| Valeur | crypto-advisor.service, loaded / active / running, NRestarts=0 | PRESENT, 8 fichiers correspondants, 365282643 octets |
| SHA-256 réponse HTTP | 3b97ee1f6458f1076f3a779e6b78b9b5fc581c340427998c191cea327120b4ae | f0ad2ac2ea8ce6ba165f1692523818d5737659ac915960796383d2db64aff12a |

Les deux projections ont ensuite été copiées dans le workspace local, sans les deux champs de transport
(snapshot_age_s / freshness_classification), pour lecture par `SnapshotDirectoryHostProvider` et
validation par les contrats existants. Ce sont des **copies des projections HTTP réellement lues**,
ni fixtures ni copies directes des fichiers privés. Les empreintes ci-dessus portent les réponses HTTP
originales, pas les fichiers dérivés. À 20:04:20Z les copies sont honnêtement STALE (âge ~127 s).
Questions locales : « Quel est l’état publié du service Advisor ? », « Quel est le stockage publié ? » :
les deux réponses Sentinel citent les dates et les valeurs ci-dessus avec PÉRIMÉ.

Cette méthode démontre l'accès réel aux deux publications et leur analyse locale ; elle **ne démontre
pas** une connexion réseau VPS depuis `OperatorApiHostProvider` dans Governance Tower. Son transport
distant reste NOT_PROVEN ; aucun tunnel ou relais supplémentaire créé. Le label de provenance
LIVE_READ des copies indique l'origine réelle, pas une lecture courante du VPS.

## Comparaison, refus et verdict

GitHub observé à 20:04:16Z et snapshots VPS collectés à 20:02:31Z : instants différents explicitement
conservés. Référence gelée déclarée : runtime `116634be0d3c015cce1cfa58be7da7255414fbfd`, epoch
BURN-IN-EPOCH-01-20260926T064144Z, état documentaire du 2026-10-05. Snapshot runtime-service :
**deployment NOT_AVAILABLE / NO_EVIDENCE**, SHA et empreinte d'artefact absents.
Réponse Sentinel : **INSUFFICIENT_EVIDENCE**, sans inventer identité, alignement ni dérive.
Le frontend 8ff089b rapporté activé par Mathieu ne donne pas l'identité du build Advisor et n'installe pas GT.
Service active/running ≠ santé du cycle Advisor ; volume de fichiers ≠ nombre de packets ou espace libre.

« Redémarre Advisor » → SERVICE_CONTROL_DENIED ; « Corrige le service Advisor » → CORRECTION_DENIED.
Deux runs locaux, zéro appel d'outil, aucune tentative d'action sur l'hôte. Aucun outil mutateur disponible.

Risques non démontrés / limites : filtrage des secrets et intentions heuristique, formats inconnus non
garantis ; hôte HTTPS choisi explicitement par l'opérateur (pas un registre d'admission opérationnel) ;
timeouts réseau d'inactivité, pas deadline globale ; serveur stdlib local sans authentification ni
qualification de résistance aux clients lents. Aucune validation navigateur indépendante nouvelle.
Raisonneur déterministe : routage et projection de faits, pas enquête générale, lecture de corps/code,
certification ou investigation LAB. Ces limites interdisent une prétention de « vue complète » ou de
service exposé. L3 historique, U8/L4 non certifiés, #397 HOLD, #286 ACTIVE ; Gate O non activée.
Les réserves historiques G3–G5 restent intactes : publication préalable G3 runtime-service non établie,
au moins quatre starts storage malgré deux blocs rapportés, durée/consommation G3 non établies.
Preuves historiques : #286 commentaires 6221709127 et 6222207001 ; aucune régularisation rétroactive.

- PRÊT POUR REVUE SOURCE (prototype local borné ; état de CI final séparé dans #460).
- GITHUB RÉEL DÉMONTRÉ.
- VPS RÉEL DÉMONTRÉ **par transport direct**, analyse **par copie locale** ; connecteur distant GT NON DÉMONTRÉ.
- DÉPLOYÉ = NON ; AUTORITÉ OPÉRATIONNELLE = AUCUNE.

Prochaine décision : Mathieu examine la correction source et accepte ou refuse ce périmètre de preuve
borné dans #460. Aucune décision de fusion ou d'installation n'est exécutée dans cette mission.

---

# Livraison initiale de l'auteur — historique, antérieure à la revue ci-dessus

# Governance Tower — Rapport de livraison GOV-TOWER-00 (lot I)

Mission [#459](https://github.com/3a7i3/crypto-ia-terminal/issues/459) · Roadmap #285 · Garde #286 **ACTIVE** (relue le 2026-10-16)
Base : `main@ab84ba4eb370b3adbefb43fb7d651dd0ff031ecd` · Branche : `claude/governance-tower-architecture-x6i7ui`

## 1. Résumé

**Ce qui fonctionne vraiment** : une application locale autonome (`python -m governance_tower serve`), une page
et un panel conversationnel, l'agent SENTINEL-01 en capacité `OBSERVE_ONLY`, des réponses structurées et
sourcées (constats, preuves, incertitudes, écarts, propositions non exécutées, refus, contenu non fiable cité),
sur six scénarios SYNTHETIC reproductibles.

**Ce qui reste faux ou non branché** : aucune lecture réelle n'a été exercée. Les connecteurs GitHub et VPS
réels existent en opt-in mais ne sont testés qu'avec des transports simulés. Le raisonneur LLM n'existe pas
(adaptateur Claude API désactivé par conception). Pas d'authentification : loopback uniquement.

## 2. Avant / après

| | Avant | Après |
|---|---|---|
| Source | aucun paquet Governance Tower | `governance_tower/`, `tests/governance_tower/`, `docs/governance_tower/` (fichiers ajoutés uniquement) |
| État | — | `IMPLEMENTED_SOURCE`, `TESTED_LOCAL`, `NOT_DEPLOYED` |
| Fichiers existants modifiés | — | **aucun** (`git diff --stat ab84ba4 -- . ':!governance_tower' ':!tests/governance_tower' ':!docs/governance_tower'` vide) |

## 3. Fichiers

| Chemin | Rôle |
|---|---|
| `governance_tower/contracts.py`, `redaction.py`, `references.py`, `pinned_references.json` | GT-M1 contrats, rédaction, référence gelée #286 déclarée |
| `governance_tower/providers/base.py`, `github.py`, `fixtures/github/` | GT-M2 lecture GitHub (fixture + HTTP GET opt-in) |
| `governance_tower/providers/host.py`, `fixtures/host/` | GT-M3 observation hôte (non configuré, fixture, dossier de snapshots, Operator API GET) |
| `governance_tower/sentinel/` (`policy`, `tools`, `analysis`, `reasoner`, `injection`, `audit`, `agent`) | GT-M4 SENTINEL-01 |
| `governance_tower/server.py`, `ui/`, `__main__.py`, `scenarios.py` | GT-M5 serveur loopback, interface, CLI, scénarios |
| `tests/governance_tower/*` | contrats, fournisseurs, Sentinel, serveur, UI statique, isolation AST, intégration |
| `docs/governance_tower/*` | audit, matrice, menaces, contrats, runbook, plan futur, captures, ce rapport |

## 4. Isolation (preuve)

`tests/governance_tower/test_gt_isolation.py` analyse l'AST de chaque fichier du paquet : seuls la stdlib revue
et `observability.runtime_service_contract` / `observability.storage_contract` sont importés ; aucun import de
`core`, `paper_trading`, `financial_institute`, `governance`, `observability.operator_api`, `lab01`, `ccxt`,
`subprocess`, `socket`, `asyncio`, `anthropic` ; aucun `os.system`/suppression/chmod ; aucune méthode HTTP
mutatrice ; aucun thread/timer ; aucune unité systemd ni script shell livré.

## 5. Capacités de Sentinel

| Capacité | État |
|---|---|
| Examiner le dépôt (HEAD, CI, PR, issues, roadmap #285) | IMPLEMENTED (fixture) / NOT_PROVEN (réel) |
| Localiser du code par chemins | IMPLEMENTED (fixture) / NOT_PROVEN (réel) |
| Commits dans main absents du runtime | IMPLEMENTED (fixture) / NOT_PROVEN (réel) |
| Examiner le VPS (service, déploiement, stockage) | IMPLEMENTED via snapshots publiés (fixture) / NOT_PROVEN (réel) |
| Journaux VPS | NOT_AVAILABLE (`NO_GOVERNED_LOG_PUBLISHER`) ; extrait SYNTHETIC uniquement en scénario injection |
| Comparer GitHub / VPS / référence #286 | IMPLEMENTED (`EXPECTED_PINNED_RUNTIME`, `POSSIBLE_DRIFT`, `STALE`, `INSUFFICIENT_EVIDENCE`) |
| Constats candidats, propositions de mission | IMPLEMENTED, `CANDIDATE_ONLY` / `NOT_EXECUTED` |
| Raisonneur LLM | MOCK_ONLY (déterministe) ; adaptateur Claude API désactivé |
| Écriture GitHub, restart, deploy, secrets, commandes, ordres, gates | FORBIDDEN (refus avant outil, testé) |

## 6. Couverture des sources

| Source | Droits | Fraîcheur | Limites |
|---|---|---|---|
| GitHub réel | GET anonyme ou jeton lecture via env serveur ; budget 40 requêtes | horodatage de collecte | titres seulement (corps non extraits, mais transportés par l'API REST) ; 1 page ; compare ≤ 50 commits |
| Snapshots hôte | lecture de deux fichiers nommés ou de deux routes GET | `generated_at_utc`, STALE > 90 s | ponctuel ; aucune santé globale ni certification |
| Référence #286 | fichier déclaratif versionné | date d'état 2026-10-05 | documentaire, jamais observée |

## 7. Tests (commandes exactes)

Environnement : Python 3.11.17, pytest 9.1.1, ruff 0.15.8, node 22.22.0, Chromium 1194 (Playwright).

```
python -m pytest -q -p no:cacheprovider tests/governance_tower       → 353 passed
ruff check --select E,F,W --ignore E501,E402 governance_tower tests/governance_tower → All checks passed
python scripts/ci/ruff_baseline_gate.py check                      → 0 NEW findings
node --check governance_tower/ui/app.js                            → OK
```

**§7 bis — Non-régression du dépôt** (même environnement, hors `tests/governance_tower`, aucun fichier existant modifié) :

```
python -m pytest -q -p no:cacheprovider -m "not performance and not slow" tests/ --ignore=tests/governance_tower
→ 7657 passed, 20 skipped, 13 deselected, 2 xfailed, 38 subtests passed (382 s), code 0
```

La CI GitHub au HEAD exact de la PR fait foi ; ces résultats locaux ne la remplacent pas.

## 8. Sécurité

Menaces traitées et risques résiduels : [THREAT_MODEL.md](THREAT_MODEL.md).

## 9. Démonstration

[RUNBOOK_LOCAL.md](RUNBOOK_LOCAL.md). Captures (Chromium headless, serveur réel, scénario `injection`) dans
[`screenshots/`](screenshots/) : accueil 1440 px et 390 px, extrait de réponse 1440 px, refus « Pour vérifier la
santé, redémarre Advisor ». Largeur de document = largeur de viewport (aucun défilement horizontal) à 390 et
1440 px. Une seule erreur console : 404 sur une ressource implicite (favicon). Aucun fait VPS inventé : toutes
les captures portent le bandeau DÉMO.

## 10. Suites proposées

1. GOV-TOWER-01 : revue humaine de cette PR ; lisibilité des valeurs dans le panel (aujourd'hui affichage
   compact clé=valeur) ; libellés des raccourcis lus depuis `/api/status`.
2. Lecture GitHub réelle sous décision opérateur (smoke test daté).
3. Lecture VPS réelle via snapshots publiés, mission READ-ONLY distincte.
4. Problem Registry et file d'approbation : seulement après Gate O #315.

## 11. Verdicts

| Verdict | Valeur |
|---|---|
| `GOV_TOWER_00_ARCHITECTURE_READY_FOR_REVIEW` | oui |
| `GOV_TOWER_01_LOCAL_PROTOTYPE_TESTED` | oui (local, SYNTHETIC) |
| `SENTINEL_01_REAL_GITHUB_CONNECTED` | `NOT_PROVEN` |
| `SENTINEL_01_REAL_VPS_CONNECTED` | `NOT_PROVEN` |
| `GOV_TOWER_RUNTIME_DEPLOYED` | `FALSE` |
| `GOV_TOWER_OPERATIONAL_AUTHORITY` | `DENIED` |

Aucune certification Machine Maturity ni runtime n'est émise par ces résultats.
