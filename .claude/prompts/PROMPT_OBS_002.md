# PROMPT — OBS-002 · Builder de panneau CYCLE

> Ticket **NON GATED**. Il modifie **ce que le système montre**, jamais **ce qu'il regarde**.
> **N reste inchangé.**

## MISSION

Faire dériver l'exposition, `paper_cash` et `free_cash` **affichés** du même store que le compte de
positions (`_virtual_portfolio`), dans le builder de snapshot du cycle de `core/advisor_loop.py`.
Rendre vert le test rouge écrit par `OBS-001`, sans changer le comportement de décision.

## CONTEXTE

Le panneau affiche « Positions: 3 » et « Portfolio Exposure: 0.0% » dans le même message,
parce que les deux valeurs viennent de **stores différents** :

- `core/advisor_loop.py:6788` — `_display_position_summary(_virtual_portfolio, pb_health)` renvoie
  `n_open` depuis `_virtual_portfolio.get_open_positions_summary()` (lignes 450-453) → **3**.
- `core/advisor_loop.py:6785-6787` — `pb_health = portfolio_brain.portfolio_health(pos_manager.get_open())`.
  En paper, `pos_manager` est **vide** → exposition **0**.

Le builder construit ensuite (`advisor:6888-6906`) :
- `paper_equity` ← `pb_health["capital"]` (lignes 6796-6798) ;
- `paper_cash` ← `max(0, paper_equity − _deployed_notional)` où `_deployed_notional` somme les
  `size_usd` de `pos_manager.get_open()` (lignes 6791-6799) → **0** en paper ;
- `free_cash` ← `pb_health["free_capital"]` (ligne 6891-6893) ;
- `portfolio_exposure_pct` ← `pb_health["total_exposure_pct"]` (lignes 6894-6897).

**Preuve** : `free_capital = capital × 0.40 − total_exposure_usd` (`portfolio_brain.py:656-663`,
constante ligne 88) donnait `674.47 × 0.40 − 0 = 269.79 $`, exactement la valeur affichée.

La docstring `core/advisor_loop.py:437-448` établit la règle : `pos_manager` **reste** la source des
contraintes de décision et **ne doit pas être modifié** ; l'affichage, lui, doit dire la vérité, et
MexcSimulator est la source qui exécute réellement les positions en paper.

Ce ticket applique cette règle aux métriques d'exposition et de cash, qui étaient restées sur `pos_manager`.

## OBJECTIF

Dans le builder de cycle :
- `portfolio_exposure_pct` et `paper_cash` calculés à partir des positions de `_virtual_portfolio` ;
- `free_cash` cohérent avec cette exposition ;
- **fallback intégral** sur `pb_health` / `pos_manager` si `_virtual_portfolio is None` (modes non-paper) ;
- le verdict de `check_new_trade` **strictement inchangé**.

## CONTRAINTES

- Maximum 2 fichiers, environ 80 lignes.
- `pos_manager.get_open()` continue d'alimenter `portfolio_health()` pour la **décision**.
  Seule la **consommation d'affichage** change.
- Aucun seuil modifié (`portfolio_brain.py:88-109` intact).
- Le fallback non-paper doit conserver le comportement actuel à l'identique.

## INVARIANTS

- **INV-1** — passivité des observers (ADR-0007).
- **INV-2** — aucun reset de N. **Test de contrôle** : `git diff` ne doit montrer aucune modification
  de l'argument passé à `check_new_trade`, ni de `pos_manager`.
- **INV-3** — `paper_trades.jsonl` non touché.
- **INV-4** — aucun seuil modifié.
- **INV-O1** — le compte de positions et l'exposition affichés doivent désormais provenir du **même** store.

## FICHIERS

| Fichier | Action |
|---|---|
| `core/advisor_loop.py` | Builder de snapshot du cycle (~6788-6906) : calcul de `_deployed_notional`, `paper_cash`, `free_cash`, `portfolio_exposure_pct` |
| *(éventuel)* fichier de test de `OBS-001` | Ajustement mineur si nécessaire |

