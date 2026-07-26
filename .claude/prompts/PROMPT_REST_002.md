# PROMPT — REST-002 · Supprimer la recopie `total_pnl_usd = open_pnl_usd`

> Ticket **NON GATED**. Couche de publication HTTP, lecture seule côté décision. **N reste inchangé.**

## MISSION

Cesser de publier le PnL **ouvert** dans le champ `total_pnl_usd` de l'API, qui est lu comme un PnL
**total**. Publier soit la vraie valeur si un producteur existant la fournit, soit `null` — jamais `0`.

## CONTEXTE

`visualization/api/portfolio_api.py:30` écrit :

```
total_pnl_usd = float(portfolio.get("open_pnl_usd", 0.0) or 0.0)
```

Le champ source `open_pnl_usd` provient de `PortfolioSnapshot` (`observability/system_snapshot.py:56`),
alimenté par `_display_position_summary` (`core/advisor_loop.py:434-459`) : c'est un PnL **latent**,
sur positions **ouvertes**.

Le PnL **fermé** est produit ailleurs, par `PaperLedger.summary()` (`paper_trading/ledger.py:191`,
clé `pnl_net_usd`). Les deux ne sont pas commensurables.

C'est le seul défaut de la phase qui publie une valeur **activement fausse** — plausible, mais fausse,
sans aucun signal d'erreur. Une valeur fausse est plus nuisible qu'une valeur absente.

L'audit SSoT recense ≈5 producteurs concurrents pour les métriques de PnL. **Ce ticket ne doit pas en
créer un sixième** : il lit une valeur existante, ou publie `null`.

## OBJECTIF

`total_pnl_usd` ne vaut plus jamais `open_pnl_usd`. `open_pnl_usd` reste publié séparément, inchangé.

## CONTRAINTES

- Maximum 2 fichiers, environ 20 lignes.
- **Aucune arithmétique** introduite dans `visualization/` : ni `sum()`, ni division, ni moyenne,
  ni boucle sur un historique de trades.
- Si aucun producteur existant ne fournit le PnL fermé accessible depuis l'API ⇒ publier `null`.
  La branche `null` est toujours applicable et suffit à corriger le défaut.

## INVARIANTS

- **INV-1** passivité (ADR-0007) · **INV-2** aucun reset de N · **INV-3** `paper_trades.jsonl` intact ·
  **INV-4** aucun seuil modifié.
- **INV-R2** — aucun recalcul de métrique créé dans la couche API.
- **INV-R6** — une métrique indisponible vaut `null`, **jamais `0`**.

## FICHIERS

| Fichier | Action |
|---|---|
| `visualization/api/portfolio_api.py` | Ligne 30 |
| *(éventuel)* `visualization/api/models.py` | Si le champ doit devenir optionnel |

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q`.
2. Relever les consommateurs de `total_pnl_usd` (dépôt + front éventuel) et leur tolérance à `null`.
   **A CONFIRMER AU DEMARRAGE DU TICKET.**
3. Vérifier qu'aucun test n'asserte `total_pnl_usd == open_pnl_usd`.
   **A CONFIRMER AU DEMARRAGE DU TICKET.**
4. Remplacer la recopie par `null` (ou par la source retenue si `REST-001` est terminé).
5. Vérifier que `open_pnl_usd` reste publié séparément et inchangé.
6. Lancer les tests, comparer à la baseline. Commiter.

## CHECKLIST

- [ ] Baseline relevée
- [ ] Consommateurs identifiés et tolérance à `null` vérifiée
- [ ] Aucun test n'assertait l'égalité des deux champs
- [ ] `total_pnl_usd` ne vaut plus `open_pnl_usd`
- [ ] `total_pnl_usd` ne vaut pas `0.0` non plus
- [ ] `open_pnl_usd` reste publié, inchangé
- [ ] Aucune arithmétique ajoutée dans `visualization/`

## TESTS

```bash
python -m pytest tests/visualization/ -q
python -m pytest tests/ -q
```

Attendu : identique à la baseline.

## VALIDATION

**Done si :** `grep -n "open_pnl_usd" visualization/api/portfolio_api.py` ne montre plus d'affectation à
`total_pnl_usd` ; le diff fait ≤ 20 lignes ; tests identiques à la baseline.

**Refus si :** le champ passe à `0.0` (viole INV-R6) ; un calcul de PnL est introduit dans
`visualization/` (viole INV-R2) ; `open_pnl_usd` a été supprimé ou modifié ; un fichier hors
`visualization/` (ou hors tests) apparaît au diff.

## LIVRABLES

- `visualization/api/portfolio_api.py` modifié.
- Commit :

```
fix(api): total_pnl_usd cesse de recopier le PnL ouvert

portfolio_api.py:30 publiait open_pnl_usd (PnL latent sur positions
ouvertes) dans un champ lu comme PnL total. Publie desormais la valeur
reelle si un producteur existant la fournit, sinon null — jamais 0.

Aucun recalcul ajoute dans l'API. Lecture seule cote decision. N inchange.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `REST-002` en **TERMINE**.

## STOP CONDITIONS

- Un consommateur casse sur `null` ⇒ **STOP**, remonter à l'opérateur. Ne pas replier sur `0` : ce
  serait remplacer une valeur fausse par une autre.
- Corriger le champ exigerait de calculer le PnL fermé dans l'API ⇒ **STOP** (INV-R2). C'est le rôle
  de `REST-001` de trancher la source.

## INTERDICTIONS

- Ne pas introduire d'arithmétique dans `visualization/`.
- Ne pas publier `0` pour un champ indisponible.
- Ne pas toucher `pos_manager`, `check_new_trade`, le sizing, le risk, `PortfolioBrain`.
- Ne pas traiter les 8 littéraux figés dans ce ticket — c'est `REST-003`.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
- Ne pas déployer.
