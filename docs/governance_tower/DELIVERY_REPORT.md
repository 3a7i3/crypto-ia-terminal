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
