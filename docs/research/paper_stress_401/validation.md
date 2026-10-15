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
comme preuve de réseau strictement offline. Le second run avec garde réseau seul a donné 6 989 PASS et **2 échecs**
(`test_market_scanners_share_exchange_instance`,
`test_market_scanner_preloads_markets_once_per_shared_exchange`) : un observer
PerpUniverse local non isolé boucle après refus réseau et crée des instances
pendant les mocks ccxt. Ce résultat n’est pas présenté comme vert ; le processus
de test local a été interrompu après la synthèse pytest.

Le flag existant UNIVERSE_ENABLED=false, uniquement pour le processus de tests,
isole cet observer sans modifier de source runtime ou de test historique.
Le probe scanner/Advisor/universe/nouveaux tests avec garde + flag : 75 PASS.
Le run complet final avec garde + flag : **6 991 PASS, 19 skipped,
13 deselected, 2 xfailed, 2 139 avertissements, exit 0, 131,04 s**.
Les 27 nouveaux tests repassent également sous garde réseau.
Les modules/protocole/tests ont exactement les empreintes du SHA source
`76179d8c851f318d855bcb7cd70c45681619265e` ; le commit de preuves n’en change
aucun. Recalcul des 648 scénarios, hash du rapport et identité : MATCH.
Arbres source protégés versus base main : identiques (voir manifest).
Liens locaux des cinq rapports : PASS.
Cela ne certifie pas la découverte marché legacy : seule l’isolation du corpus
source-only est recherchée ; pas de suppression/skip additionnel de tests.

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
