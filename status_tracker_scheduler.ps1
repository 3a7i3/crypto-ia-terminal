$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root 'tracker_system\logs\scheduler.pid'

$reported = $false

if (Test-Path $PidFile) {
    try {
        $pidText = Get-Content -Path $PidFile -Raw
        $schedulerPid = [int]$pidText
        $proc = Get-Process -Id $schedulerPid -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            Write-Host "[TrackerScheduler] RUNNING PID $schedulerPid"
            Write-Host "[TrackerScheduler] pid file: $PidFile"
            $reported = $true
        } else {
            Write-Host "[TrackerScheduler] STALE PID FILE (PID $schedulerPid not running)"
            Write-Host "[TrackerScheduler] pid file: $PidFile"
            $reported = $true
        }
    } catch {
        Write-Host "[TrackerScheduler] INVALID PID FILE"
        Write-Host "[TrackerScheduler] pid file: $PidFile"
        $reported = $true
    }
}

if (-not $reported) {
    $candidates = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq 'python.exe' -and
            $_.CommandLine -match 'tracker_system[\\/]main.py' -and
            $_.CommandLine -match '--scheduler'
        }

    if ($candidates.Count -gt 0) {
        $pids = ($candidates | ForEach-Object { $_.ProcessId }) -join ', '
        Write-Host "[TrackerScheduler] RUNNING (fallback scan) PID(s): $pids"
    } else {
        Write-Host '[TrackerScheduler] STOPPED'
    }
}