À lire sans modifier : `quant_hedge_ai/agents/risk/portfolio_brain.py:645-687`,
`observability/system_snapshot.py:56`.

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q`. Le test rouge de `OBS-001` doit y figurer en échec.
2. Confirmer la forme de `_virtual_portfolio.get_open_positions_summary()` : présence d'une taille par
   position (`qty_usd` ou équivalent) permettant de sommer l'exposition.
   **A CONFIRMER AU DEMARRAGE DU TICKET.** Si ce champ n'existe pas : **STOP** (voir STOP CONDITIONS).
3. Introduire, dans le builder de cycle, un calcul d'exposition d'affichage :
   somme des tailles des positions de `_virtual_portfolio`, divisée par `paper_equity`.
4. Recalculer `paper_cash` à partir de cette même somme (et non de `pos_manager`).
5. Recalculer `free_cash` de façon cohérente avec l'exposition d'affichage, en conservant la
   même formule que `portfolio_health` (`capital × 0.40 − exposition`), **sans modifier la constante**.
6. Conserver le **fallback** : si `_virtual_portfolio is None`, reprendre exactement les valeurs de
   `pb_health` comme aujourd'hui.
7. Vérifier que l'appel `portfolio_brain.portfolio_health(pos_manager.get_open())` est **inchangé**
   pour ce qui alimente la décision.
8. Lancer les tests : le test rouge de `OBS-001` doit devenir **vert**, la garde INV-2 rester **verte**.
9. Commiter.

## CHECKLIST

- [ ] Baseline relevée
- [ ] Champ de taille par position confirmé dans `_virtual_portfolio`
- [ ] Exposition d'affichage calculée depuis `_virtual_portfolio`
- [ ] `paper_cash` cohérent avec cette exposition
- [ ] `free_cash` cohérent, formule inchangée, constante non modifiée
- [ ] Fallback `_virtual_portfolio is None` préservé et testé
- [ ] `check_new_trade` et son argument inchangés
- [ ] `git diff` sur `portfolio_brain.py:88-109` : vide
- [ ] Test rouge de `OBS-001` désormais vert
- [ ] Garde INV-2 toujours verte

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : **zéro échec**. Le test rouge de `OBS-001` passe désormais ; aucun autre test ne régresse.

## VALIDATION

**Done si :**
- avec 3 positions ouvertes, le panneau affiche une exposition non nulle, cohérente avec la somme des tailles ;
- `paper_cash` et `free_cash` sont cohérents entre eux et avec l'exposition ;
- la garde INV-2 passe (verdict de décision inchangé) ;
- `git diff --name-only` ne liste que `core/advisor_loop.py` (+ éventuellement un test).

**Refus si :**
- `pos_manager`, `check_new_trade`, le sizing ou le risk ont été modifiés ⇒ **refus immédiat**
  (le ticket deviendrait GATED) ;
- un seuil a été modifié ;
- le fallback non-paper a changé de comportement ;
- la garde INV-2 échoue.

## LIVRABLES

- `core/advisor_loop.py` modifié (builder de cycle uniquement).
- Un commit atomique :

```
fix(observability): exposition d'affichage derivee du store reel

Le builder de cycle derive desormais exposition, paper_cash et free_cash
de _virtual_portfolio (MexcSimulator), meme source que le compte de positions,
au lieu de pos_manager (vide en paper). Fallback pb_health conserve hors paper.

Aucune modification de l'entree de decision : pos_manager et check_new_trade
sont inchanges. Aucun seuil modifie. N inchange.
```

- Mise à jour de `.claude/IMPLEMENTATION_QUEUE.md` : `OBS-002` en **TERMINE**, date, SHA.

## STOP CONDITIONS

S'arrêter et demander l'opérateur si :
- `_virtual_portfolio.get_open_positions_summary()` n'expose **aucune taille par position** — il serait
  alors impossible de calculer l'exposition sans toucher un autre composant ;
- rendre le test vert exigerait de modifier `pos_manager` ou `check_new_trade` ;
- la garde INV-2 échoue après modification (le comportement de décision aurait changé — **incident grave**) ;
- le fallback non-paper ne peut pas être préservé à l'identique.

## INTERDICTIONS

- Ne pas modifier `pos_manager`, `check_new_trade`, le sizing, le risk, ni `PortfolioBrain` en entrée
  de décision. Ce serait un ticket **GATED** avec reset d'époque.
- Ne pas modifier de seuil (INV-4).
- Ne pas « en profiter » pour corriger le gate — c'est `PORT-002`, bloqué derrière la porte d'époque.
- Ne pas refactorer `advisor_loop.py` au passage.
- Ne pas enchaîner sur `OBS-003`. **S'arrêter après le commit.**
- Ne pas déployer.
