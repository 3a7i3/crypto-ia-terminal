# TELEGRAM BOT REGISTRY
**Contrat fonctionnel — version 1.0 — 2026-08-28**

> Ce document est le référentiel de définition des bots Telegram du système.
> Aucun bot ne peut afficher d'information qui n'est pas explicitement listée dans
> sa section ALLOWED. Aucun bot ne peut consommer un token déjà déclaré POLLING_OWNER
> dans une autre entrée. Ce document fait autorité sur le code.

---

## TABLE DES MATIÈRES

1. [Phase 0 — Census (inventaire exhaustif)](#phase-0--census)
2. [Phase 1 — Bot Constitution (contrats fonctionnels)](#phase-1--bot-constitution)
   - [🛑 KillSwitch](#bot-killswitch)
   - [📡 CryptoRadar](#bot-cryptoradar)
   - [💼 Portfolio (CommandCenter)](#bot-portfolio)
   - [🔬 Quant Observer](#bot-quant-observer)
   - [🧪 Paper Arena](#bot-paper-arena)
3. [Anomalies identifiées](#anomalies-identifiées)
4. [Feuille de route — Phases 2-5](#feuille-de-route--phases-2-5)

---

## Phase 0 — Census

### Tableau maître des bots (état courant, extrait du dépôt)

| Bot | Token ENV | Chat ENV | Source principale | Service systemd | Polling owner | Auto-messages | Commandes déclarées |
|-----|-----------|----------|-------------------|-----------------|---------------|---------------|---------------------|
| 🛑 KillSwitch | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_ID` | `supervision/telegram_kill_switch.py` `supervision/killswitch_hardened.py` | *aucun dédié* (thread dans advisor) | Oui — thread background | Incidents, urgences | `/stop_all` `/resume` `/status` `/help` |
| 📡 CryptoRadar | `TELEGRAM_BOT_TOKEN` ⚠️ | `TELEGRAM_CHAT_ID` ⚠️ | `scripts/radar_bot.py` | `crypto-radar-bot.service` | Oui — boucle principale | *aucun* (fully reactive) | `/scan` `/signals` `/top50` `/longs` `/shorts` `/symbol` `/lmi` `/status` `/help` |
| 💼 Portfolio | `P10_PORTFOLIO_BOT_TOKEN` | `P10_PORTFOLIO_CHAT_ID` (fallback `TELEGRAM_CHAT_ID`) | `capital_deployment/command_center_bot.py` | *aucun dédié* (lancé par advisor) | Oui — thread interne | Rapports périodiques (`P10_PORTFOLIO_REPORT_MINS`) | `/status` `/kpis` `/balance` `/positions` `/pnl` `/signals` `/help` |
| 🔬 Quant Observer | `QC_BOT_TOKEN` | `QC_CHAT_ID` | `src/telegram/quant_observer/bot.py` | `crypto-quant-observer.service` | Oui — boucle principale + refresh pin 10 min | Message épinglé auto-rafraîchi (`QC_PINNED_UPDATE=600s`) | `/snapshot` `/health` `/pipeline` `/portfolio` `/help` |
| 🧪 Paper Arena | `PAPER_ARENA_TG_TOKEN` | `PAPER_ARENA_TG_CHAT_ID` | `src/paper/paper_runner.py` + `src/paper/paper_report.py` | `paper-arena.service` | *Non* (push only) | Entrée / sortie / résumé d'expérience | *aucune* (push uniquement) |

### Consommateurs supplémentaires du token `TELEGRAM_BOT_TOKEN`

Les fichiers suivants consomment `TELEGRAM_BOT_TOKEN` (usage en push / notification,
pas en polling) — ils ne sont pas des bots à part entière mais des émetteurs
qui partagent le canal KillSwitch/Radar :

| Fichier | Usage | Risque |
|---------|-------|--------|
| `scripts/telegram_alerts.py` | Alertes push one-shot | Partage canal avec KillSwitch ⚠️ |
| `infra/notifications/notifications.py` | Notifications infra | Idem |
| `supervision/notifications/ops_notifier.py` | Alertes ops | Idem |
| `supervision/performance_watchdog.py` | Alertes performance | Idem |
| `supervision/exchange_monitor.py` | Alertes exchange | Idem |
| `core/advisor_loop.py` | Notifications advisor | Idem |
| `quant_hedge_ai/main_v91.py` | Notifications V9.1 | Idem |
| `scripts/daily_signal_report.py` | Rapport quotidien | Contenu signal sur canal Radar ⚠️ |

---

## Phase 1 — Bot Constitution

### Principe directeur

> **Un bot = l'interface humaine d'un seul domaine.**
> Un bot répond à une seule question humaine. Tout ce qui ne répond pas à cette
> question n'a pas sa place dans ce bot.

| Bot | Question humaine |
|-----|-----------------|
| 🛑 KillSwitch | « Le système est-il sous contrôle ? Puis-je l'arrêter immédiatement ? » |
| 📡 CryptoRadar | « Où se passe-t-il quelque chose sur le marché en ce moment ? » |
| 💼 Portfolio | « Est-ce que ma machine gagne réellement de l'argent ? » |
| 🔬 Quant Observer | « Que se passe-t-il dans la microstructure du système de décision ? » |
| 🧪 Paper Arena | « Cette hypothèse de recherche survit-elle à des données réelles ? » |

---

### BOT: KillSwitch

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 🛑 KillSwitch
  Token ENV       : KILLSWITCH_BOT_TOKEN          ← cible (actuellement TELEGRAM_BOT_TOKEN)
  Chat ENV        : KILLSWITCH_CHAT_ID            ← cible (actuellement TELEGRAM_CHAT_ID)
  Source          : supervision/telegram_kill_switch.py
                    supervision/killswitch_hardened.py
  Service         : (pas de service dédié — thread interne à crypto-advisor.service)
  Polling owner   : Oui — thread background dans advisor

MISSION
  Protéger le capital. Permettre à l'opérateur d'arrêter ou de reprendre
  le système en une commande, à tout moment.

AUTHORITY : WRITE — le seul bot autorisé à modifier l'état du moteur.

CRITICALITY : CRITIQUE

COMMANDS (autorisées)
  /stop_all       Arrêt d'urgence de toutes les exécutions
  /resume         Reprise après arrêt
  /status         État de sécurité : actif/arrêté, derniers incidents
  /help           Liste des commandes

AUTOMATIC MESSAGES (autorisés)
  - Confirmation d'arrêt d'urgence
  - Confirmation de reprise
  - Alerte incident critique (drawdown extrême, erreur fatale)
  - Heartbeat superviseur (si implémenté)

ALLOWED (contenu autorisé)
  - État du moteur : RUNNING / STOPPED / EMERGENCY
  - Autorité active : qui a déclenché l'arrêt
  - Horodatage du dernier incident
  - Cause de l'arrêt
  - Confirmation de commande reçue

FORBIDDEN (contenu interdit)
  - Signaux de marché (score, direction, symbole)
  - Données de scan (univers, actionnables)
  - Portfolio / equity / PnL
  - Positions ouvertes
  - Microstructure (LMI, flow, liquidité)
  - RAM / CPU / PID
  - Logs système détaillés
  - Données d'expérience Paper Arena
  - Résultats de recherche

DEPENDENCIES
  - supervision/telegram_kill_switch.py
  - supervision/killswitch_hardened.py
  - core/advisor_loop.py (réception de commande)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: CryptoRadar

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 📡 CryptoRadar
  Token ENV       : RADAR_BOT_TOKEN               ← cible (actuellement TELEGRAM_BOT_TOKEN ⚠️)
  Chat ENV        : RADAR_CHAT_ID                 ← cible (actuellement TELEGRAM_CHAT_ID ⚠️)
  Source          : scripts/radar_bot.py
  Service         : crypto-radar-bot.service
  Polling owner   : Oui — boucle principale (scripts/radar_bot.py)

MISSION
  Être les yeux du trader sur le marché.
  Montrer ce qui mérite l'attention maintenant — pas ce que fait le système.

AUTHORITY : READ_ONLY — aucune action sur le moteur.

CRITICALITY : OBSERVATION

COMMANDS (autorisées)
  /scan [N]       Top N opportunités par score de confiance (défaut 10)
  /top50          Top 50 compact
  /longs          Opportunités directionnelles LONG uniquement
  /shorts         Opportunités directionnelles SHORT uniquement
  /symbol TICKER  Analyse détaillée d'un symbole spécifique
  /lmi            Vue d'ensemble microstructure de marché (LMI)
  /lmi TICKER     Microstructure d'un symbole spécifique
  /help           Liste des commandes

COMMANDS SUPPRIMÉES (actuellement présentes, à retirer)
  /signals        → Expose Entry/SL/TP — données internes moteur, domaine Portfolio
  /status         → Expose tailles de fichiers DB, nombre de packets — domaine Ops

AUTOMATIC MESSAGES (autorisés)
  Aucun — bot entièrement réactif aux commandes.

ALLOWED (contenu autorisé)
  - Régime de marché global (BULL / BEAR / SIDEWAYS / UNCERTAIN)
  - Taille de l'univers observé (N paires)
  - Nombre d'opportunités actionnables (score ≥ seuil)
  - Score de confiance par symbole (agrégé, anonymisé si besoin)
  - Direction dominante par symbole (LONG / SHORT / MIXED)
  - Régime par symbole
  - Résumé LMI (microstructure de marché observable)
  - Données de microstructure pour /lmi (flow, liquidité — en lecture seule)

FORBIDDEN (contenu interdit)
  - Entry price, Stop Loss, Take Profit (appartient à Portfolio / moteur)
  - RAM / CPU / PID / mémoire processus
  - Taille des fichiers de base de données
  - Nombre de fichiers de décision / logs
  - État du pipeline de décision IA
  - Statistiques shadow trading
  - Portfolio brain / equity / balances
  - Comptes réels (MEXC, Binance)
  - Positions ouvertes
  - PnL réalisé ou non réalisé
  - État Telegram / health API interne
  - Métriques systemd / uptime service
  - Signal Policy / risk internals

FORMAT CIBLE /scan
  📡 CRYPTORADAR
  28 AUG · 07:18 UTC

  Marché: SIDEWAYS
  Univers: 135 paires · Actionnables: 19 (≥66)

  🔥 TOP OPPORTUNITÉS
  1. CHIP/USDT   76  BUY  BULL
  2. TAO/USDT    75  BUY  BULL
  3. UB/USDT     75  BUY  BULL

  👀 SURVEILLANCE
  56 paires entre 50–65

  Mode: OBSERVATION

DEPENDENCIES
  - databases/decision_packets_*.jsonl (lecture)
  - trade_analysis/integrations/radar_adapter (LMI, lecture)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Portfolio

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 💼 Portfolio (CommandCenter)
  Token ENV       : P10_PORTFOLIO_BOT_TOKEN        ← déjà distinct ✅
  Chat ENV        : P10_PORTFOLIO_CHAT_ID
  Source          : capital_deployment/command_center_bot.py
  Service         : (pas de service dédié — lancé par crypto-advisor.service)
  Polling owner   : Oui — thread interne (CommandCenterBot)

MISSION
  Montrer si la machine gagne réellement de l'argent.
  Répondre à : equity, PnL, win rate, risque, positions ouvertes.

AUTHORITY : READ_ONLY — observation du capital uniquement.

CRITICALITY : PERFORMANCE

COMMANDS (autorisées)
  /status         Résumé rapide : phase, capitale, régime
  /kpis           Métriques de performance (WR, Sharpe, DD, trades)
  /balance        Soldes paper et réels
  /positions      Positions ouvertes + PnL non réalisé
  /pnl            PnL réalisé détaillé
  /help           Liste des commandes

COMMANDS SUPPRIMÉES (actuellement présentes, à retirer)
  /signals        → Scores signaux — domaine CryptoRadar / moteur

AUTOMATIC MESSAGES (autorisés)
  - Rapport périodique (configurable via P10_PORTFOLIO_REPORT_MINS)
  - Alerte drawdown dépassé (seuil EO_DD_VETO)
  - Alerte streak de pertes (seuil EO_STREAK_VETO)
  - Changement de phase (F-01 → F-02, etc.)

ALLOWED (contenu autorisé)
  - Equity paper et réelle
  - Cash disponible
  - Exposure totale (%)
  - Win Rate, Sharpe Ratio, Max Drawdown
  - Nombre de trades, PnL cumulé
  - Positions ouvertes (symbole, direction, PnL non réalisé)
  - Phase courante et progression (F-01, jour X/7, etc.)
  - État global du bot (PAPER / LIVE / STANDBY)
  - Soldes par exchange (paper + réel agrégé)
  - Métriques de risque actives (vetos en cours)

FORBIDDEN (contenu interdit)
  - Scores de signaux par symbole (appartient à CryptoRadar / moteur)
  - Top 10 opportunités, top signaux
  - Régime de marché détaillé par paire
  - Entry/SL/TP pour chaque signal actif
  - RAM / CPU / PID
  - Logs pipeline IA
  - Statistiques shadow / MAGMA
  - Microstructure LMI
  - Données Paper Arena
  - État systemd / uptime service

FORMAT CIBLE /status
  💼 MON PORTFOLIO
  Cycle #216 · 28 AUG · 06:49 UTC

  CAPITAL
  Paper Equity     $688.24
  Paper Cash       $688.24
  Exposure         0.0%

  PERFORMANCE
  Win Rate         42%
  Sharpe           3.19
  Max DD           1.5%
  Trades           432

  POSITIONS
  3 ouvertes
  SPX/USDT   +$0.14
  TAO/USDT   +$0.06
  UB/USDT    -$0.05

  PHASE
  F-01 · Jour 0.8 / 7

  ÉTAT
  🟢 PAPER / STANDBY

DEPENDENCIES
  - capital_deployment/phase_kpi_tracker.py (lecture)
  - databases/paper_trades.jsonl (lecture)
  - databases/market_data.sqlite (lecture)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Quant Observer

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 🔬 Quant Observer (@QuantCrypto_bot)
  Token ENV       : QC_BOT_TOKEN                  ← déjà distinct ✅
  Chat ENV        : QC_CHAT_ID
  Pinned MSG ENV  : QC_PINNED_MSG_ID
  Source          : src/telegram/quant_observer/bot.py
  Service         : crypto-quant-observer.service
  Polling owner   : Oui — boucle principale + refresh épinglé toutes les 10 min

MISSION
  Observer la microstructure interne du système de décision (SDOS).
  Répondre à : pipeline, décisions, santé des composants, snapshot SDOS.
  Usage : chercheur / développeur — pas usage quotidien opérationnel.

AUTHORITY : READ_ONLY — visualisation SDOS uniquement.

CRITICALITY : RECHERCHE

COMMANDS (autorisées)
  /snapshot       Snapshot SDOS complet (4 panneaux)
  /health         Santé de tous les modules (radar)
  /pipeline       État du pipeline de décision
  /help           Liste des commandes

COMMANDS SUPPRIMÉES (actuellement présentes, à retirer)
  /portfolio      → Données KPIs portfolio — domaine Portfolio bot

AUTOMATIC MESSAGES (autorisés)
  - Message épinglé auto-rafraîchi toutes les QC_PINNED_UPDATE secondes (défaut 600s)
    → Contenu : snapshot SDOS léger (état pipeline, santé, régime)

ALLOWED (contenu autorisé)
  - État du pipeline de décision (couches actives, bloquées, raisons)
  - Santé des modules système (API, DB, strategy, risk, market — status OK/WARN/ERR)
  - Snapshot SDOS : PMI, niveau, gates franchies
  - Régime de marché global (résumé — pas le détail par paire)
  - Métriques de décision agrégées (N décisions, N bloquées — anonymisées)
  - Indicateurs de qualité des données

FORBIDDEN (contenu interdit)
  - Portfolio equity, cash, PnL
  - Positions ouvertes (symbole + valeur)
  - Soldes réels par exchange
  - Signaux par symbole (score, direction)
  - Top opportunités de marché
  - Entry/SL/TP
  - Données Paper Arena (résultats d'expérience)
  - RAM / CPU / PID bruts (santé OK/WARN/ERR est suffisant)
  - Commandes de contrôle (stop, resume)

DEPENDENCIES
  - visualization/api.py (load_pipeline_snapshot, load_health_snapshot)
  - src/telegram/quant_observer/bot.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Paper Arena

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 🧪 Paper Arena
  Token ENV       : PAPER_ARENA_TG_TOKEN           ← déjà distinct ✅
  Chat ENV        : PAPER_ARENA_TG_CHAT_ID
  Source          : src/paper/paper_runner.py
                    src/paper/paper_report.py
  Service         : paper-arena.service
  Polling owner   : Non — push uniquement (pas de getUpdates)

MISSION
  Rapporter les résultats d'une expérience scientifique isolée.
  Répondre à : cette hypothèse de recherche survit-elle aux données réelles ?

AUTHORITY : PUSH_ONLY — aucune commande, aucun polling.

CRITICALITY : RECHERCHE (expérimental)

COMMANDS : Aucune.

AUTOMATIC MESSAGES (autorisés)
  - Notification d'entrée en position (symbole, direction, prix, raison)
  - Notification de sortie (symbole, PnL, durée, raison)
  - Résumé périodique d'expérience (WR, PF, N trades, gate progress)
  - Notification de gate franchie (INSUFFICIENT SAMPLE → SAMPLE_OK → CONCLUSIVE)

ALLOWED (contenu autorisé)
  - Nom et description de l'expérience
  - Symbole et timeframe de l'expérience
  - État : RUNNING / PAUSED / CONCLUDED
  - Nombre de trades de l'expérience
  - Win Rate, Profit Factor, PnL de l'expérience
  - Max Drawdown de l'expérience
  - Progression vers le gate de conclusion (N / N_required)
  - Statut de l'hypothèse (INSUFFICIENT_SAMPLE / INCONCLUSIVE / VALIDATED / REJECTED)
  - Détail de l'événement déclencheur (entrée / sortie)

FORBIDDEN (contenu interdit)
  - État global du système (pipeline, advisor)
  - Portfolio equity / PnL global
  - Positions réelles
  - Soldes exchanges
  - Signaux de marché (autres que ceux de l'expérience)
  - RAM / CPU / PID
  - Données d'autres expériences ou d'autres bots

FORMAT CIBLE (message d'entrée)
  🧪 PAPER ARENA

  Experiment: RSI-EXTREME-V1
  ETH/USDT · 4H

  STATUS: Running · Trades: 47

  PERFORMANCE
  WR: 48.9%  PF: 1.12  PnL: +$14.23
  DD: 3.1%

  GATE
  Progress: 47 / 100 trades
  Status: INSUFFICIENT SAMPLE

  Last event:
  ▶ ENTRY LONG · $3,241 · RSI=14.8

DEPENDENCIES
  - src/paper/paper_report.py (notify_entry, notify_exit, notify_summary)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Anomalies identifiées

### 🔴 CRITIQUE — Collision de token (Phase 3 requise)

| Anomalie | Fichiers concernés | Impact |
|----------|-------------------|--------|
| **COLLISION TOKEN** : `TELEGRAM_BOT_TOKEN` est partagé entre KillSwitch (`telegram_kill_switch.py`, `killswitch_hardened.py`) et CryptoRadar (`radar_bot.py`) | `supervision/telegram_kill_switch.py` `supervision/killswitch_hardened.py` `scripts/radar_bot.py` | Conflit `getUpdates` — le radar peut intercepter les commandes `/stop_all` du KillSwitch ou vice versa. Sécurité dégradée. |
| **COLLISION TOKEN** : nombreux émetteurs push partagent également `TELEGRAM_BOT_TOKEN` | `scripts/telegram_alerts.py` `infra/notifications/notifications.py` `supervision/notifications/ops_notifier.py` et al. | Pollution du canal KillSwitch par des messages non critiques. |

### 🟡 VIOLATION FONCTIONNELLE — CryptoRadar

| Commande | Violation | Destination correcte |
|----------|-----------|----------------------|
| `/signals` | Affiche Entry/SL/TP — données du moteur d'exécution | Portfolio ou suppression |
| `/status` | Affiche taille DB, nombre de fichiers de décision | Ops/Watchdog (logs dashboard) |

### 🟡 VIOLATION FONCTIONNELLE — Portfolio Bot

| Commande | Violation | Destination correcte |
|----------|-----------|----------------------|
| `/signals` | Affiche scores par symbole — domaine scanner de marché | CryptoRadar ou suppression |

### 🟡 VIOLATION FONCTIONNELLE — Quant Observer

| Commande | Violation | Destination correcte |
|----------|-----------|----------------------|
| `/portfolio` | Affiche KPIs portfolio — domaine Portfolio bot | Portfolio bot |

### ℹ️ INFO — Portfolio sans service systemd dédié

Le CommandCenter bot est lancé dans le thread de `crypto-advisor.service`. Il n'a pas
de service indépendant. Toléré en phase actuelle, à isoler si le cycle advisor redémarre
fréquemment.

---

## Feuille de route — Phases 2-5

```
PHASE 2 — Interface Audit
  Pour chaque bot : actuel → ce qu'il affiche → ce qu'il devrait afficher → écart.
  Correction des violations fonctionnelles identifiées ci-dessus.
  Suppression de /signals dans radar_bot.py et command_center_bot.py.
  Suppression de /status dans radar_bot.py.
  Suppression de /portfolio dans quant_observer/bot.py.

PHASE 3 — Identity Isolation
  Créer KILLSWITCH_BOT_TOKEN (renommer depuis TELEGRAM_BOT_TOKEN).
  Créer RADAR_BOT_TOKEN (renommer depuis TELEGRAM_BOT_TOKEN dans radar_bot.py).
  Migrer les émetteurs push vers un token dédié ALERTS_BOT_TOKEN ou
  vers les tokens de leur bot propriétaire.
  Post-condition : 1 token = 1 polling owner = 1 identité bot.

PHASE 4 — Tests anti-collision
  Test statique : grep TELEGRAM_BOT_TOKEN dans les processus polling.
  Test dynamique : vérifier qu'un seul getUpdates actif par token au runtime.
  Outil : tools/convergence_forensic_readonly.py (déjà disponible).

PHASE 5 — Runtime VPS Audit
  systemd : units actives, PID, threads, RAM par service.
  Network : connexions Telegram ouvertes par processus.
  Tokens effectivement injectés dans l'environnement systemd.
  Processus orphelins, restart loops.
  Outil : snapshot non secret du runtime à fournir à l'auditeur.
```

---

## Règle de mise à jour de ce document

> Toute modification du comportement d'un bot Telegram (nouvelles commandes,
> nouveau contenu de message, nouveau token, nouveau service systemd) doit être
> reflétée dans ce document **avant** d'être mergée dans `main`.
> Ce document est le contrat. Le code doit respecter le contrat, pas l'inverse.
