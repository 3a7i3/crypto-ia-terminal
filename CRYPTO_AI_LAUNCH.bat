@echo off
title Crypto AI — Terminal Dashboard
cd /d "%~dp0"

:: Vérifie si l'API est déjà active sur 8000
netstat -an | findstr ":8000 " >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo API deja active sur le port 8000
    goto CHECK_REACT
)

:: Lance l'API FastAPI en arrière-plan
echo Demarrage de l'API (port 8000)...
if exist ".venv\Scripts\python.exe" (
    start /B "" ".venv\Scripts\python.exe" -m uvicorn api_server:app --port 8000
) else (
    start /B "" python -m uvicorn api_server:app --port 8000
)

:: Attend que l'API réponde (max 15s)
set /A tries=0
:WAIT_API
timeout /t 2 /nobreak >nul
netstat -an | findstr ":8000 " >nul 2>&1
if %ERRORLEVEL% EQU 0 goto CHECK_REACT
set /A tries+=1
if %tries% LSS 7 goto WAIT_API
echo Timeout — verifiez que uvicorn est installe (pip install uvicorn fastapi)
pause
exit

:CHECK_REACT
:: Vérifie si le dev server React tourne déjà sur 3000
netstat -an | findstr ":3000 " >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Dev server deja actif sur le port 3000 — ouverture du navigateur...
    timeout /t 1 /nobreak >nul
    start "" "http://localhost:3000"
    exit
)

:: Lance le dev server Vite React
echo Demarrage du dashboard React (port 3000)...
set PATH=%USERPROFILE%\nodejs;%PATH%
if exist "frontend\node_modules" (
    start /B "" cmd /c "cd frontend && npm run dev"
) else (
    echo Installation des dependances npm...
    cd frontend
    npm install
    start /B "" npm run dev
    cd ..
)

:: Attend que Vite réponde (max 20s)
set /A tries=0
:WAIT_REACT
timeout /t 2 /nobreak >nul
netstat -an | findstr ":3000 " >nul 2>&1
if %ERRORLEVEL% EQU 0 goto OPEN
set /A tries+=1
if %tries% LSS 10 goto WAIT_REACT
echo Timeout — verifiez que Node.js est installe dans %USERPROFILE%\nodejs
pause
exit

:OPEN
echo Dashboard pret — ouverture...
timeout /t 1 /nobreak >nul
start "" "http://localhost:3000"
