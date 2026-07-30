<!-- GENERATED — ne pas editer a la main. Source : .claude/manifest.yaml -->

# IMPLEMENTATION_QUEUE — Backlog priorise

> Genere le 2026-07-30 00:13 UTC depuis `.claude/manifest.yaml`.

## Regle d'execution

1. **Un seul ticket a la fois.** Jamais deux tickets dans un commit.
2. Prendre le premier de la file **PRET**.
3. Ouvrir `.claude/prompts/PROMPT_<ID>.md` et l'executer.
4. Tester, commiter, mettre a jour le **manifeste**, relancer le generateur.
5. **S'ARRETER.** Jamais d'enchainement automatique.

> **PROCHAIN TICKET : `OBS-001` — Tests rouges + garde verte INV-2**

## FILE : PRET — 6 tickets demarrables maintenant

*(Sur 15 tickets non gated : les autres attendent une dependance.)*

| # | ID | Titre | Phase | Prio | Est. | Prompt |
|---|---|---|---|---|---|---|
| 1 | `OBS-001` | Tests rouges + garde verte INV-2 | PHASE_01 | P0 | 3-5 h | `PROMPT_OBS_001.md` |
| 2 | `PORT-001` | Mesure d'impact hors ligne du gate aveugle (PASSIF) | PHASE_04_GATED | P0 | 1-2 j | `PROMPT_PORT_001.md` |
| 3 | `GOV-001` | ADR-0019 : exposition d'affichage vs exposition-gate | PHASE_00 | P1 | 3-5 h | `PROMPT_GOV_001.md` |
| 4 | `GOV-003` | Journal des decisions du chantier (DEC-xxx) | PHASE_00 | P1 | 2 h | `PROMPT_GOV_003.md` |
| 5 | `GOV-005` | Checklist de deploiement VPS et verification | PHASE_00 | P1 | 2-3 h | `PROMPT_GOV_005.md` |
| 6 | `REST-002` | Supprimer la recopie total_pnl_usd = open_pnl_usd | PHASE_03 | P1 | 1-2 h | `PROMPT_REST_002.md` |

## FILE : BLOQUE — 26 tickets

| ID | Titre | Bloque par | Risque |
|---|---|---|---|
| `OBS-002` | Builder CYCLE : exposition/paper_cash/free_cash depuis _virtual_portfolio | OBS-001 | Eleve |
| `OBS-003` | Builder HEARTBEAT : parite stricte avec OBS-002 | OBS-002 | Moyen |
| `OBS-004` | Documenter affichage != gate (risque R1) | OBS-002 | Faible |
| `OBS-005` | Coherence d'affichage integrity_snapshot.py (OPTIONNEL) | OBS-002 | Moyen |
| `REST-001` | ADR de source unique pour les metriques API | GOV-001 | Faible |
| `REST-003` | Remplacer les 8 litteraux figes de portfolio_api.py:22-29 | REST-001 | Moyen |
| `REST-004` | Tests de garde REST | REST-002, REST-003 | Faible |
| `PORT-002` | Brancher portfolio_health sur le store canonique | PORTE D'EPOQUE | CRITIQUE |
| `PORT-003` | Correlation et levier sur positions reelles | PORTE D'EPOQUE | CRITIQUE |
| `PORT-004` | Arbitrage des deux PortfolioBrain | PORTE D'EPOQUE | CRITIQUE |
| `PORT-005` | PaperTrade -> TradeOpened / TradeClosed | PORTE D'EPOQUE | CRITIQUE |
| `PORT-006` | Borne d'epoque V5 + deploiement + verification | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-001` | Contrat du store de positions canonique (sans cablage) | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-002` | Adaptateur de lecture MexcSimulator -> store canonique | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-003` | Adaptateurs PositionManager et PaperLedger -> store canonique | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-004` | Resolveur de store + feature-flag (defaut false, non cable) | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-005` | Harnais de comparaison passif (dry-run, mesure d'ecart) | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-006` | Cablage AFFICHAGE sur le store canonique + activation du dry-run | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-007` | Cablage DECISION : portfolio_health lit le store resolu | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-008` | PortfolioSnapshot canonique unique + alias de compatibilite | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-009` | Migration du consommateur REST vers le PortfolioSnapshot canonique | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-010` | Arbitrage des deux PortfolioBrain | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-011` | Unification des deux SystemSnapshot | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-012` | Couche de metriques canonique : capital, equity, cash | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-013` | Couche de metriques canonique : PnL ouvert et PnL ferme | PORTE D'EPOQUE | CRITIQUE |
| `SSOT-014` | Couche de metriques canonique : win_rate et drawdown | PORTE D'EPOQUE | CRITIQUE |

### Condition de deblocage — porte d'epoque

- [ ] **P1** — Checkpoint L2 du projet franchi
- [ ] **P2** — N >= 100 atteint sur l'epoque V4 (CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z)
- [ ] **P3** — Rapport PORT-001 produit et lu par l'operateur
- [ ] **P4** — ADR d'epoque redige et signe par l'operateur

## FILE : EN COURS — 0 tickets

*(vide)*

## FILE : TERMINE — 2 tickets

| ID | Titre | Commit |
|---|---|---|
| `GOV-002` | Registre des invariants INV-1 -> INV-4 opposable | `—` |
| `GOV-004` | Gabarit de rapport de fin de ticket | `—` |
