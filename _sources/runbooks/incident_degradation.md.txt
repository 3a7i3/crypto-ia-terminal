# Incident Runbook — Dégradation OOS

## Détection

**Source:** `monitor/degradation_tracker.py` + `walk_forward/reporter.py`

**Déclencheurs:**
- DegradationEvent de niveau `critical` émis
- `is_degrading = True` sur le tracker
- Alerte `CRITICAL` dans le daily report (section Walk-Forward)

## Symptômes

- Sharpe OOS en baisse continue sur les derniers folds
- Win rate sous le plancher critique (25%)
- Tendance négative confirmée par Mann-Kendall (tau < 0, p < 0.05)
- Écart croissant entre Sharpe train et OOS (overfitting ratio < 0.5)

## Actions immédiates

1. **Geler les décisions basées sur ce modèle**
   - Marquer la stratégie comme `degrading` dans le registre
   - Exclure des prochains runs de walk-forward tant que non résolu

2. **Diagnostic**
   ```bash
   python walk_forward/reporter.py --json
   ```
   - Vérifier le dernier fold: y a-t-il un changement de régime?
   - Comparer les métriques train vs OOS sur les 5 derniers folds
   - Regarder les trades individuels: y a-t-il un pattern d'échec?

3. **Analyse racine**
   - Changement de régime de marché (bull → bear, stable → volatile)?
   - Surcharge de paramètres (overfitting)?
   - Données d'entrée corrompues ou dégradées?
   - Latence / slippage anormal dans le simulateur?

## Résolution

| Cause probable | Action |
|---|---|
| Changement de régime | Ré-entraîner sur fenêtre plus récente, ajouter détection de régime |
| Overfitting | Réduire le nombre de paramètres, augmenter le nombre de folds |
| Données corrompues | Rejouer l'ingestion, valider les OHLCV |
| Simulateur dégradé | Vérifier `fill_error_metric.py`, recalibrer slippage/latence |

## Post-mortem

- Documenter la cause racine dans `reports/postmortem/`
- Ajouter un test de non-régression si applicable
- Mettre à jour les seuils de dégradation si nécessaire

## Prévention

- Seuils de dégradation ajustables par régime de marché
- Alerte proactive dès que Sharpe OOS < 1.0 sur 3 folds consécutifs
- Revue hebdomadaire des métriques de stabilité
