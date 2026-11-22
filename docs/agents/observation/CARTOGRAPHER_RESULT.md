# Cartographie de zone — `repository-cartographer` (lot 2, banc isolé)

SHA testé (zone) : `e387318eeaed81d4e6dc90228d46943a65a5b73c`. La zone est identique à la tête de la PR
(`git diff` vide sur le périmètre). Le banc est testé au HEAD de la PR, dont le SHA est donné dans la PR.
Statut : **banc isolé, non installé, aucune validation automatique**.

## 1. Commandes de reproduction

```text
python3 -m pytest -q tests/agent_bench
python3 -m agent_bench.observation.bench cartographer-matrix --out docs/agents/observation/bench
python3 -m agent_bench.observation.bench cartographer --repo-sha e387318eeaed81d4e6dc90228d46943a65a5b73c --out /tmp/zone.json
```

Mission : [cartographer_zone_mission.json](examples/cartographer_zone_mission.json)
(`mission_id` `02e0f78f…`). Résumé scellé : [cartographer_zone_summary.json](examples/cartographer_zone_summary.json).
Rapport complet (333 Ko, hors dépôt) : `/mnt/project-files/cat-market-m1/agents-observation-pilot/repository-cartographer/zone_bbo_small_e387318_full.json`.

## 2. Matrice attendu / obtenu (10 cas)

Résultats attendus **écrits avant exécution** dans `agent_bench/observation/repository_cartographer.py` (`CASES`).
Matrice complète : [bench/cartographer_matrix.md](bench/cartographer_matrix.md).

| Cas | Attendu | Obtenu | Résultat |
|---|---|---|---|
| 1 import seul | `IMPORT_ONLY`, 0 appel de production | identique | PASS |
| 2 appel seulement dans un test | `TEST_CALL`, 0 production | identique | PASS |
| 3 helper de test importé par la production | `TEST_SCOPE_CALL`, `IMPORT_TEST_SCOPE`, 0 production | identique | PASS |
| 4 appel de secours | `primary` production, `fallback` `CONDITIONAL_PRODUCTION_CALL` | identique | PASS |
| 5 cible dynamique | 0 appel, `DYNAMIC_CALL_TARGET` INCONCLUSIVE | identique | PASS |
| 6 deux producteurs du même fichier | `MULTIPLE_PRODUCER_CANDIDATES` avec 2 références | identique | PASS |
| 7 flag sur un chemin | `FLAG_SINGLE_PATH` attribué à `cfg.py:load` | identique | PASS |
| 8 flag sur deux chemins | `FLAG_MULTI_PATH` | identique | PASS |
| 9 source illisible | `PARSE_FAILED`, statut PARTIAL | identique | PASS |
| 10 31 fichiers | `FILE_BUDGET_EXCEEDED` | identique | PASS |

Tests associés (`tests/agent_bench/test_repository_cartographer.py`) : les 4 tests d'origine du
prototype, plus un test par critère, la reproductibilité indépendante de l'ordre, le budget de 30,
la mission refusée si le type de question ne correspond pas au profil, la lecture bornée
(`.env`, `secrets/`, lien symbolique refusés), la reproductibilité de la zone et le résumé scellé.

## 3. Zone CAT analysée

Trois fichiers : `observability/operator_api/bbo_history_reader.py`,
`observability/radar_composite/bbo_history.py`, `observability/radar_composite/bbo_pilot.py`.

