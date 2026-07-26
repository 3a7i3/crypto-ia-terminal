# PROMPT — OBS-003 · Builder de panneau HEARTBEAT (parité)

> Ticket **NON GATED**. Affichage uniquement. **N reste inchangé.**

## MISSION

Appliquer au builder de snapshot **heartbeat** de `core/advisor_loop.py` le même calcul d'exposition,
`paper_cash` et `free_cash` que celui introduit par `OBS-002` dans le builder de **cycle**.

## CONTEXTE

`core/advisor_loop.py` construit un `PortfolioSnapshot` à **deux** endroits :
- le builder du **rapport de cycle** (~lignes 6788-6906), corrigé par `OBS-002` ;
- le builder du **heartbeat** `[ALIVE]` (~lignes 7444-7482), **non corrigé**.

Les deux lisaient `pb_health` (issu de `pos_manager.get_open()`, vide en paper) pour l'exposition et
`free_cash`, et dérivaient `paper_cash` de `_deployed_notional` calculé sur `pos_manager`.

Après `OBS-002`, le rapport de cycle dit la vérité mais le heartbeat continue d'afficher les anciennes
valeurs. Deux surfaces du même système publieraient deux vérités différentes — exactement le défaut
que le chantier corrige. Ce ticket rétablit la parité.

## OBJECTIF

Le snapshot heartbeat produit, pour un même instant, **les mêmes valeurs** d'exposition, `paper_cash`
et `free_cash` que le snapshot de cycle.

## CONTRAINTES

- Maximum 2 fichiers, environ 60 lignes.
- Réutiliser la logique de `OBS-002` (fonction partagée de préférence à une duplication).
- Fallback `_virtual_portfolio is None` préservé.
- Aucun seuil modifié.

## INVARIANTS

- **INV-1** passivité (ADR-0007) · **INV-2** aucun reset de N · **INV-3** `paper_trades.jsonl` intact ·
  **INV-4** aucun seuil modifié.
- **INV-O1** — même store pour le compte de positions et l'exposition.
- **INV-O2** — **parité stricte** : pour un même état, cycle et heartbeat produisent des valeurs identiques.

## FICHIERS

| Fichier | Action |
|---|---|
| `core/advisor_loop.py` | Builder heartbeat (~7444-7482) |
| *(éventuel)* fichier de test | Test de parité cycle/heartbeat |

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q` (doit être à zéro échec après `OBS-002`).
2. Lire le builder heartbeat (~7444-7482) et identifier les quatre champs concernés :
   `paper_equity`, `paper_cash`, `free_cash`, `portfolio_exposure_pct`.
3. Extraire la logique introduite par `OBS-002` dans une fonction réutilisable, si elle ne l'est pas déjà.
4. L'appliquer au builder heartbeat.
5. Ajouter un test de **parité** : à état identique, les deux builders produisent les mêmes valeurs.
6. Lancer les tests. Commiter.

## CHECKLIST

- [ ] Baseline à zéro échec avant de commencer
- [ ] Logique partagée entre les deux builders (pas de copier-coller)
- [ ] Fallback non-paper préservé
- [ ] Test de parité ajouté et vert
- [ ] `check_new_trade` et `pos_manager` inchangés
- [ ] Aucun seuil modifié

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : zéro échec, plus le nouveau test de parité vert.

## VALIDATION

**Done si :** le test de parité passe ; les deux snapshots donnent les mêmes valeurs à état égal ;
le diff ne liste que `core/advisor_loop.py` (+ test).

**Refus si :** duplication de la logique au lieu d'une fonction partagée ; `pos_manager` ou
`check_new_trade` modifiés ; parité non testée (le ticket serait invérifiable).

## LIVRABLES

- `core/advisor_loop.py` modifié (builder heartbeat).
- Commit :

```
fix(observability): parite heartbeat avec le builder cycle

Le snapshot heartbeat derive exposition, paper_cash et free_cash de la meme
source que le builder de cycle (OBS-002). Test de parite ajoute.

Aucune modification de l'entree de decision. N inchange.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `OBS-003` en **TERMINE**.

## STOP CONDITIONS

- `OBS-002` n'est pas terminé (dépendance dure) ⇒ ne pas démarrer.
- Le builder heartbeat a une structure incompatible avec la factorisation ⇒ signaler avant d'improviser.
- Le test de parité échoue de façon irréductible ⇒ signaler (un écart structurel non documenté existerait).

## INTERDICTIONS

- Ne pas modifier `pos_manager`, `check_new_trade`, le sizing, le risk, `PortfolioBrain` en entrée.
- Ne pas modifier de seuil.
- Ne pas refactorer au-delà de la factorisation strictement nécessaire.
- Ne pas enchaîner sur `OBS-004`. **S'arrêter après le commit.**
- Ne pas déployer.
