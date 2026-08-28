# TELEGRAM BOT REGISTRY
**Contrat fonctionnel — version 2.0 — 2026-08-28**

> **Principe constitutionnel** (2026-08-28) :
> **Telegram = observation et compte rendu uniquement.**
> Aucune commande qui modifie le comportement de la machine, change un paramètre,
> arrête ou reprend le trading ne peut être accessible via Telegram.
> Tout contrôle du système passe exclusivement par le VPS (SSH).

---

## Bots actifs (5 bots)

| Bot BotFather | Username | Token ENV | Rôle | Type |
|---|---|---|---|---|
| CryptoRadar_Bot | `@RadarCrypto1_bot` | `RADAR_BOT_TOKEN` (aucun fallback — isolé) | 📡 Scanner marché | Polling + réactif |
| Mon Portefeuille Bot | `@mon_portfolio_bot` | `P10_PORTFOLIO_BOT_TOKEN` | 💼 Capital + performance | Polling + rapports auto |
| Quant_Crypto 🔥 | `@QuantCrpto_bot` | `QC_BOT_TOKEN` | 🔬 Univers + régime + signaux + méta | Polling + message épinglé |
| Rapport Automatique | `@rapport_automatique_bot` | `INTEL_BOT_TOKEN` | 🧠 Rapports IA 6h | Push uniquement |
| PaperArena | `@PaperArena_bot` | `PAPER_ARENA_TG_TOKEN` | 🧪 Expérience RSI ETH/4H | Push uniquement |

## Bots supprimés

| Bot | Raison |
|---|---|
| `@Connexion_VScode_bot` (KillSwitch) | Retiré — constitution 2026-08-28 : aucune commande de contrôle via Telegram |
| `@FtnTrading_bot` (SimBot) | Retiré — non utilisé en production |
| `@Telemetrie_IA_bot` | Retiré — non utilisé (service inactif) |

---

## TABLE DES MATIÈRES

