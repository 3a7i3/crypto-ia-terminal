@echo off
title Crypto AI Terminal — Command Center Dashboard
cd /d "%~dp0"

set PYTHON=.venv\Scripts\python.exe

if not exist %PYTHON% (
    echo ERREUR: venv introuvable.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Command Center Dashboard
echo   Ouvrir dans le navigateur : http://localhost:8501
echo  ============================================
echo.

REM Ouvrir le navigateur apres 3 secondes
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8501"

%PYTHON% -m streamlit run command_center_dashboard.py --server.port 8501 --server.headless true
pause
