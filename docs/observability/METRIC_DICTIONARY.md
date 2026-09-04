# Metric Dictionary

Mission O-01 · Every operator-facing metric needs a documented
definition (mission §18). This dictionary has two parts:

- **Part 1 — Canonical registry (code-backed).** These 32 metrics are
  `MetricDefinition` entries in `observability/operator/domains/*.py`,
  aggregated by `observability/operator/canonical_registry.py`, and
  tested for uniqueness, French labels, and explicit numerator/
  denominator on every percentage (`tests/observability/operator_o01/
  test_registry.py`). This section is generated from that code — it
  cannot drift from it silently.
- **Part 2 — Telegram-observed metrics not yet promoted to the
  registry.** These are metrics the forensic bot inventory
  (`TELEGRAM_BOT_REGISTRY.md`) found currently rendered to operators.
  Where a canonical source is confirmed, the mapping is given; where it
  is not, the entry is marked `SOURCE_UNRESOLVED` per mission §23 rather
  than silently legitimized.

No thresholds are invented: any metric without an evidence-backed
warning/critical threshold carries `NOT_DEFINED` rather than a guessed
number (mission §18).

---

## Part 1 — Canonical registry (32 metrics, code-backed)

### A — SYSTEM HEALTH

#### `system_health.boot_alive` — Processus actif

- **Définition** : Le processus principal du moteur est en cours d'exécution. N'implique pas que les données produites sont scientifiquement valides.
- **Source technique** : `watchdog_vps.py pgrep(core/advisor_loop.py)`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : watchdog poll cadence (watchdog_vps.py)
- **Cadence attendue** : continuous (watchdog loop)
- **Polarité** : higher_is_better
- **Sémantique null** : UNAVAILABLE si le watchdog lui-même est injoignable
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : watchdog_vps.py:56-120; scripts/systemd/crypto-watchdog.service
- **Priorité de présentation** : primary

#### `system_health.health_score` — Score de santé scientifique

- **Définition** : Score composite pondéré (mémoire 25%, fiabilité 25%, connectivité exchange 20%, trading 20%, performance 10%) calculé à partir de MetricsSnapshot.
- **Source technique** : `observability.health_score.HealthScore.compute()`
- **Unité / type** : score_0_100 (score)
- **Fraîcheur (source)** : MetricsSnapshot flush cadence (core/advisor_loop.py:6746-6757)
- **Cadence attendue** : per advisor loop cycle
- **Polarité** : higher_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observability/health_score.py:52-72; core/advisor_loop.py:6749-6750
- **Priorité de présentation** : primary

#### `system_health.exchange_connectivity_healthy` — Connectivité exchange

- **Définition** : L'exchange actif répond aux pings de connectivité du superviseur.
- **Source technique** : `supervision.exchange_monitor.ExchangeMonitor.snapshot().healthy`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : ExchangeMonitor background thread
- **Cadence attendue** : continuous
- **Polarité** : higher_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : supervision/exchange_monitor.py:93-224
- **Priorité de présentation** : primary

#### `system_health.exchange_latency_ms` — Latence exchange

- **Définition** : Latence moyenne observée sur les appels de connectivité vers l'exchange actif.
- **Source technique** : `ExchangeMonitor.snapshot().avg_latency_ms`
- **Unité / type** : ms (duration_ms)
- **Fraîcheur (source)** : ExchangeMonitor background thread
- **Cadence attendue** : continuous
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : supervision/exchange_monitor.py:132-143
- **Priorité de présentation** : secondary


### B — MARKET STATE

#### `market_state.regime` — Régime de marché

- **Définition** : Régime de marché courant, stabilisé par un filtre de vote consécutif avant mise à jour (évite les flips à chaque cycle).
- **Source technique** : `advisor_loop._adaptive_regime (smoothed AdvancedRegimeDetector vote)`
- **Unité / type** : enum (enum)
- **Fraîcheur (source)** : advisor loop cycle cadence
- **Cadence attendue** : per advisor loop cycle
- **Polarité** : neutral
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : core/advisor_loop.py:6342-6361,6987-6988
- **Priorité de présentation** : primary

#### `market_state.regime_confidence` — Confiance du régime

- **Définition** : Confiance du détecteur de régime brut (avant lissage). Calculée et journalisée mais non exposée au SystemSnapshot opérateur aujourd'hui.
- **Source technique** : `RegimePacket.confidence / _regime_tracker`
- **Unité / type** : ratio_0_1 (score)
- **Fraîcheur (source)** : NOT_CURRENTLY_AVAILABLE at operator snapshot layer
- **Cadence attendue** : per advisor loop cycle (internal only)
- **Polarité** : higher_is_better
- **Sémantique null** : UNAVAILABLE — non câblé au SystemSnapshot opérateur (gap identifié, pas une hypothèse)
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/intelligence/market_regime_classifier.py:36; core/advisor_loop.py:6331-6339
- **Priorité de présentation** : diagnostic

