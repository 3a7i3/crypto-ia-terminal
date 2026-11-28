# MEO-03 — Lecture descriptive du flux de transactions (V0.1)

**Décision opérateur.** GO MEO-03 V0.1 du 2026-11-28, plan `CAT_MEO_03_PLAN_V0.1.md` (SHA-256 `4747d4c8…`).

**Cadre.**
- Contrat scientifique B02 v0.2 (`5b639caa…`).
- `INSTRUMENT_ADMISSION` = PROBATION pour l'usage TRADE_FLOW (MEO-02 RV01).
- Développement et évaluation hors ligne autorisés en PROBATION.
- Aucune lecture ne revendique ADMITTED_PARTIAL.

## Source et réutilisation

La lecture est une projection pure du rapport de rejeu MEO-01 (`meo-01-trades-report/1`) :

- **Calculs repris sans recalcul.** Les barres d'une minute, le Delta 300 s et le CVD avec son segment viennent de `trades.build_bars` et `trades.rolling_delta`, via `kraken_trades.replay_journal`.
- **Seuls ajouts.** Le module ajoute :
  - les signes ;
  - la règle DESALIGN-1 ;
  - un contrôle de cohérence : la somme des volumes acheteur, vendeur et inconnu des minutes doit égaler le volume total de la fenêtre, sinon refus `WINDOW_VOLUMES_INCONSISTENT`.
- **Implémentation.** Le code est dans `observability/market_flow/meo_reading.py` (pur). Il est appelé par `python3 -m observability.meo_trades_replay read DIR --out FILE`, qui écrit dans un nouveau fichier et n'écrase jamais.

## Marquage obligatoire

Chaque lecture porte les champs suivants :
- `admission.instrument_admission=PROBATION`, `use=TRADE_FLOW`, `claims_admitted_partial=false` ;
- `time_basis=UNATTESTED`, `axis=NATIVE`, `qualification=CONDITIONAL_ON_UNPROVEN_NATIVE_UTC_ALIGNMENT` ;
- `quality.state=DEGRADED`, avec ses motifs ;
- `corpus_ref` : empreintes du journal, empreinte du code de capture et SHA-256 du rapport source.

Nature de la preuve :
- Un rapport `OBSERVATION` non synthétique est projeté `HISTORICAL`, avec `source_evidence_kind=OBSERVATION` (décision MEO-02 RV01).
- Un rapport SYNTHETIC reste SYNTHETIC.
- Toute autre nature est refusée.

## Unité et définitions

L'unité de lecture est la fenêtre de 5 minutes du rapport, sur l'axe natif. Les minutes
sont reproduites comme détail descriptif. À l'intérieur d'une minute, l'ordre des trades
suit seulement le trade_id.

Fenêtre COVERED :
- `price_first` est l'ouverture de la première minute OBSERVED ; `price_last` est la clôture de la dernière.
- `price_change = price_last − price_first`, en décimal exact. Aucune variation relative en V0.1.
- Totaux, volumes acheteur, vendeur et inconnu, Delta 300 s avec ses bornes.
- `cvd_end` et `cvd_end_bounds` sont ceux de la dernière minute, tels que le moteur source les publie. `cvd_segment` est le numéro du moteur ; `cvd_anchor_ns` est le début de la première minute de ce segment.

Fenêtre non COVERED : toutes les valeurs sont `null` et l'alignement vaut UNKNOWN. Une valeur inconnue n'est jamais 0.

## Règle DESALIGN-1 v1 (sans seuil)

**Signes**
- Signe du prix : `+`, `−` ou `0` selon `price_change` ; `?` sans prix.
- Signe du flux, d'après les bornes du Delta `[lo, hi]` :
  - `+` si `lo > 0` ;
  - `−` si `hi < 0` ;
  - `0` si `lo = hi = 0` ;
  - `?` sinon.

**État d'alignement**

| prix \ flux | + | − | 0 | ? |
| --- | --- | --- | --- | --- |
| + | ALIGNED | DIVERGENT | FLAT_FLOW | UNKNOWN |
| − | DIVERGENT | ALIGNED | FLAT_FLOW | UNKNOWN |
| 0 | FLAT_PRICE | FLAT_PRICE | FLAT | UNKNOWN |
| ? | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Une fenêtre de moins de deux transactions vaut UNKNOWN (`FEWER_THAN_TWO_TRADES`), même si
sa variation arithmétique est nulle.

**Premier désalignement**
- C'est la première fenêtre DIVERGENT, dans l'ordre de l'axe natif, à l'intérieur d'un segment de couverture. La recherche repart dans chaque segment.
- Fenêtres exclues de la recherche (décision M3), avec leur motif :
  - `PRE_SUBSCRIPTION` : fenêtre antérieure à l'accusé d'abonnement ;
  - `OVERLAPS_SUBSCRIPTION` : fenêtre qui chevauche l'accusé ;
  - `TRANSPORT_NOT_CONTINUOUS` : fenêtre sans continuité du transport ;
  - `NO_SUBSCRIPTION_ACK` : aucun accusé reçu.
- Les fenêtres exclues restent lues et listées dans `divergent_windows`.
- La comparaison entre les bornes natives et l'accusé de réception est conditionnelle.

`first_desalignment.meaning = FIRST_OBSERVED_NOT_FORMATION_INSTANT` : un premier
désalignement observé n'est pas un instant de formation démontré.

## Limites

- Lecture descriptive : aucune cause, aucune prédiction, aucun seuil.
- La règle ne mesure ni l'ampleur ni la persistance.
- Aucune comparaison entre captures.
- Aucune heure UTC n'est affirmée.

## Tests

`tests/meo_03/` couvre :
- R1 : fenêtres non couvertes ;
- R2 : table de vérité et cas de moins de deux transactions ;
- R3 : côté inconnu (B02 V09) ;
- R4 : ancre et valeurs du CVD, recherche par segment ;
- R5 : exclusions M3 ;
- R6 : deux lectures identiques à l'octet ;
- R7 : sommes égales au rapport, refus d'incohérence ;
- R8 : marquage et nature de la preuve ;
- R9 : pureté du module et consommateur unique.

Toutes les entrées de test sont SYNTHETIC.
