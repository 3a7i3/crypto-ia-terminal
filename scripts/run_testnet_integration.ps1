param(
    [switch]$ListOnly,
    [switch]$DryRun,
    [string]$PytestArgs = "-q -rs",
    [string]$ReportPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"


function Write-ExecutionReport {
    param(
        [hashtable]$Data,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }

    $reportDir = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($reportDir)) {
        New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }

    $Data | ConvertTo-Json -Depth 8 | Set-Content -Path $Path -Encoding utf8
    Write-Host "Execution report written to: $Path" -ForegroundColor DarkCyan
}


function Join-CommandPreview {
    param([string[]]$Parts)

    return ($Parts | ForEach-Object {
        if ($_ -match '\s') {
            '"{0}"' -f $_
        }
        else {
            $_
        }
    }) -join ' '
}

if (-not (Test-Path $pythonExe)) {
    throw "Python introuvable: $pythonExe"
}

$mode = if ($ListOnly) {
    "list-only"
}
elseif ($DryRun) {
    "dry-run"
}
else {
    "execute"
}

$requiredVars = @("BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_TESTNET")
$envState = @{}
foreach ($varName in $requiredVars) {
    $envState[$varName] = [Environment]::GetEnvironmentVariable($varName)
}

$missingVars = @(
    $requiredVars | Where-Object {
        $value = $envState[$_]
        [string]::IsNullOrWhiteSpace($value)
    }
)

$binanceTestnet = [string]$envState["BINANCE_TESTNET"]
$isTestnetTrue = -not [string]::IsNullOrWhiteSpace($binanceTestnet) -and $binanceTestnet.ToLowerInvariant() -eq "true"

$targets = @(
    "tests/integration/test_market_pipeline.py::TestMarketScannerTestnet",
    "tests/integration/test_execution_pipeline.py::TestExecutionTestnet",
    "tests/integration/test_full_pipeline.py::TestFullPipelineTestnet",
    "tests/integration/test_backtest_pipeline.py::TestBacktestOnTestnetData"
)

$argList = @("-m", "pytest")
if (-not [string]::IsNullOrWhiteSpace($PytestArgs)) {
    $argList += ($PytestArgs -split " ") | Where-Object { $_ }
}
$argList += $targets

$commandPreview = Join-CommandPreview -Parts (@($pythonExe) + $argList)

$report = [ordered]@{
    generatedAt = (Get-Date).ToString("o")
    mode = $mode
    repoRoot = $repoRoot
    pythonExe = $pythonExe
    command = $commandPreview
    pytestArgs = $PytestArgs
    targets = $targets
    environment = [ordered]@{
        BINANCE_TESTNET = $binanceTestnet
        hasBinanceApiKey = -not [string]::IsNullOrWhiteSpace($envState["BINANCE_API_KEY"])
        hasBinanceApiSecret = -not [string]::IsNullOrWhiteSpace($envState["BINANCE_API_SECRET"])
    }
    validation = [ordered]@{
        missingVars = $missingVars
        isTestnetTrue = $isTestnetTrue
        ready = ($missingVars.Count -eq 0) -and $isTestnetTrue
    }
    exitCode = $null
    status = if (($missingVars.Count -eq 0) -and $isTestnetTrue) { "ready" } else { "not-ready" }
}

Write-Host "Testnet integration targets:" -ForegroundColor Cyan
$targets | ForEach-Object { Write-Host " - $_" }

if (-not $report.validation.ready) {
    Write-Warning "Testnet environment incomplete. Missing vars: $($missingVars -join ', ')"
    if (-not $isTestnetTrue) {
        Write-Warning "BINANCE_TESTNET must be set to 'true' to execute the testnet slice."
    }
}

if ($ListOnly) {
    Write-ExecutionReport -Data $report -Path $ReportPath
    exit 0
}

if ($DryRun) {
    Write-Host "Dry run command:" -ForegroundColor Cyan
    Write-Host " $commandPreview"
    Write-ExecutionReport -Data $report -Path $ReportPath
    exit 0
}

if (-not $report.validation.ready) {
    Write-ExecutionReport -Data $report -Path $ReportPath
    throw "Variables manquantes ou invalides. Configurez BINANCE_API_KEY, BINANCE_API_SECRET et BINANCE_TESTNET=true avant execution."
}

Push-Location $repoRoot
try {
    & $pythonExe @argList
    $report.exitCode = $LASTEXITCODE
    $report.status = if ($LASTEXITCODE -eq 0) { "passed" } else { "failed" }
    Write-ExecutionReport -Data $report -Path $ReportPath
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}