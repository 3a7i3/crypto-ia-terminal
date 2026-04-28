# ============================================================
#  V9.1 Smoke Test — diagnose + run
#  Usage : .\smoke_test_v91.bat (ou directement ce ps1)
# ============================================================

param(
    [int]$Cycles = 1,
    [int]$Population = 10,
    [int]$Generations = 1
)

$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("smoke_test_v91_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Section {
    param([string]$Title)
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
}

Section "1) Verification du venv"
if (-not (Test-Path $Python)) {
    Write-Host "[FAIL] Python venv introuvable a $Python" -ForegroundColor Red
    Write-Host "       Cree-le avec : python -m venv .venv" -ForegroundColor Yellow
    Write-Host "       Puis : .\.venv\Scripts\Activate.ps1 && pip install -r requirements-ci.txt" -ForegroundColor Yellow
    exit 1
}
$pyver = & $Python --version 2>&1
Write-Host "[OK] Venv : $Python"
Write-Host "[OK] $pyver"

Section "2) Verification des dependances cles"
$criticalDeps = @('ccxt','numpy','pandas','panel','plotly')
$missing = @()
foreach ($dep in $criticalDeps) {
    $check = & $Python -c "import $dep; print($dep.__version__ if hasattr($dep,'__version__') else 'OK')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $dep $check"
    } else {
        Write-Host "  [MANQUANT] $dep" -ForegroundColor Red
        $missing += $dep
    }
}
if ($missing.Count -gt 0) {
    Write-Host ''
    Write-Host "[ACTION REQUISE] Modules manquants : $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "  Installer avec : .\.venv\Scripts\pip install -r requirements-ci.txt" -ForegroundColor Yellow
    Write-Host ''
    $continue = Read-Host "Tenter quand meme le smoke-test ? (o/n)"
    if ($continue -ne 'o') { exit 1 }
}

Section "3) Compile-check de main_v91.py"
$compileResult = & $Python -m py_compile (Join-Path $Root 'quant_hedge_ai\main_v91.py') 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] main_v91.py compile sans erreur"
} else {
    Write-Host "[FAIL] Erreur de syntaxe :" -ForegroundColor Red
    Write-Host $compileResult
    exit 1
}

Section "4) Lancement du smoke-test"
Write-Host "Parametres : V9_MAX_CYCLES=$Cycles V9_POPULATION=$Population V9_GENERATIONS=$Generations"
Write-Host "Sortie capturee dans : $LogFile"
Write-Host ''
Write-Host "--- DEBUT DU LOG ---" -ForegroundColor DarkGray

$env:V9_MAX_CYCLES = "$Cycles"
$env:V9_POPULATION = "$Population"
$env:V9_GENERATIONS = "$Generations"
$env:V9_SLEEP_SECONDS = "0"
$env:PYTHONIOENCODING = "utf-8"

# Lance V9.1 et tee la sortie
& $Python -m quant_hedge_ai.main_v91 2>&1 | Tee-Object -FilePath $LogFile

$exitCode = $LASTEXITCODE
Write-Host "--- FIN DU LOG ---" -ForegroundColor DarkGray
Write-Host ''

Section "5) Verdict"
if ($exitCode -eq 0) {
    Write-Host "[SUCCES] V9.1 a tourne sans erreur fatale" -ForegroundColor Green
    Write-Host ''
    Write-Host "Tu peux maintenant lancer la version normale :" -ForegroundColor Green
    Write-Host '  $env:V9_MAX_CYCLES="3"; python -m quant_hedge_ai.main_v91' -ForegroundColor White
    Write-Host ''
    Write-Host "Ou la stack complete (V12 dashboard + Evolution 3D) :" -ForegroundColor Green
    Write-Host '  .\launch_all.bat' -ForegroundColor White
} else {
    Write-Host "[ECHEC] Code de sortie : $exitCode" -ForegroundColor Red
    Write-Host ''
    Write-Host "Dernieres lignes du log (pour diagnostic) :" -ForegroundColor Yellow
    Get-Content $LogFile -Tail 20
    Write-Host ''
    Write-Host "Log complet : $LogFile" -ForegroundColor Yellow
}

Write-Host ''
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Smoke-test termine"
Write-Host "============================================================" -ForegroundColor Cyan
exit $exitCode
