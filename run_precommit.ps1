# PowerShell script to run pre-commit hooks reliably on Windows
# Usage: .\run_precommit.ps1

$venvPath = ".venv\Scripts"
$precommitExe = Join-Path $venvPath "pre-commit.exe"

if (-Not (Test-Path $precommitExe)) {
    Write-Host "pre-commit.exe introuvable dans .venv. Installez-le avec 'pip install pre-commit' dans le venv."
    exit 1
}

Write-Host "Activation de l'environnement virtuel et exécution de pre-commit..."
& $precommitExe run --all-files

if ($LASTEXITCODE -eq 0) {
    Write-Host "Tous les hooks pre-commit sont passés avec succès."
} else {
    Write-Host "Des erreurs ont été détectées par pre-commit. Corrigez-les puis relancez le script."
    exit $LASTEXITCODE
}
