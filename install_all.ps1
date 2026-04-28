#!/usr/bin/env pwsh
# install_all.ps1 - Installation automatique et robuste de l'environnement Python pour crypto_ai_terminal

Write-Host "[INFO] Suppression de l'ancien environnement .venv (si présent)..."
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }

# Détection automatique de Python
$pythonBin = $null

foreach ($candidate in @('python', 'python3', 'py')) {
    $ver = & $candidate --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonBin = $candidate
        break
    }
}
if (-not $pythonBin) {
    Write-Host "[ERREUR] Aucun interpréteur Python trouvé dans le PATH. Installez Python 3.8+ et relancez ce script."
    exit 1
}

# Contrôle automatique de la version de Python
$pythonVersionOutput = & $pythonBin --version 2>&1
$versionMatch = $pythonVersionOutput -match "([0-9]+)\.([0-9]+)\.([0-9]+)"
if (-not $versionMatch) {
    Write-Host "[ERREUR] Impossible de lire la version Python."
    exit 1
}
$major = [int]$Matches[1]
$minor = [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
    Write-Host "[ERREUR] Version Python trop ancienne ($pythonVersionOutput). Installez Python >= 3.8."
    exit 1
}
if ($major -gt 3 -or ($major -eq 3 -and $minor -gt 12)) {
    Write-Host "[ERREUR] Version Python trop récente ($pythonVersionOutput). Installez Python <= 3.12."
    exit 1
}
Write-Host "[INFO] Version Python compatible détectée : $pythonVersionOutput"

Write-Host "[INFO] Création d'un nouvel environnement virtuel .venv avec $pythonBin..."
& $pythonBin -m venv .venv
if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Host "[ERREUR] La création de l'environnement virtuel a échoué. Vérifiez vos droits d'écriture et la version de Python."
    exit 1
}

Write-Host "[INFO] Activation de l'environnement virtuel..."
. .\.venv\Scripts\Activate.ps1

Write-Host "[INFO] Installation des dépendances racine..."
pip install --upgrade pip
pip install -r requirements.txt

if (Test-Path "crypto_quant_v16/requirements.txt") {
    Write-Host "[INFO] Installation des dépendances crypto_quant_v16..."
    pip install -r crypto_quant_v16/requirements.txt
}
if (Test-Path "quant-ai-system/requirements.txt") {
    Write-Host "[INFO] Installation des dépendances quant-ai-system..."
    pip install -r quant-ai-system/requirements.txt
}
if (Test-Path "quant-hedge-ai/requirements.txt") {
    Write-Host "[INFO] Installation des dépendances quant-hedge-ai..."
    pip install -r quant-hedge-ai/requirements.txt
}

# Installation automatique des modules critiques
Write-Host "[INFO] Installation manuelle des modules critiques (plotly, python-dotenv, selenium)..."
pip install plotly python-dotenv selenium

Write-Host "[INFO] Installation terminée. Vous pouvez lancer :"
Write-Host "    .\\.venv\\Scripts\\Activate.ps1"
Write-Host "    python run_all_tests.py"
