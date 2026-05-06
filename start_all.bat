@echo off
title Crypto AI Terminal — Lancement complet
cd /d "%~dp0"
 
echo.
echo  ============================================
echo   Crypto AI Terminal — Lancement complet
echo  ============================================
echo.

set PYTHON=.venv\Scripts\python.exe

if not exist %PYTHON% (
    echo ERREUR: venv introuvable.
    pause
    exit /b 1
)

echo Validation du systeme...
%PYTHON% test_boot_system.py --fast

echo.
echo Lancement du bot de trading...
start "Bot de Trading" cmd /k "%PYTHON% advisor_loop.py"

timeout /t 5 /nobreak >/dev/null

echo Lancement du dashboard...
start "Command Center" cmd /k "%PYTHON% -m streamlit run command_center_dashboard.py --server.port 8501 --server.headless true"

timeout /t 5 /nobreak >/dev/null
start http://localhost:8501

echo.
echo Bot lance + Dashboard sur http://localhost:8501
echo.
pause
