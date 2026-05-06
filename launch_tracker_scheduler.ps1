param(
    [double]$IntervalSeconds = 1800,
    [int]$MaxIterations = 0,
    [switch]$Optimizer,
    [switch]$NoOptimizer,
    [string]$LogFile = "tracker_system/logs/auto_update.log",
    [switch]$Force,
    [switch]$Visible
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$PidFile = Join-Path $Root 'tracker_system\logs\scheduler.pid'

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

if ($Optimizer -and $NoOptimizer) {
    throw "Use either -Optimizer or -NoOptimizer, not both."
}

$WindowStyle = if ($Visible) { 'Normal' } else { 'Minimized' }

$pythonArgs = @(
    'tracker_system/main.py',
    '--scheduler',
    '--interval-seconds', "$IntervalSeconds",
    '--scheduler-log-file', "$LogFile"
)

if ($MaxIterations -gt 0) {
    $pythonArgs += @('--max-iterations', "$MaxIterations")
}

if ($NoOptimizer) {
    $pythonArgs += '--no-optimizer'
}

if (Test-Path $PidFile) {
    try {
        $existingPidText = Get-Content -Path $PidFile -Raw
        $existingPid = [int]$existingPidText
        $existing = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            if ($Force) {
                Write-Host "[TrackerScheduler] force relaunch requested, stopping existing PID $existingPid"
                Stop-Process -Id $existingPid -Force
            } else {
                Write-Host "[TrackerScheduler] already running with PID $existingPid"
                Write-Host "[TrackerScheduler] use -Force to relaunch"
                Write-Host "[TrackerScheduler] pid file: $PidFile"
                return
            }
        } else {
            Write-Host "[TrackerScheduler] stale pid file detected (PID $existingPid not running)"
            Write-Host "[TrackerScheduler] relaunching and overwriting pid file"
        }
    } catch {
        Write-Host "[TrackerScheduler] invalid pid file content, relaunching and overwriting pid file"
    }
}

New-Item -ItemType Directory -Path (Split-Path -Parent $PidFile) -Force | Out-Null

Write-Host "[TrackerScheduler] starting with interval=$IntervalSeconds sec"
Write-Host "[TrackerScheduler] log file: $LogFile"
$startParams = @{
    FilePath = $Python
    ArgumentList = $pythonArgs
    WorkingDirectory = $Root
    WindowStyle = $WindowStyle
    PassThru = $true
}
$process = Start-Process @startParams

Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
Write-Host "[TrackerScheduler] PID: $($process.Id)"
Write-Host "[TrackerScheduler] pid file: $PidFile"