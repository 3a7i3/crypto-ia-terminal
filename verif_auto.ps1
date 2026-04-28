# Script PowerShell de vérification automatique
# Vérifie ports, processus et logs de démarrage principaux

# 1. Vérification des ports critiques
$ports = @(5010, 5011, 5013, 5026, 8502)
Write-Host "--- Vérification des ports ---"
foreach ($port in $ports) {
    $inUse = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($inUse) {
        Write-Host "Port $port : OCCUPÉ" -ForegroundColor Red
    } else {
        Write-Host "Port $port : libre" -ForegroundColor Green
    }
}

# 2. Vérification des processus Python principaux
Write-Host "\n--- Processus Python actifs ---"
Get-Process python, pythonw -ErrorAction SilentlyContinue | Format-Table Id, ProcessName, MainWindowTitle

# 3. Vérification rapide des logs de démarrage (exemple sur les 10 dernières lignes de chaque log)
$logFiles = @("quant-hedge-ai\logs\main.log", "crypto_quant_v16\logs\main.log")
Write-Host "\n--- Dernières lignes des logs principaux ---"
foreach ($log in $logFiles) {
    if (Test-Path $log) {
        Write-Host "\n$log :"
        Get-Content $log -Tail 10
    } else {
        Write-Host "\n$log : fichier non trouvé" -ForegroundColor Yellow
    }
}

Write-Host "\nVérification automatique terminée. Complétez avec la checklist manuelle si besoin."
