# PROMPT — REST-004 · Adapter les tests REST + gardes anti-régression

> Ticket **NON GATED**. Fichiers de test uniquement. **N reste inchangé.**
> **Dépendances dures : `REST-002` et `REST-003` terminés.**

## MISSION

Mettre les tests du loader REST en accord avec le contrat établi par `REST-001`/`002`/`003`, et ajouter
**trois tests de garde** interdisant le retour des littéraux figés.

## CONTEXTE

Avant ce chantier, `visualization/api/portfolio_api.py` publiait :
- huit métriques **écrites en dur à 0** (`:22-29`) : `n_trades`, `n_wins`, `n_losses`, `win_rate_pct`,
  `profit_factor`, `expectancy_pct`, `max_drawdown_pct`, `sharpe` ;
- `total_pnl_usd = open_pnl_usd` (`:30`) — le PnL **ouvert** publié dans un champ lu comme PnL **total**.

`REST-002` a supprimé la recopie ; `REST-003` a remplacé les littéraux par des lectures de la source
unique arbitrée par l'ADR `REST-001`, ou par `null`.

`tests/visualization/test_snapshot_only_loaders.py` validait le comportement **tel qu'il était** — donc
potentiellement les littéraux figés. Après `REST-002`/`003`, certaines de ses assertions sont fausses.

Sans test de garde, rien n'empêche un futur contributeur de réintroduire `win_rate_pct=0.0` « pour faire
passer un test ». Le défaut corrigé doit devenir **impossible à recréer silencieusement**.

## OBJECTIF

Les tests reflètent le nouveau contrat, et trois gardes rendent la régression détectable.

## CONTRAINTES

- Maximum 2 fichiers, **tous sous `tests/`**. Aucun fichier de production.
- Chaque garde doit **échouer** sur le code d'avant `REST-002`/`003`. Une garde qui passe aussi sur le
  code bugué ne garde rien.
- Aucune assertion ne doit attendre `0` pour un champ indisponible (ce serait figer INV-R6 à l'envers).

## INVARIANTS

- **INV-1** passivité · **INV-2** aucun reset de N · **INV-3** `paper_trades.jsonl` intact ·
  **INV-4** aucun seuil modifié.
- **INV-R2** — aucun recalcul de métrique, y compris dans les tests.
- **INV-R6** — un test n'asserte jamais qu'un champ indisponible vaut `0`.

## FICHIERS

| Fichier | Action |
|---|---|
| `tests/visualization/test_snapshot_only_loaders.py` | Adaptation + 3 gardes |
| *(éventuel)* 1 autre fichier de test | Si un autre test asserte les 8 champs |

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q`.
2. Lire le fichier de test et identifier les assertions devenues fausses après `REST-002`/`003`.
3. Adapter ces assertions au contrat de l'ADR `REST-001` (champs publiés vs champs `null`).
4. Ajouter les trois gardes :
   - **G1 — pas de littéraux figés** : pour chacun des 8 champs, asserter qu'il vaut `null` **ou** qu'il
     provient de la source nommée ; interdire le cas « `0.0` sans source ».
   - **G2 — `total_pnl` ≠ `open_pnl`** : asserter `total_pnl_usd != open_pnl_usd` **ou** `total_pnl_usd is None`.
   - **G3 — provenance publiée** : asserter que le champ de provenance existe et nomme une source.
5. **Vérifier que les gardes échouent sur le code antérieur** : par `git stash` ou sur une copie de
   travail, sans commit. C'est l'étape la plus importante du ticket.
6. Lancer la suite complète, comparer à la baseline. Commiter.

## CHECKLIST

- [ ] Baseline relevée
- [ ] Assertions devenues fausses identifiées et adaptées
- [ ] G1, G2, G3 écrites, nommées explicitement, documentées d'une ligne chacune
- [ ] **Les trois gardes échouent sur le code d'avant `REST-002`/`003`** (vérifié, étape 5)
- [ ] Aucune assertion n'attend `0` pour un champ indisponible
- [ ] `git diff --name-only` ne liste que des chemins sous `tests/`

## TESTS

```bash
python -m pytest tests/visualization/ -q
python -m pytest tests/ -q
```

Attendu : **zéro échec**.

## VALIDATION

**Done si :** les trois gardes existent et passent ; elles échouent sur le code antérieur (vérifié) ;
aucun fichier de production modifié ; suite complète verte.

**Refus si :** une garde passe aussi sur le code bugué ⇒ **refus** (tautologique) ; un fichier de
production apparaît au diff ; une assertion attend `0` pour un champ indisponible ; un test étranger au
périmètre a été modifié pour le faire passer.

## LIVRABLES

- 1 à 2 fichiers sous `tests/`.
- Commit :

```
test(api): gardes contre le retour des metriques figees

Adapte les assertions du loader REST au contrat de l'ADR REST-001 et
ajoute trois gardes : pas de litteraux figes, total_pnl != open_pnl,
provenance publiee. Les trois echouent sur le code d'avant REST-002/003.

Fichiers de test uniquement. N inchange.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `REST-004` en **TERMINE**.

## STOP CONDITIONS

- `REST-002` ou `REST-003` ne sont pas terminés ⇒ **ne pas démarrer** (dépendances dures).
- Une garde ne peut pas être rendue discriminante (elle passe dans les deux cas) ⇒ **STOP** : cela
  signifie que le contrat publié n'est pas observable depuis les tests, ce qui doit être remonté.
- Un test étranger casse ⇒ **ne pas le corriger**, le signaler.

## INTERDICTIONS

- Ne modifier aucun fichier de production.
- Ne pas calculer de métrique dans un test pour « vérifier » une valeur publiée.
- Ne pas affaiblir une garde pour la faire passer.
- Ne pas modifier un test étranger au périmètre.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
- Ne pas déployer.
