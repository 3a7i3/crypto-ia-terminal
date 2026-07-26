# PHASE_00 — Socle de gouvernance du chantier

> **Préfixe d'ID imposé pour cette phase : `GOV-xxx`.** Aucun autre préfixe n'est autorisé ici.
> **Statut de gating : NON GATED — exécutable sous le gel scientifique.**
> **Nature des livrables : documentation et ADR uniquement. Zéro ligne de code, zéro test modifié.**
>
> **Convention épistémique** (protocole v3, `docs/protocole_audit_epistemique.md`) :
> `[O]` = Observation (lue dans le code à la ligne citée), `[I]` = Inférence,
> `[H]` = Hypothèse non vérifiée, `[D]` = Décision.
> Toute information non présente dans le diagnostic validé est marquée
> **A CONFIRMER AU DEMARRAGE DU TICKET**. Rien n'est inventé.

---

## Objectif

Poser le socle documentaire opposable du chantier « cohérence d'affichage portefeuille / SSoT »
avant toute modification de code, quelle que soit la phase suivante.

Objectifs vérifiables :

1. **[D]** Acter par ADR (numéro libre à partir de `ADR-0019`) trois choses distinctes :
   (a) l'existence et la cause racine du bug d'observabilité `Positions: 3` / `Portfolio Exposure: 0.0%` ;
   (b) la **non-correction volontaire** de ce bug côté décision sous le gel scientifique ;
   (c) la **séparation formelle** entre **exposition d'affichage** et **exposition-gate**.
2. **[D]** Rendre le registre des invariants du chantier (`INV-1` à `INV-4`) opposable : chaque
   invariant doit être associé à un symbole concret du code et à une commande de contrôle binaire.
3. **[D]** Ouvrir un journal des décisions du chantier : qui décide, quoi, quand, sur quelle preuve.
4. **[D]** Figer le gabarit de rapport de fin de ticket, aligné sur le protocole d'audit épistémique v3
   (une phrase = une catégorie, maillon faible, portée explicite, double falsificateur, dette épistémique).
5. **[D]** Figer la checklist de déploiement VPS et de vérification post-déploiement, pour que les
   phases suivantes n'improvisent jamais un déploiement.

**Ce que la phase ne fait pas :** elle ne corrige aucun affichage, ne touche aucun store de positions,
ne modifie aucun seuil, ne déploie rien. Elle produit uniquement le référentiel qui rendra les
phases 01 à 04 vérifiables.

---

## Contexte

**[O]** Le même panneau Telegram affiche simultanément `Positions: 3` et `Portfolio Exposure: 0.0%`.
Premier point d'incohérence : `core/advisor_loop.py:6786`, qui passe `pos_manager.get_open()` à
`portfolio_brain.portfolio_health()` (`core/advisor_loop.py:6785-6787`).

**[O]** En mode paper, les positions sont ouvertes dans `_virtual_portfolio` (MexcSimulator) via
`place_market_order` (`core/advisor_loop.py:2176`), pas dans `PositionManager`. `pos_manager` est donc vide.

**[O]** `quant_hedge_ai/agents/risk/portfolio_brain.py:668-687` (`_snapshot()`) somme
`total_exposure_usd += p.size_usd` et `n_positions += 1` sur la liste reçue ; liste vide ⇒ exposition 0.
`portfolio_health()` (`portfolio_brain.py:645-664`) renvoie alors
`free_capital = max(0, capital * MAX_TOTAL_EXPOSURE_PCT - total_exposure_usd)` avec
`MAX_TOTAL_EXPOSURE_PCT = 0.40` (`portfolio_brain.py:88`).

**[O]** Preuve numérique : `free_cash` affiché = `269.79` = `674.47 × 0.40 − 0`, ce qui confirme
`total_exposure_usd = 0`. **[O]** Preuve 2 : le bloc `POSITIONS:` est absent des rapports
(condition `open_count > 0`, `core/advisor_loop.py:6971`).

**[O]** Le comptage `n_open = 3` vient d'un autre store : `_display_position_summary`
(`core/advisor_loop.py:434-459`) lit `_virtual_portfolio.get_open_positions_summary()`
(`core/advisor_loop.py:450-453`), avec repli sur `pb_health` si `None` (`:456-459`).

**[O]** Le bug est déjà documenté et **gelé volontairement** dans le code : docstring
`core/advisor_loop.py:437-448` — « pos_manager reste la source des contraintes de décision …
jamais modifié ici, corriger son entrée changerait le comportement de décision en pleine validation
scientifique. Ce bug est documenté, gelé, à corriger à la calibration. » Régression historique
documentée `core/advisor_loop.py:462-471` (2026-07-12 21:00 UTC).

**[O]** Audit SSoT validé : **0 PASS / 1 WARNING / 8 FAIL** (capital, equity, cash, positions,
exposure, PnL, win_rate, drawdown en FAIL ; `free_cash` en WARNING).

**[I]** Sans ADR préalable, toute correction d'affichage en phase 01 serait indistinguable, pour un
lecteur futur, d'une correction de l'entrée de décision — donc indistinguable d'un changement d'époque.
L'ADR est la pièce qui rend cette distinction vérifiable a posteriori.

**[O]** État du dépôt au 2026-07-25 (constaté par listage) :
- `.claude/` contient déjà `GOVERNANCE.md` (443 lignes), `ARCHITECTURE.md` (504 lignes),
  `settings.local.json`, `scheduled_tasks.lock`.
- `.claude/phases/` et `.claude/prompts/` **n'existent pas encore**.
- `.claude/GOVERNANCE.md` contient déjà une section `## 2. Les 4 invariants du chantier`
  avec `INV-1` (passivité), `INV-2` (aucun reset de N sans ADR signé), `INV-3` (`paper_trades.jsonl`
  intact), `INV-4` (sizing épinglé à `WALLET_PAPER_CAPITAL`), et une section `## 3. Registre des ADR`.
- `docs/adr/` contient `0000-template.md` et les ADR `0001` → `0017`, en nommage
  `NNNN-titre-en-kebab.md`. **[O]** Deux fichiers portent le numéro `0008`
  (`0008-ds001-runtime-path-resolution.md` et `0008-scientific-intelligence-layer.md`) : collision
  de numérotation déjà présente. **[O]** `ADR-0018-regret-source-canonical-v2.md` est à la racine
  `docs/`, pas dans `docs/adr/`, avec une convention de nommage différente.

---

## Dépendances

