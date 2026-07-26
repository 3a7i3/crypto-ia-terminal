# PROMPT — GOV-003 · Journal des décisions du chantier

> Ticket **NON GATED**, **documentaire**. Aucun `.py`. **N reste inchangé.**

## MISSION

Créer le journal `DEC-xxx` qui trace chaque arbitrage du chantier : qui a décidé, quand, sur quelle
preuve, et ce que la décision bloque ou débloque.

## CONTEXTE

Le chantier comporte des décisions **irréversibles** — au premier rang desquelles le reset d'époque
(N → 0), pour lequel aucun rollback n'existe. Il comporte aussi des arbitrages structurels
(ex. le chevauchement entre `SSOT-010` et `PORT-004`, qui traitent le même objet).

Sans journal, ces décisions se perdent dans l'historique des conversations, qui n'est pas un artefact
versionné. Six mois plus tard, personne ne saura **pourquoi** telle option a été retenue, ni sur quelle
preuve, ni qui l'a tranchée — et la décision sera rejouée à l'aveugle.

Le dépôt a déjà connu ce problème : plusieurs décisions d'époque (V1 → V4) n'ont été reconstituables
qu'a posteriori, à partir d'ADR rédigés après coup.

## OBJECTIF

Un fichier unique, en append seulement, où chaque décision reçoit un identifiant `DEC-xxx` stable,
citable depuis n'importe quel ticket ou ADR.

## CONTRAINTES

- Documentation seule. Aucun `.py`.
- **Append seulement** : une entrée n'est jamais réécrite. Une décision révisée donne lieu à une
  **nouvelle** entrée qui référence l'ancienne. C'est la même discipline que celle appliquée au
  dataset scientifique (INV-3).
- Chaque entrée doit être courte : le journal doit rester lisible.

## INVARIANTS

INV-1 à INV-4, trivialement respectés (aucun code touché).
**INV-G1** — le journal est en append seulement ; aucune entrée n'est modifiée ni supprimée.

## FICHIERS

| Fichier | Action |
|---|---|
| 1 journal Markdown sous `.claude/` ou `docs/` | Création (emplacement **A CONFIRMER AU DEMARRAGE DU TICKET**) |

## ETAPES

1. Lire `.claude/MASTER_ROADMAP.md` § « Décisions en attente de l'opérateur » : les décisions D-1 à D-5
   y sont déjà recensées et constituent le contenu initial du journal.
2. Définir le format d'une entrée : identifiant `DEC-xxx` · date · décideur · question tranchée ·
   option retenue · options écartées · **preuve invoquée** · ce que la décision débloque ou bloque ·
   réversibilité (oui / non / partielle).
3. Créer le journal et y inscrire les décisions **déjà prises** dans le chantier, s'il en existe
   (ex. le choix de l'architecture A pour PHASE_01, le gating des phases 02 et 04).
4. Y inscrire les décisions **en attente** (D-1 à D-5) avec le statut « EN ATTENTE » et le nom du
   décideur requis.
5. Ajouter la règle d'append en tête du fichier.
6. Commiter.

## CHECKLIST

- [ ] Format d'entrée défini, incluant **preuve invoquée** et **réversibilité**
- [ ] Les décisions déjà prises sont inscrites
- [ ] Les décisions en attente (D-1 à D-5) sont inscrites avec leur décideur
- [ ] La règle d'append figure en tête
- [ ] D-1 (reset d'époque) est marquée **irréversible**
- [ ] Aucun `.py` au diff

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : identique à la baseline.

## VALIDATION

**Done si :** le journal existe, son format inclut la preuve et la réversibilité, les décisions connues
et en attente y figurent, et la règle d'append est énoncée.

**Refus si :** une entrée omet la preuve invoquée ; D-1 n'est pas marquée irréversible ; le format
autorise la réécriture d'une entrée.

## LIVRABLES

- 1 journal Markdown.
- Commit :

```
docs(gov): journal des decisions du chantier

Journal DEC-xxx en append seulement : decideur, preuve invoquee,
reversibilite, ce que la decision bloque ou debloque.
Decisions D-1 a D-5 inscrites en attente.

Documentation seule.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `GOV-003` en **TERMINE**.

## STOP CONDITIONS

- Une décision déjà prise s'avère **non documentable** (décideur ou preuve inconnus) ⇒ l'inscrire
  comme telle, explicitement (« preuve non reconstituable »), plutôt que d'inventer une justification.

## INTERDICTIONS

- Ne toucher aucun `.py`, test ou configuration.
- Ne pas inventer une preuve pour une décision passée.
- Ne pas trancher soi-même une décision en attente : le journal les **enregistre**, il ne les prend pas.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
- Ne pas déployer.
