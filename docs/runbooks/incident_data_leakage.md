# Incident Runbook — Fuite de Données (Data Leakage)

## Détection

**Source:** `walk_forward/window_splitter.py` + `walk_forward/engine.py`

**Déclencheurs:**
- `WalkForwardWindow.__post_init__` lève `ValueError` (train_end > test_start)
- Sharpe OOS anormalement élevé (> 5.0) alors que le train est médiocre
- Overfitting ratio > 1.2 (OOS meilleur que train — suspect)
- Corrélation suspecte entre métriques train et OOS

## Symptômes

- Résultats OOS trop beaux pour être vrais
- Pas de dégradation détectée alors que le marché a changé
- Les métriques OOS ressemblent étrangement aux métriques train
- Erreur `ValueError: Fold X: data leakage detected` au démarrage

## Actions immédiates

1. **Vérifier les fenêtres**
   ```bash
   python -c "
   from walk_forward.window_splitter import WindowSplitter
   ws = WindowSplitter(n_samples=1000, train_size=500, test_size=100, step=200)
   for w in ws.split():
       print(f'Fold {w.fold_index}: train=[{w.train_start}:{w.train_end}] test=[{w.test_start}:{w.test_end}]')
       assert w.train_end <= w.test_start, 'LEAKAGE'
   print('Toutes les fenetres sont propres.')
   "
   ```

2. **Vérifier les données passées aux callables**
   - `run_fold` découpe-t-elle physiquement `data[train_start:train_end]`?
   - L'optimiseur reçoit-il uniquement les données train?
   - Le validateur reçoit-il uniquement les données test?

3. **Vérifier les features**
   - Les features utilisent-elles des données futures (ex: close future, indicateur lookahead)?
   - Vérifier les transformations: rolling window centrée? shift manquant?

## Résolution

| Cause probable | Action |
|---|---|
| Fenêtre mal configurée | Ajuster `train_size`, `test_size`, `step`, `gap` dans WindowSplitter |
| Feature lookahead | Remplacer les indicateurs centrés par des indicateurs décalés (shift) |
| Normalisation globale | Remplacer par normalisation rolling (fenêtre glissante uniquement) |
| Données triées incorrectement | Vérifier l'ordre chronologique des données en entrée |
| Gap insuffisant | Ajouter un gap entre train et test pour éviter la contamination |

## Check-list de validation

- [ ] `train_end <= test_start` pour tous les folds
- [ ] Aucune feature n'utilise de données au-delà de son timestamp
- [ ] Les métriques OOS sont calculées uniquement sur les données test
- [ ] Le paramètre `gap` est >= 1 pour les séries temporelles
- [ ] Les indicateurs techniques utilisent `rolling.shift(1)` et non `rolling`
- [ ] Le walk-forward est reproductible (même seed = mêmes résultats)

## Post-mortem

- Ajouter un test de non-régression qui détecte spécifiquement ce type de fuite
- Documenter la cause racine et la correction
- Vérifier que tous les modules de la chaîne sont exempts de fuite

## Prévention

- `WalkForwardWindow` lève une exception à la construction si `train_end > test_start` — ne jamais désactiver cette garde
- Revue de code obligatoire pour toute nouvelle feature avant intégration
- Test de détection de fuite automatique dans la CI
