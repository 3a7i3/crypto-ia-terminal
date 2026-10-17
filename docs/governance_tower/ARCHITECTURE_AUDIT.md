# Governance Tower — Audit d'architecture et découpage des missions (lot A)

Mission : GOV-TOWER-00 / [#459](https://github.com/3a7i3/crypto-ia-terminal/issues/459) · Roadmap #285 · Garde #286 (ACTIVE)
Date : 2026-10-16 · Rédigé par Claude (fil « Mission initiale Governance Tower »)

## 0. Point de départ vérifié

| Élément | Valeur | Nature |
|---|---|---|
| Base source | `main@ab84ba4eb370b3adbefb43fb7d651dd0ff031ecd` (merge #458) | OBSERVED (`git rev-parse HEAD`) |
| Branche de travail | `claude/governance-tower-architecture-x6i7ui`, arbre propre | OBSERVED |
| Garde #286 | `ACTIVE_BURN_IN_IMMUTABILITY_GUARD`, relue le 2026-10-16 (dernier commentaire 19:12Z) | OBSERVED (GitHub) |
| Runtime gelé | source `116634be…`, config `9d9de1af…`, epoch `BURN-IN-EPOCH-01-20260926T064144Z` | référence déclarée #286, **pas** observée |
| Gate O #315 | `OPEN / NON_RESOLVED`, OperatorDecision `NON_DEPLOYED` | OBSERVED (GitHub) |
| Accès VPS depuis cet environnement | aucun | `NOT_AVAILABLE` |
| Outils | Python 3.13, Node 22 (CI : Python 3.11, Node 20) | OBSERVED |

Aucune exception #286 n'est utilisée ni requise : tout le travail est source-only, dans le dépôt, sans contact avec le VPS.

## 1. Constats d'architecture (lot A, synthèse)

1. **Trois applications existantes partagent un même frontend** (`frontend/`, React 18 + Vite, routeur unique Machine/Research) et une même API de présentation GET-only (`observability/operator_api/app.py`, FastAPI). La Bank/FIN est servie dans ce même ensemble.
2. **LAB-01 (`lab01/`) est le meilleur précédent d'application isolée** : paquet Python racine sans dépendance au runtime, serveur `http.server` stdlib en loopback, une page `ui/index.html` autonome, CSP stricte, jeton requis, tests dédiés `tests/lab01/`. Governance Tower suit ce modèle plutôt que d'ajouter une route à l'Operator App.
3. **Contrats d'observation hôte déjà gouvernés et réutilisables en lecture** :
   - `observability/runtime_service_contract.py` (`RuntimeServiceSnapshot`, autorité `HOST_SYSTEMD_OBSERVATION`, champ `deployment.source_code_sha`) ;
   - `observability/storage_contract.py` (`StorageSnapshot`, métadonnées de fichiers) ;
   - tous deux purs (aucune E/S systemd, aucun import runtime), déjà publiés en production par les publishers passifs G3–G5 et servis par `GET /api/operator/v1/runtime-service` et `/storage`.
   Sentinel peut donc observer le VPS **sans nouveau collecteur** : il lit ces snapshots publiés et les valide avec les validateurs existants.
4. **Vocabulaire d'absence déjà établi** : `observability/operator/contracts.py` (`FreshnessStatus`, `NullSemantics`). Governance Tower reprend ces sémantiques (UNKNOWN ≠ 0, STALE ≠ CURRENT) dans ses propres contrats, sans importer le module Operator.
5. **Lecteur GitHub existant côté frontend** : `frontend/src/lib/githubRoadmapReader.ts` (anonyme, GET-only, budget 55 requêtes, corps d'issues jamais lus). Il montre la discipline attendue ; Sentinel en reprend les règles côté serveur Python (budget, erreurs typées, contenu non fiable), sans coupler les deux applications.
6. **Le paquet `governance/` existant est le routeur de décision du runtime** (`decision_router`, `risk_authorizer`, `execution_approval`). Il ne doit **pas** être réutilisé ni importé : le nom du nouveau paquet est donc `governance_tower/`, distinct.
7. **CI** : `ci.yml` exécute `pytest -q -m "not performance and not slow" tests/` et le portail ruff différentiel (`scripts/ci/ruff_baseline_gate.py`, ruff 0.15.8). De nouveaux tests sous `tests/governance_tower/` sont collectés automatiquement ; aucun workflow à modifier.

## 2. Architecture cible du prototype

```
                ┌──────────────────────── Governance Tower (local, loopback) ───────────────────────┐
 navigateur ──► │ ui/ (une page, un panel)  ──POST /api/sentinel/ask──►  server.py (stdlib)         │
                │                                                         │                         │
                │                                              Sentinel-01 (invocation manuelle)    │
                │                                    policy ─ table fixe d'outils READ-ONLY ─ reasoner│
                │                                         │                     │                    │
                │                         GithubReadProvider          HostObservationProvider       │
                │                      fixture | http opt-in      fixture | snapshots | operator-api │
                └─────────────────────────────┬──────────────────────────────┬──────────────────────┘
                                              │ GET only                      │ lecture de snapshots publiés
                                        api.github.com                 runtime_service / storage (validés
                                        (désactivé par défaut)         par les contrats existants)
```

Choix argumentés :

| Décision | Choix | Raison |
|---|---|---|
| Emplacement | `governance_tower/` à la racine, tests `tests/governance_tower/`, docs `docs/governance_tower/` | même forme que `lab01/` ; séparation physique de `frontend/`, `observability/operator_api/` et `governance/` |
| Backend | Python stdlib (`http.server`, `urllib`), aucune nouvelle dépendance | précédent LAB-01 ; « éviter des dépendances nouvelles » ; aucune réutilisation de FastAPI/session de l'Operator App |
| Frontend | une page HTML + JS/CSS statiques servis par le même processus, rendu `textContent` uniquement | pas de nouveau `package.json`/lockfile ; CSP `script-src 'self'` ; aucun couplage au routeur React |
| Imports autorisés hors paquet | uniquement `observability.runtime_service_contract`, `observability.storage_contract` (et leur dépendance pure `event_center_contract`) | réutiliser les contrats gouvernés sans créer d'autorité parallèle ; vérifié par test AST |
| Imports interdits | `core`, `paper_trading`, `financial_institute`, `governance`, `observability.operator_api`, exchange/ccxt, `subprocess`, `os.system` | test AST bloquant |
| Moteur de raisonnement | interface `Reasoner` ; `DeterministicDemoReasoner` par défaut (offline) ; adaptateur Claude API **désactivé par défaut** | aucun appel payant implicite ; tests reproductibles |
| Lecture GitHub réelle | fournisseur HTTP GET opt-in (`--github live`), jeton éventuel lu côté serveur depuis l'environnement, jamais journalisé | #459 : permission minimale ; `DENIED` ≠ `EMPTY` |
| Lecture VPS réelle | fournisseur opt-in lisant les snapshots publiés (dossier local copié **ou** GET de l'Operator API) | aucun shell, aucun nouveau collecteur, aucun port ; non activé dans ce mandat |
| Référence gelée | fichier déclaratif `pinned_references.json` cité à #286 | permet le verdict `EXPECTED_PINNED_RUNTIME` au lieu de « installer main » |
| Exposition réseau | refusée hors loopback (adresse de bind vérifiée, en-tête `Host` contrôlé, en-tête anti-CSRF requis) | l'authentification réelle est un préalable de toute future exposition |

Statuts qualifiés partout : `OBSERVED`, `INFERRED`, `PROPOSED`, `IMPLEMENTED_SOURCE`, `TESTED_LOCAL`, `NOT_DEPLOYED`, `NOT_PROVEN` ; disponibilité `AVAILABLE | STALE | NOT_AVAILABLE | DENIED | RATE_LIMITED | ERROR | UNKNOWN`.

## 3. Découpage en missions

| Mission | Lot | Dépend de | Fichiers | Critères de validation | Parallélisable |
|---|---|---|---|---|---|
| **GT-M0 Forensic et architecture** | A | — | `docs/governance_tower/ARCHITECTURE_AUDIT.md`, `REUSE_MATRIX.md`, `THREAT_MODEL.md` | chaque fait cité avec fichier/issue ; matrice KEEP/REUSE/ISOLATE/FUTURE ; menaces → mitigations → tests | non (socle) |
| **GT-M1 Contrats** | B | M0 | `governance_tower/contracts.py`, `redaction.py`, `pinned_references.json`, `docs/governance_tower/CONTRACTS.md` | schémas fermés et versionnés ; UTC explicite ; refus des champs inconnus ; limites de taille ; tests unitaires (absence ≠ zéro, dates futures, provenance mélangée SYNTHETIC/réelle refusée) | non (socle) |
| **GT-M2 Connecteur GitHub lecture** | C | M1 | `governance_tower/providers/github.py`, fixtures | GET seul, liste blanche d'endpoints, budget/timeout, 401/403 → `DENIED`, 429 → `RATE_LIMITED`, chemins exclus et rédaction ; 4 questions types | **oui** (fichiers propres) |
| **GT-M3 Observation hôte** | D | M1 | `governance_tower/providers/host.py`, fixtures | validation par contrats existants ; symlink/traversal refusés ; taille bornée ; STALE ; VPS absent → `NOT_AVAILABLE` ; runtime épinglé → `EXPECTED_PINNED_RUNTIME` | **oui** |
| **GT-M4 Sentinel-01** | E | M2, M3 (interfaces) | `governance_tower/sentinel/` (policy, tools, reasoner, agent, audit) | table fixe d'outils READ-ONLY ; intentions mutatrices refusées avant tout effet ; prompt-injection citée comme donnée ; sortie structurée CONSTATS/PREUVES/INCERTITUDES/PROPOSITIONS NON EXÉCUTÉES ; journal rédigé opt-in | non |
| **GT-M5 Interface à panel unique** | F | M1 (schéma de réponse) | `governance_tower/server.py`, `governance_tower/ui/*`, `__main__.py` | une route, un panel ; en-tête GOVERNANCE TOWER / SENTINEL-01 / READ ONLY + GitHub/VPS séparés ; 5 raccourcis ; bannière DEMO/SYNTHETIC ; 360–1440 px ; clavier/aria ; aucun bouton d'action ; CSP | **oui** (contre le schéma M1) |
| **GT-M6 Sécurité et tests négatifs** | G | M2–M5 | `tests/governance_tower/test_security_*.py` | toutes les catégories de #459 §5 et du prompt maître §9, dont les 3 scénarios d'intégration | non |
| **GT-M7 Documentation et exploitation future** | H | M1–M6 | `RUNBOOK_LOCAL.md`, `USER_GUIDE.md`, `FUTURE_DEPLOYMENT_PLAN.md`, registre des risques | démarrage loopback reproductible ; plan d'admission futur sans autorisation implicite | partiel |
| **GT-M8 Handoff** | I | tout | `docs/governance_tower/DELIVERY_REPORT.md`, PR brouillon | verdicts selon preuves, SHA exacts, tests exacts | non |

**Parallélisme** : après M1, les missions M2, M3 et M5 touchent des fichiers disjoints et peuvent avancer en parallèle. Je les exécute dans ce fil avec des sous-agents en worktrees isolés, puis je les intègre sur une seule branche et une seule PR brouillon (un commit par mission). Cela évite trois PR concurrentes qui modifieraient le même paquet. Si tu préfères des fils séparés visibles dans le projet, M2 (GitHub), M3 (VPS) et M5 (UI) sont les candidats ; ils devraient alors partir d'une branche commune contenant M1.

## 4. Matrice de réutilisation (extrait)

| Module existant | Décision | Motif |
|---|---|---|
| `observability/runtime_service_contract.py` | REUSE (import lecture) | contrat hôte gouverné, pur |
| `observability/storage_contract.py` | REUSE (import lecture) | idem |
| `observability/operator/contracts.py` | REUSE du vocabulaire, pas de l'import | éviter de lier GT au cycle de vie Operator |
| `observability/operator_api/*` | ISOLATE | autorité de présentation de l'Operator App ; consommée éventuellement par HTTP GET, jamais importée |
| `frontend/` (React, routeur, session) | ISOLATE | séparation exigée par #459 ; tokens de couleur repris par valeur |
| `frontend/src/lib/githubRoadmapReader.ts` | REUSE des règles, pas du code | même discipline, autre runtime |
| `lab01/api.py` | REUSE du patron (loopback, CSP, jeton) | précédent validé |
| `governance/` (routeur de décision runtime) | ISOLATE, interdit d'import | autorité de trading |
| `core/`, `paper_trading/`, `financial_institute/` | ISOLATE, interdit d'import | burn-in / PPL / FIN |
| OperatorDecision (#315), passerelle #445 | FUTURE | aucune approbation ni opération nommée avant Gate O / gate #445 |

## 5. Hors périmètre (demandera ton approbation)

- Toute lecture réelle du VPS (même READ-ONLY) depuis Sentinel : exige une mission/gate séparée et un transport déjà autorisé.
- Toute lecture GitHub réelle authentifiée (PAT) ; un test anonyme ponctuel de lecture publique n'est pas fait sans ton accord explicite.
- Activation de l'adaptateur Claude API (coût, clé).
- Installation, port, unité systemd, tunnel ou déploiement sur le VPS ; exception #286.
- Fusion dans `main`.

Note d'interprétation : le prompt maître demande de préparer branche et PR sans pousser, alors que ton message et la consigne du projet demandent de livrer par branches et PR en brouillon. Je pousse uniquement la branche désignée et j'ouvre une **PR brouillon**, jamais fusionnée ; c'est une livraison de développement demandée par toi, pas une « PR autonome » de Sentinel (qui reste interdite et techniquement impossible dans le code).

## 6. Verdicts attendus en fin de mission

`GOV_TOWER_00_ARCHITECTURE_READY_FOR_REVIEW` et `GOV_TOWER_01_LOCAL_PROTOTYPE_TESTED` si les preuves le permettent ;
`SENTINEL_01_REAL_GITHUB_CONNECTED = NOT_PROVEN` ; `SENTINEL_01_REAL_VPS_CONNECTED = NOT_PROVEN` ;
`GOV_TOWER_RUNTIME_DEPLOYED = FALSE` ; `GOV_TOWER_OPERATIONAL_AUTHORITY = DENIED`.
