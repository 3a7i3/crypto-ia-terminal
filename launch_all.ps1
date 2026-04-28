param(
    [switch]$Visible,
    [switch]$LoadEnv
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$StreamlitPort = 8501
$StreamlitTitle = '3D Evolution Viewer'
$StreamlitScript = 'evolution_3d_view.py'
$WindowStyle = if ($Visible) { 'Normal' } else { 'Minimized' }
$EnvFile = Join-Path $Root '.env'

# === Étape 0 : Vérification automatique des systèmes et tests ===
$VerifyScript = Join-Path $Root 'scripts\verify_all_systems.ps1'
if (Test-Path $VerifyScript) {
    Write-Host '============================================================'
    Write-Host '  [AUTO-TEST] Vérification des systèmes et tests critiques'
    Write-Host '============================================================'
    $verifyResult = & $VerifyScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ERREUR] Un ou plusieurs tests critiques ont échoué. Arrêt du lancement.' -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host '[OK] Tous les tests critiques sont passés.' -ForegroundColor Green
    Write-Host ''
}

function Write-Section {
    param([string]$Text)
    Write-Host ''
    Write-Host $Text
}

function Load-DotEnv {
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) {
        Write-Host "[WARN] No .env found at $FilePath"
        return
    }

    Write-Host "[INFO] Loading environment from $FilePath"
    Get-Content -Path $FilePath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith('#') -or $line.StartsWith(';')) { return }

        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { return }

        $key = $parts[0].Trim()
        $val = $parts[1]
        if ($key) {
            [Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }

    if ([string]::IsNullOrWhiteSpace($env:TELEGRAM_BOT_TOKEN)) {
        Write-Host '[WARN] TELEGRAM_BOT_TOKEN is empty'
    } else {
        Write-Host '[OK] TELEGRAM_BOT_TOKEN loaded'
    }

    if ([string]::IsNullOrWhiteSpace($env:TELEGRAM_CHAT_ID)) {
        Write-Host '[WARN] TELEGRAM_CHAT_ID is empty'
    } else {
        Write-Host '[OK] TELEGRAM_CHAT_ID loaded'
    }
}

function Test-PortListening {
    param([int]$Port)

    try {
        $sock = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        return $null -ne $sock
    } catch {
        return $false
    }
}

function Ensure-PanelService {
    param(
        [int]$Port,
        [string]$Title,
        [string]$WorkingDir,
        [string]$ScriptPath
    )

    if (Test-PortListening -Port $Port) {
        Write-Host "[$Title] already running on port $Port, skipping."
        return
    }

    $cmd = "cd /d `"$WorkingDir`" && `"$Python`" -m panel serve $ScriptPath --port $Port --show --autoreload"
    Write-Host "[$Title] starting on port $Port ..."
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $cmd -WindowStyle $WindowStyle | Out-Null
    Start-Sleep -Seconds 2
}

function Ensure-BackgroundPython {
    param(
        [string]$Title,
        [string]$Match,
        [string]$WorkingDir,
        [string]$Command
    )

    $running = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match $Match } |
        Select-Object -First 1

    if ($running) {
        Write-Host "[$Title] already running, skipping."
        return
    }

    $cmd = "cd /d `"$WorkingDir`" && `"$Python`" $Command"
    Write-Host "[$Title] starting ..."
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $cmd -WindowStyle $WindowStyle | Out-Null
}


# === Vérification de la version de Python ===
if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}
$pythonVersion = & $Python --version 2>&1
Write-Host "[INFO] Python version: $pythonVersion"

# === Vérification des ports déjà utilisés ===
$allPorts = @(5010, $StreamlitPort)
$busyPorts = @()
foreach ($p in $allPorts) {
    if (Test-PortListening -Port $p) {
        $busyPorts += $p
    }
}
if ($busyPorts.Count -gt 0) {
    Write-Host "[WARN] Ports déjà occupés: $($busyPorts -join ', ')" -ForegroundColor Yellow
}

Write-Host '============================================================'
Write-Host '  AI Quant Platform - PowerShell Launcher (V9.1 + Evolution)'
Write-Host '  V12 Dashboard (5010) + 3D Evolution Viewer (8501)'
Write-Host '============================================================'

if ($LoadEnv) {
    Load-DotEnv -FilePath $EnvFile
}


# === V12 Dashboard (V9.1 Quant Terminal) ===
# Note : utilise quant_hedge_ai/ (avec underscore — le vrai code).
# Le dossier quant-hedge-ai/ avec tiret n'est qu'un wrapper compat sans dashboard.
Ensure-PanelService -Port 5010 -Title 'V12 Dashboard' -WorkingDir (Join-Path $Root 'quant_hedge_ai') -ScriptPath 'dashboard\quant_terminal_v12.py'

# === Dashboards V13/V16/V26 désactivés ===
# Ces dashboards appartiennent à crypto_quant_v16/ qui est dans _old/ (legacy).
# Pour les réactiver, il faudrait sortir le dossier de _old/ et décommenter ci-dessous.
# Ensure-PanelService -Port 5011 -Title 'V16 Dashboard' -WorkingDir (Join-Path $Root 'crypto_quant_v16') -ScriptPath 'ui\quant_dashboard.py'
# Ensure-PanelService -Port 5013 -Title 'V13 Dashboard' -WorkingDir (Join-Path $Root 'crypto_quant_v16') -ScriptPath 'ui\quant_dashboard_v13.py'
# Ensure-PanelService -Port 5026 -Title 'V26 Dashboard' -WorkingDir (Join-Path $Root 'crypto_quant_v16') -ScriptPath 'ui\quant_dashboard_v26.py'

# === Lancement du 3D Evolution Viewer (Streamlit) ===
function Ensure-StreamlitService {
    param(
        [int]$Port,
        [string]$Title,
        [string]$ScriptPath
    )
    if (Test-PortListening -Port $Port) {
        Write-Host "[$Title] already running on port $Port, skipping."
        return
    }
    $cmd = "cd /d `"$Root`" && `"$Python`" -m streamlit run $ScriptPath --server.port $Port --server.headless true"
    Write-Host "[$Title] starting on port $Port ..."
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $cmd -WindowStyle $WindowStyle | Out-Null
    Start-Sleep -Seconds 2
}

Ensure-StreamlitService -Port $StreamlitPort -Title $StreamlitTitle -ScriptPath $StreamlitScript

# === Loops legacy désactivés ===
# main_v13.py et binance_alert_app.py vivaient dans crypto_quant_v16/ qui est dans _old/.
# Réactivez-les en sortant le dossier de _old/ si vous en avez besoin.
# Ensure-BackgroundPython -Title 'V13 Autonomous Loop' -Match 'main_v13.py' -WorkingDir (Join-Path $Root 'crypto_quant_v16') -Command 'main_v13.py'
# Ensure-BackgroundPython -Title 'Binance Alert App' -Match 'binance_alert_app.py' -WorkingDir (Join-Path $Root 'crypto_quant_v16') -Command 'binance_alert_app.py --symbol BTC/USDT --timeframe 1h --poll 45'

Write-Section 'Services state checked:'
Write-Host '  V12 Dashboard   : http://localhost:5010/quant_terminal_v12'
Write-Host "  3D Evolution    : http://localhost:$StreamlitPort"
Write-Host "  Window Mode     : $WindowStyle"
Write-Host ''
Write-Host 'Use stop_all.bat to stop everything cleanly.'
