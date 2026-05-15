# Incident Runbook — Latence Anormale

## Détection

**Source:** `monitoring/pipeline_monitor.py` + `monitoring/profiler.py`

**Déclencheurs:**
- Latence moyenne d'exécution > 2x la baseline sur 10 trades consécutifs
- P95 fill latency > 500ms
- Durée d'un fold walk-forward > 3x la moyenne historique
- Alerte `WARNING` ou `CRITICAL` dans le daily report

## Symptômes

- Trades qui prennent anormalement longtemps à s'exécuter
- Pipeline de backtest ralenti sans raison apparente
- Profilage CPU/Memory anormal

## Actions immédiates

1. **Profiler le pipeline**
   ```bash
   python -c "
   from monitoring.profiler import Profiler
   p = Profiler()
   result, report = p.profile(run_pipeline)
   report.write_markdown('reports/profiling_incident.md')
   print(report.summary_line())
   "
   ```

2. **Vérifier les ressources système**
   - CPU: `top -bn1 | head -20`
   - Mémoire: `free -m`
   - Disque: `df -h`
   - Processus Python: `ps aux | grep python`

3. **Identifier le goulot**
   - Regarder le top 5 des fonctions dans le rapport de profiling
   - Vérifier si un module spécifique (ingestion, calcul, I/O) est en cause
   - Tester l'isolation: chaque module séparément

## Résolution

| Cause probable | Action |
|---|---|
| I/O disque saturé | Déplacer les données en RAM / cache, optimiser les lectures |
| Algorithme O(n²) | Revoir la complexité, ajouter du caching |
| Garbage collection | Réduire les allocations, utiliser des pools d'objets |
| API rate limité | Vérifier les appels réseau, ajouter du caching |
| Base de données lente | Optimiser les requêtes, ajouter des index |

## Post-mortem

- Ajouter un test de performance avec seuil (`tests/stress/`)
- Mettre à jour les benchmarks de référence
- Si récurrent: ajouter un monitoring temps réel sur ce métrique

## Prévention

- Benchmark de référence après chaque modification majeure
- Profilage automatique hebdomadaire
- Seuil d'alerte sur le temps d'exécution des tests d'intégration
