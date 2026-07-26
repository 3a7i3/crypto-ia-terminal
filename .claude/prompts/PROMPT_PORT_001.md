# PROMPT — PORT-001 · Mesure d'impact hors ligne du gate aveugle

> **PASSIF — EXCEPTION DOCUMENTEE.** Ce ticket appartient à la phase `PHASE_04_GATED`, mais il est
> le **seul** de cette phase à ne pas modifier l'entrée de décision. Il **mesure** hors ligne ce que la
> bascule changerait. Il **ne reset pas N** et peut être exécuté **avant** l'ADR d'époque —
> c'est même souhaitable, puisque son résultat **fonde** cette décision.

## MISSION

Produire un rapport chiffré répondant à une question : *sur l'historique de l'époque V4, combien de
trades autorisés auraient été **refusés** si le gate de risque avait vu les positions réellement
ouvertes ?*

## CONTEXTE

`core/advisor_loop.py:6785-6787` passe `pos_manager.get_open()` à `portfolio_health()`.
En mode paper, `pos_manager` (PositionManager) est **vide** : les positions sont ouvertes dans
`_virtual_portfolio` (MexcSimulator) via `place_market_order` (`advisor:2176`).

`portfolio_brain.py:668-687` `_snapshot()` itère la liste reçue (`total_exposure_usd += p.size_usd`,
`n_positions += 1`) puis calcule `total_exposure_pct = total_exposure_usd / self._capital`.
Liste vide ⇒ exposition 0.

Ces valeurs alimentent les **cinq contrôles** de `check_new_trade` (`portfolio_brain.py:121-190`) :
exposition totale (§1), concentration par actif (§2), exposition par régime (§3), corrélation (§4),
levier agrégé (§5). **Les cinq s'exécutent donc sur un portefeuille perçu comme vide** — le gate est
structurellement **trop permissif**.

**Preuve numérique** : `free_capital = max(0, capital × MAX_TOTAL_EXPOSURE_PCT − total_exposure_usd)`
(`portfolio_brain.py:656-663`, constante `0.40` ligne 88). Le panneau affichait
`674.47 × 0.40 − 0 = 269.79 $`, exactement la valeur observée ⇒ `total_exposure_usd = 0` confirmé en
production, alors que trois positions étaient ouvertes.

Corriger ce défaut (ticket `PORT-002`) change le comportement du moteur, donc impose une **nouvelle
époque** et remet **N à zéro**. Le rollback de code existe ; **le rollback d'époque n'existe pas**.

D'où ce ticket : décider d'un reset sans savoir ce qu'il achète serait une décision non informée sur une
action irréversible.

## OBJECTIF

Un rapport chiffré, vérifiable, contenant :
1. le nombre total de décisions d'ouverture rejouées ;
2. le nombre (et le pourcentage) qui auraient été **refusées** avec l'exposition réelle ;
3. la répartition des **motifs** de refus parmi les cinq contrôles ;
4. le **PnL cumulé** des trades qui auraient été refusés (gagnants ou perdants ?) ;
5. l'**exposition maximale réellement atteinte**, comparée au plafond de 40 %.

## CONTRAINTES

- **Rejeu hors ligne, en lecture seule.** Aucun composant de production n'est modifié.
- Le moteur en cours d'exécution n'est **ni arrêté ni influencé** (ADR-0007).
- Maximum 2 fichiers : 1 script d'analyse + 1 rapport. Aucun fichier de production.
- Le script ne doit **jamais** écrire dans `paper_trades.jsonl`.

## INVARIANTS

- **INV-1** — passivité (ADR-0007) : le script n'influence aucune décision.
- **INV-2** — **respecté** : aucun reset de N. Le ticket ne modifie pas l'entrée de décision.
- **INV-3** — `paper_trades.jsonl` lu en **lecture seule**, jamais écrit ni réécrit.
- **INV-4** — aucun seuil modifié : le rejeu utilise les seuils **actuels**, sans les toucher.
- **INV-P2** — tout écart mesuré est **chiffré et journalisé**, jamais résumé qualitativement.

## FICHIERS

| Fichier | Action |
|---|---|
| 1 script sous `analysis/` ou `research/` | Création (emplacement **A CONFIRMER AU DEMARRAGE DU TICKET**) |
| 1 rapport Markdown | Création |

À lire sans modifier : `quant_hedge_ai/agents/risk/portfolio_brain.py:121-190` et `:645-687`,
`paper_trading/ledger.py`, `scripts/data_quality.py` (borne `CLEAN_DATA_SINCE_ACTIVE`).

## ETAPES

