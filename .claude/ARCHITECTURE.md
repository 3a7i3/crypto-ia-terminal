# ARCHITECTURE.md — Architecture reelle de crypto_ai_terminal

> **Statut** : document de reference descriptif. Il decrit le systeme **tel qu'il est**,
> pas tel qu'il devrait etre. Il ne contient aucune prescription de correctif executable.
> **Portee** : pipeline de decision + chaine d'affichage + chaine scientifique, mode **paper**.
> **Base factuelle** : diagnostic valide par inspection directe du code (voir `.claude/README.md`).
> **Date de la photographie** : 2026-07-25. Depot : `C:/Users/WINDOWS/crypto_ai_terminal`.
> **Convention epistemique** (protocole v3, `docs/protocole_audit_epistemique.md`) :
> chaque affirmation est marquee `[O]` Observation (lue dans le code, verifiable a la ligne citee),
> `[I]` Inference (deduite d'observations), `[H]` Hypothese (non verifiee).
> Toute information absente du diagnostic est marquee **A CONFIRMER AU DEMARRAGE DU TICKET**.

---

## 0. Resume executif en 10 lignes

1. `[O]` Le systeme possede **quatre stores de positions** distincts et non reconcilies.
2. `[O]` En mode paper, la verite des positions ouvertes vit dans `_virtual_portfolio` (MexcSimulator).
3. `[O]` `PositionManager` est **vide** en mode paper : rien ne l'alimente sur le chemin paper.
4. `[O]` `advisor_loop.py:6786` passe `pos_manager.get_open()` a `portfolio_brain.portfolio_health()`.
5. `[I]` Consequence : exposure, free_cash et n_positions cote PortfolioBrain sont calcules sur une liste vide.
6. `[O]` Le meme panneau Telegram affiche donc `Positions: 3` et `Portfolio Exposure: 0.0%`.
7. `[O]` Le bug est **documente et gele volontairement** (docstring `advisor_loop.py:437-448`).
8. `[O]` Audit SSoT : **0 PASS / 1 WARNING / 8 FAIL** sur 9 metriques affichees.
9. `[I]` Deux lignees coexistent : lignee d'**affichage** (memoire, live) et lignee **scientifique** (`paper_trades.jsonl`).
10. `[I]` Les corriger n'est pas le meme geste : la premiere est neutre pour N, la seconde ne l'est pas.

---

## 1. Vue d'ensemble : le pipeline de decision

### 1.1 La chaine telle qu'elle apparait dans le panneau Telegram

```
   Scanner                 (univers de paires, epingle a 135 symboles — epoque V4)
      |
      v
   Feature Engine          (indicateurs, contexte marche, regime)
      |
      v
   AI Scoring              (score de packet, personnalites, meta-strategie)
      |
      v
   Portfolio Brain         (contraintes de portefeuille : exposition, correlation, concentration)
      |
      v
   Risk Manager            (gates de risque, SEC-01, consecutive_losses, kill-switch)
      |
      v
   Execution               (sizing, ordre)
      |
      v
   Exchange                (MEXC reel OU MexcSimulator en mode paper)
      |
      v
   Telegram                (rendu du panneau : CYCLE, HEARTBEAT, POSITIONS, SHADOW STATS)
```

`[O]` Cette sequence est la representation affichee dans le panneau.
`[I]` Elle decrit correctement l'ordre des etapes de **decision**.
`[I]` Elle ne decrit **pas** le flux de **donnees d'etat** : le panneau agrege, en un seul rendu,
des valeurs produites par des sous-systemes qui ne partagent aucun store commun (voir §2 et §5).

> **Point critique a retenir** : la fleche `Portfolio Brain` du schema ci-dessus recouvre en realite
> **deux usages disjoints** du meme objet :
> - un usage **decisionnel** (contraintes appliquees a une entree candidate) ;
> - un usage **d'affichage** (`portfolio_health()` appele a la construction du snapshot, `advisor_loop.py:6785-6787`).
> `[O]` Les deux usages lisent `pos_manager`. `[O]` `pos_manager` est vide en mode paper.

### 1.2 Modules pivots

| Role | Fichier | Reperes |
|---|---|---|
| Boucle principale, orchestrateur, rendu | `core/advisor_loop.py` | 7776 lignes |
| Contraintes de portefeuille (canonique en usage) | `quant_hedge_ai/agents/risk/portfolio_brain.py` | `PortfolioBrain:75` |
| Simulateur d'exchange paper | `paper_trading/mexc_simulator.py` | `MexcSimulator:230` |
| Ledger paper | `paper_trading/ledger.py` | `PaperLedger:121`, `summary():191` |
| Modele de snapshot d'affichage | `observability/system_snapshot.py` | `PortfolioSnapshot:56`, `SystemSnapshot:132`, `to_dict:143` |
| Lignee scientifique | `scripts/data_quality.py`, `tools/cri_calculator.py` | `CLEAN_DATA_SINCE_ACTIVE`, `load_clean_trades()` |

### 1.3 Points d'ancrage dans `core/advisor_loop.py`

| Zone | Lignes | Contenu |
|---|---|---|
| `_display_position_summary` | 434-459 | Compte les positions pour l'affichage ; source primaire = `_virtual_portfolio` (450-453) ; fallback `pb_health` (456-459) |
| Docstring de gel | 437-448 | Declare explicitement que le bug est connu, gele, et corrigeable seulement a la calibration |
| Regression historique | 462-471 | Incident 2026-07-12 21:00 UTC : `POSITIONS 0` affiche alors que le ledger MexcSim portait 3 positions BTC/BNB/ETH |
| `_positions_for_display` | 462+ | Selection de la liste affichee |
| `place_market_order` (ouverture paper) | 2176 | Ecrit dans `_virtual_portfolio` |
| `_register_position_from_execution` | 3859-3883 | `pos_manager.add_position` en 3883 ; ecriture `databases/positions_snapshot.json` en 3888+ |
| **Appel divergent** | **6785-6787** | **`portfolio_brain.portfolio_health(pos_manager.get_open())`** |
| Appel d'affichage | 6788 | `_display_position_summary(_virtual_portfolio, pb_health)` |
| Calculs derives | 6791-6799 | `_deployed_notional`, `_paper_equity`, `_paper_cash` |
| Construction `PortfolioSnapshot` (CYCLE) | 6888-6906 | |
| Bloc `POSITIONS:` | 6971-6989 | Condition d'affichage : `open_count > 0` |
| `SHADOW STATS` | 6992-6999 | |
| Construction snapshot (HEARTBEAT) | 7444-7482 | Deuxieme constructeur, chemin distinct du CYCLE |

`[I]` Il existe **deux constructeurs de snapshot** (CYCLE 6788-6906, HEARTBEAT 7444-7482).
`[H]` Ils peuvent diverger entre eux — **A CONFIRMER AU DEMARRAGE DU TICKET** : verifier si HEARTBEAT
reproduit le meme appel `portfolio_health(pos_manager.get_open())` ou une variante.

---

## 2. Cartographie des donnees affichees

Legende des colonnes :
- **Source primaire** : d'ou vient physiquement le fait (store, fichier, constante).
- **Producteur** : le composant qui materialise la valeur.
- **Transformateur** : ce qui la derive, l'agrege ou la recopie.
- **Consommateur** : ou elle apparait.
- **Verdict SSoT** : resultat de l'audit Single Source of Truth (0 PASS / 1 WARNING / 8 FAIL).

| Metrique | Source primaire | Producteur | Transformateur | Consommateur | Verdict SSoT |
|---|---|---|---|---|---|
| **capital** | `WALLET_PAPER_CAPITAL` (constante epinglee) | config / `PortfolioBrain._capital` | 5 recalculs independants (advisor, portfolio_brain, ledger `summary():191`, `visualization/api/portfolio_api.py:33`, `system/integrity_snapshot.py:100-135`) | Panneau Telegram, REST, snapshot | **FAIL** (5 recalculs) |
| **equity** | `_virtual_portfolio` + prix courants | `advisor_loop.py:6791-6799` (`_paper_equity`) | 5 chaines de derivation concurrentes | `PortfolioSnapshot.paper_equity` (6888-6906), REST `capital_usd` (portfolio_api:33) | **FAIL** (5) |
| **cash** | ambigu | `advisor_loop.py:6791-6799` (`_paper_cash`) vs `PortfolioBrain` | 2 definitions rivales : `capital - notional_deploye` vs `capital*0.40 - exposure` | `PortfolioSnapshot.paper_cash` | **FAIL** (2 definitions rivales) |
| **free_cash** | `PortfolioBrain._capital` et liste de positions | `portfolio_health()` (`portfolio_brain.py:645-664`) : `max(0, capital * MAX_TOTAL_EXPOSURE_PCT - total_exposure_usd)`, `MAX_TOTAL_EXPOSURE_PCT = 0.40` (ligne 88) | aucun | `PortfolioSnapshot.free_cash` | **WARNING** (producteur unique, mais co-affiche avec `paper_cash` contradictoire) |
| **positions (n_open)** | `_virtual_portfolio` (MexcSimulator) | `get_open_positions_summary()` (advisor:450-453) | fallback vers `pb_health` si `None` (456-459) | Ligne `Positions: N`, bloc `POSITIONS:` (6971-6989) | **FAIL** (4 stores) |
| **exposure** | `pos_manager.get_open()` — **liste vide en paper** | `portfolio_brain._snapshot()` (668-687) : `total_exposure_usd += p.size_usd`, `total_exposure_pct = total_exposure_usd / self._capital` | 3 lignees (`portfolio_brain`, `advisor` `_deployed_notional`, `system/integrity_snapshot.py:100-135`) | `Portfolio Exposure: 0.0%` | **FAIL** (3) |
| **PnL ouvert** | `_virtual_portfolio` + prix marche | MexcSimulator | 4 chemins de calcul | `PortfolioSnapshot.open_pnl_usd` ; REST `portfolio_api:30` le recopie dans `total_pnl_usd` | **FAIL** (4 open) |
| **PnL ferme** | `paper_trades.jsonl` (evenements `CLOSE`) | `mexc_simulator.py`, `paper_trading/recorder.py` | 2 chemins (`PaperLedger.summary():191` ; agregation advisor / session) | `session_pnl_usd`, rapports | **FAIL** (2 closed) |
| **win_rate** | `paper_trades.jsonl` (lignee scientifique) OU ledger memoire (lignee affichage) | `PaperLedger.summary():191` / `analysis/base.py:88` | ~5 implementations (`analysis/base.py:88`, `ledger.py:191`, `certification/operator_signoff.py:46`, `visualization/api/portfolio_api.py:24-29` **hardcode a 0.0**, advisor) | Panneau, REST, rapports scientifiques | **FAIL** (~5) |
| **drawdown** | serie d'equity | `analysis/base.py:125` `max_drawdown()` / `ledger.py:191` `max_drawdown_pct` | ~5 implementations (dont `certification/operator_signoff.py:46` `paper_max_dd`, REST hardcode `max_drawdown_pct=0.0`) | Panneau, REST, certification | **FAIL** (~5) |

### 2.1 Preuves numeriques de la divergence

`[O]` **Preuve 1** : `free_cash = 269.79` affiche. Or `269.79 = 674.47 * 0.40 - 0`.
Donc `total_exposure_usd = 0` dans `portfolio_health()`, alors que 3 positions sont ouvertes.

`[O]` **Preuve 2** : le bloc `POSITIONS:` est **absent** des rapports. Sa condition d'affichage est
`open_count > 0` (`advisor_loop.py:6971`). `[I]` Donc le compteur utilise a cet endroit provient de
`pos_manager`, qui est vide — alors que la ligne `Positions: 3` du meme panneau provient de `_virtual_portfolio`.

### 2.2 La couche REST est un cas a part

`[O]` `visualization/api/portfolio_api.py` :
- lignes 22-29 : `n_trades=0`, `n_wins=0`, `n_losses=0`, `win_rate_pct=0.0`, `profit_factor=0.0`,
  `expectancy_pct=0.0`, `max_drawdown_pct=0.0`, `sharpe=0.0` sont **codes en dur** ;
- ligne 30 : `total_pnl_usd = open_pnl_usd` — le PnL **ouvert** est recopie dans le PnL **total** ;
- ligne 33 : `capital_usd = portfolio.paper_equity` — equity presentee comme capital ;
- ligne 34 : `trade_history = []`.

`[I]` Toute lecture de l'API REST comme source de verite metrique est invalide par construction.
`[I]` Cette couche n'est pas une divergence de calcul : c'est une absence de calcul.

---

## 3. Les quatre stores de positions

### 3.1 Inventaire

| # | Store | Localisation | Alimente par | Contenu en mode paper | Role reel |
|---|---|---|---|---|---|
| 1 | `PaperLedger._open` | `paper_trading/ledger.py:121` | ouverture/cloture paper | positions du ledger | Historique + `summary():191` (n_trades, capital, win_rate, max_drawdown_pct, total_fees_usd) |
| 2 | `PositionManager` | via `advisor_loop._register_position_from_execution:3859-3883` (`add_position:3883`) | chemin d'**execution reelle** uniquement | **VIDE** | Source des **contraintes de decision** (exposition, max_positions) |
| 3 | `_virtual_portfolio` | `MexcSimulator` (`paper_trading/mexc_simulator.py:230`), ecrit par `place_market_order` (advisor:2176) | ouverture paper | **3 positions** (etat de reference) | **Verite des positions ouvertes en mode paper** |
| 4 | `WalletSync` | compte reel, lecture seule | API exchange | soldes reels multi-exchange | Observation du compte reel, hors perimetre paper |

### 3.2 Lequel contient la verite en mode paper

`[O]` En mode paper, une entree est materialisee par `place_market_order` (`advisor_loop.py:2176`),
qui ecrit dans `_virtual_portfolio` (MexcSimulator).
`[O]` `pos_manager.add_position` n'est appele que depuis `_register_position_from_execution` (3883),
sur le chemin d'execution.
`[I]` **`_virtual_portfolio` est la seule source de verite des positions ouvertes en mode paper.**
`[I]` `PaperLedger._open` est une vue derivee/parallele du meme evenement ; sa coherence avec
`_virtual_portfolio` **A CONFIRMER AU DEMARRAGE DU TICKET**.
`[I]` `PositionManager` est structurellement vide en paper ; toute metrique qui en derive vaut zero.
`[O]` `WalletSync` est en lecture seule sur le compte reel : il ne participe ni a la decision paper ni au N.

### 3.3 Pourquoi ils divergent

`[I]` Ils divergent parce qu'il n'existe **aucun ecrivain commun** : chaque store a son propre point
d'entree, sur un chemin de code distinct (paper vs execution reelle vs API exchange).
`[I]` Aucune reconciliation n'est effectuee entre eux au cours d'un cycle.
`[I]` La divergence est donc **permanente et deterministe**, pas intermittente.

### 3.4 Pourquoi elle n'est pas corrigee

`[O]` Docstring `advisor_loop.py:437-448` :
> `pos_manager` reste la source des contraintes de decision, n'est jamais modifie ici ;
> corriger son entree changerait le comportement de decision en pleine validation scientifique.
> Ce bug est documente, gele, a corriger a la calibration.

`[I]` Alimenter `pos_manager` en mode paper modifierait l'**entree de decision** (exposition,
`max_positions`, sizing). `[I]` Cela constituerait un **changement d'epoque** au sens ADR-0017,
donc un **reset de N a zero** et la destruction du burn-in en cours.

