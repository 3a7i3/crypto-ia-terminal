# 📚 Documentation automatique – Crypto AI Terminal

Bienvenue dans la documentation générée automatiquement pour le projet **Crypto AI Terminal** (V9.1).

---

## Table des matières
- [Présentation](#présentation)
- [Architecture](#architecture)
- [Modules principaux](#modules-principaux)
- [Entrypoints](#entrypoints)
- [Utilisation rapide](#utilisation-rapide)
- [Tests et validation](#tests-et-validation)
- [FAQ et support](#faq-et-support)

---

## Présentation

Crypto AI Terminal est un laboratoire quantitatif autonome pour la génération, l'évolution et l'orchestration de stratégies de trading IA. Il intègre un dashboard interactif, un orchestrateur multi-agents, des outils d'analyse de marché, de gestion des risques, et des modules de monitoring avancés.

---

## Architecture

- **quant-hedge-ai/** : Système principal V9.1 (agents, dashboard, core, data, tests)
- **crypto_quant_v16/** : Stack dashboard V16/V26/V30
- **docs/** : Documentation technique et guides
- **run_all_tests.py** : Lancement de tous les tests
- **requirements.txt** : Dépendances principales

---

## Modules principaux

- **Agents d'exécution** : Arbitrage, exécution, liquidité, paper trading
- **Agents d'intelligence** : Feature engineering, détection de régimes, analyse de flux
- **Agents de marché** : Scanner, orderflow, volatilité, radar baleine
- **Agents de portefeuille** : PortfolioBrain, KellyAllocator, VolatilityTargeter
- **Agents de stratégie** : Générateur, optimiseur génétique, RL trader
- **Agents de risque** : RiskMonitor, DrawdownGuard, ExposureManager
- **Monitoring** : PerformanceMonitor, SystemMonitor, PromptDoctor
- **Dashboard** : Contrôle centralisé, visualisation avancée (Panel/Plotly)

---

## Entrypoints

- **main_v91.py** : Orchestrateur principal du laboratoire quantitatif
- **dashboard_panel.py** : Dashboard interactif (Panel/Plotly)
- **run_all_tests.py** : Lancement automatisé de tous les tests

---

## Utilisation rapide

```powershell
cd quant-hedge-ai
python main_v91.py
```

Pour lancer le dashboard :
```powershell
panel serve dashboard/dashboard_panel.py --port 5010 --show
```

---

## Tests et validation

- **Exécuter tous les tests** :
  ```powershell
  python run_all_tests.py
  ```
- **Checklist QA** : Voir [VALIDATION_CHECKLIST.md](VALIDATION_CHECKLIST.md)

---

## FAQ et support

- [FAQ_EVOLUTION_DASHBOARD_FR.md](FAQ_EVOLUTION_DASHBOARD_FR.md)
- Issues GitHub ou contact direct

---

*Documentation générée automatiquement – Mars 2026*
