# EXECUTION_FLOW — Que faire quand ça ne se passe pas comme prévu

> Procédures de traitement des échecs. Un ticket qui se déroule normalement n'a pas besoin de ce
> document : voir `COMMANDS.md`.
>
> **Principe directeur** : en cas de doute, **s'arrêter et signaler** coûte une session.
> **Improviser** peut coûter une époque (N → 0, irréversible).

---

## 1. Un ticket échoue (le travail ne peut pas aboutir)

**Symptôme** : une étape du prompt est impossible, une hypothèse `A CONFIRMER` est infirmée, ou un
critère de refus est atteint.

**Procédure :**
1. **Ne rien commiter.** `git status` doit être propre avant d'aller plus loin.
2. `git stash` ou `git checkout -- <fichiers>` pour revenir à l'état de départ.
3. Rédiger un compte rendu d'échec selon le gabarit de `GOV-004` :
   - **Observation** : ce qui a été effectivement constaté (commande, sortie).
   - **Inférence** : pourquoi le ticket ne peut pas aboutir, avec sa portée.
   - **Décision** : ce qu'il faut trancher, et par qui.
4. Marquer le ticket **BLOQUE** dans `IMPLEMENTATION_QUEUE.md` et `INDEX.md`, avec la raison.
5. Consulter `DEPENDENCY_GRAPH.md` § « Règle de propagation d'un échec » : marquer les descendants
   directs comme **non démarrables**.
6. **S'arrêter.** Ne pas prendre le ticket suivant « en attendant ».

**Interdiction** : ne jamais modifier le ticket pour le rendre réalisable. Un ticket qui ne passe pas
révèle soit une erreur de diagnostic, soit un changement du code — les deux méritent un arbitrage,
pas un contournement.

---

## 2. Un test échoue

Trois cas, à distinguer **avant** toute action.

### 2a. Le test échoue et c'est le résultat attendu
Cas de `OBS-001` : le test rouge **doit** échouer. Ce n'est pas un incident.
→ Poursuivre. Le noter explicitement dans le compte rendu.

### 2b. Le test échoue à cause du ticket en cours
→ Corriger, dans le périmètre du ticket uniquement. Relancer. Si trois tentatives échouent,
traiter comme un échec de ticket (§1).

### 2c. Un test ÉTRANGER au ticket échoue
→ **Ne pas le corriger.** C'est la règle la plus importante de cette section.
1. Vérifier qu'il échouait déjà dans la baseline relevée en début de ticket.
   - **Oui** → échec préexistant, hors périmètre. Le signaler, poursuivre.
   - **Non** → **le ticket a causé une régression hors de son périmètre.** Traiter comme §1 :
     annuler, ne pas commiter, signaler.
2. Ne jamais « réparer » un test étranger pour faire passer la suite : cela masque une régression
   réelle et pollue le diff.

> **Corollaire** : relever la baseline **avant** de commencer n'est pas une formalité.
> Sans elle, on ne peut pas distinguer 2b de 2c.

---

## 3. Un rollback est nécessaire

**Deux niveaux, à ne jamais confondre.**

### 3a. Rollback technique (toujours possible)
```bash
git revert <sha-du-ticket>
```
Un ticket = un commit atomique ⇒ le revert est ciblé et sûr.
Après revert : remettre le ticket en **PRET** dans `IMPLEMENTATION_QUEUE.md` et `INDEX.md`,
et noter au journal `DEC-xxx` pourquoi.

### 3b. Rollback d'époque — **N'EXISTE PAS**
Une fois `PORT-006` déployé et la borne V5 posée, les décisions prises sous le nouveau comportement
appartiennent à la nouvelle époque. `git revert` restaure le **code**, jamais la **mesure**.
Revenir en arrière créerait une troisième époque hybride, pire que les deux.

> C'est la raison d'être des quatre préconditions de la porte d'époque.
> **Avant `PORT-002`, tout est réversible. Après, plus rien ne l'est côté scientifique.**

### 3c. Rollback de déploiement VPS
Redéployer le tag de repli identifié **avant** le déploiement
(`GOV-005` impose de le noter en prérequis), puis vérifier côté serveur
(SHA VPS = SHA attendu, service actif). Un tag n'est pas une preuve : voir l'incident du 2026-07-09.

---

## 4. Un ticket est interrompu en cours de route

**Symptôme** : fin de session, coupure, limite atteinte, interruption par l'opérateur.

**Procédure :**
1. Ne **pas** commiter un travail partiel sur la branche de travail.
2. Deux options :
   - `git stash push -m "WIP <TICKET-ID>"` — si la reprise est proche.
   - Commit sur une **branche de travail dédiée** `wip/<TICKET-ID>` — si la reprise est lointaine.
     Ne jamais laisser un WIP sur `main`.