---

## 4. Duplications de classes

### 4.1 `PortfolioSnapshot` — 3 definitions

| Chemin | Ligne | Usage |
|---|---|---|
| `observability/system_snapshot.py` | 56 | Modele d'affichage (champs : `paper_equity`, `paper_cash`, `free_cash`, `portfolio_exposure_pct`, `open_pnl_usd`, `open_positions`, `correlation_risk_pct`, `session_pnl_usd`) |
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | 64 | Snapshot interne de PortfolioBrain, produit par `_snapshot()` (668-687) |
| `visualization/api/models.py` | 69 | Modele d'API REST |

`[I]` Trois modeles homonymes, trois jeux de champs, aucun contrat commun.
`[I]` Un lecteur qui voit `PortfolioSnapshot` dans un import ne peut pas savoir lequel sans lire le chemin.

### 4.2 `PortfolioBrain` — 2 definitions

| Chemin | Ligne | Statut |
|---|---|---|
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | 75 | Utilise par `advisor_loop.py:6785-6787` |
| `quant_hedge_ai/agents/portfolio/__init__.py` | 71 | Second implementation ; usage **A CONFIRMER AU DEMARRAGE DU TICKET** |

### 4.3 `SystemSnapshot` — 2 definitions

| Chemin | Ligne | Usage |
|---|---|---|
| `observability/system_snapshot.py` | 132 | Snapshot d'affichage, `to_dict:143` |
| `infra/monitoring/daily_analyzer.py` | 19 | Snapshot d'analyse quotidienne |

