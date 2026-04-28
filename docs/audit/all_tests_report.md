
--- Résultats pour quant-ai-system/quant_ai_tests ---

============================= test session starts =============================
platform win32 -- Python 3.11.8, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\WINDOWS\AppData\Local\Programs\Python\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\WINDOWS\crypto_ai_terminal\quant-ai-system
configfile: pytest.ini
plugins: asyncio-1.3.0, cov-7.1.0, timeout-2.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

quant_ai_tests/test_infrastructure.py::TestNeutraliseInfrastructure::test_neutralise SKIPPED [100%]

============================= 1 skipped in 0.17s ==============================


--- Résultats pour C:\Users\WINDOWS\crypto_ai_terminal\quant_hedge_ai\tests ---

============================= test session starts =============================
platform win32 -- Python 3.11.8, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\WINDOWS\AppData\Local\Programs\Python\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\WINDOWS\crypto_ai_terminal
configfile: pytest.ini
plugins: asyncio-1.3.0, cov-7.1.0, timeout-2.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 0 items

============================ no tests ran in 3.42s ============================


--- Résultats pour C:\Users\WINDOWS\crypto_ai_terminal\tests ---

============================= test session starts =============================
platform win32 -- Python 3.11.8, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\WINDOWS\AppData\Local\Programs\Python\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\WINDOWS\crypto_ai_terminal
configfile: pytest.ini
plugins: asyncio-1.3.0, cov-7.1.0, timeout-2.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 17 items / 2 skipped

tests/test_alert_dashboard_functional.py::test_filtrage_module FAILED    [  5%]
tests/test_alert_dashboard_functional.py::test_export_csv FAILED         [ 11%]
tests/test_alert_dashboard_functional.py::test_filtrage_severity FAILED  [ 17%]
tests/test_alert_dashboard_import.py::test_alert_dashboard_import PASSED [ 23%]
tests/test_alert_manager.py::test_alert_and_autoheal PASSED              [ 29%]
tests/test_backtest_profiler.py::test_backtest_profiler_runs PASSED      [ 35%]
tests/test_backtest_profiler.py::test_backtest_profiler_bad_args PASSED  [ 41%]
tests/test_botdoctor_alert.py::test_alert_on_critical PASSED             [ 47%]
tests/test_botdoctor_alert.py::test_no_alert_on_healthy PASSED           [ 52%]
tests/test_evolution_core.py::test_mutate_changes_genome PASSED          [ 58%]
tests/test_evolution_core.py::test_crossover_combines_genes PASSED       [ 64%]
tests/test_evolution_core.py::test_apply_extinction_removes_rare_species PASSED [ 70%]
tests/test_evolution_core.py::test_evaluate_fitness_sets_values PASSED   [ 76%]
tests/test_evolution_core.py::test_create_population_size PASSED         [ 82%]
tests/test_monitoring_profiler.py::test_monitoring_profiler_runs FAILED  [ 88%]
tests/test_monitoring_profiler.py::test_monitoring_profiler_bad_args FAILED [ 94%]
tests/test_panels_tutorials.py::test_panel_import_and_tutorial FAILED    [100%]

================================== FAILURES ===================================
____________________________ test_filtrage_module _____________________________
tests\test_alert_dashboard_functional.py:34: in test_filtrage_module
    data = dash.load_audit()
           ^^^^^^^^^^^^^^^
E   AttributeError: module 'dashboard.alert_dashboard' has no attribute 'load_audit'
_______________________________ test_export_csv _______________________________
tests\test_alert_dashboard_functional.py:54: in test_export_csv
    data = dash.load_audit()
           ^^^^^^^^^^^^^^^
E   AttributeError: module 'dashboard.alert_dashboard' has no attribute 'load_audit'
___________________________ test_filtrage_severity ____________________________
tests\test_alert_dashboard_functional.py:70: in test_filtrage_severity
    data = dash.load_audit()
           ^^^^^^^^^^^^^^^
E   AttributeError: module 'dashboard.alert_dashboard' has no attribute 'load_audit'
________________________ test_monitoring_profiler_runs ________________________
tests\test_monitoring_profiler.py:8: in test_monitoring_profiler_runs
    assert "Démarrage du monitoring" in result.stdout or "Démarrage du monitoring" in result.stderr
