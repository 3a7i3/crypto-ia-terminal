# COMMANDS — Commandes standardisées du chantier

> Vocabulaire d'exécution. Chaque commande décrit **précisément** ce que la session doit faire.
> À utiliser tel quel dans une conversation : `START`, `IMPLEMENT OBS-001`, `HANDOFF`, etc.
>
> Une commande ne dispense jamais de lire le prompt du ticket.

---

## `START`

**Ouvrir une nouvelle session de travail.**

1. Lire `.claude/SESSION_BOOTSTRAP.md` et exécuter ses 5 étapes.
2. Lire `INDEX.md` (état des 34 tickets) puis `IMPLEMENTATION_QUEUE.md` (file PRET).
3. Identifier le ticket : premier de la file PRET dont **toutes** les dépendances sont TERMINE.
4. Relever la baseline : `python -m pytest tests/ -q`.
5. **Annoncer** : ticket retenu, son statut gated ou non, ses dépendances, la baseline.
6. **S'arrêter et attendre** la confirmation avant d'exécuter.

**Ne produit aucune modification.**

---

## `RESUME`

**Reprendre un ticket interrompu.**

1. Lire `IMPLEMENTATION_QUEUE.md` § file **EN COURS**.
2. Récupérer le travail : `git stash list` ou `git branch --list "wip/*"`.
3. **Relire le prompt du ticket depuis l'étape 1** — jamais depuis l'étape interrompue.
4. Relever une **nouvelle** baseline (l'ancienne peut être périmée).
5. Annoncer l'étape de reprise et ce qui reste à faire.

**Interdiction** : ne pas reprendre « de mémoire ». Le raisonnement d'une session ne se transmet pas.

---

## `IMPLEMENT <TICKET-ID>`

**Exécuter un ticket.**

1. Ouvrir `.claude/prompts/PROMPT_<ID_avec_underscores>.md`.
2. Vérifier son statut de gating (`INDEX.md`). Si **GATED** ⇒ vérifier les **quatre préconditions**
   de la porte d'époque. L'une manque ⇒ **STOP**, ne pas exécuter.
3. Vérifier que les dépendances sont TERMINE.
4. Relever la baseline si ce n'est pas déjà fait.
5. Exécuter les `ETAPES` du prompt, **dans l'ordre exact**.
6. Ne toucher **que** les fichiers listés en section `FICHIERS`.
7. Parcourir la `CHECKLIST` — chaque case doit être cochée.
8. **S'arrêter avant le commit** et annoncer le diff (`git diff --stat`).

**Interdictions** : aucun refactor opportuniste, aucune optimisation non demandée, aucun changement de
comportement hors du ticket, aucun enchaînement sur le ticket suivant.

---

## `TEST`

**Lancer les tests et interpréter le résultat.**

```bash
python -m pytest tests/ -q
```

Comparer à la baseline, puis classer selon `EXECUTION_FLOW.md` §2 :

| Constat | Action |
|---|---|
| Identique à la baseline | Poursuivre |
| Échec **attendu** (test rouge d'un ticket TDD) | Poursuivre, le noter |
| Échec causé par le ticket | Corriger dans le périmètre (3 tentatives max) |
| Échec d'un test **étranger**, préexistant | Signaler, poursuivre |
| Échec d'un test **étranger**, nouveau | **Annuler.** Régression hors périmètre |

**Interdiction absolue** : ne jamais corriger un test étranger au ticket pour faire passer la suite.

---

## `VERIFY`

**Vérifier qu'un ticket respecte ses invariants avant commit.**

```bash
git diff --cached --name-only
git diff --cached --stat
```

Contrôles :

- [ ] Les fichiers du diff sont **exactement** ceux de la section `FICHIERS`
- [ ] **INV-1** — aucun observer n'influence une décision
- [ ] **INV-2** — `pos_manager`, `check_new_trade`, sizing, risk, `PortfolioBrain` en entrée : **intacts**
      (sauf ticket GATED avec ADR signé)
- [ ] **INV-3** — `paper_trades.jsonl` et `databases/` : intacts
- [ ] **INV-4** — aucun seuil modifié (`git diff` sur `portfolio_brain.py:88-109` doit être vide)
- [ ] Aucun secret, aucun fichier parasite
- [ ] Les critères `VALIDATION` du prompt sont satisfaits

Un seul contrôle en échec ⇒ **ne pas commiter**.

---

## `COMMIT`

**Créer le commit atomique du ticket.**

1. Stager **uniquement** les fichiers du ticket.
2. Utiliser le message **exact** de la section `LIVRABLES` du prompt — sans l'abréger.
3. Laisser les hooks pre-commit s'exécuter. **Ne jamais utiliser `--no-verify`.**
4. Vérifier : `git log -1 --stat` — un commit, les bons fichiers.

Un ticket = un commit. Jamais deux tickets dans un commit, jamais un ticket en deux commits
(sauf correction d'un hook, qui peut être amendée avant push).

---

## `PR`

**Ouvrir une pull request.**

1. Vérifier que la branche ne contient **qu'un** ticket.
2. Base : `main`. Une branche par ticket.
3. Corps de PR : objectif, contenu, hors périmètre, invariants vérifiés, tests (baseline vs après),
   rollback.
4. Si la CI est rouge : déterminer si l'échec est **préexistant** (plusieurs workflows du dépôt le sont,
   constat du 2026-07-24). Le signaler dans la PR sans le corriger.
5. **Ne pas merger sans autorisation** — voir `GOVERNANCE.md` § autorité de décision.

---

## `ROLLBACK`

**Annuler un ticket.**

```bash
git revert <sha-du-ticket>
```

Puis : remettre le ticket en **PRET** dans `IMPLEMENTATION_QUEUE.md` et `INDEX.md`, inscrire la raison
au journal `DEC-xxx`, marquer les descendants comme non démarrables.

> **Avertissement** : le rollback **technique** est toujours possible.
> Le rollback **d'époque** n'existe pas. Après `PORT-006` (borne V5 posée et moteur redémarré),
> `git revert` restaure le code, **jamais la mesure**. Voir `EXECUTION_FLOW.md` §3b.

---

## `HANDOFF`

**Produire le bloc de passation de fin de session.**

```
HANDOFF — <date>
Ticket termine  : <ID> — <titre>
Commit          : <sha>
Tests           : <resultat vs baseline>
Prochain ticket : <ID> (dependances satisfaites : oui/non)
Decisions en attente : <D-x, ou "aucune">
Points de vigilance  : <ecarts, hypotheses infirmees, ou "aucun">
```

Ce bloc doit être compréhensible **sans** la conversation. C'est son seul critère de qualité.

---

## `FINISH`

**Clôturer proprement la session.**

1. Appliquer `.claude/SESSION_SHUTDOWN.md` en entier.
2. Mettre à jour les trois fichiers d'état : `IMPLEMENTATION_QUEUE.md`, `INDEX.md`, `MASTER_ROADMAP.md`.
3. Mettre à jour `CHECKPOINTS.md` **si** un checkpoint a bougé.
4. Rédiger le rapport de fin de ticket (gabarit `GOV-004`).
5. Produire le `HANDOFF`.
6. **S'arrêter.** Ne jamais enchaîner sur le ticket suivant.

---

## Séquence normale d'une session

```
START  →  IMPLEMENT <ID>  →  TEST  →  VERIFY  →  COMMIT  →  [PR]  →  HANDOFF  →  FINISH
```

Séquence en cas de problème :

```
TEST (echec)  →  EXECUTION_FLOW.md  →  ROLLBACK  →  HANDOFF  →  FINISH
```

---

## Commandes interdites

| Ce qui n'existe pas | Pourquoi |
|---|---|
| `IMPLEMENT ALL` | Un ticket à la fois, sans exception |
| `SKIP TESTS` | La baseline est le seul moyen de détecter une régression |
| `FORCE COMMIT` | `--no-verify` contourne un invariant de qualité du dépôt |
| `DEPLOY` | Le déploiement est un geste opérateur délibéré (`GOV-005`), jamais une commande de session |
| `UNGATE` | Le gating ne se lève que par ADR signé par l'opérateur |
