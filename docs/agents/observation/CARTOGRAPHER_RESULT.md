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
| Appels | 981 : 498 `PRODUCTION_CALL`, 483 `CONDITIONAL_PRODUCTION_CALL` |
| Constats | `FLAG_SINGLE_PATH` : `OPERATOR_BBO_HISTORY_PATH` lu seulement dans `bbo_history_reader.py:BboHistoryReader.__init__` (ligne 30) |
| Producteurs multiples | aucun constat (pas d'écriture commune dans la zone) |
| Reproduction | deux exécutions : même `content_sha256` (`67bdcc05…`) |
| Mesure | 141 ms, 3 fichiers de zone + profil, 0 écriture, 0 réseau |

Lecture : la zone n'a aucun import de test ni appel dans un test ; les 483 appels conditionnels
viennent surtout de blocs `if` (`BRANCH`) et de la fonction `main` de `bbo_pilot.py`, qui sont
reconnus comme conditionnels mais pas comme atteignables.

## 4. Verdict proposé

**Recevable pour revue humaine, avec les limites ci-dessous.** Il ne qualifie aucun runner et
n'allume aucun voyant. Le profil reste `NOT_WIRED`.

Limites restantes (à reporter dans toute décision) :

1. Analyse statique seulement : aucun import, aucune exécution. Un import sans appel n'établit pas l'absence de chargement (effets de bord à l'import).
2. Un saut de résolution de noms : les alias et les appels indirects au-delà d'un saut ne sont pas suivis.
3. `BRANCH` est large : tout appel sous un `if` (même dans une fonction définie sous un `if`) est conditionnel. Une branche n'est pas prouvée atteignable.
4. `FLAG_SINGLE_PATH` ne vaut que pour la zone analysée ; un autre module hors zone peut lire le même flag.
5. Les fixtures et les attendus sont écrits par le même auteur que le code : une revue humaine des attendus est requise.
6. Les flags lus par `argparse` ne sont pas inventoriés dans ce lot.
7. Aucune mesure runtime : la zone n'est pas observée sur l'hôte, et ce rapport ne dit rien de ce qui tourne réellement.
8. `observability-cartographer` et `repo-architect` restent non qualifiés.
