```{dropdown} Profiler & Monitoring – Orchestration & Utilisation

- Les scripts `strategy_factory/backtest_profiler.py` et `supervision/monitoring_profiler.py` sont désormais appelés automatiquement à la fin de l'orchestration (voir orchestrate_all.py et orchestrate_ecosystem.py).
- Options CLI disponibles pour personnaliser la durée, la taille, le log, etc.
- Les logs et résultats sont sauvegardés dans le dossier `results/`.
- Robustesse accrue : gestion d'erreur, logs détaillés, options de sauvegarde.

**Utilisation manuelle** :
```bash
python strategy_factory/backtest_profiler.py --n 5000 --n_strat 4 --logfile results/backtest_profiler.log --save results/backtest_profiler_results.csv
python supervision/monitoring_profiler.py --duration 5 --logfile results/monitoring_profiler.log
```

**Intégration automatique** : rien à faire, inclus dans l'orchestration.

Voir les fichiers results/backtest_profiler.log et results/monitoring_profiler.log pour les logs détaillés.
```
