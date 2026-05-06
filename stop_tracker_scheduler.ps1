param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root 'tracker_system\logs\scheduler.pid'

function Stop-SchedulerProcess {
    param(
        [int]$Id,
        [switch]$ForceStop
    )

    $proc = Get-Process -Id $Id -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        return $false
    }

    Stop-Process -Id $Id -Force:$ForceStop
    return $true
}

$stopped = $false

if (Test-Path $PidFile) {
    try {
        $pidText = Get-Content -Path $PidFile -Raw
        $schedulerPid = [int]$pidText
        if (Stop-SchedulerProcess -Id $schedulerPid -ForceStop:$Force) {
            Write-Host "[TrackerScheduler] stopped PID $schedulerPid"
            $stopped = $true
        } else {
            Write-Host "[TrackerScheduler] stale pid file: PID $schedulerPid is not running"
        }
    } catch {
        Write-Host "[TrackerScheduler] invalid pid file content, fallback process scan will be used"
    }
}

if (-not $stopped) {
    $candidates = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq 'python.exe' -and
            $_.CommandLine -match 'tracker_system[\\/]main.py' -and
            $_.CommandLine -match '--scheduler'
        }

    foreach ($candidate in $candidates) {
        if (Stop-SchedulerProcess -Id ([int]$candidate.ProcessId) -ForceStop:$Force) {
            Write-Host "[TrackerScheduler] stopped PID $($candidate.ProcessId) (fallback scan)"
            $stopped = $true
        }
    }
}

if (Test-Path $PidFile) {
    Remove-Item -Path $PidFile -Force
    if (-not $stopped) {
        Write-Host "[TrackerScheduler] stale pid file removed: $PidFile"
    }
}

if (-not $stopped) {
    Write-Host '[TrackerScheduler] no running scheduler process found'
}