### 4.4 Lignees de calcul metrique concurrentes

| Lignee | Chemin | Perimetre |
|---|---|---|
| Affichage live | `core/advisor_loop.py` (6788-6906, 7444-7482) | Panneau Telegram |
| PortfolioBrain | `quant_hedge_ai/agents/risk/portfolio_brain.py` (645-687) | Contraintes + `pb_health` |
| Integrite | `system/integrity_snapshot.py:100-135` | Recalcule `pb_free` / `pb_exposure` / `pb_n` via `pos_manager` (**3e lignee**) |
| Scientifique | `analysis/base.py:88` (`win_rate`), `:125` (`max_drawdown`) | Tests H1-H6 |
| Certification | `certification/operator_signoff.py:46` (`paper_max_dd`, `paper_win_rate`) | **4e lignee** |
| REST | `visualization/api/portfolio_api.py:22-34` | Valeurs codees en dur |

`[I]` Six producteurs pour le meme vocabulaire metrique. `[I]` C'est la cause structurelle du verdict `0 PASS`.

---

## 5. Diagramme du flux et point de divergence

```
==================================  PRIMAIRES  ==================================

 [P1] _virtual_portfolio            [P2] pos_manager            [P3] PaperLedger._open
      (MexcSimulator:230)                (PositionManager)           (ledger.py:121)
      ecrit par                          ecrit par                   ecrit a l'ouverture
      place_market_order                 _register_position_         et a la cloture paper
      advisor:2176                       from_execution:3883
      ---> 3 positions                   ---> VIDE en paper          ---> historique
                                         (chemin execution reelle)

 [P4] WalletSync (compte reel, lecture seule — hors perimetre paper)

 [P5] paper_trades.jsonl  (fichier ; ecrivains : mexc_simulator.py + paper_trading/recorder.py)


===============================  AGREGATEURS  ==================================

           |                                  |
           |                                  |
           |                    +-------------+-----------------------+
           |                    |                                     |
           |                    v                                     v
           |        portfolio_brain.portfolio_health()      system/integrity_snapshot.py
           |        (portfolio_brain.py:645-664)            :100-135  (pb_free/pb_exposure/pb_n)
           |          <- _snapshot() 668-687                  <- lit AUSSI pos_manager
           |             total_exposure_usd += p.size_usd
           |             total_exposure_pct = expo/_capital
           |             free_capital = max(0,
           |                 capital*0.40 - total_exposure_usd)
           |
           |                    ^
           |                    |
           |     ############################################################
           |     #  POINT DE DIVERGENCE : advisor_loop.py:6786              #
           |     #                                                          #
           |     #  portfolio_brain.portfolio_health( pos_manager.get_open() )
           |     #                                    ^^^^^^^^^^^^^^^^^^^^^  #
           |     #  MAUVAIS STORE : liste VIDE en mode paper.               #
           |     #  Tout ce qui descend de cette fleche vaut 0.             #
           |     ############################################################
           |
           v
  _display_position_summary(_virtual_portfolio, pb_health)   <- advisor:6788
      advisor:450-453  n_open <- _virtual_portfolio.get_open_positions_summary()
      advisor:456-459  fallback pb_health si None
           |
           |     _deployed_notional / _paper_equity / _paper_cash   <- advisor:6791-6799
           |
           v

=================================  SNAPSHOT  ===================================

    PortfolioSnapshot  (observability/system_snapshot.py:56)
    construit en advisor:6888-6906 (CYCLE)  |  advisor:7444-7482 (HEARTBEAT)
      paper_equity ......... <- P1 (via _paper_equity)
      paper_cash ........... <- P1 (via _paper_cash)
      free_cash ............ <- P2 (via portfolio_health)   <-- INCOHERENT
      portfolio_exposure_pct <- P2 (via portfolio_health)   <-- INCOHERENT
      open_positions ....... <- P1                          <-- COHERENT
      open_pnl_usd ......... <- P1
      session_pnl_usd ...... <- P5 / agregation session
      correlation_risk_pct . <- portfolio_health
           |
           v
    SystemSnapshot (observability/system_snapshot.py:132) --> to_dict:143


==================================  RENDU  =====================================

    Panneau Telegram
      "Positions: 3"              <- P1  (_virtual_portfolio)
      "Portfolio Exposure: 0.0%"  <- P2  (pos_manager, vide)   <-- CONTRADICTION VISIBLE
      "free_cash: 269.79"         = 674.47 * 0.40 - 0          <-- PREUVE NUMERIQUE
      bloc "POSITIONS:"           condition open_count>0 (advisor:6971) -> ABSENT
      "SHADOW STATS"              advisor:6992-6999

    REST /portfolio (visualization/api/portfolio_api.py)
      lignes 22-29 : metriques CODEES EN DUR a 0
      ligne 30     : total_pnl_usd = open_pnl_usd
      ligne 33     : capital_usd = paper_equity
      ligne 34     : trade_history = []
```