E   AssertionError: assert ('D\xe9marrage du monitoring' in '' or 'D\xe9marrage du monitoring' in '[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n')
E    +  where '' = CompletedProcess(args=['C:\\Users\\WINDOWS\\AppData\\Local\\Programs\\Python\\Python311\\python.exe', 'supervision/monitoring_profiler.py', '--duration', '2'], returncode=0, stdout='', stderr='[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n').stdout
E    +  and   '[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n' = CompletedProcess(args=['C:\\Users\\WINDOWS\\AppData\\Local\\Programs\\Python\\Python311\\python.exe', 'supervision/monitoring_profiler.py', '--duration', '2'], returncode=0, stdout='', stderr='[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n').stderr
______________________ test_monitoring_profiler_bad_args ______________________
tests\test_monitoring_profiler.py:13: in test_monitoring_profiler_bad_args
    assert result.returncode != 0
E   AssertionError: assert 0 != 0
E    +  where 0 = CompletedProcess(args=['C:\\Users\\WINDOWS\\AppData\\Local\\Programs\\Python\\Python311\\python.exe', 'supervision/monitoring_profiler.py', '--duration', 'abc'], returncode=0, stdout='', stderr='[2026-04-24 22:24:19,469][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n').returncode
_______________________ test_panel_import_and_tutorial ________________________
tests\test_panels_tutorials.py:21: in test_panel_import_and_tutorial
    mod = importlib.import_module(modname)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
..\AppData\Local\Programs\Python\Python311\Lib\importlib\__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1204: in _gcd_import
    ???
<frozen importlib._bootstrap>:1176: in _find_and_load
    ???
<frozen importlib._bootstrap>:1147: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:690: in _load_unlocked
    ???
<frozen importlib._bootstrap_external>:936: in exec_module
    ???
<frozen importlib._bootstrap_external>:1074: in get_code
    ???
<frozen importlib._bootstrap_external>:1004: in source_to_code
    ???
<frozen importlib._bootstrap>:241: in _call_with_frames_removed
    ???