#### `market_state.exchange_latency_ms` — Latence exchange (marché)

- **Définition** : Latence de connectivité vers l'exchange actif, telle que reflétée dans MarketSnapshot.
- **Source technique** : `ExchangeMonitor.snapshot().last_latency_ms`
- **Unité / type** : ms (duration_ms)
- **Fraîcheur (source)** : ExchangeMonitor background thread
- **Cadence attendue** : continuous
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : supervision/exchange_monitor.py; core/advisor_loop.py:6989-6994
- **Priorité de présentation** : secondary

#### `market_state.universe_size` — Taille de l'univers scanné

- **Définition** : Nombre d'instruments dans l'univers de scan courant.
- **Source technique** : `INCONCLUSIVE — aucun compteur confirmé`
- **Unité / type** : count (count)
- **Fraîcheur (source)** : NOT_CURRENTLY_AVAILABLE
- **Cadence attendue** : NOT_CURRENTLY_AVAILABLE
- **Polarité** : not_applicable
- **Sémantique null** : UNKNOWN — producteur non confirmé, à revalider avant intégration
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : core/perp_universe_service.py, quant_hedge_ai/agents/market/market_scanner.py — pas de champ de couverture confirmé consommé par une couche d'observabilité
- **Priorité de présentation** : diagnostic


### C — DECISION PIPELINE

#### `decision_pipeline.trade_allowed` — Verdict final

- **Définition** : Verdict terminal du pipeline pour ce symbole/cycle: le trade est-il autorisé ?
- **Source technique** : `DecisionObservation.trade_allowed`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : per-cycle DecisionObservation publication
- **Cadence attendue** : per advisor loop cycle per symbol
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observability/decision_observation.py:56-239
- **Priorité de présentation** : primary

#### `decision_pipeline.first_blocker` — Premier bloqueur

- **Définition** : Première couche du pipeline ayant refusé le trade, dans l'ordre d'évaluation.
- **Source technique** : `DecisionObservation.first_blocker`
- **Unité / type** : enum (enum)
- **Fraîcheur (source)** : per-cycle DecisionObservation publication
- **Cadence attendue** : per advisor loop cycle per symbol
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observability/decision_observation.py
- **Priorité de présentation** : primary

#### `decision_pipeline.disagreement_rate` — Taux de désaccord Packet/Legacy

- **Définition** : Fraction des décisions où le pipeline DecisionPacket (candidat canonique) diverge du pipeline dict legacy qui pilote encore l'exécution réelle.
- **Source technique** : `advisor_loop._dp_disagreement_count / _dp_compared_count`
- **Unité / type** : pct (percentage)
- **Numérateur** : décisions où DecisionPacket et le pipeline legacy divergent
- **Dénominateur** : décisions comparées dans le cycle
- **Fraîcheur (source)** : advisor loop cycle cadence
- **Cadence attendue** : per advisor loop cycle
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : core/advisor_loop.py:6274-6295
- **Priorité de présentation** : diagnostic


### D — ATTRITION / REJECTIONS

#### `attrition.by_layer_pct` — Répartition des refus par couche

- **Définition** : Part de chaque couche bloqueuse parmi les refus enregistrés dans la fenêtre interrogée.
- **Source technique** : `DecisionTraceService.statistics().by_layer_pct`
- **Unité / type** : pct (percentage)
- **Numérateur** : refus attribués à cette couche
- **Dénominateur** : total des enregistrements de refus dans la fenêtre (PAS le total des signaux évalués)
- **Fraîcheur (source)** : RejectionStore JSONL rotation (daily UTC)
- **Cadence attendue** : on query
- **Polarité** : not_applicable
- **Sémantique null** : ZERO si RejectionStore contient des enregistrements mais aucun pour la couche; UNAVAILABLE si le store est injoignable
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : visualization/decision_trace_service.py:350-374
- **Priorité de présentation** : primary

#### `attrition.execution_ratio` — Taux d'exécution

- **Définition** : Fraction des signaux évalués qui ont été exécutés (dénominateur = exécutés + refusés, PAS uniquement les refus).
- **Source technique** : `ActivityTracker.execution_ratio`
- **Unité / type** : pct (percentage)
- **Numérateur** : signaux exécutés
- **Dénominateur** : signaux exécutés + signaux refusés (cumul cycle)
- **Fraîcheur (source)** : ActivityTracker cycle cadence
- **Cadence attendue** : per advisor loop cycle
- **Polarité** : higher_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/intelligence/activity_tracker.py:198-200
- **Priorité de présentation** : primary