`[I]` **Lecture du diagramme** : un seul panneau, deux ancetres primaires (`P1` et `P2`) qui ne sont
jamais reconcilies. La contradiction n'est pas un bug de rendu : elle est injectee en amont,
a l'unique ligne `advisor_loop.py:6786`.

---

## 6. Les deux lignees disjointes

### 6.1 Lignee d'affichage (live, en memoire)

```
_virtual_portfolio / pos_manager --> portfolio_health / _paper_* --> PortfolioSnapshot --> Telegram / REST
```

- `[O]` Vit en memoire du processus `advisor_loop`.
- `[O]` Reconstruite a chaque cycle et a chaque heartbeat.
- `[I]` Perdue au redemarrage (hors etats persistes, §7).
- `[I]` Sa fonction est **operationnelle** : dire a l'operateur ce qui se passe maintenant.
- `[I]` Ses defauts (8 FAIL) degradent la **confiance operateur**, pas la validite du dataset.

### 6.2 Lignee scientifique (fichier, historisee)

```
paper_trades.jsonl --> scripts/data_quality.py (CLEAN_DATA_SINCE_ACTIVE) --> tools/cri_calculator.py::load_clean_trades() --> CRI, N, gates H1-H6
```

- `[O]` Ecrivains de `paper_trades.jsonl` : `paper_trading/mexc_simulator.py` et `paper_trading/recorder.py`.
- `[O]` Borne d'epoque canonique : `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`, alias `CLEAN_DATA_SINCE_ACTIVE`.
- `[O]` La borne est definie dans `scripts/data_quality.py` et importee, **jamais recopiee localement**.
- `[I]` Sa fonction est **probatoire** : constituer N, calculer le CRI, arbitrer Go/No-Go.

