# PROMPT — OBS-004 · Documenter « exposition d'affichage » ≠ « exposition-gate »

> Ticket **NON GATED**. Documentation dans le code. **N reste inchangé.**

## MISSION

Documenter, dans le code lui-même, le fait que l'exposition **affichée** (corrigée par `OBS-002`/`OBS-003`)
et l'exposition **utilisée par le gate de décision** (toujours calculée sur `pos_manager`, vide en paper)
sont **deux valeurs différentes**, et que la seconde reste volontairement non corrigée.

## CONTEXTE

À l'issue de `OBS-002` et `OBS-003`, le panneau Telegram dit la vérité : il affiche une exposition
cohérente avec les positions réellement ouvertes.

**Mais le gate de décision, lui, reste aveugle.** `core/advisor_loop.py:6785-6787` continue de passer
`pos_manager.get_open()` — vide en paper — à `portfolio_health()`, dont les valeurs alimentent les cinq
contrôles de `check_new_trade` (`quant_hedge_ai/agents/risk/portfolio_brain.py:121-190`) :
exposition totale, concentration par actif, exposition par régime, corrélation, levier.

C'est le **risque R1** du chantier : *un panneau honnête peut masquer que la décision reste bugguée.*
Un lecteur futur, voyant une exposition correcte à l'écran, pourrait légitimement conclure que le
problème est résolu. Il ne l'est pas — sa correction est `PORT-002`, bloqué derrière la porte d'époque
parce qu'il change le comportement du moteur et impose un reset de N.

Ce ticket rend cette asymétrie **impossible à ignorer** pour quiconque lit le code.

## OBJECTIF

Toute personne lisant le builder de snapshot ou `portfolio_health` doit comprendre en quelques lignes :
1. qu'il existe deux notions d'exposition ;
2. laquelle est affichée, laquelle décide ;
3. pourquoi la seconde n'est pas corrigée ;
4. où et quand elle le sera.

## CONTRAINTES

- **Documentation uniquement** : docstrings et commentaires. Aucune ligne de logique modifiée.
- Maximum 2 fichiers, environ 40 lignes.
- Le style doit suivre celui de la docstring existante `core/advisor_loop.py:437-448`, qui documente
  déjà le même type de gel.

## INVARIANTS

- **INV-1** passivité (ADR-0007) · **INV-2** aucun reset de N · **INV-3** `paper_trades.jsonl` intact ·
  **INV-4** aucun seuil modifié.
- **INV-O3** — aucune ligne exécutable modifiée : `git diff` ne doit contenir que des commentaires
  et des docstrings.

## FICHIERS

| Fichier | Action |
|---|---|
| `core/advisor_loop.py` | Docstring/commentaire au point de construction du snapshot et au site d'appel `:6786` |
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | Docstring de `portfolio_health` : préciser que son entrée est la source **de décision** |

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q`.
2. Lire la docstring existante `core/advisor_loop.py:437-448` pour en reprendre le ton et la forme.
3. Ajouter, au site d'appel `:6786`, un commentaire expliquant :
   que cet argument alimente la **décision** ; qu'il est vide en paper ; que c'est un bug **connu et gelé** ;
   que sa correction est `PORT-002` (GATED, reset d'époque).
4. Ajouter, près du calcul d'affichage introduit par `OBS-002`, une note indiquant que cette valeur est
   l'**exposition d'affichage** et qu'elle peut différer de l'exposition-gate.
5. Compléter la docstring de `portfolio_health` (`portfolio_brain.py:645`) : préciser que la liste reçue
   détermine les contraintes de décision, et que l'appelant est responsable de lui fournir le bon store.
6. Vérifier que `git diff` ne contient **aucune** ligne exécutable modifiée.
7. Lancer les tests. Commiter.

## CHECKLIST

- [ ] Baseline relevée
- [ ] Le commentaire au site `:6786` nomme explicitement `PORT-002` et le mot « GATED »
- [ ] La distinction affichage / gate est énoncée en clair
- [ ] La docstring de `portfolio_health` précise la responsabilité de l'appelant
- [ ] `git diff` ne contient que des commentaires et docstrings
- [ ] Tests identiques à la baseline

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : **strictement identique à la baseline** (aucune ligne exécutable n'a changé).

## VALIDATION

**Done si :** la distinction est documentée aux trois endroits ; le renvoi vers `PORT-002` est explicite ;
`git diff` ne montre aucune ligne exécutable modifiée ; tests inchangés.

**Refus si :** une ligne de logique a été modifiée ; la note se contente de décrire sans dire **pourquoi**
le gate n'est pas corrigé ; aucun renvoi vers le ticket de correction future.

## LIVRABLES

- 1 à 2 fichiers modifiés (commentaires/docstrings uniquement).
- Commit :

```
docs(observability): distinguer exposition d'affichage et exposition-gate

Documente le risque R1 : apres OBS-002/OBS-003 le panneau dit la verite,
mais le gate de decision lit toujours pos_manager (vide en paper) via
advisor_loop.py:6786. Bug connu, gele, corrige par PORT-002 (GATED).

Commentaires et docstrings uniquement. Aucune ligne executable modifiee.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `OBS-004` en **TERMINE**.

## STOP CONDITIONS

- `OBS-002` n'est pas terminé ⇒ ne pas démarrer (la note décrirait un état inexistant).
- La rédaction de la note révèle que le gate **n'est pas** aveugle (contradiction avec le diagnostic)
  ⇒ **STOP** et remontée : le diagnostic devrait être revérifié.

## INTERDICTIONS

- Ne modifier **aucune** ligne exécutable.
- Ne pas corriger le gate — c'est `PORT-002`, GATED.
- Ne pas supprimer ni réécrire la docstring existante `:437-448` : la compléter.
- Ne pas enchaîner sur `OBS-005`. **S'arrêter après le commit.**
- Ne pas déployer.