#### `attrition.no_trade_layer_rejection_rate` — Taux de refus — couche no-trade

- **Définition** : Ratio refusé/vérifié pour la couche no-trade spécifiquement.
- **Source technique** : `no_trade_layer.NoTradeLayer.stats().rejection_rate`
- **Unité / type** : pct (percentage)
- **Numérateur** : vérifications refusées par la couche no-trade
- **Dénominateur** : vérifications totales de la couche no-trade
- **Fraîcheur (source)** : in-process counter, reset on process restart
- **Cadence attendue** : NOT_CURRENTLY_AVAILABLE — calculé mais jamais lu
- **Polarité** : lower_is_better
- **Sémantique null** : UNAVAILABLE — aucun point d'appel de .stats() trouvé dans le dépôt (code mort du point de vue observabilité)
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/intelligence/no_trade_layer.py:182-191
- **Priorité de présentation** : diagnostic


### E — PORTFOLIO STATE

#### `portfolio_state.paper_equity_usd` — Capital paper (simulé)

- **Définition** : Équité simulée, basée sur WALLET_PAPER_CAPITAL + PnL cumulé du ledger paper_trades.jsonl. Ne représente aucun fonds réel.
- **Source technique** : `infra.wallet_sync.WalletSync.get_balance() [paper mode]`
- **Unité / type** : usd (currency_usd)
- **Fraîcheur (source)** : infra/wallet_sync.py ledger read
- **Cadence attendue** : per advisor loop cycle
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : infra/wallet_sync.py:48-70
- **Priorité de présentation** : primary

#### `portfolio_state.real_account_equity_usd` — Équité compte réel (API, lecture seule)

- **Définition** : Équité agrégée lue en lecture seule depuis les comptes exchange réels (multi-exchange via ccxt). Jamais utilisée pour le sizing et jamais combinée arithmétiquement au capital paper.
- **Source technique** : `observability.real_accounts.RealAccountsObserver.aggregate()`
- **Unité / type** : usd (currency_usd)
- **Fraîcheur (source)** : RealAccountsObserver poll cadence
- **Cadence attendue** : per notify cycle
- **Polarité** : not_applicable
- **Sémantique null** : NOT_APPLICABLE si aucun compte réel n'est configuré pour cette fenêtre de stabilisation
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observability/real_accounts.py:39-271; core/advisor_loop.py:393-401,7102-7106
- **Priorité de présentation** : primary

#### `portfolio_state.paper_open_positions_count` — Positions paper ouvertes

- **Définition** : Nombre de positions simulées actuellement ouvertes, prix réels de marché.
- **Source technique** : `paper_trading.mexc_simulator.MexcSimulator._positions (via paper_portfolio_view)`
- **Unité / type** : count (count)
- **Fraîcheur (source)** : MexcSimulator in-memory state
- **Cadence attendue** : per advisor loop cycle
- **Polarité** : not_applicable
- **Sémantique null** : ZERO si le simulateur est actif sans position; UNAVAILABLE si le simulateur n'est pas instancié
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : paper_trading/mexc_simulator.py; paper_trading/paper_portfolio_view.py:46-108
- **Priorité de présentation** : primary


### F — EXECUTION STATE

#### `execution_state.mode` — Mode d'exécution

- **Définition** : Mode effectif du dernier ordre traité: paper, live, live_failed ou rejected.
- **Source technique** : `ExecutionEngine.create_order() return.mode`
- **Unité / type** : enum (enum)
- **Fraîcheur (source)** : per order attempt
- **Cadence attendue** : on order attempt
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/execution/execution_engine.py:265-332
- **Priorité de présentation** : primary

#### `execution_state.live_trading_confirmed` — Confirmation trading réel (SEC-01)

- **Définition** : Double-opt-in défense-en-profondeur: doit être true ET une clé API doit être présente avant que le chemin d'exécution réelle soit atteignable.
- **Source technique** : `os.getenv('LIVE_TRADING_CONFIRMED')`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : process env at read time
- **Cadence attendue** : static per process lifetime
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : true hors fenêtre de stabilisation autorisée doit être signalé à l'opérateur
- **Source de preuve** : quant_hedge_ai/agents/execution/execution_engine.py:185-200
- **Priorité de présentation** : primary

#### `execution_state.orders_rejected` — Ordres rejetés (pré-exchange)

