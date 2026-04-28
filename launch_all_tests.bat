@echo off
REM Lancer tous les tests du projet (y compris quant-ai-system) et générer le rapport global
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
    echo [ERREUR] L'environnement virtuel .venv n'existe pas. Lancez d'abord install_all.ps1
    exit /b 1
)
.venv\Scripts\python.exe run_all_tests.py
if %errorlevel% neq 0 (
    echo [ERREUR] Certains tests ont échoué. Voir all_tests_report.md
    exit /b %errorlevel%
) else (
    echo [OK] Tous les tests sont passés. Voir all_tests_report.md
)