### 6.3 Pourquoi il ne faut jamais les confondre

| Critere | Lignee d'affichage | Lignee scientifique |
|---|---|---|
| Support | memoire du process | fichier append-only |
| Duree de vie | un cycle | l'epoque entiere |
| Filtre d'epoque | aucun | `CLEAN_DATA_SINCE_ACTIVE` obligatoire |
| Impact d'un correctif | **neutre pour N** si l'entree de decision est intacte | change N ou sa definition |
| Autorite | aucune | seule autorite pour Go/No-Go |

`[I]` **Regle de lecture** : un chiffre lu dans le panneau Telegram ne prouve rien sur l'etat scientifique.
`[I]` Reciproquement, un CRI correct ne garantit rien sur la coherence du panneau.
`[O]` Precedent documente : l'ancien `regret_analysis.jsonl` etait **mort depuis le 10/07** alors que le
CRI le lisait encore, produisant un faux zero — corrige par ADR-0018 (source canonique = `regret_horizons` v2).
`[I]` Le mode de defaillance dangereux n'est pas « le panneau ment » mais « une metrique probatoire lit un
producteur mort ». C'est la lignee scientifique qui exige un contrat de mesure, pas l'affichage.

### 6.4 Consequence de gating

`[I]` Un correctif qui reste **entierement dans la lignee d'affichage** ne modifie aucune entree de decision,
donc ne cree pas d'epoque, donc **ne reinitialise pas N**.
`[I]` Un correctif qui touche `PositionManager`, `check_new_trade`, le sizing, le risk, ou `PortfolioBrain`
**en entree de decision** cree une epoque : `GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE`.

