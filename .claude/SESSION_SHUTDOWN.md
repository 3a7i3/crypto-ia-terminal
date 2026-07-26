# SESSION_SHUTDOWN — Fermer une session de travail

> À appliquer **avant chaque fin de session**, qu'un ticket soit terminé ou interrompu.
>
> **Principe** : le contexte conversationnel ne survit pas. Tout ce qui n'est pas écrit dans un
> fichier ou un commit est perdu. Cette procédure existe pour que rien d'important ne le soit.

---

## Cas A · Le ticket est terminé

### A1 · Vérifier les tests

```bash
python -m pytest tests/ -q
```

Comparer à la **baseline** relevée au démarrage.

| Constat | Action |
|---|---|
| Identique à la baseline | ✅ Poursuivre |
| Un échec attendu en plus (ex. test rouge de `OBS-001`) | ✅ Poursuivre, le noter |
| Un échec non attendu | ❌ **Ne pas fermer.** Voir `EXECUTION_FLOW.md` §2 |

### A2 · Vérifier Git

```bash
git status --short
git diff --cached --name-only
git log --oneline -3
```

- [ ] Le diff ne contient **que** les fichiers listés dans la section `FICHIERS` du prompt
- [ ] **Un seul commit** pour ce ticket (atomicité)
- [ ] Le message de commit est **exactement** celui du prompt (section `LIVRABLES`)
- [ ] Aucun fichier parasite (`.env`, cache, artefact de test, fichier temporaire)
- [ ] `git status` est propre après le commit
- [ ] Aucun secret dans le diff

### A3 · Mettre à jour l'état — trois fichiers

| Fichier | Mise à jour |
|---|---|
| `IMPLEMENTATION_QUEUE.md` | Déplacer le ticket de **PRET** vers **TERMINE** : date, SHA, résultat des tests |
| `INDEX.md` | Colonne `Statut` du ticket → `TERMINE` ; compteurs en tête |
| `MASTER_ROADMAP.md` | Cocher la case du ticket dans § « État d'avancement » |

Si le ticket a franchi un checkpoint (voir `CHECKPOINTS.md`), mettre également `CHECKPOINTS.md` à jour.

Si une décision a été prise ou tranchée, l'inscrire au journal `DEC-xxx` (`GOV-003`).

### A4 · Rédiger le rapport de fin de ticket

Selon le gabarit défini par `GOV-004`, aligné sur `docs/protocole_audit_epistemique.md` v3 :

- **Observation** — ce qui a été effectivement constaté (commandes lancées, sorties obtenues).
- **Inférence** — ce qu'on en déduit, avec confiance, portée et falsificateur.
- **Hypothèse** — les `A CONFIRMER AU DEMARRAGE DU TICKET` rencontrés et leur issue.
- **Décision** — ce qui est recommandé pour la suite, et par qui cela doit être tranché.
- **Invariants vérifiés** — lesquels, par quel contrôle.
- **Ce qui n'a pas été fait** — périmètre volontairement laissé de côté.

### A5 · Préparer le handoff

Écrire, en fin de session, un bloc court et autonome :

```
HANDOFF — <date>
Ticket termine  : <ID> — <titre>
Commit          : <sha>
Tests           : <resultat vs baseline>
Prochain ticket : <ID> (dependances satisfaites : oui/non)
Decisions en attente : <D-x, ou "aucune">
Points de vigilance  : <ecarts constates, hypotheses infirmees, ou "aucun">
```

Ce bloc doit être compréhensible **sans** la conversation.

---

## Cas B · Le ticket est interrompu

### B1 · Ne pas commiter un travail partiel sur `main`

Deux options :

```bash
git stash push -m "WIP <TICKET-ID> etape <n>"      # reprise proche
```
ou
```bash
git checkout -b wip/<TICKET-ID> && git commit -m "wip(<TICKET-ID>): etape <n>"   # reprise lointaine
```

**Jamais de WIP sur `main`.**

### B2 · Marquer l'état

Dans `IMPLEMENTATION_QUEUE.md`, passer le ticket en **EN COURS** avec :
- la date ;
- le **numéro d'étape** du prompt atteint ;
- ce qui reste à faire ;
- où se trouve le travail (stash ou branche `wip/`).

### B3 · Handoff d'interruption

```
HANDOFF INTERROMPU — <date>
Ticket      : <ID>
Etape       : <n>/<total> du prompt
Travail     : stash "<message>" | branche wip/<ID>
Reste a faire : <liste>
Blocage     : <raison, ou "aucun — interruption externe">
```

> **À la reprise** : relire le prompt **depuis l'étape 1**, pas depuis l'étape interrompue.
> Le raisonnement d'une session ne se transmet pas ; le prompt, si.

---

## Cas C · Le ticket a échoué

Voir `EXECUTION_FLOW.md` §1. En résumé :

1. Annuler le travail (`git stash` / `git checkout --`), ne rien commiter.
2. Rédiger le compte rendu d'échec (gabarit `GOV-004`).
3. Marquer le ticket **BLOQUE** dans `IMPLEMENTATION_QUEUE.md` et `INDEX.md`, avec la raison.
4. Marquer les descendants directs comme non démarrables (`DEPENDENCY_GRAPH.md`).
5. Handoff mentionnant explicitement ce qui doit être tranché, et par qui.

---

## Contrôle final — commun aux trois cas

- [ ] `python -m pytest tests/ -q` lancé et comparé à la baseline
- [ ] `git status` propre (ou WIP explicitement rangé)
- [ ] Aucun fichier `.py`, test ou configuration modifié hors du périmètre du ticket
- [ ] `IMPLEMENTATION_QUEUE.md` à jour
- [ ] `INDEX.md` à jour
- [ ] `MASTER_ROADMAP.md` à jour (case cochée)
- [ ] `CHECKPOINTS.md` à jour **si** un checkpoint a bougé
- [ ] Journal `DEC-xxx` à jour **si** une décision a été prise
- [ ] Rapport de fin de ticket rédigé
- [ ] Bloc de handoff écrit
- [ ] **Aucun déploiement effectué** sans `--confirm` et sans vérification post-déploiement (`GOV-005`)

---

## Ce qu'il ne faut jamais faire en fin de session

- **Enchaîner sur le ticket suivant** « puisqu'il reste du temps ». Un ticket = une session ou une PR.
- **Reporter la mise à jour des statuts** à plus tard. La session suivante repartirait d'un état faux —
  et un index périmé est pire qu'aucun index.
- **Commiter pour « sauvegarder »** sans que le ticket soit terminé. Utiliser `stash` ou `wip/`.
- **Résumer qualitativement** un résultat chiffré. Si un chiffre a été mesuré, il figure au rapport.
- **Laisser un doute de gating non signalé.** S'il y a eu un doute, il doit apparaître dans le handoff,
  même s'il a été levé.
