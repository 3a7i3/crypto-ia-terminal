# PHASE_02_GATED — Unification des sources de verite (architecture B, amorce de C)

> **GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
>
> Toute la phase est bloquee. Precondition de deblocage commune a tous les tickets :
> checkpoint L2 franchi **ET** N >= 100 sur l epoque courante (V4, borne
> `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`) **ET** ADR d epoque signe par l operateur.
> Aucun ticket SSOT-xxx ne peut etre presente comme executable immediatement.

Prefixe d identifiants de la phase : **SSOT-xxx**. Aucun autre prefixe n est valide ici.

---

## Objectif

Faire converger les sources de verite du portefeuille vers un store de positions canonique
et une couche de metriques canonique, de sorte que l affichage et les contraintes de decision
lisent le meme etat.

Cibles mesurables de fin de phase :

1. Un seul store de positions canonique en mode paper, avec adaptateurs de lecture pour
   les stores historiques (`_virtual_portfolio` de MexcSimulator, `PositionManager`,
   `PaperLedger._open`, `WalletSync` en lecture seule compte reel).
2. Une seule classe `PortfolioSnapshot` (aujourd hui 3 : `observability/system_snapshot.py:56`,
   `quant_hedge_ai/agents/risk/portfolio_brain.py:64`, `visualization/api/models.py:69`).
3. Une seule classe `SystemSnapshot` (aujourd hui 2 : `observability/system_snapshot.py:132`,
   `infra/monitoring/daily_analyzer.py:19`).
4. Un `PortfolioBrain` canonique designe (aujourd hui 2 :
   `quant_hedge_ai/agents/risk/portfolio_brain.py:75`, `quant_hedge_ai/agents/portfolio/__init__.py:71`).
5. Une couche de metriques canonique pour capital, equity, cash, PnL ouvert, PnL ferme,
   win_rate, drawdown, avec suppression des recalculs concurrents (audit SSoT : 8 FAIL / 1 WARNING).
6. Un protocole de bascule documente et execute : dry-run, comparaison des verdicts de decision
   avant/apres, mesure de l ecart, decision d epoque, activation.

Non-objectif : ameliorer la qualite des decisions. La phase ne change aucun seuil, aucune
regle, aucune personnalite. Elle change **d ou vient l etat lu**, ce qui suffit a constituer
une nouvelle epoque.

## Contexte

Diagnostic valide, non re-instruit dans cette phase :

- `core/advisor_loop.py:6785-6787` appelle `portfolio_brain.portfolio_health(pos_manager.get_open())`.
  En mode paper, `pos_manager` est vide : les positions sont ouvertes dans `_virtual_portfolio`
  (MexcSimulator) via `place_market_order` (`core/advisor_loop.py:2176`).
- `quant_hedge_ai/agents/risk/portfolio_brain.py:668-687` (`_snapshot`) somme `p.size_usd` et compte
  `n_positions` sur la liste recue ; liste vide => exposition 0.
- `quant_hedge_ai/agents/risk/portfolio_brain.py:645-664` (`portfolio_health`) renvoie
  `free_capital = max(0, capital * MAX_TOTAL_EXPOSURE_PCT - total_exposure_usd)` avec
  `MAX_TOTAL_EXPOSURE_PCT = 0.40` (`:88`).
- `core/advisor_loop.py:6788` appelle `_display_position_summary(_virtual_portfolio, pb_health)` :
  `n_open` vient de `_virtual_portfolio.get_open_positions_summary()`
  (`core/advisor_loop.py:450-453`), avec repli sur `pb_health` si `None` (`:456-459`).
- Consequence observee : dans le meme panneau Telegram, `Positions: 3` (source `_virtual_portfolio`)
  et `Portfolio Exposure: 0.0%` (source `pos_manager`, vide).
  Premier point d incoherence = `core/advisor_loop.py:6786`.
- Preuve numerique : `free_cash = 269.79 = 674.47 * 0.40 - 0`, donc `total_exposure_usd = 0`.
- Preuve secondaire : le bloc `POSITIONS:` est absent des rapports (condition
  `core/advisor_loop.py:6971`, `open_count > 0`), ce qui confirme `pos_manager` vide.
- Le bug est **documente et gele volontairement** : docstring `core/advisor_loop.py:437-448`
  (« pos_manager reste la source des contraintes de decision ... jamais modifie ici, corriger son
  entree changerait le comportement de decision en pleine validation scientifique. Ce bug est
  documente, gele, a corriger a la calibration »). Regression historique documentee
  `core/advisor_loop.py:462-471` (2026-07-12 21:00 UTC).

La PHASE_01 (prefixe OBS-xxx) traite l affichage sans toucher a la decision (architecture A).
La presente phase traite l unification reelle (architecture B) et amorce C. Elle est donc
incompatible avec le gel actuel tant que la precondition de deblocage n est pas remplie.

## Dependances

| Dependance | Nature | Etat |
|---|---|---|
| PHASE_00 (GOV-xxx) | Gouvernance, regles de gating, registre des ADR | Prealable obligatoire |
| PHASE_01 (OBS-xxx) | Affichage derive de `_virtual_portfolio`, sans toucher `pos_manager` | Prealable obligatoire : fournit la mesure de reference « affichage coherent » a comparer |
| Checkpoint L2 | Gate scientifique | Non franchi |
| N >= 100 sur epoque V4 | Volume de dataset | Non atteint (N de session ~ 32 trades fermes) |
| ADR d epoque (numero libre a partir de ADR-0019) | Decision operateur signee | Non redige |
| `scripts/data_quality.py` (`CLEAN_DATA_SINCE_ACTIVE`) | Borne d epoque, source unique | Existant, a faire evoluer en fin de phase seulement |
| `tools/cri_calculator.py::load_clean_trades` | Lecture dataset propre | Existant |

Dependance externe non technique : la phase consomme du temps de burn-in. Executer la phase
avant N >= 100 detruit le burn-in en cours (reset de N a zero).

## Prerequis

1. Checkpoint L2 franchi et trace dans le registre de gouvernance (PHASE_00).
2. N >= 100 trades fermes sur l epoque V4, mesure via `tools/cri_calculator.py::load_clean_trades`.
3. ADR d epoque redige, numerote a partir de ADR-0019, signe par l operateur, precisant :
   raison du changement d epoque, nouvelle borne `CLEAN_DATA_SINCE_V5`, sort du dataset V4
   (archive, comparable en interne), duree de burn-in attendue pour la nouvelle epoque.
4. Dossier Go/No-Go de l epoque V4 clos (verdicts H1-H6 figes avant le reset).
5. Sauvegarde des datasets V4 (`databases/paper_trades.jsonl`, artefacts regret v2) verifiee
   — chemin exact et procedure : A CONFIRMER AU DEMARRAGE DU TICKET.
6. Aucun deploiement VPS en cours ; dernier tag `deploy-*` connu et note.

## Risques

| # | Risque | Gravite | Mitigation |
|---|---|---|---|
| R1 | Le changement d entree de decision modifie les verdicts et invalide le burn-in | Critique | Reset d epoque assume, ADR signe, dataset V4 archive avant bascule |
| R2 | Bascule silencieuse du flag (defaut mal choisi, `.env` VPS divergent) | Critique | Defaut `false` code en dur ; SSOT-004 impose la lecture explicite ; verification post-deploiement obligatoire |
| R3 | Un observer devient actif (violation ADR-0007) : le harnais de comparaison influence une decision | Critique | SSOT-005 : lecture seule, aucun retour dans le flux de decision, teste par un test d isolement |
| R4 | Unification de `PortfolioSnapshot` cassant des consommateurs non identifies | Elevee | Alias de compatibilite conserve pendant toute la phase, retire seulement en fin de phase |
| R5 | Double comptage de positions (meme position vue via 2 adaptateurs) | Elevee | Cle d identite canonique definie en SSOT-001, test de deduplication |
| R6 | Divergence des metriques scientifiques (`analysis/base.py:88`, `:125`) et des metriques d exploitation | Elevee | SSOT-014 : `analysis/base.py` designe lignee canonique scientifique, les autres deviennent consommateurs |
| R7 | Regression de l affichage acquise en PHASE_01 | Moyenne | Tests de PHASE_01 conserves et executes a chaque ticket |
| R8 | Ecart local / VPS pendant la bascule | Moyenne | Bascule = un seul deploiement delibere avec `--restart`, verification live immediate |
| R9 | Ticket depassant l atomicite (300 lignes / 4 fichiers) | Faible | Decoupe imposee ; un ticket qui deborde est refuse et scinde |

## Architecture

Cible de la phase (architecture B, sous flag) :

```text
                 +-------------------------------+
                 |  Sources d etat (existantes)  |
                 |  - MexcSimulator._virtual_... |
                 |  - PaperLedger._open          |
                 |  - PositionManager            |
                 |  - WalletSync (reel, RO)      |
                 +---------------+---------------+
                                 |
                     adaptateurs de lecture seule
                                 |
                 +---------------v---------------+
                 |  CanonicalPositionStore       |   <- SSOT-001..003
                 |  (contrat unique, RO)         |
                 +---------------+---------------+
                                 |
              +------------------+------------------+
              |                                     |
   +----------v-----------+             +-----------v-----------+
   |  Couche metriques    |             |  Resolveur + flag     |  <- SSOT-004
   |  canonique           |  <- 012/014 |  FEATURE_CANONICAL_*  |
   +----------+-----------+             +-----------+-----------+
              |                                     |
      +-------v--------+                   +--------v---------+
      |  AFFICHAGE     |  <- SSOT-006      |  DECISION        |  <- SSOT-007
      |  snapshots,    |                   |  portfolio_health|
      |  panneaux      |                   |  contraintes     |
      +----------------+                   +------------------+
```

Amorce de l architecture C : la couche de metriques (SSOT-012 a SSOT-014) est ecrite comme
un ensemble de **projections pures** sur un flux d evenements. En phase 02 le flux d entree
reste l etat courant des stores ; en phase C il sera remplace par `paper_trades.jsonl` sans
changer la signature des projections.

Principes structurants :

- Le store canonique est **en lecture seule**. Aucun ticket de cette phase n ecrit dans un store.
- Le flag est **binaire et global** : soit tout l affichage et toute la decision lisent le
  canonique, soit rien. Interdiction d un etat mixte durable (source d incoherence nouvelle).
  L etat mixte n existe qu entre SSOT-006 et SSOT-007, et uniquement en dry-run.
- Aucun composant d observabilite n ecrit ni ne renvoie de valeur consommee par la decision
  (ADR-0007).

## Fichiers concernes

Lecture / modification prevue au cours de la phase :

- `core/advisor_loop.py` (7776 lignes) : `_display_position_summary:434-459`,
  `_positions_for_display:462+`, docstring gelee `437-448`, regression documentee `462-471`,
  appel fautif `6785-6787` (`6786` = premier point d incoherence), `6788`,
  builder snapshot CYCLE `6788-6906` (recalculs `_deployed_notional` / `_paper_equity` /
  `_paper_cash` `6791-6799`, construction `PortfolioSnapshot` `6888-6906`),
  bloc `POSITIONS:` `6971-6989` (condition `6971`), `SHADOW STATS 6992-6999`,
  builder snapshot HEARTBEAT `7444-7482`,
  `_register_position_from_execution:3859-3883` (`pos_manager.add_position:3883`,
  ecriture `databases/positions_snapshot.json` `3888+`).
- `quant_hedge_ai/agents/risk/portfolio_brain.py` : `PortfolioSnapshot:64`, `PortfolioBrain:75`,
  `MAX_TOTAL_EXPOSURE_PCT:88`, `portfolio_health:645-664`, `_snapshot:668-687`.
