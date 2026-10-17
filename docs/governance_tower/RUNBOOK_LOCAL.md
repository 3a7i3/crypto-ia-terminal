# Governance Tower — Démarrage local et guide d'utilisation (lot H)

**Local seulement, loopback seulement, démo SYNTHETIC par défaut.** Ce document ne vaut
aucune autorisation de déploiement ; voir [FUTURE_DEPLOYMENT_PLAN.md](FUTURE_DEPLOYMENT_PLAN.md).

## 1. Prérequis

- Python 3.11+ (stdlib uniquement pour l'application ; `pytest` pour les tests).
- Aucune dépendance npm, aucun CDN, aucune clé, aucun accès VPS.
- Taille approximative : paquet `governance_tower/` < 400 Kio (code, UI, fixtures) ; mémoire d'exécution de l'ordre de quelques dizaines de Mio. Coût : nul en démo (aucun appel payant, raisonneur déterministe).

## 2. Démarrer la démo

```bash
cd crypto-ia-terminal
python -m governance_tower serve --scenario nominal        # http://127.0.0.1:8765/
python -m governance_tower serve --scenario injection --port 8766
```

Scénarios : `nominal` (runtime épinglé attendu), `injection` (instructions cachées dans PR, issue et journal),
`drift` (SHA inattendu), `stale` (snapshot périmé), `host_unavailable` (VPS indisponible),
`github_denied` (GitHub refuse l'accès), et depuis GOV-TOWER-01 `github_rate_limited` (quota GitHub atteint),
`no_deployment_id` (aucune identité de build publiée), `partial` (un seul snapshot frais). Toutes les données sont **SYNTHETIC** et le bandeau
« DÉMO — DONNÉES SYNTHÉTIQUES » reste affiché.

Question en ligne de commande :

```bash
python -m governance_tower ask "Quels commits sont dans main mais pas prouvés comme déployés ?"
python -m governance_tower ask "" --shortcut compare --scenario drift --json
```

Le serveur refuse de démarrer hors loopback (`--host 0.0.0.0` → `NotLoopback`).

## 3. Lectures réelles (opt-in, hors démo)

Preuves datées et méthode exacte : [revue indépendante](DELIVERY_REPORT.md).
Le connecteur GitHub a été exercé ; le VPS a été lu par transport direct existant puis copies locales.
Le connecteur distant OperatorApiHostProvider reste non démontré.

| Option | Effet | Statut |
|---|---|---|
| `--github-live` | GET anonymes vers `api.github.com` (jeton optionnel via `GT_GITHUB_TOKEN`, côté serveur) ; budget 12 requêtes par question, plafond de service 40 requêtes par heure glissante, quota distant GitHub (`429`/`Retry-After`/`X-RateLimit-Reset`) respecté entre questions | Démontré réellement le 2026-10-16 (voir rapport, budget 5 puis 6 GET) |
| `--host-snapshots DIR` | lit une **copie locale** de `runtime_service_snapshot.json` et `storage_snapshot.json` | `NOT_PROVEN` |
| `--host-operator-api URL` | GET `/api/operator/v1/runtime-service` et `/storage` sur une URL loopback/https | `NOT_PROVEN` |

Toute lecture réelle du VPS, même READ-ONLY, relève d'une mission séparée autorisée (#286).
Fixtures et lectures réelles ne peuvent pas être combinées.

## 4. Parler à Sentinel

Exemples :

- « Quelle est la roadmap active ? »
- « Quels travaux sont en cours ? »
- « Quels composants du code contrôlent les publishers ? »
- « Quels commits sont dans main mais pas prouvés comme déployés ? »
- « Sentinel, analyse mon dépôt et les observations autorisées du VPS. Distingue ce qui est intégré dans GitHub, ce qui est effectivement déployé, ce qui est certifié et ce qui demeure inconnu. Cite les preuves. Ne corrige rien. »

Lire une réponse :

| Section | Signification |
|---|---|
| CONSTATS `OBSERVED` | fait lu dans une source, avec ses puces de preuve |
| `INFERRED` | déduit ou déclaré (ex. référence gelée #286), non observé |
| `NOT_PROVEN` | non établi (ex. certification) |
| INCERTITUDES | sources absentes, limites de lecture, bandeau démo |
| ÉCARTS GitHub/VPS | `EXPECTED_PINNED_RUNTIME` = runtime volontairement épinglé, ne pas « corriger » |
| PROPOSITIONS NON EXÉCUTÉES | missions documentées ; aucune autorité, décision opérateur requise |
| CONTENU EXTERNE NON FIABLE | texte GitHub/journal cité comme donnée, jamais suivi |
| REFUS | demande d'action refusée avant tout outil |

Sentinel refuse : redémarrer/arrêter/activer un service, déployer, écrire sur GitHub (PR, merge, commentaire),
lire un secret ou un `.env`, exécuter une commande, passer un ordre ou un paiement, modifier un paramètre gelé,
valider une gate.

## 5. Tests

```bash
python -m pytest -q tests/governance_tower
ruff check --select E,F,W --ignore E501,E402 governance_tower tests/governance_tower
node --check governance_tower/ui/app.js
```

## 6. Journal d'audit (opt-in)

`--audit-log /chemin/audit.jsonl` : une ligne par question (identité du run, intention, outils et états,
codes de refus, nombre de preuves), sans question ni contenu externe, fichier `0600`,
`O_NOFOLLOW`, plafond 1 Mio puis arrêt d'écriture. Rétention proposée : supprimer à la fin de la session
de démonstration ; aucune rotation automatique.

Un échec d'audit n'est jamais silencieux : plafond atteint (`AUDIT_CAP_REACHED`) ou écriture refusée
(`AUDIT_WRITE_ERROR`, ex. cible devenue lien symbolique) ajoutent une incertitude à la réponse
(« ce run n'a pas été journalisé ») et apparaissent dans `/api/status` (`audit`) et la ligne de mode.

## 7. Bannière des sources et aperçu

Chaque source affiche son heure de collecte et son âge (« consulté il y a … »). Au-delà de 300 s,
un dernier état `AVAILABLE` devient `STALE` (« dernier état connu, périmé ») ; un état en échec
(`DENIED`, `ERROR`…) garde son état. La page relit `/api/status` (GET) toutes les 60 s : cette relecture
ne consulte aucune source. `http://127.0.0.1:8765/#apercu` affiche `sample_run.json`, exemple
SYNTHETIC versionné, sans remplacer l'état réel des sources de la bannière.

## 8. GOV-TOWER-01 — lectures ciblées, diagnostics, cartographie

Statuts : `GT01_LIVE_GITHUB_PROVEN = NOT_PROVEN`, `GT01_LIVE_VPS_PROVEN = NOT_PROVEN`,
`GT01_LLM_LIVE = DISABLED`. Tout ce qui suit fonctionne en démo SYNTHETIC ; `--github-live`
utilise le même code, sous le même budget.

Questions nouvelles :

| Question | Intention | Lecture |
|---|---|---|
| « Le VPS exécute-t-il la même version que GitHub ? » | `COMPARE` | dépôt + snapshots, diagnostics croisés |
| « Lis le fichier governance_tower/contracts.py lignes 1-40 » (option « au SHA <40 hex> ») | `READ_FILE` | 1 GET `/contents`, extrait ≤ 200 lignes, empreinte Git vérifiée |
| « Montre l'issue #461 » | `ISSUE_DETAIL` | 1 GET, corps ≤ 3000 car. expurgé, commentaires non lus |
| « Détaille la PR 460 » | `PULL_DETAIL` | 1 GET + CI du SHA de tête de la PR |
| « Quelle est la CI du commit <40 hex> ? » | `CI_FOR_SHA` | 1 GET check-runs (≤ 100) |
| « Quels sont tes angles morts ? » | `COVERAGE_MAP` | aucune lecture : cartographie déclarée (`governance_tower/coverage.py`) |

Chemins refusés avant toute requête : `.env*`, `secrets/`, clés (`*.pem`, `id_rsa`…), `.git/`,
traversée, binaires, extensions hors allowlist. « relance la CI », « ferme l'issue » et toute
écriture GitHub sont refusés.

Lire un diagnostic : **Observation** (ce qui est publié) → **Interprétation possible** (jamais
une violation ni une santé) → **Ce qui reste à vérifier** (jamais vide) → **Proposition de
mission** (non exécutée, aucune autorité). Le code (`EXPECTED_PINNED_RUNTIME`, `POSSIBLE_DRIFT`,
`NO_DEPLOYED_BUILD_ID`, `ACTIVE_NOT_HEALTH`…) vient du serveur. Les preuves sont repliées sous
« Preuves (n) » ; un bandeau signale toute source non fraîche ou non lue.

La ligne de mode affiche le raisonneur, l'état du modèle externe (désactivé) et, en lecture
GitHub réelle, le budget GET consommé.

Démo : en mode DÉMO, l'âge affiché dans la bannière compare l'horodatage figé des fixtures à
l'horloge réelle (le VPS apparaît « Périmé ») alors que les diagnostics utilisent l'horloge des
fixtures ; c'est une limite de la démo, pas un état du VPS.

Tests et parcours navigateur :

```bash
python -m pytest -q tests/governance_tower
NODE_PATH=$(npm root -g) node scripts/governance_tower/gt01_ui_e2e.mjs docs/governance_tower/screenshots
```

Le parcours E2E lance des serveurs DÉMO sur `127.0.0.1:18761-18764`, bloque toute requête hors
loopback et produit les captures `gt01_*` à 390 et 1440 px.