- **Définition** : Nombre d'ordres rejetés avant tout envoi à l'exchange (SessionGuard, déduplication, limites).
- **Source technique** : `TradeLogger.log_rejected() count`
- **Unité / type** : count (count)
- **Fraîcheur (source)** : TradeLogger SQLite table
- **Cadence attendue** : per order attempt
- **Polarité** : lower_is_better
- **Sémantique null** : ZERO si aucun rejet enregistré; UNAVAILABLE si la table SQLite est injoignable
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/execution/trade_logger.py:48-125
- **Priorité de présentation** : secondary


### G — DATA FRESHNESS

#### `data_freshness.regret_canonical_freshness` — Fraîcheur canonique Regret

- **Définition** : Age du dernier événement HORIZON_EVIDENCE évalué (EVALUATED) sur l'horizon canonique (1h). Distincte de 'dernier événement écrit' — un PENDING/DROPPED récent n'avance jamais cette horloge.
- **Source technique** : `tools.regret_repository.freshness()`
- **Unité / type** : seconds (duration_s)
- **Fraîcheur (source)** : tools/regret_repository.py:247-310
- **Cadence attendue** : MAX_STALE_H (env-configured)
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : tools/regret_repository.py:247-310
- **Priorité de présentation** : primary

#### `data_freshness.market_pulse_age` — Fraîcheur du pouls marché

- **Définition** : Age du dernier tick de marché écrit par le collecteur de pouls découplé.
- **Source technique** : `observation.market_observer latest_tick.json mtime`
- **Unité / type** : seconds (duration_s)
- **Fraîcheur (source)** : crypto-market-observer.timer cadence (15 min)
- **Cadence attendue** : 900s
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observation/market_observer.py:252-273
- **Priorité de présentation** : secondary


### H — REGRET STATE

#### `regret_state.canonical_freshness` — Fraîcheur canonique Regret

- **Définition** : Basée strictement sur le dernier événement EVALUATED de l'horizon canonique (1h) — jamais sur le dernier événement écrit, quel que soit son statut.
- **Source technique** : `tools.regret_repository.is_fresh()/freshness()`
- **Unité / type** : enum (enum)
- **Fraîcheur (source)** : tools/regret_repository.py:247-310
- **Cadence attendue** : MAX_STALE_H
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : tools/regret_repository.py:277-310
- **Priorité de présentation** : primary

#### `regret_state.horizon_status_counts` — Répartition des statuts d'horizon

- **Définition** : Comptage par statut d'évidence (PENDING, MISSING_PRICE, DROPPED, EVALUATED) sur l'horizon canonique.
- **Source technique** : `tools.regret_repository.diagnostics().horizon_status_counts`
- **Unité / type** : count (count)
- **Fraîcheur (source)** : regret_horizons_YYYY-MM-DD.jsonl
- **Cadence attendue** : per RegretScheduler evaluation
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : tools/regret_repository.py:157-204
- **Priorité de présentation** : secondary

#### `regret_state.decision_feedback_enabled` — Rétroaction décisionnelle Regret

- **Définition** : Double opt-in constitutionnel (ADR-0007): tant que false, Regret reste strictement passif et n'influence aucune décision de trading.
- **Source technique** : `config.feature_flags.FEATURE_REGRET_DECISION_FEEDBACK`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : process config at read time
- **Cadence attendue** : static per process lifetime
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : true sans ADR signé par l'opérateur constitue une violation d'ADR-0007
- **Source de preuve** : config/feature_flags.py (lecture seule, fichier protégé S-02B.1); docs/adr/0007-observabilite-passive-separation.md
- **Priorité de présentation** : primary

#### `regret_state.missed_win_semantic_caveat` — MISSED_WIN (avertissement scientifique)

- **Définition** : Un mouvement de prix favorable non capturé selon l'évaluation contrefactuelle de l'horizon. NE SIGNIFIE PAS un profit manqué exécutable — aucune garantie de remplissage, de slippage ou de contrainte de risque n'est prise en compte.
- **Source technique** : `RegretCandidate.regret_type == MISSED_WIN`
- **Unité / type** : count (count)
- **Fraîcheur (source)** : regret_horizons_YYYY-MM-DD.jsonl
- **Cadence attendue** : per RegretScheduler evaluation
- **Polarité** : not_applicable
- **Sémantique null** : ZERO (aucun MISSED_WIN sur la fenêtre) différent de UNAVAILABLE (Regret non câblé)
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observability/regret_scheduler.py:270-279
- **Priorité de présentation** : primary


### I — ADAPTIVE LEARNING STATE