- `quant_hedge_ai/agents/portfolio/__init__.py` : `PortfolioBrain:71`.
- `observability/system_snapshot.py` : `PortfolioSnapshot:56`, `SystemSnapshot:132`, `to_dict:143`.
- `infra/monitoring/daily_analyzer.py` : `SystemSnapshot:19`.
- `visualization/api/models.py` : `PortfolioSnapshot:69`.
- `visualization/api/portfolio_api.py` : constantes figees `22-29`, `total_pnl_usd = open_pnl_usd` `30`,
  `capital_usd = portfolio.paper_equity` `33`, `trade_history = []` `34` (traite en PHASE_03, cite ici
  comme consommateur).
- `system/integrity_snapshot.py:100-135` : recalculs `pb_free` / `pb_exposure` / `pb_n` via `pos_manager`.
- `analysis/base.py` : `win_rate:88`, `max_drawdown:125`.
- `certification/operator_signoff.py:46` : `paper_max_dd`, `paper_win_rate`.
- `paper_trading/ledger.py` : `PaperLedger:121`, `summary():191`, `PaperTrade` (mutation en place
  a la cloture : `is_open` passe a `False`, champs `exit_*` remplis).
- `paper_trading/mexc_simulator.py` : `MexcSimulator:230`.
- `paper_trading/recorder.py` : second ecrivain de `paper_trades.jsonl`.
- Tests existants a adapter : `tests/test_system_snapshot.py:31-36`,
  `tests/test_state_integrity.py:51-56` et `277-285`,
  `tests/capital_deployment/test_capital_lines.py:22-48`,
  `tests/visualization/test_snapshot_only_loaders.py`.

Fichiers nouveaux prevus (chemins proposes, a valider au demarrage du ticket concerne) :
`core/state/position_store.py`, `core/state/adapters/`, `core/state/metrics/`,
`docs/adr/ADR-0019-*.md`, `docs/runbooks/bascule_ssot.md`.

## Invariants

Invariants de phase, verifiables, opposables a chaque ticket :

- **I-01** — Tant que le flag est `false`, le comportement observable du systeme est
  strictement identique a celui d avant la phase (bit a bit sur les verdicts de decision).
- **I-02** — Le store canonique n ecrit jamais. Aucune methode publique ne mute un etat.
- **I-03** — Aucun composant d observabilite ne renvoie une valeur consommee par la decision
  (ADR-0007).
- **I-04** — Une position est comptee une fois et une seule, quelle que soit le nombre
  d adaptateurs qui la voient (cle d identite canonique, SSOT-001).
- **I-05** — `n_positions`, `total_exposure_usd`, `free_capital` affiches et utilises par la
  decision proviennent du meme appel, dans le meme cycle.
- **I-06** — Aucun seuil, aucune constante de risque n est modifiee dans la phase
  (`MAX_TOTAL_EXPOSURE_PCT = 0.40` reste a 0.40).
- **I-07** — `FEATURE_AUTO_CALIBRATION` reste `false`. La base de sizing reste `WALLET_PAPER_CAPITAL`.
- **I-08** — Un ticket = un commit revertable seul. Aucun commit ne melange deux IDs SSOT.
- **I-09** — Atomicite : max 300 lignes modifiees OU max 4 fichiers par ticket, la contrainte
  la plus stricte s applique.
- **I-10** — La bascule du flag en production est un geste unique, delibere, trace par un tag
  `deploy-YYYYMMDD-HHMM` et par l ADR d epoque.

## Validation

Validation de phase (au-dela de la validation par ticket) :

1. `python -m pytest tests/ -q` : aucun echec nouveau par rapport a la baseline notee au
   demarrage de la phase.
2. Flag a `false` : rejeu de N cycles enregistres, comparaison des verdicts avant/apres.
   Sortie attendue : `0 divergence`.
3. Flag a `true` en dry-run : rapport d ecart produit par SSOT-005, contenant au minimum
   `n_positions`, `total_exposure_usd`, `free_capital`, verdict de decision, par cycle.
4. Recherche de duplications residuelles : la recherche des definitions de classes
   `PortfolioSnapshot`, `SystemSnapshot`, `PortfolioBrain` retourne respectivement
   1, 1 et 1 definition (hors alias de compatibilite explicitement marques).
5. Recherche des recalculs concurrents : aucune occurrence de calcul local de
   `win_rate`, `max_drawdown`, `equity`, `exposure` en dehors de la couche canonique
   (liste d exceptions autorisees tenue dans le ticket SSOT-015).
6. Coherence panneau : `Positions: k` et `Portfolio Exposure: x%` sont non contradictoires
   (`k > 0` implique `x > 0`), verifie sur 10 cycles consecutifs.

## Rollback

- Rollback par ticket : `git revert <sha>` du commit unique du ticket. Chaque ticket doit rester
  revertable sans toucher aux autres (I-08).
- Rollback de la bascule : remettre le flag a `false`, redeployer, redemarrer. Le code canonique
  reste en place mais inerte (I-01).
- Rollback d epoque : impossible. Une fois le flag active en production et des trades produits,
  les donnees posterieures appartiennent a la nouvelle epoque. Le retour au flag `false`
  cree encore une nouvelle rupture. C est la raison principale du gating.
- Rollback de la phase entiere : revert des commits dans l ordre inverse de la section « Ordre »,
  puis `python -m pytest tests/ -q` doit retrouver la baseline.

## Estimation

| Bloc | Tickets | Estimation |
|---|---|---|
| Contrat + adaptateurs | SSOT-001 a SSOT-003 | 2.5 j |
| Flag + harnais de comparaison | SSOT-004, SSOT-005 | 2 j |
| Cablage affichage puis decision | SSOT-006, SSOT-007 | 2 j |
| Unification des classes | SSOT-008 a SSOT-011 | 3 j |
| Couche de metriques canonique | SSOT-012 a SSOT-014 | 3 j |
| Retrait des recalculs concurrents | SSOT-015 | 1.5 j |
| Runbook de bascule + ADR d epoque | SSOT-016 | 1 j |
| **Total** | **16 tickets** | **~15 j homme, sur 1 a 2 semaines calendaires** |

Ces estimations excluent le temps d attente de la precondition (N >= 100), qui domine le
calendrier reel.

## Tickets

16 tickets : SSOT-001 a SSOT-016.

### SSOT-001 — Contrat du store de positions canonique (sans cablage)

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur. Ce ticket seul n a pas d effet sur la decision, mais il ouvert la chaine
qui la modifie : il n est pas detachable du gating.

- **ID** : SSOT-001
- **Titre** : Definir le contrat `CanonicalPositionStore` et le modele `PositionCanonique`.
- **Objectif** : produire une interface de lecture unique des positions ouvertes, avec une cle
  d identite, un jeu de champs minimal et des invariants explicites. Aucun appelant n est modifie.
- **Pourquoi** : aujourd hui 4 stores coexistent (`PaperLedger._open` `paper_trading/ledger.py:121`,
  `PositionManager`, `_virtual_portfolio` de `MexcSimulator` `paper_trading/mexc_simulator.py:230`,
  `WalletSync` en lecture seule). Sans contrat commun, toute unification se reduit a un choix
  arbitraire de store, non testable.
- **Diagnostic resume** :
  `core/advisor_loop.py:6785-6787` passe `pos_manager.get_open()` a `portfolio_health`, alors que
  les positions paper vivent dans `_virtual_portfolio` (ouverture via `place_market_order`,
  `core/advisor_loop.py:2176`). `quant_hedge_ai/agents/risk/portfolio_brain.py:668-687` somme
  `p.size_usd` sur la liste recue : liste vide => `total_exposure_usd = 0`, d ou
  `free_capital = 674.47 * 0.40 - 0 = 269.79` (`:645-664`, `MAX_TOTAL_EXPOSURE_PCT` `:88`).
  Dans le meme panneau, `Positions: 3` vient de `_virtual_portfolio`
  (`core/advisor_loop.py:450-453`). Le contrat manquant est celui d une position : chaque store
  a sa propre forme, donc aucun code ne peut consommer les deux sans conversion ad hoc.
- **Contexte** : phase de gel scientifique. Ce ticket cree du code inerte : rien ne l importe
  encore. Il doit etre revertable sans impact.
- **Hypotheses** :
  - H1 : les champs minimaux suffisants sont symbole, cote, taille en USD, prix d entree,
    horodatage d ouverture, identifiant d origine, store d origine.
    Statut : A CONFIRMER AU DEMARRAGE DU TICKET (inventaire exact des champs de
    `_virtual_portfolio`, de `PositionManager` et de `PaperTrade`).
  - H2 : une cle d identite `(store_origine, identifiant_origine)` est unique et stable
    entre deux cycles. A CONFIRMER AU DEMARRAGE DU TICKET.
  - H3 : aucune position n existe simultanement dans deux stores avec la meme identite metier
    en mode paper. A verifier par SSOT-005, pas par ce ticket.
- **Invariants** : I-02 (lecture seule), I-04 (identite unique), I-08, I-09.
- **Fichiers** (2) :
  - `core/state/position_store.py` (nouveau ; chemin a valider au demarrage)
  - `tests/state/test_position_store_contract.py` (nouveau)
- **Pseudo-code** :

```text
STRUCTURE PositionCanonique (immuable)
    symbole            : texte
    sens               : LONG ou SHORT
    taille_usd         : nombre >= 0
    prix_entree        : nombre > 0
    ouverte_a          : horodatage UTC
    id_origine         : texte
    store_origine      : enum {MEXC_SIM, PAPER_LEDGER, POSITION_MANAGER, WALLET_SYNC}
    FONCTION cle_identite() -> (store_origine, id_origine)

CONTRAT CanonicalPositionStore (lecture seule, aucune mutation)
    OPERATION positions_ouvertes() -> LISTE DE PositionCanonique
    OPERATION nombre_ouvertes()    -> entier
    OPERATION exposition_usd()     -> somme des taille_usd
    OPERATION provenance()         -> texte identifiant la source effective

INVARIANTS DU CONTRAT
    - aucune operation ne modifie l etat sous-jacent
    - nombre_ouvertes() EGALE longueur(positions_ouvertes())
    - exposition_usd() EGALE somme des taille_usd de positions_ouvertes()
    - les cles d identite de positions_ouvertes() sont deux a deux distinctes
```

- **Plan d action** :
  1. Inventorier les champs reellement disponibles dans `_virtual_portfolio`, `PositionManager`
     et `PaperTrade` (`paper_trading/ledger.py`), noter les champs absents.
  2. Arreter le jeu de champs minimal ; tout champ non present dans au moins deux stores est exclu.
  3. Ecrire la structure immuable et le contrat (protocole / classe abstraite).
  4. Ecrire les tests de contrat sur une implementation factice.
  5. Verifier qu aucun module existant n importe le nouveau fichier.
- **Ordre exact** :
  1. Inventaire des champs (lecture seule du code, aucune modification).
  2. Creation de `core/state/position_store.py`.
  3. Creation de `tests/state/test_position_store_contract.py`.
  4. `python -m pytest tests/state/test_position_store_contract.py -q`.
  5. `python -m pytest tests/ -q` pour confirmer l absence d effet de bord.
  6. Commit unique `SSOT-001`.
- **Tests** :
  - Contrat : les 4 invariants du bloc pseudo-code, sur une implementation factice.
  - Non-regression : aucune modification attendue dans les tests existants.
  - Isolement : recherche d import du nouveau module dans le depot => 0 occurrence hors tests.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; le nouveau fichier n est
  importe par aucun module de production.