| Mesure | Valeur |
|---|---|
| Statut | PARTIAL (2 `DYNAMIC_CALL_TARGET`, INCONCLUSIVE) |
| Sources | 3 Python, 0 refus, 0 fichier ignoré |
| Imports | 43 : 37 `IMPORT_USED`, 6 `IMPORT_ONLY` (vérifiés à la main : directive `annotations`, attributs `sys.*`, `timezone.utc`, constante `PERIOD_MS`) |
| Appels | 981 expressions d'appel repérées par analyse statique : 498 `PRODUCTION_CALL`, 483 `CONDITIONAL_PRODUCTION_CALL` |
| Constats | `FLAG_SINGLE_PATH` : `OPERATOR_BBO_HISTORY_PATH` lu seulement dans `bbo_history_reader.py:BboHistoryReader.__init__` (ligne 30) |
| Producteurs multiples | aucun constat (pas d'écriture commune dans la zone) |
| Reproduction | deux exécutions : même `content_sha256` (`67bdcc05…`) |
| Mesure | 141 ms, 3 fichiers de zone + profil, 0 écriture, 0 réseau |

Lecture : les 498 `PRODUCTION_CALL` et 483 `CONDITIONAL_PRODUCTION_CALL` sont des **expressions
d'appel repérées par analyse statique** dans trois fichiers Python. Ces compteurs **ne mesurent aucune
exécution réelle** : ils ne disent ni ce qui a été appelé, ni combien de fois, ni par quel chemin.
Une expression classée conditionnelle ne prouve pas que sa branche est atteignable. La zone n'a aucun
import de test ni appel dans un test ; les appels conditionnels viennent surtout de blocs `if`
(`BRANCH`) et de la fonction `main` de `bbo_pilot.py`, reconnus comme conditionnels mais non prouvés
atteignables.

## 3 bis. Répétition sous l'identité prévue du runner

Environnement : conteneur jetable, **hors VPS**, sans service installé. Compte `cat-obs-ro` créé
pour la répétition (sans shell de connexion, sans groupe sensible, sans sudo). Identité logique
`obs-repo-cartographer-ro-01`.

Deux SHA distincts, à ne pas confondre :

- **SHA du code du banc** (ce qui est exécuté) : `3b67c91b641b4c805cf07c01782db4f547090a67`.
  Checkout détaché, clone local, `chmod a-w` sur tout l'arbre, propriétaire `root`.
- **SHA de la zone analysée** (`analyzed_ref` de la mission) : `e387318eeaed81d4e6dc90228d46943a65a5b73c`.
  Les trois fichiers de zone sont identiques dans les deux SHA (`git diff` vide sur le périmètre).

| Contrôle | Attendu | Obtenu | Preuve | Statut |
|---|---|---|---|---|
| Lecture du checkout par `cat-obs-ro` | lisible | lecture OK | commande ci-dessous | PASS |
| Écriture d'un témoin dans le checkout | refusée | `Permission denied` (code 2) | idem | PASS |
| Écriture dans `/srv/cat-obs/reports` | autorisée | OK | idem | PASS |
| Écriture hors de `reports` (témoin `/srv/cat-obs-decoy-outside.txt`) | refusée | `Permission denied` (code 2) | idem | PASS |
| Réseau bloqué (contrôle négatif dans le contexte du runner) | connexion impossible | `Network is unreachable` (errno 101) | `unshare -n` (espace réseau sans route) | PASS |
| Exécution du cartographe | `PARTIAL`, `content_sha256` `67bdcc05…` | `PARTIAL`, `67bdcc05…` | rapport hors dépôt | PASS |
| Empreinte recalculée indépendamment | identique à l'empreinte scellée | identique | `sha256_json(content)` | PASS |

Mécanisme d'isolation réseau : espace de noms réseau sans interface routable (`unshare -n`). Ce n'est
**pas** le mécanisme prévu en production (règles pare-feu ou ressource sans route), qui reste à établir sur l'hôte.

Preuve d'invocation expurgée : [invocation_proof_zone.json](rehearsal/invocation_proof_zone.json).
Elle contient l'identité du runner, les deux SHA, l'issue, l'empreinte du rapport. Elle ne contient
aucun chemin d'hôte ni secret.

**Non vérifié (à compléter avant branchement) :**

- Le compte réel sur l'hôte cible (`cat-obs-ro` sur le VPS) : seul un compte équivalent a été créé dans le conteneur.
- L'isolation réseau de production : `unshare -n` prouve le blocage dans cet espace de noms seulement.
- La preuve d'invocation est écrite par un wrapper root de répétition, pas par le runner lui-même.
- `/srv/cat-obs` réel et ses permissions d'hôte.

Commandes exécutées (répétition) :

```text
git clone --no-local <dépôt> /srv/cat-obs/checkout/3b67c91b… && git checkout --detach 3b67c91b…
chmod -R a-w /srv/cat-obs/checkout/3b67c91b…
unshare -n setpriv --reuid cat-obs-ro --regid cat-obs-ro --clear-groups env -i PATH=… HOME=/nonexistent PYTHONDONTWRITEBYTECODE=1 \
  sh -c 'cd <checkout> && python3 -m agent_bench.observation.bench cartographer --repo-sha e387318eeaed81d4e6dc90228d46943a65a5b73c --out /srv/cat-obs/reports/<fichier>.json'
→ PARTIAL 67bdcc05ec67e54013991028275d78ff4727c299fe2f9b6762c2b3da35a3fa4e
```

## 4. Verdict proposé

**Recevable pour revue humaine, avec les limites ci-dessous.** Il ne qualifie aucun runner et
n'allume aucun voyant. Le profil reste `NOT_WIRED`.

Verdict `PARTIAL` conservé : deux cibles d'appel dynamiques restent **INCONCLUSIVE** (non résolues,
non comptées comme appels).

Limites restantes (à reporter dans toute décision) :

1. Analyse statique seulement : aucun import, aucune exécution. Un import sans appel n'établit pas l'absence de chargement (effets de bord à l'import).
2. Un saut de résolution de noms : les alias et les appels indirects au-delà d'un saut ne sont pas suivis.
3. `BRANCH` est large : tout appel sous un `if` (même dans une fonction définie sous un `if`) est conditionnel. Une branche n'est pas prouvée atteignable.
4. `FLAG_SINGLE_PATH` ne vaut que pour la zone analysée ; un autre module hors zone peut lire le même flag.
5. Les fixtures et les attendus sont écrits par le même auteur que le code : une revue humaine des attendus est requise.
6. Les flags lus par `argparse` ne sont pas inventoriés dans ce lot.
7. Aucune mesure runtime : la zone n'est pas observée sur l'hôte, et ce rapport ne dit rien de ce qui tourne réellement.
8. `observability-cartographer` et `repo-architect` restent non qualifiés.
