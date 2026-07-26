# `.claude/` — Système de développement du projet

Ce dossier est le **système d'exploitation du chantier** de `crypto_ai_terminal`. Il contient les règles,
la roadmap, le backlog et les prompts d'exécution qui permettent à n'importe quelle session Claude
(ou à n'importe quel ingénieur) de reprendre le travail **sans contexte préalable**.

Il pilote un chantier précis : la **remédiation de la dette Single Source of Truth** révélée par l'audit
du 2026-07-24.

---

## Le problème, en cinq lignes

1. Le panneau Telegram affiche **« Positions: 3 »** et **« Portfolio Exposure: 0.0% »** dans le même message.
2. Cause racine : `core/advisor_loop.py:6786` passe `pos_manager.get_open()` à `portfolio_health()`,
   or `pos_manager` est **vide en mode paper** — les positions vivent dans `_virtual_portfolio` (MexcSimulator).
3. Preuve : `free_cash = 674.47 × 0.40 − 0 = 269.79 $`, exactement la valeur affichée.
4. Conséquence invisible : les **cinq contrôles de risque** de `check_new_trade` s'exécutent sur un
   portefeuille perçu comme vide — le gate est **trop permissif**.
5. Audit SSoT : **0 PASS / 1 WARNING / 8 FAIL**.

---

## Par où commencer

1. **Lire `GOVERNANCE.md`** — les règles qui ne se négocient pas (invariants, époques, checkpoints, interdictions).
2. **Lire `CLAUDE_IMPLEMENTATION.md`** — le protocole de travail (commits, tests, rollback, déploiement, arrêt).
3. **Ouvrir `IMPLEMENTATION_QUEUE.md`** — y prendre le **premier ticket de la file PRET**.
4. **Ouvrir son prompt** dans `prompts/PROMPT_<ID>.md` — il est auto-portant, il suffit à exécuter le ticket.
5. **Exécuter, tester, commiter, mettre à jour la queue, puis S'ARRÊTER.**

> Pour démarrer une session de travail, écrire exactement :
>
> ```
> Respecte .claude/CLAUDE_IMPLEMENTATION.md et exécute le ticket <ID>.
> ```

---

## Arborescence

| Fichier | Rôle | Quand le lire |
|---|---|---|
| `README.md` | Ce document. Porte d'entrée. | En premier, une fois. |
| `GOVERNANCE.md` | Règles du projet, ADR, resets d'époque, checkpoints, interdictions. | Avant toute décision. |
| `CLAUDE_IMPLEMENTATION.md` | Protocole d'implémentation : commits, tests, rollback, déploiement, arrêt. | Au début de **chaque** session. |
| `ARCHITECTURE.md` | Architecture réelle, cartographie des données, 4 stores, duplications. | Pour comprendre le système. |
| `MASTER_ROADMAP.md` | Vue globale, 5 phases, diagrammes, dépendances, gating, calendrier, ordre optimal. | Pour situer un ticket. |
| `IMPLEMENTATION_QUEUE.md` | Backlog priorisé et **état d'avancement**. Fichier vivant. | À **chaque** ticket, avant et après. |
| `PROMPT_GUIDE.md` | Comment utiliser les prompts d'exécution. | Une fois, puis en cas de doute. |
| `phases/` | Les 5 documents de phase, avec le détail complet des tickets. | Pour le détail d'un ticket. |
| `prompts/` | Un prompt d'exécution autonome par ticket. | Au moment d'exécuter. |

---

## État du chantier

**5 phases · 34 tickets · 15 exécutables · 19 bloqués.**

| Phase | Objet | Gating | Tickets | Statut |
|---|---|---|---|---|
| `phases/PHASE_00.md` | Gouvernance : ADR, invariants, journal, gabarits | Non | 5 (`GOV-001→005`) | **PRET** |
| `phases/PHASE_01.md` | Observabilité — panneau honnête, décision intacte | Non | 5 (`OBS-001→005`) | **PRET** |
| `phases/PHASE_02_GATED.md` | SSoT — store canonique, unification, métriques | **Oui** | 14 (`SSOT-001→014`) | **BLOQUE** |
| `phases/PHASE_03.md` | REST — littéraux figés, recopie de PnL | Non | 4 (`REST-001→004`) | **PRET** |
| `phases/PHASE_04_GATED.md` | Portefeuille — décision sur le réel, borne V5 | **Oui** (sauf `PORT-001`) | 6 (`PORT-001→006`) | **BLOQUE** |

- **Premier ticket à exécuter** : `GOV-002` (documentaire).
- **Premier ticket touchant du code** : `OBS-001` (tests rouges).

---

## LES RÈGLES QUI NE SE NÉGOCIENT PAS

> **INV-1** — Passivité absolue des observers (ADR-0007). Un composant d'observabilité ne peut jamais
> influencer une décision en temps réel.
>
> **INV-2** — Aucun reset de N sans ADR d'époque signé par l'opérateur. Le burn-in est un actif.
>
> **INV-3** — `paper_trades.jsonl` n'est écrit que par `mexc_simulator.py` et `recorder.py`.
> L'historique n'est jamais réécrit.
>
> **INV-4** — Aucun seuil n'est modifié avant N ≥ 500 et CRI ≥ 90 (règle du statisticien).
>
> **RÈGLE DE GATING** — *« Ce changement modifie-t-il ce que le moteur REGARDE, ou seulement ce qu'il
> MONTRE ? »* Ce qu'il **montre** → exécutable. Ce qu'il **regarde**
> (`PositionManager`, `check_new_trade`, sizing, risk, `PortfolioBrain` en entrée) → **GATED**,
> reset d'époque, ADR obligatoire.

---

## Ce que ce chantier ne résout pas

- Les phases 00, 01 et 03 corrigent **l'observabilité**. À leur terme le panneau dit la vérité,
  **mais le gate de décision reste aveugle** (risque R1, documenté par `OBS-004`).
- Les 8 FAIL de l'audit SSoT ne tombent qu'après `PHASE_02_GATED` et `PHASE_04_GATED`.
- La question scientifique de fond — *l'edge existe-t-il ?* — est **hors périmètre**.
  Ce chantier répare l'instrument de mesure ; il ne mesure rien.