E     File "C:\Users\WINDOWS\crypto_ai_terminal\supervision\botdoctor_dashboard.py", line 40
E       st.info("""
E   IndentationError: unexpected indent

During handling of the above exception, another exception occurred:
tests\test_panels_tutorials.py:30: in test_panel_import_and_tutorial
    pytest.fail(f"Erreur import/tutoriel pour {label} ({modname}): {e}")
E   Failed: Erreur import/tutoriel pour BotDoctor Dashboard (supervision.botdoctor_dashboard): unexpected indent (botdoctor_dashboard.py, line 40)
=========================== short test summary info ===========================
FAILED tests/test_alert_dashboard_functional.py::test_filtrage_module - AttributeError: module 'dashboard.alert_dashboard' has no attribute 'load_audit'
FAILED tests/test_alert_dashboard_functional.py::test_export_csv - AttributeError: module 'dashboard.alert_dashboard' has no attribute 'load_audit'
FAILED tests/test_alert_dashboard_functional.py::test_filtrage_severity - AttributeError: module 'dashboard.alert_dashboard' has no attribute 'load_audit'
FAILED tests/test_monitoring_profiler.py::test_monitoring_profiler_runs - AssertionError: assert ('D\xe9marrage du monitoring' in '' or 'D\xe9marrage du monitoring' in '[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n')
 +  where '' = CompletedProcess(args=['C:\\Users\\WINDOWS\\AppData\\Local\\Programs\\Python\\Python311\\python.exe', 'supervision/monitoring_profiler.py', '--duration', '2'], returncode=0, stdout='', stderr='[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n').stdout
 +  and   '[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n' = CompletedProcess(args=['C:\\Users\\WINDOWS\\AppData\\Local\\Programs\\Python\\Python311\\python.exe', 'supervision/monitoring_profiler.py', '--duration', '2'], returncode=0, stdout='', stderr='[2026-04-24 22:24:17,149][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n').stderr
FAILED tests/test_monitoring_profiler.py::test_monitoring_profiler_bad_args - AssertionError: assert 0 != 0
 +  where 0 = CompletedProcess(args=['C:\\Users\\WINDOWS\\AppData\\Local\\Programs\\Python\\Python311\\python.exe', 'supervision/monitoring_profiler.py', '--duration', 'abc'], returncode=0, stdout='', stderr='[2026-04-24 22:24:19,469][WARNING] prometheus_client non install\xe9 : export Prometheus d\xe9sactiv\xe9.\n').returncode
FAILED tests/test_panels_tutorials.py::test_panel_import_and_tutorial - Failed: Erreur import/tutoriel pour BotDoctor Dashboard (supervision.botdoctor_dashboard): unexpected indent (botdoctor_dashboard.py, line 40)
============= 6 failed, 11 passed, 2 skipped in 215.33s (0:03:35) =============


--- Résultats unittest discover ---

          close
0  10000.000000
1  10008.796673
2  10229.250460
3  10089.229016
4   9883.245165

Dernier prix: 10759.029546006406
Image sauvegardée sous synthetic_market_bull.png
Parent 1: {'signal': 'breakout', 'filter': 'none', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '5m'}
Parent 2: {'signal': 'rsi_reversion', 'filter': 'volatility_low', 'risk_model': 'volatility_risk', 'position_model': 'fixed_size', 'timeframe': '5m'}
Mutated Parent 1: {'signal': 'breakout', 'filter': 'none', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '5m'}
Child (crossover): {'signal': 'rsi_reversion', 'filter': 'none', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '5m'}
Population size: 3
{'signal': 'momentum', 'filter': 'none', 'risk_model': 'volatility_risk', 'position_model': 'fixed_size', 'timeframe': '4h'} score: 0.857
{'signal': 'breakout', 'filter': 'none', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '4h'} score: 0.535
{'signal': 'breakout', 'filter': 'volume_spike', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '5m'} score: 0.699
{'signal': 'breakout', 'filter': 'volatility_low', 'risk_model': 'atr_risk', 'position_model': 'risk_parity', 'timeframe': '5m'} score: 1.316
{'signal': 'breakout', 'filter': 'none', 'risk_model': 'fixed_risk', 'position_model': 'risk_parity', 'timeframe': '5m'} score: 1.103
{'signal': 'momentum', 'filter': 'none', 'risk_model': 'atr_risk', 'position_model': 'fixed_size', 'timeframe': '4h'} score: 0.824
{'signal': 'breakout', 'filter': 'volume_spike', 'risk_model': 'atr_risk', 'position_model': 'risk_parity', 'timeframe': '4h'} score: 0.642
{'signal': 'rsi_reversion', 'filter': 'volatility_low', 'risk_model': 'fixed_risk', 'position_model': 'fixed_size', 'timeframe': '5m'} score: 0.907
{'signal': 'momentum', 'filter': 'none', 'risk_model': 'atr_risk', 'position_model': 'fixed_size', 'timeframe': '5m'} score: 0.863
{'signal': 'volatility_expansion', 'filter': 'volatility_low', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '4h'} score: 1.287

Top 3 strategies:
{'signal': 'breakout', 'filter': 'volatility_low', 'risk_model': 'atr_risk', 'position_model': 'risk_parity', 'timeframe': '5m'}
{'signal': 'momentum', 'filter': 'none', 'risk_model': 'atr_risk', 'position_model': 'fixed_size', 'timeframe': '4h'}
{'signal': 'volatility_expansion', 'filter': 'volatility_low', 'risk_model': 'volatility_risk', 'position_model': 'risk_parity', 'timeframe': '4h'}
[AIResearchAgent] Rapport envoyé automatiquement (placeholder)
Rapport de recherche AI Research Agent :
{'patterns_detected': {'volatility_cluster': 0.02122465706579748, 'volume_spike': np.False_, 'regime_shift': np.False_, 'anomaly': np.False_}, 'research_hypotheses': [], 'strategy_recommendations': [], 'explanations': {'general': 'Aucun pattern critique détecté.'}, 'visualizations': ['pattern_chart.png', 'risk_score_plot.png'], 'audit': {'generated_at': '2026-04-25T05:24:53.258880+00:00', 'pattern_count': 4, 'hypothesis_count': 0, 'recommendation_count': 0}}
[OK] Plotly 3D + export PNG/SVG
[OK] Matplotlib 3D + export PNG
[OK] Matplotlib heatmap 2D + export PNG
[DataStorage] Saved CSV: test.csv
[DataStorage] Loading CSV: test.csv
Order sent: BUY



---
**Résultat global : ÉCHEC** (code 1)
