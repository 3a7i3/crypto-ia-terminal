# TELEGRAM_AUDIT_REPORT — Phase 1, audit avant modification

> **Statut : audit seul. Aucune modification de template n'a été effectuée.**
> Mesuré le 2026-08-05 sur la branche `phase-a/v5-foundation`.
> Chaque ligne est ancrée sur un `fichier:ligne` vérifié, jamais sur une
> supposition de câblage.

---

## 1. Canaux réellement configurés

Cinq canaux existent dans `.env`. Un sixième est nommé dans la mission mais
**n'a aucun canal configuré**.

| # | Bot | Variables `.env` | Émetteur | Déclenchement |
|---|---|---|---|---|
| 1 | **@QuantCrpto_bot** | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | `_telegram()` — `core/advisor_loop.py:926` | ~20 sites d'appel |
| 2 | **Rapport_ia-crypto-quant** | *même token* + `TELEGRAM_BEHAVIOR_CHAT_ID` | `_telegram_behavior()` — `:1018` | `cycle % 50` + transitions |
| 3 | **@rapport_automatique_bot** | `INTEL_BOT_TOKEN` + `INTEL_BOT_CHAT_ID` | `_telegram_intel()` — `:1062` | briefing 6 h + radar marché |
| 4 | **@mon_portfolio_bot** | `P10_PORTFOLIO_BOT_TOKEN` + `P10_PORTFOLIO_CHAT_ID` | `CommandCenterBot` — `capital_deployment/command_center_bot.py:980`, instancié `advisor_loop.py:3611` | boucle `_report_loop` (`:1546`) |
| 5 | **bot compte réel** | `REAL_ACCOUNT_BOT_TOKEN` + `REAL_ACCOUNT_CHAT_ID` | `_telegram_real()` — `:1037` | périodique |
| — | **@PaperArena_bot** | *aucune* — présent uniquement dans `.env.example` | — | **n'existe pas** |

Notes de câblage vérifiées :

- Les bots 1 et 2 **partagent le même token** et ne diffèrent que par le `chat_id`.
  `_telegram_behavior` retombe sur `TELEGRAM_CHAT` si `TELEGRAM_BEHAVIOR_CHAT_ID`
  est vide (`:1022`) — un canal mal configuré déverse donc sur le canal principal.
- Le bot 4 tourne **dans le processus `advisor_loop`**, pas comme service séparé
  (aucun processus distinct sur le VPS). Le tuer implique de toucher `advisor_loop`.
- `observation/market_radar.py:14-15` émet sur **`INTEL_BOT`**, donc sur le bot 3.

---

## 2. Contenu actuel, par canal

### Bot 1 — @QuantCrpto_bot

`_build_summary()` (`advisor_loop.py:2367`) assemble :
`ACTIONNABLES` (`:2400`) · `SURVEILLANCE` (`:2433`) · `FAIBLES` (`:2455`).

Puis le cycle y concatène : `HEALTH` · `AI DECISION` · `PIPELINE` ·
`BLOCK STATS` · `SHADOW STATS` (`:7092`) · `COMMANDEMENT` (`:7103-7110`) ·
`PORTFOLIO BRAIN` · `COMPTE N°1` · `META-STRATEGY` (`:7210`) · `[ALIVE]`.

### Bot 2 — Rapport_ia-crypto-quant

`[BEHAVIOR]` (`behavioral_stability_monitor.py:317`) + digest de transitions
(`advisor_loop.py`, `_format_regime_digest`). **Déjà corrigé et conforme** —
commits `1ce42c4` et `5209b83`.

### Bot 3 — @rapport_automatique_bot

Briefing 6 h construit par `system_intel_reporter.py:210` (`build_report`) :
KPI (`_compute_kpis`, `:100`), régimes courants et changements (`:235-239`),
anomalie de stagnation (`_stall_anomaly`, `:162`). Plus le digest du radar marché.

### Bot 4 — @mon_portfolio_bot

`command_center_bot.py:980` : `RAPPORT` = Phase + Wallet + `PERFORMANCE` (`:992`)
+ `POSITIONS` (`:1018`) + `SIGNAUX` (`:1034`).

### Bot 5 — bot compte réel

Soldes API MEXC/Binance, statut STANDBY/LIVE.

---

## 3. Duplications mesurées

Sept, dont deux non identifiées lors de la discussion initiale.

