# Contexte projet — `crypto_ai_terminal` (export pour Claude / autre IA)

**Usage :** copiez tout ce fichier dans une conversation Claude (ou autre LLM) comme contexte de dépôt.  
**Chemin du dépôt :** `crypto_ai_terminal` (aussi appelé *Crypto AI Terminal* sur le README).  
**Langage principal :** Python. **UI :** Panel, Streamlit, Plotly/HoloViz selon modules.

---

## 1. Identité et objectif

Ce dépôt est un **monorepo** orienté **recherche et trading quantitatif sur crypto** : génération et évolution de stratégies, backtests massifs, agents IA multi-rôles, gestion du risque et du portefeuille, exécution papier/live, supervision, dashboards interactifs, orchestration de services, documentation et CI (tests, couverture, pre-commit, workflows GitHub/GitLab).

Le README racine positionne le système comme un **laboratoire quant autonome** (références V9.1, audits 2026, badges Codecov/Coveralls, guides d’onboarding).

**Avertissement opérationnel :** le dépôt met l’accent sur la **simulation / paper trading** et sur la **non-committal des secrets**. Toute utilisation en **trading réel** relève de la responsabilité de l’opérateur (risques financiers, réglementation, clés API).

---

## 2. Piège fréquent pour les LLM : noms de dossiers

La documentation racine cite parfois **`quant-hedge-ai`** (avec tiret). Sur le disque, le **package Python V9.1** est sous **`quant_hedge_ai`** (underscore).

- **Lancement recommandé depuis la racine du repo :**  
  `python -m quant_hedge_ai.main_v91`  
  (après activation du venv et `PYTHONPATH` correct si besoin)

- Le fichier `quant_hedge_ai/main_v91.py` affiche un message d’erreur explicite si le module `quant_hedge_ai` est introuvable (souvent lancement depuis un sous-dossier).

Toujours **vérifier le chemin réel** avant de proposer des commandes `cd quant-hedge-ai`.

---

## 3. Carte des zones majeures du monorepo

| Zone | Rôle |
|------|------|
| **`quant_hedge_ai/`** | **Système V9.1** : agents (marché, exécution, risque, recherche, stratégie, baleines), moteurs de décision, evolution engine, dashboards (`AIControlCenter`, `DirectorDashboard`), bases / scoreboards, intégration `GlobalRiskGate`, `StreamBus`, etc. Point d’entrée : `main_v91.py` / module `quant_hedge_ai.main_v91`. |
| **`crypto_quant_v16/`** | **Plateforme V16** : multi-exchange (CCXT), scanner, agents IA, backtest, RL, risk engine, dashboard Panel (`ui/quant_dashboard.py`, ex. port 5011), scripts `launch_*.bat`, `main_v16.py`. |
| **`quant-ai-system/`** | **Stack documentée « V6 »** : `main.py`, `main_v2.py`, `core/`, `ai/`, `quant/`, `dashboard/`, `utils/`, dossier **`tests/`** (cible pytest fréquente). |
| **`AI_HEDGE_FUND_SYSTEM/`** | Architecture **type hedge fund** : data_layer, research_lab, strategy_ecosystem, alpha_discovery, execution_system, market_intelligence, supervision, etc. README : boucle autonome bout en bout. |
| **`AI_HEDGE_FUND_SYSTEM/evolution_levels/`** | **Niveaux 1→7** : pipelines évolutifs (fonctionnel → évolutif → IA → écosystème → supercluster → metacluster → swarm), chaque niveau avec modules et tests. |
| **`AI_QUANT_LAB_V4/`** | Lab découpé par domaines : `data_intelligence`, `research_ai`, `strategy_ecosystem`, `simulation_lab`, `risk_intelligence`, `portfolio_ai`, `execution_system`, `supervision`, `infrastructure`. Script : `run_all_module_tests.py`. |
| **`quant-hedge-bot/`**, **`quant-trading-system/`**, **`QUANT_CORE/`**, **`my_trading_system/`** | Autres variantes / noyaux / bots — chacun peut avoir ses propres `requirements*.txt`. |
| **`orchestration/`** | PowerShell : surveillance multi-services, logs, API HTTP statut, menu interactif, hooks d’alerte — voir `README_ORCHESTRATEUR.md`. |
| **`dashboard/`**, **`supervision/`**, **`scripts/`**, **`install/`** | Dashboards partagés, supervision, scripts utilitaires, installation. |
| **`docs/`** | Documentation Sphinx et guides. |
| **`k8s/`** | Notes / manifests déploiement Kubernetes. |
| **`tests/`**, `data/`, `logs/`, `results/`, `reports/` | Tests transverses, données runtime, sorties. |
| **`.github/workflows/`**, **`.gitlab-ci.yml`** | CI : tests Python, pytest + couverture, pre-commit, builds Docker, workflows annexes (panels, sphinx, diagnostic env, etc.). |

**Dépendances racine :** le fichier racine `requirements.txt` est **minimal** (ex. panel, pandas, hvplot, requests). Pour travailler sur un sous-système, installer en général **le `requirements` du sous-dossier** concerné.

---

## 4. Flux métier (boucle autonome)

Schéma logique répété dans la doc hedge-fund :

**Market Data** → **Market Intelligence** → **Research Lab** → **Strategy Ecosystem** → **Simulation Lab** → **Backtesting** → **Risk Intelligence** → **Portfolio AI** → **Execution System** → **Feedback** → retour **Research Lab**.

Les **evolution_levels** décrivent une montée en puissance par « générations » de l’organisme quant (du pipeline minimal aux essaims / meta-orchestrateurs).

