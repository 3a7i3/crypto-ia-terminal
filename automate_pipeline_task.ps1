# automate_pipeline_task.ps1
# Script PowerShell pour planifier l'exécution automatique du pipeline d'analyse évolutive

$scriptPath = "C:\Users\WINDOWS\crypto_ai_terminal\automate_pipeline.py"
$pythonExe = "C:\Users\WINDOWS\crypto_ai_terminal\.venv\Scripts\python.exe"
$taskName = "AutomateEvolutionPipeline"

# Crée une tâche planifiée qui exécute le pipeline tous les jours à 2h du matin
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Description "Pipeline d'analyse évolutive automatisé"
Write-Host "Tâche planifiée '$taskName' créée pour exécuter le pipeline chaque nuit à 2h."
