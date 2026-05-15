# Documentation Hub -- crypto_ai_terminal

> Source of truth unique. Genere automatiquement le 2026-05-13 11:26.
> Pour regenerer : `python project_os/doc_indexer.py`

---

## Navigation rapide

| Besoin | Section |
|--------|---------|
| Demarrer le systeme | [Quick Start](#quick-start--setup) |
| Comprendre l'architecture | [Architecture](#architecture--design) |
| Etat du projet (live) | [Project OS](#project-os--etat-courant) |
| Roadmap et phases | [Roadmap](#roadmap--planification) |
| Un composant specifique | [Composants](#composants--modules) |
| Rapports historiques | [Rapports](#rapports-historiques) |

---

## Project OS — Etat courant

**Coverage tests :** 30.1% (108 OK / 39 partiel / 342 manquant)
**Maturite globale :** 2.25/5
**Cycles :** aucun (propre)

| Commande | Role |
|----------|------|
| `python project_os/reporter.py --check` | CI check (exit 0/1) |
| `python project_os/reporter.py --file` | Rapport daily |
| `python project_os/doc_indexer.py` | Regenerer cet index |

---

## Quick Start & Setup

| Fichier | Titre |
|---------|-------|
| [CHECKLIST_DEMARRAGE_COMPLET.md](../docs/onboarding/CHECKLIST_DEMARRAGE_COMPLET.md) | Checklist de démarrage complet |
| [DEMARRAGE_RAPIDE_FR.md](../docs/DEMARRAGE_RAPIDE_FR.md) | 📚 Documentation enrichie et guides d’utilisation |
| [INSTALLATION_AUTOMATION.md](../install/INSTALLATION_AUTOMATION.md) | Améliorations automatiques pour l'installation |
| [ONBOARDING_QUICK_START.md](../docs/onboarding/ONBOARDING_QUICK_START.md) | 5. Navigation et UI/UX (Nouveautés 2026) |
| [QUICKSTART.md](../QUICKSTART.md) | ⚡ QUICKSTART — Optimization Stack |
| [QUICK_START.md](../QUICK_START.md) | 🚀 QUICK START — 3 Priorités Implémentées |
| [QUICK_START_V91.md](../docs/QUICK_START_V91.md) | 📚 Documentation enrichie et guides d’utilisation |
| [SETUP_VERIFY.md](../scripts/SETUP_VERIFY.md) | Setup Verify |

## Architecture & Design

| Fichier | Titre |
|---------|-------|
| [ARBORESCENCE.md](../ARBORESCENCE.md) | Arborescence du projet |
| [ARCHITECTURE_NOTES.md](../ARCHITECTURE_NOTES.md) | ARCHITECTURE_NOTES |
| [COMPLETE_SYSTEM_ARCHITECTURE.md](../COMPLETE_SYSTEM_ARCHITECTURE.md) | COMPLETE TRADING SYSTEM ARCHITECTURE — Phases 1-9 |
| [STACK_INDEX.md](../STACK_INDEX.md) | 📑 INDEX — Optimization Stack Files |
| [TRACKER_SCHEMA_MISMATCH_AUDIT.md](../TRACKER_SCHEMA_MISMATCH_AUDIT.md) | Tracker Schema Mismatch — Audit Complet |
| [TRACKER_SYSTEM_README.md](../TRACKER_SYSTEM_README.md) | Tracker System — Phase 1-7 Complete |
| [TRADE_EVENT_SCHEMA.md](../tracker_system/TRADE_EVENT_SCHEMA.md) | Canonical Trade Event Schema |
| [decision_lifecycle.md](../core/decision_lifecycle.md) | Decision Lifecycle |
| [lifecycle.md](../anara_context/lifecycle.md) | Cycle de vie d'une décision — crypto_ai_terminal |

## Roadmap & Planification

| Fichier | Titre |
|---------|-------|
| [ACTION_PLAN_CHECKLIST.md](../ACTION_PLAN_CHECKLIST.md) | Crypto Quant Trading System — Action Plan Checklist |
| [IMPLEMENTATION_3_PRIORITIES.md](../IMPLEMENTATION_3_PRIORITIES.md) | 🚀 IMPLÉMENTATION COMPLÉTÉE — 3 PRIORITÉS VALIDÉES |
| [P0_IMPLEMENTATION_REPORT.md](../P0_IMPLEMENTATION_REPORT.md) | P0 — IMPLÉMENTATION AMÉLIORATIONS CRITIQUES |
| [PHASE_1_7_SUMMARY.md](../PHASE_1_7_SUMMARY.md) | Phase 1-7 Implementation Summary |
| [PHASE_8_9_COMPLETE.md](../PHASE_8_9_COMPLETE.md) | Phase 8-9 COMPLETE — Dashboard Intelligence & Audit Engine |
| [PLAN_REPRISE.md](../PLAN_REPRISE.md) | Plan de reprise — Crypto AI Terminal |
| [ROADMAP_V9_V10_V11.md](../docs/ROADMAP_V9_V10_V11.md) | 🚀 VERSIONS ROADMAP - V9 → V9.1 → V10 → Beyond |
| [V10_IMPLEMENTATION_ROADMAP.md](../docs/v91/V10_IMPLEMENTATION_ROADMAP.md) | 🚀 V10 IMPLEMENTATION ROADMAP |
| [orchestration_improvement_plan.md](../docs/divers/orchestration_improvement_plan.md) | Plan d'amélioration de l'orchestration automatique |

## Operations & Deploiement

| Fichier | Titre |
|---------|-------|
| [CLOUD_DEPLOYMENT_DEMO.md](../docs/deployment/CLOUD_DEPLOYMENT_DEMO.md) | ☁️ Démo d’intégration cloud – Streamlit Cloud |
| [DEPLOIEMENT_CLOUD_GUIDE.md](../docs/deployment/DEPLOIEMENT_CLOUD_GUIDE.md) | Déploiement multi-cloud des dashboards Streamlit |
| [GUIDE_SCRIPTS_FRANCAIS.md](../GUIDE_SCRIPTS_FRANCAIS.md) | SCRIPTS EN FRANÇAIS — GUIDE D'UTILISATION |
| [OPTIMIZATION_GUIDE.md](../OPTIMIZATION_GUIDE.md) | 🚀 Optimization Guide — crypto_ai_terminal V9.1 |
| [README_DEPLOY_K8S.md](../k8s/README_DEPLOY_K8S.md) | Déploiement BotDoctor sur Kubernetes |
| [TEST_ISOLATION_GUIDE.md](../docs/ci/TEST_ISOLATION_GUIDE.md) | Procédure d'isolation et d'automatisation des tests |
| [TRACKER_SCHEDULER_WINDOWS_README.md](../TRACKER_SCHEDULER_WINDOWS_README.md) | Tracker Scheduler (Windows) |
| [UPDATE_DEPLOY_GUIDE.md](../docs/deployment/UPDATE_DEPLOY_GUIDE.md) | Procédure de mise à jour et déploiement |
| [oracle_cloud_guide.md](../deploy/oracle_cloud_guide.md) | Déploiement Oracle Cloud Free Tier — Guide étape par étape |

## Composants & Modules

| Fichier | Titre |
|---------|-------|
| [AIDE_GPT_EVOLUTION_DASHBOARD_FR.md](../docs/evolution/AIDE_GPT_EVOLUTION_DASHBOARD_FR.md) | 🤖 Aide interactive – Assistant GPT pour l’écosystème évolutif |
| [ARCHIVE.md](../quant_hedge_ai/_legacy/ARCHIVE.md) | Legacy Code Archive |
| [CHATBOT_EXTENSION.md](../docs/divers/CHATBOT_EXTENSION.md) | 🤖 Extension Chatbot Externe (démo) |
| [CHECKLIST_DASHBOARD_3D.md](../docs/evolution/CHECKLIST_DASHBOARD_3D.md) | Checklist de validation manuelle – Dashboard 3D Evolution |
| [CLAUDE_TRACKER_HANDOFF.md](../CLAUDE_TRACKER_HANDOFF.md) | Tracker System Handoff For Claude |
| [DASHBOARDS_AUDIT_REPORT.md](../docs/audit/DASHBOARDS_AUDIT_REPORT.md) | Rapport d'audit des Dashboards/Applications |
| [DASHBOARDS_README.md](../docs/checklists/DASHBOARDS_README.md) | Dashboards & Visualisation Apps — Crypto AI Terminal |
| [DASHBOARD_USAGE_TEMPLATES.md](../DASHBOARD_USAGE_TEMPLATES.md) | Tests & Validation (global) |
| [DOCUMENTATION_EVOLUTION_DASHBOARD.md](../docs/evolution/DOCUMENTATION_EVOLUTION_DASHBOARD.md) | 📖 Documentation détaillée – Écosystème évolutif & Dashboard |
| [DOCUMENTATION_EVOLUTION_DASHBOARD_EN.md](../DOCUMENTATION_EVOLUTION_DASHBOARD_EN.md) | 📖 Detailed Documentation – Evolutionary Ecosystem & Dashboard (EN) |
| [DOCUMENTATION_EVOLUTION_DASHBOARD_FR.md](../DOCUMENTATION_EVOLUTION_DASHBOARD_FR.md) | 📖 Documentation détaillée – Écosystème évolutif & Dashboard |
| [FAQ_EVOLUTION_DASHBOARD_EN.md](../docs/evolution/FAQ_EVOLUTION_DASHBOARD_EN.md) | ❓ FAQ – Evolutionary Ecosystem & Dashboard |
| [FAQ_EVOLUTION_DASHBOARD_FR.md](../FAQ_EVOLUTION_DASHBOARD_FR.md) | ❓ FAQ – Écosystème évolutif & Dashboard |
| [GPT_HELP_EVOLUTION_DASHBOARD_EN.md](../docs/evolution/GPT_HELP_EVOLUTION_DASHBOARD_EN.md) | 🤖 Interactive Help – GPT Assistant for the Evolutionary Ecosystem |
| [MIGRATION.md](../quant_hedge_ai/_legacy/MIGRATION.md) | Migration Guide |
| [RAPPORT_FINAL_SUPERVISION.md](../docs/audit/RAPPORT_FINAL_SUPERVISION.md) | RAPPORT FINAL — SUPERVISION BOTDOCTOR |
| [README.md](../quant_hedge_ai/README.md) | V9 Autonomous Quant Hedge Fund System |
| [README.md](../quant_hedge_ai/strategy_lab/README.md) | Strategy Lab — Exemples d'utilisation |
| [README_V91.md](../quant_hedge_ai/README_V91.md) | V9.1 - Autonomous Quant Lab with AI Portfolio Brain |
| [TUTORIAL_EVOLUTION_DASHBOARD_EN.md](../docs/evolution/TUTORIAL_EVOLUTION_DASHBOARD_EN.md) | 🚀 Step-by-step Tutorial – Evolutionary Ecosystem & Dashboard |
| [TUTORIEL_EVOLUTION_DASHBOARD_FR.md](../TUTORIEL_EVOLUTION_DASHBOARD_FR.md) | 🚀 Tutoriel pas-à-pas – Écosystème évolutif & Dashboard |
| [dashboard.md](../tracker_system/dashboard/dashboard.md) | Dashboard Intelligence |
| [final_report.md](../tracker_system/sessions/session_2026_05_12_23_04/final_report.md) | RAPPORT SESSION — session_2026_05_12_23_04 |
| [final_report.md](../tracker_system/sessions/session_2026_05_12_23_11/final_report.md) | RAPPORT SESSION — session_2026_05_12_23_11 |

## Tests & Validation

| Fichier | Titre |
|---------|-------|
| [CHECKLIST_ROBUSTESSE.md](../docs/checklists/CHECKLIST_ROBUSTESSE.md) | Checklist de robustesse Quant AI Terminal |
| [CODE_VALIDATION_REPORT.md](../CODE_VALIDATION_REPORT.md) | ✅ CODE VALIDATION & CLEANUP REPORT |
| [DOC_NOTIFY_TEST_STATUS.md](../DOC_NOTIFY_TEST_STATUS.md) | Documentation d’utilisation – notify_test_status.py |
| [MODULE_DEVELOPMENT_STATUS.md](../docs/checklists/MODULE_DEVELOPMENT_STATUS.md) | Module Development Status |
| [PROPOSITIONS_AUTOMATION.md](../docs/checklists/PROPOSITIONS_AUTOMATION.md) | Propositions d'améliorations automatiques pour crypto_ai_terminal |
| [RAPPORT_FINAL_AUDIT.md](../docs/audit/RAPPORT_FINAL_AUDIT.md) | Rapport final d’audit et robustesse |
| [RAPPORT_FONCTIONS_PROJET.md](../docs/audit/RAPPORT_FONCTIONS_PROJET.md) | 📋 RAPPORT DÉTAILLÉ DES FONCTIONS DU PROJET |
| [RAPPORT_SANTE_GLOBAL.md](../docs/audit/RAPPORT_SANTE_GLOBAL.md) | Rapport de santé global – Système Quantitatif |
| [ROOT_TEST_AUDIT.md](../ROOT_TEST_AUDIT.md) | Audit cible des `test_*.py` racine |
| [TESTS_AUTOMATION.md](../tests/TESTS_AUTOMATION.md) | Améliorations automatiques pour les tests |
| [TESTS_CI_DOC.md](../docs/ci/TESTS_CI_DOC.md) | CI/CD: Pytest + Coverage (Windows/Unix) |
| [VALIDATION_CHECKLIST.md](../docs/VALIDATION_CHECKLIST.md) | ✅ V9.1 VALIDATION CHECKLIST |
| [VALIDATION_COMPLETE.md](../VALIDATION_COMPLETE.md) | Phase 1-7 VALIDATION COMPLETE |
| [VERIFICATION_CHECKLIST.md](../VERIFICATION_CHECKLIST.md) | ✅ FINAL CHECKLIST — All Complete |
| [all_tests_report.md](../docs/audit/all_tests_report.md) | All Tests Report |
| [test_report.md](../docs/audit/test_report.md) | Test Report |

## Rapports historiques

| Fichier | Titre |
|---------|-------|
| [CLEANUP_REPORT_FINAL.md](../CLEANUP_REPORT_FINAL.md) | 🎯 ANALYSE & CORRECTION COMPLÈTE — RAPPORT FINAL |
| [DEDUPLICATION_REPORT.md](../DEDUPLICATION_REPORT.md) | Deduplication Report — Trade Tracker & Exit Engine |
| [DOCUMENTATION_FRANCAISE_COMPLETE.md](../DOCUMENTATION_FRANCAISE_COMPLETE.md) | SYSTÈME COMPLET DE TRADING — Documentation Française |
| [INTEGRATION_REPORT.md](../INTEGRATION_REPORT.md) | 📋 RAPPORT FINAL — Optimisation crypto_ai_terminal V9.1 |
| [INVENTAIRE_2026-04-25.md](../INVENTAIRE_2026-04-25.md) | Inventaire du projet `crypto_ai_terminal` — V2 complète |
| [P1_COMPLETE_REPORT.md](../P1_COMPLETE_REPORT.md) | P1 COMPLET — Advanced Metrics + Dashboard WebSocket |
| [P1_REGIME_DETECTION_REPORT.md](../P1_REGIME_DETECTION_REPORT.md) | P1 — AUTO REGIME DETECTION |
| [P2_COMPLETE_REPORT.md](../P2_COMPLETE_REPORT.md) | P2 COMPLET — ML Exit + Multi-Asset + API Stub |
| [PROJECT_COMPLETION_SUMMARY.md](../docs/PROJECT_COMPLETION_SUMMARY.md) | 🎉 V9.1 PROJECT COMPLETION SUMMARY |
| [PROJECT_INVENTORY.md](../docs/v91/PROJECT_INVENTORY.md) | 📦 COMPLETE PROJECT INVENTORY - V9.1 |
| [RAPPORT_AMELIORATIONS_CRITIQUES.md](../RAPPORT_AMELIORATIONS_CRITIQUES.md) | RAPPORT D'AMÉLIORATION — Points Critiques à Adresser |
| [RAPPORT_GLOBAL_V9.md](../docs/v91/RAPPORT_GLOBAL_V9.md) | 📊 RAPPORT GLOBAL - Architecture Crypto AI Hedge Fund (V7-V9) |
| [V91_COMPLETE_SUMMARY.md](../docs/v91/V91_COMPLETE_SUMMARY.md) | 🚀 V9.1 COMPLETE SUMMARY - Autonomous Quant Lab with AI Portfolio Brain |

## Divers

| Fichier | Titre |
|---------|-------|
| [BADGES_README.md](../docs/ci/BADGES_README.md) | Badges à ajouter en haut de votre README.md |
| [BANDIT_SECURITY_DOC.md](../docs/ci/BANDIT_SECURITY_DOC.md) | Bandit security scan job for GitHub Actions |
| [CODECOV_UPLOAD_DOC.md](../docs/ci/CODECOV_UPLOAD_DOC.md) | GitHub Actions job to upload coverage to Codecov |
| [CONFIG_REFERENCE_V91.md](../docs/CONFIG_REFERENCE_V91.md) | ⚙️ V9.1 CONFIGURATION REFERENCE |
| [CSV_POPULATION_FORMAT.md](../CSV_POPULATION_FORMAT.md) | Format attendu des fichiers CSV de population |
| [DISCORD_NOTIFY_DOC.md](../docs/notifications/DISCORD_NOTIFY_DOC.md) | Exemple de job GitHub Actions pour notifier sur Discord après un build |
| [DOCS_AUTOMATION.md](../docs/DOCS_AUTOMATION.md) | Améliorations automatiques pour la documentation & onboarding |
| [DOCUMENTATION.md](../DOCUMENTATION.md) | Documentation — crypto_ai_terminal |
| [DOCUMENTATION_AUTOMATIQUE.md](../docs/DOCUMENTATION_AUTOMATIQUE.md) | 📚 Documentation automatique – Crypto AI Terminal |
| [DOCUMENTATION_INDEX.md](../docs/DOCUMENTATION_INDEX.md) | 📚 MASTER DOCUMENTATION INDEX - V9.1 System |
| [DOC_AUTO.md](../docs/divers/DOC_AUTO.md) | Documentation automatique du projet Quant AI Terminal |
| [HOME.md](../docs/HOME.md) | Page d’accueil personnalisée pour la documentation Crypto AI Terminal |
| [PROJECT_CONTEXT_EXPORT_CLAUDE_FR.md](../docs/divers/PROJECT_CONTEXT_EXPORT_CLAUDE_FR.md) | Contexte projet — `crypto_ai_terminal` (export pour Claude / autre IA) |
| [PROMPT_POUR_GPT.md](../docs/divers/PROMPT_POUR_GPT.md) | 🤖 PROMPT POUR GPT - Analyse & Conseils Architecture V9 |
| [README.md](../README.md) | 🛡️ Robustesse & Audit (avril 2026) |
| [README_CONSOLIDATED.md](../README_CONSOLIDATED.md) | 🛡️ Audit & Robustesse (avril 2026) |
| [README_profiler_monitoring.md](../docs/modules/README_profiler_monitoring.md) | Readme Profiler Monitoring |
| [README_strategy_factory_config.md](../docs/modules/README_strategy_factory_config.md) | Configuration centralisée : strategy_factory_config.ini |
| [SLACK_NOTIFY_DOC.md](../docs/notifications/SLACK_NOTIFY_DOC.md) | Exemple de job GitHub Actions pour notifier sur Slack après un build |
| [SPHINX_README.md](../docs/SPHINX_README.md) | Sphinx quickstart config for API doc generation |
| [TEAMS_NOTIFY_DOC.md](../docs/notifications/TEAMS_NOTIFY_DOC.md) | Exemple de job GitHub Actions pour notifier sur Microsoft Teams après  |

---

*Genere par `project_os/doc_indexer.py` le 2026-05-13 11:26.*
*110 fichiers .md indexes.*
