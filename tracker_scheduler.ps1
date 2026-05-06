param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'status', 'stop', 'restart', 'logs', 'clean', 'once')]
    [string]$Action = 'status',
    [double]$IntervalSeconds = 1800,
    [int]$MaxIterations = 0,
    [switch]$Optimizer,
    [switch]$NoOptimizer,
    [string]$LogFile = 'tracker_system/logs/auto_update.log',
    [int]$Tail = 20,
    [int]$TailLogs = 0,
    [switch]$Json,
    [switch]$Force,
    [switch]$Visible
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root 'tracker_system\logs\scheduler.pid'
$Python = Join-Path $Root '.venv\Scripts\python.exe'

function Resolve-TrackerSchedulerLogFile {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return (Join-Path $Root $PathValue)
}

function Resolve-TrackerSchedulerPidFile {
    return (Join-Path $Root 'tracker_system\logs\scheduler.pid')
}

function Get-TrackerSchedulerStatus {
    param([string]$ResolvedLogFile)

    if (Test-Path $PidFile) {
        try {
            $pidText = Get-Content -Path $PidFile -Raw
            $schedulerPid = [int]$pidText
            $proc = Get-Process -Id $schedulerPid -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                return [pscustomobject][ordered]@{
                    state = 'running'
                    isRunning = $true
                    source = 'pid-file'
                    pids = @($schedulerPid)
                    pidFile = $PidFile
                    logFile = $ResolvedLogFile
                    message = "RUNNING PID $schedulerPid"
                }
            }

            return [pscustomobject][ordered]@{
                state = 'stale-pid-file'
                isRunning = $false
                source = 'pid-file'
                pids = @($schedulerPid)
                pidFile = $PidFile
                logFile = $ResolvedLogFile
                message = "STALE PID FILE (PID $schedulerPid not running)"
            }
        } catch {
            return [pscustomobject][ordered]@{
                state = 'invalid-pid-file'
                isRunning = $false
                source = 'pid-file'
                pids = @()
                pidFile = $PidFile
                logFile = $ResolvedLogFile
                message = 'INVALID PID FILE'
            }
        }
    }

    $candidates = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq 'python.exe' -and
            $_.CommandLine -match 'tracker_system[\\/]main.py' -and
            $_.CommandLine -match '--scheduler'
        }

    if ($candidates.Count -gt 0) {
        $pids = @($candidates | ForEach-Object { [int]$_.ProcessId })
        return [pscustomobject][ordered]@{
            state = 'running'
            isRunning = $true
            source = 'fallback-scan'
            pids = $pids
            pidFile = $PidFile
            logFile = $ResolvedLogFile
            message = "RUNNING (fallback scan) PID(s): $($pids -join ', ')"
        }
    }

    return [pscustomobject][ordered]@{
        state = 'stopped'
        isRunning = $false
        source = 'none'
        pids = @()
        pidFile = $PidFile
        logFile = $ResolvedLogFile
        message = 'STOPPED'
    }
}

function Write-TrackerSchedulerJson {
    param([object]$Value)

    $Value | ConvertTo-Json -Depth 5
}

