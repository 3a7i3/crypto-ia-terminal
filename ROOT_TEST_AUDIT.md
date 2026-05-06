# Audit cible des `test_*.py` racine

Date: 2026-05-05

## Objectif

Séparer les fichiers racine `test_*.py` entre:

- vrais tests à migrer sous `tests/`
- validateurs manuels à renommer ou déplacer hors du pattern `test_*.py`
- cas ambigus qui demandent une revue plus profonde avant migration

## Déjà migré dans ce lot

- `test_genome.py` -> `tests/test_run_strategy_factory_genome.py`
- `test_mutation_extreme.py` -> `tests/test_run_strategy_factory_mutation.py`
- `test_run_strategy_factory.py` -> `tests/test_run_strategy_factory_main.py`
- `test_validate_population_csv.py` -> `population_csv_validator.py` + `tests/test_validate_population_csv.py` + `scripts/validate_population_csv.py`
- `test_ui_utils.py` -> `tests/test_ui_utils.py`
- `test_streamlit_dashboard.py` -> `tests/test_streamlit_dashboard.py`
- `test_onboarding_script.py` -> `tests/test_onboarding_script.py`
- `test_integration_workflow.py` -> `tests/test_integration_workflow.py` avec artefacts de plot isolés et `skip` propre si `matplotlib` manque
- `test_integration_multimodule.py` -> `tests/test_integration_multimodule.py` avec logging/notifier déterministe et `skip` propre si `matplotlib` manque
- `test_boot_system.py` -> `scripts/boot_system_validator.py`
- `test_panels_with_report.py` -> `scripts/panels_with_report.py`
- `test_performance_benchmarks.py` -> `scripts/performance_benchmarks.py`
- `test_evolution_3d_view.py` -> `tests/test_evolution_3d_view.py`
- `test_evolution_3d_view_main.py` -> `tests/test_evolution_3d_view_main.py`
- `test_visualize_strategy_ecosystem.py` -> `tests/test_visualize_strategy_ecosystem.py`
- `test_visualize_strategy_ecosystem_all_gens.py` -> `tests/test_visualize_strategy_ecosystem_all_gens.py`
- `test_dashboard_launch.py` -> `scripts/dashboard_launch.py`
- `test_alert_dashboard_csv_export.py` -> `scripts/alert_dashboard_csv_export.py`
- `test_alert_dashboard_playwright_csv.py` -> `scripts/alert_dashboard_playwright_csv.py`
- `test_optimization_stack.py` -> `scripts/optimization_stack_validator.py`
- `test_plotly_matplotlib_compat.py` -> `scripts/plotly_matplotlib_compat.py`
- `test_streamlit_onboarding_integration.py` -> `scripts/streamlit_onboarding_integration.py`
- `test_stream_bus.py` -> `scripts/stream_bus_simulation.py`
- `test_onboarding_logging.py` -> `tests/test_onboarding_script.py`
- `test_dataframe_tracking.py` -> `tests/test_run_strategy_factory_genome.py`
- `test_imports_all_modules.py` -> `tests/test_import_smoke.py`
- `test_robustness.py` -> `tests/test_run_strategy_factory_genome.py` + `tests/test_validate_population_csv.py`

## A migrer vers `tests/`

- Aucun dans l'immédiat.

## A renommer ou déplacer en script manuel

- Aucun dans l'immédiat.

## Revue complémentaire avant décision

- `test_analyze_strategy_niches.py`: dépend de reload et patchs de modules, à fiabiliser avant migration.
- `test_fallbacks_intelligents.py`: mélange cas unitaires et dépendances réseau simulées.
- `test_fullsuite.py`: mélange de plusieurs responsabilités et d’artefacts visuels.
- `test_onboarding_feedback_playwright.py`: dépendance navigateur/temporisation.
- `test_plot_god_mode.py`: rendu graphique à rendre déterministe.
- `test_security_permissions.py`: très dépendant de l’OS et des permissions locales.

## Dépendances optionnelles vérifiées localement

- `matplotlib` est maintenant installé dans la `.venv`, ce qui rend exécutables ici les validateurs hérités basés sur `run_strategy_factory.py`.
- `playwright` reste une dépendance optionnelle pour `scripts/alert_dashboard_playwright_csv.py`; le script affiche désormais la commande d’installation requise si le package ou les navigateurs manquent.
- `kaleido` reste une dépendance optionnelle pour `scripts/plotly_matplotlib_compat.py` afin de tester l'export Plotly PNG/SVG; le script affiche maintenant la commande d'installation requise si l'export n'est pas disponible.

## Politique proposee

- `tests/`: uniquement couverture `pytest` collectable et relativement déterministe.
- `scripts/`: validateurs manuels, benchmarks, runners opérateur, smoke tests bavards.
- `e2e` ou marqueurs `integration` / `e2e`: flows navigateur, subprocess, réseau local.