- **Rollback** : `git revert` du commit `SSOT-001`. Aucun autre ticket ne depend encore de lui.
- **Risques** : jeu de champs trop large, qui forcerait des adaptateurs a inventer des valeurs.
  Mitigation : exclusion de tout champ absent d au moins deux stores.
- **Temps estime** : 0.5 j.
- **Dependances** : PHASE_00 (GOV) close ; precondition de gating remplie.
- **Criteres Done** :
  - `python -m pytest tests/state/test_position_store_contract.py -q` => `passed`, `0 failed`.
  - `python -m pytest tests/ -q` => aucun echec nouveau vs baseline.
  - La recherche du nom `CanonicalPositionStore` dans le depot ne retourne que le nouveau
    module et son test.
  - Diff <= 300 lignes et <= 2 fichiers.
- **Criteres Refus** :
  - Une operation du contrat mute un etat.
  - Un module de production importe le nouveau fichier dans ce ticket.
  - Un champ du modele n existe dans aucun store reel.
  - Le diff touche `core/advisor_loop.py` ou `quant_hedge_ai/agents/risk/portfolio_brain.py`.

---

### SSOT-002 — Adaptateur de lecture MexcSimulator -> store canonique

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-002
- **Titre** : Adaptateur `_virtual_portfolio` (MexcSimulator) vers `PositionCanonique`.
- **Objectif** : exposer les positions paper reellement ouvertes sous le contrat SSOT-001,
  en lecture seule, sans modifier `MexcSimulator`.
- **Pourquoi** : `_virtual_portfolio` est le store qui contient effectivement les positions
  en mode paper ; c est la source qui affiche `Positions: 3` alors que l exposition affiche 0.
- **Diagnostic resume** :
  Les positions paper sont ouvertes dans `_virtual_portfolio` via `place_market_order`
  (`core/advisor_loop.py:2176`), et l affichage lit `_virtual_portfolio.get_open_positions_summary()`
  (`core/advisor_loop.py:450-453`). `pos_manager` n est alimente que par
  `_register_position_from_execution` (`core/advisor_loop.py:3859-3883`, `add_position` `:3883`),
  chemin non emprunte en paper, d ou le bloc `POSITIONS:` absent (condition
  `core/advisor_loop.py:6971`). L adaptateur de ce ticket rend cette source lisible par un
  consommateur unique, sans changer qui ecrit.
- **Contexte** : `MexcSimulator` est defini a `paper_trading/mexc_simulator.py:230` ; il est
  aussi l un des deux ecrivains de `paper_trades.jsonl` (avec `paper_trading/recorder.py`).
  Ce ticket ne touche a aucun des deux.
- **Hypotheses** :
  - H1 : `get_open_positions_summary()` expose taille en USD et prix d entree.
    A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : un identifiant stable par position existe dans `_virtual_portfolio`.
    Si absent, la cle d identite se construit comme `(symbole, ouverte_a)`.
    A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-02, I-04, I-06, I-09. En particulier, aucune ecriture dans `_virtual_portfolio`.
- **Fichiers** (2) :
  - `core/state/adapters/mexc_sim_adapter.py` (nouveau)
  - `tests/state/test_mexc_sim_adapter.py` (nouveau)
- **Pseudo-code** :

```text
ADAPTATEUR MexcSimAdapter IMPLEMENTE CanonicalPositionStore
    RECOIT une reference au simulateur (jamais copiee, jamais mutee)

    OPERATION positions_ouvertes()
        LIRE le resume des positions ouvertes du simulateur
        POUR CHAQUE entree du resume
            SI taille_usd MANQUANTE OU prix_entree MANQUANT
                ALORS journaliser un avertissement ET IGNORER l entree
            SINON produire PositionCanonique(store_origine = MEXC_SIM, ...)
        RENVOYER la liste produite

    OPERATION provenance() -> "mexc_sim:_virtual_portfolio"

REGLE : aucune operation d ecriture, aucune methode du simulateur mutante appelee
REGLE : une entree illisible est ignoree et comptee, jamais remplacee par une valeur par defaut
```

- **Plan d action** :
  1. Lire la forme exacte de `get_open_positions_summary()` et des positions internes.
  2. Ecrire l adaptateur en lecture seule.
  3. Definir la strategie sur entree incomplete : ignorer + compteur d erreurs expose.
  4. Ecrire les tests avec un simulateur factice (0, 1, 3 positions ; une entree incomplete).
  5. Verifier l absence d appel mutant vers le simulateur.
- **Ordre exact** :
  1. Inspection de `paper_trading/mexc_simulator.py` autour de la ligne 230.
  2. Creation de `core/state/adapters/mexc_sim_adapter.py`.
  3. Creation de `tests/state/test_mexc_sim_adapter.py`.
  4. `python -m pytest tests/state -q`.
  5. `python -m pytest tests/ -q`.
  6. Commit unique `SSOT-002`.
- **Tests** :
  - 0 position => `nombre_ouvertes() = 0`, `exposition_usd() = 0`.
  - 3 positions => `nombre_ouvertes() = 3`, exposition = somme exacte des tailles.
  - Entree incomplete => ignoree, compteur d erreurs = 1, aucune exception levee.
  - Test d immutabilite : le simulateur factice enregistre tout appel mutant ; le test echoue
    si un seul appel mutant est observe.
- **Validation** : `python -m pytest tests/state -q` sans echec ; aucun module de production
  n importe encore l adaptateur.
- **Rollback** : `git revert` du commit `SSOT-002`.
- **Risques** : R5 (double comptage) si l adaptateur est plus tard combine a un autre sans
  deduplication ; traite en SSOT-004.
- **Temps estime** : 0.5 j.
- **Dependances** : SSOT-001.
- **Criteres Done** :
  - `python -m pytest tests/state/test_mexc_sim_adapter.py -q` => `0 failed`.
  - Le test d immutabilite passe (0 appel mutant).
  - Diff <= 300 lignes et <= 2 fichiers.
- **Criteres Refus** :
  - `paper_trading/mexc_simulator.py` est modifie.
  - Une entree incomplete est completee par une valeur par defaut.
  - L adaptateur est importe par `core/advisor_loop.py` dans ce ticket.

---

### SSOT-003 — Adaptateurs PositionManager et PaperLedger -> store canonique

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-003
- **Titre** : Adaptateurs de lecture `PositionManager` et `PaperLedger._open`.
- **Objectif** : exposer les deux autres stores paper sous le contrat SSOT-001, pour permettre
  la comparaison d ecart (SSOT-005) et le choix de source (SSOT-004).
- **Pourquoi** : `PositionManager` est aujourd hui la source des contraintes de decision
  (docstring gelee `core/advisor_loop.py:437-448`). Pour mesurer l ecart entre l etat lu par la
  decision et l etat reel, il faut lire les deux sous la meme forme.
- **Diagnostic resume** :
  `portfolio_health` recoit `pos_manager.get_open()` (`core/advisor_loop.py:6785-6787`), qui est
  vide en paper ; `_snapshot` (`quant_hedge_ai/agents/risk/portfolio_brain.py:668-687`) en deduit
  `total_exposure_usd = 0` et `n_positions = 0`, confirme numeriquement par
  `free_cash = 269.79 = 674.47 * 0.40 - 0` (`:645-664`, `:88`). `PaperLedger._open`
  (`paper_trading/ledger.py:121`) est un troisieme etat, avec mutation en place a la cloture
  (`PaperTrade.is_open` passe a `False`, champs `exit_*` remplis), ce qui impose de lire
  les positions ouvertes par filtre et non par pop.
- **Contexte** : `WalletSync` (compte reel, lecture seule) n est pas adapte dans ce ticket :
  il ne participe pas au mode paper. Son adaptation eventuelle est hors perimetre de phase.
- **Hypotheses** :
  - H1 : `PositionManager.get_open()` renvoie des objets porteurs de `size_usd`
    (utilise par `_snapshot` `:668-687`).
  - H2 : `PaperLedger` expose les positions ouvertes par filtre sur `is_open`.
    A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-02, I-04, I-09.
- **Fichiers** (3) :
  - `core/state/adapters/position_manager_adapter.py` (nouveau)
  - `core/state/adapters/paper_ledger_adapter.py` (nouveau)
  - `tests/state/test_legacy_adapters.py` (nouveau)
- **Pseudo-code** :

```text
ADAPTATEUR PositionManagerAdapter IMPLEMENTE CanonicalPositionStore
    OPERATION positions_ouvertes()
        LIRE la liste des positions ouvertes du gestionnaire
        CONVERTIR chaque position en PositionCanonique(store_origine = POSITION_MANAGER)
        RENVOYER la liste (vide est un resultat legitime, jamais une erreur)
    OPERATION provenance() -> "position_manager"

ADAPTATEUR PaperLedgerAdapter IMPLEMENTE CanonicalPositionStore
    OPERATION positions_ouvertes()
        LIRE le registre des trades
        FILTRER ceux dont l indicateur d ouverture est VRAI
        CONVERTIR en PositionCanonique(store_origine = PAPER_LEDGER)
        RENVOYER la liste
    OPERATION provenance() -> "paper_ledger:_open"

REGLE : la cloture d un trade est une mutation en place cote ledger ;
        l adaptateur relit a chaque appel, il ne met jamais en cache
```

- **Plan d action** :
  1. Verifier la forme des positions de `PositionManager` (champs consommes par `_snapshot`).
  2. Verifier le mode d acces aux positions ouvertes de `PaperLedger` (`paper_trading/ledger.py:121`).
  3. Ecrire les deux adaptateurs, sans cache.
  4. Ecrire les tests, dont le cas « store vide » qui doit renvoyer une liste vide sans erreur.
- **Ordre exact** :
  1. Lecture de `paper_trading/ledger.py` (`:121`, `summary():191`) et du module `PositionManager`.
  2. Creation de `core/state/adapters/position_manager_adapter.py`.
  3. Creation de `core/state/adapters/paper_ledger_adapter.py`.
  4. Creation de `tests/state/test_legacy_adapters.py`.
  5. `python -m pytest tests/state -q`.
  6. `python -m pytest tests/ -q`.
  7. Commit unique `SSOT-003`.
- **Tests** :
  - `PositionManagerAdapter` sur gestionnaire vide => liste vide, `exposition_usd() = 0`,
    aucune exception (reproduit l etat paper actuel).
  - `PaperLedgerAdapter` avec 2 ouverts et 3 fermes => `nombre_ouvertes() = 2`.
  - Absence de cache : deux appels successifs autour d une cloture simulee renvoient
    des resultats differents.
  - Immutabilite : aucun appel mutant vers les stores sous-jacents.
- **Validation** : `python -m pytest tests/state -q` sans echec ; toujours aucun import
  depuis la production.
- **Rollback** : `git revert` du commit `SSOT-003`.
- **Risques** : mise en cache accidentelle masquant les clotures ; couverte par le test dedie.
- **Temps estime** : 0.75 j.
- **Dependances** : SSOT-001.
- **Criteres Done** :
  - `python -m pytest tests/state -q` => `0 failed`.
  - Le test « absence de cache » passe.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - `paper_trading/ledger.py` ou le module `PositionManager` est modifie.
  - Un adaptateur leve une exception sur store vide.
  - Presence d un cache memoire non invalide.

---

### SSOT-004 — Resolveur de store + feature-flag (defaut false, non cable)

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-004
- **Titre** : `FEATURE_CANONICAL_POSITION_STORE` et resolveur de source.
- **Objectif** : introduire un point unique qui decide quel store est lu, pilote par un flag
  dont le defaut est `false`, sans qu aucun appelant ne l utilise encore.
- **Pourquoi** : la bascule doit etre un unique interrupteur verifiable, pas une serie de
  modifications dispersees. Sans ce point unique, l etat mixte devient permanent (risque R2).
