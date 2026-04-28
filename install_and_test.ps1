# Installation, lancement et test automatisé complet
# Usage : powershell -ExecutionPolicy Bypass -File install_and_test.ps1

Write-Host "[1/5] Activation de l'environnement virtuel..."
. .\.venv\Scripts\Activate.ps1

Write-Host "[2/5] Installation des dépendances Python (si besoin)..."
.\.venv\Scripts\pip.exe install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install fastapi uvicorn[standard] pydantic

Write-Host "[3/5] Lancement de l'orchestration complète..."
Start-Process powershell -ArgumentList '-NoExit','-Command','./launch_all.ps1 -Visible -LoadEnv'

# Attente active de l'API orchestrateur
$maxWait = 60
$waited = 0
while ($waited -lt $maxWait) {
    $tcp = Test-NetConnection -ComputerName 'localhost' -Port 8090 -WarningAction SilentlyContinue
    if ($tcp.TcpTestSucceeded) {
        Write-Host "[OK] API orchestrateur détectée sur le port 8090."
        break
    }
    Write-Host "[WAIT] Attente du démarrage de l'API orchestrateur (port 8090)..."
    Start-Sleep -Seconds 1
    $waited++
}
if ($waited -ge $maxWait) {
    Write-Host "[FATAL] L'API orchestrateur n'a pas démarré sur le port 8090 après $maxWait secondes."
    exit 1
}

Write-Host "[4/5] Lancement des tests racine..."
$rootResult = .\.venv\Scripts\python.exe -m pytest -v --tb=short
Write-Host $rootResult

Write-Host "[4b/5] Lancement des tests quant-ai-system..."
$qasResult = .\.venv\Scripts\python.exe -m pytest quant-ai-system/quant_ai_tests -v --tb=short
Write-Host $qasResult

Write-Host "[5/5] Résultat des tests :"
if ($rootResult -like '*FAILED*' -or $rootResult -like '*ERROR*' -or $qasResult -like '*FAILED*' -or $qasResult -like '*ERROR*') {
    Write-Host "[ECHEC] Des tests ont échoué. Vérifiez les logs."
    exit 1
} else {
    Write-Host "[SUCCES] Tous les tests sont passés. Système opérationnel."
    exit 0
}
