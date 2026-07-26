# SESSION_BOOTSTRAP — Ouvrir une session de travail

> **Point d'entrée unique.** Une nouvelle session Claude, sans aucun contexte, doit pouvoir travailler
> en moins de 5 minutes en suivant ce seul document.
>
> Si un seul fichier doit être lu en premier, c'est celui-ci.

---

## Chemin court — piloté par l'état (recommandé)

Depuis la mise en place du manifeste, **le chemin le plus rapide ne passe plus par les 35 documents** :

```
.claude/state/project_state.yaml    (ou en est le chantier — 15 lignes)
        ▼
.claude/state/current_ticket.yaml   (quel ticket, quel prompt — 10 lignes)
        ▼
.claude/prompts/PROMPT_<ID>.md      (comment le faire)
        ▼
CODE
```

Ces fichiers `state/` sont **générés** depuis `.claude/manifest.yaml` — ils ne peuvent pas diverger
de la source de vérité. Les lire prend moins d'une minute.

Le reste de la documentation (procédure détaillée ci-dessous, `GOVERNANCE.md`, `ARCHITECTURE.md`,
`DEPENDENCY_GRAPH.md`, `EXECUTION_FLOW.md`) ne se lit **qu'en cas de besoin**.

> **Après chaque ticket** : mettre à jour `.claude/manifest.yaml` (statut du ticket), puis lancer
> `python .claude/tools/render_docs.py`. Ne jamais éditer à la main un fichier portant le marqueur
> `GENERATED`.

---

## Procédure complète — 5 étapes, ~5 minutes

### Étape 1 · Comprendre le projet (60 s)

`crypto_ai_terminal` est un terminal de trading crypto IA, en **phase de validation scientifique**,
sous **gel fonctionnel**. Aucune nouvelle fonctionnalité n'est autorisée : seuls les outils de mesure,
d'audit et de correction de dette le sont.

Le chantier en cours corrige une **dette de sources de vérité multiples** (SSoT).
Le symptôme fondateur : le panneau Telegram affiche simultanément **« Positions: 3 »** et
**« Portfolio Exposure: 0.0% »**.

Cause racine : `core/advisor_loop.py:6786` passe `pos_manager.get_open()` à `portfolio_health()`,
or `pos_manager` est **vide en mode paper** — les positions vivent dans `_virtual_portfolio`
(MexcSimulator). Preuve : `free_cash = 674.47 × 0.40 − 0 = 269.79 $`, exactement la valeur affichée.

Conséquence non visible : les cinq contrôles de risque de `check_new_trade` s'exécutent sur un
portefeuille perçu comme vide — **le gate est trop permissif**.

### Étape 2 · Lire les règles non négociables (90 s)

Les **quatre invariants** :

| ID | Invariant | Violation = |
|---|---|---|
| **INV-1** | Passivité absolue des observers (ADR-0007) | Un observer influence une décision |
| **INV-2** | Aucun reset de N sans ADR d'époque signé | Modifier ce que le moteur **regarde** |
| **INV-3** | `paper_trades.jsonl` écrit uniquement par `mexc_simulator.py` et `recorder.py` | Écrire ou réécrire l'historique |
| **INV-4** | Aucun seuil modifié avant N ≥ 500 et CRI ≥ 90 | Toucher une constante de seuil |

La **règle de gating**, à appliquer à tout changement :

> **« Ce changement modifie-t-il ce que le moteur REGARDE, ou seulement ce qu'il MONTRE ? »**
>
> - Ce qu'il **montre** (panneau, REST, logs, docs) → **exécutable**, N inchangé.
> - Ce qu'il **regarde** (`PositionManager`, `check_new_trade`, sizing, risk, `PortfolioBrain`
>   en entrée, seuils, `CLEAN_DATA_SINCE_*`) → **GATED**, reset d'époque, ADR signé obligatoire.

**En cas de doute sur le gating : la réponse par défaut est GATED, et on s'arrête.**

### Étape 3 · Connaître l'état du chantier (60 s)

```bash
git log --oneline -5
git status --short
```

Puis ouvrir **`.claude/INDEX.md`** — il donne en un tableau : les 34 tickets, leur statut, leurs
dépendances, leur prompt associé et leur niveau de risque.