| # | Donnée | Émise par | Devrait appartenir à |
|---|---|---|---|
| 1 | Positions ouvertes | Bot 1 (`PORTFOLIO BRAIN`) **et** Bot 4 (`POSITIONS`) | un seul |
| 2 | Signaux / scores | Bot 1 (`ACTIONNABLES`+`SURVEILLANCE`+`FAIBLES`) **et** Bot 4 (`SIGNAUX`) | Bot 4 cible = QuantCrypto |
| 3 | Régime de marché | Bot 1 (`Tendance`) **et** Bot 3 (`regimes_now`) **et** Bot 4 | QuantCrypto |
| 4 | Equity paper | Bot 1 (`Paper Equity`) **et** Bot 1 (`[ALIVE]`) **et** Bot 4 (`Wallet virtuel`) | un seul |
| 5 | Soldes réels | Bot 1 (`COMPTE N°1`) **et** Bot 5 | Bot 5 |
| 6 | **KPI de performance** | Bot 3 (`_compute_kpis`) **et** Bot 4 (`PERFORMANCE`) | un seul |
| 7 | **Message de clôture de trade** | `_telegram()` **et** `_portfolio_bot.send()` (`advisor_loop.py:4096-4099`) | un seul |

---

## 4. Anomalies découvertes pendant l'audit

**A. Aucun événement de trade n'atteint Telegram.**
Le message `SORTIE` existe (`advisor_loop.py:4088`) mais dans
`_on_position_close`, un callback de `pos_manager` (`:4103`). Or les trades du
dataset sont ouverts et fermés par `MexcSimulator`
(`mexc_simulator.py:711` et `:881`), qui n'émet aucune notification de trade.
**Le chemin instrumenté n'est pas le chemin exécuté** — quatrième occurrence de
ce motif dans le dépôt (cf. modules `v2_*`, `seal()`, `market_context`).

**B. Un canal mal configuré déverse sur le canal principal.**
`_telegram_behavior` (`:1022`) : `chat = TELEGRAM_BEHAVIOR_CHAT or TELEGRAM_CHAT`.
Ce repli silencieux mélangerait deux responsabilités sans aucun signal.

**C. Test en échec, antérieur à cette phase.**
`tests/paper_trading/test_paper_trade_e2e.py::…::test_mexc_simulator_market_order_complete`
échoue avec ou sans modification (vérifié par `git stash`) : la fixture fournit
OHLCV à $100 000 contre ticker à $1, ce qui déclenche la garde anti-prix périmé.
**Hors périmètre de cette mission**, mentionné pour ne pas être attribué au nettoyage.

---

## 5. Deux points bloquants pour l'Étape 2

### Bloquant 1 — La destination des trades est contradictoire

| Source | @QuantCrypto doit contenir | Les trades vont à |
|---|---|---|
| Consigne du 2026-08-05, plus tôt | « les logs de trade en live… exclusivement les résultats de trade » | @QuantCrpto |
| Mission Phase 1 (ci-présente) | « Market Intelligence Engine ». *Interdit :* Paper Equity, portefeuille, positions | @PaperArena_bot |

Les deux ne peuvent pas être vraies. **Aucune modification ne sera faite sur ce
point avant arbitrage.**

État du travail en cours : un journal de trades a été écrit et testé
(`format_entree` / `format_sortie` dans `mexc_simulator.py`, 12 tests verts dans
`tests/test_telegram_trade_journal.py`), câblé sur `_telegram` (@QuantCrpto)
selon la première consigne. **Non commité**, en attente de l'arbitrage.
Le formateur est indépendant du canal : seule la ligne de câblage
(`advisor_loop.py`, `trade_journal_fn=_telegram`) changerait.

### Bloquant 2 — @PaperArena_bot n'existe pas

Aucun token, aucun `chat_id`. Le bot 2 de la mission n'a pas de destination.
Créer un bot Telegram exige BotFather et un token — **c'est une action qui vous
revient**, je ne manipule pas de jeton. Une fois créé, les variables attendues
seraient à ajouter à `.env` ; je lirai leurs noms, jamais leurs valeurs.

Sans ce canal, trois options : rendre son rôle à @mon_portfolio_bot, le donner à
@QuantCrpto, ou geler le bot 2.

---

## 6. Risques de modification, par bot

| Bot | Risque | Mitigation |
|---|---|---|
| 1 | `_telegram()` a ~20 sites d'appel dont des **alertes critiques** (kill switch `:5116`, exchange dégradé `:3579-3594`). Filtrer trop large les supprimerait | Ne toucher que `_build_summary` et la concaténation du cycle. Ne jamais filtrer `_telegram()` lui-même |
| 2 | Aucun — déjà conforme | — |
| 3 | `system_intel_reporter` calcule des KPI **lus ailleurs** ? À vérifier avant de couper | Vérifier les consommateurs de `build_report` avant retrait |
| 4 | Tourne dans le processus moteur ; `_signals_lines` est **testé** (`tests/capital_deployment/test_command_center_signals.py`) | Retirer `SIGNAUX` casse ce test → l'adapter, pas le supprimer |
| 5 | Aucun | — |

---

## 7. Ce que l'Étape 2 modifiera, une fois débloquée

Uniquement des fonctions de **présentation** : `_build_summary`, la
concaténation du cycle dans `main()`, `command_center_bot._report_loop` et ses
blocs `_signals_lines` / positions.

Aucune touche à `ExecutionEngine`, `RiskManager`, `Strategy`, `PortfolioBrain`,
`MarketScanner`, ni à un calcul, un seuil ou un stockage.
