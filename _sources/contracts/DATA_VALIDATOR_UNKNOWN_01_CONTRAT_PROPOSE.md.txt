# DATA-VALIDATOR-UNKNOWN-01 — population et PnL inconnu

Mission [#351](https://github.com/3a7i3/crypto-ia-terminal/issues/351), issue mère
[#349](https://github.com/3a7i3/crypto-ia-terminal/issues/349), roadmap #285.
Base source examinée : `385b8c9cdd4f0f67fd58898ba18f6a37b5e308a4`, 2026-10-03 UTC.

**CONTRAT PROPOSÉ — NON IMPLÉMENTÉ.** Ce document prépare une correction source
future ; sa fusion ne modifie ni le validateur PAPER ni une gate opérationnelle.
Aucune observation VPS, aucun dataset Machine ouvert, aucune donnée immuable
réécrite. #286 reste actif ; le déploiement U8 conserve G0–G8.

## 1. Défaut et frontière d'autorité

`paper_trading/dataset_validator.py:521–535` transforme `pnl_usd=None` en `0.0`
puis compte une perte. Sur trois paires synthétiques +2 / -1 / None, le triage
#356 a observé W=1, L=2, WR=1/3, sans alerte. Cela ne prouve pas une contamination
des données réelles. La correction visée est une classification de preuves,
sans nouveau calcul de PnL et sans transfert de l'autorité FIN/PPL.

Le recorder distingue déjà `is_win=None` d'une perte (`recorder.py:495–499`) ;
son `summary()` exclut les résultats inconnus et les frais incomplets.
Son WR est un **pourcentage**, tandis que `CorpusReport.win_rate` est un
**ratio**. Aucun consommateur ne doit mélanger ces unités.

Les protections existantes pour `expired_on_restore` et
`pnl_fee_evidence_incomplete` doivent être conservées. Les schémas de TradeEvent
1–5, la définition des paires, l'horloge du corpus et l'intégrité lifecycle
restent hors correction.

## 2. Population proposée

Chaque paire reste dans `paired_trades`, y compris quand le résultat financier
n'est pas exploitable. Les diagnostics d'intégrité chronologique doivent être
examinés indépendamment des exclusions de performance : exclure un PnL ne doit
pas masquer une incohérence lifecycle.

Deux vues sont nécessaires : motifs financiers potentiellement recouvrants
(missing, non-finite, frais incomplets, restore) et partition primaire exclusive
pour vérifier les dénominateurs. Ordre proposé pour cette partition :

1. `expired_on_restore` : exclusion historique préservée ;
2. frais incomplets : exclusion préservée ;
3. PnL absent/None : `UNKNOWN`, aucune valeur de remplacement ;
4. PnL non numérique, booléen, NaN ou ±inf : preuve invalide, jamais gain/perte ;
5. PnL numérique fini et non exclu : résultat financièrement exploitable.

La vérification numérique n'accepte pas implicitement une chaîne ou un booléen.
L'absence historique du flag de frais conserve sa lecture actuelle ; elle ne
prouve pas rétroactivement des frais complets. Une nouvelle exigence de preuve
pour les anciens schémas exigerait une mission distincte.

Pour les cas structurellement valides :
`paired_trades = performance_count + excluded_count`.
Les motifs recouvrants ne doivent pas être additionnés pour obtenir cette égalité.
Les violations structurelles restent visibles et empêchent une certification
scientifique du corpus ; aucune paire n'est effacée pour rendre un résultat vert.

## 3. Zéro, dénominateurs et absence de population

La politique de compatibilité proposée conserve le résultat connu zéro comme
**non-gain** dans le dénominateur du WR, conformément au recorder existant.
Un compteur `flat_count` le distingue d'une perte strictement négative ;
`loss_count` conserve provisoirement son sens legacy « résultat connu <= 0 ».
Cette convention doit être affichée et documentée, sans renommer silencieusement
un champ existant ou modifier les consommateurs.

- `performance_count = win_count + loss_count` ;
- `negative_count = loss_count - flat_count` ;
- `win_rate = win_count / performance_count` quand ce dénominateur est positif ;
- aucun résultat certifiable : `win_rate=null`, statut `NOT_AVAILABLE`, jamais 0 ;
- TP/SL et durée sont calculés sur la même population admise, avec leurs propres
  compteurs de valeurs réellement disponibles ; une durée absente n'est pas zéro.

Les seuils historiques de WR/SL restent inchangés par cette proposition. Leur
validité statistique éventuelle est une autre mission. Le PnL à précision déjà
publiée n'est pas recalculé à partir du prix ou de frais supposés.

| Corpus synthétique | Population financière | Résultat attendu |
|---|---|---|
| +2 / -1 / None | 2 | W=1, L=1, UNKNOWN=1, WR=0,5 ; trois paires conservées |
| +2 / 0 / -1 | 3 | W=1, L=2 dont flat=1, negative=1, WR=1/3 |
| None uniquement | 0 | UNKNOWN=1, WR=null, NOT_AVAILABLE |
| NaN / +inf / -inf | 0 | trois preuves invalides, aucun gain/perte, alertes explicites |
| +2 avec frais incomplets | 0 | exclusion frais conservée, aucun gain certifié |
| 0 avec expired_on_restore | 0 | exclusion restore conservée ; zéro non admis |
| None avec frais incomplets | 0 | motif primaire frais, motif UNKNOWN également visible ; une seule exclusion |
| clôture avant ouverture avec None | 0 | UNKNOWN et violation chronologique visibles simultanément |
| aucune paire | 0 | pas de performance disponible, aucune admission implicite |

## 4. Éligibilité et métadonnées : migration explicite requise

Aujourd'hui `burnin_eligible` dépend seulement de l'absence de violations.
Il est lu par `scripts/prelive_gate.py:gate_c_dataset`,
`scripts/runtime_validator.py` et `scripts/validate_trade_dataset.py`.
Le script de validation utilise aussi ce booléen comme code de sortie.
Le champ ne constitue pas une autorisation de déploiement ou de nouvelle epoch.

Ne pas changer son sens en même temps qu'un simple compteur UNKNOWN.
Proposition : exposer séparément intégrité structurelle et disponibilité de la
performance, puis faire examiner une éventuelle modification d'admission et ses
consommateurs dans une gate distincte. Une performance de sous-population doit
porter sa couverture et ses exclusions ; elle ne certifie pas tout le corpus.
La taille suffisante et la fin du burn-in restent des décisions gouvernées.

Les métadonnées actuelles sont `schema_version=1`, avec ratios arrondis mais sans
compteurs W/L ni dénominateur financier. Proposition **schema_version=2** :
compteurs W/L/flat/negative, performance/exclusions, motifs, statut de disponibilité,
unités, convention du zéro et lien explicite à la frontière source examinée.
Les valeurs absentes restent null ; JSON strict, aucun NaN/Infinity publié.
Ne pas réécrire les fichiers v1 immuables. Les lecteurs doivent reconnaître v1/v2,
conserver v1 comme historique et ne pas en déduire une population financière
certifiée. Aucun adaptateur ni writer n'est modifié par ce document.

## 5. Gates de correction future et rollback

Avant patch métier : admission explicite du scope source PAPER sensible sous
#286, revue de la convention du zéro, du schéma v2 et de l'éligibilité séparée,
inventaire complet des lecteurs de métadonnées et des consumers dynamiques.
L'inventaire statique ci-dessus ne prétend pas être une preuve runtime complète.

Validation future : matrice ci-dessus sur corpus temporaires seulement ; preuve
avant/après pour +2/-1/None ; conservation des tests REM-C R1.1/R1.3, restore,
chronologie, chemins tardifs, paires, metadata et gates. Aucun skip ou changement
de baseline pour masquer le défaut. Vérifier l'absence d'import/writer actif dans
les API et les projections ; aucune reconstruction de vérité côté frontend.

Rollback source : revert du futur commit admis, sans accès VPS ni modification
Advisor/epoch/dataset. Le rollback ne transforme jamais les anciennes preuves
v2 en v1 ; conserver leurs identités et portée. Déploiement et migration runtime
restent des missions séparées explicitement autorisées.

Verdict documentaire : `DATA_VALIDATOR_UNKNOWN_01_CONTRACT_PROPOSED_NOT_IMPLEMENTED`.
La mission #351 reste ouverte après cette proposition ; le défaut n'est pas corrigé.