- **Diagnostic resume** :
  Le systeme lit deux stores dans le meme cycle : `pos_manager` pour la decision
  (`core/advisor_loop.py:6785-6787`) et `_virtual_portfolio` pour l affichage
  (`core/advisor_loop.py:6788`, `:450-453`). Le resolveur remplace ce choix implicite,
  disperse dans `advisor_loop`, par un choix explicite et unique. Tant que le flag vaut `false`,
  le resolveur renvoie l adaptateur `PositionManager` (SSOT-003), donc le meme etat vide
  qu aujourd hui : comportement inchange (I-01).
- **Contexte** : la valeur du flag doit etre lue une fois au demarrage et journalisee.
  Une lecture par cycle ouvrirait la porte a une bascule silencieuse en cours de burn-in.
- **Hypotheses** :
  - H1 : le mecanisme de configuration a utiliser est `config/settings.py` (SSoT Pydantic).
    A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : le mode paper est detectable de facon fiable a l initialisation.
    A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-01, I-02, I-04 (deduplication a la charge du resolveur), I-06, I-07.
- **Fichiers** (3) :
  - `core/state/store_resolver.py` (nouveau)
  - `config/settings.py` (ajout du flag, defaut `false`)
  - `tests/state/test_store_resolver.py` (nouveau)
- **Pseudo-code** :

```text
CONSTANTE FEATURE_CANONICAL_POSITION_STORE : booleen, DEFAUT FAUX

FONCTION resoudre_store(mode, simulateur, gestionnaire, registre) -> CanonicalPositionStore
    SI FEATURE_CANONICAL_POSITION_STORE EST FAUX
        ALORS RENVOYER PositionManagerAdapter(gestionnaire)      # comportement historique
    SINON SI mode EST PAPER
        ALORS RENVOYER MexcSimAdapter(simulateur)                # source reelle des positions paper
    SINON
        ALORS RENVOYER PositionManagerAdapter(gestionnaire)

AU DEMARRAGE
    JOURNALISER une ligne unique : valeur du flag, store resolu, provenance()
    SI le flag est VRAI, JOURNALISER egalement un rappel d epoque

REGLE : la valeur du flag est lue UNE SEULE FOIS au demarrage
REGLE : le resolveur ne combine jamais deux stores (pas d union, pas de fusion)
```

- **Plan d action** :
  1. Ajouter le flag avec defaut `false` dans la configuration, sans le referencer ailleurs.
  2. Ecrire le resolveur avec les trois branches ci-dessus.
  3. Journaliser flag + provenance au demarrage du resolveur.
  4. Ecrire les tests des trois branches et le test de defaut.
- **Ordre exact** :
  1. Modification de `config/settings.py` (ajout du flag uniquement).
  2. Creation de `core/state/store_resolver.py`.
  3. Creation de `tests/state/test_store_resolver.py`.
  4. `python -m pytest tests/state -q`.
  5. `python -m pytest tests/ -q`.
  6. Commit unique `SSOT-004`.
- **Tests** :
  - Defaut : sans variable d environnement, le flag vaut `false`.
  - Branche flag `false` => provenance `position_manager`.
  - Branche flag `true` + paper => provenance `mexc_sim:_virtual_portfolio`.
  - Branche flag `true` + non paper => provenance `position_manager`.
  - Le resolveur ne renvoie jamais une union de stores (test sur la provenance unique).
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; le flag n est reference
  que par le resolveur et son test.
- **Rollback** : `git revert` du commit `SSOT-004`. Le flag disparait avec le commit.
- **Risques** : R2 (bascule silencieuse). Mitigation : defaut `false` en dur, lecture unique
  au demarrage, journalisation obligatoire.
- **Temps estime** : 0.5 j.
- **Dependances** : SSOT-002, SSOT-003.
- **Criteres Done** :
  - `python -m pytest tests/state/test_store_resolver.py -q` => `0 failed`.
  - Avec la configuration par defaut, la journalisation de demarrage indique
    `flag=false store=position_manager`.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Le defaut du flag est `true`.
  - Le flag est relu ailleurs qu au demarrage.
  - Le resolveur fusionne plusieurs stores.
  - `core/advisor_loop.py` est modifie dans ce ticket.

---

### SSOT-005 — Harnais de comparaison passif (dry-run, mesure d ecart)

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-005
- **Titre** : Comparateur passif « store legacy vs store canonique » avec journal d ecart.
- **Objectif** : produire, a chaque cycle, un enregistrement de l ecart entre l etat lu par la
  decision aujourd hui et l etat qui serait lu apres bascule, sans influencer aucune decision.
- **Pourquoi** : la decision d epoque exige une mesure d ecart, pas une intuition. Sans ce
  harnais, la bascule serait un saut a l aveugle.
- **Diagnostic resume** :
  L ecart attendu est structurel et non marginal : la decision lit `pos_manager` vide
  (`core/advisor_loop.py:6785-6787`), l affichage lit `_virtual_portfolio` a 3 positions
  (`core/advisor_loop.py:450-453`). L exposition passerait de 0 a une valeur non nulle, donc
  `free_capital = capital * 0.40 - total_exposure_usd`
  (`quant_hedge_ai/agents/risk/portfolio_brain.py:645-664`, `:88`) diminuerait, ce qui peut
  transformer des acceptations en refus. Ce ticket mesure cette transformation avant de la subir.
- **Contexte** : ADR-0007 impose la passivite. Le harnais ecrit un journal et rien d autre.
  Il ne retourne aucune valeur au flux de decision, il n a pas de valeur de retour consommee.
- **Hypotheses** :
  - H1 : le format de journal utilisable est une ligne JSON par cycle dans `databases/`
    ou `logs/`. Chemin exact : A CONFIRMER AU DEMARRAGE DU TICKET (les repertoires
    `databases/`, `logs/` sont exclus du deploiement par `scripts/deploy_vps.sh`).
  - H2 : le cout d un appel supplementaire aux deux adaptateurs par cycle est negligeable
    devant la duree de cycle (~4-7 min). A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-02, I-03 (passivite stricte), I-05, I-09.
- **Fichiers** (2) :
  - `core/state/shadow_diff.py` (nouveau)
  - `tests/state/test_shadow_diff.py` (nouveau)
- **Pseudo-code** :

```text
OBSERVATEUR ShadowDiff (STRICTEMENT PASSIF)
    OPERATION observer(store_legacy, store_canonique, capital, horodatage)
        legacy    <- { n: store_legacy.nombre_ouvertes(),    expo: store_legacy.exposition_usd() }
        canonique <- { n: store_canonique.nombre_ouvertes(), expo: store_canonique.exposition_usd() }

        free_legacy    <- MAX(0, capital * 0.40 - legacy.expo)
        free_canonique <- MAX(0, capital * 0.40 - canonique.expo)

        ECRIRE UNE LIGNE de journal contenant :
            horodatage, capital,
            legacy.n, canonique.n, ecart_n,
            legacy.expo, canonique.expo, ecart_expo,
            free_legacy, free_canonique, ecart_free,
            provenance de chaque store

        NE RIEN RENVOYER
        SI une erreur survient : la capturer, journaliser, ne jamais la propager

REGLE ADR-0007 : aucune valeur produite ici n est lue par le moteur de decision
REGLE : la constante 0.40 est LUE depuis la configuration existante, jamais redefinie
```

- **Plan d action** :
  1. Ecrire l observateur passif, sans valeur de retour.
  2. Encapsuler tout le corps dans une capture d erreur qui ne propage jamais.
  3. Lire `MAX_TOTAL_EXPOSURE_PCT` depuis sa definition existante
     (`quant_hedge_ai/agents/risk/portfolio_brain.py:88`), sans la dupliquer.
  4. Ecrire les tests, dont un test d isolement verifiant l absence de valeur de retour
     et l absence de mutation.
  5. Ne pas cabler dans `advisor_loop` : le cablage est fait en SSOT-006.
- **Ordre exact** :
  1. Creation de `core/state/shadow_diff.py`.
  2. Creation de `tests/state/test_shadow_diff.py`.
  3. `python -m pytest tests/state -q`.
  4. `python -m pytest tests/ -q`.
  5. Commit unique `SSOT-005`.
- **Tests** :
  - Cas nominal : legacy vide, canonique a 3 positions => `ecart_n = 3`, `ecart_expo > 0`,
    `ecart_free < 0`.
  - Cas identique : les deux stores egaux => tous les ecarts nuls.
  - Erreur d un store : exception levee par l adaptateur => aucune exception propagee,
    une ligne de journal d erreur ecrite.
  - Passivite : l observation ne renvoie rien et ne mute aucun objet recu.
- **Validation** : `python -m pytest tests/state -q` sans echec ; le module n a aucune
  fonction renvoyant une valeur exploitable par la decision.
- **Rollback** : `git revert` du commit `SSOT-005`.
- **Risques** : R3 (observer devenant actif). Mitigation : absence de valeur de retour, test dedie.
  Risque secondaire : volume du journal ; une ligne par cycle a ~4-7 min est borne.
- **Temps estime** : 0.75 j.
- **Dependances** : SSOT-002, SSOT-003, SSOT-004.
- **Criteres Done** :
  - `python -m pytest tests/state/test_shadow_diff.py -q` => `0 failed`.
  - Le test de passivite passe (aucune valeur de retour, aucune mutation).
  - Diff <= 300 lignes et <= 2 fichiers.
- **Criteres Refus** :
  - L observateur renvoie une valeur.
  - Une exception peut remonter au flux de decision.
  - La constante `0.40` est redefinie localement.

---

### SSOT-006 — Cablage AFFICHAGE sur le store canonique + activation du dry-run

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-006
- **Titre** : L affichage lit le store resolu ; le comparateur passif est appele a chaque cycle.
- **Objectif** : faire passer les lignes d affichage du panneau par le resolveur SSOT-004 et
  activer l enregistrement d ecart SSOT-005, sans toucher a l entree de decision.
- **Pourquoi** : c est l etape qui produit la donnee necessaire a la decision d epoque, tout en
  supprimant la derniere source d incoherence d affichage residuelle apres PHASE_01.
- **Diagnostic resume** :
  `core/advisor_loop.py:6788` appelle `_display_position_summary(_virtual_portfolio, pb_health)` :
  `n_open` vient de `_virtual_portfolio` (`:450-453`) avec repli sur `pb_health` (`:456-459`),
  tandis que `pb_health` provient de `pos_manager` (`:6785-6787`). Le builder de snapshot CYCLE
  recalcule `_deployed_notional` / `_paper_equity` / `_paper_cash` en `:6791-6799` et construit
  `PortfolioSnapshot` en `:6888-6906` ; le builder HEARTBEAT fait un travail equivalent en
  `:7444-7482`. Ce ticket fait converger ces lectures d affichage vers le store resolu.
- **Contexte** : avec le flag a `false`, le store resolu est `PositionManagerAdapter`, donc
  l affichage redeviendrait incoherent tel quel. Pour respecter I-01 sans regresser l acquis de
  PHASE_01, l affichage lit le store resolu **quand le flag est vrai** et conserve le chemin
  PHASE_01 (`_virtual_portfolio`) quand il est faux.
- **Hypotheses** :
  - H1 : PHASE_01 a deja fait deriver `exposure` / `paper_cash` / `free_cash` de
    `_virtual_portfolio` cote affichage. A CONFIRMER AU DEMARRAGE DU TICKET (lire PHASE_01.md).
  - H2 : les deux builders (CYCLE `:6788-6906` et HEARTBEAT `:7444-7482`) peuvent appeler
    un helper commun sans depasser l atomicite. Si le refactor depasse 300 lignes,
    scinder en SSOT-006a (CYCLE) et SSOT-006b (HEARTBEAT).
