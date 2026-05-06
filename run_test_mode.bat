@echo off
REM ============================================================
REM  run_test_mode.bat
REM  Lance advisor_loop en mode test forcé.
REM  A executer dans une cmd ADMIN si tu veux que le resync
REM  d'horloge fonctionne (sinon il sera juste skippe).
REM ============================================================

cd /d "%~dp0"

echo.
echo === [1/4] Resync horloge Windows (cause racine du faux DD) ===
net start w32time >nul 2>&1
w32tm /resync /force
if errorlevel 1 (
    echo [WARN] Resync echoue - relance ce .bat en admin si DD revient.
) else (
    echo [OK] Horloge resynchronisee.
)

echo.
echo === [2/4] Variables d'environnement test mode ===
set GATE_MIN_SCORE_OVERRIDE=50
set FORCE_TEST_EXECUTION=true
echo GATE_MIN_SCORE_OVERRIDE=%GATE_MIN_SCORE_OVERRIDE%
echo FORCE_TEST_EXECUTION=%FORCE_TEST_EXECUTION%

echo.
echo === [3/4] mistake_memory deja vide (fait par Claude) ===
if exist "databases\mistake_memory.jsonl" (
    for %%I in ("databases\mistake_memory.jsonl") do (
        if %%~zI==0 (
            echo [OK] Fichier vide, aucune regle de blocage.
        ) else (
            echo [INFO] Fichier non vide ^(%%~zI octets^) - reset...
            type nul > "databases\mistake_memory.jsonl"
            echo [OK] Reset effectue.
        )
    )
) else (
    echo [INFO] Fichier absent - rien a faire.
)

echo.
echo === [4/4] Lancement advisor_loop ===
echo.
".venv\Scripts\python.exe" advisor_loop.py

pause