> **O-01R reconciliation note.** This section was written pre-S-02B.1 and
> assumed no governance flag existed for these subsystems. It has been
> reconciled against the merged S-02B.1 (PR #111) implementation.
>
> ```
> PRE-S02 FORENSIC FINDING:
> mistake_memory.check_before_trade() and meta_learner.find_best()+learn()
> recorded as decision-active independent of any feature flag, with no
> RECOMMENDED vs APPLIED distinction anywhere.
>
> REMEDIATED BY:
> S-02B.1 / PR #111
>
> POST-S02 CURRENT STATE:
> config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK (default False,
> fail-closed) gates APPLICATION only; learning/observation stays active
> unconditionally. See below.
> ```

> **O-01R metric-semantics fix (this pass).** `decision_feedback_enabled`,
> `is_decision_active` and `recommendation_equals_applied` are three
> distinct concepts and must never be computed as functions of one
> another — in particular `is_decision_active == decision_feedback_enabled`
> and `recommendation_equals_applied == decision_feedback_enabled` are both
> overclaims and are explicitly rejected below.

#### `adaptive_learning.decision_feedback_enabled` — Rétroaction décisionnelle adaptative autorisée

- **Définition** : AUTORITÉ/PERMISSION uniquement : indique si `config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK` (défaut False, fail-closed) est effectivement actif pour ce process. Ne prouve rien sur une recommandation en particulier — ce n'est pas une preuve d'application, seulement l'autorisation qu'un chemin d'application existe. Ne jamais utiliser cette valeur pour déduire `is_decision_active` ou `recommendation_equals_applied`.
- **Source technique** : `config.feature_flags.adaptive_decision_feedback_enabled()`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : process config, re-résolu à chaque appel (jamais mis en cache) — AVAILABLE
- **Cadence attendue** : static per process lifetime unless .env changes
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED — le flag est toujours lisible
- **Sémantique avertissement** : true hors fenêtre de stabilisation autorisée doit être signalé à l'opérateur
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : config/feature_flags.py:64-86 — lecture seule, aucune modification
- **Priorité de présentation** : primary

#### `adaptive_learning.is_decision_active` — Sous-système décisionnel-actif

- **Définition** : EFFECTIVE APPLICATION / INFLUENCE DÉCISIONNELLE : indique si ce sous-système a réellement influencé la décision effective pour l'observation représentée — pas simplement si le flag l'y autorise. `decision_feedback_enabled=true` autorise un chemin d'application ; il ne prouve pas qu'une recommandation a existé, a survécu aux conditions restantes, a été sélectionnée, a changé l'état effectif, ou a été journalée comme appliquée. En l'absence de preuve par-événement, cette valeur reste UNKNOWN/FUTURE_PROVIDER — **jamais** déduite comme `is_decision_active == decision_feedback_enabled`.
- **Source technique** : `mistake_memory.check_before_trade(count_as_applied_block=FEATURE_ADAPTIVE_DECISION_FEEDBACK) / meta_learner.find_best()+learn() / strategy_memory.load_by_regime(record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK) / strategy_ranker.best_sharpe()`
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : FUTURE_PROVIDER — nécessite une preuve par-événement (pas seulement la lecture du flag) au moment de la décision, non encore exposée par un compteur dédié
- **Cadence attendue** : FUTURE_PROVIDER
- **Polarité** : not_applicable
- **Sémantique null** : UNKNOWN tant qu'aucun compteur dédié n'expose une preuve d'application par-événement — S02_PROVENANCE_DEBT. Ne jamais combler ce UNKNOWN en substituant la valeur de `decision_feedback_enabled` : enabled != used.
- **Sémantique avertissement** : true alors que `decision_feedback_enabled=false` doit être signalé à l'opérateur comme incohérence à investiguer immédiatement (le flag est la seule autorité d'application POST-S02B.1)
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : config/feature_flags.py:64-86 ; core/advisor_loop.py:77-79,687-691,1497,1526,1745-1763,1839,1976,2061-2067,3985-3990,4422-4427,4718-4750 ; tracker_system/autonomous/auto_decision_engine.py:19-23 (`_PASSIVE_GATED_ACTIONS`) — lecture seule, aucune modification
- **Priorité de présentation** : primary

#### `adaptive_learning.recommendation_equals_applied` — Recommandation = Action appliquée

