# PROMPT — OBS-001 · Tests de régression d'abord

> Ticket **NON GATED**. Il ne touche pas l'entrée de décision. **N reste inchangé.**
> Fichiers touchés : `tests/` uniquement.

## MISSION

Écrire deux tests dans `tests/` :
1. un test **rouge** qui reproduit le bug d'observabilité « 3 positions ouvertes ⇒ exposition affichée nulle » ;
2. un test **vert** de garde qui fige l'invariant INV-2 : le verdict de `check_new_trade` ne doit pas changer.

Aucun fichier de production ne doit être modifié.

## CONTEXTE

Le panneau Telegram du système affiche simultanément **« Positions: 3 »** et
**« Portfolio Exposure: 0.0% »**. Ces deux valeurs proviennent de **deux stores différents** :

- Le **compte de positions** vient de `_virtual_portfolio` (MexcSimulator) via
  `_display_position_summary` (`core/advisor_loop.py:434-459`, retour `summary.n_open` ligne 450-453).
- L'**exposition** vient de `pos_manager.get_open()` passé à `portfolio_health()`
  (`core/advisor_loop.py:6785-6787`). En mode paper, `pos_manager` (PositionManager) est **vide** :
  les positions sont ouvertes dans `_virtual_portfolio` via `place_market_order` (`advisor:2176`).

`portfolio_brain.py:668-687` `_snapshot()` itère la liste reçue (`total_exposure_usd += p.size_usd`)
puis calcule `total_exposure_pct = total_exposure_usd / self._capital`. Liste vide ⇒ exposition 0.

**Preuve numérique du diagnostic** : `portfolio_health` (`portfolio_brain.py:645-664`) dérive
`free_capital = max(0, capital × MAX_TOTAL_EXPOSURE_PCT − total_exposure_usd)` avec
`MAX_TOTAL_EXPOSURE_PCT = 0.40` (`portfolio_brain.py:88`). Or le panneau affichait
`674.47 × 0.40 − 0 = 269.79 $` — exactement la valeur observée, ce qui confirme
`total_exposure_usd = 0` alors que trois positions étaient ouvertes.

Ce bug est **documenté et gelé volontairement** : voir la docstring `core/advisor_loop.py:437-448`.
Le corriger **côté décision** changerait le comportement du moteur et imposerait un reset d'époque.
Ce ticket ne corrige rien : il **fige le bug par un test**, pour que la correction d'affichage
(ticket `OBS-002`) soit vérifiable.

## OBJECTIF

Produire une base de tests qui :
- **échoue aujourd'hui** sur le comportement d'affichage (test rouge) ;
- **passe aujourd'hui et devra continuer de passer** sur le verdict de décision (garde INV-2).

## CONTRAINTES

- Aucun fichier de production modifié. Le diff ne contient que des chemins sous `tests/`.
- Maximum 2 fichiers, environ 150 lignes.
- Le test rouge doit **échouer** avant `OBS-002` et **réussir** après. S'il passe déjà, il ne reproduit
  pas le bug : le ticket est en échec.
- Aucun test existant ne doit être supprimé ni affaibli.

## INVARIANTS

- **INV-1** — passivité des observers (ADR-0007) : le test n'influence aucune décision.
- **INV-2** — aucun reset de N. Le ticket ne touche ni `pos_manager`, ni `check_new_trade`, ni le sizing,
  ni le risk, ni `PortfolioBrain` en entrée de décision.
- **INV-3** — `paper_trades.jsonl` n'est ni lu en écriture ni modifié.
- **INV-4** — aucun seuil modifié.

## FICHIERS

| Fichier | Action |
|---|---|
| `tests/test_system_snapshot.py` **ou** un nouveau fichier `tests/` | Ajout des deux tests |
| *(éventuel)* second fichier de test | Si la séparation est plus lisible |

