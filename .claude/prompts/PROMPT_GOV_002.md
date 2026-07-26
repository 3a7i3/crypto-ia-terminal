# PROMPT — GOV-002 · Registre des invariants INV-1 → INV-4 rendu opposable

> Ticket **NON GATED**, **documentaire**. Aucun fichier `.py`. **N reste inchangé.**
> **C'est le premier ticket du chantier.**

## MISSION

Produire un registre des quatre invariants du chantier, rédigé de façon **opposable** : chaque invariant
énoncé, numéroté, avec son **test de violation** vérifiable. Tous les tickets ultérieurs s'y réfèrent.

## CONTEXTE

Le chantier corrige une dette de sources de vérité multiples dans un système de trading en phase de
validation scientifique. Le risque dominant n'est pas technique : c'est de **détruire le burn-in en cours**
en modifiant par inadvertance le comportement du moteur de décision.

Un invariant énoncé en prose (« ne pas toucher à la décision ») n'arrête personne. Un invariant assorti
d'un **test de violation** (« si `git diff` montre une modification de l'argument passé à
`check_new_trade`, l'invariant est violé ») est vérifiable mécaniquement, donc opposable.

Les quatre invariants à formaliser :

- **INV-1 — Passivité des observers (ADR-0007).** Aucun composant d'observabilité, de télémétrie, de
  regret ou de calibration ne peut influencer une décision en temps réel.
- **INV-2 — Aucun reset de N sans ADR d'époque signé.** Modifier ce que le moteur **regarde** change son
  comportement, ce qui impose une nouvelle borne d'époque et remet le compteur de trades à zéro.
  La borne courante est `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` (`scripts/data_quality.py`).
- **INV-3 — `paper_trades.jsonl` est écrit uniquement par `paper_trading/mexc_simulator.py` et
  `paper_trading/recorder.py`.** L'historique n'est jamais réécrit ; on ajoute, on ne modifie pas.
- **INV-4 — Aucun seuil modifié** avant N ≥ 500 et CRI ≥ 90 (règle du statisticien).
  Sizing épinglé à `WALLET_PAPER_CAPITAL`.

## OBJECTIF

Un document que n'importe quel ticket peut citer, et contre lequel n'importe quelle revue peut trancher
sans débat d'interprétation.

## CONTRAINTES

- **Documentation seule.** Aucun fichier `.py`, aucun test, aucune configuration.
- Chaque invariant doit comporter : énoncé, raison d'être, **test de violation** (commande ou contrôle
  concret), et conséquence d'une violation.
- Le document doit être court et lisible d'un trait. Un registre que personne ne lit ne protège rien.

## INVARIANTS

Le ticket **produit** les invariants ; il est lui-même soumis à INV-1 → INV-4, trivialement respectés
puisqu'aucun code n'est touché.

## FICHIERS

| Fichier | Action |
|---|---|
| 1 document Markdown sous `.claude/` ou `docs/` | Création (emplacement **A CONFIRMER AU DEMARRAGE DU TICKET** — cohérence avec `GOVERNANCE.md`) |

Aucun autre fichier.

## ETAPES

1. Lire `.claude/GOVERNANCE.md` pour ne pas dupliquer ce qui y figure déjà — le registre doit
   **compléter**, pas recopier.
2. Pour chaque invariant, rédiger : énoncé · raison d'être · test de violation · conséquence.
3. Pour INV-2, énoncer explicitement le **test de gating** :
   *« ce changement modifie-t-il ce que le moteur regarde, ou seulement ce qu'il montre ? »*
   avec la liste des symboles sensibles : `PositionManager`, `check_new_trade`, sizing, risk,
   `PortfolioBrain` en entrée de décision, seuils par régime, `CLEAN_DATA_SINCE_*`.
4. Vérifier que chaque test de violation est **exécutable** (commande `git diff`, `grep`, ou contrôle
   décrit sans ambiguïté). Un test qui demande un jugement subjectif n'est pas un test.
5. Commiter.

## CHECKLIST

- [ ] Les 4 invariants sont énoncés et numérotés
- [ ] Chacun a un test de violation **exécutable**
- [ ] Chacun a une conséquence de violation explicite
- [ ] Le test de gating figure sous INV-2, avec la liste des symboles sensibles
- [ ] Aucun doublon avec `GOVERNANCE.md`
- [ ] `git diff --name-only` ne liste aucun `.py`

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : **strictement identique à la baseline** — aucun fichier de code n'est touché.

## VALIDATION

**Done si :** les 4 invariants sont énoncés avec un test de violation exécutable et une conséquence ;
le test de gating est présent ; aucun `.py` au diff.

**Refus si :** un invariant est énoncé sans test de violation ; un test exige un jugement subjectif ;
le document recopie `GOVERNANCE.md` au lieu de le compléter.

## LIVRABLES

- 1 document Markdown.
- Commit :

```
docs(gov): registre des invariants INV-1..INV-4

Quatre invariants du chantier, chacun avec son test de violation executable
et la consequence d'une violation. Inclut le test de gating sous INV-2.

Documentation seule. Aucun fichier de code touche.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `GOV-002` en **TERMINE**, date, SHA.

## STOP CONDITIONS

- Un invariant s'avère **déjà violé** par le code existant ⇒ le documenter comme tel et **remonter à
  l'opérateur** avant de poursuivre. Ne pas réécrire l'invariant pour qu'il colle au code.
- L'emplacement du document est ambigu ⇒ demander plutôt que de créer un doublon.

## INTERDICTIONS

- Ne toucher aucun fichier `.py`, aucun test, aucune configuration.
- Ne pas affaiblir un invariant pour le rendre plus facile à respecter.
- Ne pas enchaîner sur `GOV-004`. **S'arrêter après le commit.**
- Ne pas déployer.
