@echo off
title Crypto AI — Dashboards
cd /d "%~dp0"

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

:: ── VPS Data Sync ─────────────────────────────────────────────────────────
echo Demarrage VPS Data Sync ^(30s^)...
start /B "" "%PYTHON%" vps_data_sync.py
timeout /t 3 /nobreak >nul

:: ── Execution Health (port 8509) ──────────────────────────────────────────
netstat -an | findstr ":8509 " >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Execution Health deja actif sur 8509
    goto CHECK_HUB
)
echo Demarrage Execution Health ^(port 8509^)...
start /B "" "%PYTHON%" -m streamlit run execution_health.py --server.port 8509 --server.headless true

:: ── Dashboard Hub (port 8500) ─────────────────────────────────────────────
:CHECK_HUB
netstat -an | findstr ":8500 " >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Dashboard Hub deja actif sur 8500
    goto WAIT
)
echo Demarrage Dashboard Hub ^(port 8500^)...
start /B "" "%PYTHON%" -m streamlit run dashboard_hub.py --server.port 8500 --server.headless true

:WAIT
echo.
echo Attente demarrage ^(5s^)...
timeout /t 5 /nobreak >nul

:: Ouvre les deux dans le navigateur
start "" "http://localhost:8509"
timeout /t 1 /nobreak >nul
start "" "http://localhost:8500"

echo.
echo Dashboards actifs :
echo   Execution Health  : http://localhost:8509
echo   Dashboard Hub     : http://localhost:8500
echo.
echo Fermer cette fenetre ne stoppe PAS les dashboards.
echo Pour les arreter : fermer les processus python dans le gestionnaire des taches.
