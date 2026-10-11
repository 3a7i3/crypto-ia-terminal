# D1_C_TEST_REPORT

Tests locaux du 2026-10-11 UTC dans le workspace Research Linux isolé :
Python 3.12.14, pytest 9.1.1, Ruff 0.15.8, dépendances requirements-ci.txt.
La CI utilise Python 3.11 ; cette différence est explicite, pas une validation
locale de 3.11. Aucun secret/dataset privé/runtime utilisé. Données temporaires
synthétiques seulement. Aucun typage mypy/pyright configuré trouvé ; annotations
présentes, py_compile exécuté ; pas de faux PASS de type checker.

## Identité exacte du code final testé

Commit source : `b5225ea7b69fe689f238ae97f8d8775b4f02c775`, parent d'implémentation
`03d66eb8a93a3a5deffe5dab03449540789f480d`, parent D1 #406
`b99c2ed4f38ebeff481b5f470ed2d08e8e852257`. Version script `D1_C_V1`.

| Fichier | SHA-256 |
|---|---|
| research_data/stress_d1_rejection_eligibility.py | 2a467c59a28bb7fcc2eb1fa79204c08443bad2d375e38dfef6eed9bbe90b7e3d |
| tests/research_data/test_stress_d1_rejection_eligibility.py | 24dd9492f607030e19294ba9e370e5bd5655535e840d149b274908dcd0e88a05 |
| auditeur historique intact | 11d3e13e90e04446f6d1fc5bff4840103fa4f23e2865a211e8b5f77771b94494 |

## Résultats et portée

| Commande / périmètre | Révision | Résultat |
|---|---|---|
| pytest test_stress_d1_rejection_eligibility + capture + rejection_store + decision_observation + s03b_provenance + decision_event_bus + decision_packet_confidence | b5225ea7… | 140 PASS dont 62 D1-C, 0 skip, 0 échec, 3 avertissements de dépréciation |
| pytest research_data/replay/diag/candidate + rb3 epoch + rb3 config + herm_02 isolation | b5225ea7… | 239 PASS, 0 skip, 0 échec, 399 avertissements de dépréciation |
| pytest tests/cross_stack/ | b5225ea7… | 96 PASS, 0 skip, 0 échec, 1 avertissement dépendance HTTP |
| pytest -q -m 'not performance and not slow' tests/ | 03d66eb8… | 7066 PASS, 19 SKIPPED, 13 DESELECTED, 2 XFAIL, 0 échec, 2138 avertissements, 121.85 s |
| Ruff fichiers nouveaux et scripts/ci/ruff_baseline_gate.py check | b5225ea7… | PASS ; 957 findings baseline, 945 actuels, 0 nouvelle violation |
| py_compile des deux nouveaux fichiers | b5225ea7… | PASS |
| git diff --check | source + documents | PASS |

Le seul delta logiciel après la suite générale à 03d66eb8 est la conservation
du nom natif global_risk_gate dans la matrice d'acteurs (pas renommé gate),
avec son test négatif vérifiant que le premier blocker inconnu reste inconnu.
Les tests ciblés et Research/cross-stack ont été réexécutés au commit final
b5225ea7. La CI de la PR doit vérifier sa composition exacte ; une réussite
locale antérieure n'est pas promue en CI finale.

Les 19 skips et 2 xfails appartiennent aux suites existantes et ne sont pas
comptés comme PASS ; les 13 deselections sont les marqueurs performance/slow
explicitement exclus. Les 62 nouveaux contrôles ne sont jamais skipped.
Première exécution ciblée : 52 tests PASS ; Ruff a signalé trois imports
inutilisés du fichier de tests, corrigés. Les contrôles supplémentaires ont
ensuite porté D1-C à 62. Aucun test supprimé ni baseline modifiée pour cacher
un échec. L'avertissement initial asyncio_mode (plugin non encore installé)
a disparu après installation complète des dépendances CI.

## Couverture scientifique des contrôles synthétiques

Partitions LINKED/non-actionable/HOLD/FLAT/candidat/UNKNOWN ; booléens manquants
ou chaînes jamais coercés ; signal_raw écrasé ou non corroboré ; verdict Gate
sans marqueur G8-D conservé UNKNOWN ; permutations et équations de matrices ;
aucune mutation des entrées ni ID dans stdout ; duplication packet, trace,
observation et plusieurs observations pour un packet ; trace/symbol/cycle
incohérents ; observation orpheline ; packet sans identité ; digest invalide ;
historique identité explicite ; ordre causal invalide ; champ record requis
absent et prix invalide/non fini ; manifest falsifié, composant/index SHA faux,
composant manquant, symlink, epoch/source/config incorrectes et prétention de
complétude refusée ; hors fenêtre pour chacun des quatre composants ; JSONL
malformé, clé dupliquée, blanc, non-object, NaN, newline manquant ; racine
production/relative/symlink refusée ; EXECUTION_PENDING jamais FILLED ; absence
de certification contrefactuelle implicite et pertes certifiées inconnues.

Ces tests prouvent des comportements source dans ce périmètre, pas le runtime
actuel, les bytes historiques, les flags, la publication ou le fsync réel.
Le diff D1-C ne modifie aucun producteur runtime, configuration, stratégie,
risk/sizing/admission, epoch, PPL/FIN ni workflow de déploiement. L'auditeur
historique et les cinq fichiers #406 hérités ne sont pas modifiés. Aucun merge,
deploy, restart, accès exchange, écriture PPL/FIN ou feedback Research n'a eu lieu.

## Verdict et gate réelle

`D1_C_SOURCE_READY_FOR_REVIEW`, pour les hashes source ci-dessus, revue
indépendante encore requise. `REAL_BYTES_NOT_AVAILABLE` : appareil distant
Offline au relevé ~05:18 UTC ; aucun compte/permission/hash dataset réobservé.
Manifest réel attendu a57d64a69aa4c65df5d5c601a5d56b169a8e31e7f81fd9b39de6a277bfeeb657,
fenêtre [2026-10-10T00:00:00Z,2026-10-11T00:00:00Z), population réelle D1-C
NOT_OBSERVED. Dataset/source boundary NOT_PROVEN ; aucun identifiant O4 emprunté.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
