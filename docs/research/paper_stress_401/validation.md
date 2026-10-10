# Validation source-only

Environnement de recherche indépendant : Linux, CPython 3.12.14,
pytest 9.1.1, Ruff 0.15.8. Cible CI du dépôt : Python 3.11, non substituée par
cette preuve locale. Dépendances existantes installées dans un venv hors repo ;
aucune dépendance du dépôt modifiée. Base main :
`b751333e53c8c341d8a4a64af82499bc03140210`.

| Contrôle local | Résultat |
|---|---|
| nouveaux tests `tests/research_stress` | 27 PASS |
| Research/replay/data/diag/candidate/FIN | 282 PASS, 399 avertissements legacy |
| Python cross-stack | 96 PASS, 1 avertissement legacy |
| Ruff baseline différentiel | 0 nouveau constat ; baseline inchangée |
| `git diff --check` | PASS |
| garde réseau opt-in, DNS/connexion externes | smoke PASS, exceptions contrôlées |

La première exécution complète a donné 6 991 PASS, 19 skipped, 13 deselected,
2 xfailed, 2 139 avertissements. Un observer legacy y a tenté une lecture publique
MEXC qui a échoué ; aucune donnée n'a été utilisée. Ce run n’est **pas** revendiqué
comme preuve de réseau strictement offline. Le run final avec garde opt-in est
consigné ci-dessous après son achèvement.

Les tests nouveaux vérifient : neuf cellules et 648 scénarios analytiques,
calcul indépendant d’une perte connue, contexte décimal de l’appelant neutralisé,
identités source/config, déterminisme byte-identical, refus de JSON dupliqué/NaN,
protocole actif refusé, coûts incomplets refusés, politique stale fail-closed,
altération de résultat refusée même après rehash, corruption dataset refusée,
replay factuel et maintien de UNRESOLVED, non-mutation des copies/protected fixture,
imports/calcul sous interdiction écriture/réseau/process, CLI stdout déterministe.

Les skips/xfails legacy ne sont pas des PASS. Aucun test performance/slow rejoué,
aucun frontend modifié. Aucun critère scientifique de puissance/OOS/runtime prouvé
par ces tests. Le guard CPython n’est pas un sandbox natif contre du code hostile.
Les hashes des modules exécutés et le SHA source sont dans `source_manifest.json` ;
les rapports génèrent leurs identités avec ce SHA et sans chemin/horloge/hostname.
GitHub CI à vérifier au HEAD final de la Draft PR ; aucun succès d’un ancien SHA
n’est réutilisé comme résultat de la PR.
