# EXECUTION_GUIDE — Le système d'orchestration en un document

> Comment les 35 documents de `.claude/` s'articulent, et pourquoi il n'en faut lire que trois pour
> travailler.
>
> Ce document explique le **système**. Pour travailler, aller directement à `SESSION_BOOTSTRAP.md`.

---

## Le principe : trois documents suffisent

Le risque d'un système documentaire de cette taille est qu'il devienne **plus coûteux à naviguer que
le problème qu'il résout**. La conception vise donc un chemin court :

```
   SESSION_BOOTSTRAP.md   ──►   IMPLEMENTATION_QUEUE.md   ──►   prompts/PROMPT_<ID>.md
   (comprendre, 5 min)          (quel ticket)                   (comment le faire)
```

**Les 32 autres documents ne se lisent pas d'affilée.** Ils se consultent au besoin, via la carte de
`SESSION_BOOTSTRAP.md` § « Carte des documents ». Une session qui lit tout perd son temps ; une session
qui ne lit que ces trois-là travaille correctement.

---

## Les quatre couches du système

| Couche | Rôle | Documents | Change |
|---|---|---|---|
| **Constitution** | Ce qui ne se négocie pas | `GOVERNANCE.md`, `CLAUDE_IMPLEMENTATION.md` | Rarement, par ADR |
| **Connaissance** | Ce qu'on sait du système | `ARCHITECTURE.md` | Quand le code change |
| **Plan** | Ce qu'on va faire | `MASTER_ROADMAP.md`, `phases/`, `DEPENDENCY_GRAPH.md` | Par révision de phase |
| **Exécution** | Ce qu'on fait maintenant | `INDEX.md`, `IMPLEMENTATION_QUEUE.md`, `CHECKPOINTS.md`, `prompts/` | **À chaque ticket** |

La distinction importe : les couches basses sont **stables**, la couche Exécution est **vivante**.
Seuls quatre fichiers changent à chaque ticket : `IMPLEMENTATION_QUEUE.md`, `INDEX.md`,
`MASTER_ROADMAP.md` (case cochée), et `CHECKPOINTS.md` si un palier bouge.

---

## Le cycle de vie d'un ticket

```
   [ PRET ]
      │  START          ← SESSION_BOOTSTRAP.md
      ▼
   [ selectionne ]
      │  IMPLEMENT      ← prompts/PROMPT_<ID>.md
      ▼
   [ EN COURS ]────────► interruption ──► SESSION_SHUTDOWN.md cas B ──► [ EN COURS ]
      │  TEST / VERIFY
      ├──── echec ─────► EXECUTION_FLOW.md ──► [ BLOQUE ] ou ROLLBACK ──► [ PRET ]
      ▼
   [ valide ]
      │  COMMIT → PR
      ▼
   [ TERMINE ]
      │  FINISH         ← SESSION_SHUTDOWN.md cas A
      ▼
   mise a jour : IMPLEMENTATION_QUEUE / INDEX / MASTER_ROADMAP / CHECKPOINTS
      │
      ▼
   HANDOFF ──► fin de session (JAMAIS d'enchainement automatique)
```

---

## Les trois garde-fous du système

### 1. Le gating — la protection contre la perte irréversible

Une seule question, à poser pour **tout** changement :

> **« Ce changement modifie-t-il ce que le moteur REGARDE, ou seulement ce qu'il MONTRE ? »**

Ce qu'il **montre** → exécutable, N inchangé.
Ce qu'il **regarde** (`PositionManager`, `check_new_trade`, sizing, risk, `PortfolioBrain` en entrée,
seuils, `CLEAN_DATA_SINCE_*`) → **GATED**, reset d'époque, ADR signé obligatoire.

**En cas de doute : GATED, et on s'arrête.** Le coût des deux erreurs n'est pas symétrique — s'arrêter
à tort coûte une session, continuer à tort peut coûter le burn-in complet, sans retour possible.

### 2. L'atomicité — la protection contre l'irréversibilité technique

Un ticket = un commit = un `git revert` possible. C'est ce qui rend chaque pas du chantier annulable.
Deux tickets dans un commit détruisent cette propriété.

### 3. L'arrêt obligatoire — la protection contre la dérive

Une session exécute **un** ticket, puis s'arrête. Jamais d'enchaînement automatique.
C'est ce qui garantit qu'un humain voit chaque pas avant le suivant.

---

## Ce qui rend ce système faux

Un système de pilotage qui ment est pire qu'aucun système. Trois modes de défaillance, à surveiller :

| Défaillance | Symptôme | Prévention |
|---|---|---|
| **État périmé** | Un ticket terminé mais toujours `PRET` dans `INDEX.md` | `SESSION_SHUTDOWN.md` impose la mise à jour **avant** de fermer |
| **Duplication divergente** | Le même fait écrit dans deux documents qui divergent | Chaque document déclare ce dont il fait foi ; `INDEX.md` ne porte que des pointeurs |
| **Théâtre de conformité** | Des cases cochées sans vérification réelle | Chaque critère est **binaire et vérifiable** (une commande, une sortie attendue) |

> En cas de divergence entre deux documents, la hiérarchie de vérité est :
> **`git log` > `phases/` > `IMPLEMENTATION_QUEUE.md` > `INDEX.md`.**
> L'état réel du dépôt prime toujours sur ce qui est écrit à son sujet.

---

## Inventaire — 35 documents

**Racine (15)** — `README.md` · `SESSION_BOOTSTRAP.md` · `SESSION_SHUTDOWN.md` · `COMMANDS.md` ·
`EXECUTION_GUIDE.md` · `EXECUTION_FLOW.md` · `INDEX.md` · `DEPENDENCY_GRAPH.md` · `CHECKPOINTS.md` ·
`GOVERNANCE.md` · `CLAUDE_IMPLEMENTATION.md` · `ARCHITECTURE.md` · `MASTER_ROADMAP.md` ·
`IMPLEMENTATION_QUEUE.md` · `PROMPT_GUIDE.md`

**`phases/` (5)** — `PHASE_00` · `PHASE_01` · `PHASE_02_GATED` · `PHASE_03` · `PHASE_04_GATED`

**`prompts/` (15)** — un par ticket exécutable (`GOV`×5, `OBS`×5, `REST`×4, `PORT-001`)

**Absents volontairement (19)** — les prompts des tickets GATED. Leur contenu dépend de décisions non
prises (ADR d'époque, arbitrage D-2, résultat de `PORT-001`). Les rédiger maintenant figerait des choix
qui appartiennent à l'opérateur. Ils seront écrits au moment du déblocage ; leur détail figure dès
aujourd'hui dans `phases/PHASE_02_GATED.md` et `phases/PHASE_04_GATED.md`.

---

## Démarrer maintenant

```
Respecte .claude/CLAUDE_IMPLEMENTATION.md et exécute le ticket GOV-002.
```

- Premier ticket : **`GOV-002`** (documentaire, sans risque).
- Premier ticket touchant du code : **`OBS-001`** (tests rouges).
- Palier actuel : **L0**. Palier visé : **L1** (5 tickets `GOV`).

---

## Le rappel qui prime sur le reste

> Ce système pilote la **réparation d'un instrument de mesure**.
> Il ne dit rien sur la question de fond : *le système de trading a-t-il un edge ?*
>
> Atteindre le palier L4 signifiera que le système **mesure correctement** — pas qu'il **gagne**.
> Ne jamais confondre les deux.