---

## 7. Etats persistes et caches

| Etat | Nature | Producteur | Role | Risque connu |
|---|---|---|---|---|
| `paper_trades.jsonl` | fichier append-only | `mexc_simulator.py`, `paper_trading/recorder.py` | Dataset scientifique ; base de N et du CRI | Deux ecrivains pour un fichier probatoire — invariant single-writer **A CONFIRMER AU DEMARRAGE DU TICKET** |
| `SystemSnapshot` persiste | fichier | `observability/system_snapshot.py` (`to_dict:143`) | Rendu differe, dashboards « snapshot-only » | Herite des 8 FAIL de la lignee d'affichage |
| `databases/positions_snapshot.json` | fichier | `advisor_loop.py:3888+` (apres `pos_manager.add_position:3883`) | Persistance du store `PositionManager` | `[I]` Vide ou stale en mode paper, puisque son producteur ne s'execute pas sur le chemin paper |
| `warmup_state.json` | fichier **signe** | machine a etats de warmup | Empeche un redemarrage de reinitialiser l'etat de chauffe | Signature a valider avant toute lecture |
| `startup_cache` | cache | pile d'optimisation (boot) | Acceleration du boot | `[I]` Peut re-servir un etat anterieur au dernier deploiement |
| `_snapshot_provider` | reference en memoire | `advisor_loop` | Fournit le snapshot au rendu | `[I]` Point d'injection unique : ce qui est faux ici est faux partout en aval |
| `_snapshot_block_stats` | agregat en memoire | `advisor_loop` | Statistiques de blocage par couche (`BLOCK STATS`) | Non persiste ; perdu au restart |
| `watchdog._components` | registre en memoire | `crypto-watchdog` | Sante des composants | `[I]` Un composant absent du registre n'est pas surveille |
| `pending_spool.json` | fichier atomique | `RegretScheduler` | File des horizons de regret ; rechargee au boot | Deploye et verifie le 22/07 ; les restarts ne perdent plus la file |