1. Confirmer les trois hypothèses :
   - **H1** — l'historique V4 permet de reconstituer, pour chaque décision, les positions ouvertes à cet
     instant (source probable : `paper_trades.jsonl` + horodatages d'ouverture/fermeture).
   - **H2** — `check_new_trade` est appelable en pur calcul, sans effet de bord.
   - **H3** — le capital historique est reconstituable par instant.
   **A CONFIRMER AU DEMARRAGE DU TICKET.** Si l'une échoue : voir STOP CONDITIONS.
2. Écrire le script de rejeu hors ligne, en lecture seule, borné par `CLEAN_DATA_SINCE_ACTIVE`.
3. Reconstituer chronologiquement l'état du portefeuille à chaque décision.
4. Pour chaque décision d'ouverture enregistrée : appeler `check_new_trade` avec les positions
   **réelles** de cet instant, et comparer au verdict historique (qui fut « autorisé »).
5. **Auto-valider le harnais** : rejouer avec `open_positions = []` doit reproduire **à l'identique**
   les verdicts historiques. Sans cette preuve, le chiffre produit est invérifiable.
6. Produire le rapport avec les 5 métriques de la section OBJECTIF.
7. Commiter (script + rapport).

## CHECKLIST

- [ ] H1, H2, H3 confirmées ou l'échec documenté
- [ ] Le script est en lecture seule ; il n'ouvre `paper_trades.jsonl` qu'en lecture
- [ ] La borne `CLEAN_DATA_SINCE_ACTIVE` est importée, jamais recopiée en littéral
- [ ] Le script n'est branché sur aucun processus en exécution
- [ ] **Auto-validation du harnais démontrée** (verdicts historiques reproduits avec liste vide)
- [ ] Les 5 métriques figurent au rapport, chiffrées
- [ ] Aucun fichier de production modifié
- [ ] Les seuils utilisés sont les seuils actuels, non modifiés

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : **identique à la baseline** (aucun fichier de production touché).

Plus le contrôle d'auto-validation de l'étape 5, qui est le test réel de ce ticket.

## VALIDATION

**Done si :** le rapport contient les 5 métriques chiffrées ; l'auto-validation du harnais est
démontrée ; aucun fichier de production n'est modifié ; la suite de tests est inchangée.

**Refus si :** le script écrit dans `paper_trades.jsonl` ⇒ **refus immédiat** (INV-3) ; le script est
branché sur le moteur en exécution ⇒ refus (ADR-0007) ; le rapport donne une conclusion sans chiffre ;
l'auto-validation est absente (le chiffre serait invérifiable) ; un seuil a été modifié pour le rejeu.

## LIVRABLES

- 1 script d'analyse hors ligne + 1 rapport Markdown.
- Commit :

```
feat(analysis): mesure d'impact hors ligne du gate aveugle

Rejeu en lecture seule de l'epoque V4 : combien de trades autorises
auraient ete refuses si check_new_trade avait vu les positions reelles.
Cinq metriques chiffrees + auto-validation du harnais.

Passif : aucun fichier de production modifie, aucune influence sur le
moteur en execution (ADR-0007). Aucun reset de N.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `PORT-001` en **TERMINE**.
- **Signaler à l'opérateur** que le rapport est disponible : il conditionne la décision **D-1**
  (autoriser ou non le reset d'époque V4 → V5).

## STOP CONDITIONS

S'arrêter et demander l'opérateur si :
- **H1 échoue** — l'état du portefeuille n'est pas reconstituable de façon fiable. Un chiffre approximatif
  servirait alors une décision **irréversible** : mieux vaut pas de chiffre qu'un faux chiffre.
- **H2 échoue** — `check_new_trade` a des effets de bord empêchant le rejeu pur.
- L'auto-validation ne reproduit **pas** les verdicts historiques : le harnais est faux, tout résultat
  produit serait sans valeur.
- Le rejeu exigerait de modifier un seuil ou un fichier de production.

## INTERDICTIONS

- Ne modifier aucun fichier de production. Ce ticket **mesure**, il ne corrige rien.
- Ne pas écrire dans `paper_trades.jsonl`, ni dans aucun fichier de `databases/`.
- Ne pas brancher le script sur le moteur en cours d'exécution.
- Ne pas modifier de seuil pour « voir ce que ça donne » (INV-4).
- **Ne pas exécuter `PORT-002`** ni aucun autre ticket de `PHASE_04_GATED` : ils sont **BLOQUES**
  derrière la porte d'époque.
- Ne pas conclure à la place de l'opérateur : le rapport **présente** le chiffre, il ne décide pas du reset.
- **S'arrêter après le commit.**
