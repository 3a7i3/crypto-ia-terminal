# Cybertechnique Certification Layer — Install Script
# Copie l'extension locale dans le dossier extensions VS Code

$ExtSrc  = Join-Path $PSScriptRoot "extension"
$ExtDest = Join-Path $env:USERPROFILE ".vscode\extensions\cybertechnique-certification-1.0.0"

Write-Host ""
Write-Host "=== CYBERTECHNIQUE CERTIFICATION LAYER ===" -ForegroundColor Cyan
Write-Host "Source : $ExtSrc"
Write-Host "Dest   : $ExtDest"
Write-Host ""

if (-not (Test-Path $ExtSrc)) {
    Write-Host "[ERREUR] Dossier extension introuvable : $ExtSrc" -ForegroundColor Red
    exit 1
}

if (Test-Path $ExtDest) {
    Write-Host "[INFO] Suppression ancienne version..." -ForegroundColor Yellow
    Remove-Item $ExtDest -Recurse -Force
}

Copy-Item $ExtSrc $ExtDest -Recurse -Force
Write-Host "[OK] Extension installée dans : $ExtDest" -ForegroundColor Green
Write-Host ""
Write-Host "→ Redémarre VS Code pour activer le Cybertechnique Certification Layer." -ForegroundColor Cyan
Write-Host ""
