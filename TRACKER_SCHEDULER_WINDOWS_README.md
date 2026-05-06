# Tracker Scheduler (Windows)

## Helper unique

Commande recommandée:

```powershell
.\tracker_scheduler.ps1 start -IntervalSeconds 300 -LogFile tracker_system/logs/auto_update.log
.\tracker_scheduler.ps1 status
.\tracker_scheduler.ps1 status -Json
.\tracker_scheduler.ps1 stop
.\tracker_scheduler.ps1 stop -Json
.\tracker_scheduler.ps1 restart -IntervalSeconds 300 -LogFile tracker_system/logs/auto_update.log
.\tracker_scheduler.ps1 once -NoOptimizer -TailLogs 20
.\tracker_scheduler.ps1 once -Optimizer -TailLogs 20
.\tracker_scheduler.ps1 logs -Tail 50
.\tracker_scheduler.ps1 clean -Force
.\tracker_scheduler.ps1 clean -Force -Json
```

Options utiles:
- Ajouter `-NoOptimizer` sur `start`, `restart` ou `once` pour ne pas relancer l'optimizer.
- Ajouter `-Optimizer` sur `start`, `restart` ou `once` pour l'exécuter explicitement.
- Ajouter `-Force` sur `start` pour relancer même si un PID existe déjà.
- Ajouter `-Force` sur `stop` pour forcer l'arrêt.
- Ajouter `-Visible` sur `start` pour laisser la fenêtre visible.
- Utiliser `restart` pour enchaîner arrêt + relance.
- Utiliser `logs` pour afficher les dernières lignes de `auto_update.log`.
- Utiliser `clean -Force` pour arrêter un scheduler encore actif, supprimer `scheduler.pid` et tronquer `auto_update.log`.
- Utiliser `-Json` sur `status`, `stop` et `clean` pour une intégration scriptable.

## Schémas JSON

### status -Json

```powershell
.\tracker_scheduler.ps1 status -Json | ConvertFrom-Json
```

Champs renvoyés:
- `state`: `running`, `stale-pid-file`, `invalid-pid-file` ou `stopped`
- `isRunning`: booléen
- `source`: `pid-file`, `fallback-scan` ou `none`
- `pids`: tableau de PID détectés
- `pidFile`: chemin absolu du fichier PID
- `logFile`: chemin absolu du log scheduler
- `message`: résumé texte du statut

Exemple:

```json
{
	"state": "running",
	"isRunning": true,
	"source": "pid-file",
	"pids": [12345],
	"pidFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\scheduler.pid",
	"logFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\auto_update.log",
	"message": "RUNNING PID 12345"
}
```

### stop -Json

```powershell
.\tracker_scheduler.ps1 stop -Json | ConvertFrom-Json
```

Champs renvoyés:
- `action`: `stop`
- `requestedForce`: booléen indiquant si `-Force` a été demandé
- `before`: objet de statut avant l'arrêt, même schéma que `status -Json`
- `after`: objet de statut après l'arrêt, même schéma que `status -Json`
- `stopped`: booléen indiquant si au moins un PID a été arrêté
- `stoppedPids`: tableau des PID arrêtés
- `output`: sortie texte capturée du script d'arrêt

Exemple:

```json
{
	"action": "stop",
	"requestedForce": false,
	"before": {
		"state": "running",
		"isRunning": true,
		"source": "pid-file",
		"pids": [12345],
		"pidFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\scheduler.pid",
		"logFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\auto_update.log",
		"message": "RUNNING PID 12345"
	},
	"after": {
		"state": "stopped",
		"isRunning": false,
		"source": "none",
		"pids": [],
		"pidFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\scheduler.pid",
		"logFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\auto_update.log",
		"message": "STOPPED"
	},
	"stopped": true,
	"stoppedPids": [12345],
	"output": "[TrackerScheduler] stopped PID 12345"
}
```

### clean -Json

```powershell
.\tracker_scheduler.ps1 clean -Force -Json | ConvertFrom-Json
```

Champs renvoyés en succès:
- `action`: `clean`
- `cleaned`: booléen
- `refused`: booléen
- `requestedForce`: booléen indiquant si `-Force` a été demandé
- `pidFile`: chemin absolu du fichier PID
- `pidFileRemoved`: booléen indiquant si le fichier PID a été supprimé
- `logFile`: chemin absolu du log scheduler
- `logSizeBefore`: taille du log avant troncature en octets
- `logSizeAfter`: taille du log après troncature en octets
- `stopOutput`: sortie texte du stop forcé si un scheduler était encore actif

Si `clean` refuse de s'exécuter parce qu'un scheduler tourne encore sans `-Force`, la réponse garde `action`, `refused`, `runningPid`, `requestedForce`, `pidFile`, `logFile`, `logSizeBefore` et `logSizeAfter`, avec `cleaned=false` et `reason=scheduler-running`.

Exemple:

```json
{
	"action": "clean",
	"cleaned": true,
	"refused": false,
	"requestedForce": true,
	"pidFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\scheduler.pid",
	"pidFileRemoved": true,
	"logFile": "C:\\Users\\WINDOWS\\crypto_ai_terminal\\tracker_system\\logs\\auto_update.log",
	"logSizeBefore": 1010,
	"logSizeAfter": 5,
	"stopOutput": "[TrackerScheduler] stopped PID 12345"
}
```

## Start

```powershell
.\launch_tracker_scheduler.ps1 -IntervalSeconds 300 -LogFile tracker_system/logs/auto_update.log
```

Options:
- Ajouter `-NoOptimizer` pour rafraîchir dashboard et métriques sans relancer l'optimizer.
- Ajouter `-Optimizer` pour l'exécuter explicitement.
- Ajouter `-Force` pour relancer même si un PID existe déjà.
- Ajouter `-Visible` pour garder la fenêtre visible.

## Status

```powershell
.\status_tracker_scheduler.ps1
```

Le script texte renvoie l'un des statuts suivants:
- `RUNNING PID <id>`
- `STALE PID FILE`
- `INVALID PID FILE`
- `STOPPED`

## Stop

```powershell
.\stop_tracker_scheduler.ps1
```

Options:
- Ajouter `-Force` pour forcer l'arrêt.

## Notes

- PID file path: `tracker_system/logs/scheduler.pid`
- Scheduler log path (default): `tracker_system/logs/auto_update.log`