- **Définition** : PROPRIÉTÉ STRUCTURELLE des cinq sous-systèmes adaptatifs gated (mistake_memory, strategy_memory, meta_learner, strategy_ranker, system_controller_adaptive), pas une vérification d'égalité par événement. PRE-S02B.1, la valeur retournée par ces sous-systèmes ÉTAIT la valeur appliquée (même chemin de code) : `recommendation_equals_applied` était structurellement vrai. POST-S02B.1, la recommandation reste toujours calculée, mais son application est désormais un pas distinct gouverné par `FEATURE_ADAPTIVE_DECISION_FEEDBACK`. C'est cette séparation architecturale — le fait qu'elle existe, indépendamment de la valeur courante du flag — que ce champ rapporte : `recommendation_equals_applied=False` de façon fixe pour ces cinq sous-systèmes, que le flag lise true ou false. **Ne jamais** calculer cette valeur comme `recommendation_equals_applied == decision_feedback_enabled` ni comme une fonction quelconque de la vérité runtime du flag.
- **Source technique** : `S02B1_STRUCTURAL_SPLIT` — propriété structurelle, pas une égalité runtime avec le flag
- **Unité / type** : boolean (boolean)
- **Fraîcheur (source)** : AVAILABLE — propriété structurelle du code actuel, ne varie pas avec le flag ni dans le temps
- **Cadence attendue** : n/a — structurel, pas un compteur temporel
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED — la propriété structurelle est toujours déterminable (False pour ces cinq sous-systèmes)
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : config/feature_flags.py:64-86 ; quant_hedge_ai/agents/intelligence/mistake_memory.py:198-245 (count_as_applied_block, would_match_count/trigger_count désormais distincts) ; quant_hedge_ai/ai_evolution/strategy_memory.py:80-112 (record_usage)
- **Priorité de présentation** : primary

#### `adaptive_learning.recommendation_count` — Nombre de recommandations

- **Définition** : Nombre de recommandations produites par le sous-système sur la fenêtre observée, que le flag d'application soit actif ou non.
- **Source technique** : `would_match_count (mistake_memory) / find_best() calls (meta_learner) / load_by_regime() calls (strategy_memory) / best_sharpe() calls (strategy_ranker)`
- **Unité / type** : count (count)
- **Fraîcheur (source)** : FUTURE_PROVIDER — S02_PROVENANCE_DEBT : per-recommendation versioning/compteur agrégé non encore exposé
- **Cadence attendue** : FUTURE_PROVIDER
- **Polarité** : not_applicable
- **Sémantique null** : UNKNOWN
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/intelligence/mistake_memory.py:91,232 (would_match_count) — au-delà de ce champ, aucun compteur persistant agrégé confirmé pour strategy_memory/meta_learner/strategy_ranker au-delà de stats()/summary() ponctuels
- **Priorité de présentation** : diagnostic

#### `adaptive_learning.applied_count` — Nombre d'actions appliquées

- **Définition** : Nombre de recommandations effectivement appliquées à une décision live sur la fenêtre observée (distinct de `recommendation_count`, jamais inféré depuis `decision_feedback_enabled`). `mistake_memory.BlockRule.trigger_count` existe par règle mais aucune méthode n'agrège encore ce compteur au niveau du sous-système entier ; aucun compteur équivalent confirmé pour strategy_memory/meta_learner/strategy_ranker/system_controller_adaptive au-delà de leurs points de gate individuels.
- **Source technique** : `trigger_count (mistake_memory)` — pas d'agrégat sous-système confirmé pour les autres sous-systèmes
- **Unité / type** : count (count)
- **Fraîcheur (source)** : FUTURE_PROVIDER — S02_PROVENANCE_DEBT : agrégat sous-système non encore exposé
- **Cadence attendue** : FUTURE_PROVIDER
- **Polarité** : not_applicable
- **Sémantique null** : UNKNOWN
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/intelligence/mistake_memory.py:88,234 (BlockRule.trigger_count, par règle, pas de somme exposée)
- **Priorité de présentation** : diagnostic

#### `adaptive_learning.memory_state_provenance` — Provenance de l'état mémoire

- **Définition** : Objet `{subsystem, source_path, state_mtime, compteurs volumétriques}` exposé par chacun des cinq sous-systèmes adaptatifs (`state_provenance()`), permettant de distinguer une recommandation produite depuis l'état mémoire X d'une autre produite depuis l'état Y. Ne remplace pas un versioning complet par recommandation (S02_PROVENANCE_DEBT) — c'est une provenance de l'état mémoire agrégé, pas une preuve d'application par-événement (ne pas confondre avec `is_decision_active`).
- **Source technique** : `<subsystem>.state_provenance()`
- **Unité / type** : object (enum)
- **Fraîcheur (source)** : state_mtime dans la valeur elle-même — AVAILABLE (méthode confirmée présente sur les cinq modules protégés)
- **Cadence attendue** : on demand
- **Polarité** : not_applicable
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : quant_hedge_ai/agents/intelligence/mistake_memory.py:608 ; quant_hedge_ai/ai_evolution/strategy_memory.py:138 ; quant_hedge_ai/ai_evolution/strategy_ranker.py:292 ; tracker_system/meta_learner.py:156 ; tracker_system/meta_memory.py:62 — lecture seule, aucune modification
- **Priorité de présentation** : diagnostic


### J — DISK / I-O

#### `disk_io.utilization_pct` — Utilisation disque

