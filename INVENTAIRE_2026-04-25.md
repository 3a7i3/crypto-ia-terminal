# Inventaire du projet `crypto_ai_terminal` — V2 complète

**Date** : 25 avril 2026
**Statut** : V2 — corrige et étend le rapport initial qui était basé sur des données tronquées
**Méthode** : exploration shell complète (`ls`, `du`, `find`, `git log`)

---

## ⚠️ Avertissement (à lire en premier)

Le projet est **bien plus large** que ce que la doc V9.1 laissait entendre :

- ~3,5 GB sur disque (dont 2,9 GB d'archives + 510 MB de `_old/`)
- 25 dossiers racine, 61 fichiers `.md` racine, 48 scripts `.bat`/`.ps1`, 120+ fichiers Python directement à la racine
- **6 sous-systèmes** distincts cohabitent — pas un seul bot V9.1
- ~206 fichiers racine modifiés dans les dernières 24 h → activité intense récente
- Branche Git active : `chore/safe-archive-legacy-folders` → tu avais déjà commencé un nettoyage avant
- Plusieurs branches `copilot/*` → des sessions d'agents IA précédentes ont travaillé en parallèle

**Le bot ne tourne pas** principalement parce que (a) plusieurs sous-stacks coexistent sans arbitre clair, (b) certains dossiers semblent avoir perdu du contenu lors d'un sync récent (ex : `strategy_factory/` racine n'a qu'1 fichier alors que tu y travailles), (c) les ops scripts pointent vers des chemins de l'ancienne organisation.

---

## 1. Vue Git

| Élément | Valeur |
|---|---|
| Repo distant | `0xl1v/crypto-ai-terminal` (GitHub) |
| Branche active | `chore/safe-archive-legacy-folders` |
| Dernier commit "humain" | `2026-03-19` — *Initial commit* sur master |
| Commits récents | `Session 019d47b6-... checkpoint turn N` (sessions d'agent IA) |
| Branches locales | 5 (master, copilot/*×2, agents/*×2, chore/safe-archive-legacy-folders) |
| Branches remote | 8 (master, main, copilot/*×6) |
| `git status` | Vide (pas de modifs non-commitées détectées dans le tracking, mais beaucoup de fichiers gitignored) |
| `.gitignore` couvre | `logs/`, `*.log`, `__pycache__/`, `*.pyc`, `.env`, `.venv/`, `data/`, `*.csv` |

**Remarque** : `data/` et `*.csv` sont gitignored, donc tout ce qui est dans `_old/results/`, `archives/ecosystem_*/` et les CSV racine n'est pas versionné. Sécurité pour l'archivage : **rien d'important n'est tracké dans ces zones**.

---

## 2. Empreinte disque par dossier

| Dossier | Taille | Statut |
|---|---|---|
| `archives/` | **2.9 GB** | 7 snapshots ecosystem × 416 MB (mars 19-20) — possibles doublons |
| `_old/` | **510 MB** | Legacy (V13/V16/V26/V30, bot-v3, quant-ai-system, etc.) |
| `.git/` | 31 MB | Normal |
| `docs/` | 12 MB | Doc générée |
| `quant_hedge_ai/` | 2.6 MB | V9.1 — système actif |
| `__pycache__/` (racine) | 780 KB | Caches Python à la racine — anormal |
| `tests/` | 248 KB | Tests |
| `reports/` | 140 KB | Rapports |
| `results/` | 100 KB | Résultats |
| `archive_results/` | 80 KB | Archive de résultats |
| `data/` | 80 KB | CSV bitcoin |
| `.github/` | 88 KB | Agents/prompts/instructions GitHub |
| `supervision/` | 64 KB | Bot doctor + notifications |
| `scripts/` | 64 KB | Scripts de setup/verify |
| `logs/` | 28 KB | Logs setup_verify |
| `dashboard/`, `databases/`, `strategy_factory/`, `terminal_core/`, `install/`, `tickets/`, `ai_autonomous_loop/`, `crypto_quant_v16/`, `quant-hedge-ai/`, `feedback_logs/`, `k8s/` | < 50 KB chacun | **Squelettes / dossiers presque vides** |

**Findings critiques :**

- **`archives/`** : 7 snapshots `ecosystem_2026031{9,9,9,9,9,9,20}_*` créés à quelques minutes d'intervalle. Très probablement des copies quasi-identiques. À dédupliquer.
- **Dossiers presque vides** : `dashboard/` (1 fichier), `databases/` (1 fichier JSON), `strategy_factory/` (1 fichier), `terminal_core/` (3 fichiers), `install/` (1 .md), `crypto_quant_v16/` (3 fichiers stub), `quant-hedge-ai/` (5 fichiers wrapper), `ai_autonomous_loop/` (2 fichiers). Soit ce sont des squelettes/placeholders, soit du contenu a été perdu lors d'un sync.
- **`feedback_logs/`** : 190 fichiers (taille négligeable) — probablement des logs JSONL.

---

## 3. Les 6 sous-systèmes identifiés

### Stack A — V9.1 Quant Lab (le seul bien documenté)

- Code : `quant_hedge_ai/` (avec underscore)
- Entry : `quant_hedge_ai/main_v91.py`
- Doc : `V91_COMPLETE_SUMMARY.md`, `README_V91.md`, `CONFIG_REFERENCE_V91.md`, `RAPPORT_GLOBAL_V9.md`
- Statut : code propre, ~100 fichiers .py, 20 agents, dashboards Panel
- **Note** : `quant-hedge-ai/` (avec tiret) est un wrapper compat qui fait `runpy` vers le vrai code

### Stack B — Strategy Farm / Evolution Lab (le code "racine")

- Entry : `main.py` à la racine
- Modules clés : `evolution_core.py` (21 KB), `evolution_dashboard.py` (13 KB), `evolution_3d_view.py` (41 KB), `streamlit_dashboard.py` (47 KB)
- Pipeline : `automate_pipeline.py`, `orchestrate_all.py`, `orchestrate_ecosystem.py`
- Stockage : `strategy_lab.sqlite`, `alpha_vault_export.json` (72 KB), `alpha_vault_test.json`
- Doc : `EVOLUTION_DASHBOARD.md`, `CHECKLIST_DASHBOARD_3D.md`, `AIDE_GPT_EVOLUTION_DASHBOARD_FR.md`, `TUTORIEL_EVOLUTION_DASHBOARD_FR.md`, etc.
- Statut : c'est ce qui semble **le plus actif** aujourd'hui (gros fichiers, modifs récentes)

### Stack C — Strategy Factory + Alpha Vault

- Entry : `run_strategy_factory.py` (22 KB), `run_strategy_factory_batch.py`, `run_strategy_factory_large.py`
- Modules : `strategy_factory/backtest_profiler.py` (à la racine), `analyze_strategy_niches.py`
- Tests : `test_run_strategy_factory.py`, `test_analyze_strategy_niches.py`
- Doc : `README_strategy_factory_config.md`, `BANDIT_SECURITY_DOC.md`
- Config : `strategy_factory_config.ini`, `batch_configs.json`
- Statut : actif (tu l'as confirmé)

### Stack D — Supervision / Monitoring / Bot Doctor

- Module : `supervision/` — `bot_doctor.py`, `alert_manager.py`, `monitoring_profiler.py`, `botdoctor_dashboard.py`
- Notifications : `supervision/notifications/` — Slack, Telegram, multi-channel
- Entry root : `supervise_all.py`, `surveillance_continue.py`, `notifications.py`, `notify_test_status.py`
- Doc : `SLACK_NOTIFY_DOC.md`, `DISCORD_NOTIFY_DOC.md`, `TEAMS_NOTIFY_DOC.md`, `DOC_NOTIFY_TEST_STATUS.md`
- Launchers : `launch_botdoctor_api.bat`, `launch_botdoctor_dashboard.bat`, `launch_alert_dashboard.bat`, `launch_feedback_dashboard.bat`, `launch_monitoring_api.bat`

### Stack E — CI/CD / Tests / Onboarding

- Tests racine : ~35 fichiers `test_*.py` (alert_dashboard, evolution_3d, fullsuite, integration, mutation, onboarding, panels, plotly, robustness, security, stream_bus, ui_utils...)
- CI : `pytest.ini`, `conftest.py`, `.coveragerc`, `codecov.yml`, `.gitlab-ci.yml`, `.pre-commit-config.yaml`, `requirements-ci.txt`, `requirements-dev.txt`
- Reports : `all_tests_output.txt`, `panel_test_report.txt`, `panel_http_report.txt`, `generate_html_report.py`, `panel_ci_report.py`
- Onboarding : `ONBOARDING_SCRIPT.py`, `ONBOARDING_QUICK_START.md`, `test_onboarding_*.py` (4 fichiers)
- Docker/k8s : `Dockerfile`, `docker-compose.yml`, `k8s/`
- Doc : `BADGES_README.md`, `CODECOV_UPLOAD_DOC.md`, `TESTS_CI_DOC.md`, `TEST_ISOLATION_GUIDE.md`

### Stack F — Tickets / Backlog

- `tickets/` : 27 fichiers .md organisés en 4 catégories (docs, install, orchestration, tests)
- Format : tickets numérotés, ressemble à un backlog d'amélioration

---

## 4. La forêt de docs (61 fichiers .md racine)

**Catégories principales** (cluster automatique sur les noms) :

| Cluster | Exemples | Nombre |
|---|---|---|
| V9.1 / Roadmap | `V91_COMPLETE_SUMMARY`, `V10_IMPLEMENTATION_ROADMAP`, `ROADMAP_V9_V10_V11`, `RAPPORT_GLOBAL_V9`, `CONFIG_REFERENCE_V91`, `QUICK_START_V91`, `VALIDATION_CHECKLIST`, `PROJECT_INVENTORY`, `PROJECT_COMPLETION_SUMMARY` | 9 |
| Evolution Dashboard / 3D | `AIDE_GPT_EVOLUTION_DASHBOARD_FR`, `CHECKLIST_DASHBOARD_3D`, `DOCUMENTATION_EVOLUTION_DASHBOARD`, `DOCUMENTATION_EVOLUTION_DASHBOARD_EN`, `FAQ_EVOLUTION_DASHBOARD_FR`, `FAQ_EVOLUTION_DASHBOARD_EN`, `GPT_HELP_EVOLUTION_DASHBOARD_EN`, `TUTORIAL_EVOLUTION_DASHBOARD_EN`, `TUTORIEL_EVOLUTION_DASHBOARD_FR` | 9 |
| Dashboards autres | `DASHBOARDS_AUDIT_REPORT`, `DASHBOARDS_README`, `DASHBOARD_USAGE_TEMPLATES` | 3 |
| Tests / CI / Sécurité | `BADGES_README`, `BANDIT_SECURITY_DOC`, `CODECOV_UPLOAD_DOC`, `TESTS_CI_DOC`, `TEST_ISOLATION_GUIDE` | 5 |
| Notifications / Discord / Slack / Teams | `DISCORD_NOTIFY_DOC`, `SLACK_NOTIFY_DOC`, `TEAMS_NOTIFY_DOC`, `DOC_NOTIFY_TEST_STATUS` | 4 |
| Cloud / Déploiement | `CLOUD_DEPLOYMENT_DEMO`, `DEPLOIEMENT_CLOUD_GUIDE`, `UPDATE_DEPLOY_GUIDE` | 3 |
| Onboarding / Quick start | `ONBOARDING_QUICK_START`, `DEMARRAGE_RAPIDE_FR`, `CHECKLIST_DEMARRAGE_COMPLET`, `README`, `README_CONSOLIDATED` | 5 |
| Rapports d'audit | `RAPPORT_FINAL_AUDIT`, `RAPPORT_FINAL_SUPERVISION`, `RAPPORT_SANTE_GLOBAL`, `RAPPORT_FONCTIONS_PROJET`, `all_tests_report.md`, `test_report.md` | 6 |
| Action plans / Checklists | `ACTION_PLAN_CHECKLIST`, `CHECKLIST_ROBUSTESSE`, `orchestration_improvement_plan`, `PROPOSITIONS_AUTOMATION` | 4 |
| Divers / Format / Extension | `CHATBOT_EXTENSION`, `CSV_POPULATION_FORMAT`, `DOCUMENTATION_AUTOMATIQUE`, `DOC_AUTO`, `DOCUMENTATION_INDEX`, `PROJECT_CONTEXT_EXPORT_CLAUDE_FR`, `PROMPT_POUR_GPT`, `INVENTAIRE_2026-04-25` (ce doc), `README_profiler_monitoring`, `README_strategy_factory_config` | 10 |

**Beaucoup de doublons probables** : 2× README, 2× Tutorial Evolution (FR/EN), 2× FAQ Evolution (FR/EN), 2× Documentation Evolution (FR/EN), 2× Démarrage (FR + Quick Start), 2× Rapport audit (Final + Santé Global)…

---

## 5. La forêt de scripts (48 .bat/.ps1 racine)

**Launchers identifiés** (groupés par cible) :

| Cible | Scripts |
|---|---|
| All / orchestration | `start_all.bat`, `stop_all.bat`, `launch_all.bat`, `launch_all.ps1`, `launch_all_visible.bat`, `launch_all_with_env.bat`, `launch_all_ps.bat`, `launch_all_ps_visible.bat`, `launch_all_ps_with_env.bat` (9 variantes !) |
| Dashboards | `launch_dashboard_advanced.bat`, `launch_dashboard_api.bat`, `launch_dashboard_fastapi.bat`, `launch_dashboard_quant_terminal.bat`, `launch_dash_app.bat`, `launch_quant_dashboard_v16.bat`, `launch_quant_terminal_v12.bat`, `launch_v12_dashboard.bat`, `launch_alert_dashboard.bat`, `launch_botdoctor_dashboard.bat`, `launch_evolution_dashboard.bat`, `launch_evolution_3d_view.bat`, `launch_feedback_dashboard.bat`, `launch_panel_overview.bat`, `launch_equity_curve_streamlit.bat` (15) |
| API | `launch_api_rest.bat`, `launch_botdoctor_api.bat`, `launch_dashboard_api.bat`, `launch_dashboard_fastapi.bat`, `launch_monitoring_api.bat`, `launch_orchestrator_api.bat` (6) |
| Tests | `launch_all_tests.bat`, `run_all_tests.ps1`, `run_alpha_discovery_test.bat`, `run_quant_ai_system_tests.bat`, `run_strategy_lab_tests.bat`, `run_strategy_lab_unit.bat` (6) |
| Healthcheck / monitoring | `healthcheck_v27.bat`, `healthcheck_v27.ps1`, `verif_auto.ps1`, `diagnose_python_env.ps1` (4) |
| Setup / install / venv | `ONE_CLICK_SETUP_VERIFY.bat`, `install_all.ps1`, `install_and_test.ps1`, `setup_quant_matrix_venv.ps1`, `reset_quant_matrix_venv.ps1`, `install_surveillance_task.ps1` (6) |
| Docs / build | `build_docs.ps1` |
| Git / push | `push_with_message.ps1` |
| Misc | `automate_pipeline_task.ps1`, `set_smtp_env.ps1`, `run_precommit.ps1` |

**9 launchers `launch_all*`** font sans doute presque la même chose avec de petites variantes (visible/invisible, avec/sans env, ps1 vs bat). À consolider.

---

## 6. Fichiers ponctuels à archiver / supprimer

| Fichier | Type | Action évidente |
|---|---|---|
| `netstat_check.txt`, `ports_check.txt`, `ports_check_after_env_launcher.txt`, `runtime_status_final.txt`, `runtime_status_after_stop.txt` | Snapshots ops du 11 mars 2026 | Supprimer |
| `PID` | 1 ligne, reste de session | Supprimer |
| `data/bot.log` | Vide | Supprimer |
| `__init__.py` racine (vide) | 0 octet | Supprimer (sauf si nécessaire à un import) |
| `__pycache__/` racine | 780 KB de caches | Supprimer |
| `*.pyc` un peu partout | Caches | Supprimer |
| `dashboard_startup.log` | 136 octets | Supprimer |
| `quant_system.log` | 207 octets | Supprimer |
| `meta_orchestrator.log` | 1.8 KB | Supprimer (logs gitignored) |
| `panel_http_report.txt`, `panel_test_report.txt`, `all_tests_output*.txt` | Sorties de tests anciens | Archive ou suppression |
| `test_*.png`, `test_*.svg` à la racine (test_heatmap2d, test_matplotlib3d, test_plotly3d) | Outputs de tests visuels | À déplacer dans `tests/outputs/` ou supprimer |
| `export_codebase_mars2026.zip` (5.4 MB) | Vieux export | Supprimer ou déplacer |

---

## 7. Pourquoi le bot ne tourne pas (hypothèses raffinées)

1. **Confusion d'entry points** : `start_all.bat` → `launch_all.bat` → `launch_all.ps1` (qui n'est pas listé / vérifié). 9 variantes co-existent. Aucun ne dit clairement « voici le bot ».
2. **Dossiers vidés** : `strategy_factory/`, `dashboard/`, `databases/`, `terminal_core/` n'ont presque rien dedans alors qu'ils sont importés par du code racine. Probable problème de sync récent.
3. **Stop scripts périmés** : `stop_all.bat` cherche `main_v13.py` (dans `_old/`), `healthcheck_v27.ps1` cherche les ports V12/V13/V16/V27 dont les apps Panel sont dans `_old/crypto_quant_v16/`.
4. **Wrapper compat** : `launch_v12_dashboard.bat` fait `cd quant-hedge-ai` (avec tiret, donc le wrapper) puis `panel serve dashboard\quant_terminal_v12.py` — ça plante car le wrapper n'a pas de dossier `dashboard/`.
5. **Branche cleanup en cours** : tu étais déjà sur `chore/safe-archive-legacy-folders` — il y a un nettoyage qui a été démarré mais pas fini.

---

## 8. Plan de tri proposé — par lots vérifiables

À chaque lot, je te propose précisément, tu valides, j'applique. Aucune action destructive sans ton OK explicite.

### Lot 1 — Caches et artefacts ponctuels (zéro risque)

- Supprimer tous les `__pycache__/` et `*.pyc`
- Supprimer `netstat_check.txt`, `ports_check*.txt`, `runtime_status_*.txt`, `PID`, `data/bot.log`, `dashboard_startup.log`, `quant_system.log`, `meta_orchestrator.log`
- Supprimer `__init__.py` racine vide (à vérifier qu'aucun import racine ne s'en sert)

**Gain attendu** : ~1 MB, mais surtout du bruit en moins à la racine.

### Lot 2 — Déduplication des snapshots `archives/` (gros gain disque)

- Vérifier si les 7 snapshots `archives/ecosystem_2026031{9,9,9,9,9,9,20}_*` sont des doublons
- Garder le plus récent + 1 snapshot du 19 mars en backup
- Supprimer les 5 autres
- Optionnel : zipper le snapshot final pour le sortir du repo de travail

**Gain attendu** : ~2 GB

### Lot 3 — Outputs de tests à ranger

- Créer `tests/outputs/` et y déplacer tous les `test_*.png`, `test_*.svg`, `*.png` de tests racine, `all_tests_output*.txt`, `panel_*_report.txt`
- Garder à la racine : `pytest.ini`, `conftest.py`, `.coveragerc`, `codecov.yml`

### Lot 4 — Consolidation des launchers (un peu plus délicat)

- Auditer ce que font réellement les 9 `launch_all*.bat/ps1`. Garder 1 seul + supprimer les 8 autres
- Réécrire `stop_all.bat` pour ne référencer que les processus/ports actuellement utilisés
- Renommer `healthcheck_v27.*` → `healthcheck.*` et le réécrire pour ne checker que les services actifs
- Garder les launchers spécifiques (`launch_evolution_dashboard.bat`, `launch_botdoctor_*.bat`, etc.)

### Lot 5 — Reorganisation des docs

- Créer `docs/` (existe déjà — vérifier ce qu'il contient avant de fusionner)
- Garder à la racine : `README.md`, `INVENTAIRE_2026-04-25.md`, `QUICK_START_V91.md`, `CONFIG_REFERENCE_V91.md`
- Déplacer le reste dans `docs/` rangé par thème (v91/, evolution/, supervision/, ci/, deployment/, audit-reports/)
- Supprimer les vrais doublons identifiés

### Lot 6 — Diagnostic des dossiers vidés

- Pour chaque dossier presque vide (`strategy_factory/`, `dashboard/`, `databases/`, `terminal_core/`, `ai_autonomous_loop/`, `install/`) :
  - Voir s'il y a un équivalent dans `_old/` ou `archives/`
  - Soit restaurer le contenu manquant, soit acter qu'il est mort et supprimer le dossier
- Décider du sort des stubs : `crypto_quant_v16/` racine, `quant-hedge-ai/` (wrapper)

### Lot 7 — Archivage de `_old/` (510 MB)

- Une fois lots 1-6 faits et le bot relancé proprement
- Zip + déplacer hors du projet vers `C:\Users\WINDOWS\Documents\` (comme prévu)

### Lot 8 — Commit unique

- `git add . && git commit -m "chore: full project cleanup post-inventory V2"`
- Sur la branche `chore/safe-archive-legacy-folders` qui est déjà la bonne branche pour ça

---

## 9. Ce que je recommande de faire MAINTENANT

Plutôt que de tout faire, je propose **3 actions ciblées et vite vérifiables** :

1. **Lot 1 (caches/artefacts)** — sans risque, immédiat, nettoie visuellement
2. **Lot 2 (dédupliquer `archives/`)** — gros gain disque, vérifiable avec `diff`
3. **Diagnostic Lot 6** — identifier si `strategy_factory/`, `dashboard/`, `databases/` sont vraiment vides ou si du contenu manque

Pour le reste (consolidation launchers, réorganisation docs, archivage `_old/`), on attaque ensuite par lots, en relançant le bot entre chaque.

---

## 10. Question structurante restée ouverte

Maintenant qu'on voit qu'il y a 6 sous-systèmes au lieu d'1, l'option "A + C" qu'on avait choisie (= V9.1 seul actif) ne tient plus telle quelle. Il faut redécider :

- Stack A (V9.1) — garder ?
- Stack B (Evolution / Strategy Farm) — garder ? c'est ce qui semble le plus actif
- Stack C (Strategy Factory / Alpha Vault) — garder ? confirmé actif
- Stack D (Supervision / Bot Doctor) — garder ? probablement utile
- Stack E (CI/CD / Tests) — garder, c'est l'infra
- Stack F (Tickets backlog) — garder, c'est ton backlog

Si tu gardes tout, le travail c'est : **clarifier qui est l'entry point principal du projet** et écrire un README qui le dit, puis éliminer les déchets sans toucher aux 6 stacks.

---

*Fin de l'inventaire V2. Prochaine action recommandée : valider les 3 actions du §9, ou poser une question si une partie n'est pas claire.*