---

## 5. V9.1 (`quant_hedge_ai`) — composants (aperçu depuis `main_v91.py`)

Sans lister exhaustivement chaque fichier, les **familles de modules** branchées au démarrage incluent notamment :

- **Marché :** `MarketScanner`, analyse d’order flow, détecteur de volatilité, `MarketRadar`, détection de régimes avancée, feature engineering.
- **Exécution :** `ExecutionEngine`, agents d’arbitrage et de liquidité, **paper trading**.
- **Quant / recherche :** `BacktestLab`, Monte Carlo, optimiseur de portefeuille, construction de modèles, analyse de papers, chercheur de stratégies.
- **Stratégie :** générateur, **optimiseur génétique**, **RL trader**, `StrategyFactory`.
- **Risque :** drawdown guard, gestion d’exposition, moniteur de risque.
- **Portfolio :** `PortfolioBrain`.
- **Whales / liquidité :** `WhaleRadar`, carte des flux.
- **Évolution :** `EvolutionEngine`.
- **Décision :** `DecisionEngine`, `StrategyRanker`.
- **Dashboards :** centre de contrôle IA, tableau de bord « directeur ».

**Documentation utilisateur V9.1 (ordre de lecture suggéré dans le repo) :**  
`DOCUMENTATION_INDEX.md` → `QUICK_START_V91.md` → `README_V91.md` → `CONFIG_REFERENCE_V91.md` → `V91_COMPLETE_SUMMARY.md`, etc.

---

## 6. V16 (`crypto_quant_v16`)

Plateforme **multi-exchange** (Binance, Bybit, Kraken via CCXT), scanner large, **quatre agents** (observer marché, générateur de stratégies, trader RL, enforceur de risque), backtest avancé (walk-forward, Monte Carlo), dashboard Panel + Plotly, scripts Windows de lancement. Voir `crypto_quant_v16/README.md` pour l’architecture ASCII et la structure des dossiers `ai/`, `core/`, `quant/`, `ui/`.

---

## 7. `quant-ai-system` (doc « V6 »)

Orchestrateurs Python, modules **core** (scanner, portefeuille, risque, exécution), couche **IA** (génération / évaluation / sélection de stratégies, prédicteur LSTM, agent DQN), **quant** (optimiseur, backtester), dashboards Streamlit/Panel. Les tests pytest sont typiquement sous `quant-ai-system/tests/`.

---

## 8. Dashboards, UX 2026, onboarding

- **README racine** et **README_CONSOLIDATED.md** : onboarding Windows/Linux/Mac, `install_all.ps1` / `install_all.sh`, copie `.env.example` → `.env`, lancement des dashboards par scripts `.bat` ou `panel serve ...`.
- **Navigation unifiée** : sidebars, bouton de retour vers l’accueil 3D Evolution, exports (PNG, SVG, CSV, JSON), wording/icônes homogènes.
- **Ports d’exemple** (doc) : 5010–5014, 5026, 8502 — vérifier les collisions (`ports_check.txt`, `netstat`).
- **Templates d’usage :** `DASHBOARD_USAGE_TEMPLATES.md`.
- **Captures :** dossier `screenshots/`.
- **Diagnostic environnement :** `diagnostic_env.py`.
- **Mises à jour / déploiement :** `UPDATE_DEPLOY_GUIDE.md` (référencé dans la doc).

---

## 9. Tests, CI, qualité

- **`run_all_tests.py`** : aujourd’hui, la fonction `main()` **retourne immédiatement** après avoir exécuté pytest sur `quant-ai-system/tests` avec `sys.executable`. Le code situé **après** ce `return` (venv Windows, pytest racine, unittest, rapport `all_tests_report.md`, notifications) est **inaccessible** — si l’objectif est une orchestration complète, ce fichier mérite une correction (hors périmètre de ce document d’export).
- **CI GitHub** (ex. `.github/workflows/ci.yml`) : Python 3.10, `requirements-ci.txt`, unittest discover, pytest avec couverture, pre-commit, build Docker, étapes optionnelles (DockerHub, S3) selon secrets.
- **Pre-commit :** `.pre-commit-config.yaml`.
- **Rapports / audit :** README pointe vers `RAPPORT_FINAL_AUDIT.md`, `all_tests_report.md`, `ACTION_PLAN_CHECKLIST.md`, etc.

---

## 10. Conseils pour modifier le code (pour un LLM assistant)

1. **Cibler un sous-projet** et ses dépendances/tests propres ; éviter d’assimiler tout le monorepo à une seule appli.
2. **Respecter les conventions** du dossier touché (imports, structure des agents, nommage).
3. **Ne pas committer** de clés API ; utiliser `.env` local.
4. Après changement : lancer les **tests du module** concerné (pytest dans le bon répertoire ou `AI_QUANT_LAB_V4/run_all_module_tests.py` pour ce lab).

---

## 11. Résumé en une phrase

**`crypto_ai_terminal` est un monorepo de laboratoire trading crypto** qui regroupe plusieurs générations de stacks (V9.1 `quant_hedge_ai`, V16 `crypto_quant_v16`, `quant-ai-system`, labs `AI_HEDGE_FUND_SYSTEM` / `AI_QUANT_LAB_V4`), des dashboards Panel/Streamlit, de l’orchestration PowerShell, de la doc riche et une CI multi-workflow — avec une documentation parfois historique ou incohérente sur les noms de chemins, d’où l’importance de vérifier l’arborescence réelle.

---

*Document généré pour export de contexte LLM — à jour par rapport à l’analyse du dépôt au moment de sa création.*
