# PROMPT — REST-001 · ADR de source unique pour les métriques publiées par l'API

> Ticket **NON GATED**, **documentaire**. Aucun `.py`. **N reste inchangé.**

## MISSION

Rédiger l'ADR qui tranche **une seule** source pour les métriques publiées par l'API REST, et démontre,
champ par champ, que ce choix **ne crée aucun recalcul supplémentaire**.

## CONTEXTE

`visualization/api/portfolio_api.py:22-29` construit `PortfolioSnapshot`
(`visualization/api/models.py:69`) avec huit valeurs **écrites en dur** :

```
n_trades=0, n_wins=0, n_losses=0, win_rate_pct=0.0,
profit_factor=0.0, expectancy_pct=0.0, max_drawdown_pct=0.0, sharpe=0.0
```

Elles ne sont jamais calculées. Le dashboard affiche donc `win_rate = 0 %` alors que
`PaperLedger.summary()` (`paper_trading/ledger.py:191`) mesurait 28 % sur la même session.

Producteurs réels existants, recensés par l'audit :
- `paper_trading/ledger.py:191` — `n_trades`, `win_rate`, `max_drawdown_pct`, `capital`, `total_fees_usd` ;
- `analysis/base.py:88` (`win_rate`) et `:125` (`max_drawdown`) — **lignée scientifique**, réservée aux
  tests d'hypothèses, **à ne pas appeler depuis l'API** ;
- `certification/operator_signoff.py:46` — `paper_max_dd`, `paper_win_rate` — quatrième lignée ;
- `observability/system_snapshot.py:56`, `:132`, `to_dict:143` — snapshot persisté.

L'audit SSoT classe `win_rate` et `drawdown` en **FAIL** avec ≈5 producteurs chacun. Le risque de ce
ticket est donc précis : **en créer un sixième** en calculant les métriques dans l'API.

Contrainte d'époque : `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` (`scripts/data_quality.py`, alias
`CLEAN_DATA_SINCE_ACTIVE`). Une métrique publiée sans borne mélange les époques V3 et V4.

## OBJECTIF

Un ADR qui nomme **une** source (une seule, avec `fichier:ligne`), liste les champs qu'elle fournit
tels quels, liste ceux qui seront publiés `null`, et démontre qu'aucun champ n'est « à calculer ».

## CONTRAINTES

- Documentation seule. Aucun `.py`, aucun test, aucune configuration.
- Deux critères **éliminatoires** dans la grille de décision : **zéro recalcul ajouté** et
  **borne d'époque applicable**.
- Un champ qu'aucun producteur existant ne fournit est publié `null` — jamais calculé dans l'API,
  jamais `0`.

## INVARIANTS

INV-1 à INV-4, trivialement respectés (aucun code touché).
**INV-R2** — aucun recalcul créé dans la couche API. **INV-R4** — borne d'époque tranchée explicitement.
**INV-R6** — `null`, jamais `0`. **INV-R8** — provenance publiée avec la métrique.

## FICHIERS

| Fichier | Action |
|---|---|
| `docs/adr/00XX-....md` | Création (numéro ≥ 0019, ou suivant si `GOV-001` en a pris un) |

## ETAPES

1. Lire `visualization/api/portfolio_api.py` en entier ; relever ce que contient réellement l'objet
   `portfolio` passé à l'endpoint (`:30`, `:33`).
2. Lire `paper_trading/ledger.py:191` `summary()` ; lister exactement les champs retournés.
3. Lire `observability/system_snapshot.py:56`, `:132`, `:143` ; lister les champs du snapshot persisté,
   son producteur et sa fréquence d'écriture.
4. Pour chaque candidat, vérifier si la borne `CLEAN_DATA_SINCE_ACTIVE` est appliquée.
5. Inventorier les consommateurs de l'endpoint et leur tolérance à `null`.
6. Remplir la grille C1 → C5 : C1 zéro recalcul (**éliminatoire**) · C2 borne d'époque (**éliminatoire**)
   · C3 lecture atomique · C4 couverture de champs · C5 coût. Trancher.
7. Rédiger l'ADR, avec la table **champ → producteur existant** couvrant les 8 champs de `:22-29`
   **plus** `total_pnl_usd` (`:30`), chaque case valant un `fichier:ligne` ou `NULL`.
8. Commiter.

## CHECKLIST

- [ ] Les deux candidats sont décrits (champs fournis, champs absents, fraîcheur, atomicité, borne)
- [ ] La grille C1 → C5 est remplie
- [ ] **Une seule** source est retenue, avec `fichier:ligne`
- [ ] La table champ → producteur couvre les 9 champs
- [ ] Aucune case ne vaut « à calculer dans l'API »
- [ ] La question de la borne d'époque est tranchée explicitement
- [ ] Deux falsificateurs de la décision sont énoncés
- [ ] Aucun `.py` au diff

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : identique à la baseline (aucun fichier de code touché).

## VALIDATION

**Done si :** l'ADR nomme une source unique ; la table champ → producteur est complète ; les champs
non couverts sont listés comme `null` ; la borne d'époque est tranchée ; deux falsificateurs figurent.

**Refus si :** l'ADR retient deux sources ou laisse le choix ouvert (le ticket existe pour trancher) ;
une case vaut « à calculer dans l'API » ; un champ indisponible est décidé à `0` ; la borne d'époque
n'est pas tranchée ; un `.py` apparaît au diff.

## LIVRABLES

- 1 fichier sous `docs/adr/`.
- Commit :

```
docs(adr): source unique des metriques publiees par l'API

Tranche une source unique pour les 8 metriques figees de
portfolio_api.py:22-29 et pour total_pnl_usd (:30). Table champ ->
producteur existant ; champs non couverts publies null, jamais calcules
dans l'API. Borne d'epoque tranchee.

Documentation seule.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `REST-001` en **TERMINE**.

## STOP CONDITIONS

- Aucun candidat ne satisfait les deux critères éliminatoires ⇒ **STOP** et remontée : la décision
  serait alors « tous les champs sont `null` », ce qui doit être validé par l'opérateur.
- Une source semble idéale mais n'applique pas la borne d'époque ⇒ ne pas la retenir en silence :
  le documenter comme un défaut connu et trancher explicitement.

## INTERDICTIONS

- Ne toucher aucun `.py`, test ou configuration.
- Ne pas appeler `analysis/base.py` depuis l'API : c'est la lignée scientifique, pas une source de publication.
- Ne pas retenir deux sources.
- Ne pas enchaîner sur `REST-003`. **S'arrêter après le commit.**
- Ne pas déployer.