- **Définition** : Pourcentage d'espace utilisé sur le système de fichiers racine, tel qu'observé lors du dernier audit DA-01.
- **Source technique** : `DA-01 filesystem_observation().used_basis_points`
- **Unité / type** : pct (percentage)
- **Numérateur** : used_bytes
- **Dénominateur** : total_bytes
- **Fraîcheur (source)** : dernier run DA-01 (workflow_dispatch manuel, non planifié)
- **Cadence attendue** : on-demand only
- **Polarité** : lower_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : scripts/claude-disk-attribution.py:43-60
- **Priorité de présentation** : primary

#### `disk_io.residual_bytes` — Octets résiduels non attribués

- **Définition** : Croissance non attribuée à un bucket connu (blocs de répertoire, métadonnées fs, fichiers supprimés mais ouverts). Un résiduel important ne doit jamais être silencieusement assigné à l'application.
- **Source technique** : `filesystem used delta - somme(bucket allocated deltas)`
- **Unité / type** : bytes (bytes)
- **Fraîcheur (source)** : nécessite deux snapshots DA-01 comparables (catalog_sha256/schema_version identiques)
- **Cadence attendue** : on-demand only
- **Polarité** : lower_is_better
- **Sémantique null** : UNKNOWN avec un seul snapshot — la croissance ne peut jamais être déduite d'un unique relevé
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : docs/runbooks/DISK_ATTRIBUTION_AUDIT_PACK.md:41-49
- **Priorité de présentation** : secondary

#### `disk_io.market_observer_write_guard` — Garde d'espace disque (écriture pouls marché)

- **Définition** : Vérification d'espace libre avant chaque écriture de tick de marché; l'écriture est sautée si l'espace libre est sous OBS_MIN_FREE_DISK_GB. Garde privée d'un seul writer, pas une métrique disque opérateur générale.
- **Source technique** : `observation.market_observer.free_disk_gb()`
- **Unité / type** : gb (bytes)
- **Fraîcheur (source)** : checked at each write attempt
- **Cadence attendue** : continuous (per market_observer tick)
- **Polarité** : higher_is_better
- **Sémantique null** : NOT_DEFINED
- **Sémantique avertissement** : NOT_DEFINED
- **Sémantique critique** : NOT_DEFINED
- **Source de preuve** : observation/market_observer.py:86-90,204-215
- **Priorité de présentation** : diagnostic


---

## Part 2 — Telegram-observed metrics not yet promoted to the registry

These are metrics the forensic Telegram inventory
(`TELEGRAM_BOT_REGISTRY.md`) confirmed are currently rendered to the
operator. Each row states whether a canonical source is confirmed today
(and if so, which domain/metric it maps to) or whether it must be
treated as `SOURCE_UNRESOLVED` — not silently legitimized (mission §23).

### Quant Observer (`@QuantCrpto_bot`)

| Telegram metric | Current source | Canonical mapping | Availability |
|---|---|---|---|
| Engine version / cycle, snapshot age | `visualization.api.load_quant_live_snapshot()` -> `VisualizationEngine` | `system_health` (partial — snapshot age is a freshness field, not yet on the canonical registry) | CANONICAL_EXISTING (bot side), not yet registered |
| Market/API health, exchange latency/uptime | `SystemSnapshot.health`, `MarketSnapshot.exchange_latency_ms/exchange_uptime_pct` | `system_health.exchange_connectivity_healthy`, `market_state.exchange_latency_ms` | CANONICAL_EXISTING |
| Regime | `SystemSnapshot.market.regime` | `market_state.regime` | CANONICAL_EXISTING |
| Top candidate score / required score, mean signal score | `render_quant_live_panel()` formatting over the live analysis result | `decision_pipeline` (not yet a registered metric — score composition is internal to the legacy dict pipeline) | PARTIAL |
| Refusal breakdown + total, dominant filter % | Bot-side aggregation of `all_blockers` | `attrition.by_layer_pct` | CANONICAL_EXISTING, same numerator/denominator caveat applies |
| Pipeline stage status | Bot renders this explicitly labeled `"REPORTED/PARTIAL"` in its own text (`bot.py`) | `decision_pipeline` stages | PARTIAL — bot already flags this as partial; O-01 preserves that honesty rather than hiding it |
| Decision trace | Bot renders this explicitly labeled `"PARTIAL"` | `decision_pipeline` | PARTIAL |

### Portfolio bot (`@mon_portfolio_bot`, Command Center)