- **Invariants** : I-01 (flag `false` = comportement inchange), I-03, I-05, I-09.
- **Fichiers** (3) :
  - `core/advisor_loop.py` (zones `434-459`, `6788-6906`, `7444-7482` uniquement)
  - `tests/test_system_snapshot.py` (adaptation `31-36`)
  - `tests/capital_deployment/test_capital_lines.py` (adaptation `22-48`)
- **Pseudo-code** :

```text
DANS le builder de snapshot du CYCLE (zone 6788-6906)
    store_affichage <- resoudre_store(...)                       # SSOT-004
    APPELER ShadowDiff.observer(store_legacy, store_canonique, capital, maintenant)   # passif
    n_open    <- store_affichage.nombre_ouvertes()
    expo_usd  <- store_affichage.exposition_usd()
    ALIMENTER les champs d affichage a partir de ces deux valeurs UNIQUEMENT

DANS le builder HEARTBEAT (zone 7444-7482)
    APPLIQUER exactement la meme derivation via le meme helper

INTERDIT DANS CE TICKET
    - modifier l appel portfolio_health(pos_manager.get_open())   # ligne 6786, traite en SSOT-007
    - modifier pos_manager, ses ecritures, ou _register_position_from_execution (3859-3883)
    - modifier une constante de risque
```

- **Plan d action** :
  1. Extraire un helper unique de derivation d affichage utilise par les deux builders.
  2. Brancher le resolveur dans ce helper.
  3. Ajouter l appel au comparateur passif une fois par cycle.
  4. Verifier que la ligne `6786` est inchangee (diff cible).
  5. Adapter les tests d instantane et de lignes de capital.
- **Ordre exact** :
  1. Lecture des zones `434-459`, `6788-6906`, `7444-7482`.
  2. Extraction du helper commun.
  3. Branchement du resolveur + appel du comparateur passif.
  4. Adaptation de `tests/test_system_snapshot.py:31-36`.
  5. Adaptation de `tests/capital_deployment/test_capital_lines.py:22-48`.
  6. `python -m pytest tests/test_system_snapshot.py tests/capital_deployment -q`.
  7. `python -m pytest tests/ -q`.
  8. Commit unique `SSOT-006`.
- **Tests** :
  - Flag `false` : les valeurs affichees sont identiques a la baseline PHASE_01 (test d egalite).
  - Flag `true`, 3 positions : `n_open = 3` ET `exposition > 0` dans le meme snapshot.
  - Coherence croisee : il n existe aucun etat produit ou `n_open > 0` et `exposition = 0`.
  - Le comparateur passif est appele exactement une fois par cycle.
  - La ligne `core/advisor_loop.py:6786` n apparait pas dans le diff.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; inspection du diff
  confirmant l absence de modification de l entree de decision.
- **Rollback** : `git revert` du commit `SSOT-006`. L affichage revient au chemin PHASE_01.
- **Risques** : R7 (regression d affichage). Mitigation : test d egalite avec la baseline PHASE_01
  quand le flag est `false`.
- **Temps estime** : 1 j.
- **Dependances** : SSOT-004, SSOT-005, PHASE_01 close.
- **Criteres Done** :
  - `python -m pytest tests/ -q` => aucun echec nouveau.
  - Le journal d ecart contient au moins une ligne par cycle sur 10 cycles consecutifs.
  - `git diff` du commit ne contient aucune ligne de la zone `6785-6787`.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - L appel `portfolio_health(pos_manager.get_open())` est modifie.
  - Un etat `n_open > 0` avec `exposition = 0` reste possible quand le flag est `true`.
  - Le comparateur passif influence une valeur consommee par la decision.
  - Le diff depasse 300 lignes (dans ce cas : scinder en SSOT-006a / SSOT-006b).

---

### SSOT-007 — Cablage DECISION : `portfolio_health` lit le store resolu

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur. **Ticket le plus contraint de la phase : il modifie l entree de decision,
donc il cree l epoque. Il ne peut etre commite qu apres signature de l ADR et archivage du
dataset V4.**

- **ID** : SSOT-007
- **Titre** : Remplacer `pos_manager.get_open()` par le store resolu dans l appel a `portfolio_health`.
- **Objectif** : faire lire a la decision le meme etat que l affichage, sous flag, en un seul
  point de modification.
- **Pourquoi** : c est le premier point d incoherence identifie
  (`core/advisor_loop.py:6786`). Tant qu il n est pas corrige, les contraintes de portefeuille
  sont calculees sur un portefeuille vide, donc inoperantes en paper.
- **Diagnostic resume** :
  `core/advisor_loop.py:6785-6787` : `portfolio_brain.portfolio_health(pos_manager.get_open())`.
  En paper, `pos_manager` est vide car les positions sont ouvertes dans `_virtual_portfolio`
  (`:2176`) et `pos_manager.add_position` (`:3883`, via `_register_position_from_execution`
  `:3859-3883`) n est pas emprunte. `_snapshot`
  (`quant_hedge_ai/agents/risk/portfolio_brain.py:668-687`) somme `p.size_usd` sur une liste vide
  => `total_exposure_usd = 0`, `n_positions = 0` ; `portfolio_health` (`:645-664`) renvoie donc
  `free_capital = capital * 0.40` complet (preuve : `269.79 = 674.47 * 0.40 - 0`, `:88`).
  La docstring `core/advisor_loop.py:437-448` gele explicitement cette correction jusqu a la
  calibration ; le present ticket est la levee de ce gel, sous ADR.
- **Contexte** : la modification est d une ligne, son effet est une nouvelle epoque. Les refus
  de `portfolio_brain` vont augmenter (exposition non nulle, `free_capital` reduit), ce qui
  modifie la population de trades et donc tous les verdicts H1-H6.
- **Hypotheses** :
  - H1 : `portfolio_health` accepte une liste d objets porteurs de `size_usd` ; les
    `PositionCanonique` devront exposer ce champ ou etre convertis par l appelant.
    A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : aucun autre appelant de `portfolio_health` n existe ailleurs dans la base.
    A CONFIRMER AU DEMARRAGE DU TICKET (recherche du nom `portfolio_health`).
- **Invariants** : I-01 (flag `false` = strictement inchange), I-05, I-06 (`0.40` inchange),
  I-07, I-08, I-10.
- **Fichiers** (3) :
  - `core/advisor_loop.py` (zone `6785-6790` et docstring `437-448` a mettre a jour)
  - `tests/test_state_integrity.py` (adaptation `51-56`, `277-285`)
  - `tests/state/test_decision_input.py` (nouveau)
- **Pseudo-code** :

```text
DANS le cycle (zone 6785-6790)
    positions_pour_decision <- store_resolu.positions_ouvertes()      # SSOT-004
    sante <- portfolio_brain.portfolio_health(positions_pour_decision)

    # flag FAUX  => store_resolu = PositionManagerAdapter => liste identique a aujourd hui
    # flag VRAI  => store_resolu = MexcSimAdapter        => NOUVELLE EPOQUE

METTRE A JOUR la docstring 437-448
    REMPLACER « bug documente, gele, a corriger a la calibration »
    PAR       « corrige sous flag FEATURE_CANONICAL_POSITION_STORE, ADR-00XX, epoque V5 »
    CONSERVER le rappel de la regression historique du 2026-07-12 21:00 UTC (462-471)

INTERDIT
    - modifier _snapshot ou portfolio_health (668-687, 645-664)
    - modifier MAX_TOTAL_EXPOSURE_PCT (88)
    - toucher au sizing, au risk gate, ou a check_new_trade dans ce ticket
```

- **Plan d action** :
  1. Verifier l unicite de l appelant de `portfolio_health`.
  2. Remplacer l argument par la lecture du store resolu (une ligne).
  3. Mettre a jour la docstring gelee `437-448` en citant le numero d ADR reel.
  4. Ecrire un test qui, flag `false`, verifie l egalite stricte de la sante de portefeuille
     avec la baseline.
  5. Ecrire un test qui, flag `true` avec 3 positions, verifie `n_positions = 3` et
     `total_exposure_pct > 0`.
  6. Adapter `tests/test_state_integrity.py:51-56` et `:277-285`.
- **Ordre exact** :
  1. Recherche des appelants de `portfolio_health`.
  2. Modification de la zone `6785-6790`.
  3. Mise a jour de la docstring `437-448`.
  4. Creation de `tests/state/test_decision_input.py`.
  5. Adaptation de `tests/test_state_integrity.py`.
  6. `python -m pytest tests/test_state_integrity.py tests/state -q`.
  7. `python -m pytest tests/ -q`.
  8. Commit unique `SSOT-007` (message citant l ADR d epoque).
- **Tests** :
  - Flag `false` : `portfolio_health` recoit exactement la meme liste qu avant (egalite stricte).
  - Flag `true`, 3 positions : `n_positions = 3`, `total_exposure_usd = somme des tailles`,
    `free_capital = capital * 0.40 - total_exposure_usd`.
  - Coherence intra-cycle (I-05) : affichage et decision produisent le meme `n` et la meme
    exposition dans un cycle donne.
  - Aucun changement de constante : test verifiant `MAX_TOTAL_EXPOSURE_PCT = 0.40`.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; rejeu de cycles enregistres
  avec flag `false` => `0 divergence` de verdict.
- **Rollback** : `git revert` du commit `SSOT-007` (code) ; **le rollback de donnees est
  impossible** une fois des trades produits avec le flag `true` (voir section Rollback de phase).
- **Risques** : R1 (destruction du burn-in) — assume et couvert par l ADR ; R2 (bascule
  silencieuse) — couvert par SSOT-004 ; R5 (double comptage) — couvert par I-04.
- **Temps estime** : 1 j (hors temps de decision d epoque).
- **Dependances** : SSOT-006, ADR d epoque signe (SSOT-016), archivage du dataset V4.
- **Criteres Done** :
  - `python -m pytest tests/ -q` => aucun echec nouveau.
  - Flag `false` : rejeu => `0 divergence`.
  - Flag `true` : dans 10 cycles consecutifs, aucun etat `n_positions > 0` avec
    `total_exposure_pct = 0`.
  - La docstring `437-448` ne contient plus la mention « gele, a corriger a la calibration ».
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Le commit est fait sans ADR signe reference dans le message.
  - Le dataset V4 n a pas ete archive avant le commit.
  - Une constante de risque est modifiee.
  - Le flag `false` produit une seule divergence de verdict au rejeu.
  - Le ticket touche au sizing, a `check_new_trade` ou au risk gate.

---

### SSOT-008 — `PortfolioSnapshot` canonique unique + alias de compatibilite

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-008
- **Titre** : Designer `observability/system_snapshot.py:56` comme `PortfolioSnapshot` canonique.
- **Objectif** : une seule definition de la structure, les deux autres devenant des alias
  explicitement marques comme deprecies, sans changer les champs.
- **Pourquoi** : trois definitions concurrentes rendent toute garantie de coherence impossible :
  un champ corrige dans l une reste faux dans les deux autres.
- **Diagnostic resume** :
  3 classes `PortfolioSnapshot` : `observability/system_snapshot.py:56` (champs `paper_equity`,
  `paper_cash`, `free_cash`, `portfolio_exposure_pct`, `open_pnl_usd`, `open_positions`,
  `correlation_risk_pct`, `session_pnl_usd`), `quant_hedge_ai/agents/risk/portfolio_brain.py:64`,
  `visualization/api/models.py:69`. Le builder `core/advisor_loop.py:6888-6906` construit la
  premiere ; `portfolio_health` (`:645-664`) alimente la deuxieme ; l API REST expose la troisieme
  (`visualization/api/portfolio_api.py:33` recopie `portfolio.paper_equity` dans `capital_usd`).
  La coexistence est la cause structurelle du WARNING sur `free_cash` (producteur unique mais
  co-affiche avec `paper_cash` contradictoire).
