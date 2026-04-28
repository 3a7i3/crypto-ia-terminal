param(
    [int]$TimeoutSec = 12
)

$ErrorActionPreference = 'SilentlyContinue'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# Services actifs (V9.1 + Evolution).
# Pour réactiver les dashboards legacy V13/V16/V26, sortez crypto_quant_v16 de _old/
# et rajoutez les routes correspondantes ici.
$routes = @(
    @{ Name = 'V12';        Port = 5010; Path = 'quant_terminal_v12'; Type = 'Panel' },
    @{ Name = 'Evolution3D'; Port = 8501; Path = '';                  Type = 'Streamlit' }
)

function Test-PortListening {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        return $null -ne $conn
    } catch {
        return $false
    }
}

function Test-Http {
    param(
        [string]$Url,
        [int]$Timeout = 12
    )
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $Timeout
        return @{ Ok = $true; Code = [int]$r.StatusCode; Error = '' }
    } catch {
        return @{ Ok = $false; Code = 0; Error = ($_.Exception.Message) }
    }
}

Write-Host '============================================================'
Write-Host " V9.1 Healthcheck - $timestamp"
Write-Host '============================================================'

# Python env check
if (Test-Path $python) {
    Write-Host "[OK] Python venv found: $python"
} else {
    Write-Host "[FAIL] Python venv not found: $python"
}

Write-Host ''
Write-Host '--- Services ---'

$okCount = 0
foreach ($svc in $routes) {
    if ($svc.Path) {
        $url = "http://localhost:$($svc.Port)/$($svc.Path)"
    } else {
        $url = "http://localhost:$($svc.Port)/"
    }

    $listening = Test-PortListening -Port $svc.Port
    $appResp = Test-Http -Url $url -Timeout $TimeoutSec

    if ($listening -and $appResp.Ok) {
        $okCount += 1
        Write-Host ("[{0}] {1} ({2}) port={3} http={4}" -f 'OK', $svc.Name, $svc.Type, $svc.Port, $appResp.Code)
    } elseif ($listening -and -not $appResp.Ok) {
        Write-Host ("[{0}] {1} ({2}) port={3} listens but app route failed: {4}" -f 'WARN', $svc.Name, $svc.Type, $svc.Port, $appResp.Error)
    } else {
        Write-Host ("[{0}] {1} ({2}) port={3} not listening" -f 'FAIL', $svc.Name, $svc.Type, $svc.Port)
    }
}

Write-Host ''
Write-Host '--- Background Processes ---'

$evolution = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'evolution_3d_view.py' }
$streamlit = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'streamlit_dashboard.py' }
$mainV91 = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'main_v91.py' }

Write-Host ("Evolution 3D viewer processes : {0}" -f @($evolution).Count)
Write-Host ("Streamlit dashboard processes : {0}" -f @($streamlit).Count)
Write-Host ("V9.1 main loop processes      : {0}" -f @($mainV91).Count)

Write-Host ''
Write-Host '--- Summary ---'
if ($okCount -eq $routes.Count) {
    Write-Host ("[OK] All services healthy ({0}/{1})" -f $okCount, $routes.Count)
} else {
    Write-Host ("[WARN] Service health partial ({0}/{1})" -f $okCount, $routes.Count)
    Write-Host 'Tip: run launch_all.bat then retry.'
}
