# PowerShell script to build Sphinx docs on Windows
# Usage: .\build_docs.ps1

$venvPath = ".venv\Scripts"
$sphinxBuild = Join-Path $venvPath "sphinx-build.exe"
$docsDir = "docs"
$buildDir = "$docsDir\_build\html"

if (-Not (Test-Path $sphinxBuild)) {
    Write-Host "sphinx-build.exe introuvable dans .venv. Installez-le avec 'pip install sphinx sphinx_rtd_theme' dans le venv."
    exit 1
}

if (-Not (Test-Path $docsDir)) {
    Write-Host "Le dossier $docsDir n'existe pas. Initialisez-le avec 'sphinx-quickstart' d'abord."
    exit 1
}

& $sphinxBuild -b html $docsDir $buildDir

if ($LASTEXITCODE -eq 0) {
    Write-Host "Documentation générée dans $buildDir."
} else {
    Write-Host "Erreur lors de la génération de la documentation."
    exit $LASTEXITCODE
}
