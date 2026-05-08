# Arborescence du projet

```
crypto_ai_terminal/
|-- ai_autonomous_loop/
|   |-- __init__.py
|   L-- feedback_dashboard.py
|-- audit/
|   |-- __init__.py
|   |-- decision_trace.py
|   |-- replay_engine.py
|   L-- trade_audit.py
|-- core/
|   |-- quant/
|   |   |-- __init__.py
|   |   L-- logging_alerts.py
|   L-- __init__.py
|-- crypto_quant_v16/
|   |-- ui/
|   |   |-- __init__.py
|   |   L-- quant_dashboard.py
|   L-- __init__.py
|-- dashboard/
|   |-- __init__.py
|   |-- alert_dashboard.py
|   |-- builder.py
|   |-- exporter.py
|   |-- intelligence.py
|   |-- metrics_aggregator.py
|   |-- operator_dashboard_pro.py
|   L-- websocket_dashboard.py
|-- databases/
|   |-- ai_evolution/
|   L-- shadow_execution/
|-- deploy/
|   |-- deploy.sh
|   L-- setup_vps.sh
|-- event_bus/
|   |-- __init__.py
|   |-- bridge.py
|   |-- bus.py
|   L-- events.py
|-- feedback_logs/
|-- install/
|-- k8s/
|   |-- botdoctor-deployment.yaml
|   L-- botdoctor-service.yaml
|-- lm_studio/
|   |-- __init__.py
|   |-- ai_router.py
|   |-- client.py
|   L-- status.py
|-- meta_learning/
|   |-- __init__.py
|   |-- decision_engine.py
|   |-- learner.py
|   |-- memory.py
|   L-- similarity.py
|-- mvp/
|   |-- __init__.py
|   |-- execution_engine_mvp.py
|   |-- market_state_engine.py
|   |-- mvp_orchestrator.py
|   |-- post_trade_learning.py
|   |-- risk_engine_mvp.py
|   |-- signal_engine_mvp.py
|   L-- trade_logger.py
|-- pieuvre/
|   |-- dashboard/
|   |   |-- __init__.py
|   |   L-- tableau_bord.py
|   |-- incidents/
|   |   |-- __init__.py
|   |   |-- models.py
|   |   L-- store.py
|   |-- tentacles/
|   |   |-- __init__.py
|   |   |-- audit_commits.py
|   |   |-- base.py
|   |   |-- evolution.py
|   |   |-- guerison.py
|   |   |-- memoire.py
|   |   |-- performance.py
|   |   |-- resilience.py
|   |   |-- securite.py
|   |   L-- surveillance.py
|   |-- __init__.py
|   L-- brain.py
|-- quant-hedge-ai/
|   |-- example_orchestrator_integration.py
|   |-- main_v91.py
|   |-- test_env_parsing_v91.py
|   L-- test_research_strategy_agent_skip.py
|-- quant_hedge_ai/
|   |-- _legacy/
|   |   |-- archived_modules/
|   |   |   |-- intelligence/
|   |   |   |   |-- __init__.py
|   |   |   |   L-- regime_detector.py
|   |   |   |-- liquidity_map/
|   |   |   |   |-- __init__.py
|   |   |   |   L-- flow_analyzer.py
|   |   |   |-- market_radar/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- anomaly_detector.py
|   |   |   |   |-- radar_core.py
|   |   |   |   |-- social_scanner.py
|   |   |   |   |-- token_scanner.py
|   |   |   |   L-- whale_tracker.py
|   |   |   |-- massive_backtest_engine/
|   |   |   |   |-- batch_manager.py
|   |   |   |   |-- cache_manager.py
|   |   |   |   |-- engine.py
|   |   |   |   |-- parallel_executor.py
|   |   |   |   |-- ranking.py
|   |   |   |   L-- results_collector.py
|   |   |   L-- research/
|   |   |       |-- __init__.py
|   |   |       |-- feature_engineer.py
|   |   |       |-- model_builder.py
|   |   |       |-- paper_analyzer.py
|   |   |       L-- strategy_researcher.py
|   |   |-- orphan_tests/
|   |   |   |-- test_flow_analyzer.py
|   |   |   |-- test_liquidity_flow_map.py
|   |   |   |-- test_liquidity_flow_map_multiword.py
|   |   |   L-- test_market_radar.py
|   |   L-- __init__.py
|   |-- agents/
|   |   |-- execution/
|   |   |   |-- execution_v2/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- execution_optimizer.py
|   |   |   |   |-- optimal_timing_engine.py
|   |   |   |   L-- slippage_predictor.py
|   |   |   |-- __init__.py
|   |   |   |-- arbitrage_agent.py
|   |   |   |-- execution_engine.py
|   |   |   |-- latency_monitor.py
|   |   |   |-- liquidity_agent.py
|   |   |   |-- live_signal_engine.py
|   |   |   |-- multi_timeframe_signal.py
|   |   |   |-- order_deduplicator.py
|   |   |   |-- paper_trading_engine.py
|   |   |   |-- position_manager.py
|   |   |   |-- shadow_engine.py
|   |   |   |-- signal_engine.py
|   |   |   |-- subaccount_manager.py
|   |   |   |-- test_execution_engine.py
|   |   |   |-- test_execution_engine_futures.py
|   |   |   |-- test_order_deduplicator.py
|   |   |   |-- test_paper_trading_engine.py
|   |   |   |-- test_trade_logger.py
|   |   |   |-- trade_logger.py
|   |   |   |-- trade_postmortem.py
|   |   |   L-- trade_replay.py
|   |   |-- intelligence/
|   |   |   |-- v2/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- decision_arbitrator.py
|   |   |   |   |-- hmm_regime_engine.py
|   |   |   |   L-- regime_transition_predictor.py
|   |   |   |-- __init__.py
|   |   |   |-- ai_advisor.py
|   |   |   |-- black_box.py
|   |   |   |-- chief_officer.py
|   |   |   |-- confidence_explainer.py
|   |   |   |-- conviction_engine.py
|   |   |   |-- decision_quality_engine.py
|   |   |   |-- feature_engineer.py
|   |   |   |-- meta_strategy_engine.py
|   |   |   |-- mistake_memory.py
|   |   |   |-- no_trade_layer.py
|   |   |   |-- proactive_alerts.py
|   |   |   |-- regime_detector.py
|   |   |   |-- regret_engine.py
|   |   |   |-- self_awareness_engine.py
|   |   |   |-- test_regime_detector.py
|   |   |   |-- threat_radar.py
|   |   |   L-- weekly_report.py
|   |   |-- market/
|   |   |   |-- microstructure/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- microstructure_engine.py
|   |   |   |   |-- orderbook_analyzer.py
|   |   |   |   L-- spread_predictor.py
|   |   |   |-- __init__.py
|   |   |   |-- historical_fetcher.py
|   |   |   |-- market_scanner.py
|   |   |   |-- multi_timeframe_scanner.py
|   |   |   |-- ohlcv_validator.py
|   |   |   |-- orderflow_agent.py
|   |   |   |-- regime_detector.py
|   |   |   |-- retry_policy.py
|   |   |   |-- test_historical_fetcher.py
|   |   |   |-- test_ohlcv_validator.py
|   |   |   |-- test_retry_policy.py
|   |   |   L-- volatility_agent.py
|   |   |-- monitoring/
|   |   |   |-- __init__.py
|   |   |   |-- performance_monitor.py
|   |   |   |-- prompt_doctor_agent.py
|   |   |   L-- system_monitor.py
|   |   |-- onchain/
|   |   |   |-- __init__.py
|   |   |   |-- blockchain_ingester.py
|   |   |   |-- exchange_flow_tracker.py
|   |   |   L-- whale_behavior_classifier.py
|   |   |-- portfolio/
|   |   |   L-- __init__.py
|   |   |-- quant/
|   |   |   |-- __init__.py
|   |   |   |-- backtest_lab.py
|   |   |   |-- monte_carlo.py
|   |   |   |-- portfolio_optimizer.py
|   |   |   |-- stress_test.py
|   |   |   |-- test_backtest_lab.py
|   |   |   |-- test_walk_forward.py
|   |   |   L-- walk_forward.py
|   |   |-- research/
|   |   |   |-- __init__.py
|   |   |   |-- feature_engineer.py
|   |   |   |-- model_builder.py
|   |   |   |-- paper_analyzer.py
|   |   |   L-- strategy_researcher.py
|   |   |-- risk/
|   |   |   |-- __init__.py
|   |   |   |-- capital_allocation_engine.py
|   |   |   |-- drawdown_guard.py
|   |   |   |-- executive_override.py
|   |   |   |-- exposure_manager.py
|   |   |   |-- global_risk_gate.py
|   |   |   |-- order_sizer.py
|   |   |   |-- portfolio_brain.py
|   |   |   |-- risk_dashboard_api.py
|   |   |   |-- risk_monitor.py
|   |   |   |-- session_guard.py
|   |   |   |-- test_drawdown_guard.py
|   |   |   |-- test_risk_monitor.py
|   |   |   L-- test_session_guard.py
|   |   |-- strategy/
|   |   |   |-- __init__.py
|   |   |   |-- genetic_optimizer.py
|   |   |   |-- rl_trader.py
|   |   |   L-- strategy_generator.py
|   |   |-- whales/
|   |   |   L-- __init__.py
|   |   L-- __init__.py
|   |-- ai_evolution/
|   |   |-- v2/
|   |   |   |-- __init__.py
|   |   |   |-- adaptive_calibration_engine.py
|   |   |   |-- model_degradation_monitor.py
|   |   |   L-- unified_learning_layer.py
|   |   |-- __init__.py
|   |   |-- evolution_engine.py
|   |   |-- strategy_memory.py
|   |   L-- strategy_ranker.py
|   |-- dashboard/
|   |   |-- __init__.py
|   |   |-- agent_monitor.py
|   |   |-- ai_dashboard.py
|   |   |-- bot_doctor_panel.py
|   |   |-- control_center.py
|   |   |-- dashboard_ai.py
|   |   |-- dashboard_bot_doctor.py
|   |   |-- dashboard_control_center.py
|   |   |-- dashboard_director.py
|   |   |-- dashboard_quant_terminal.py
|   |   |-- director_dashboard.py
|   |   |-- live_snapshot.py
|   |   |-- operator_dashboard_pro.py
|   |   |-- quant_terminal_v12.py
|   |   |-- system_health.py
|   |   L-- trade_monitor.py
|   |-- databases/
|   |   |-- ai_evolution/
|   |   |-- paper_trading/
|   |   L-- strategy_scoreboard.py
|   |-- engine/
|   |   L-- decision_engine.py
|   |-- features/
|   |   |-- __init__.py
|   |   |-- feature_materializer.py
|   |   |-- feature_registry.py
|   |   |-- feature_store.py
|   |   L-- feature_validator.py
|   |-- liquidity_map/
|   |   |-- __init__.py
|   |   L-- flow_analyzer.py
|   |-- market_radar/
|   |   |-- __init__.py
|   |   |-- anomaly_detector.py
|   |   |-- radar_core.py
|   |   |-- social_scanner.py
|   |   |-- token_scanner.py
|   |   L-- whale_tracker.py
|   |-- strategy_factory/
|   |   |-- __init__.py
|   |   |-- backtester.py
|   |   |-- bot_doctor_validator.py
|   |   |-- factory_core.py
|   |   |-- multi_timeframe_backtester.py
|   |   |-- performance_analyzer.py
|   |   L-- strategy_generator.py
|   |-- strategy_lab/
|   |   |-- __init__.py
|   |   |-- backtest_launcher.py
|   |   |-- batch_runner.py
|   |   |-- evolution_engine.py
|   |   |-- example_pipeline.py
|   |   |-- feature_cache.py
|   |   |-- generator.py
|   |   |-- market_db.py
|   |   |-- parallel_engine.py
|   |   |-- parameter_space.py
|   |   |-- ranker.py
|   |   |-- signal_builder.py
|   |   |-- strategy_db.py
|   |   |-- templates.py
|   |   |-- test_batch_runner.py
|   |   |-- test_evolution_engine.py
|   |   |-- test_market_db.py
|   |   |-- test_parallel_engine.py
|   |   |-- test_performance.py
|   |   |-- test_strategy_db_sqlite.py
|   |   |-- test_strategy_lab.py
|   |   |-- test_strategy_lab_errors.py
|   |   L-- test_strategy_lab_integration.py
|   |-- tests/
|   |   L-- __init__.py
|   |-- __init__.py
|   |-- advisor_only_mode.py
|   |-- backtest_real.py
|   |-- bench_1h_limit.py
|   |-- bench_boot_constructors.py
|   |-- bench_ccxt_cold.py
|   |-- bench_e2e_warmup.py
|   |-- bench_session_contention.py
|   |-- binance_connector.py
|   |-- fetch_audit.py
|   |-- health_endpoint.py
|   |-- main_system.py
|   |-- main_v91.py
|   |-- main_v91.py.broken_backup
|   |-- main_v91.py.broken_v2_backup
|   |-- persistent_warmup.py
|   |-- runtime_config.py
|   |-- setup_binance.py
|   |-- test_dashboard_sector_coverage.py
|   |-- test_dashboard_sector_coverage_full.py
|   |-- test_decision_engine_v91.py
|   |-- test_env_parsing_v91.py
|   |-- test_evolution_engine.py
|   |-- test_prompt_doctor_agent.py
|   L-- test_strategy_factory.py
|-- reports/
|-- results/
|-- scripts/
|   |-- alert_dashboard_csv_export.py
|   |-- alert_dashboard_playwright_csv.py
|   |-- boot_system_validator.py
|   |-- check_badges.py
|   |-- crypto_market_scanner.py
|   |-- crypto_terminal.py
|   |-- dashboard_launch.py
|   |-- demo_p0_integration.py
|   |-- generate_audit_report.py
|   |-- generate_dashboards_table.py
|   |-- generate_panel_screenshots.py
|   |-- install_legacy_py314.ps1
|   |-- minimal_test.py
|   |-- optimization_stack_validator.py
|   |-- panels_with_report.py
|   |-- performance_benchmarks.py
|   |-- plotly_matplotlib_compat.py
|   |-- quickstart.py
|   |-- QUICKSTART_COMPLET_FR.py
|   |-- QUICKSTART_COMPLETE.py
|   |-- run_setup_verify.bat
|   |-- run_testnet_integration.ps1
|   |-- seed_strategy_memory.py
|   |-- setup_and_verify_all.ps1
|   |-- smoke_test_ci.py
|   |-- stream_bus_simulation.py
|   |-- streamlit_onboarding_integration.py
|   |-- TEST_AUDIT_FR.py
|   |-- test_integration_full.py
|   |-- test_panel.py
|   |-- test_phase1_tracker.py
|   |-- test_phase3_metrics.py
|   |-- test_phase4_backtester.py
|   |-- test_phase6_meta_learning.py
|   |-- test_phase7_decision_engine.py
|   |-- test_phase8_9_integration.py
|   |-- test_phase8_dashboard.py
|   |-- test_phase9_audit.py
|   |-- test_python.py
|   |-- test_tracker_scheduler_helper.ps1
|   |-- test_websocket_dashboard.py
|   |-- validate_historical.py
|   |-- validate_population_csv.py
|   |-- verify_all_systems.ps1
|   L-- watch_dashboards.py
|-- strategy_factory/
|   |-- __init__.py
|   |-- alpha_vault.py
|   |-- backtest_profiler.py
|   |-- backtester.py
|   |-- evolution.py
|   |-- generator.py
|   |-- genetic_evolution.py
|   |-- genome.py
|   L-- reproduction.py
|-- supervision/
|   |-- notifications/
|   |   |-- __init__.py
|   |   |-- email_notifier.py
|   |   |-- multi_notifier.py
|   |   |-- ops_notifier.py
|   |   |-- slack_notifier.py
|   |   L-- telegram_notifier.py
|   |-- __init__.py
|   |-- alert_manager.py
|   |-- bot_doctor.py
|   |-- botdoctor_dashboard.py
|   |-- custom_module.py
|   |-- exchange_monitor.py
|   |-- kill_switch.py
|   |-- monitoring_profiler.py
|   |-- ops_watchdog.py
|   |-- performance_watchdog.py
|   |-- self_healing_bot.py
|   |-- telegram_kill_switch.py
|   |-- test_ops_monitoring.py
|   L-- test_supervision.py
|-- terminal_core/
|   |-- quant/
|   |   |-- __init__.py
|   |   L-- logging_alerts.py
|   L-- __init__.py
|-- tests/
|   |-- integration/
|   |   |-- __init__.py
|   |   |-- conftest.py
|   |   |-- test_backtest_pipeline.py
|   |   |-- test_execution_pipeline.py
|   |   |-- test_full_pipeline.py
|   |   L-- test_market_pipeline.py
|   |-- outputs/
|   |-- __init__.py
|   |-- _sim_full.py
|   |-- test_advisor_loop_smoke.py
|   |-- test_advisor_only_mode.py
|   |-- test_ai_advisor.py
|   |-- test_alert_dashboard_functional.py
|   |-- test_alert_dashboard_import.py
|   |-- test_alert_manager.py
|   |-- test_alert_manager_full.py
|   |-- test_auto_decision_engine.py
|   |-- test_backtest_profiler.py
|   |-- test_botdoctor_alert.py
|   |-- test_botdoctor_dashboard.py
|   |-- test_botdoctor_full.py
|   |-- test_event_bus_integration.py
|   |-- test_event_bus_unit.py
|   |-- test_evolution_3d_view.py
|   |-- test_evolution_3d_view_main.py
|   |-- test_evolution_core.py
|   |-- test_evolution_core_coverage.py
|   |-- test_evolution_core_extended.py
|   |-- test_evolution_quantitative.py
|   |-- test_evolve_world.py
|   |-- test_feature_engineer.py
|   |-- test_feature_engineer_extended.py
|   |-- test_full_integration.py
|   |-- test_genome_serializer.py
|   |-- test_global_risk_gate.py
|   |-- test_health_endpoint.py
|   |-- test_import_smoke.py
|   |-- test_integration_full_lifecycle.py
|   |-- test_integration_multimodule.py
|   |-- test_integration_workflow.py
|   |-- test_live_signal_engine.py
|   |-- test_lm_studio.py
|   |-- test_logging_alerts.py
|   |-- test_market_scanner_cache.py
|   |-- test_market_scanner_migration.py
|   |-- test_meta_learner.py
|   |-- test_monitoring_profiler.py
|   |-- test_multi_timeframe.py
|   |-- test_multi_timeframe_backtester.py
|   |-- test_multi_timeframe_scanner.py
|   |-- test_new_modules_coverage.py
|   |-- test_onboarding_script.py
|   |-- test_ops_watchdog.py
|   |-- test_optimization_stack.py
|   |-- test_order_sizer.py
|   |-- test_p0_improvements.py
|   |-- test_p1_advanced_metrics.py
|   |-- test_p1_regime_detection.py
|   |-- test_p2_ml_exit.py
|   |-- test_p2_multi_asset.py
|   |-- test_panels_tutorials.py
|   |-- test_panels_unit.py
|   |-- test_pieuvre.py
|   |-- test_pieuvre_state_machine.py
|   |-- test_proactive_alerts.py
|   |-- test_run_strategy_factory_genome.py
|   |-- test_run_strategy_factory_main.py
|   |-- test_run_strategy_factory_mutation.py
|   |-- test_safe_execution.py
|   |-- test_sidebar_tutorial.py
|   |-- test_streamlit_dashboard.py
|   |-- test_supervise_all.py
|   |-- test_tracker_auto_update.py
|   |-- test_tracker_backward_compat.py
|   |-- test_tracker_dashboard.py
|   |-- test_tracker_exit_dedup.py
|   |-- test_tracker_main_entrypoint.py
|   |-- test_tracker_mixed_events.py
|   |-- test_tracker_mvp_refactor.py
|   |-- test_tracker_optimizer_config.py
|   |-- test_tracker_schema_compat.py
|   |-- test_tracker_schema_validation.py
|   |-- test_tracker_system_builder.py
|   |-- test_trade_postmortem.py
|   |-- test_ui_utils.py
|   |-- test_validate_population_csv.py
|   |-- test_visualize_strategy_ecosystem.py
|   |-- test_visualize_strategy_ecosystem_all_gens.py
|   |-- test_weekly_report.py
|   L-- test_whale_radar_migration.py
|-- tickets/
|   |-- install/
|   |-- orchestration/
|   L-- tests/
|-- tools/
|   L-- analyze_cycles.py
|-- tracker_system/
|   |-- analytics/
|   |   |-- __init__.py
|   |   |-- advanced_metrics.py
|   |   |-- metrics.py
|   |   |-- mfe_mae.py
|   |   L-- regime_analysis.py
|   |-- autonomous/
|   |   L-- auto_decision_engine.py
|   |-- backtest/
|   |   L-- backtest_engine.py
|   |-- backtesting/
|   |   |-- __init__.py
|   |   |-- auto_backtester.py
|   |   L-- simulator.py
|   |-- config/
|   |   |-- __init__.py
|   |   |-- exit_config.py
|   |   L-- settings.py
|   |-- core/
|   |   |-- __init__.py
|   |   |-- event_writer.py
|   |   |-- position_manager.py
|   |   |-- trade_logger.py
|   |   L-- trade_tracker.py
|   |-- dashboard/
|   |   |-- __init__.py
|   |   L-- builder.py
|   |-- engine/
|   |   |-- rules/
|   |   |   |-- __init__.py
|   |   |   |-- breakeven.py
|   |   |   |-- tp_sl.py
|   |   |   L-- trailing.py
|   |   |-- __init__.py
|   |   |-- composite_exit_engine.py
|   |   |-- exit_engine.py
|   |   |-- exit_factory.py
|   |   L-- exit_rules.py
|   |-- exchange/
|   |   L-- binance_client.py
|   |-- exit_engine/
|   |   |-- __init__.py
|   |   |-- base.py
|   |   |-- breakeven.py
|   |   |-- engine.py
|   |   |-- tp_sl.py
|   |   L-- trailing.py
|   |-- intelligence/
|   |   L-- auto_regime_detector.py
|   |-- ml/
|   |   L-- exit_predictor.py
|   |-- portfolio/
|   |   L-- multi_asset.py
|   |-- risk/
|   |   |-- __init__.py
|   |   |-- alert_system.py
|   |   |-- execution_reality.py
|   |   L-- portfolio_risk.py
|   |-- safety/
|   |   L-- safe_execution_framework.py
|   |-- scheduler/
|   |   |-- __init__.py
|   |   L-- auto_update.py
|   |-- storage/
|   |   |-- __init__.py
|   |   |-- loader.py
|   |   L-- saver.py
|   |-- __init__.py
|   |-- auto_backtester.py
|   |-- main.py
|   |-- meta_learner.py
|   |-- meta_memory.py
|   |-- p0_integration.py
|   |-- tracker.py
|   L-- trade_tracker.py
|-- .coverage
|-- .coveragerc
|-- .env
|-- .env.example
|-- .env.smtp.example
|-- .gitattributes
|-- .gitignore
|-- .gitlab-ci.yml
|-- .pre-commit-config.yaml
|-- __init__.py
|-- advisor_loop.py
|-- advisor_runtime_adapters.py
|-- analyze_strategy_niches.py
|-- api_rest.py
|-- automate_pipeline.py
|-- automate_pipeline_task.ps1
|-- automl_tuning.py
|-- bootstrap_integration.py
|-- build_docs.ps1
|-- build_docs.sh
|-- check_imports.py
|-- circuit_breaker.py
|-- clustering.py
|-- codecov.yml
|-- command_center_dashboard.py
|-- COMMANDS.sh
|-- commit_cleanup.bat
|-- config_utils.py
|-- conftest.py
|-- copy_docs_for_sphinx.py
|-- daily_analyzer.py
|-- dashboard_compare_multi.py
|-- dashboard_functions.py
|-- dashboard_live.py
|-- dashboard_positions.py
|-- dashboard_risk.py
|-- data_verifier.py
|-- diagnose_python_env.ps1
|-- diagnose_python_env.sh
|-- diagnostic_env.py
|-- docker-compose.yml
|-- docker_streamlit_fastapi_redis_kafka_demo.ipynb
|-- Dockerfile
|-- evolution_3d_view.py
|-- evolution_core.py
|-- evolution_dashboard.py
|-- evolution_memory.py
|-- exchange_factory.py
|-- export_codebase_mars2026.zip
|-- export_excel_report.py
|-- export_latex_md.py
|-- final_validation.py
|-- generate_ai_quant_lab_structure.py
|-- generate_coverage_report.py
|-- generate_html_report.py
|-- generate_report.py
|-- generate_test_report.py
|-- global_risk_gate.py
|-- healthcheck.bat
|-- healthcheck.ps1
|-- install_all.ps1
|-- install_all.sh
|-- install_and_test.ps1
|-- install_surveillance_task.ps1
|-- launch_alert_dashboard.bat
|-- launch_all.bat
|-- launch_all.ps1
|-- launch_all_tests.bat
|-- launch_all_visible.bat
|-- launch_all_with_env.bat
|-- launch_api_rest.bat
|-- launch_botdoctor_api.bat
|-- launch_botdoctor_dashboard.bat
|-- launch_dash_app.bat
|-- launch_dashboard_advanced.bat
|-- launch_dashboard_api.bat
|-- launch_dashboard_fastapi.bat
|-- launch_dashboard_quant_terminal.bat
|-- launch_equity_curve_streamlit.bat
|-- launch_evolution_3d_view.bat
|-- launch_evolution_dashboard.bat
|-- launch_feedback_dashboard.bat
|-- launch_monitoring_api.bat
|-- launch_orchestrator_api.bat
|-- launch_panel_overview.bat
|-- launch_pieuvre.py
|-- launch_quant_dashboard_v16.bat
|-- launch_quant_terminal_v12.bat
|-- launch_tracker_scheduler.ps1
|-- launch_v12_dashboard.bat
|-- lazy_loader.py
|-- main.py
|-- notifications.py
|-- notify_selenium_report_discord.py
|-- notify_selenium_report_slack.py
|-- notify_test_status.py
|-- observer_logs.py
|-- ONBOARDING_SCRIPT.py
|-- ONE_CLICK_SETUP_VERIFY.bat
|-- orchestrate_all.py
|-- orchestrate_and_test_panels.py
|-- orchestrate_ecosystem.py
|-- orchestrate_internal_panels.py
|-- orchestrate_panels_test.py
|-- panel_ci_report.py
|-- panel_http_test.py
|-- panel_registry.py
|-- panel_selenium_test.py
|-- pareto_front.py
|-- population_csv_validator.py
|-- push_with_message.ps1
|-- pytest.ini
|-- replay_cli.py
|-- reset_quant_matrix_venv.ps1
|-- restore_broken_files.bat
|-- restore_broken_files.ps1
|-- run_all_tests.ps1
|-- run_all_tests.py
|-- run_alpha_discovery_test.bat
|-- run_multi_simulations.py
|-- run_precommit.ps1
|-- run_precommit.sh
|-- run_quant_ai_system_tests.bat
|-- run_strategy_factory.py
|-- run_strategy_factory_batch.py
|-- run_strategy_factory_large.py
|-- run_strategy_lab_tests.bat
|-- run_strategy_lab_unit.bat
|-- run_test_mode.bat
|-- send_orchestration_notification.py
|-- sensitivity_analysis.py
|-- set_smtp_env.ps1
|-- setup.cfg
|-- setup_quant_matrix_venv.ps1
|-- smoke_test_v91.bat
|-- smoke_test_v91.ps1
|-- start_all.bat
|-- START_BOT.bat
|-- START_DASHBOARD.bat
|-- startup_cache.py
|-- status_tracker_scheduler.ps1
|-- stop_all.bat
|-- stop_tracker_scheduler.ps1
|-- strategy_factory_config.ini
|-- strategy_farm_pipeline_demo.ipynb
|-- strategy_farm_scenarios.ipynb
|-- stream_bus.py
|-- streamlit_dashboard.py
|-- stress_test_cli.py
|-- supervise_all.py
|-- surveillance_continue.py
|-- test_alert_dashboard_ui.py
|-- test_analyze_strategy_niches.py
|-- test_boot_system.py
|-- test_fallbacks_intelligents.py
|-- test_fullsuite.py
|-- test_onboarding_feedback_playwright.py
|-- test_onboarding_playwright.py
|-- test_optimization_stack.py
|-- test_orchestrate_ecosystem.py
|-- test_plot_god_mode.py
|-- test_runner_controlled.py
|-- test_security_permissions.py
|-- timeline_animation.py
|-- tracker_scheduler.ps1
|-- tune.py
|-- ui_utils.py
|-- validate_pytest.sh
|-- validate_vault_dashboard.py
|-- verif_auto.ps1
|-- visualization.py
|-- visualize_strategy_ecosystem.py
|-- visualize_strategy_ecosystem_all_gens.py
L-- warm_boot.py
```