Repères au 2026-07-24 : **5 phases · 34 tickets · 15 PRET · 19 BLOQUE · 0 TERMINE.**

### Étape 4 · Identifier le ticket courant (60 s)

Ouvrir **`.claude/IMPLEMENTATION_QUEUE.md`** :

1. Si un ticket est en file **EN COURS** → c'est celui-là. Lire la note de reprise.
   Relire son prompt **depuis l'étape 1**, jamais depuis l'étape interrompue.
2. Sinon → prendre le **premier de la file PRET** dont **toutes** les dépendances sont en **TERMINE**.
3. Vérifier son niveau de risque dans `INDEX.md`. Si `CRITIQUE` ⇒ vérifier les quatre préconditions
   de la porte d'époque avant toute chose.

**Au démarrage du chantier** : le premier ticket est **`GOV-002`** (documentaire).
Le premier ticket touchant du code est **`OBS-001`**.

### Étape 5 · Ouvrir le prompt et relever la baseline (60 s)

```bash
python -m pytest tests/ -q
```

**Noter le résultat.** Cette baseline est indispensable : sans elle, il sera impossible de distinguer
une régression causée par le ticket d'un échec préexistant (voir `EXECUTION_FLOW.md` §2c).

Puis ouvrir `.claude/prompts/PROMPT_<ID>.md` — il est auto-portant et suffit à exécuter le ticket.

---

## Formulation de démarrage

Pour lancer une session, écrire exactement :

```
Respecte .claude/CLAUDE_IMPLEMENTATION.md et exécute le ticket <ID>.
```

Ou, pour laisser la session choisir :

```
Lis .claude/SESSION_BOOTSTRAP.md, prends le premier ticket PRET de
.claude/IMPLEMENTATION_QUEUE.md et exécute-le. Arrête-toi après.
```

---

## Ce qu'une session ne doit jamais supposer

- **Qu'elle se souvient.** Le contexte conversationnel ne survit pas. Si ce n'est pas écrit dans
  `.claude/`, dans un ADR ou dans un commit, **cela n'existe pas**.
- **Qu'une décision a été prise.** Vérifier le journal `DEC-xxx` (`GOV-003`).
- **Que la CI est verte.** Plusieurs workflows du dépôt sont rouges indépendamment de toute
  modification (constat du 2026-07-24). Relever la baseline, toujours.
- **Qu'un numéro de ligne est exact.** Le code évolue. Un numéro de ligne faux n'est pas bloquant ;
  une **structure de code différente de celle décrite** l'est.

---

## Carte des documents — quand lire quoi

| Besoin | Document |
|---|---|
| Démarrer une session | **ce document** |
| Voir l'état de tous les tickets | `INDEX.md` |
| Savoir quel ticket prendre | `IMPLEMENTATION_QUEUE.md` |
| Exécuter un ticket | `prompts/PROMPT_<ID>.md` |
| Comprendre les règles du projet | `GOVERNANCE.md` |
| Comprendre le protocole de travail | `CLAUDE_IMPLEMENTATION.md` |
| Comprendre le système technique | `ARCHITECTURE.md` |
| Situer un ticket dans le plan | `MASTER_ROADMAP.md` |
| Savoir ce qui dépend de quoi | `DEPENDENCY_GRAPH.md` |
| Un problème survient | `EXECUTION_FLOW.md` |
| Connaître les commandes | `COMMANDS.md` |
| Savoir où en est le chantier | `CHECKPOINTS.md` |
| Terminer une session | `SESSION_SHUTDOWN.md` |

**Ne pas lire les 27 documents.** Ce tableau existe pour l'éviter.

---

## Contrôle de démarrage

Avant d'écrire la première ligne, ces cinq réponses doivent être connues :

- [ ] Quel ticket ? (ID exact)
- [ ] Est-il GATED ? (si oui : les 4 préconditions sont-elles réunies ?)
- [ ] Ses dépendances sont-elles TERMINE ?
- [ ] Quelle est la baseline de tests ?
- [ ] Quels fichiers ai-je le droit de toucher ? (section `FICHIERS` du prompt)

Si une seule réponse manque, **ne pas commencer**.
