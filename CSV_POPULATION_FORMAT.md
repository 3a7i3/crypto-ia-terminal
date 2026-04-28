# Format attendu des fichiers CSV de population

Chaque fichier CSV de population (ex : `pop_gen_0.csv`, `chaos_pop_gen_0.csv`, etc.) doit respecter le format suivant :

## Colonnes obligatoires
- **id** : identifiant unique de la stratégie
- **fitness** : score de fitness (float)
- **species** : nom ou type d’espèce (str)
- **exit.tp** : valeur du Take Profit (float)
- **exit.sl** : valeur du Stop Loss (float)

## Colonnes recommandées (pour analyses avancées)
- **entry.type** : type d’entrée (ex : trend, mean_reversion, hybrid)
- **entry.rsi_period** : période RSI utilisée (float)
- **entry.rsi_buy** : seuil d’achat RSI (float)
- **ma_short** : période de la moyenne mobile courte (float)
- **ma_long** : période de la moyenne mobile longue (float)
- **ma_signal** : type de signal MA (str)
- **risk.risk_per_trade** : risque par trade (float)
- **environment** : environnement de simulation (str)
- **world** : nom du monde (str)
- **parent_ids** : identifiants des parents (str ou liste)

## Exemple de première ligne (header)

id,fitness,species,exit.tp,exit.sl,entry.type,entry.rsi_period,entry.rsi_buy,ma_short,ma_long,ma_signal,risk.risk_per_trade,environment,world,parent_ids

## Contraintes
- Toutes les colonnes obligatoires doivent être présentes et sans valeurs manquantes.
- Les fichiers doivent être encodés en UTF-8.
- Les valeurs numériques doivent utiliser le point comme séparateur décimal.

## Validation
Utilisez le script `test_validate_population_csv.py` pour vérifier automatiquement la conformité de vos fichiers CSV.

---
Pour toute question ou exemple détaillé, consultez la documentation du dashboard ou contactez l’équipe technique.
