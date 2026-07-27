<!-- GENERATED — ne pas editer a la main. Source : .claude/manifest.yaml -->

# INDEX — Tous les tickets du chantier

> Genere le 2026-07-27 02:17 UTC depuis `.claude/manifest.yaml`.
> Pour modifier un statut : editer le manifeste, puis relancer
> `python .claude/tools/render_docs.py`.

**34 tickets** · PRET **6** · BLOQUE **26** · EN COURS **0** · TERMINE **2**

> **Deux comptages distincts, a ne pas confondre :**
> **6 tickets PRET** = demarrables *maintenant*
> (dependances satisfaites).
> **15 tickets NON GATED** = executables sous le gel *a terme* ;
> certains attendent
> encore une dependance. Un ticket non gated dont une dependance
> n'est pas TERMINE
> est **BLOQUE**, pas PRET.

## PHASE_00 — Gouvernance

| ID | Titre | Prio | Statut | Bloque par | Prompt | Est. | Risque |
|---|---|---|---|---|---|---|---|
| `GOV-001` | ADR-0019 : exposition d'affichage vs exposition-gate | P1 | **PRET** | — | `PROMPT_GOV_001.md` | 3-5 h | Faible |
| `GOV-002` | Registre des invariants INV-1 -> INV-4 opposable | P0 | **TERMINE** | — | `PROMPT_GOV_002.md` | 2-4 h | Faible |
| `GOV-003` | Journal des decisions du chantier (DEC-xxx) | P1 | **PRET** | — | `PROMPT_GOV_003.md` | 2 h | Faible |
| `GOV-004` | Gabarit de rapport de fin de ticket | P0 | **TERMINE** | — | `PROMPT_GOV_004.md` | 2 h | Faible |
| `GOV-005` | Checklist de deploiement VPS et verification | P1 | **PRET** | — | `PROMPT_GOV_005.md` | 2-3 h | Faible |

## PHASE_01 — Observabilite (architecture A)

| ID | Titre | Prio | Statut | Bloque par | Prompt | Est. | Risque |
|---|---|---|---|---|---|---|---|
| `OBS-001` | Tests rouges + garde verte INV-2 | P0 | **PRET** | — | `PROMPT_OBS_001.md` | 3-5 h | Faible |
| `OBS-002` | Builder CYCLE : exposition/paper_cash/free_cash depuis _virtual_portfolio | P0 | **BLOQUE** | OBS-001 | `PROMPT_OBS_002.md` | 4-8 h | Eleve |
| `OBS-003` | Builder HEARTBEAT : parite stricte avec OBS-002 | P1 | **BLOQUE** | OBS-002 | `PROMPT_OBS_003.md` | 2-3 h | Moyen |
| `OBS-004` | Documenter affichage != gate (risque R1) | P1 | **BLOQUE** | OBS-002 | `PROMPT_OBS_004.md` | 1-2 h | Faible |
| `OBS-005` | Coherence d'affichage integrity_snapshot.py (OPTIONNEL) | P3 | **BLOQUE** | OBS-002 | `PROMPT_OBS_005.md` | 2-4 h | Moyen |

## PHASE_02_GATED — SSoT : store canonique et unification · **GATED**

| ID | Titre | Prio | Statut | Bloque par | Prompt | Est. | Risque |
|---|---|---|---|---|---|---|---|
| `SSOT-001` | Contrat du store de positions canonique (sans cablage) | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-002` | Adaptateur de lecture MexcSimulator -> store canonique | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-003` | Adaptateurs PositionManager et PaperLedger -> store canonique | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-004` | Resolveur de store + feature-flag (defaut false, non cable) | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-005` | Harnais de comparaison passif (dry-run, mesure d'ecart) | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-006` | Cablage AFFICHAGE sur le store canonique + activation du dry-run | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-007` | Cablage DECISION : portfolio_health lit le store resolu | P1 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-008` | PortfolioSnapshot canonique unique + alias de compatibilite | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-009` | Migration du consommateur REST vers le PortfolioSnapshot canonique | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-010` | Arbitrage des deux PortfolioBrain | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-011` | Unification des deux SystemSnapshot | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-012` | Couche de metriques canonique : capital, equity, cash | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-013` | Couche de metriques canonique : PnL ouvert et PnL ferme | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |
| `SSOT-014` | Couche de metriques canonique : win_rate et drawdown | P2 | **BLOQUE** | PORTE D'EPOQUE | — | A CONFIRMER | CRITIQUE |

## PHASE_03 — REST / Dashboard

| ID | Titre | Prio | Statut | Bloque par | Prompt | Est. | Risque |
|---|---|---|---|---|---|---|---|
| `REST-001` | ADR de source unique pour les metriques API | P1 | **BLOQUE** | GOV-001 | `PROMPT_REST_001.md` | 2-4 h | Faible |
| `REST-002` | Supprimer la recopie total_pnl_usd = open_pnl_usd | P1 | **PRET** | — | `PROMPT_REST_002.md` | 1-2 h | Moyen |
| `REST-003` | Remplacer les 8 litteraux figes de portfolio_api.py:22-29 | P2 | **BLOQUE** | REST-001 | `PROMPT_REST_003.md` | 3-5 h | Moyen |
| `REST-004` | Tests de garde REST | P2 | **BLOQUE** | REST-002, REST-003 | `PROMPT_REST_004.md` | 2-3 h | Faible |

## PHASE_04_GATED — Portefeuille / Risque · **GATED**

| ID | Titre | Prio | Statut | Bloque par | Prompt | Est. | Risque |
|---|---|---|---|---|---|---|---|
| `PORT-001` | Mesure d'impact hors ligne du gate aveugle (PASSIF) | P0 | **PRET** | — | `PROMPT_PORT_001.md` | 1-2 j | Faible |
| `PORT-002` | Brancher portfolio_health sur le store canonique | P1 | **BLOQUE** | PORTE D'EPOQUE | — | 1-2 j | CRITIQUE |
| `PORT-003` | Correlation et levier sur positions reelles | P2 | **BLOQUE** | PORTE D'EPOQUE | — | 1 j | CRITIQUE |
| `PORT-004` | Arbitrage des deux PortfolioBrain | P2 | **BLOQUE** | PORTE D'EPOQUE | — | 1-2 j | CRITIQUE |
| `PORT-005` | PaperTrade -> TradeOpened / TradeClosed | P3 | **BLOQUE** | PORTE D'EPOQUE | — | 2-3 j | CRITIQUE |
| `PORT-006` | Borne d'epoque V5 + deploiement + verification | P1 | **BLOQUE** | PORTE D'EPOQUE | — | 0.5 j | CRITIQUE |

## Notes

- `OBS-001` — PREMIER TICKET TOUCHANT DU CODE
- `OBS-005` — Retenu ou ecarte par la decision D-4
- `PORT-001` — EXCEPTION DOCUMENTEE : passif, dans une phase gated. Ne reset pas N.
- `PORT-002` — POINT DE NON-RETOUR SCIENTIFIQUE
- `PORT-004` — CHEVAUCHEMENT avec SSOT-010 — decision D-2 requise, n'en garder qu'un
- `PORT-006` — EXECUTE EFFECTIVEMENT LE RESET D'EPOQUE
- `SSOT-010` — CHEVAUCHEMENT avec PORT-004 — decision D-2 requise

