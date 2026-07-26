# PROMPT — REST-003 · Remplacer les 8 littéraux figés de `portfolio_api.py:22-29`

> Ticket **NON GATED**. Couche de publication HTTP, lecture seule côté décision. **N reste inchangé.**
> **Dépendance dure : `REST-001` doit être terminé.**

## MISSION

Publier `n_trades`, `n_wins`, `n_losses`, `win_rate_pct`, `profit_factor`, `expectancy_pct`,
`max_drawdown_pct` et `sharpe` depuis la source unique arbitrée par `REST-001`, ou `null` pour les
champs qu'aucun producteur existant ne fournit.

## CONTEXTE

`visualization/api/portfolio_api.py:22-29` construit `PortfolioSnapshot`
(`visualization/api/models.py:69`) avec huit **constantes littérales à 0** :

```
n_trades=0, n_wins=0, n_losses=0, win_rate_pct=0.0,
profit_factor=0.0, expectancy_pct=0.0, max_drawdown_pct=0.0, sharpe=0.0
```

Le dashboard affiche donc `win_rate = 0 %` alors que `PaperLedger.summary()`
(`paper_trading/ledger.py:191`) mesurait 28 % sur la même session. Deux surfaces du même système
publient deux vérités incompatibles.

L'audit SSoT classe `win_rate` et `drawdown` en **FAIL** avec ≈5 producteurs concurrents chacun
(`paper_trading/ledger.py:191`, `analysis/base.py:88` et `:125`,
`certification/operator_signoff.py:46`, `system/integrity_snapshot.py`, l'API elle-même).

**Le risque central de ce ticket est d'en créer un sixième.** La tentation d'un `sum()` local est
directe. `REST-001` a tranché la source précisément pour l'éviter.

## OBJECTIF

Aucun des 8 champs n'est un littéral figé. Chaque champ publié est traçable à un producteur existant
par `fichier:ligne`. Les champs non couverts valent `null`.

## CONTRAINTES

- Maximum 2 fichiers, environ 60 lignes.
- **Aucune arithmétique** dans `visualization/` : ni `sum(`, ni `/`, ni `mean`, ni écart-type,
  ni boucle sur un historique de trades.
- La provenance (source, borne d'époque, horodatage) doit être publiée avec les métriques.

## INVARIANTS

- **INV-1** passivité · **INV-2** aucun reset de N · **INV-3** `paper_trades.jsonl` intact ·
  **INV-4** aucun seuil modifié.
- **INV-R2** — **zéro recalcul ajouté** (invariant central du ticket).
- **INV-R4** — borne d'époque appliquée ou son absence documentée.
- **INV-R6** — `null`, jamais `0`. **INV-R8** — provenance publiée.

## FICHIERS

| Fichier | Action |
|---|---|
| `visualization/api/portfolio_api.py` | Lignes 22-29 + champ de provenance |
| *(éventuel)* `visualization/api/models.py` | Si un champ doit devenir optionnel |

## ETAPES

1. Relire l'ADR produit par `REST-001` ; en extraire : source retenue, champs fournis, champs `null`.
   **Sans cet ADR, le ticket n'est pas démarrable.**
2. Relever la baseline : `python -m pytest tests/ -q`.
3. Remplacer les 8 littéraux par des lectures de la source retenue, ou par `null`.
4. Ajouter le champ de provenance (source, borne d'époque, horodatage) — INV-R8.
5. Relire le fichier et vérifier qu'**aucune** opération arithmétique n'a été introduite.
6. Contrôle de cohérence croisée : la valeur publiée pour `win_rate_pct` doit être identique,
   **chiffre pour chiffre**, à celle du producteur nommé.
7. Lancer les tests. Commiter.

## CHECKLIST

- [ ] ADR `REST-001` lu ; source et champs `null` connus
- [ ] Baseline relevée
- [ ] Aucun des 8 champs n'est un littéral figé
- [ ] Chaque champ publié est traçable à un `fichier:ligne`
- [ ] Les champs non couverts valent `null`, pas `0`
- [ ] Champ de provenance publié
- [ ] Le fichier ne contient ni `sum(`, ni `/`, ni `mean`, ni boucle sur des trades
- [ ] Cohérence croisée vérifiée sur `win_rate_pct`

## TESTS

```bash
python -m pytest tests/visualization/ -q
python -m pytest tests/ -q
```

Attendu : identique à la baseline, hors tests adaptés par `REST-004`.

## VALIDATION

**Done si :** `grep -nE "=\s*0\.0|=\s*0\b" visualization/api/portfolio_api.py` ne retourne plus aucun
des 8 champs ; aucune arithmétique dans le fichier ; `win_rate_pct` identique au producteur nommé.

**Refus si :** une métrique est calculée dans `visualization/` ⇒ **refus immédiat** (INV-R2) ;
deux sources différentes alimentent deux champs sans que l'ADR l'ait prévu ; un champ indisponible est
publié à `0` ; la provenance n'est pas publiée.

## LIVRABLES

- `visualization/api/portfolio_api.py` modifié.
- Commit :

```
fix(api): publier les metriques reelles au lieu de litteraux figes

Les 8 champs figes a 0 de portfolio_api.py:22-29 sont desormais lus
depuis la source unique arbitree par l'ADR REST-001, ou publies null.
Provenance (source, borne d'epoque, horodatage) publiee avec les metriques.

Aucun recalcul ajoute dans l'API. Lecture seule cote decision. N inchange.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `REST-003` en **TERMINE**.

## STOP CONDITIONS

- L'ADR `REST-001` est absent ou ne tranche pas une source unique ⇒ **ne pas démarrer**.
- La source retenue s'avère inaccessible depuis le process qui sert l'API ⇒ **STOP**, remonter :
  l'ADR doit être révisé, pas contourné par un calcul local.
- Rendre un champ correct exigerait un calcul dans l'API ⇒ **STOP**. Publier `null` et le signaler.

## INTERDICTIONS

- **Ne créer aucun calcul de métrique dans `visualization/`.** C'est le refus n°1.
- Ne pas appeler `analysis/base.py` (lignée scientifique) depuis l'API.
- Ne pas publier `0` pour un champ indisponible.
- Ne pas toucher `pos_manager`, `check_new_trade`, le sizing, le risk, `PortfolioBrain`.
- Ne pas adapter les tests dans ce ticket — c'est `REST-004`.
- Ne pas enchaîner sur `REST-004`. **S'arrêter après le commit.**
- Ne pas déployer.
