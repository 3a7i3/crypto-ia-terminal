@echo off
title Crypto AI — Dashboard Hub
cd /d "%~dp0"

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

:: ── Dashboard Hub (port 8500) ─────────────────────────────────────────────
netstat -an | findstr ":8500 " >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Dashboard Hub deja actif sur 8500
    goto OPEN
)
echo Demarrage Dashboard Hub ^(port 8500^)...
start /B "" "%PYTHON%" -m streamlit run dashboard_hub.py --server.port 8500 --server.headless true

:OPEN
echo.
echo Attente demarrage ^(5s^)...
timeout /t 5 /nobreak >nul
start "" "http://localhost:8500"

echo.
echo Dashboard Hub : http://localhost:8500
echo.
echo Fermer cette fenetre ne stoppe PAS le dashboard.
echo Pour l'arreter : fermer le processus python dans le gestionnaire des taches.