switch ($Action) {
    'start' {
        if ($Optimizer -and $NoOptimizer) {
            throw "Use either -Optimizer or -NoOptimizer with 'start', not both."
        }
        $startParams = @{
            IntervalSeconds = $IntervalSeconds
            MaxIterations = $MaxIterations
            Optimizer = $Optimizer
            NoOptimizer = $NoOptimizer
            LogFile = $LogFile
            Force = $Force
            Visible = $Visible
        }
        & (Join-Path $Root 'launch_tracker_scheduler.ps1') @startParams
        break
    }
    'status' {
        if ($Json) {
            $resolvedLog = Resolve-TrackerSchedulerLogFile -PathValue $LogFile
            Write-TrackerSchedulerJson -Value (Get-TrackerSchedulerStatus -ResolvedLogFile $resolvedLog)
        } else {
            & (Join-Path $Root 'status_tracker_scheduler.ps1')
        }
        break
    }
    'stop' {
        if ($Json) {
            $resolvedLog = Resolve-TrackerSchedulerLogFile -PathValue $LogFile
            $statusBefore = Get-TrackerSchedulerStatus -ResolvedLogFile $resolvedLog
            $stopOutput = (& (Join-Path $Root 'stop_tracker_scheduler.ps1') -Force:$Force 6>&1) | Out-String
            $statusAfter = Get-TrackerSchedulerStatus -ResolvedLogFile $resolvedLog
            $stoppedPids = @()
            foreach ($line in ($stopOutput -split "`r?`n")) {
                if ($line -match 'stopped PID (\d+)') {
                    $stoppedPids += [int]$Matches[1]
                }
            }
            Write-TrackerSchedulerJson -Value ([pscustomobject][ordered]@{
                action = 'stop'
                requestedForce = $Force.IsPresent
                before = $statusBefore
                after = $statusAfter
                stopped = ($stoppedPids.Count -gt 0)
                stoppedPids = $stoppedPids
                output = $stopOutput.Trim()
            })
        } else {
            & (Join-Path $Root 'stop_tracker_scheduler.ps1') -Force:$Force
        }
        break
    }
    'restart' {
        if ($Optimizer -and $NoOptimizer) {
            throw "Use either -Optimizer or -NoOptimizer with 'restart', not both."
        }
        & (Join-Path $Root 'stop_tracker_scheduler.ps1') -Force:$Force
        $startParams = @{
            IntervalSeconds = $IntervalSeconds
            MaxIterations = $MaxIterations
            Optimizer = $Optimizer
            NoOptimizer = $NoOptimizer
            LogFile = $LogFile
            Force = $true
            Visible = $Visible
        }
        & (Join-Path $Root 'launch_tracker_scheduler.ps1') @startParams
        break
    }
    'logs' {
        $resolvedLog = Resolve-TrackerSchedulerLogFile -PathValue $LogFile
        if (Test-Path $resolvedLog) {
            Get-Content -Path $resolvedLog -Tail $Tail
        } else {
            Write-Host "[TrackerScheduler] log file not found: $resolvedLog"
        }
        break
    }
    'clean' {
        $resolvedLog = Resolve-TrackerSchedulerLogFile -PathValue $LogFile
        $runningPid = $null
        $logSizeBefore = 0
        $stopOutput = $null
        $pidFileRemoved = $false
        $refused = $false

        if (Test-Path $resolvedLog) {
            $logSizeBefore = (Get-Item -Path $resolvedLog).Length
        }

        if (Test-Path $PidFile) {
            try {
                $pidText = Get-Content -Path $PidFile -Raw
                $candidatePid = [int]$pidText
                $proc = Get-Process -Id $candidatePid -ErrorAction SilentlyContinue
                if ($null -ne $proc) {
                    $runningPid = $candidatePid
                }
            } catch {
                $runningPid = $null
            }
        }

        if ($null -ne $runningPid -and -not $Force) {
            if ($Json) {
                $refused = $true
            } else {
                Write-Host "[TrackerScheduler] clean refused: scheduler is still running with PID $runningPid"
                Write-Host "[TrackerScheduler] stop it first or use -Force"
            }
        }

        if ($refused) {
            Write-TrackerSchedulerJson -Value ([pscustomobject][ordered]@{
                action = 'clean'
                cleaned = $false
                refused = $true
                reason = 'scheduler-running'
                runningPid = $runningPid
                requestedForce = $Force.IsPresent
                pidFile = $PidFile
                logFile = $resolvedLog
                logSizeBefore = $logSizeBefore
                logSizeAfter = $logSizeBefore
            })
            break
        }

        if ($null -ne $runningPid -and $Force) {
            $stopOutput = (& (Join-Path $Root 'stop_tracker_scheduler.ps1') -Force:$true 6>&1) | Out-String
        }

        if (Test-Path $PidFile) {
            Remove-Item -Path $PidFile -Force
            $pidFileRemoved = $true
        }

        New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedLog) -Force | Out-Null
        Set-Content -Path $resolvedLog -Value '' -Encoding utf8
        $logSizeAfter = (Get-Item -Path $resolvedLog).Length
        if ($Json) {
            Write-TrackerSchedulerJson -Value ([pscustomobject][ordered]@{
                action = 'clean'
                cleaned = $true
                refused = $false
                requestedForce = $Force.IsPresent
                pidFile = $PidFile
                pidFileRemoved = $pidFileRemoved
                logFile = $resolvedLog
                logSizeBefore = $logSizeBefore
                logSizeAfter = $logSizeAfter
                stopOutput = if ($null -ne $stopOutput) { $stopOutput.Trim() } else { $null }
            })
        } else {
            if ($pidFileRemoved) {
                Write-Host "[TrackerScheduler] pid file removed: $PidFile"
            } else {
                Write-Host "[TrackerScheduler] no pid file to remove"
            }
            Write-Host "[TrackerScheduler] log truncated: $resolvedLog"
            Write-Host "[TrackerScheduler] log size bytes: before=$logSizeBefore after=$logSizeAfter"
        }
        break
    }
    'once' {
        if (-not (Test-Path $Python)) {
            throw "Python executable not found: $Python"
        }
        if ($Optimizer -and $NoOptimizer) {
            throw "Use either -Optimizer or -NoOptimizer with 'once', not both."
        }
        $resolvedLog = Resolve-TrackerSchedulerLogFile -PathValue $LogFile
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        $pythonArgs = @(
            'tracker_system/main.py',
            '--scheduler',
            '--max-iterations', '1',
            '--interval-seconds', "$IntervalSeconds",
            '--scheduler-log-file', "$resolvedLog"
        )
        if (-not $Optimizer) {
            $pythonArgs += '--no-optimizer'
        }
        & $Python @pythonArgs
        $timer.Stop()
        Write-Host ("[TrackerScheduler] once summary: duration={0:N2}s optimizer={1} log={2}" -f $timer.Elapsed.TotalSeconds, $Optimizer.IsPresent, $resolvedLog)
        if ($TailLogs -gt 0) {
            if (Test-Path $resolvedLog) {
                Write-Host "[TrackerScheduler] last $TailLogs log lines:"
                Get-Content -Path $resolvedLog -Tail $TailLogs
            } else {
                Write-Host "[TrackerScheduler] log file not found: $resolvedLog"
            }
        }
        break
    }
}