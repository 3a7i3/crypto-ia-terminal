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

## Seconde revue — correctifs de chargement isolé (2026-10-11 UTC)

Les résultats V1 ci-dessus restent historiques. Source V2 testée :
`f4c816e4e9679757726aa972f642aa86666785b0`, basée sur le HEAD #407 revu
`f18b4ba27f012193a2d0c25485429c384298c239`. Le commit de rapport suivant
ne modifie que la documentation ; les hashes ci-dessous identifient exactement
les sources exécutées. Environnement local inchangé : Python 3.12.14,
pytest 9.1.1, Ruff 0.15.8, Linux Research ; CI Python 3.11.

| Fichier | SHA-256 V2 |
|---|---|
| Lanceur autonome | `579bff90b9e2aa89885e4e64056f91c31233adf31942f344e2907cd8a36d4e25` |
| Classificateur | `96f1f13e814190860adc69ccae2c868df6a0c3acd8b072b995ef1cd902224e47` |
| Tests nouveaux de chargement | `aef84154c63b0cb5e63bc38679c0b91716248db43a6be891e687acbf7e64a224` |
| Auditeur historique inchangé | `11d3e13e90e04446f6d1fc5bff4840103fa4f23e2865a211e8b5f77771b94494` |

Commandes exactes et résultats locaux :

```bash
python -m pytest -q tests/research_data/test_stress_d1_isolated_runner.py tests/research_data/test_stress_d1_rejection_eligibility.py
# 86 PASS, 0 échec, 0 skip (24 nouveaux + 62 existants)

python -m pytest -q tests/research_data/test_stress_d1_isolated_runner.py tests/research_data/test_stress_d1_rejection_eligibility.py tests/research_data/test_stress_d1_capture.py tests/test_rejection_store.py tests/test_decision_observation.py tests/test_s03b_provenance.py tests/test_decision_event_bus.py tests/test_decision_packet_confidence.py
# 164 PASS, 0 échec, 0 skip, 3 avertissements

python -m pytest -q tests/research_data tests/research_replay tests/research_diag tests/research_candidate tests/paper_trading/test_rb3_burn_in_epoch_identity.py tests/test_rb3_burn_in_config_freeze.py tests/test_herm_02_test_persistence_isolation.py
# 264 PASS, 0 échec, 0 skip, 399 avertissements

python -m pytest -q tests/cross_stack/
# 96 PASS, 0 échec, 0 skip, 1 avertissement

ruff check research_data/stress_d1_isolated_runner.py research_data/stress_d1_rejection_eligibility.py tests/research_data/test_stress_d1_isolated_runner.py
# PASS
python scripts/ci/ruff_baseline_gate.py check
# PASS : baseline 957, actuels 945, 0 nouvelle violation ; baseline inchangée
python -m py_compile research_data/stress_d1_isolated_runner.py research_data/stress_d1_rejection_eligibility.py tests/research_data/test_stress_d1_isolated_runner.py
# PASS (compilation locale seulement ; le lanceur gouverné conserve -B)
git diff --check
# PASS
```

Les nouveaux contrôles prouvent : chargement des bytes vérifiés, liaison du module
réel, substitution même sans attributs, mauvais __file__/origine, fichier modifié,
mauvais digest classificateur/historique avant exécution, symlink, racine non
Research, fichier/répertoire non root-owned ou writable, audit package sans
provenance refusé avant lecture, package absent sous `-I -B`, lanceur autonome
utilisable depuis cwd sans package, aucune extension sys.path, PYTHONPATH ignoré,
absence de bytecode, invocation sans options isolées refusée.

Le harness positif isolé remplace la custody OS du tempfile synthétique pour
CI non-root ; il conserve les contrôles SHA et ne lance aucun audit réel.
Les tests de custody sont séparés. Cette substitution de test n'est pas une
option publique ni une validation de custody distante. Premier passage :
85 PASS / 1 échec du contrôle sans -I, dû au shadowing stdlib par le répertoire
de script ; le lanceur a été corrigé pour refuser avant ces imports. Nouveau
passage complet : 86 PASS. Aucun test retiré, aucun baseline modifié.
Aucun mypy/pyright configuré dans le périmètre CI inspecté ; aucun PASS de
vérification de types revendiqué.

Device status recontrôlé le 2026-10-11 UTC, avant 05:59:34 UTC : crypto-advisor-2 Offline.
Compte `chatgpt-ro`, permissions, bytes réels et exit code réel non observés.
`D1_C_REAL_BYTES_NOT_AVAILABLE` ; classification réelle `NOT_OBSERVED`.
Manifest attendu et fenêtre UTC restent ceux de la preuve historique, sans
nouvelle attestation de dataset/source boundary ni complétude producteur.
Les partitions synthétiques ne sont pas des métriques réelles des 4 186 packets.

Verdict source : `D1_C_SOURCE_READY_FOR_REVIEW`, seconde revue indépendante
requise sur le nouveau HEAD. La CI doit être observée au HEAD final dans la PR,
sans transposer les résultats d'un ancien commit ni compter des jobs pending
ou skipped comme PASS. Aucun merge ni déploiement.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Suite générale supplémentaire sur les mêmes sources V2 :

```bash
python -m pytest -q -m 'not performance and not slow' tests/
# 7092 PASS, 19 SKIPPED, 13 DESELECTED, 2 XFAIL, 0 échec,
# 2139 avertissements, 143.91 secondes ; processus terminé exit 0.
```

Limite observée : après le résumé pytest, un avertissement du service Universe
existant mentionne `mexc GET .../exchangeInfo` échoué, univers inchangé.
Cette suite générale n'est donc **pas une preuve d'absence de tentative réseau**.
Aucun accès réussi, byte exchange, ordre ou mutation distante n'est attesté par
ce message. Le périmètre précis de cette tentative n'a pas été certifié ; ne
pas présenter toute la suite générale comme strictement offline. Les sources
runtime ne sont pas modifiées pour corriger un effet hors scope. Aucun rerun
réseau supplémentaire effectué ; les nouveaux tests D1-C exécutent uniquement
les fixtures locales et ne lancent pas ce service. Les skips, xfails et
avertissements restent distincts des PASS.
