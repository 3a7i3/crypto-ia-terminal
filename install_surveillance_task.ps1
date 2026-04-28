# Script PowerShell pour installer la surveillance continue comme tâche planifiée Windows

$action = New-ScheduledTaskAction -Execute "c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe" -Argument "c:/Users/WINDOWS/crypto_ai_terminal/surveillance_continue.py"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd -StartWhenAvailable
Register-ScheduledTask -TaskName "SurveillanceContinueQuant" -Action $action -Trigger $trigger -Settings $settings -Description "Surveillance continue de l'écosystème quantitatif (orchestration + dashboard) toutes les 30 minutes."
Write-Host "Tâche planifiée 'SurveillanceContinueQuant' créée. Elle vérifiera l'écosystème toutes les 30 minutes."