1. [Principe constitutionnel](#principe-constitutionnel)
2. [Phase 0 — Census](#phase-0--census)
3. [Phase 1 — Bot Constitution](#phase-1--bot-constitution)
   - [📡 CryptoRadar](#bot-cryptoradar)
   - [💼 Portfolio (CommandCenter)](#bot-portfolio)
   - [🔬 Quant Observer (@QuantCrpto_bot)](#bot-quant-observer)
   - [🧠 Rapport Automatique](#bot-rapport-automatique)
   - [🧪 Paper Arena](#bot-paper-arena)
4. [Anomalies résolues](#anomalies-résolues)
5. [Feuille de route — Phases 2-5](#feuille-de-route--phases-2-5)

---

## Principe constitutionnel

```
╔══════════════════════════════════════════════════════════════════════╗
║  CONSTITUTION TELEGRAM — 2026-08-28                                  ║
║                                                                      ║
║  Règle absolue : Telegram = OBSERVATION ET COMPTE RENDU UNIQUEMENT. ║
║                                                                      ║
║  AUTORISÉ sur Telegram :                                             ║
║    - Lire des données (equity, positions, PnL, régime, signaux)      ║
║    - Recevoir des rapports automatiques (push)                       ║
║    - Demander un résumé d'état                                       ║
║                                                                      ║
║  INTERDIT sur Telegram :                                             ║
║    - Modifier un paramètre de trading ou de risque                   ║
║    - Arrêter ou reprendre le moteur                                  ║
║    - Changer de phase                                                ║
║    - Modifier la taille des ordres                                   ║
║    - Réinitialiser des KPIs                                          ║
║    - Redémarrer un service                                           ║
║    - Toute action qui change le comportement de la machine           ║
║                                                                      ║
║  Tout contrôle passe exclusivement par le VPS (SSH).                ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Phase 0 — Census

### Tableau des bots actifs (état courant)

| Bot | Token ENV | Chat ENV | Source principale | Service systemd | Polling owner | Auto-messages |
|-----|-----------|----------|-------------------|-----------------|---------------|---------------|
| 📡 CryptoRadar | `RADAR_BOT_TOKEN` (aucun fallback — isolé) | `RADAR_CHAT_ID` (aucun fallback — isolé) | `scripts/radar_bot.py` | `crypto-radar-bot.service` | Oui | *Aucun* (réactif) |
| 💼 Portfolio | `P10_PORTFOLIO_BOT_TOKEN` | `P10_PORTFOLIO_CHAT_ID` | `capital_deployment/command_center_bot.py` | in-process `crypto-advisor` | Oui | Rapports périodiques |
| 🔬 Quant Observer | `QC_BOT_TOKEN` | `QC_CHAT_ID` | `src/telegram/quant_observer/bot.py` | `crypto-quant-observer.service` | Oui | Message épinglé 10 min |
| 🧠 Rapport Auto | `INTEL_BOT_TOKEN` | `INTEL_BOT_CHAT_ID` | `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` | in-process `crypto-advisor` | Non | Push 6h |
| 🧪 Paper Arena | `PAPER_ARENA_TG_TOKEN` | `PAPER_ARENA_TG_CHAT_ID` | `src/paper/paper_runner.py` | `paper-arena.service` | Non | Push événements |

---

## Phase 1 — Bot Constitution

### Question humaine par bot

| Bot | Question humaine |
|-----|-----------------|
| 📡 CryptoRadar | « Où se passe-t-il quelque chose sur le marché en ce moment ? » |
| 💼 Portfolio | « Est-ce que ma machine gagne réellement de l'argent ? » |
| 🔬 Quant Observer | « Que se passe-t-il dans la microstructure du système de décision ? » |
| 🧠 Rapport Auto | Rapport de synthèse IA toutes les 6h — aucune interaction |
| 🧪 Paper Arena | « Cette hypothèse de recherche survit-elle aux données réelles ? » |

---

### BOT: CryptoRadar

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 📡 CryptoRadar
  BotFather       : @RadarCrypto1_bot
  Token ENV       : RADAR_BOT_TOKEN (aucun fallback — isolé, exit 1 si absent)
  Chat ENV        : RADAR_CHAT_ID (aucun fallback — isolé)
  Source          : scripts/radar_bot.py
  Service         : crypto-radar-bot.service
  Polling owner   : Oui

MISSION : Être les yeux du trader sur le marché.

AUTHORITY : READ_ONLY
CRITICALITY : OBSERVATION

COMMANDS
  /scan [N]       Top N opportunités par score (défaut 10)
  /top50          Top 50 compact (conf>=60)
  /longs          Opportunités LONG uniquement
  /shorts         Opportunités SHORT uniquement
  /symbol TICKER  Analyse d'un symbole
  /lmi            Vue microstructure marché
  /lmi TICKER     Microstructure d'un symbole
  /help           Liste des commandes

AUTOMATIC MESSAGES : Aucun (bot entièrement réactif)

ALLOWED
  - Régime de marché global
  - Univers observé (N paires)
  - Score de confiance agrégé par symbole
  - Direction dominante (LONG/SHORT/MIXED)
  - Régime par symbole
  - LMI microstructure (lecture seule)

FORBIDDEN
  - Entry/SL/TP (données moteur d'exécution)
  - Portfolio / equity / PnL
  - RAM / CPU / PID / taille DB
  - Pipeline IA / shadow stats
  - Toute commande de contrôle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Portfolio

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 💼 Portfolio (CommandCenter)
  BotFather       : @mon_portfolio_bot
  Token ENV       : P10_PORTFOLIO_BOT_TOKEN
  Chat ENV        : P10_PORTFOLIO_CHAT_ID
  Source          : capital_deployment/command_center_bot.py
  Service         : in-process crypto-advisor.service
  Polling owner   : Oui

MISSION : Montrer si la machine gagne réellement de l'argent.

AUTHORITY : READ_ONLY — aucune commande de contrôle
CRITICALITY : PERFORMANCE

COMMANDS (lecture seule uniquement)
  /status         Résumé : phase, capital, régime
  /kpis           Win Rate, Sharpe, DD, trades
  /balance        Soldes paper et réels
  /positions      Positions ouvertes + PnL non réalisé
  /pnl            PnL réalisé détaillé
  /phase          Phase F-xx + progression
  /regime         Régime marché (résumé global)
  /risk           État risque (lecture)
  /health         Santé modules (lecture)
  /eo             ExecutiveOverride (lecture)
  /gate           GlobalRiskGate (lecture)
  /perf           Courbe PnL ASCII
  /recap [N]      Recap N derniers jours
  /history [N]    Historique trades
  /logs [N]       Derniers logs
  /config         Paramètres (lecture seule)
  /get PARAM      Valeur d'un paramètre
  /certif         Certification P10-G
  /charts         Lien dashboard
  /help           Liste des commandes

AUTOMATIC MESSAGES
  - Rapport périodique (P10_PORTFOLIO_REPORT_MINS)
  - Alerte drawdown (lecture d'état)

FORBIDDEN
  - /pause /resume /set /setphase /maxorder /reset /restart /confirm /cancel
  - Toute commande qui modifie un paramètre ou le comportement du moteur
  - Signaux par symbole (domaine CryptoRadar)
  - Données Paper Arena
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Quant Observer

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 🔬 Quant Observer
  BotFather       : @QuantCrpto_bot
  Token ENV       : QC_BOT_TOKEN
  Chat ENV        : QC_CHAT_ID
  Source          : src/telegram/quant_observer/bot.py
  Service         : crypto-quant-observer.service
  Polling owner   : Oui + refresh message épinglé (10 min)

MISSION : Univers scanné, régime dominant, scores des signaux,
          candidats actionnables, état méta-stratégie. Aucun capital.

AUTHORITY : READ_ONLY
CRITICALITY : RECHERCHE

COMMANDS
  /snapshot       Snapshot SDOS complet (4 panneaux)
  /health         Santé des modules (radar)
  /pipeline       État du pipeline de décision
  /help           Liste des commandes

AUTOMATIC MESSAGES
  - Message épinglé auto-rafraîchi (QC_PINNED_UPDATE=600s)

ALLOWED
  - Univers observé (N paires)
  - Régime dominant (global + distribution)
  - Scores de signaux agrégés
  - Candidats actionnables (sans Entry/SL/TP)
  - État méta-stratégie
  - Pipeline de décision (lecture)
  - Santé modules

FORBIDDEN
  - Portfolio equity / PnL / balances
  - Positions réelles
  - RAM / CPU / PID bruts
  - Données Paper Arena
  - Toute commande de contrôle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Rapport Automatique

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 🧠 Rapport Automatique
  BotFather       : @rapport_automatique_bot
  Token ENV       : INTEL_BOT_TOKEN
  Chat ENV        : INTEL_BOT_CHAT_ID
  Source          : quant_hedge_ai/agents/intelligence/system_intel_reporter.py
  Service         : in-process crypto-advisor.service
  Polling owner   : Non (push uniquement)

MISSION : Rapport de synthèse IA toutes les 6h. Aucune interaction.

AUTHORITY : PUSH_ONLY — aucune commande, aucun polling
CRITICALITY : INFORMATION

AUTOMATIC MESSAGES
  - Rapport IA complet toutes les 6h (push)

FORBIDDEN
  - Toute commande interactive
  - Données de contrôle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### BOT: Paper Arena

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY
  Name            : 🧪 Paper Arena
  BotFather       : @PaperArena_bot
  Token ENV       : PAPER_ARENA_TG_TOKEN
  Chat ENV        : PAPER_ARENA_TG_CHAT_ID
  Source          : src/paper/paper_runner.py + src/paper/paper_report.py
  Service         : paper-arena.service
  Polling owner   : Non (push uniquement)

MISSION : Rapporter les résultats d'une expérience scientifique isolée.

AUTHORITY : PUSH_ONLY
CRITICALITY : RECHERCHE

AUTOMATIC MESSAGES
  - Notification d'entrée / sortie
  - Résumé d'expérience périodique
  - Statut gate (INSUFFICIENT_SAMPLE → CONCLUSIVE)

ALLOWED
  - Résultats de l'expérience uniquement (WR, PF, PnL expérience, N trades)
  - Gate progress

FORBIDDEN
  - État global du système
  - Portfolio / balances / PnL global
  - Toute commande interactive
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Anomalies résolues

| # | Anomalie | Solution | Statut |
|---|----------|----------|--------|
| 1 | `TELEGRAM_BOT_TOKEN` partagé entre KillSwitch et CryptoRadar | KillSwitch supprimé + `RADAR_BOT_TOKEN` ajouté ; fallback `TELEGRAM_BOT_TOKEN` supprimé du code (audit 2026-08-28, voir `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`) | ✅ Résolu |
| 2 | KillSwitch Telegram (commandes `/stop_all` `/resume`) | Interface Telegram retirée — état interne conservé pour `advisor_loop` | ✅ Résolu |
| 3 | `/signals` dans CryptoRadar (Entry/SL/TP hors domaine) | Remplacé par message de redirection | ✅ Résolu |
| 4 | `/status` dans CryptoRadar (métriques DB hors domaine) | Remplacé par message de redirection | ✅ Résolu |
| 5 | `/signals` dans Portfolio (scores par symbole) | Retiré du dispatch et du rapport auto | ✅ Résolu |
| 6 | `/portfolio` dans Quant Observer | Retiré + handler de redirection | ✅ Résolu |
| 7 | Commandes d'écriture dans Portfolio (`/pause` `/resume` `/set` etc.) | Retirées — constitution 2026-08-28 | ✅ Résolu |
| 8 | `@QuantCrpto_bot` non mappé dans le Registry | Mappé → `QC_BOT_TOKEN` | ✅ Résolu |

---

## Feuille de route — Phases 2-5

```
PHASE 2 — Interface Audit         ✅ COMPLÈTE
PHASE 3 — Token Isolation Prep    ✅ COMPLÈTE (isolation stricte, fallback retiré 2026-08-28)

PHASE 3 (finalisation VPS)
  Ajouter dans .env.secrets :
    RADAR_BOT_TOKEN=<token @RadarCrypto1_bot>
    RADAR_CHAT_ID=<chat_id>
  Supprimer :
    KILLSWITCH_BOT_TOKEN / KILLSWITCH_CHAT_ID (plus utilisés)
  Redémarrer :
    crypto-radar-bot.service + crypto-advisor.service

PHASE 4 — Tests anti-collision
  Vérifier : 1 token = 1 polling owner = 0 conflit 409
  Outil : tools/convergence_forensic_readonly.py

PHASE 5 — Runtime VPS Audit
  systemd, PID, RAM, connexions Telegram ouvertes par processus.
```

---

## Règle de mise à jour de ce document

> Toute modification du comportement d'un bot Telegram (nouvelles commandes,
> nouveau contenu de message, nouveau token, nouveau service systemd) doit être
> reflétée dans ce document **avant** d'être mergée dans `main`.
> Ce document est le contrat. Le code doit respecter le contrat, pas l'inverse.