- **Contexte** : le choix du canonique se porte sur `observability/system_snapshot.py:56` car
  c est la structure la plus complete (8 champs) et celle qui est serialisee (`to_dict:143`).
- **Hypotheses** :
  - H1 : les champs des deux autres classes sont un sous-ensemble des 8 champs canoniques.
    A CONFIRMER AU DEMARRAGE DU TICKET ; tout champ supplementaire doit etre liste et arbitre
    avant de poursuivre.
  - H2 : aucun consommateur ne teste le type exact par identite de classe.
    A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-01, I-08, I-09. Aucun champ n est renomme ni supprime dans ce ticket.
- **Fichiers** (3) :
  - `observability/system_snapshot.py` (marquage canonique, docstring)
  - `quant_hedge_ai/agents/risk/portfolio_brain.py` (remplacement de la definition `:64` par un alias)
  - `tests/test_system_snapshot.py` (adaptation `31-36`)
- **Pseudo-code** :

```text
DANS observability/system_snapshot.py
    MARQUER PortfolioSnapshot (ligne 56) COMME CANONIQUE
    DOCUMENTER : producteur unique, liste des 8 champs, unites, source de chaque champ

DANS quant_hedge_ai/agents/risk/portfolio_brain.py
    SUPPRIMER la definition locale de PortfolioSnapshot (ligne 64)
    IMPORTER la definition canonique
    DECLARER un alias marque DEPRECIE avec date de retrait prevue

REGLE : aucun champ renomme, aucun champ supprime, aucune valeur recalculee ici
REGLE : si un champ local n existe pas dans le canonique -> ARRETER et arbitrer, ne pas inventer
```

- **Plan d action** :
  1. Comparer champ par champ les trois definitions ; produire le tableau des ecarts.
  2. Si un champ manque au canonique, arreter le ticket et ouvrir un arbitrage.
  3. Remplacer la definition de `portfolio_brain.py:64` par l import + alias deprecie.
  4. Adapter `tests/test_system_snapshot.py:31-36`.
  5. Laisser `visualization/api/models.py:69` pour SSOT-009 (contrainte d atomicite).
- **Ordre exact** :
  1. Tableau comparatif des champs (document de travail du ticket).
  2. Marquage canonique dans `observability/system_snapshot.py`.
  3. Modification de `quant_hedge_ai/agents/risk/portfolio_brain.py`.
  4. Adaptation de `tests/test_system_snapshot.py`.
  5. `python -m pytest tests/test_system_snapshot.py -q`.
  6. `python -m pytest tests/ -q`.
  7. Commit unique `SSOT-008`.
- **Tests** :
  - Le nombre de definitions de classe `PortfolioSnapshot` dans le depot passe de 3 a 2.
  - Serialisation : `to_dict()` (`:143`) produit les memes cles qu avant.
  - Un consommateur de `portfolio_brain` recoit un objet portant les 8 champs canoniques.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; recherche `class PortfolioSnapshot`
  => 2 occurrences (canonique + `visualization/api/models.py:69`, traite en SSOT-009).
- **Rollback** : `git revert` du commit `SSOT-008`.
- **Risques** : R4 (consommateur non identifie). Mitigation : alias conserve, aucun champ retire.
- **Temps estime** : 0.75 j.
- **Dependances** : aucune technique ; a executer apres SSOT-007 pour ne pas melanger les diffs.
- **Criteres Done** :
  - Recherche de `class PortfolioSnapshot` => exactement 2 occurrences.
  - `python -m pytest tests/ -q` => aucun echec nouveau.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Un champ est renomme ou supprime.
  - Un champ present dans une definition locale disparait sans arbitrage ecrit.
  - Le ticket modifie egalement `visualization/api/models.py` (depassement de perimetre).

---

### SSOT-009 — Migration du consommateur REST vers le `PortfolioSnapshot` canonique

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-009
- **Titre** : `visualization/api/models.py:69` remplace par la structure canonique.
- **Objectif** : supprimer la troisieme definition de `PortfolioSnapshot` et faire consommer
  la canonique par la couche API, sans modifier le contenu expose (traite en PHASE_03).
- **Pourquoi** : tant que l API porte sa propre definition, toute correction de la structure
  canonique ne se propage pas jusqu au client.
- **Diagnostic resume** :
  `visualization/api/models.py:69` definit une troisieme `PortfolioSnapshot`.
  `visualization/api/portfolio_api.py` la remplit avec des valeurs figees : `n_trades = 0`,
  `n_wins = 0`, `n_losses = 0`, `win_rate_pct = 0.0`, `profit_factor = 0.0`,
  `expectancy_pct = 0.0`, `max_drawdown_pct = 0.0`, `sharpe = 0.0` (`:22-29`),
  `total_pnl_usd = open_pnl_usd` (`:30`, recopie du PnL ouvert dans le PnL total),
  `capital_usd = portfolio.paper_equity` (`:33`), `trade_history = []` (`:34`).
  Le present ticket ne corrige pas ces valeurs (perimetre PHASE_03, prefixe REST-xxx) :
  il unifie seulement la structure.
- **Contexte** : separer structure et contenu evite un ticket non atomique et permet de
  reverter independamment.
- **Hypotheses** :
  - H1 : la structure de l API est utilisee pour la serialisation HTTP et impose un contrat
    de champs vers le client. A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : la structure canonique est serialisable dans le meme format.
    A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-01, I-08, I-09. Le contrat de champs expose au client reste identique.
- **Fichiers** (3) :
  - `visualization/api/models.py` (suppression de la definition `:69`, import du canonique)
  - `visualization/api/portfolio_api.py` (adaptation d appel uniquement, valeurs inchangees)
  - `tests/visualization/test_snapshot_only_loaders.py` (adaptation)
- **Pseudo-code** :

```text
DANS visualization/api/models.py
    SUPPRIMER la definition locale de PortfolioSnapshot (ligne 69)
    IMPORTER la definition canonique d observability
    SI le contrat HTTP exige des champs supplementaires
        ALORS definir un MODELE DE PRESENTATION distinct qui ENVELOPPE le canonique
        JAMAIS une seconde definition du meme concept

DANS visualization/api/portfolio_api.py
    ADAPTER uniquement la construction de l objet
    NE PAS TOUCHER aux valeurs figees des lignes 22-29, 30, 33, 34   # perimetre PHASE_03 / REST-xxx
    AJOUTER un commentaire renvoyant au ticket REST correspondant
```

- **Plan d action** :
  1. Verifier le contrat de champs expose par l API.
  2. Supprimer la definition locale et importer le canonique, ou envelopper si le contrat differe.
  3. Adapter la construction dans `portfolio_api.py` sans changer une seule valeur.
  4. Adapter `tests/visualization/test_snapshot_only_loaders.py`.
- **Ordre exact** :
  1. Releve du contrat de champs actuel de l API (avant modification).
  2. Modification de `visualization/api/models.py`.
  3. Modification de `visualization/api/portfolio_api.py` (appel seulement).
  4. Adaptation de `tests/visualization/test_snapshot_only_loaders.py`.
  5. `python -m pytest tests/visualization -q`.
  6. `python -m pytest tests/ -q`.
  7. Commit unique `SSOT-009`.
- **Tests** :
  - Le contrat de champs expose est identique avant / apres (comparaison des cles serialisees).
  - Les valeurs figees `:22-29` sont toujours presentes et inchangees (test explicite qui
    documente la dette, leve en PHASE_03).
  - Recherche `class PortfolioSnapshot` => 1 occurrence.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; cles de reponse identiques.
- **Rollback** : `git revert` du commit `SSOT-009`.
- **Risques** : R4 ; rupture du contrat client si le canonique n a pas tous les champs
  (mitige par le modele de presentation enveloppant).
- **Temps estime** : 0.75 j.
- **Dependances** : SSOT-008.
- **Criteres Done** :
  - Recherche de `class PortfolioSnapshot` => exactement 1 occurrence
    (`observability/system_snapshot.py:56`).
  - Les cles de la reponse API sont inchangees.
  - `python -m pytest tests/ -q` => aucun echec nouveau.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Une valeur exposee par l API change dans ce ticket.
  - Une quatrieme definition apparait (modele de presentation nomme `PortfolioSnapshot`).
  - Le contrat de champs expose au client est modifie.

---

### SSOT-010 — Arbitrage des deux `PortfolioBrain`

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-010
- **Titre** : Designer un `PortfolioBrain` canonique et deprecier le second.
- **Objectif** : une seule implementation de la logique de sante de portefeuille, les autres
  points d entree devenant des reexports marques deprecies.
- **Pourquoi** : deux implementations d un composant qui produit `total_exposure_pct`,
  `n_positions`, `free_capital` = deux verites possibles sur la meme grandeur, selon le module
  qui importe.
- **Diagnostic resume** :
  2 classes `PortfolioBrain` : `quant_hedge_ai/agents/risk/portfolio_brain.py:75` (celle qui
  porte `portfolio_health:645-664`, `_snapshot:668-687`, `MAX_TOTAL_EXPOSURE_PCT:88`, appelee
  par `core/advisor_loop.py:6785-6787`) et `quant_hedge_ai/agents/portfolio/__init__.py:71`.
  Seule la premiere est prouvee active sur le chemin de decision (preuve numerique
  `free_cash = 269.79 = 674.47 * 0.40 - 0`). Le role exact de la seconde et ses appelants :
  A CONFIRMER AU DEMARRAGE DU TICKET.
- **Contexte** : ADR-0007 et gel des seuils ; l arbitrage ne doit modifier aucun comportement.
  Si les deux implementations divergent fonctionnellement, le ticket s arrete et remonte
  l arbitrage a l operateur.
- **Hypotheses** :
  - H1 : `quant_hedge_ai/agents/risk/portfolio_brain.py:75` est canonique (seule prouvee
    active sur le chemin de decision).
  - H2 : la seconde est soit un reexport, soit une variante non utilisee.
    A CONFIRMER AU DEMARRAGE DU TICKET (recherche des importations de
    `quant_hedge_ai/agents/portfolio`).
  - H3 : si les deux divergent (constantes, checks), l unification est un changement de
    comportement => ticket suspendu, arbitrage operateur requis.
- **Invariants** : I-01, I-06 (aucun seuil change), I-08, I-09.
- **Fichiers** (3) :
  - `quant_hedge_ai/agents/portfolio/__init__.py` (reexport deprecie)
  - `quant_hedge_ai/agents/risk/portfolio_brain.py` (marquage canonique, docstring)
  - `tests/state/test_portfolio_brain_unicity.py` (nouveau)
- **Pseudo-code** :

```text
ETAPE 1 : COMPARER les deux implementations
    LISTER pour chacune : constantes, checks, signature de portfolio_health
    SI DIFFERENCE FONCTIONNELLE
        ALORS SUSPENDRE LE TICKET, produire le tableau des ecarts, demander arbitrage
    SINON CONTINUER

ETAPE 2 : DESIGNER LE CANONIQUE
    MARQUER quant_hedge_ai/agents/risk/portfolio_brain.py COMME CANONIQUE
    REMPLACER la definition de quant_hedge_ai/agents/portfolio/__init__.py PAR UN REEXPORT
    MARQUER le reexport DEPRECIE, avec date de retrait

REGLE : les 8 checks de portefeuille ne sont ni ajoutes, ni retires, ni reordonnes
REGLE : MAX_TOTAL_EXPOSURE_PCT reste a 0.40
```

