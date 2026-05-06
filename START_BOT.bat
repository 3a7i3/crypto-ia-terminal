@echo off
title Crypto AI Terminal — Bot de Trading
cd /d "%~dp0"

echo.
echo  ============================================
echo   Crypto AI Terminal — Demarrage
echo  ============================================
echo.

REM Utiliser le venv Python 3.11 du projet
set PYTHON=.venv\Scripts\python.exe

REM Verification que le venv existe
if not exist %PYTHON% (
    echo ERREUR: venv introuvable. Lancer: python -m venv .venv
    pause
    exit /b 1
)

REM Validation du systeme avant lancement
echo [1/2] Validation du systeme...
%PYTHON% test_boot_system.py --fast
if errorlevel 1 (
    echo.
    echo ATTENTION: Certains checks ont echoue. Continuer quand meme ? (O/N)
    set /p CONTINUE=
    if /i not "%CONTINUE%"=="O" exit /b 1
)

echo.
echo [2/2] Lancement du bot...
echo Logs: logs\advisor_loop.log
echo Arreter: Ctrl+C
echo.

%PYTHON% advisor_loop.py %*
pause
