# Handoff scientifique D1-D → D1-E pour revue indépendante ChatGPT

## Résultat livré et frontière de preuve

La mission source-only a étendu la Draft [#409](https://github.com/3a7i3/crypto-ia-terminal/pull/409)
et créé la Draft [#411](https://github.com/3a7i3/crypto-ia-terminal/pull/411).
D1-D V2 comptabilise les tentatives natives sans écraser les réanalyses d'un même
cycle/symbole. D1-E vérifie la cohérence de receipts causales et de bytes fournis
entre construction d'observation et retour `fsync`. Aucun nouveau résultat réel
de complétude ou de durabilité n'est obtenu. La revue auteur est effectuée ;
la présente livraison demande une **revue indépendante**, pas une certification.

Décision permanente : **`PAPER_STRESS_RUNTIME_GO=DENIED`**.
Garde #286 : **ACTIVE** ; burn-in #282 protégé. Aucun merge GitHub, déploiement,
restart, accès VPS, export production, instrumentation de l'epoch active,
élévation `chatgpt-ro`, accès secret ou mutation runtime/config/epoch/PPL/FIN,
stratégie/risk/sizing/Watchdog/TESTNET/LIVE/exchange n'a été réalisé.

Les seuls writers employés sont les outils de développement local et les
écritures source autorisées sur branches/Draft PR. Le commit source gelé
`116634be0d3c015cce1cfa58be7da7255414fbfd` a été lu depuis Git, sans importer
ses modules de production. Ce SHA n'atteste pas le processus courant.

## Identités et dépendances à vérifier

| Objet | Identité observée / disposition |
|---|---|
| `main` | `2015a88f10c31e3379b569f864696d62c282b0f0`, vérifié sur GitHub, inchangé pendant les travaux |
| #405, contrat D0/D1 | Draft `2499891ab56bdd4dfb35e18ec7d471dddc2cb228`, non modifiée |
| #406, capture D1 | Draft `b99c2ed4f38ebeff481b5f470ed2d08e8e852257`, non modifiée |
| #407, D1-C | Draft `9e4bed4393caadc8f328f698c806f82fd91271e7`, non modifiée, non fusionnée |
| #409 au départ | `8f9ddc317821edb51f8685bbb802c516633158e4`, historique conservé |
| #409 livré | `d2a1cfa997d46c7d09ceffe93918df2ffeb9ca5b`, 2 commits ajoutés, sans force-push |
| Code D1-E testé | `58059ec41ca7fc0d11c0e5b1d996f26266015386` ; HEAD documentaire final à relever dans #411 |
| Composition test/fixture | `a68a775ae335913154b87847a8c43d6e9c0da84d`, correction bornée de l'isolation smoke et exemple/contrôle synthétiques ; hashes des modules inchangés |
| #411 | `research/paper-stress-404-d1-e` vers `main`, dépendance source explicite à #409 |
| Epoch de gouvernance | `BURN-IN-EPOCH-01-20260926T064144Z`, référence historique, pas binding natif de D1 |
| Config de gouvernance | `9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`, même limite |

Les 8 fichiers D1-D sont hérités sans modification dans #411. La cible `main`
permet l'exécution des workflows habituels ; elle ne rend pas #409 intégrée.
Lire séparément le diff `main…#409`, le diff `#409…#411` et la composition finale.
Il n'existe aucune dépendance source à #407 ; ses résultats historiques sont
une référence scientifique. Si l'un des HEAD/base évolue, refaire le tri de
dépendances et CI ; ne pas recycler une preuve comme si elle était actuelle.

## Faits D1-C conservés, sans nouvel audit réel

L'exécution historique D1-C V2 gouvernée, sortie 0, concernait une copie Research
immuable sous `chatgpt-ro`, fenêtre `[2026-10-10T00:00:00Z, 2026-10-11T00:00:00Z)`.

| Population capturée | Résultat historique |
|---|---:|
| DecisionPackets | 10 824 |
| REJECTED | 9 672 |
| EXECUTION_PENDING, **pas FILLED** | 1 152 |
| REJECTED LINKED | 5 486 |
| PROVEN_NOT_ELIGIBLE | 4 186 |
| ELIGIBLE_WITHOUT_OBSERVED_RECORD | 0 dans cette capture |
| UNKNOWN_ELIGIBILITY | 0 dans cette capture |

Les 4 186 exclusions portent `NATIVE_LSE_NON_ACTIONABLE`. Elles ne démontrent
pas des pertes d'écriture. Les timestamps naïfs de la capture restent une
limite historique ; le manifest indique un binding epoch non vérifié et ne
fournit pas les identités natives dataset/boundary nécessaires à la nouvelle
preuve. Le zéro capturé ne devient pas zéro parmi tous les appels/opportunités.

## Source nouvelle et garanties de méthode

| Artifact | Objet et limites |
|---|---|
| [D1_D_NATIVE_ATTEMPT_CONTRACT](D1_D_NATIVE_ATTEMPT_CONTRACT.md) | Roster indépendant, plan natif multi-tentatives, retours/no-packet/exceptions, fenêtres et gaps |
| [D1_D_TEST_REPORT](D1_D_TEST_REPORT.md) | Résultats locaux, versions, commandes et limites |
| [D1_E_DURABILITY_RECEIPT_CONTRACT](D1_E_DURABILITY_RECEIPT_CONTRACT.md) | États/transitions, filtres tri-state, cible listener, quatre bundles, clôture et durabilité |
| [D1_E_FROZEN_SOURCE_FORENSIC](D1_E_FROZEN_SOURCE_FORENSIC.md) | Empreintes et observations du code gelé, sans preuve runtime fraîche |
| [D1_E_SYNTHETIC_EXAMPLE](D1_E_SYNTHETIC_EXAMPLE.json) | Bytes d'entrée, pins et sortie reproductible **entièrement synthétiques** |
| [D1_E_TEST_REPORT](D1_E_TEST_REPORT.md) | Vérifications finales et premier échec général conservé |

Empreintes SHA256 des modules après le correctif demandé en revue indépendante (contrôles CI du nouveau HEAD à vérifier) :

| Module sous `research_data/` | SHA256 |
|---|---|
| `stress_d1_evidence_contract.py` | `22a46c388d6dee90582e6bc407f8dbfb39103c9125888d92e828306150393636` |
| `stress_d1_producer_attempts.py` | `6fdaac443bb19245801b2f54f0fae5daf2bb5a59430a6722bb2f31a4c33792b7` |
| `stress_d1_durability.py` | `1bc36290ccd29b8ed6192057e87d36040ecc92f3150c0a77206fa1b5bbb0e5e6` |

La V1 D1-D et ses 19 tests restent inchangés. V2 conserve séparément les unités
roster et tentative ; un plan vide pour une sélection reste inconnu. Les counts
de gaps peuvent compter plusieurs preuves manquantes pour un seul cas : ce ne
sont pas des counts de décisions perdues. D1-E compte uniquement son roster de
packets déclaré ; il ne remplace pas le dénominateur indépendant D1-D.

Les quatre bundles D1-E sont confrontés à leurs pins et boundary, aux identités
attempt/packet/trace/decision/observation, aux offsets/bytes exacts et à un témoin
`fsync` distinct. Les séquences natives, pas l'ordre des listes ou la proximité
temporelle, donnent la causalité. Aucun retour listener ou présence JSONL n'est
substitué à un retour `fsync`. La date de partition vient de sa sélection native,
pas de l'event time ; append et fsync peuvent franchir minuit.

## Points obligatoires de la revue indépendante

1. Vérifier les HEAD et SHA des modules, tous les commits/diffs/CI/reviews paginés.
   Distinguer les gates requises, workflows en cours, skips et CI historique.
2. Vérifier les deux équations de conservation D1-D et l'exclusivité D1-E ;
   contrôler les invocations supplémentaires, retries et réanalyses.
3. Challenger l'indépendance réelle du roster, du plan et des quatre sources.
   Des noms différents et des hashes corrects ne prouvent pas l'origine.
4. Examiner les retours précoces, exception avant packet, état inconnu, missing
   receipt, capture manquante et booléen persist ignoré par le listener.
5. Examiner la course executor/post-submit counter : V1 suppose une séquence
   causale native future, une livraison RejectionStore par tentative et un domaine
   UTC cohérent. Aucun assemblage de logs actuels n'est réputé la fournir.
6. Vérifier les critères absents, flags inconnus, prix bool/nonfini et la différence
   entre filtre natif et validation Research plus stricte ; ne pas fabriquer un
   défaut runtime constaté à partir de cette seule différence source.
7. Challenger descriptor/file-generation, offsets, bytes, partition-selection,
   événements tardifs, fences et prefixes. Le verifier ne rehashe pas les prefixes
   complets ; leur authenticité/continuité et la quiescence restent externes.
8. Distinguer fsync-return, succès persist, erreur close ultérieure, crash/power-loss
   et durabilité directory. Une chaîne synthétique cohérente ne prouve aucun des
   faits réels manquants et ne certifie aucun runtime.
9. Relire les deux échecs généraux puis le diagnostic de la séquence smoke →
   MarketScanner : les threads Universe échappaient aux fixtures et appelaient
   la factory factice du test suivant. Le correctif borne uniquement la fixture
   locale smoke (`UNIVERSE_ENABLED=false` dans pytest) ; aucune assertion
   MarketScanner, baseline ni source runtime n'est modifiée. Relire les résultats
   après correction sans effacer l'historique des échecs.
10. Confirmer que le diff source n'introduit aucun producteur déployé, service,
    consommateur runtime, admission, config, feedback Research ou autorité PAPER.

## Reproduction source-only

Résultats locaux : D1-D **56 tests** ; D1-E **109 tests** ; composition
Research/no-feedback/cross-stack **446 tests**, dont **96 cross-stack** ; contrôle
isolé et Ruff PASS. Au commit de composition `a68a775a`, le corpus général final
donne **7 160 PASS, 19 skips, 13 deselections, 2 xfails**, sortie 0, 94,24 s.
Les deux passages précédents avec 1 échec sont conservés et expliqués dans le
rapport ; aucun PASS final ne les efface. Python local 3.12.14, CI 3.11.

Avec une copie source isolée, Python compatible et les dépendances CI installées,
sans production ni secret :

```bash
git rev-parse HEAD
sha256sum research_data/stress_d1_evidence_contract.py research_data/stress_d1_producer_attempts.py research_data/stress_d1_durability.py
python -m pytest -q tests/research_data/test_stress_d1_producer_denominator.py tests/research_data/test_stress_d1_producer_attempts.py tests/research_data/test_stress_d1_durability.py
python -I -B tests/research_data/d1_isolated_source_check.py
python scripts/ci/ruff_baseline_gate.py check
BINANCE_TESTNET=true MARKET_SCANNER_SYNTHETIC=true \
  PYTHONPATH="$PWD/tests/research_stress/offline_guard" \
  python -m pytest -q -m 'not performance and not slow' tests/
python -m pytest -q tests/cross_stack/
git diff --check
```

Le contrôle `-I -B` charge uniquement les sources explicitement hashées avec une
enveloppe package synthétique, sans importer le checkout runtime, puis interdit
fichiers et sockets pendant les appels. C'est un **contrôle synthétique de
passivité**, pas un lanceur autorisé pour de vraies données. La garde réseau du
corpus général est une audit hook Python existante, pas un sandbox OS pour du
code natif hostile ; les tentatives Universe/MEXC échouées restent signalées.

## Disposition scientifique et suite permise

`D1_D_SOURCE_ACCOUNTING_CAPABILITY=FOR_REVIEW`
`D1_E_SOURCE_CHAIN_CAPABILITY=FOR_REVIEW`
`D1_D_REAL_PRODUCER_ROSTER=NOT_OBSERVED`
`D1_D_HISTORICAL_EARLY_RETURN_COUNT=UNKNOWN`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`ACTUAL_PERSISTENCE_PROOF=NOT_OBSERVED`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`D1_NATIVE_EPOCH_BOUNDARY_BINDING=NOT_PROVEN`
`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

La prochaine étape est la revue indépendante du HEAD source final et de ses
limites. Toute future collecte/staging Research ou instrumentation d'une future
epoch exige une mission/gate opérateur séparée avec custody, provenance native,
fences, indépendance et protocole de preuve. Rien dans ces Draft PR n'autorise
une activation PAPER-STRESS ni une modification du burn-in actif.


## Addendum de revue indépendante — overflow JSON et SHA corrigés

Les revues de #409 et #411 ont détecté un cas non couvert : un flottant JSON
`1e400` ou `-1e400` décodé en infini par Python malgré
`parse_constant`. Le parseur de bundles commun et le parseur de lignes JSONL
utilisent désormais un `parse_float` fail-closed, y compris pour un champ
numérique inutilisé. Les fixtures réépinglent explicitement les bytes et les
SHA/offsets/reçus physiques avant de tester le refus du nombre non fini.

Les trois SHA de la table ci-dessus représentent désormais les sources corrigées.
Le rapport antérieur (7160 PASS, 19 skips, 13 deselections, 2 xfails) reste une
**preuve historique** du HEAD Codex : ne pas l'attribuer aux nouveaux HEAD
sans consulter leurs propres workflows et/ou réexécuter localement. Le contrôle
isolé `d1_isolated_source_check.py` a été réépinglé sur les octets corrigés.

Toute hypothèse de nouvelle preuve réelle reste interdite : aucune custody,
roster producteur, reçu fsync ou rattachement native epoch n'est introduit.
`PAPER_STRESS_RUNTIME_GO=DENIED` ; Draft sans fusion ni déploiement.
