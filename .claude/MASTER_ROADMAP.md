# MASTER_ROADMAP — Chantier de remédiation SSoT

> Document de pilotage. À lire **après** `GOVERNANCE.md` et **avant** `IMPLEMENTATION_QUEUE.md`.
> Version 1.0 — 2026-07-24.

---

## Vue globale

### Le problème en cinq lignes

1. Le panneau Telegram affiche simultanément **« Positions: 3 »** et **« Portfolio Exposure: 0.0% »**.
2. Cause racine : `core/advisor_loop.py:6786` passe `pos_manager.get_open()` à `portfolio_health()`,
   or `pos_manager` est **vide en mode paper** — les positions vivent dans `_virtual_portfolio` (MexcSimulator).
3. Preuve numérique : `free_cash = 674.47 × 0.40 − 0 = 269.79 $`, exactement la valeur affichée
   ⇒ confirme `total_exposure_usd = 0`.
4. Conséquence non visible : les **cinq contrôles de risque** de `check_new_trade` s'exécutent sur un
   portefeuille perçu comme vide. Le gate est **trop permissif** depuis le début de l'époque V4.
5. Audit SSoT : **0 PASS / 1 WARNING / 8 FAIL** sur capital, equity, cash, free_cash, positions,
   exposure, PnL, win_rate, drawdown.

### Le principe directeur du chantier

> **Corriger ce que le système MONTRE ne coûte rien. Corriger ce que le système REGARDE coûte une époque.**

Toute la roadmap découle de cette asymétrie. Les phases qui touchent l'affichage sont exécutables
immédiatement. Celles qui touchent l'entrée de décision détruisent le burn-in (N → 0) et sont **gated**.

---

## Phases

| Phase | Objet | Gating | Tickets | Estimation | Statut |
|---|---|---|---|---|---|
| **PHASE_00** | Gouvernance : ADR, invariants, journal, gabarits, checklist déploiement | **NON GATED** | 5 (`GOV-001→005`) | 2 – 4 j | **PRET** |
| **PHASE_01** | Observabilité — architecture A : panneau honnête, décision intacte | **NON GATED** | 5 (`OBS-001→005`) | 2 – 3 j | **PRET** |
| **PHASE_02_GATED** | SSoT : store canonique, unification des classes, couche de métriques | **GATED** | 14 (`SSOT-001→014`) | 2 – 3 sem | **BLOQUE** |
| **PHASE_03** | REST / dashboard : supprimer les littéraux figés et la recopie de PnL | **NON GATED** | 4 (`REST-001→004`) | 1 – 2 j | **PRET** |
| **PHASE_04_GATED** | Portefeuille / risque : brancher la décision sur le réel, borne V5 | **GATED** (sauf `PORT-001`) | 6 (`PORT-001→006`) | 7 – 11 j | **BLOQUE** |

**Total : 5 phases, 34 tickets.**
**15 tickets exécutables sous le gel** · **19 tickets bloqués derrière la porte d'époque.**

---

## Diagrammes

### Flux de la cause racine

```
                        ┌── _virtual_portfolio (MexcSimulator) ── 3 positions REELLES
                        │        │
  ouverture de position ┤        └──► _display_position_summary ──► "Positions: 3"   ✔ vrai
                        │
                        └── pos_manager (PositionManager) ── VIDE en paper
                                 │
                                 ├──► portfolio_health() ──► "Exposure: 0.0%"        ✘ faux
                                 │         └──► free_cash = capital x 0.40 - 0 = 269.79
                                 │
                                 └──► check_new_trade() ──► 5 controles sur un VIDE  ✘ aveugle
                                            ^
                                            └── advisor_loop.py:6786  = POINT DE DIVERGENCE
```

### Séquencement des phases et portes de décision