| Dépendance | Nature | État |
|---|---|---|
| Diagnostic validé (cause racine, lignes citées) | Entrée obligatoire | Fourni, validé, non re-enquêté |
| `CLAUDE.md` (règles invariantes, bornes d'époque) | Référence normative supérieure | Présent |
| `docs/protocole_audit_epistemique.md` (v3) | Gabarit de rédaction | Présent (fusionné dans `main`) |
| `docs/adr/0000-template.md` | Gabarit d'ADR | Présent, **contenu à lire au démarrage de GOV-001** |
| `.claude/GOVERNANCE.md` | Cible d'édition GOV-002 / GOV-003 / GOV-005 | Présent, 443 lignes |
| `.claude/PROMPT_GUIDE.md` | Cible d'édition GOV-004 | **A CONFIRMER AU DEMARRAGE DU TICKET** (absent au 2026-07-25) |
| Phases 01 → 04 | Consommateurs du socle | Bloquées tant que PHASE_00 n'est pas close |

**Aucune dépendance envers un ticket d'une autre phase.** PHASE_00 est la racine du graphe.

---

## Prérequis

1. Dépôt `main` propre avant le premier ticket : `git status --short` renvoie une sortie vide.
2. Lecture faite de : `CLAUDE.md`, `.claude/GOVERNANCE.md`, `docs/protocole_audit_epistemique.md`,
   `docs/adr/0000-template.md`.
3. Numéro d'ADR libre confirmé : `git ls-files "docs/adr/0019*" "docs/ADR-0019*"` renvoie une sortie vide.
4. Aucun déploiement VPS en cours, aucun redémarrage du moteur planifié pendant la phase
   (PHASE_00 ne déploie rien, mais un redémarrage concurrent brouillerait les vérifications d'invariance de N).
5. Relevé de N (nombre de trades fermés de l'époque V4) noté avant le premier ticket, pour comparaison
   en fin de phase. **A CONFIRMER AU DEMARRAGE DU TICKET** : invocation exacte à utiliser
   (`tools/cri_calculator.py::load_clean_trades` est la source canonique citée par `CLAUDE.md`).

---

## Risques

| # | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Un ticket « documentaire » modifie par glissement un fichier `.py` | Faible | **Critique** (reset d'époque, N→0) | Contrôle binaire imposé dans chaque ticket : `git diff --name-only <base>..HEAD -- ":!*.md"` doit être vide |
| R2 | Collision de numéro d'ADR (précédent connu : deux `0008`) | Moyenne | Moyen | Prérequis 3 : vérification `git ls-files` avant écriture |
| R3 | L'ADR est rédigé comme une prescription de correctif au lieu d'une décision | Moyenne | Moyen | L'ADR déclare une séparation de concepts + un gel ; il n'ordonne aucun patch |
| R4 | La séparation « affichage » / « gate » est comprise comme une autorisation de faire converger les deux | Faible | **Critique** | L'ADR marque explicitement toute convergence comme GATED / RESET D'ÉPOQUE / ADR OBLIGATOIRE |
| R5 | Édition concurrente de `.claude/GOVERNANCE.md` par plusieurs tickets | Moyenne | Faible | Ordre strict GOV-001 → GOV-002 → GOV-003 → GOV-005 ; sections disjointes, ajout en fin de fichier |
| R6 | Le lecteur futur prend l'ADR pour un acte d'acceptation opérateur | Moyenne | Moyen | L'ADR naît en statut **Proposé** ; passage à **Accepté** uniquement par entrée signée dans le journal (GOV-003) |
| R7 | Documentation produite mais jamais utilisée par les phases suivantes | Moyenne | Moyen | GOV-004 (gabarit de rapport) est cité comme critère Done de tout ticket des phases 01 → 04 |

---

## Architecture

PHASE_00 n'introduit aucune architecture logicielle. Elle introduit une **architecture de vocabulaire**,
qui conditionne toutes les phases suivantes.

Deux grandeurs sont aujourd'hui confondues sous le même mot « exposition » :

| Grandeur | Nom imposé | Producteur **[O]** | Consommateur | Peut être corrigée sous le gel ? |
|---|---|---|---|---|
| Exposition montrée à l'opérateur | **exposition d'affichage** | doit dériver du store qui compte les positions affichées, c.-à-d. `_virtual_portfolio` (MexcSimulator), `core/advisor_loop.py:450-453` | panneaux Telegram, snapshots | **Oui** — architecture A, phase 01, NON GATED |
| Exposition qui contraint la décision | **exposition-gate** | `portfolio_brain.portfolio_health(pos_manager.get_open())`, `core/advisor_loop.py:6785-6787` → `portfolio_brain.py:645-664`, `:668-687` | contraintes de trade, sizing, risk | **Non** — GATED / RESET D'ÉPOQUE / N → 0 / ADR OBLIGATOIRE |

**[D]** Règle de vocabulaire issue de la phase : les deux termes ne sont jamais interchangeables,
jamais affichés sous le même libellé, et une valeur de l'un ne peut jamais alimenter l'autre
(conséquence directe d'ADR-0007, passivité absolue des observers).

**[I]** Cette séparation est ce qui rend l'architecture A (phase 01) compatible avec le gel : corriger
l'affichage ne touche pas `pos_manager`, donc ne change pas le comportement de décision, donc ne
déclenche pas de reset d'époque (ADR-0017).

Chaîne documentaire produite :

```
ADR-0019 (docs/adr/)                  ← décision de fond, opposable, versionnée
   │
   ├─→ .claude/GOVERNANCE.md §2+      ← invariants INV-1..INV-4 rendus testables
   │        │
   │        └─→ .claude/GOVERNANCE.md ← procédure de déploiement + vérification
   │
   ├─→ .claude/DECISION_JOURNAL.md    ← qui décide quoi, quand, sur quelle preuve
   │
   └─→ .claude/PROMPT_GUIDE.md        ← gabarit de rapport de fin de ticket (protocole v3)
```

---

## Fichiers concernés

**Créés :**

| Chemin | Ticket | Nature |
|---|---|---|
| `docs/adr/0019-exposition-affichage-vs-exposition-gate.md` | GOV-001 | ADR, statut initial `Proposé` |
| `.claude/DECISION_JOURNAL.md` | GOV-003 | Journal append-only |
| `.claude/PROMPT_GUIDE.md` | GOV-004 | Gabarit de rapport (si absent ; sinon édition) |

**Modifiés :**

| Chemin | Ticket | Portion |
|---|---|---|
| `.claude/GOVERNANCE.md` | GOV-001 | §3 « Registre des ADR » : une ligne pour ADR-0019 |
| `.claude/GOVERNANCE.md` | GOV-002 | Nouvelle sous-section « matrice de vérification des invariants » |
| `.claude/GOVERNANCE.md` | GOV-003 | Renvoi vers `.claude/DECISION_JOURNAL.md` |
| `.claude/GOVERNANCE.md` | GOV-005 | Nouvelle section « déploiement VPS et vérification » |

**Lus, jamais modifiés (référence uniquement) :**
`core/advisor_loop.py`, `quant_hedge_ai/agents/risk/portfolio_brain.py`,
`paper_trading/mexc_simulator.py`, `paper_trading/ledger.py`, `observability/system_snapshot.py`,
`scripts/deploy_vps.sh`, `scripts/data_quality.py`, `tools/cri_calculator.py`, `CLAUDE.md`,
`docs/protocole_audit_epistemique.md`, `docs/adr/0000-template.md`.

**Interdits d'écriture sur toute la phase :** tout `*.py`, tout `tests/**`, tout `*.json`,
`*.yaml`, `*.yml`, `*.env`, `*.sh`, `*.service`, ainsi que `databases/**`.

---

## Invariants

Les quatre invariants du chantier sont déjà énoncés dans `.claude/GOVERNANCE.md §2` **[O]**.
PHASE_00 ne les redéfinit pas : elle les rend **testables**. Rappel de leur portée pour cette phase :

| Invariant | Énoncé (portée PHASE_00) | Contrôle binaire de la phase |
|---|---|---|
| **INV-1 — Passivité (ADR-0007)** | Aucun artefact de PHASE_00 n'est lu par le pipeline de décision | Les livrables sont des `.md` hors chemins d'import Python ⇒ `git diff --name-only <base>..HEAD -- ":!*.md"` vide |
| **INV-2 — Aucun reset de N sans ADR signé** | PHASE_00 ne change aucune entrée de décision, donc N est conservé | Même contrôle + relevé de N identique (hors trades naturels) avant/après |
| **INV-3 — `paper_trades.jsonl` intact** | PHASE_00 n'ouvre aucun chemin d'écriture vers le dataset | `git diff --name-only <base>..HEAD` ne contient aucun fichier de `paper_trading/` ni `databases/` |
| **INV-4 — Sizing épinglé à `WALLET_PAPER_CAPITAL`** | Aucun paramètre de sizing n'est touché | Aucun `.py`/`.env`/`.json` modifié |

**Invariant propre à la phase :**

**INV-PH00 — Documentation seule.** Un ticket GOV-xxx dont le diff contient un fichier non `.md`
est refusé et reverté sans discussion, quel que soit son contenu.

**Falsificateur de la phase (protocole v3) :** si, après clôture de PHASE_00, un fichier `.py` du dépôt
diffère de son état à l'ouverture de la phase, la phase est déclarée en échec et intégralement revertée.

---

## Validation

Validation de phase (à exécuter après le dernier ticket, `<base>` = SHA du commit précédant GOV-001) :

| # | Commande | Sortie attendue |
|---|---|---|
| V1 | `git diff --name-only <base>..HEAD -- ":!*.md"` | **vide** |
| V2 | `git diff --name-only <base>..HEAD` | exactement : `.claude/DECISION_JOURNAL.md`, `.claude/GOVERNANCE.md`, `.claude/PROMPT_GUIDE.md`, `.claude/phases/PHASE_00.md`, `docs/adr/0019-exposition-affichage-vs-exposition-gate.md` |
| V3 | `git log --oneline <base>..HEAD` | 5 commits, un par ticket GOV-001 → GOV-005 |
| V4 | `git grep -n "exposition-gate" -- docs/adr/0019-*.md .claude/GOVERNANCE.md` | au moins 1 occurrence dans chaque fichier |
| V5 | `git grep -c "INV-1\|INV-2\|INV-3\|INV-4" -- .claude/GOVERNANCE.md` | ≥ 4 |
| V6 | `git ls-files "docs/adr/0019*"` | 1 seul fichier (pas de collision, cf. précédent `0008`) |
| V7 | `git status --short` | vide |
| V8 | Relevé de N (époque V4) | identique au relevé du prérequis 5, aux trades naturels près (aucune variation imputable à la phase) |

**Aucun test unitaire n'est exécuté ni modifié par cette phase** : il n'y a pas de code à couvrir.
La suite de tests existante doit rester strictement inchangée — c'est vérifié par V1.

---

## Rollback

Rollback par ticket (un ticket = un commit) :

```
git revert --no-edit <sha_du_ticket>
```

Rollback de phase complète :

```
git revert --no-edit <sha_GOV-005> <sha_GOV-004> <sha_GOV-003> <sha_GOV-002> <sha_GOV-001>
```

Propriétés :

- **[O]** Aucun artefact de PHASE_00 n'est déployé ni chargé par un service ⇒ le rollback ne
  nécessite ni redémarrage, ni déploiement VPS, ni intervention sur l'état runtime.
- **[I]** Le rollback documentaire n'a aucun effet sur N, sur `paper_trades.jsonl`, ni sur l'époque V4.
- Un ADR reverté doit être **tracé** dans `.claude/DECISION_JOURNAL.md` (entrée « décision annulée »),
  jamais effacé silencieusement.

---

## Estimation

| Ticket | Estimation | Fichiers | Lignes modifiées (plafond) |
|---|---|---|---|
| GOV-001 | 2 h 00 | 2 | ≤ 220 |
| GOV-002 | 1 h 00 | 1 | ≤ 90 |
| GOV-003 | 1 h 00 | 2 | ≤ 120 |
| GOV-004 | 1 h 30 | 1 | ≤ 200 |
| GOV-005 | 1 h 30 | 1 | ≤ 160 |
| **Total** | **7 h 00** | **5 fichiers distincts** | **≤ 790** |

Tous les tickets respectent la contrainte d'atomicité : ≤ 300 lignes modifiées **et** ≤ 4 fichiers.

---

## Tickets

### GOV-001 — ADR-0019 : séparation exposition d'affichage / exposition-gate

- **ID** : `GOV-001`
- **Titre** : Rédiger ADR-0019 actant le bug d'observabilité, son gel côté décision, et la séparation
  formelle « exposition d'affichage » vs « exposition-gate »
- **Objectif** : produire une décision d'architecture versionnée, opposable et citable par tous les
  tickets ultérieurs, qui (a) constate le bug, (b) déclare sa non-correction côté décision sous le gel,
  (c) impose deux noms distincts pour deux grandeurs aujourd'hui confondues.
- **Pourquoi** : **[I]** sans cet ADR, la correction d'affichage prévue en phase 01 est indistinguable
  d'une modification d'entrée de décision pour un auditeur futur ; **[O]** le projet exige un ADR pour
  toute décision structurante (`CLAUDE.md`, registre `docs/adr/` 0001→0018) ; **[I]** l'ADR est la seule
  pièce qui permet à un ticket NON GATED de prouver qu'il ne déclenche pas de reset d'époque.
- **Diagnostic résumé** :
  1. **[O]** `core/advisor_loop.py:6785-6787` appelle `portfolio_brain.portfolio_health(pos_manager.get_open())`.
  2. **[O]** En mode paper, les positions vivent dans `_virtual_portfolio` (MexcSimulator), ouvertes via
     `place_market_order` (`core/advisor_loop.py:2176`) ; `pos_manager` est vide.
  3. **[O]** `portfolio_brain.py:668-687` (`_snapshot()`) somme `p.size_usd` et compte `n_positions` sur
     la liste reçue ⇒ liste vide ⇒ `total_exposure_usd = 0`, `n_positions = 0`.
  4. **[O]** `portfolio_brain.py:645-664` renvoie `free_capital = max(0, capital × 0.40 − 0)` avec
     `MAX_TOTAL_EXPOSURE_PCT = 0.40` (`portfolio_brain.py:88`) ; preuve numérique `269.79 = 674.47 × 0.40`.
  5. **[O]** Le comptage affiché vient d'ailleurs : `_display_position_summary`
     (`core/advisor_loop.py:434-459`) lit `_virtual_portfolio.get_open_positions_summary()` (`:450-453`).
  6. **[O]** Le bloc `POSITIONS:` est absent des rapports (`core/advisor_loop.py:6971`, condition
     `open_count > 0`) ⇒ confirmation indépendante que `pos_manager` est vide.
  7. **[O]** Le gel est déjà écrit dans le code : docstring `core/advisor_loop.py:437-448`
     (« corriger son entrée changerait le comportement de décision en pleine validation scientifique »).
  8. **[O]** Régression historique tracée : `core/advisor_loop.py:462-471` (2026-07-12 21:00 UTC,
     `POSITIONS 0` affiché alors que le ledger MexcSim portait 3 positions BTC/BNB/ETH).
- **Contexte** : **[O]** `docs/adr/` contient `0000-template.md` et `0001` → `0017` en nommage
  `NNNN-titre-kebab.md` ; **[O]** `ADR-0018-regret-source-canonical-v2.md` est à la racine `docs/` avec
  une autre convention ; **[O]** un doublon de numéro existe déjà (`0008` ×2). Le ticket adopte la
  convention majoritaire `docs/adr/0019-….md` et vérifie l'unicité du numéro avant écriture.
  **A CONFIRMER AU DEMARRAGE DU TICKET** : sections exactes imposées par `docs/adr/0000-template.md`.
- **Hypothèses** :
  - **[H1]** Le numéro `0019` est libre. Vérifiable par `git ls-files "docs/adr/0019*" "docs/ADR-0019*"`.
    Si occupé, prendre le premier numéro libre et le mentionner en tête d'ADR.
  - **[H2]** Le gabarit `0000-template.md` est applicable tel quel. Si le gabarit impose des sections
    non pertinentes, elles sont conservées et remplies par « Sans objet — chantier documentaire ».
  - **[H3]** L'opérateur n'a pas encore statué sur l'architecture A/B/C. L'ADR **constate** l'arbitrage
    documenté (A = NON GATED, B et C = GATED) mais ne prononce aucune acceptation à la place de l'opérateur :
    statut initial **Proposé**.
- **Invariants** : INV-1 (aucun symbole de décision touché), INV-2 (aucune entrée de décision modifiée
  ⇒ pas de reset de N), INV-3, INV-4, INV-PH00 (documentation seule).
  **Démonstration explicite de non-atteinte à l'entrée de décision** : le ticket ne crée qu'un fichier
  `.md` dans `docs/adr/` et n'ajoute qu'une ligne de tableau dans `.claude/GOVERNANCE.md` ; aucun module
  Python n'importe ces chemins ; contrôle binaire : `git diff --name-only HEAD~1..HEAD -- ":!*.md"` vide.
- **Fichiers** (2) :
  - `docs/adr/0019-exposition-affichage-vs-exposition-gate.md` — **créé**
  - `.claude/GOVERNANCE.md` — **modifié**, §3 « Registre des ADR », une ligne ajoutée
- **Pseudo-code** (description non exécutable) :

```
DOCUMENT ADR-0019
  TITRE           : "Exposition d'affichage et exposition-gate — deux grandeurs, deux noms"
  STATUT          : "Proposé"   # jamais "Accepté" par l'agent
  DATE            : date du jour
  DECIDEUR        : "Opérateur (Mathieu) — signature requise, cf. DECISION_JOURNAL"
  REDACTEUR       : "Agent, sur diagnostic validé"

  SECTION Contexte
    RAPPELER  le symptôme          -> "Positions: 3" et "Portfolio Exposure: 0.0%" dans le même panneau
    CITER     advisor_loop.py:6785-6787, :2176, :434-459, :450-453, :6971
    CITER     portfolio_brain.py:645-664, :668-687, :88
    CITER     la preuve numérique  -> 269.79 = 674.47 × 0.40 − 0
    CITER     le gel déjà écrit    -> docstring advisor_loop.py:437-448
    RAPPELER  l'audit SSoT         -> 0 PASS / 1 WARNING / 8 FAIL

  SECTION Décision
    DECISION_1 : NOMMER "exposition d'affichage"  la grandeur montrée à l'opérateur
    DECISION_2 : NOMMER "exposition-gate"         la grandeur qui contraint la décision
    DECISION_3 : INTERDIRE tout transfert de valeur de l'une vers l'autre   # ADR-0007
    DECISION_4 : DECLARER le bug côté décision GELÉ, non corrigé, sous le gel scientifique
    DECISION_5 : CLASSER  correction d'affichage seule  -> NON GATED
    DECISION_6 : CLASSER  toute unification des deux    -> GATED / RESET D'ÉPOQUE / N -> 0 / ADR OBLIGATOIRE

  SECTION Conséquences
    POUR CHAQUE architecture DANS {A, B, C}
        ECRIRE  portée, coût, gating, condition de déblocage
    FIN POUR
    ECRIRE  condition de déblocage commune -> checkpoint L2 franchi
                                          ET N >= 100 sur l'époque courante
                                          ET ADR d'époque signé par l'opérateur

  SECTION Falsificateurs        # protocole v3 : deux, obligatoires
    FALSIFICATEUR_1 : "si un panneau affiche une exposition non nulle alors que pos_manager est vide
                       ET que cette valeur est lue par une contrainte de décision, la séparation est violée"
    FALSIFICATEUR_2 : "si un ticket NON GATED modifie un symbole listé comme entrée de décision,
                       le classement NON GATED de cet ADR est faux"

  SECTION Dette épistémique
    ECRIRE  "cet ADR ne démontre pas que l'exposition-gate est correcte ;
             il déclare seulement qu'elle ne sera pas corrigée maintenant"
FIN DOCUMENT

DOCUMENT .claude/GOVERNANCE.md
  DANS section "3. Registre des ADR"
     AJOUTER une ligne : numéro 0019 | titre | date | statut "Proposé" | invariant lié "INV-1, INV-2"
  NE RIEN SUPPRIMER, NE RIEN REFORMULER AILLEURS
FIN DOCUMENT
```

- **Plan d'action** :
  1. Lire `docs/adr/0000-template.md` et relever ses sections obligatoires.
  2. Vérifier que le numéro 0019 est libre (`git ls-files`).
  3. Rédiger l'ADR selon le gabarit, avec marquage épistémique `[O]/[I]/[H]/[D]` par phrase.
  4. Vérifier que chaque affirmation factuelle cite un fichier et un numéro de ligne du diagnostic.
  5. Ajouter la ligne ADR-0019 au registre `.claude/GOVERNANCE.md §3`, sans toucher au reste.
  6. Contrôler le diff (aucun fichier non `.md`, volume ≤ 220 lignes).
  7. Commiter en un seul commit `docs(adr): ADR-0019 exposition d'affichage vs exposition-gate [GOV-001]`.
- **Ordre exact** :
  1. `git status --short` ⇒ vide ; noter `<base> = git rev-parse HEAD`.
  2. `git ls-files "docs/adr/0019*" "docs/ADR-0019*"` ⇒ vide.
  3. Lire `docs/adr/0000-template.md`.
  4. Écrire `docs/adr/0019-exposition-affichage-vs-exposition-gate.md`.
  5. Éditer `.claude/GOVERNANCE.md` §3 (ajout d'une ligne).
  6. `git diff --name-only` ⇒ exactement les 2 fichiers attendus.
  7. `git diff --stat` ⇒ total ≤ 220 lignes.
  8. `git add` des 2 fichiers, puis commit.
  9. `git diff --name-only HEAD~1..HEAD -- ":!*.md"` ⇒ vide.
- **Tests** : aucun test unitaire n'est créé ni exécuté (aucun code produit). Les contrôles sont les
  commandes `git` ci-dessus. La suite de tests existante doit rester bit-à-bit identique — vérifié par
  `git diff --name-only HEAD~1..HEAD -- "tests/**"` ⇒ vide.
- **Validation** :
  - `git ls-files "docs/adr/0019*"` renvoie exactement 1 fichier.
  - `git grep -c "advisor_loop.py:6785" -- docs/adr/0019-*.md` ≥ 1.
  - `git grep -c "exposition-gate" -- docs/adr/0019-*.md` ≥ 3.
  - `git grep -n "Statut" -- docs/adr/0019-*.md` mentionne `Proposé` et jamais `Accepté`.
  - `git grep -n "0019" -- .claude/GOVERNANCE.md` ≥ 1.
- **Rollback** : `git revert --no-edit <sha>`. Aucun effet runtime, aucun redémarrage, aucun déploiement.
- **Risques** : R2 (collision de numéro — mitigé par l'étape 2) ; R3 (ADR rédigé comme prescription —
  mitigé par la structure « Décision / Conséquences » sans plan de patch) ; R6 (ADR pris pour une
  acceptation — mitigé par le statut `Proposé` et la validation qui l'exige).
- **Temps estimé** : 2 h 00.
- **Dépendances** : aucune. C'est la racine de la phase et du chantier.
- **Critères Done** (binaires) :
  - [ ] `git ls-files "docs/adr/0019*"` ⇒ 1 ligne.
  - [ ] `git diff --name-only HEAD~1..HEAD` ⇒ exactement 2 lignes, toutes deux en `.md`.
  - [ ] `git diff --name-only HEAD~1..HEAD -- ":!*.md"` ⇒ vide.
  - [ ] `git diff --stat HEAD~1..HEAD` ⇒ ≤ 220 lignes modifiées au total.
  - [ ] L'ADR contient les sections Contexte / Décision / Conséquences / Falsificateurs / Dette épistémique.
  - [ ] L'ADR contient au moins 2 falsificateurs explicitement libellés.
  - [ ] Statut de l'ADR = `Proposé`.
- **Critères Refus** (l'un suffit) :
  - `git diff --name-only HEAD~1..HEAD -- ":!*.md"` non vide ⇒ **REFUS immédiat + revert**.
  - L'ADR conclut « Accepté » sans entrée signée dans `.claude/DECISION_JOURNAL.md` ⇒ REFUS.
  - L'ADR prescrit un correctif de code ou un diff sur `core/advisor_loop.py` ⇒ REFUS.
  - Une affirmation factuelle sans fichier ni numéro de ligne ⇒ REFUS.
  - Plus de 2 fichiers dans le diff ⇒ REFUS (atomicité).

---

### GOV-002 — Registre des invariants INV-1 → INV-4 rendu opposable

- **ID** : `GOV-002`
- **Titre** : Établir la matrice de vérification des invariants du chantier (INV-1 à INV-4)
- **Objectif** : transformer quatre énoncés en quatre tests. Pour chaque invariant : symbole concret
  du code, fichier et ligne, commande de contrôle, sortie attendue, falsificateur.
- **Pourquoi** : **[O]** `.claude/GOVERNANCE.md §2` énonce déjà INV-1 → INV-4 avec un falsificateur
  chacun, mais sans commande de contrôle exécutable ; **[I]** un invariant sans procédure de
  vérification n'est pas opposable : il ne permet ni d'accepter ni de refuser un ticket ;
  **[I]** les phases 01 → 04 doivent pouvoir prouver leur conformité, pas la déclarer.
- **Diagnostic résumé** :
  1. **[O]** L'entrée de décision incriminée est `pos_manager.get_open()` passé à `portfolio_health()`
     en `core/advisor_loop.py:6785-6787` — c'est le symbole que INV-1 et INV-2 protègent.
  2. **[O]** Le store d'affichage est `_virtual_portfolio` lu en `core/advisor_loop.py:450-453` — c'est
     le seul store qu'un ticket NON GATED a le droit de lire pour l'affichage.
  3. **[O]** `portfolio_brain.py:88` fixe `MAX_TOTAL_EXPOSURE_PCT = 0.40` : constante de décision,
     donc intouchable (INV-4 par extension du gel des seuils).
  4. **[O]** Les écrivains de `paper_trades.jsonl` sont `paper_trading/mexc_simulator.py` et
     `paper_trading/recorder.py` — périmètre exact protégé par INV-3.
  5. **[O]** `_register_position_from_execution` (`core/advisor_loop.py:3859-3883`) appelle
     `pos_manager.add_position` (`:3883`) et écrit `databases/positions_snapshot.json` (`:3888+`) :
     second point d'entrée de décision à lister.
  6. **[I]** Sans cette liste nominative, un ticket futur peut violer INV-1 en croyant faire de
     l'observabilité.
- **Contexte** : la section `## 2. Les 4 invariants du chantier` existe déjà (`.claude/GOVERNANCE.md`,
  lignes 82 à 126 au 2026-07-25 **[O]**). Le ticket **n'y touche pas** : il **ajoute** une sous-section
  de matrice juste après, pour préserver la revertabilité et éviter toute réécriture d'un texte
  normatif déjà accepté. **A CONFIRMER AU DEMARRAGE DU TICKET** : état exact et numérotation des
  sections de `.claude/GOVERNANCE.md` au moment de l'exécution (fichier susceptible d'avoir bougé).
  Si `§2` est absent, le ticket rédige INV-1 → INV-4 intégralement en reprenant les énoncés de `CLAUDE.md`.
- **Hypothèses** :
  - **[H1]** Les énoncés INV-1 → INV-4 en place sont ceux du chantier (passivité, reset de N,
    `paper_trades.jsonl`, sizing). Vérifiable par lecture directe avant édition.
  - **[H2]** Aucune commande de contrôle proposée n'exécute le moteur ; toutes sont des commandes `git`
    ou de lecture. Vérifiable par relecture de la matrice.
- **Invariants** : INV-PH00 (documentation seule) ; le ticket documente INV-1 → INV-4 sans les modifier.
  **Démonstration de non-atteinte à l'entrée de décision** : un seul fichier `.md` édité, ajout en fin
  de section, aucun symbole Python touché ; contrôle `git diff --name-only HEAD~1..HEAD -- ":!*.md"` vide.
- **Fichiers** (1) : `.claude/GOVERNANCE.md` — **modifié** (ajout d'une sous-section).
- **Pseudo-code** (description non exécutable) :

```
DANS .claude/GOVERNANCE.md
  APRES la section "2. Les 4 invariants du chantier"
  AJOUTER sous-section "2.5 Matrice de vérification des invariants"

  TABLE colonnes = [ invariant, symbole protégé, fichier:ligne, commande de contrôle,
                     sortie attendue, falsificateur ]

  LIGNE INV-1
     symbole  -> "pos_manager.get_open() passé à portfolio_health"
     ancrage  -> advisor_loop.py:6785-6787 ; portfolio_brain.py:645-664, :668-687
     contrôle -> "diff du ticket ne contient aucun .py"
     attendu  -> "sortie vide"
     falsif.  -> "un symbole modifié est lu par le pipeline de décision"

  LIGNE INV-2
     symbole  -> "toute entrée de décision : pos_manager.add_position (advisor_loop.py:3883),
                  seuils de gate, sizing, univers tradé"
     contrôle -> "relevé de N avant/après via la source canonique"
     attendu  -> "N inchangé hors trades naturels"
     falsif.  -> "N repart à zéro sans ADR d'époque signé"

  LIGNE INV-3
     symbole  -> "paper_trades.jsonl et ses deux écrivains :
                  paper_trading/mexc_simulator.py, paper_trading/recorder.py"
     contrôle -> "diff du ticket ne contient aucun fichier de paper_trading/ ni databases/"
     attendu  -> "sortie vide"
     falsif.  -> "un nouveau chemin d'écriture, même en append, même en test"

  LIGNE INV-4
     symbole  -> "WALLET_PAPER_CAPITAL comme base de sizing ;
                  MAX_TOTAL_EXPOSURE_PCT = 0.40 (portfolio_brain.py:88)"
     contrôle -> "aucun .py, .env, .json modifié"
     attendu  -> "sortie vide"
     falsif.  -> "la taille d'un ordre change après le patch"

  AJOUTER note : "cette matrice ne crée aucun invariant ;
                  elle rend vérifiables ceux de la section 2"
  AJOUTER renvoi vers ADR-0019
FIN
```

- **Plan d'action** :
  1. Lire `.claude/GOVERNANCE.md` §2 et §3 dans leur état courant ; relever la numérotation réelle.
  2. Vérifier que ADR-0019 existe (dépendance GOV-001) et relever son chemin exact.
  3. Rédiger la sous-section « Matrice de vérification des invariants » (4 lignes de table + note).
  4. Vérifier qu'aucune commande de la matrice n'exécute le moteur ni n'écrit de fichier.
  5. Contrôler le diff (1 fichier, ≤ 90 lignes).
  6. Commiter : `docs(gov): matrice de vérification INV-1..INV-4 [GOV-002]`.
- **Ordre exact** :
  1. `git status --short` ⇒ vide.
  2. Lire `.claude/GOVERNANCE.md` (sections 2 et 3).
  3. `git ls-files "docs/adr/0019*"` ⇒ 1 fichier (sinon **STOP**, GOV-001 non fait).
  4. Éditer `.claude/GOVERNANCE.md` : insertion de la sous-section après §2.
  5. `git diff --name-only` ⇒ `.claude/GOVERNANCE.md` uniquement.
  6. `git diff --stat` ⇒ ≤ 90 lignes.
  7. Commit.
  8. `git diff --name-only HEAD~1..HEAD -- ":!*.md"` ⇒ vide.
- **Tests** : aucun test créé ni exécuté. Contrôles = commandes `git` et `git grep` ci-dessous.
- **Validation** :
  - `git grep -c "INV-1" -- .claude/GOVERNANCE.md` ≥ 2 (énoncé + matrice).
  - `git grep -n "portfolio_brain.py:88" -- .claude/GOVERNANCE.md` ≥ 1.
  - `git grep -n "mexc_simulator.py" -- .claude/GOVERNANCE.md` ≥ 1.
  - `git grep -n "ADR-0019" -- .claude/GOVERNANCE.md` ≥ 1.
  - La matrice contient 4 lignes, une par invariant, chacune avec une commande et une sortie attendue.
- **Rollback** : `git revert --no-edit <sha>`. La section §2 d'origine n'ayant pas été touchée, le
  revert ne peut pas détruire l'énoncé des invariants.
- **Risques** : R5 (édition concurrente de `GOVERNANCE.md` — mitigé par l'ordre strict et l'insertion
  en fin de section) ; risque de réécriture involontaire de §2 — mitigé par le critère de refus dédié.
- **Temps estimé** : 1 h 00.
- **Dépendances** : `GOV-001` (la matrice renvoie à ADR-0019).
- **Critères Done** :
  - [ ] `git diff --name-only HEAD~1..HEAD` ⇒ exactement `.claude/GOVERNANCE.md`.
  - [ ] `git diff --stat HEAD~1..HEAD` ⇒ ≤ 90 lignes.
  - [ ] `git diff HEAD~1..HEAD -- .claude/GOVERNANCE.md` ne contient **aucune ligne supprimée** (`-`)
        dans la plage de la section 2 d'origine.
  - [ ] Les 4 invariants ont chacun : symbole, `fichier:ligne`, commande, sortie attendue, falsificateur.
  - [ ] Aucune commande de la matrice ne lance le moteur ni n'écrit un fichier.
- **Critères Refus** :
  - Diff contenant un fichier non `.md` ⇒ REFUS + revert.
  - Modification ou reformulation de l'énoncé d'un invariant existant ⇒ REFUS (hors périmètre :
    changer un invariant exige un ADR, pas un ticket de documentation).
  - Une commande de contrôle qui exécute `advisor_loop.py` ou écrit dans `databases/` ⇒ REFUS.
  - Matrice incomplète (moins de 4 lignes, ou une colonne vide) ⇒ REFUS.

---

### GOV-003 — Journal des décisions du chantier

- **ID** : `GOV-003`
- **Titre** : Ouvrir le journal des décisions du chantier (qui décide quoi, quand, sur quelle preuve)
- **Objectif** : créer un fichier append-only qui trace chaque décision du chantier avec cinq champs
  obligatoires : date, décideur, décision, preuve invoquée, conséquence sur N / époque. Première entrée :
  la soumission d'ADR-0019 à l'opérateur.
- **Pourquoi** : **[O]** `CLAUDE.md` réserve à l'opérateur les décisions de calibration, d'époque et de
  déploiement ; **[O]** `.claude/GOVERNANCE.md §8` distingue déjà les décisions opérateur des actions
  agent ; **[I]** sans journal, la frontière « proposé par l'agent » / « accepté par l'opérateur »
  n'est pas reconstituable a posteriori, et un ADR en statut `Proposé` peut être lu plus tard comme accepté ;
  **[I]** c'est la contrepartie procédurale du statut `Proposé` imposé par GOV-001.
- **Diagnostic résumé** :
  1. **[O]** Le bug d'affichage est gelé volontairement : docstring `core/advisor_loop.py:437-448`.
     C'est une **décision**, prise à une date, par quelqu'un, sur une preuve — aujourd'hui tracée
     uniquement dans un commentaire de code.
  2. **[O]** Une régression du même sujet est datée dans le code (`core/advisor_loop.py:462-471`,
     2026-07-12 21:00 UTC) : le projet a déjà eu besoin de mémoire décisionnelle.
  3. **[O]** L'arbitrage des architectures A / B / C conditionne des resets d'époque (N → 0) :
     décision opérateur exclusive.
  4. **[I]** Un journal séparé du code survit aux refactorisations, contrairement à une docstring.
  5. **[O]** ADR-0019 naît en statut `Proposé` (GOV-001) : son passage à `Accepté` doit être daté
     et attribué, sinon le statut n'a pas de valeur probante.
- **Contexte** : le fichier est créé à `.claude/DECISION_JOURNAL.md`. **[D]** Ce chemin ne figure pas
  dans la liste de structure imposée du chantier : il est ajouté parce qu'un journal append-only ne doit
  pas grossir un document normatif. **Repli explicite si l'opérateur refuse un chemin hors liste** :
  déplacer le contenu en section finale de `.claude/GOVERNANCE.md`, sans changer le format des entrées.
  **A CONFIRMER AU DEMARRAGE DU TICKET** : préférence de l'opérateur entre fichier dédié et section.
- **Hypothèses** :
  - **[H1]** Le journal n'est lu par aucun script. Vérifiable :
    `git grep -n "DECISION_JOURNAL" -- "*.py"` ⇒ vide.
  - **[H2]** Une entrée par décision suffit ; l'historique antérieur au chantier n'est pas reconstitué
    (le journal démarre à sa date de création et le déclare explicitement).
- **Invariants** : INV-PH00 (documentation seule) ; INV-1 (le journal est passif : aucun composant ne
  le lit) ; INV-2 (aucune entrée de décision touchée).
  **Démonstration de non-atteinte à l'entrée de décision** : création d'un `.md` + un renvoi d'une ligne
  dans `.claude/GOVERNANCE.md` ; aucun import Python ne pointe vers ces chemins ; contrôle
  `git diff --name-only HEAD~1..HEAD -- ":!*.md"` vide.
- **Fichiers** (2) :
  - `.claude/DECISION_JOURNAL.md` — **créé**
  - `.claude/GOVERNANCE.md` — **modifié**, renvoi d'une ou deux lignes vers le journal
- **Pseudo-code** (description non exécutable) :

```
DOCUMENT .claude/DECISION_JOURNAL.md
  EN-TETE
     DECLARER "journal append-only : on ajoute, on ne réécrit jamais une entrée passée"
     DECLARER "une entrée annulée est marquée ANNULÉE, jamais supprimée"
     DECLARER "date de départ = date de création ; aucune décision antérieure n'est reconstituée"
     DECLARER "l'agent peut PROPOSER ; seul l'opérateur peut ACCEPTER"

  FORMAT D'ENTREE (obligatoire, 7 champs)
     ID           -> "DEC-nnn", incrémental, jamais réutilisé
     DATE         -> horodatage UTC
     DECIDEUR     -> "Opérateur" | "Agent (proposition)"
     DECISION     -> une phrase, une seule, à l'indicatif
     PREUVE       -> fichier:ligne, commande + sortie, ou ADR référencé
     CONSEQUENCE  -> "aucune sur N" | "reset d'époque, N -> 0" | "gating d'un ticket"
     STATUT       -> "Proposé" | "Accepté" | "Refusé" | "Annulée"

  ENTREE DEC-001
     DATE        -> date d'exécution du ticket
     DECIDEUR    -> "Agent (proposition)"
     DECISION    -> "soumettre ADR-0019 (séparation exposition d'affichage / exposition-gate)
                     à l'acceptation de l'opérateur"
     PREUVE      -> docs/adr/0019-… ; advisor_loop.py:6785-6787 ; portfolio_brain.py:668-687
     CONSEQUENCE -> "aucune sur N : document seul"
     STATUT      -> "Proposé"

  ENTREE DEC-002   # gabarit vide, à remplir par l'opérateur, non pré-rempli par l'agent
     DECIDEUR    -> "Opérateur"
     DECISION    -> "<acceptation ou refus d'ADR-0019>"
     STATUT      -> "<à remplir>"
FIN DOCUMENT

DANS .claude/GOVERNANCE.md
   AJOUTER dans la section d'autorité de décision un renvoi :
       "toute décision de ce chantier est consignée dans .claude/DECISION_JOURNAL.md"
   NE RIEN SUPPRIMER
FIN
```

- **Plan d'action** :
  1. Vérifier que ADR-0019 existe et relever son chemin et son statut.
  2. Créer `.claude/DECISION_JOURNAL.md` : en-tête, format d'entrée à 7 champs, `DEC-001`, gabarit `DEC-002`.
  3. Ne pas pré-remplir la décision de l'opérateur (`DEC-002` reste à trous).
  4. Ajouter le renvoi dans `.claude/GOVERNANCE.md` (section d'autorité de décision).
  5. Contrôler le diff (2 fichiers, ≤ 120 lignes).
  6. Commiter : `docs(gov): journal des décisions du chantier [GOV-003]`.
- **Ordre exact** :
  1. `git status --short` ⇒ vide.
  2. `git ls-files "docs/adr/0019*"` ⇒ 1 fichier (sinon **STOP**).
  3. Écrire `.claude/DECISION_JOURNAL.md`.
  4. Éditer `.claude/GOVERNANCE.md` (renvoi).
  5. `git grep -n "DECISION_JOURNAL" -- "*.py"` ⇒ vide (confirme la passivité, INV-1).
  6. `git diff --name-only` ⇒ 2 fichiers `.md`.
  7. `git diff --stat` ⇒ ≤ 120 lignes.
  8. Commit, puis `git diff --name-only HEAD~1..HEAD -- ":!*.md"` ⇒ vide.
- **Tests** : aucun test créé ni exécuté.
- **Validation** :
  - `git ls-files .claude/DECISION_JOURNAL.md` ⇒ 1 ligne.
  - `git grep -c "DEC-001" -- .claude/DECISION_JOURNAL.md` ≥ 1.
  - `git grep -n "Opérateur" -- .claude/DECISION_JOURNAL.md` ≥ 1.
  - `git grep -n "DECISION_JOURNAL" -- .claude/GOVERNANCE.md` ≥ 1.
  - `git grep -n "DECISION_JOURNAL" -- "*.py"` ⇒ **vide**.
  - `DEC-001` porte les 7 champs ; `STATUT = Proposé`.
- **Rollback** : `git revert --no-edit <sha>`. Le journal étant append-only et non lu par le runtime,
  son retrait n'a aucun effet système.
- **Risques** : R5 (édition concurrente de `GOVERNANCE.md`) ; risque que l'agent pré-remplisse une
  décision opérateur — mitigé par le critère de refus dédié ; risque de chemin hors structure imposée —
  mitigé par le repli documenté.
- **Temps estimé** : 1 h 00.
- **Dépendances** : `GOV-001` (DEC-001 référence ADR-0019). Indépendant de `GOV-002`.
- **Critères Done** :
  - [ ] `git diff --name-only HEAD~1..HEAD` ⇒ exactement 2 fichiers, tous deux `.md`.
  - [ ] `git diff --stat HEAD~1..HEAD` ⇒ ≤ 120 lignes.
  - [ ] `.claude/DECISION_JOURNAL.md` contient l'en-tête append-only + le format à 7 champs + `DEC-001`.
  - [ ] `DEC-002` existe et reste non rempli (mention explicite « à remplir par l'opérateur »).
  - [ ] `git grep -n "DECISION_JOURNAL" -- "*.py"` ⇒ vide.
- **Critères Refus** :
  - Diff contenant un fichier non `.md` ⇒ REFUS + revert.
  - Une entrée attribuée à l'opérateur sans qu'il l'ait écrite ⇒ REFUS (usurpation d'autorité de décision).
  - Une entrée du journal marquée `Accepté` par l'agent ⇒ REFUS.
  - Suppression ou réécriture d'une entrée existante ⇒ REFUS (viole la nature append-only).

---

### GOV-004 — Gabarit de rapport de fin de ticket (protocole épistémique v3)

- **ID** : `GOV-004`
- **Titre** : Figer le gabarit de rapport de fin de ticket, aligné sur le protocole d'audit épistémique v3
- **Objectif** : produire un gabarit unique, obligatoire pour tout ticket des phases 01 → 04, qui impose :
  une phrase = une catégorie (`[O]/[I]/[H]/[D]`), l'identification du maillon faible, la portée explicite,
  deux falsificateurs, la dette épistémique relative à la décision prise, et la preuve de non-atteinte à
  l'entrée de décision.
- **Pourquoi** : **[O]** le protocole v3 (`docs/protocole_audit_epistemique.md`) est fusionné dans `main`
  et impose ces éléments ; **[I]** un protocole sans gabarit d'application produit des rapports
  hétérogènes, donc non comparables entre tickets ; **[I]** la preuve « ce ticket n'a pas déclenché de
  reset d'époque » doit être un champ obligatoire du rapport, sinon elle sera omise sous pression.
- **Diagnostic résumé** :
  1. **[O]** L'audit SSoT du chantier conclut 0 PASS / 1 WARNING / 8 FAIL : les rapports futurs devront
     distinguer un FAIL corrigé d'un FAIL déplacé.
  2. **[O]** Le WARNING porte sur `free_cash` : producteur unique (`portfolio_health`,
     `portfolio_brain.py:645-664`) mais co-affiché avec `paper_cash` contradictoire — cas typique où un
     rapport doit distinguer « source unique » de « affichage cohérent ».
  3. **[O]** La confusion racine est un mélange de sources dans un même panneau
     (`core/advisor_loop.py:6786` pour l'exposition, `:450-453` pour le comptage) : tout rapport de
     ticket d'affichage doit donc nommer la source de chaque chiffre touché.
  4. **[O]** Le bug est gelé par décision documentée (`core/advisor_loop.py:437-448`) : un rapport doit
     pouvoir conclure « non corrigé volontairement » sans que ce soit lu comme un échec.
  5. **[I]** Le champ « dette épistémique » sert exactement à cela : dire ce que le ticket **ne prouve pas**.
- **Contexte** : cible `.claude/PROMPT_GUIDE.md`. **A CONFIRMER AU DEMARRAGE DU TICKET** : ce fichier
  existe-t-il déjà et contient-il déjà des gabarits ? (absent au 2026-07-25 **[O]**). S'il existe, le
  ticket **ajoute** une section et ne réécrit rien.
- **Hypothèses** :
  - **[H1]** Le protocole v3 impose bien : catégorisation par phrase, maillon faible, composition DAG,
    portée, double falsificateur, filtre des mots forts. **A vérifier par lecture de
    `docs/protocole_audit_epistemique.md` au démarrage** ; en cas d'écart, c'est le protocole qui fait foi
    et le gabarit qui s'aligne.
  - **[H2]** Un gabarit unique couvre les tickets documentaires (GOV-xxx) et les tickets de code
    (OBS-xxx, REST-xxx) : les champs non pertinents sont remplis « Sans objet », jamais supprimés.
- **Invariants** : INV-PH00 ; INV-1 (le gabarit est un document, aucun composant ne le lit).
  **Démonstration de non-atteinte à l'entrée de décision** : un seul fichier `.md` créé ou étendu dans
  `.claude/` ; aucun symbole de décision cité en écriture ; contrôle
  `git diff --name-only HEAD~1..HEAD -- ":!*.md"` vide.
- **Fichiers** (1) : `.claude/PROMPT_GUIDE.md` — **créé si absent, sinon modifié** (section ajoutée).
- **Pseudo-code** (description non exécutable) :

```
DANS .claude/PROMPT_GUIDE.md
  AJOUTER section "Gabarit de rapport de fin de ticket (obligatoire)"

  CHAMPS DU RAPPORT, dans cet ordre, aucun champ facultatif :
     1  IDENTITE          -> ID du ticket, phase, SHA du commit, date UTC
     2  PORTEE            -> ce que le ticket couvre ET ce qu'il ne couvre pas, en deux listes
     3  CE QUI A CHANGE   -> liste fichier par fichier, avec nombre de lignes
     4  OBSERVATIONS [O]  -> une phrase = un fait, chacune avec fichier:ligne ou commande + sortie
     5  INFERENCES [I]    -> une phrase = une déduction, chacune pointant ses observations sources
     6  HYPOTHESES [H]    -> une phrase = une conjecture non vérifiée, avec son test de vérification
     7  DECISIONS [D]     -> une phrase = une décision, avec son décideur
     8  MAILLON FAIBLE    -> l'étape la moins solide de la chaîne, nommée ; la conclusion
                             ne peut pas être plus forte que ce maillon (chaîne conjonctive)
     9  FALSIFICATEURS    -> exactement 2, formulés comme observations qui invalideraient le ticket
    10  DETTE EPISTEMIQUE -> ce que le ticket NE prouve pas, relatif à la décision prise
    11  PREUVE DE NON-RESET -> commande exécutée + sortie, démontrant qu'aucune entrée de
                             décision n'a été touchée (donc aucun reset d'époque, N conservé)
    12  INVARIANTS        -> INV-1..INV-4 : conforme / non conforme, avec la commande de contrôle
    13  RESTE A FAIRE     -> liste, ou "aucun"

  REGLES DE REDACTION IMPOSEES
     INTERDIRE  une phrase qui mélange deux catégories
     INTERDIRE  les mots forts non quantifiés : "toujours", "jamais", "prouve", "garantit",
                "complètement", sauf s'ils sont accompagnés de la mesure qui les soutient
     IMPOSER    "A CONFIRMER" pour toute information manquante ; l'invention est un motif de refus
     IMPOSER    pour toute conclusion issue de plusieurs preuves : dire si la composition est
                conjonctive (force = minimum des maillons) ou disjonctive (force peut monter
                SEULEMENT si les preuves sont indépendantes)

  AJOUTER un exemple rempli, court, sur un cas fictif documentaire
  AJOUTER la règle : "un ticket sans rapport conforme n'est pas Done"
FIN
```

- **Plan d'action** :
  1. Lire `docs/protocole_audit_epistemique.md` et relever les exigences v3 réellement écrites.
  2. Créer ou étendre `.claude/PROMPT_GUIDE.md` avec la section « Gabarit de rapport de fin de ticket ».
  3. Écrire les 13 champs dans l'ordre, avec pour chacun une définition en une ligne.
  4. Ajouter les règles de rédaction (catégories, mots forts, `A CONFIRMER`, composition conjonctive/disjonctive).
  5. Ajouter un exemple rempli court, explicitement fictif.
  6. Ajouter la règle de blocage : rapport non conforme ⇒ ticket non Done.
  7. Contrôler le diff (1 fichier, ≤ 200 lignes) et commiter :
     `docs(gov): gabarit de rapport de fin de ticket [GOV-004]`.
- **Ordre exact** :
  1. `git status --short` ⇒ vide.
  2. Lire `docs/protocole_audit_epistemique.md`.
  3. `git ls-files .claude/PROMPT_GUIDE.md` ⇒ noter présence ou absence.
  4. Écrire la section.
  5. `git diff --name-only` (ou `git status --short` si création) ⇒ `.claude/PROMPT_GUIDE.md` uniquement.
  6. `git diff --stat` / `wc -l` ⇒ ≤ 200 lignes.
  7. Commit, puis `git diff --name-only HEAD~1..HEAD -- ":!*.md"` ⇒ vide.
- **Tests** : aucun test créé ni exécuté. Contrôle de complétude par `git grep` sur les 13 intitulés de champs.
- **Validation** :
  - `git ls-files .claude/PROMPT_GUIDE.md` ⇒ 1 ligne.
  - `git grep -c "MAILLON FAIBLE\|Maillon faible" -- .claude/PROMPT_GUIDE.md` ≥ 1.
  - `git grep -c "DETTE EPISTEMIQUE\|Dette épistémique" -- .claude/PROMPT_GUIDE.md` ≥ 1.
  - `git grep -c "PREUVE DE NON-RESET\|non-reset" -- .claude/PROMPT_GUIDE.md` ≥ 1.
  - `git grep -c "Falsificateur" -- .claude/PROMPT_GUIDE.md` ≥ 2.
  - Les 13 champs sont présents et numérotés dans l'ordre.
- **Rollback** : `git revert --no-edit <sha>` (ou suppression du fichier s'il a été créé par ce ticket).
  Aucun effet runtime.
- **Risques** : R7 (gabarit non utilisé — mitigé par la règle « rapport non conforme ⇒ ticket non Done »
  et par son rappel dans les critères Done des phases 01 → 04) ; risque de divergence avec le protocole v3
  — mitigé par l'étape 1 et par la règle « le protocole fait foi ».
- **Temps estimé** : 1 h 30.
- **Dépendances** : `GOV-002` (le champ 12 renvoie à la matrice des invariants). Indépendant de `GOV-003`.
- **Critères Done** :
  - [ ] `git diff --name-only HEAD~1..HEAD` ⇒ exactement `.claude/PROMPT_GUIDE.md`.
  - [ ] Fichier ≤ 200 lignes ajoutées.
  - [ ] Les 13 champs sont présents, dans l'ordre, chacun défini en une ligne au moins.
  - [ ] Le champ « preuve de non-reset » cite une commande concrète et sa sortie attendue.
  - [ ] Le gabarit impose exactement 2 falsificateurs.
  - [ ] Un exemple rempli, marqué fictif, est présent.
- **Critères Refus** :
  - Diff contenant un fichier non `.md` ⇒ REFUS + revert.
  - Moins de 13 champs, ou champs déclarés facultatifs ⇒ REFUS.
  - Gabarit sans champ « preuve de non-reset » ⇒ REFUS (c'est la raison d'être du gabarit sous le gel).
  - Exemple rempli utilisant des données réelles non vérifiées ⇒ REFUS (l'exemple doit être marqué fictif).
  - Réécriture d'une section préexistante de `.claude/PROMPT_GUIDE.md` ⇒ REFUS.

---

### GOV-005 — Checklist de déploiement VPS et de vérification post-déploiement

- **ID** : `GOV-005`
- **Titre** : Figer la procédure de déploiement VPS et la checklist de vérification post-déploiement
- **Objectif** : documenter, en une procédure numérotée et vérifiable, ce qui doit être fait avant,
  pendant et après un déploiement du chantier — y compris le cas « ce ticket ne se déploie pas ».
- **Pourquoi** : **[O]** `CLAUDE.md` impose que le déploiement soit un geste délibéré
  (`bash scripts/deploy_vps.sh --confirm [--yes] [--dry-run] [--restart]`), le hook `post-commit` ayant
  été aboli ; **[O]** un incident documenté (2026-07-09) a produit trois tags de déploiement mensongers
  parce que `ssh` était appelé sans `-n` : des fichiers n'ont jamais atteint le VPS alors que le tag
  d'audit affirmait le contraire ; **[I]** un déploiement non vérifié produit une croyance fausse sur
  l'état du système, ce qui contamine ensuite toute analyse scientifique ; **[I]** les phases 01 et 03
  déploieront du code d'affichage : la procédure doit exister avant elles.
- **Diagnostic résumé** :
  1. **[O]** Le chantier corrigera de l'affichage (architecture A, phase 01) : les fichiers concernés
     seront `core/advisor_loop.py` autour de `:434-459`, `:6788-6906`, `:7444-7482` — c'est-à-dire du
     code chargé par le service en production.
  2. **[O]** Le premier point d'incohérence est `core/advisor_loop.py:6786` : une vérification
     post-déploiement doit donc porter sur le **panneau rendu**, pas seulement sur la présence du fichier.
  3. **[O]** Preuve numérique disponible pour vérifier : `free_cash = capital × 0.40 − exposition`
     (`portfolio_brain.py:645-664`, `:88`) — si l'affichage reste `269.79` avec 3 positions ouvertes,
     le déploiement n'a rien changé.
  4. **[O]** Preuve 2 disponible : présence ou absence du bloc `POSITIONS:`
     (`core/advisor_loop.py:6971`, condition `open_count > 0`).
  5. **[O]** `scripts/deploy_vps.sh` conserve un filtre d'exclusion (`databases/|cache/|logs/|tests/|docs/`)
     qui protège l'état runtime du VPS.
  6. **[O]** Le redémarrage du service est un double opt-in : `VPS_RESTART_CMD` dans `.env` **et**
     `--restart` explicite.
  7. **[O]** VPS courant : `35.240.166.72` ; l'ancienne IP `34.171.188.99` est morte et ne doit jamais
     être réutilisée.
- **Contexte** : PHASE_00 ne déploie rien — ses livrables sont des `.md`. La checklist est écrite
  **pour les phases suivantes**. Point ouvert :
  **A CONFIRMER AU DEMARRAGE DU TICKET** — le répertoire `.claude/` fait-il partie des fichiers
  transférés par `scripts/deploy_vps.sh` ? Le filtre d'exclusion connu (`databases/|cache/|logs/|tests/|docs/`)
  ne le mentionne pas ; la réponse doit être établie par lecture du script, pas supposée.
- **Hypothèses** :
  - **[H1]** `scripts/deploy_vps.sh` crée toujours un tag annoté `deploy-YYYYMMDD-HHMM` après succès et
    jamais en `--dry-run`. **A CONFIRMER par lecture du script au démarrage du ticket.**
  - **[H2]** Un tag de déploiement n'est pas une preuve de déploiement (précédent du 2026-07-09).
    La checklist doit donc exiger une vérification **côté VPS**, indépendante du tag.
  - **[H3]** Les vérifications post-déploiement peuvent être faites en lecture seule (comparaison de SHA,
    lecture d'un panneau, lecture de log) sans écrire sur le VPS.
- **Invariants** : INV-PH00 (documentation seule) ; INV-1 (la checklist décrit, n'exécute pas) ;
  INV-3 (la checklist interdit explicitement de déployer quoi que ce soit vers `databases/`).
  **Démonstration de non-atteinte à l'entrée de décision** : un seul fichier `.md` modifié ;
  `scripts/deploy_vps.sh` est **lu, jamais modifié** ; contrôle
  `git diff --name-only HEAD~1..HEAD -- ":!*.md"` vide.
- **Fichiers** (1) : `.claude/GOVERNANCE.md` — **modifié** (nouvelle section en fin de fichier).
- **Pseudo-code** (description non exécutable) :

```
DANS .claude/GOVERNANCE.md
  AJOUTER section "Déploiement VPS et vérification post-déploiement"

  ETAPE 0  DECIDER SI ON DEPLOIE
     SI le ticket ne modifie que des .md ALORS
         CONCLURE "aucun déploiement" et ARRETER la procédure ici
     FIN SI

  ETAPE 1  AVANT
     VERIFIER  arbre de travail propre
     VERIFIER  commit poussé sur main
     RELEVER   le SHA local à déployer
     RELEVER   N (époque courante) et l'horodater  # comparaison après restart
     SIMULER   déploiement en --dry-run et LIRE la liste des fichiers annoncés
     VERIFIER  que cette liste ne contient ni databases/ ni cache/ ni logs/

  ETAPE 2  PENDANT
     EXECUTER  le déploiement avec confirmation explicite
     NE PAS    passer --restart sauf si le fichier déployé est chargé au boot du service
     CAPTURER  la sortie complète, y compris les erreurs ssh

  ETAPE 3  APRES — VERIFICATION INDEPENDANTE DU TAG
     COMPARER  empreinte du fichier côté VPS et empreinte locale   # le tag ne prouve rien
     SI les empreintes diffèrent ALORS DECLARER "déploiement partiel" et ARRETER
     VERIFIER  que le service tourne et depuis quand
     LIRE      le premier panneau produit après déploiement
     VERIFIER  la cohérence attendue :
                  - le nombre de positions affiché et l'exposition affichée
                    proviennent du même store
                  - free_cash n'est plus égal à capital × 0.40 quand des positions sont ouvertes
                  - le bloc POSITIONS est présent quand open_count > 0
     RELEVER   N à nouveau et COMPARER au relevé de l'étape 1
     SI N a diminué ou est reparti à zéro ALORS
         DECLARER "reset d'époque non prévu" -> INCIDENT, arrêt, entrée au journal des décisions
     FIN SI

  ETAPE 4  TRACER
     ECRIRE une entrée dans .claude/DECISION_JOURNAL.md :
         date, SHA, fichiers, restart oui/non, résultat des vérifications, N avant / N après

  REGLE D'ARRET
     A la première anomalie : ARRETER, ne pas enchaîner, ne pas "réessayer pour voir"
FIN
```

- **Plan d'action** :
  1. Lire `scripts/deploy_vps.sh` : options réellement supportées, filtre d'exclusion, création de tag,
     conditions de `--restart`, et présence ou non de `.claude/` dans les fichiers transférés.
  2. Rédiger la section « Déploiement VPS et vérification post-déploiement » en 5 blocs
     (étape 0 à étape 4 + règle d'arrêt).
  3. Écrire les vérifications post-déploiement en s'appuyant sur les preuves observables du diagnostic
     (`free_cash = capital × 0.40 − exposition`, présence du bloc `POSITIONS:`).
  4. Marquer explicitement toute information non confirmée par lecture du script comme
     **A CONFIRMER AU DEMARRAGE DU TICKET**.
  5. Rappeler l'IP VPS courante et l'interdiction d'utiliser l'ancienne.
  6. Contrôler le diff (1 fichier, ≤ 160 lignes) et commiter :
     `docs(gov): procédure de déploiement VPS et vérification [GOV-005]`.
- **Ordre exact** :
  1. `git status --short` ⇒ vide.
  2. Lire `scripts/deploy_vps.sh` (lecture seule).
  3. Éditer `.claude/GOVERNANCE.md` : nouvelle section en fin de fichier.
  4. `git diff --name-only` ⇒ `.claude/GOVERNANCE.md` uniquement.
  5. `git diff --stat` ⇒ ≤ 160 lignes.
  6. Commit.
  7. `git diff --name-only HEAD~1..HEAD -- ":!*.md"` ⇒ vide (prouve que `deploy_vps.sh` n'a pas été touché).
- **Tests** : aucun test créé ni exécuté. **Aucun déploiement, même en `--dry-run`, n'est réalisé par ce
  ticket** : il écrit la procédure, il ne l'exécute pas.
- **Validation** :
  - `git grep -n "dry-run" -- .claude/GOVERNANCE.md` ≥ 1.
  - `git grep -n "35.240.166.72" -- .claude/GOVERNANCE.md` ≥ 1 et
    `git grep -n "34.171.188.99" -- .claude/GOVERNANCE.md` n'apparaît que comme IP morte à ne pas utiliser.
  - `git grep -n "tag" -- .claude/GOVERNANCE.md` inclut la mention « un tag ne prouve pas un déploiement ».
  - La section contient les étapes 0 à 4 et la règle d'arrêt.
  - La section contient au moins une vérification post-déploiement chiffrée
    (`free_cash` vs `capital × 0.40`).
- **Rollback** : `git revert --no-edit <sha>`. Aucun effet système : la procédure n'a jamais été exécutée
  par ce ticket.
- **Risques** : risque d'écrire une procédure fausse à partir d'une supposition sur `deploy_vps.sh` —
  mitigé par l'étape 1 (lecture obligatoire) et par le marquage `A CONFIRMER` ; risque qu'un lecteur
  exécute la procédure pendant PHASE_00 — mitigé par l'étape 0 (« si le ticket ne modifie que des `.md`,
  aucun déploiement ») ; R5 (édition concurrente de `GOVERNANCE.md`).
- **Temps estimé** : 1 h 30.
- **Dépendances** : `GOV-003` (l'étape 4 écrit dans `.claude/DECISION_JOURNAL.md`) ;
  `GOV-004` recommandé (le compte rendu de déploiement réutilise le gabarit de rapport).
- **Critères Done** :
  - [ ] `git diff --name-only HEAD~1..HEAD` ⇒ exactement `.claude/GOVERNANCE.md`.
  - [ ] `git diff --stat HEAD~1..HEAD` ⇒ ≤ 160 lignes.
  - [ ] Les étapes 0 → 4 et la règle d'arrêt sont présentes et numérotées.
  - [ ] La procédure exige une vérification côté VPS **indépendante du tag** de déploiement.
  - [ ] La procédure exige un relevé de N avant et après tout redémarrage.
  - [ ] Toute affirmation sur `scripts/deploy_vps.sh` est soit tirée de sa lecture, soit marquée
        `A CONFIRMER AU DEMARRAGE DU TICKET`.
- **Critères Refus** :
  - Diff contenant un fichier non `.md` ⇒ REFUS + revert.
  - Modification de `scripts/deploy_vps.sh` ⇒ REFUS immédiat (hors périmètre, et fichier d'exploitation).
  - Exécution réelle d'un déploiement pendant ce ticket ⇒ REFUS.
  - Procédure qui traite le tag `deploy-*` comme preuve suffisante ⇒ REFUS (précédent du 2026-07-09).
  - Mention de l'ancienne IP `34.171.188.99` comme cible active ⇒ REFUS.

---

## Ordre

Ordre d'exécution imposé (un ticket = un commit, dans cet ordre) :

```
GOV-001  ──►  GOV-002  ──►  GOV-004
   │                            ▲
   └────────►  GOV-003  ────────┘
                  │
                  └──►  GOV-005
```

| Rang | Ticket | Pourquoi ce rang |
|---|---|---|
| 1 | `GOV-001` | Racine : tous les autres tickets citent ADR-0019 |
| 2 | `GOV-002` | La matrice d'invariants référence ADR-0019 |
| 3 | `GOV-003` | Le journal ouvre avec la soumission d'ADR-0019 (DEC-001) |
| 4 | `GOV-004` | Le gabarit de rapport renvoie à la matrice d'invariants (GOV-002) |
| 5 | `GOV-005` | L'étape 4 de la procédure écrit dans le journal (GOV-003) et réutilise le gabarit (GOV-004) |

Parallélisation possible : `GOV-002` et `GOV-003` sont mutuellement indépendants, mais tous deux
éditent `.claude/GOVERNANCE.md` (R5) — **exécution séquentielle recommandée** pour garder des commits
revertables séparément sans conflit.

**Point d'arrêt opérateur** : après `GOV-003`, ADR-0019 est en statut `Proposé` et `DEC-002` attend la
décision de l'opérateur. `GOV-004` et `GOV-005` peuvent être exécutés sans cette décision (ils ne
supposent pas l'acceptation), mais **aucune phase 01 → 04 ne démarre avant** que `DEC-002` soit
renseignée par l'opérateur.

---

## Priorité

| Ticket | Priorité | Justification |
|---|---|---|
| `GOV-001` | **P0 — bloquante** | Sans ADR, aucun ticket de phase 01 ne peut prouver son caractère NON GATED |
| `GOV-002` | **P0 — bloquante** | Sans matrice, les critères Done des phases suivantes ne sont pas vérifiables |
| `GOV-003` | **P1 — haute** | Sans journal, le statut `Proposé`/`Accepté` d'ADR-0019 n'a pas de valeur probante |
| `GOV-004` | **P1 — haute** | Sans gabarit, les rapports de phase 01 → 04 sont hétérogènes et non comparables |
| `GOV-005` | **P2 — normale** | Nécessaire seulement avant le premier déploiement, c'est-à-dire avant la fin de la phase 01 |

Priorité de la phase entière : **P0**. PHASE_00 bloque PHASE_01, PHASE_02_GATED, PHASE_03 et PHASE_04_GATED.

**Coût du non-fait** : **[I]** exécuter la phase 01 sans PHASE_00 revient à modifier l'affichage sans
trace opposable de la frontière affichage/décision, donc sans moyen de démontrer plus tard que
l'époque V4 n'a pas été rompue — ce qui, en pratique, revient à devoir invalider le burn-in par précaution.

---

## Statut

**Statut initial : PRÊT.**

Justification, point par point :

| Condition de démarrage | État | Preuve |
|---|---|---|
| Diagnostic disponible et validé | Satisfait | Cause racine, fichiers et lignes fournis, non re-enquêtés |
| Gating de la phase | NON GATED | Aucun livrable n'est un `.py` ; aucun symbole de décision touché |
| Compatibilité avec le gel scientifique | Satisfait | Scientific Debt Rule autorise explicitement les outils de mesure, d'audit et la documentation |
| Compatibilité ADR-0007 | Satisfait | Livrables strictement passifs, non lus par le moteur |
| Risque de reset d'époque (N → 0) | Nul | Contrôle V1 : `git diff --name-only <base>..HEAD -- ":!*.md"` doit être vide |
| Dépendances externes | Aucune | PHASE_00 est la racine du graphe de phases |
| Décision opérateur requise pour démarrer | Non | Requise seulement pour **accepter** ADR-0019 (`DEC-002`), pas pour le rédiger |

**Points ouverts n'empêchant pas le démarrage** (à traiter dans le ticket concerné) :

1. Sections exactes de `docs/adr/0000-template.md` — **A CONFIRMER AU DEMARRAGE DU TICKET** (GOV-001).
2. État et numérotation courants de `.claude/GOVERNANCE.md` — **A CONFIRMER AU DEMARRAGE DU TICKET** (GOV-002).
3. Chemin retenu pour le journal (fichier dédié vs section) — **A CONFIRMER AU DEMARRAGE DU TICKET** (GOV-003).
4. Existence de `.claude/PROMPT_GUIDE.md` et exigences littérales du protocole v3 —
   **A CONFIRMER AU DEMARRAGE DU TICKET** (GOV-004).
5. Comportement réel de `scripts/deploy_vps.sh`, notamment le transfert éventuel de `.claude/` —
   **A CONFIRMER AU DEMARRAGE DU TICKET** (GOV-005).

**Condition de clôture de la phase** : les 8 contrôles V1 → V8 de la section « Validation » passent,
et `DEC-001` figure au journal. La clôture de PHASE_00 **n'implique pas** l'acceptation d'ADR-0019 :
c'est une décision opérateur distincte, tracée en `DEC-002`.
