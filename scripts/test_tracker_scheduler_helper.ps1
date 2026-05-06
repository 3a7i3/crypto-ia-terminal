$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Helper = Join-Path $Root 'tracker_scheduler.ps1'
$LogFile = 'tracker_system/logs/auto_update.log'

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Label
    )

    if ($Text -notmatch [regex]::Escape($Expected)) {
        throw "[$Label] expected to find: $Expected`nActual:`n$Text"
    }
}

Push-Location $Root
try {
    & $Helper clean -Force -LogFile $LogFile | Out-Null

    $onceOutput = (& $Helper once -NoOptimizer -TailLogs 3 -LogFile $LogFile 6>&1) | Out-String
    Assert-Contains -Text $onceOutput -Expected 'once summary:' -Label 'once'
    Assert-Contains -Text $onceOutput -Expected 'optimizer=False' -Label 'once'
    Assert-Contains -Text $onceOutput -Expected 'last 3 log lines:' -Label 'once'

    $onceOptimizerOutput = (& $Helper once -Optimizer -LogFile $LogFile 6>&1) | Out-String
    Assert-Contains -Text $onceOptimizerOutput -Expected 'once summary:' -Label 'once-optimizer'
    Assert-Contains -Text $onceOptimizerOutput -Expected 'optimizer=True' -Label 'once-optimizer'

    $startOutput = (& $Helper start -IntervalSeconds 5 -NoOptimizer -LogFile $LogFile 6>&1) | Out-String
    Assert-Contains -Text $startOutput -Expected 'PID:' -Label 'start'

    $statusOutput = (& $Helper status 6>&1) | Out-String
    Assert-Contains -Text $statusOutput -Expected 'RUNNING PID' -Label 'status'

    $statusJsonOutput = (& $Helper status -Json -LogFile $LogFile 6>&1) | Out-String
    $statusJson = $statusJsonOutput | ConvertFrom-Json
    if (-not $statusJson.isRunning) {
        throw "[status-json] expected isRunning=true`nActual:`n$statusJsonOutput"
    }
    if ($statusJson.state -ne 'running') {
        throw "[status-json] expected state=running`nActual:`n$statusJsonOutput"
    }

    $stopOutput = (& $Helper stop 6>&1) | Out-String
    Assert-Contains -Text $stopOutput -Expected 'stopped PID' -Label 'stop'

    $startJsonOutput = (& $Helper start -IntervalSeconds 5 -Optimizer -LogFile $LogFile -Force 6>&1) | Out-String
    Assert-Contains -Text $startJsonOutput -Expected 'PID:' -Label 'start-optimizer'

    $stopJsonOutput = (& $Helper stop -Json -LogFile $LogFile 6>&1) | Out-String
    $stopJson = $stopJsonOutput | ConvertFrom-Json
    if (-not $stopJson.stopped) {
        throw "[stop-json] expected stopped=true`nActual:`n$stopJsonOutput"
    }
    if ($stopJson.after.isRunning) {
        throw "[stop-json] expected after.isRunning=false`nActual:`n$stopJsonOutput"
    }

    $cleanOutput = (& $Helper clean -LogFile $LogFile 6>&1) | Out-String
    Assert-Contains -Text $cleanOutput -Expected 'log truncated:' -Label 'clean'
    Assert-Contains -Text $cleanOutput -Expected 'log size bytes:' -Label 'clean'

    $cleanJsonOutput = (& $Helper clean -Json -LogFile $LogFile 6>&1) | Out-String
    $cleanJson = $cleanJsonOutput | ConvertFrom-Json
    if (-not $cleanJson.cleaned) {
        throw "[clean-json] expected cleaned=true`nActual:`n$cleanJsonOutput"
    }
    if ($cleanJson.logSizeAfter -lt 0) {
        throw "[clean-json] expected non-negative logSizeAfter`nActual:`n$cleanJsonOutput"
    }

    Write-Host '[TrackerSchedulerTest] PASS'
} finally {
    try {
        & $Helper stop | Out-Null
    } catch {
    }
    Pop-Location
}