| Telegram metric | Current source | Canonical mapping | Availability |
|---|---|---|---|
| Win rate, Sharpe, max/current drawdown, total trades (`/status`, `/kpis`) | `PhaseKPITracker`, fed exclusively by `paper_trading.recorder.get_recorder().get_trades()` (**paper trades**) but initialized with `initial_capital=real_capital` (**real** allocated capital) | `portfolio_state` (paper) — **but the KPI panel never labels these as paper-derived next to the real-capital figure shown in the same message** | **SOURCE_UNRESOLVED for the presentation pairing** — the underlying data is traceable, but the display mixes a paper-trade-derived ratio with a real-capital base with no "paper" qualifier. Flagged as an O-02 priority fix, not fixed by O-01 (Telegram runtime is out of scope). |
| `/balance` (spot/futures) | `exec_engine.fetch_available_capital()` -> `real_capital` | `portfolio_state.real_account_equity_usd`-adjacent (real, not paper) | CANONICAL_EXISTING, but labeled generically "Spot"/"Futures" rather than "Real" |
| `/positions` | In-process closures over `_virtual_portfolio` (paper) | `portfolio_state.paper_open_positions_count` | CANONICAL_EXISTING |
| `/eo`, `/gate` | `black_box.query()`, `gate._last_snapshot` | `decision_pipeline` / `attrition` (risk gate) | PARTIAL, not yet registered |

### Paper Arena (`@PaperArena_bot`)

| Telegram metric | Current source | Canonical mapping | Availability |
|---|---|---|---|
| Paper Equity, entry/exit PnL | `src/paper/paper_runner.py::PaperMetrics` (explicitly prefixed "Paper" in every message) | `portfolio_state.paper_equity_usd`-equivalent, but a **separate, isolated experiment engine** — not the same paper equity as `WalletSync`/`MexcSimulator` | CANONICAL_EXISTING for its own scope, explicitly and correctly labeled paper; do not conflate with the main system's paper equity |
| Win rate, profit factor, expectancy, max DD %, ENL cost, gate status | `src/paper/paper_report.py` | `execution_state` (simulated fill/ENL cost) | CANONICAL_EXISTING for this isolated experiment; `_enl_fill()` duplicates `src/execution/enl.py` friction math by hand rather than importing it — a drift risk flagged in the bot registry, not fixed by O-01 |

### Telemetrie/CMVK (`@Telemetrie_IA_bot`, `sim_bot.py`)

| Telegram metric | Current source | Canonical mapping | Availability |
|---|---|---|---|
| Run PnL, win rate, max DD, regime | `SimBot` synthetic/backtest engine, `RunRepository` (`databases/sim_runs.sqlite`) | None — this is a synthetic/backtest run result, not live system state | **SOURCE_UNRESOLVED as an operator-health signal** — it answers "how would a strategy have performed," not "how is the machine doing now." Bot identity itself is also unresolved (env vars named `TELEMETRIE_IA_BOT_TOKEN` vs. `docs/architecture/TELEGRAM_BOT_REGISTRY.md` naming it `@FtnTrading_bot`; no systemd unit deploys it). |
| Edge Scoring System matrix | `src.analytics.edge_scorer.EdgeScorer` | Not mapped to any O-01 domain — an offline analytics tool, not an operator observability signal | SOURCE_UNRESOLVED for this architecture's purposes |
| Balance shown in `/run`, `/status`, `/pnl` | `self._balance`, seeded at a synthetic `10_000.0` | None — purely synthetic, no real or paper capital involved | Correctly out of scope for `portfolio_state`; flag risk: not self-labeled as synthetic beyond the bot's `[SIM]`-prefixed pushes |

### Radar bot (`@RadarCrypto1_bot`)

| Telegram metric | Current source | Canonical mapping | Availability |
|---|---|---|---|
| Per-symbol confidence, dominant side %, regime (`/scan`, `/top50`) | `compute_symbol_stats()` reading `databases/decision_packets_{date}.jsonl` directly (independent aggregation, not via `RejectionStore`/`DecisionObservation`) | `market_state` / `decision_pipeline` (candidate view) | **ACTIVE_DUPLICATED** at the aggregation level — reads the same raw decision-packet files that other subsystems also parse independently; no shared canonical aggregator used. Not fixed by O-01 (Telegram runtime out of scope); documented as a reuse gap for O-02/future work. |

### Cross-cutting finding

No literal summation of paper and real capital was found anywhere in the
codebase — `observability/real_accounts.py` is a deliberate, documented
guardrail (mission §10, preserved verbatim in `portfolio_state.py`). The
one real ambiguity is the **presentation pairing** in `/kpis`/`/status`
on the portfolio bot (paper-derived ratios shown unlabeled next to a
real-capital figure), not a computation bug. Both are documented above
rather than silently accepted or silently "fixed" by relabeling
something O-01 has no authority to touch (Telegram runtime is out of
scope for this mission).
