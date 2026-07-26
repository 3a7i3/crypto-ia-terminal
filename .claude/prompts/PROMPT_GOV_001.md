# PROMPT — GOV-001 · ADR-0019 : séparation exposition d'affichage / exposition-gate

> Ticket **NON GATED**, **documentaire**. Aucun `.py`. **N reste inchangé.**
> Le ticket **rédige** l'ADR ; son **acceptation** est une décision opérateur distincte (D-3).

## MISSION

Rédiger l'ADR (numéro libre à partir de **ADR-0019**) qui acte formellement l'existence de deux notions
d'exposition dans le système, et la non-correction volontaire de l'une d'elles sous le gel scientifique.

## CONTEXTE

Le panneau Telegram affiche « Positions: 3 » et « Portfolio Exposure: 0.0% » simultanément.

Cause : `core/advisor_loop.py:6785-6787` passe `pos_manager.get_open()` à `portfolio_health()`.
En mode paper, `pos_manager` (PositionManager) est **vide** — les positions sont ouvertes dans
`_virtual_portfolio` (MexcSimulator) via `place_market_order` (`advisor:2176`). Le compte de positions
affiché vient, lui, de `_virtual_portfolio` (`_display_position_summary`, `advisor:434-459`).

`portfolio_brain.py:668-687` itère la liste reçue ; vide ⇒ `total_exposure_pct = 0`.
Preuve numérique : `free_capital = capital × 0.40 − 0 = 674.47 × 0.40 = 269.79 $`, exactement la valeur
affichée (`portfolio_brain.py:656-663`, constante ligne 88).

Conséquence non visible : les cinq contrôles de `check_new_trade` (`portfolio_brain.py:121-190`)
s'exécutent sur un portefeuille perçu comme vide — le gate est **trop permissif**.

Le code documente déjà ce gel (`advisor:437-448`) : corriger l'entrée de décision changerait le
comportement du moteur en pleine validation scientifique, ce qui imposerait une nouvelle époque et un
reset de N. L'ADR formalise cette situation pour qu'elle soit **traçable et opposable**, et non
seulement enfouie dans une docstring.

## OBJECTIF

Un ADR qui établit : les deux notions d'exposition, laquelle est corrigée et laquelle ne l'est pas,
pourquoi, et la condition exacte de levée du gel.

## CONTRAINTES

- Documentation seule. Aucun `.py`, aucun test, aucune configuration.
- Numéro **≥ 0019** (0001 à 0018 sont pris). Vérifier le prochain libre dans `docs/adr/`.
- Suivre le format des ADR existants du dépôt (**A CONFIRMER AU DEMARRAGE DU TICKET** : lire
  `docs/adr/0000-template.md`).
- L'ADR est **proposé**, pas accepté. Son statut initial reflète cela.

## INVARIANTS

INV-1 à INV-4, trivialement respectés (aucun code touché).

## FICHIERS

| Fichier | Action |
|---|---|
| `docs/adr/00XX-....md` | Création de l'ADR (numéro ≥ 0019) |

## ETAPES

1. Lister `docs/adr/` et déterminer le prochain numéro libre (≥ 0019).
2. Lire `docs/adr/0000-template.md` pour le format.
3. Rédiger l'ADR avec : contexte (le diagnostic ci-dessus, avec fichiers et lignes) ; décision
   (deux notions distinctes, l'affichage est corrigé, le gate ne l'est pas) ; conséquences assumées
   (le gate reste permissif, risque R1) ; condition de levée (les quatre préconditions de la porte
   d'époque) ; liens vers ADR-0007, ADR-0017, et vers `PORT-002`.
4. Statuer explicitement que l'ADR est **proposé**, en attente de décision opérateur (D-3).
5. Commiter.

## CHECKLIST

- [ ] Numéro d'ADR ≥ 0019, non déjà utilisé
- [ ] Format conforme au template du dépôt
- [ ] Le diagnostic est cité avec fichiers et numéros de ligne
- [ ] La preuve numérique (`674.47 × 0.40 = 269.79`) figure
- [ ] Les deux notions d'exposition sont nommées et distinguées sans ambiguïté
- [ ] La condition de levée (4 préconditions) est énoncée
- [ ] Le statut « proposé » est explicite
- [ ] Aucun `.py` au diff

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : identique à la baseline.

## VALIDATION

**Done si :** l'ADR existe sous `docs/adr/` avec un numéro ≥ 0019, distingue les deux expositions,
énonce la condition de levée, et se déclare proposé.

**Refus si :** l'ADR se déclare accepté (l'acceptation appartient à l'opérateur) ; le numéro est déjà
pris ; la condition de levée est absente ou vague ; un `.py` apparaît au diff.

## LIVRABLES

- 1 fichier sous `docs/adr/`.
- Commit :

```
docs(adr): ADR-00XX exposition d'affichage vs exposition-gate

Acte l'existence de deux notions d'exposition : celle affichee (corrigee
par PHASE_01) et celle utilisee par le gate de decision (non corrigee,
gelee sous le gel scientifique). Enonce la condition de levee.

Statut : propose. Documentation seule.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `GOV-001` en **TERMINE**.

## STOP CONDITIONS

- `docs/adr/0000-template.md` est absent ⇒ signaler et demander le format attendu.
- La lecture du code montre que le gate **n'est pas** aveugle ⇒ **STOP** : le diagnostic entier devrait
  être revérifié avant d'acter quoi que ce soit.

## INTERDICTIONS

- Ne toucher aucun `.py`, test ou configuration.
- Ne pas déclarer l'ADR accepté.
- Ne pas corriger le gate — c'est `PORT-002`, GATED.
- Ne pas modifier un ADR existant.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
- Ne pas déployer.