`[I]` **Regle** : un fichier local `databases/*.jsonl` ou `*.json` sur le poste de developpement
n'est **jamais** une preuve de l'etat runtime du VPS (piege documente 2026-07-08).
`[O]` VPS de reference : `35.240.166.72` (l'ancienne IP `34.171.188.99` est morte).

---

## 8. Les trois architectures cibles

### 8.1 Tableau comparatif

| | **A — Alignement d'affichage** | **B — Store canonique sous flag** | **C — Event sourcing** |
|---|---|---|---|
| Principe | L'affichage (exposure / `paper_cash` / `free_cash`) derive du **meme store** que le compte de positions (`_virtual_portfolio`) | Un store de positions canonique alimente **affichage ET decision**, derriere un feature-flag | `paper_trades.jsonl` devient la source unique ; toutes les metriques deviennent des **projections** |
| Touche `pos_manager` ? | **Non, jamais** | Oui (entree de decision) | Oui (refonte complete) |
| Cout | 1-2 jours | 1-2 semaines | 4-8 semaines |
| Impact sur N | **Aucun reset** | **RESET D EPOQUE, N -> 0** | **RESET D EPOQUE, N -> 0** |
| ADR requis | Non (correctif d'observabilite) | **Oui, ADR d'epoque signe operateur** | **Oui, ADR d'epoque signe operateur** |
| Compatibilite gel | **COMPATIBLE** (Scientific Debt Rule : outil de mesure/audit) | **GATED** | **GATED** |
| Resout les 8 FAIL ? | Partiellement : supprime la contradiction visible du panneau | Largement | Structurellement |
| Statut | **Executable immediatement** | Bloque | Bloque |

### 8.2 Precondition de deblocage de B et C

`[O]` Tout ticket touchant `PositionManager`, `check_new_trade`, le sizing, le risk, ou `PortfolioBrain`
**en entree de decision** doit porter le marquage :

```
GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE
```

`[O]` Conditions cumulatives de deblocage :
1. checkpoint **L2 franchi** ;
2. **N >= 100** atteint sur l'epoque courante (N de session ~ 32 trades fermes au moment du diagnostic) ;
3. **ADR d'epoque signe** par l'operateur (numeros libres a partir de **ADR-0019**).

`[I]` Ces tickets ne doivent **jamais** etre presentes comme executables immediatement, meme si leur
implementation technique est triviale. `[O]` Discipline operateur en vigueur : « zero nouvelle construction avant N ~ 100 ».

### 8.3 Pourquoi A n'est pas une demi-mesure

`[I]` A ne « masque » pas le bug : elle supprime la **contradiction interne au panneau** en faisant
descendre l'affichage d'un seul ancetre (`_virtual_portfolio`).
`[I]` Le bug de decision (`pos_manager` vide alimente les contraintes) reste entier, documente et gele —
c'est precisement ce que le gel scientifique exige.
`[I]` A rend donc le systeme **honnete sur ce qu'il montre** sans le rendre **different sur ce qu'il decide**.

---

## 9. Contraintes de gouvernance applicables a toute evolution

| Regle | Enonce operationnel |
|---|---|
| ADR-0007 | Passivite absolue des observers. Un composant d'observabilite n'influence jamais une decision en temps reel. |
| Scientific Debt Rule | Gel architectural. Seuls outils de mesure, d'audit, de visualisation et de reproductibilite sont autorises. |
| Regle du statisticien | Avant toute calibration : 500 trades / 150 W / 150 L / 100 MISSED_WIN / 100 GOOD_REFUSAL / 50 par regime / 30 par couche bloqueuse / CRI >= 90. |
| Borne d'epoque | `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`, importee depuis `scripts/data_quality.py`, jamais recopiee. |
| ADR-0017 | Changer l'entree de decision = changer d'epoque = reset de N. |
| Auto-calibration | `FEATURE_AUTO_CALIBRATION=false` permanent. Sizing epingle a `WALLET_PAPER_CAPITAL`. |
| Deploiement | `bash scripts/deploy_vps.sh --confirm [--yes] [--restart]`. Jamais automatique. Tag `deploy-YYYYMMDD-HHMM` apres succes. |
| Atomicite des tickets | Max 300 lignes modifiees **ou** max 4 fichiers (la plus contraignante des deux). Un ticket = un commit = revertable. |

---

## 10. Surface de test existante a considerer

`[O]` Tests susceptibles d'etre impactes par toute intervention sur la chaine d'affichage :

| Fichier | Lignes | Objet |
|---|---|---|
| `tests/test_system_snapshot.py` | 31-36 | Construction et champs du snapshot |
| `tests/test_state_integrity.py` | 51-56, 277-285 | Coherence d'etat |
| `tests/capital_deployment/test_capital_lines.py` | 22-48 | Lignes de capital |
| `tests/visualization/test_snapshot_only_loaders.py` | — | Chargement snapshot-only |

`[I]` Ces tests encodent l'etat **actuel**. `[H]` Certains peuvent verrouiller la valeur `0.0` d'exposure —
**A CONFIRMER AU DEMARRAGE DU TICKET** avant toute modification d'affichage.

---

## 11. Falsificateurs du present document

`[I]` Conformement au protocole d'audit epistemique v3, ce document enonce ses propres conditions de refutation.

**Falsificateur 1 (cartographie)** : si une inspection montre que `pos_manager` est alimente sur le chemin
paper (par un ecrivain autre que `_register_position_from_execution:3883`), alors le §3 est faux et la
divergence decrite au §5 n'a pas la cause indiquee.
**Test** : tracer tous les appelants de `add_position` et verifier qu'aucun n'est atteignable en mode paper.

**Falsificateur 2 (lignees)** : si `paper_trades.jsonl` s'avere alimente par la lignee d'affichage
(et non uniquement par MexcSimulator/recorder), alors la separation du §6 est fausse et un correctif
d'affichage cesserait d'etre neutre pour N.
**Test** : verifier l'ensemble des ecrivains du fichier et l'absence de dependance a `PortfolioSnapshot`.

`[I]` **Dette epistemique** relative a la decision « executer A » : trois points restent non verifies —
(a) coherence `PaperLedger._open` vs `_virtual_portfolio` ; (b) contenu exact du constructeur HEARTBEAT
(7444-7482) ; (c) usage reel de la seconde classe `PortfolioBrain` (`quant_hedge_ai/agents/portfolio/__init__.py:71`).
Aucun de ces trois points ne remet en cause la cause racine ; tous conditionnent le perimetre d'un correctif.

---

## 12. Ce qu'il faut retenir en une page

- `[O]` Le systeme n'a pas un bug d'affichage : il a **une absence de source unique de verite**, mesuree
  a 0 PASS / 1 WARNING / 8 FAIL.
- `[O]` La contradiction visible (`Positions: 3` vs `Exposure: 0.0%`) est injectee en **une seule ligne** :
  `advisor_loop.py:6786`.
- `[I]` En mode paper, la verite est dans `_virtual_portfolio`. `pos_manager` est vide et le restera tant
  que le gel scientifique tient.
- `[O]` Le bug est **connu, documente et gele volontairement** — ce n'est pas un oubli.
- `[I]` La lignee d'affichage et la lignee scientifique sont disjointes : reparer la premiere ne touche
  pas N ; toucher la seconde ou l'entree de decision reinitialise N.
- `[O]` Architecture **A** = compatible avec le gel, executable. Architectures **B** et **C** =
  `GATED / RESET D EPOQUE / N -> 0 / ADR OBLIGATOIRE`.
