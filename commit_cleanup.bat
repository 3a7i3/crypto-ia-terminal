@echo off
REM ============================================================
REM   Commit du nettoyage de la session 2026-04-25 (V2)
REM   Branche : chore/safe-archive-legacy-folders
REM   - Gere l'index corrompu (cross-OS)
REM   - Gere le faux modified CRLF/LF
REM   - Supprime le fichier resaduel ersWINDOWS...
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   ETAPE 1 : Branche actuelle
echo ============================================================
git rev-parse --abbrev-ref HEAD
echo.

echo ============================================================
echo   ETAPE 2 : Nettoyage des residus
echo ============================================================

REM 2a) Supprimer un eventuel lock obsolete laisse par le sandbox Linux
if exist .git\index.lock (
    echo [INFO] Suppression de .git\index.lock
    del /f /q .git\index.lock
)

REM 2b) Supprimer le fichier corrompu cree par redirection avec mauvais escape
if exist ersWINDOWScrypto_ai_terminal (
    echo [INFO] Suppression du fichier corrompu ersWINDOWScrypto_ai_terminal
    del /f /q ersWINDOWScrypto_ai_terminal
)
echo.

echo ============================================================
echo   ETAPE 3 : Configuration des line endings (anti faux-modified)
echo ============================================================
git config core.autocrlf true
git config core.safecrlf false
echo [OK] core.autocrlf = true (convention Windows standard)
echo.

echo ============================================================
echo   ETAPE 4 : Reset propre de l'index
echo ============================================================
echo [INFO] Reconstruction de l'index depuis HEAD pour effacer les faux modified
git read-tree HEAD
if errorlevel 1 (
    echo [WARN] read-tree a echoue, tentative avec git reset
    git reset
)
echo [OK]
echo.

echo ============================================================
echo   ETAPE 5 : Etat reel apres reset
echo ============================================================
echo Comptage des changements...
git status --porcelain | find /c /v ""
echo lignes au total
echo.
echo Premieres 20 lignes :
git status --porcelain > __status_temp.txt 2>nul
powershell -NoProfile -Command "Get-Content __status_temp.txt -TotalCount 20"
del /f /q __status_temp.txt 2>nul
echo.

set /p CONFIRM="Continuer avec le commit ? (o/n) : "
if /i not "%CONFIRM%"=="o" goto :abort

echo.
echo ============================================================
echo   ETAPE 6 : git add
echo ============================================================
git add -A
if errorlevel 1 (
    echo [ERREUR] git add a echoue
    pause
    exit /b 1
)
echo [OK] Tous les changements stages
echo.

echo ============================================================
echo   ETAPE 7 : git commit
echo ============================================================
git commit -m "chore: cleanup project structure post-inventory V2" -m "Caches Python, artefacts ponctuels, snapshots archives redondants supprimes." -m "Modules manquants restaures depuis _old/ (strategy_factory + email_notifier)." -m "main_v91.py reconstitue (etait tronque ligne 658)." -m "Outputs tests deplaces dans tests/outputs/. 50 .md reorganises dans docs/." -m "Doublons launch_all_ps* supprimes. launch_all.ps1 corrige (V12 dashboard)." -m "Reecriture stop_all.bat + healthcheck.* (au lieu de healthcheck_v27.*)." -m "_old/ archive vers Documents (15MB compresse, 2382 fichiers) et supprime du projet." -m "Resultat : 3.5GB -> 468MB, 279 .py compilent, 0 import casse." -m "Nouveau .gitattributes pour empecher les futurs problemes CRLF/LF cross-OS."

if errorlevel 1 (
    echo [ERREUR] git commit a echoue ^(possiblement rien a commiter^)
    echo.
    echo Etat actuel :
    git status -s
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 8 : Verification
echo ============================================================
git log --oneline -3
echo.

echo ============================================================
echo   COMMIT REUSSI
echo   Branche : chore/safe-archive-legacy-folders
echo.
echo   Pour pousser vers GitHub :
echo     git push -u origin chore/safe-archive-legacy-folders
echo ============================================================
pause
exit /b 0

:abort
echo.
echo Commit annule par l'utilisateur.
pause
exit /b 1