- **Plan d action** :
  1. Rechercher tous les importateurs des deux classes.
  2. Produire le tableau comparatif constantes / checks / signatures.
  3. Si divergence fonctionnelle : suspendre et remonter.
  4. Sinon : transformer la seconde en reexport deprecie.
  5. Ecrire le test d unicite.
- **Ordre exact** :
  1. Recherche des importateurs (`quant_hedge_ai.agents.portfolio`, `portfolio_brain`).
  2. Tableau comparatif (document de travail du ticket).
  3. Marquage canonique.
  4. Transformation en reexport.
  5. Creation de `tests/state/test_portfolio_brain_unicity.py`.
  6. `python -m pytest tests/ -q`.
  7. Commit unique `SSOT-010`.
- **Tests** :
  - Recherche de `class PortfolioBrain` => 1 occurrence.
  - Les deux chemins d import renvoient le meme objet (identite de classe).
  - `MAX_TOTAL_EXPOSURE_PCT` vaut 0.40.
  - Les checks de portefeuille sont au meme nombre qu avant (valeur exacte :
    A CONFIRMER AU DEMARRAGE DU TICKET).
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; identite de classe verifiee.
- **Rollback** : `git revert` du commit `SSOT-010`.
- **Risques** : divergence fonctionnelle silencieuse entre les deux implementations.
  Mitigation : suspension du ticket en cas de divergence, arbitrage explicite.
- **Temps estime** : 0.75 j.
- **Dependances** : SSOT-008 (la structure canonique doit exister avant l unification du producteur).
- **Criteres Done** :
  - Recherche de `class PortfolioBrain` => exactement 1 occurrence.
  - Le test d identite de classe entre les deux chemins d import passe.
  - `python -m pytest tests/ -q` => aucun echec nouveau.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Un check de portefeuille est ajoute, retire ou reordonne.
  - Une constante de risque change.
  - Le ticket est commite malgre une divergence fonctionnelle non arbitree.

---

### SSOT-011 — Unification des deux `SystemSnapshot`

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-011
- **Titre** : `observability/system_snapshot.py:132` designe canonique ;
  `infra/monitoring/daily_analyzer.py:19` devient consommateur.
- **Objectif** : une seule structure d instantane systeme, serialisee par un seul `to_dict`.
- **Pourquoi** : deux instantanes systeme = deux photographies potentiellement contradictoires
  du meme cycle, dont l une alimente l analyse quotidienne.
- **Diagnostic resume** :
  2 classes `SystemSnapshot` : `observability/system_snapshot.py:132` (avec `to_dict:143`,
  contenant le `PortfolioSnapshot` canonique `:56`) et `infra/monitoring/daily_analyzer.py:19`.
  Le builder du cycle produit la premiere (`core/advisor_loop.py:6888-6906`), le builder
  HEARTBEAT une variante (`:7444-7482`). La seconde structure est utilisee par l analyse
  quotidienne ; ses champs exacts et ses producteurs : A CONFIRMER AU DEMARRAGE DU TICKET.
- **Contexte** : `daily_analyzer` est un observateur (ADR-0007). Son unification ne doit
  introduire aucun retour vers la decision.
- **Hypotheses** :
  - H1 : les champs de `daily_analyzer.SystemSnapshot` sont un sous-ensemble du canonique.
    A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : `daily_analyzer` lit un instantane deja produit, il ne le recalcule pas.
    A CONFIRMER AU DEMARRAGE DU TICKET ; si `daily_analyzer` recalcule, le recalcul est
    traite en SSOT-015 et non ici.
- **Invariants** : I-01, I-03, I-08, I-09.
- **Fichiers** (3) :
  - `infra/monitoring/daily_analyzer.py` (suppression de la definition `:19`, import du canonique)
  - `observability/system_snapshot.py` (docstring de designation, aucun changement de champ)
  - `tests/test_system_snapshot.py` (extension)
- **Pseudo-code** :

```text
DANS infra/monitoring/daily_analyzer.py
    SUPPRIMER la definition locale de SystemSnapshot (ligne 19)
    IMPORTER la structure canonique (observability/system_snapshot.py:132)
    SI un champ local est absent du canonique
        ALORS NE PAS l ajouter au canonique dans ce ticket
        MAIS le declarer dans un tableau d ecarts et suspendre la partie concernee

REGLE : la serialisation reste celle de to_dict (ligne 143), unique
REGLE : daily_analyzer reste STRICTEMENT PASSIF (ADR-0007)
```

- **Plan d action** :
  1. Comparer champ par champ les deux structures.
  2. Supprimer la definition locale et importer le canonique.
  3. Verifier qu aucune valeur de sortie de l analyse quotidienne ne change.
  4. Etendre `tests/test_system_snapshot.py`.
- **Ordre exact** :
  1. Tableau comparatif des champs.
  2. Modification de `infra/monitoring/daily_analyzer.py`.
  3. Docstring de designation dans `observability/system_snapshot.py`.
  4. Extension de `tests/test_system_snapshot.py`.
  5. `python -m pytest tests/ -q`.
  6. Commit unique `SSOT-011`.
- **Tests** :
  - Recherche de `class SystemSnapshot` => 1 occurrence.
  - La sortie de l analyse quotidienne est identique avant / apres sur un jeu fige.
  - `to_dict()` produit les memes cles qu avant.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; sortie de l analyse
  quotidienne inchangee sur jeu fige.
- **Rollback** : `git revert` du commit `SSOT-011`.
- **Risques** : perte silencieuse d un champ specifique a `daily_analyzer`.
  Mitigation : tableau d ecarts obligatoire, suspension partielle plutot qu ajout au canonique.
- **Temps estime** : 0.75 j.
- **Dependances** : SSOT-008.
- **Criteres Done** :
  - Recherche de `class SystemSnapshot` => exactement 1 occurrence.
  - Sortie de l analyse quotidienne identique sur jeu fige.
  - `python -m pytest tests/ -q` => aucun echec nouveau.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Un champ est ajoute au canonique sans arbitrage ecrit.
  - `daily_analyzer` produit une valeur consommee par la decision.
  - Une sortie de l analyse quotidienne change.

---

### SSOT-012 — Couche de metriques canonique : capital, equity, cash

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-012
- **Titre** : Projections canoniques `capital`, `equity`, `cash` (definitions uniques, pures).
- **Objectif** : ecrire un module de projections pures qui produit ces trois grandeurs a partir
  du store canonique et de la base de capital, et qui devient le seul producteur autorise.
- **Pourquoi** : audit SSoT : `capital` recalcule a 5 endroits, `equity` a 5, `cash` avec
  2 definitions rivales. Sans definition unique, chaque panneau peut afficher une valeur
  differente et defendable.
- **Diagnostic resume** :
  Le builder de cycle recalcule localement `_deployed_notional`, `_paper_equity`, `_paper_cash`
  (`core/advisor_loop.py:6791-6799`) ; le builder HEARTBEAT refait un travail equivalent
  (`:7444-7482`) ; `portfolio_health` produit `capital` et `free_capital`
  (`quant_hedge_ai/agents/risk/portfolio_brain.py:645-664`) ; `PaperLedger.summary()`
  (`paper_trading/ledger.py:191`) produit `capital` ; l API recopie
  `capital_usd = portfolio.paper_equity` (`visualization/api/portfolio_api.py:33`).
  Le WARNING de l audit porte sur `free_cash` : producteur unique, mais co-affiche avec un
  `paper_cash` calcule ailleurs et contradictoire.
- **Contexte** : la base de sizing reste epinglee a `WALLET_PAPER_CAPITAL` (I-07). Ce ticket
  ne change pas la base, il rend sa propagation unique.
- **Hypotheses** :
  - H1 : `equity = capital_de_base + PnL_ferme + PnL_ouvert`.
    A CONFIRMER AU DEMARRAGE DU TICKET (les definitions rivales existantes doivent etre
    relevees avant d en fixer une).
  - H2 : `cash = capital_de_base + PnL_ferme - exposition_usd`.
    A CONFIRMER AU DEMARRAGE DU TICKET.
  - H3 : les deux definitions rivales de `cash` sont documentables et l une d elles est
    strictement dominante. Si aucune ne l est : arbitrage operateur, ticket suspendu.
- **Invariants** : I-02, I-05, I-06, I-07, I-09. Fonctions pures : memes entrees => meme sortie,
  aucun acces global, aucun effet de bord.
- **Fichiers** (2) :
  - `core/state/metrics/capital.py` (nouveau)
  - `tests/state/test_metrics_capital.py` (nouveau)
- **Pseudo-code** :

```text
MODULE metrics.capital (FONCTIONS PURES, AUCUN ETAT GLOBAL)

    FONCTION capital_de_base(configuration) -> nombre
        RENVOYER la valeur epinglee WALLET_PAPER_CAPITAL          # jamais l equity

    FONCTION exposition_usd(store) -> nombre
        RENVOYER store.exposition_usd()

    FONCTION equity(capital_de_base, pnl_ferme, pnl_ouvert) -> nombre
        RENVOYER capital_de_base + pnl_ferme + pnl_ouvert

    FONCTION cash(capital_de_base, pnl_ferme, exposition) -> nombre
        RENVOYER capital_de_base + pnl_ferme - exposition

    FONCTION free_capital(capital_de_base, exposition, plafond_expo) -> nombre
        RENVOYER MAX(0, capital_de_base * plafond_expo - exposition)

REGLE : chaque grandeur a UNE definition, ecrite ici, citee dans la docstring
REGLE : plafond_expo est PASSE en argument, jamais redefini (source : portfolio_brain.py:88)
REGLE : aucune fonction ne lit un fichier, une base, ou une variable d environnement
```

- **Plan d action** :
  1. Relever les definitions existantes de `capital`, `equity`, `cash` aux 5 + 5 + 2 endroits
     identifies par l audit ; produire le tableau des definitions rivales.
  2. Fixer une definition par grandeur ; documenter celles ecartees et pourquoi.
  3. Ecrire les projections pures.
  4. Ecrire les tests, dont les cas limites (exposition > capital, PnL negatif).
  5. Ne cabler aucun appelant : cablage en SSOT-015.
- **Ordre exact** :
  1. Tableau des definitions rivales (document de travail du ticket).
  2. Creation de `core/state/metrics/capital.py`.
  3. Creation de `tests/state/test_metrics_capital.py`.
  4. `python -m pytest tests/state -q`.
  5. `python -m pytest tests/ -q`.
  6. Commit unique `SSOT-012`.
- **Tests** :
  - Purete : deux appels identiques renvoient la meme valeur ; aucun acces disque ni
    variable d environnement (test par instrumentation).
  - `free_capital` reproduit exactement la preuve numerique : capital 674.47, exposition 0,
    plafond 0.40 => 269.79.
  - Exposition superieure au plafond => `free_capital = 0`, jamais negatif.
  - `equity` et `cash` : cas PnL ferme negatif, PnL ouvert negatif.
- **Validation** : `python -m pytest tests/state -q` sans echec ; module non importe par
  la production a ce stade.
- **Rollback** : `git revert` du commit `SSOT-012`.
- **Risques** : choisir une definition de `cash` qui contredit un affichage existant.
  Mitigation : tableau des definitions rivales et arbitrage explicite avant ecriture.
- **Temps estime** : 1 j.
- **Dependances** : SSOT-001.
- **Criteres Done** :
  - `python -m pytest tests/state/test_metrics_capital.py -q` => `0 failed`.
  - Le test reproduisant `269.79 = 674.47 * 0.40 - 0` passe.
  - Le tableau des definitions rivales est joint au commit (message ou fichier de doc).
  - Diff <= 300 lignes et <= 2 fichiers.