Fichiers **à lire** (jamais à modifier) : `core/advisor_loop.py:434-459` et `:6785-6799`,
`quant_hedge_ai/agents/risk/portfolio_brain.py:645-687`, `observability/system_snapshot.py:56`.

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q` — noter le nombre de tests et d'échecs.
2. Lire `core/advisor_loop.py:434-459` (`_display_position_summary`) pour connaître la forme exacte
   de `_virtual_portfolio.get_open_positions_summary()` (`n_open`, `unrealized_pnl_usd`).
   **A CONFIRMER AU DEMARRAGE DU TICKET** : la présence d'un champ de taille par position
   (`qty_usd` ou équivalent), nécessaire à `OBS-002`.
3. Lire `portfolio_brain.py:645-687` pour connaître la forme de `portfolio_health()` et de `_snapshot()`.
4. Lire `observability/system_snapshot.py:56` pour les champs de `PortfolioSnapshot`.
5. Écrire le **test rouge** : construire un double de `_virtual_portfolio` portant 3 positions et un
   `pos_manager` vide ; construire le `PortfolioSnapshot` d'affichage par le même chemin que le builder
   de cycle ; asserter que `portfolio_exposure_pct > 0`. **Ce test doit échouer aujourd'hui.**
6. Écrire le **test de garde INV-2** : pour un jeu d'entrées fixé, asserter que le verdict de
   `check_new_trade` est identique à une valeur de référence figée. **Ce test doit passer aujourd'hui.**
7. Lancer `python -m pytest tests/ -q` et vérifier : le test rouge échoue, la garde passe, aucun autre
   test ne régresse par rapport à la baseline.
8. Commiter.

## CHECKLIST

- [ ] Baseline de tests relevée avant toute modification
- [ ] Le test rouge **échoue** sur le code actuel
- [ ] Le test de garde INV-2 **passe** sur le code actuel
- [ ] Aucun autre test ne régresse par rapport à la baseline
- [ ] `git diff --name-only` ne liste que des chemins sous `tests/`
- [ ] Aucun test existant supprimé ou affaibli
- [ ] Les deux tests portent un nom explicite et une docstring d'une ligne

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu après ce ticket : **1 échec supplémentaire** par rapport à la baseline (le test rouge),
et aucun autre changement. Cet échec est **le résultat attendu** du ticket, pas un défaut.

## VALIDATION

**Done si :**
- le test rouge échoue avec un message montrant `portfolio_exposure_pct == 0` alors que 3 positions existent ;
- le test de garde INV-2 passe ;
- le diff ne contient que des fichiers de test.

**Refus si :**
- le test rouge passe déjà (il ne reproduit pas le bug) ;
- un fichier de production apparaît dans le diff ;
- un test existant a été modifié pour faire passer les nouveaux ;
- le test de garde échoue (cela signifierait que le verdict de décision a déjà changé — **STOP**).

## LIVRABLES

- 1 à 2 fichiers sous `tests/`.
- Un commit atomique :

```
test(observability): figer le bug exposition d'affichage + garde INV-2

Test rouge reproduisant "3 positions ouvertes => exposition affichee nulle"
(cause racine core/advisor_loop.py:6786, pos_manager vide en paper).
Test de garde figeant le verdict de check_new_trade (INV-2, aucun reset de N).

Aucun fichier de production modifie.
```

- Mise à jour de `.claude/IMPLEMENTATION_QUEUE.md` : `OBS-001` passe en **TERMINE**, avec date et SHA.

## STOP CONDITIONS

S'arrêter et demander l'opérateur si :
- le test rouge **passe** dès son écriture (le bug ne se reproduit pas ⇒ le diagnostic doit être revérifié) ;
- le test de garde INV-2 **échoue** (le verdict de décision aurait déjà changé — incident) ;
- la structure de `_display_position_summary` ou de `portfolio_health` diffère de la description ci-dessus ;
- il devient nécessaire de modifier un fichier de production pour rendre le test écrivable.

## INTERDICTIONS

- Ne pas modifier `core/advisor_loop.py`, `portfolio_brain.py`, ni aucun fichier de production.
- Ne pas toucher `pos_manager`, `check_new_trade`, le sizing, le risk, `PortfolioBrain` en entrée de décision.
- Ne pas modifier un seuil (INV-4).
- Ne pas corriger le bug dans ce ticket — c'est le rôle de `OBS-002`.
- Ne pas enchaîner sur `OBS-002`. **S'arrêter après le commit.**
- Ne pas déployer.