3. Dans `IMPLEMENTATION_QUEUE.md`, passer le ticket en **EN COURS**, avec : date, étape atteinte
   (numéro d'étape du prompt), ce qui reste à faire.
4. Suivre `SESSION_SHUTDOWN.md`.

**À la reprise** : relire le prompt **en entier** depuis l'étape 1, pas depuis l'étape interrompue.
Le contexte d'une session ne se transmet pas ; le prompt, si.

---

## 5. Changement de session Claude

Le contexte conversationnel **ne survit pas**. Seuls les fichiers survivent.

**Procédure :** appliquer `SESSION_SHUTDOWN.md` avant, `SESSION_BOOTSTRAP.md` après.

**Ne jamais supposer** qu'une session suivante « se souvient » d'une décision, d'un arbitrage ou d'un
constat. Si ce n'est pas écrit dans `.claude/`, dans un ADR ou dans un commit, cela n'existe pas.

---

## 6. Un commit échoue

### 6a. Hook pre-commit en échec (`black`, `flake8`, `isort`, `bandit`)
→ Corriger **uniquement** ce que le hook signale, dans les fichiers du ticket.
Ne jamais utiliser `--no-verify` : les hooks sont un invariant de qualité du dépôt.
Si le hook signale un fichier **hors périmètre** du ticket, c'est que le diff déborde ⇒ vérifier
`git diff --cached --name-only` et retirer ce qui ne relève pas du ticket.

### 6b. Le diff contient plus que le ticket
→ `git reset` puis restaging sélectif. Un commit = un ticket, sans exception.

### 6c. Message de commit refusé ou incomplet
→ Reprendre le message **exact** fourni dans la section `LIVRABLES` du prompt. Ne pas l'abréger.

---

## 7. Une PR échoue

### 7a. CI rouge
1. Déterminer si l'échec est **préexistant** : comparer aux runs de la branche de base.
   *(Constat documenté au 2026-07-24 : plusieurs workflows du dépôt sont rouges indépendamment de
   toute modification — `CI/Lint`, `Coverage Report`, `Test Dashboards`, `Build & Deploy Sphinx Docs`.)*
2. **Préexistant** → le signaler dans la PR, ne pas le corriger dans ce ticket.
3. **Causé par le ticket** → §2b.

### 7b. La PR contient plus d'un ticket
→ Fermer la PR, refaire une branche propre depuis la base, un ticket par PR.

### 7c. Aucune review disponible
→ Ce n'est pas un blocage technique mais une **décision de gouvernance**. Voir `GOVERNANCE.md` :
qui a autorité pour merger, et sur quelles catégories de changement.

---

## 8. Conflit Git

### 8a. Conflit sur `core/advisor_loop.py`
Fichier de 7 776 lignes, touché par plusieurs tickets (`OBS-002`, `OBS-003`, `OBS-004`).
1. **Ne pas résoudre le conflit à l'aveugle.**
2. Identifier quel ticket a introduit chaque côté du conflit.
3. Si les deux côtés touchent la **même fonction** ⇒ les tickets n'étaient pas indépendants :
   c'est une erreur de séquencement. Rebaser sur le ticket terminé et refaire l'autre proprement.
4. Après résolution, **relancer la suite complète** : un conflit mal résolu dans ce fichier peut
   changer silencieusement un comportement.

### 8b. Conflit sur un fichier de `.claude/`
Typiquement `IMPLEMENTATION_QUEUE.md` ou `INDEX.md`, modifiés par deux sessions parallèles.
→ Résoudre en **conservant les deux mises à jour de statut**. Ces fichiers sont additifs par nature.

### 8c. Conflit sur `paper_trades.jsonl` ou un fichier de `databases/`
→ **STOP immédiat.** Ces fichiers ne doivent jamais être modifiés par un ticket (INV-3).
Un conflit ici signale une violation d'invariant. Ne pas résoudre : annuler et signaler.

---

## 9. Tableau de décision rapide

| Situation | Action immédiate | Peut-on continuer ? |
|---|---|---|
| Test rouge attendu (`OBS-001`) | Noter, poursuivre | Oui |
| Test du ticket échoue | Corriger dans le périmètre | Oui (3 tentatives max) |
| Test étranger échoue, préexistant | Signaler | Oui |
| Test étranger échoue, nouveau | Annuler, ne pas commiter | **Non** |
| Hypothèse `A CONFIRMER` infirmée | Signaler | **Non** |
| Diff déborde du périmètre | Restaging sélectif | Oui |
| Conflit sur `advisor_loop.py` | Identifier les tickets en cause | Oui, avec prudence |
| Conflit sur `paper_trades.jsonl` | **STOP** | **Non** |
| Un seuil devrait être modifié | **STOP** (INV-4) | **Non** |
| `pos_manager` / `check_new_trade` à modifier dans un ticket non gated | **STOP** (INV-2) | **Non** |
| Doute sur le gating d'un changement | **STOP**, demander | **Non** |

---

## 10. La règle qui prime sur toutes les autres

> **Si un doute porte sur le gating — « ce changement touche-t-il ce que le moteur regarde ? » —
> la réponse par défaut est OUI, et on s'arrête.**

Se tromper en s'arrêtant coûte une session.
Se tromper en continuant peut coûter le burn-in complet, sans retour possible.
Le coût des deux erreurs n'est pas symétrique : la conduite ne doit pas l'être non plus.