- **Criteres Refus** :
  - Une fonction lit une variable d environnement, un fichier ou un etat global.
  - `plafond_expo` est redefini dans le module.
  - La base de capital devient l equity (violation I-07).

---

### SSOT-013 — Couche de metriques canonique : PnL ouvert et PnL ferme

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-013
- **Titre** : Projections canoniques `pnl_ouvert` et `pnl_ferme`.
- **Objectif** : une definition unique du PnL ouvert (positions en cours) et du PnL ferme
  (trades clotures), separees et jamais confondues.
- **Pourquoi** : audit SSoT : 4 calculs de PnL ouvert et 2 de PnL ferme. Le cas le plus grave
  est une recopie du PnL ouvert dans le PnL total.
- **Diagnostic resume** :
  `visualization/api/portfolio_api.py:30` fait `total_pnl_usd = open_pnl_usd` : le PnL total
  expose est en realite le PnL ouvert. Le champ `open_pnl_usd` existe aussi dans le
  `PortfolioSnapshot` canonique (`observability/system_snapshot.py:56`), alimente par le builder
  de cycle (`core/advisor_loop.py:6888-6906`) et par le builder HEARTBEAT (`:7444-7482`).
  `PaperLedger.summary()` (`paper_trading/ledger.py:191`) produit une lignee separee a partir de
  trades dont la cloture est une mutation en place (`is_open` passe a `False`, champs `exit_*`
  remplis), ce qui impose de distinguer clairement les deux populations.
- **Contexte** : la phase ne corrige pas l API (perimetre PHASE_03 / REST-xxx). Ce ticket fournit
  la definition que REST-xxx consommera.
- **Hypotheses** :
  - H1 : `pnl_ouvert = somme sur positions ouvertes de (prix_courant - prix_entree) * quantite`,
    signe selon le sens. La source du prix courant : A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : `pnl_ferme = somme des PnL des trades clotures de l epoque courante`, bornee par
    `CLEAN_DATA_SINCE_ACTIVE` (`scripts/data_quality.py`).
  - H3 : les frais sont inclus dans le PnL ferme (`total_fees_usd` existe dans
    `paper_trading/ledger.py:191`). A CONFIRMER AU DEMARRAGE DU TICKET.
- **Invariants** : I-02, I-05, I-09. Les deux grandeurs ne sont jamais additionnees sous un nom
  unique sans que ce nom soit `pnl_total` explicitement defini.
- **Fichiers** (2) :
  - `core/state/metrics/pnl.py` (nouveau)
  - `tests/state/test_metrics_pnl.py` (nouveau)
- **Pseudo-code** :

```text
MODULE metrics.pnl (FONCTIONS PURES)

    FONCTION pnl_ouvert(positions_ouvertes, prix_courants) -> nombre
        POUR CHAQUE position
            SI prix courant MANQUANT
                ALORS EXCLURE la position ET COMPTER une exclusion
            SINON accumuler la variation signee selon le sens
        RENVOYER (somme, nombre_d_exclusions)      # l exclusion est visible, jamais silencieuse

    FONCTION pnl_ferme(trades_clotures_epoque) -> nombre
        RENVOYER la somme des resultats nets, frais inclus

    FONCTION pnl_total(pnl_ouvert, pnl_ferme) -> nombre
        RENVOYER pnl_ouvert + pnl_ferme
        # NOTE : total n est JAMAIS une recopie de l ouvert (cf. portfolio_api.py:30)

REGLE : la population des trades clotures est filtree par la borne d epoque canonique
REGLE : aucune valeur par defaut ne remplace un prix manquant
```

- **Plan d action** :
  1. Relever les 4 calculs de PnL ouvert et les 2 de PnL ferme identifies par l audit.
  2. Fixer les definitions, dont le traitement des frais et des prix manquants.
  3. Ecrire les projections pures avec remontee explicite des exclusions.
  4. Ecrire les tests, dont un test qui echoue si `pnl_total` egale `pnl_ouvert` alors que
     `pnl_ferme` est non nul.
- **Ordre exact** :
  1. Tableau des definitions rivales de PnL.
  2. Creation de `core/state/metrics/pnl.py`.
  3. Creation de `tests/state/test_metrics_pnl.py`.
  4. `python -m pytest tests/state -q`.
  5. `python -m pytest tests/ -q`.
  6. Commit unique `SSOT-013`.
- **Tests** :
  - LONG gagnant, LONG perdant, SHORT gagnant, SHORT perdant : signes corrects.
  - Prix courant manquant : position exclue, compteur d exclusions = 1, aucune valeur inventee.
  - `pnl_ferme` filtre par borne d epoque : un trade anterieur a la borne est exclu.
  - `pnl_total` != `pnl_ouvert` des que `pnl_ferme` est non nul (test anti-regression
    de `portfolio_api.py:30`).
- **Validation** : `python -m pytest tests/state -q` sans echec ; module non cable a ce stade.
- **Rollback** : `git revert` du commit `SSOT-013`.
- **Risques** : double comptage des frais (deja deduits en amont). Mitigation : test explicite
  sur un trade a frais connus.
- **Temps estime** : 1 j.
- **Dependances** : SSOT-001, SSOT-012.
- **Criteres Done** :
  - `python -m pytest tests/state/test_metrics_pnl.py -q` => `0 failed`.
  - Le test anti-regression `pnl_total != pnl_ouvert` passe.
  - Diff <= 300 lignes et <= 2 fichiers.
- **Criteres Refus** :
  - Un prix manquant est remplace par une valeur par defaut.
  - `pnl_ferme` n est pas filtre par la borne d epoque canonique.
  - Le module lit un fichier ou une base directement.

---

### SSOT-014 — Couche de metriques canonique : win_rate et drawdown

**GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE**
Precondition de deblocage : checkpoint L2 franchi + N >= 100 sur l epoque courante + ADR d epoque
signe par l operateur.

- **ID** : SSOT-014
- **Titre** : `analysis/base.py` designe lignee canonique ; les autres lignees deviennent
  consommatrices.
- **Objectif** : une seule definition de `win_rate` et de `max_drawdown`, celle utilisee par
  les tests d hypotheses, consommee par l exploitation.
- **Pourquoi** : audit SSoT : environ 5 calculs de `win_rate` et 5 de `drawdown`. Une metrique
  scientifique qui differe de la metrique affichee rend tout dossier Go/No-Go contestable.
- **Diagnostic resume** :
  `analysis/base.py:88` (`win_rate`) et `analysis/base.py:125` (`max_drawdown`) constituent la
  lignee scientifique (tests H1-H6). `certification/operator_signoff.py:46` (`paper_max_dd`,
  `paper_win_rate`) est une quatrieme lignee. `paper_trading/ledger.py:191` (`summary()`) produit
  `win_rate` et `max_drawdown_pct`. `visualization/api/portfolio_api.py:22-29` fige
  `win_rate_pct = 0.0` et `max_drawdown_pct = 0.0`. Le present ticket designe la lignee
  scientifique comme canonique et branche les autres dessus, sans changer les valeurs
  scientifiques.
- **Contexte** : les valeurs produites par `analysis/base.py` alimentent les verdicts H1-H6 ;
  toute modification de ces fonctions est interdite dans ce ticket.
- **Hypotheses** :
  - H1 : `analysis/base.py:88` et `:125` sont deja des fonctions pures prenant une population
    de trades en entree. A CONFIRMER AU DEMARRAGE DU TICKET.
  - H2 : `certification/operator_signoff.py:46` et `paper_trading/ledger.py:191` peuvent
    appeler ces fonctions sans changer leur sortie actuelle. Si la sortie change, l ecart est
    mesure et documente, et l arbitrage revient a l operateur.
- **Invariants** : I-02, I-08, I-09. `analysis/base.py` n est pas modifie fonctionnellement.
- **Fichiers** (3) :
  - `core/state/metrics/performance.py` (nouveau ; facade qui delegue a `analysis/base.py`)
  - `certification/operator_signoff.py` (branchement sur la facade)
  - `tests/state/test_metrics_performance.py` (nouveau)
- **Pseudo-code** :

```text
MODULE metrics.performance (FACADE, AUCUNE FORMULE NOUVELLE)

    FONCTION win_rate(trades_epoque) -> nombre
        DELEGUER a analysis/base.py:88          # lignee scientifique, non reimplementee

    FONCTION max_drawdown(courbe_equity) -> nombre
        DELEGUER a analysis/base.py:125

    FONCTION resume_performance(trades_epoque, courbe_equity) -> STRUCTURE
        RENVOYER { win_rate, max_drawdown, n_trades, n_winners, n_losers }

DANS certification/operator_signoff.py
    REMPLACER le calcul local de paper_win_rate ET paper_max_dd (ligne 46)
    PAR un appel a la facade
    SI l ecart avec l ancienne valeur est non nul
        ALORS le JOURNALISER et SUSPENDRE la partie concernee, ne pas ecraser silencieusement

REGLE : aucune formule statistique n est reecrite ici
REGLE : la population de trades est bornee par CLEAN_DATA_SINCE_ACTIVE
```

- **Plan d action** :
  1. Verifier la purete et les signatures de `analysis/base.py:88` et `:125`.
  2. Ecrire la facade de delegation, sans nouvelle formule.
  3. Brancher `certification/operator_signoff.py:46` sur la facade, avec mesure d ecart.
  4. Laisser `paper_trading/ledger.py:191` et l API pour SSOT-015 et PHASE_03 (atomicite).
  5. Ecrire les tests, dont un test d equivalence avec les valeurs actuelles.
- **Ordre exact** :
  1. Lecture de `analysis/base.py` (`:88`, `:125`).
  2. Creation de `core/state/metrics/performance.py`.
  3. Modification de `certification/operator_signoff.py`.
  4. Creation de `tests/state/test_metrics_performance.py`.
  5. `python -m pytest tests/state -q`.
  6. `python -m pytest tests/ -q`.
  7. Commit unique `SSOT-014`.
- **Tests** :
  - Equivalence : sur un jeu fige, la facade renvoie exactement les valeurs de `analysis/base.py`.
  - `certification/operator_signoff.py` renvoie les memes valeurs qu avant sur le meme jeu,
    ou l ecart est journalise et le test le documente explicitement.
  - Population vide : `win_rate` non defini plutot que 0.0 (une absence de donnee n est pas
    une performance nulle). Comportement exact attendu :
    A CONFIRMER AU DEMARRAGE DU TICKET (aligner sur `analysis/base.py`).
  - Borne d epoque appliquee.
- **Validation** : `python -m pytest tests/ -q` sans echec nouveau ; ecart documente s il existe.
- **Rollback** : `git revert` du commit `SSOT-014`.
- **Risques** : R6 (divergence scientifique / exploitation). Mitigation : delegation stricte,
  aucune reimplementation.
- **Temps estime** : 1 j.
- **Dependances** : SSOT-013.
- **Criteres Done** :
  - `python -m pytest tests/state/test_metrics_performance.py -q` => `0 failed`.
  - `certification/operator_signoff.py` ne contient plus de formule locale de `win_rate`
    ou de `max_drawdown`.
  - `analysis/base.py` n apparait pas dans le diff, sauf commentaire de designation.
  - Diff <= 300 lignes et <= 3 fichiers.
- **Criteres Refus** :
  - Une formule statistique est reecrite dans la facade.
  - `analysis/base.py` est modifie fonctionnellement.
  - Un ecart avec les valeurs actuelles est ecrase sans journalisation.
  - Une population vide produit `0.0` sans que ce soit le comportement de la lignee canonique.

---

<!-- SUITE_TICKETS -->
