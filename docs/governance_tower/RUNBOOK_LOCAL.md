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
`github_denied` (GitHub refuse l'accès). Toutes les données sont **SYNTHETIC** et le bandeau
« DÉMO — DONNÉES SYNTHÉTIQUES » reste affiché.

Question en ligne de commande :

```bash
python -m governance_tower ask "Quels commits sont dans main mais pas prouvés comme déployés ?"
python -m governance_tower ask "" --shortcut compare --scenario drift --json
```

Le serveur refuse de démarrer hors loopback (`--host 0.0.0.0` → `NotLoopback`).

## 3. Lectures réelles (opt-in, hors démo, non éprouvées)

| Option | Effet | Statut |
|---|---|---|
| `--github-live` | GET anonymes vers `api.github.com` (jeton optionnel via `GT_GITHUB_TOKEN`, côté serveur) ; budget 40 requêtes par instance | `NOT_PROVEN` : testé avec transport simulé uniquement |
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
codes de refus, nombre de preuves), extrait de question expurgé et tronqué, fichier `0600`,
`O_NOFOLLOW`, plafond 1 Mio puis arrêt d'écriture. Rétention proposée : supprimer à la fin de la session
de démonstration ; aucune rotation automatique.
