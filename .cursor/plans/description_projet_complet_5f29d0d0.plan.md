---
name: Description projet complet
overview: "Document d’export pour un autre LLM : vue d’ensemble du monorepo **crypto_ai_terminal**, ses stacks (V9.1, V16, quant-ai-system, labs IA), orchestration, dashboards, tests/CI et documentation — sans modification du code."
todos:
  - id: copy-paste-block
    content: Copier le bloc « Contexte projet… » du message assistant dans Claude (ou fusionner avec ce plan).
    status: completed
isProject: false
---

# Description du dépôt `crypto_ai_terminal` (export pour Claude / autre IA)

## 1. Identité et objectif

**crypto_ai_terminal** (également référencé comme *Crypto AI Terminal*) est un **dépôt monorepo** orienté **recherche et trading quantitatif crypto** : génération et évolution de stratégies, backtests, agents IA, supervision, dashboards interactifs (Panel / Streamlit), orchestration et intégrations (alertes, exports, CI). Le README racine annonce une orientation **production / laboratoire autonome** (V9.1, audits 2026, couverture, CI).

**Important pour un lecteur machine** : la documentation racine mentionne parfois le dossier `quant-hedge-ai` avec tiret, alors que le package Python et l’arborescence opérationnelle pour V9.1 sont sous [`quant_hedge_ai`](c:\Users\WINDOWS\crypto_ai_terminal\quant_hedge_ai) (underscore). Le point d’entrée documenté côté code est typiquement : `python -m quant_hedge_ai.main_v91` depuis la racine (le script gère l’import et affiche une aide si le `PYTHONPATH` est incorrect).

---

## 2. Organisation générale du monorepo

À la racine, on trouve notamment :

