param(
    [string]$PythonExe = "C:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# === Préparation du rapport HTML ===
$ReportDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir | Out-Null }
$ReportPath = Join-Path $ReportDir "verify_all_systems_report.html"
$Report = @()
$Report += "<html><head><title>Rapport de tests - verify_all_systems.ps1</title><style>body{font-family:sans-serif;} .ok{color:green;} .fail{color:red;} .step{font-weight:bold;} .ts{color:#888;}</style></head><body>"
$Report += "<h1>Rapport de tests - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</h1>"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    $ts = (Get-Date -Format 'HH:mm:ss')
    Write-Host "[STEP] $Name" -ForegroundColor Cyan
    $Report += "<div class='step'>[$ts] $Name</div>"
    try {
        & $Action 2>&1 | ForEach-Object {
            $line = $_ -replace '<', '&lt;' -replace '>', '&gt;'
            $Report += "<div style='margin-left:2em;font-size:90%'>$_</div>"
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FAIL] $Name" -ForegroundColor Red
            $Report += "<div class='fail'>[FAIL] $Name</div>"
            $Report += "</body></html>"
            $Report -join "`n" | Out-File -Encoding UTF8 $ReportPath
            exit $LASTEXITCODE
        }
        Write-Host "[OK] $Name" -ForegroundColor Green
        $Report += "<div class='ok'>[OK] $Name</div>"
    } catch {
        Write-Host "[FAIL] $Name : $_" -ForegroundColor Red
        $Report += "<div class='fail'>[FAIL] $Name : $_</div>"
        $Report += "</body></html>"
        $Report -join "`n" | Out-File -Encoding UTF8 $ReportPath
        exit 1
    }
}

Invoke-Step -Name "Pip dependency integrity" -Action {
    & $PythonExe -m pip check
}

Invoke-Step -Name "Crypto V30 regression tests" -Action {
    Push-Location (Join-Path $RepoRoot "crypto_quant_v16")
    try {
        $env:V30_OFFLINE_TESTS = "1"
        & $PythonExe test_v30_smart_chart.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PythonExe test_v30_profile.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PythonExe test_v30_multi_exchange.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PythonExe test_v30_profile_persistence.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Remove-Item Env:V30_OFFLINE_TESTS -ErrorAction SilentlyContinue
        Pop-Location
    }
}

Invoke-Step -Name "Quant Hedge AI syntax compile" -Action {
    $env:PYTHONPATH = $RepoRoot
    Push-Location (Join-Path $RepoRoot "quant_hedge_ai")
    try {
        Write-Host "[DEBUG] Running: $PythonExe -m quant_hedge_ai.main_v91"
        $output1 = & $PythonExe -m quant_hedge_ai.main_v91 2>&1
        Write-Host "[DEBUG] Output main_v91.py:" -ForegroundColor Yellow
        Write-Host $output1
        Write-Host "[DEBUG] LASTEXITCODE main_v91.py: $LASTEXITCODE"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "[DEBUG] Running: $PythonExe -m quant_hedge_ai.main_system"
        $output2 = & $PythonExe -m quant_hedge_ai.main_system 2>&1
        Write-Host "[DEBUG] Output main_system.py:" -ForegroundColor Yellow
        Write-Host $output2
        Write-Host "[DEBUG] LASTEXITCODE main_system.py: $LASTEXITCODE"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "Quant AI System syntax compile" -Action {
    Push-Location (Join-Path $RepoRoot "quant-ai-system")
    try {
        & $PythonExe -m py_compile main.py main_v2.py main_v7_multiagent.py main_v7_production.py
    }
    finally {
        Pop-Location
    }
}


Write-Host "All system checks passed." -ForegroundColor Green
$Report += "<h2 style='color:green'>Tous les tests sont passés avec succès.</h2>"
$Report += "</body></html>"
$Report -join "`n" | Out-File -Encoding UTF8 $ReportPath
Write-Host "[RAPPORT] Rapport HTML généré : $ReportPath" -ForegroundColor Cyan

# === Couverture de tests étendue : tests globaux et modules critiques ===

Invoke-Step -Name "Global Python tests (run_all_tests.py)" -Action {
    & $PythonExe "$RepoRoot\run_all_tests.py"
}

Invoke-Step -Name "AI Hedge Fund System - Intégration" -Action {
    Push-Location (Join-Path $RepoRoot "AI_HEDGE_FUND_SYSTEM")
    try {
        & $PythonExe test_ai_hedge_fund_system.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "AI Hedge Fund System - Feature Discovery Pipeline" -Action {
    Push-Location (Join-Path $RepoRoot "AI_HEDGE_FUND_SYSTEM")
    try {
        & $PythonExe -m AI_HEDGE_FUND_SYSTEM.test_feature_discovery_alpha_mining
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "AI Quant Lab V4 - Simulation tests" -Action {
    Push-Location (Join-Path $RepoRoot "AI_QUANT_LAB_V4\simulation_lab")
    try {
        & $PythonExe run_all_sim_tests.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "AI Quant Lab V4 - Team agent cycle" -Action {
    Push-Location (Join-Path $RepoRoot "AI_QUANT_LAB_V4\ai_agents")
    try {
        & $PythonExe test_ai_quant_team.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "Quant Hedge AI - Strategy Factory" -Action {
    Push-Location (Join-Path $RepoRoot "quant-hedge-ai")
    try {
        & $PythonExe test_strategy_factory.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "Quant Hedge AI - Prompt Doctor Agent" -Action {
    Push-Location (Join-Path $RepoRoot "quant-hedge-ai")
    try {
        & $PythonExe test_prompt_doctor_agent.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "Quant Hedge AI - Market Radar" -Action {
    Push-Location (Join-Path $RepoRoot "quant-hedge-ai")
    try {
        & $PythonExe test_market_radar.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "QUANT_CORE - Integration" -Action {
    Push-Location (Join-Path $RepoRoot "QUANT_CORE")
    try {
        & $PythonExe test_quant_core_integration.py
        & $PythonExe test_quant_core.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "QUANT_CORE - Unit tests" -Action {
    Push-Location (Join-Path $RepoRoot "QUANT_CORE\tests")
    try {
        & $PythonExe test_quant_core.py
        & $PythonExe test_core_interface.py
    }
    finally {
        Pop-Location
    }
}

Invoke-Step -Name "Crypto Quant V16 - Sniper/Execution" -Action {
    Push-Location (Join-Path $RepoRoot "crypto_quant_v16\tests")
    try {
        & $PythonExe test_sniper_bot.py
        & $PythonExe test_execution_engine.py
    }
    finally {
        Pop-Location
    }
}