```
  PHASE_00 (gouvernance)          PHASE_03 (REST)
        │                              │
        ├──────────────┐               │  (independante)
        ▼              ▼               ▼
  PHASE_01 (affichage honnete)   [ executables SOUS LE GEL — aucun reset de N ]
        │
        │   PORT-001 (mesure d'impact passive) ── produit le chiffre de la decision
        │        │
        ▼        ▼
  ╔═══════════════════════════════════════════════════════════════════╗
  ║  PORTE D'EPOQUE                                                   ║
  ║   1. checkpoint L2 franchi                                        ║
  ║   2. N >= 100 atteint sur l'epoque V4                             ║
  ║   3. ADR d'epoque signe par l'operateur                           ║
  ║   4. rapport PORT-001 lu                                          ║
  ╚═══════════════════════════════════════════════════════════════════╝
        │
        ▼
  PHASE_02_GATED (store canonique)  ──►  PHASE_04_GATED (decision + borne V5)
        │                                        │
        └────────────────────────────────────────┴──► deploiement + verification
```

---

## Dépendances

### Entre phases

| Phase | Dépend de | Nature |
|---|---|---|
| PHASE_00 | — | Racine |
| PHASE_01 | PHASE_00 (gabarits, format d'ADR) | Recommandée |
| PHASE_03 | PHASE_00 (format d'ADR pour `REST-001`) | Recommandée |
| PHASE_02_GATED | PORTE D'EPOQUE + PHASE_00 | **Dure** |
| PHASE_04_GATED | PHASE_02_GATED + PORTE D'EPOQUE | **Dure** |

### Chaînes internes critiques

```
GOV-001 ──► (format ADR) ──► REST-001 ──► REST-003 ──► REST-004
                                  ▲
                            REST-002 (independant)

OBS-001 (tests rouges) ──► OBS-002 ──► OBS-003
                              └──────► OBS-004

SSOT-001 ──► SSOT-002/003 ──► SSOT-004 ──► SSOT-005 ──► SSOT-006 ──► SSOT-007
                                                                          │
PORT-001 (passif, hors chaine) ─────────────────────────────────────────┐ │
                                                                        ▼ ▼
                                                                    PORT-002
                                                          ┌─────────────┼─────────────┐
                                                          ▼             ▼             ▼
                                                      PORT-003      PORT-004      PORT-005
                                                          └─────────────┴─────────────┘
                                                                        ▼
                                                                    PORT-006 (borne V5)
```

### Chevauchement identifié — à arbitrer

> **SSOT-010** (« Arbitrage des deux `PortfolioBrain` ») et **PORT-004** (même intitulé) traitent le
> même objet. Ils ont été produits par deux documents de phase distincts.
> **Décision requise avant exécution** : conserver `SSOT-010` (phase SSoT, cohérent avec l'unification
> des classes) et **supprimer `PORT-004`**, ou l'inverse. Ne pas exécuter les deux.
> Tant que l'arbitrage n'est pas fait, les deux sont marqués **BLOQUE** dans la queue.

---

## Gating

### Test opérationnel — classer n'importe quel changement

> **« Ce changement modifie-t-il ce que le moteur de décision REGARDE, ou seulement ce qu'il MONTRE ? »**

| Réponse | Classement | Conséquence |
|---|---|---|
| Ce qu'il **montre** (panneau, REST, logs, documentation) | **NON GATED** | Exécutable sous le gel. N inchangé. |
| Ce qu'il **regarde** (`PositionManager`, `check_new_trade`, sizing, risk, `PortfolioBrain` en entrée) | **GATED** | Reset d'époque. ADR signé obligatoire. |

### Symboles sensibles — tout contact déclenche le gating

`PositionManager` · `check_new_trade` · sizing · risk · `PortfolioBrain` **en entrée de décision** ·
seuils par régime · `CLEAN_DATA_SINCE_*`

### Ce que coûte le franchissement de la porte

- **N → 0.** Le burn-in de l'époque V4 est clos. Les données restent archivées mais ne comptent plus
  pour les seuils de la règle du statisticien (500 trades / 150 W / 150 L / 100 MW / 100 GR / CRI ≥ 90).
- **Le rollback d'époque n'existe pas.** `git revert` restaure le code, jamais la mesure.
- C'est pourquoi la porte exige **quatre** préconditions cumulatives, et pourquoi `PORT-001`
  (mesure d'impact) doit être lu **avant** la décision.

---

## Calendrier

Le calendrier distingue le **temps de travail** (contrôlable) du **temps d'attente**
(accumulation de N — non contrôlable).

| Séquence | Nature | Durée |
|---|---|---|
| PHASE_00 + PHASE_01 + PHASE_03 | Travail | **5 – 9 jours** |
| `PORT-001` (mesure d'impact) | Travail, en parallèle | 1 – 2 jours |
| **Attente : N passe de ~32 à ≥ 100 sur V4** | **Attente** | **Non datable — dépend du débit de trades** |
| Décision opérateur (ADR d'époque) | Décision | Variable |
| PHASE_02_GATED | Travail | 2 – 3 semaines |
| PHASE_04_GATED | Travail | 7 – 11 jours |

> **Les phases gated dépendent d'un ÉVÉNEMENT (N ≥ 100 + checkpoint L2 + ADR signé), pas d'une DATE.**
> Toute planification calendaire des phases 02 et 04 serait une fiction : elle supposerait un débit
> de trades qui n'est pas maîtrisé.

Contrainte externe indépendante du chantier : l'infrastructure GCP (voir `GOVERNANCE.md`).

---

## Ordre optimal

### File exécutable immédiatement — 15 tickets, dans cet ordre

| # | Ticket | Phase | Justification de la position |
|---|---|---|---|
| 1 | `GOV-002` | 00 | Rend les invariants opposables : toute la suite s'y réfère. |
| 2 | `GOV-004` | 00 | Gabarit de rapport — nécessaire dès le premier ticket de code. |
| 3 | `GOV-003` | 00 | Journal des décisions — trace les arbitrages à venir. |
| 4 | `GOV-001` | 00 | ADR-0019 (séparation affichage / gate) — fonde PHASE_01. |
| 5 | `GOV-005` | 00 | Checklist de déploiement — requise avant tout déploiement. |
| 6 | **`OBS-001`** | 01 | **PREMIER TICKET DE CODE.** Tests rouges + garde INV-2. |
| 7 | `OBS-002` | 01 | Corrige le builder CYCLE — cœur de l'architecture A. |
| 8 | `OBS-003` | 01 | Parité HEARTBEAT. |
| 9 | `OBS-004` | 01 | Documente le risque R1 (panneau honnête ≠ gate corrigé). |
| 10 | `OBS-005` | 01 | Optionnel — cohérence `integrity_snapshot`. |
| 11 | `REST-002` | 03 | Seule valeur **activement fausse** publiée (PnL ouvert en total). |
| 12 | `REST-001` | 03 | ADR de choix de source — bloquant pour `REST-003`. |
| 13 | `REST-003` | 03 | Supprime les 8 littéraux figés. |
| 14 | `REST-004` | 03 | Tests de garde — ferme la boucle. |
| 15 | `PORT-001` | 04 | **Passif.** Produit le chiffre qui fondera la décision d'époque. |

> **Le premier ticket à exécuter est `GOV-002`** (documentaire).
> **Le premier ticket touchant du code est `OBS-001`.**

### File bloquée — 19 tickets

`SSOT-001` → `SSOT-014` (14) et `PORT-002` → `PORT-006` (5).
Déblocage : franchissement de la **PORTE D'EPOQUE** (4 préconditions cumulatives).

---

## Roadmap complète — tous les tickets

| ID | Titre | Phase | Gated | Dépendances | Statut |
|---|---|---|---|---|---|
| GOV-001 | ADR-0019 : séparation exposition d'affichage / exposition-gate | 00 | Non | — | PRET |
| GOV-002 | Registre des invariants INV-1 → INV-4 rendu opposable | 00 | Non | — | PRET |
| GOV-003 | Journal des décisions du chantier | 00 | Non | — | PRET |
| GOV-004 | Gabarit de rapport de fin de ticket (protocole épistémique v3) | 00 | Non | — | PRET |
| GOV-005 | Checklist de déploiement VPS et vérification post-déploiement | 00 | Non | — | PRET |
| OBS-001 | Tests de régression d'abord — rouge + garde verte INV-2 | 01 | Non | GOV-004 | PRET |
| OBS-002 | Builder CYCLE — exposition/`paper_cash`/`free_cash` depuis `_virtual_portfolio` | 01 | Non | OBS-001 | PRET |
| OBS-003 | Builder HEARTBEAT — parité stricte avec OBS-002 | 01 | Non | OBS-002 | PRET |
| OBS-004 | Documentation code — « exposition d'affichage » ≠ « exposition-gate » | 01 | Non | OBS-002 | PRET |
| OBS-005 | Cohérence d'affichage `integrity_snapshot.py` (optionnel) | 01 | Non | OBS-002 | PRET |
| REST-001 | ADR de choix de source unique pour les métriques REST | 03 | Non | GOV-001 | PRET |
| REST-002 | Supprimer la recopie `total_pnl_usd = open_pnl_usd` | 03 | Non | — | PRET |
| REST-003 | Remplacer les 8 littéraux figés de `portfolio_api.py:22-29` | 03 | Non | REST-001 | PRET |
| REST-004 | Adapter `test_snapshot_only_loaders.py` + tests de garde | 03 | Non | REST-002, REST-003 | PRET |
| PORT-001 | Mesure d'impact hors ligne (passif) | 04 | **Non** | — | PRET |
| SSOT-001 | Contrat du store de positions canonique | 02 | **Oui** | PORTE | BLOQUE |
| SSOT-002 | Adaptateur MexcSimulator → store canonique | 02 | **Oui** | SSOT-001 | BLOQUE |
| SSOT-003 | Adaptateurs PositionManager et PaperLedger → store canonique | 02 | **Oui** | SSOT-001 | BLOQUE |
| SSOT-004 | Résolveur de store + feature-flag (défaut false) | 02 | **Oui** | SSOT-002, SSOT-003 | BLOQUE |
| SSOT-005 | Harnais de comparaison passif (dry-run) | 02 | **Oui** | SSOT-004 | BLOQUE |
| SSOT-006 | Câblage AFFICHAGE + activation du dry-run | 02 | **Oui** | SSOT-005 | BLOQUE |
| SSOT-007 | Câblage DECISION : `portfolio_health` lit le store résolu | 02 | **Oui** | SSOT-006 | BLOQUE |
| SSOT-008 | `PortfolioSnapshot` canonique unique + alias | 02 | **Oui** | SSOT-007 | BLOQUE |
| SSOT-009 | Migration du consommateur REST vers le snapshot canonique | 02 | **Oui** | SSOT-008 | BLOQUE |
| SSOT-010 | Arbitrage des deux `PortfolioBrain` | 02 | **Oui** | SSOT-008 | BLOQUE ⚠ |
| SSOT-011 | Unification des deux `SystemSnapshot` | 02 | **Oui** | SSOT-008 | BLOQUE |
| SSOT-012 | Couche de métriques canonique : capital, equity, cash | 02 | **Oui** | SSOT-008 | BLOQUE |
| SSOT-013 | Couche de métriques canonique : PnL ouvert et fermé | 02 | **Oui** | SSOT-012 | BLOQUE |
| SSOT-014 | Couche de métriques canonique : win_rate et drawdown | 02 | **Oui** | SSOT-012 | BLOQUE |
| PORT-002 | Brancher `portfolio_health` sur le store canonique | 04 | **Oui** | SSOT-007, PORT-001 | BLOQUE |
| PORT-003 | Corrélation et levier sur positions réelles | 04 | **Oui** | PORT-002 | BLOQUE |
| PORT-004 | Arbitrage des deux `PortfolioBrain` | 04 | **Oui** | PORT-002 | BLOQUE ⚠ |
| PORT-005 | `PaperTrade` → `TradeOpened` / `TradeClosed` | 04 | **Oui** | PORT-002 | BLOQUE |
| PORT-006 | Borne d'époque V5 + déploiement + vérification | 04 | **Oui** | PORT-002 | BLOQUE |

⚠ = chevauchement `SSOT-010` / `PORT-004` à arbitrer (voir section Dépendances).

---

## Décisions en attente de l'opérateur

| # | Décision | Impact | Bloque |
|---|---|---|---|
| D-1 | **Autoriser ou non le reset d'époque V4 → V5** | N → 0, burn-in clos, irréversible | PHASE_02, PHASE_04 |
| D-2 | Arbitrer le chevauchement `SSOT-010` / `PORT-004` | Double exécution évitée | Ces 2 tickets |
| D-3 | Accepter ADR-0019 (`GOV-001`) | Fonde PHASE_01 | Rien (PHASE_01 exécutable sans) |
| D-4 | Retenir ou écarter `OBS-005` (optionnel) | Périmètre PHASE_01 | Rien |
| D-5 | Fenêtre d'arrêt du moteur pour `PORT-006` | Déploiement + redémarrage | PORT-006 |

> **D-1 ne doit pas être prise avant lecture du rapport `PORT-001`.** Décider d'un reset sans connaître
> son bénéfice chiffré serait une décision non informée sur une action irréversible.

---

## État d'avancement

> Bloc **généré** depuis `.claude/manifest.yaml`. Ne pas éditer à la main :
> modifier le manifeste puis lancer `python .claude/tools/render_docs.py`.

<!-- GENERATED:avancement -->
### PHASE_00 — Gouvernance
[ ] GOV-001 · [x] GOV-002 · [ ] GOV-003 · [x] GOV-004 · [ ] GOV-005

### PHASE_01 — Observabilite (architecture A)
[ ] OBS-001 · [ ] OBS-002 · [ ] OBS-003 · [ ] OBS-004 · [ ] OBS-005

### PHASE_02_GATED — SSoT : store canonique et unification
[ ] SSOT-001 · [ ] SSOT-002 · [ ] SSOT-003 · [ ] SSOT-004 · [ ] SSOT-005 · [ ] SSOT-006 · [ ] SSOT-007 · [ ] SSOT-008 · [ ] SSOT-009 · [ ] SSOT-010 · [ ] SSOT-011 · [ ] SSOT-012 · [ ] SSOT-013 · [ ] SSOT-014

### PHASE_03 — REST / Dashboard
[ ] REST-001 · [ ] REST-002 · [ ] REST-003 · [ ] REST-004

### PHASE_04_GATED — Portefeuille / Risque
[ ] PORT-001 · [ ] PORT-002 · [ ] PORT-003 · [ ] PORT-004 · [ ] PORT-005 · [ ] PORT-006
<!-- /GENERATED:avancement -->

### PORTE D'EPOQUE
- [ ] Checkpoint L2 franchi
- [ ] N ≥ 100 sur l'époque V4
- [ ] Rapport PORT-001 lu par l'opérateur
- [ ] ADR d'époque rédigé et signé

---

## Ce que ce chantier ne résout pas

Énoncé explicitement pour qu'aucune session future ne croie le problème clos :

- Les phases **00, 01, 03** corrigent **l'observabilité**. À leur terme, le panneau et le REST disent
  la vérité — **mais le gate de décision reste aveugle**. C'est le risque R1, documenté dans `OBS-004`.
- Les 8 **FAIL** de l'audit SSoT ne sont résolus qu'à l'issue de **PHASE_02_GATED** et **PHASE_04_GATED**.
- L'architecture C (event-sourcing complet, métriques comme projections) n'est **amorcée** que par
  `PORT-005`. Elle n'est pas couverte par cette roadmap.
- La question scientifique de fond — *l'edge existe-t-il ?* — est **hors périmètre**. Ce chantier
  répare l'instrument de mesure ; il ne mesure rien.