| Zone | Rôle |
|------|------|
| [`quant_hedge_ai`](c:\Users\WINDOWS\crypto_ai_terminal\quant_hedge_ai) | **Système V9.1** : agents (marché, exécution, risque, recherche, stratégie, baleines), moteurs de décision, evolution engine, dashboards intégrés, `main_v91.py` |
| [`crypto_quant_v16`](c:\Users\WINDOWS\crypto_ai_terminal\crypto_quant_v16) | **Plateforme V16** : multi-exchange (CCXT), agents IA, backtest, RL, dashboard Panel (ex. port 5011), scripts `launch_*.bat` |
| [`quant-ai-system`](c:\Users\WINDOWS\crypto_ai_terminal\quant-ai-system) | **Stack V6** documentée : orchestrateurs `main.py` / `main_v2.py`, core trading, IA (GA, DQN, LSTM), dashboard Streamlit/Panel, dossier `tests` |
| [`AI_HEDGE_FUND_SYSTEM`](c:\Users\WINDOWS\crypto_ai_terminal\AI_HEDGE_FUND_SYSTEM) | Architecture **type hedge fund** modulaire + **niveaux d’évolution** 1→7 sous [`evolution_levels`](c:\Users\WINDOWS\crypto_ai_terminal\AI_HEDGE_FUND_SYSTEM\evolution_levels) |
| [`AI_QUANT_LAB_V4`](c:\Users\WINDOWS\crypto_ai_terminal\AI_QUANT_LAB_V4) | Lab quant par domaines (data_intelligence, research_ai, strategy_ecosystem, simulation_lab, risk_intelligence, portfolio_ai, execution_system, supervision, infrastructure) + [`run_all_module_tests.py`](c:\Users\WINDOWS\crypto_ai_terminal\AI_QUANT_LAB_V4\run_all_module_tests.py) |
| [`quant-hedge-bot`](c:\Users\WINDOWS\crypto_ai_terminal\quant-hedge-bot), [`quant-trading-system`](c:\Users\WINDOWS\crypto_ai_terminal\quant-trading-system), [`QUANT_CORE`](c:\Users\WINDOWS\crypto_ai_terminal\QUANT_CORE), [`my_trading_system`](c:\Users\WINDOWS\crypto_ai_terminal\my_trading_system) | Variantes / noyaux trading et utilitaires |
| [`orchestration`](c:\Users\WINDOWS\crypto_ai_terminal\orchestration) | Scripts PowerShell d’orchestration multi-services, logs, API statut, alertes — voir [`README_ORCHESTRATEUR.md`](c:\Users\WINDOWS\crypto_ai_terminal\orchestration\README_ORCHESTRATEUR.md) |
| [`dashboard`](c:\Users\WINDOWS\crypto_ai_terminal\dashboard), [`supervision`](c:\Users\WINDOWS\crypto_ai_terminal\supervision), racine `scripts`, `install` | Dashboards partagés, supervision, utilitaires |
| [`docs`](c:\Users\WINDOWS\crypto_ai_terminal\docs) | Documentation Sphinx / guides |
| [`k8s`](c:\Users\WINDOWS\crypto_ai_terminal\k8s) | Manifestes / notes de déploiement Kubernetes |
| [`tests`](c:\Users\WINDOWS\crypto_ai_terminal\tests), `data`, `logs`, `results`, `reports` | Données d’exécution, sorties, tests transverses |
| `.github/workflows`, `.gitlab-ci.yml | CI GitHub / GitLab, pre-commit, workflows annexes (coverage, panels, sphinx, etc.) |

Le fichier racine [`requirements.txt`](c:\Users\WINDOWS\crypto_ai_terminal\requirements.txt) est **minimal** (ex. `panel`, `pandas`, `hvplot`, `requests`) ; chaque sous-projet a souvent son propre `requirements*.txt`.

---

## 3. Flux fonctionnel (vue métier)

- **Données / marché** → **intelligence & régimes** → **recherche / features** → **génération & évolution de stratégies** → **simulation & backtest** → **risque & allocation** → **exécution (papier / live)** → **supervision & feedback** → boucle de recherche.

[`AI_HEDGE_FUND_SYSTEM/README.md`](c:\Users\WINDOWS\crypto_ai_terminal\AI_HEDGE_FUND_SYSTEM\README.md) résume explicitement cette **boucle autonome** entre modules (DATA_LAYER, RESEARCH_LAB, STRATEGY_ECOSYSTEM, SIMULATION_LAB, RISK_INTELLIGENCE, PORTFOLIO_AI, EXECUTION_SYSTEM, MARKET_INTELLIGENCE, SUPERVISION, INFRASTRUCTURE).

[`AI_HEDGE_FUND_SYSTEM/evolution_levels/README.md`](c:\Users\WINDOWS\crypto_ai_terminal\AI_HEDGE_FUND_SYSTEM\evolution_levels\README.md) décrit une **progression par « niveaux »** (organisme fonctionnel → évolutif → IA → écosystème recherche → supercluster → méta-organisme → chercheur IA), chaque niveau avec pipelines et tests dédiés.

---

## 4. V9.1 (`quant_hedge_ai`) — détail technique utile

D’après [`quant_hedge_ai/main_v91.py`](c:\Users\WINDOWS\crypto_ai_terminal\quant_hedge_ai\main_v91.py) (imports représentatifs), le système assemble entre autres :

- **Agents marché** : scanner, order flow, volatilité, radar marché  
- **Agents exécution** : moteur d’exécution, arbitrage, liquidité, paper trading  
- **Quant / recherche** : backtest lab, Monte Carlo, optimiseur de portefeuille, feature engineering, modèles, analyse de papers, chercheur de stratégies  
- **Stratégie** : générateur, optimiseur génétique, RL trader, **factory** de stratégies  
- **Risque** : drawdown guard, exposure, risk monitor  
- **Portfolio** : « PortfolioBrain »  
- **Whales** : WhaleRadar, carte de flux de liquidité  
- **Évolution** : `EvolutionEngine`  
- **Dashboards** : `AIControlCenter`, `DirectorDashboard`  
- **Décision** : `DecisionEngine`, `StrategyRanker`  
- Intégrations transverses : `GlobalRiskGate`, `StreamBus` (modules racine importés)

La doc indexée pour l’utilisateur V9.1 est dans [`DOCUMENTATION_INDEX.md`](c:\Users\WINDOWS\crypto_ai_terminal\DOCUMENTATION_INDEX.md) (ordre de lecture : QUICK_START_V91, README_V91, CONFIG_REFERENCE_V91, etc.).

---

## 5. Dashboards et UX (2026)

[`README.md`](c:\Users\WINDOWS\crypto_ai_terminal\README.md) et [`README_CONSOLIDATED.md`](c:\Users\WINDOWS\crypto_ai_terminal\README_CONSOLIDATED.md) décrivent :

- Dashboards **Panel** et **Streamlit**, **sidebar** unifiée, tutoriels, exports (PNG, SVG, CSV, JSON)  
- Exemples de ports : 5010–5014, 5026, 8502 (selon launcher)  
- Fichier d’exemples : [`DASHBOARD_USAGE_TEMPLATES.md`](c:\Users\WINDOWS\crypto_ai_terminal\DASHBOARD_USAGE_TEMPLATES.md)  
- Captures sous [`screenshots`](c:\Users\WINDOWS\crypto_ai_terminal\screenshots)

---

## 6. Installation, config, diagnostic

- Guides : [`ONBOARDING_QUICK_START.md`](c:\Users\WINDOWS\crypto_ai_terminal\ONBOARDING_QUICK_START.md), [`README_CONSOLIDATED.md`](c:\Users\WINDOWS\crypto_ai_terminal\README_CONSOLIDATED.md), [`UPDATE_DEPLOY_GUIDE.md`](c:\Users\WINDOWS\crypto_ai_terminal\UPDATE_DEPLOY_GUIDE.md) (référencés dans la doc)  
- Scripts : `install_all.ps1` / `install_all.sh`  
- Variables d’environnement : `.env.example` (et variantes comme `.env.smtp.example` selon l’état du dépôt)  
- [`diagnostic_env.py`](c:\Users\WINDOWS\crypto_ai_terminal\diagnostic_env.py) : contrôle Python, pip, dépendances, permissions, git  

---

## 7. Tests et CI

- [`run_all_tests.py`](c:\Users\WINDOWS\crypto_ai_terminal\run_all_tests.py) : orchestration pytest / unittest et rapport `all_tests_report.md` — **à relire dans le dépôt** car une version observée du fichier retournait tôt après un bloc `quant-ai-system/tests` (code mort en dessous selon l’état du fichier)  
- [`requirements-ci.txt`](c:\Users\WINDOWS\crypto_ai_terminal\requirements-ci.txt) pour CI  
- [`.github/workflows/ci.yml`](c:\Users\WINDOWS\crypto_ai_terminal\.github\workflows\ci.yml) : tests Python 3.10, pytest + couverture, pre-commit, build Docker, export S3 optionnel (secrets)  
- Badges / rapports : README mentionne **Codecov**, **Coveralls**, rapports d’audit (`RAPPORT_FINAL_AUDIT.md`, `all_tests_report.md`)

---

## 8. Ce qu’un autre LLM doit retenir (contexte minimal)

1. **Un seul dépôt, plusieurs produits expérimentaux** partageant thèmes communs (agents, risque, dashboards).  
2. **Ne pas confondre** chemins documentés (`quant-hedge-ai`) et package réel (`quant_hedge_ai`) sans vérifier le disque.  
3. **Trading réel** : le dépôt insiste sur papier/simulation et secrets hors git ; toute exécution live relève de la responsabilité opérateur.  
4. Pour modifier ou étendre : cibler **le sous-dossier** concerné et ses `requirements` / tests associés.

---

**Livrable utilisateur** : le message assistant suivant ce plan contient une **version rédigée longue** (style « prompt de contexte ») prête à copier-coller dans Claude ; ce plan sert de **squelette fidèle au code et à la doc** avec liens vers les fichiers clés.
