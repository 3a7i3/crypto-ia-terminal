# Archive — paper_trades corrompu (2026-06-14)

## Raison de l'archivage

Dataset invalide généré par un bug dans `_restore_positions()` de `paper_trading/mexc_simulator.py`.

## Symptômes détectés par validate_corpus()

- 95 trade_id(s) dupliqués
- 2 OPEN sans CLOSE (positions fantômes)
- win_rate=100% sur 27 trades (statistiquement impossible)
- Zéro SL déclenché sur 27 trades

## Cause racine

Au restart du simulateur, `_restore_positions()` recalculait le TP à `entry * 1.04`
sans vérifier le prix courant. Si BTC avait progressé de +4% pendant le downtime,
la position fermait immédiatement comme TP sur le premier tick (duration=0s).
Les positions étaient re-créées à chaque restart avec un nouvel ID → duplicates.

## Fix appliqué

`SIM_RESTORE_MAX_AGE_H=4` (défaut) — toute position ouverte depuis plus de 4h
est archivée dans le ledger avec `reason="expired_on_restore"` et ne peut
plus être restaurée.

Commit : voir git log paper_trading/mexc_simulator.py

## Utilisation

Ce fichier est conservé pour le debug uniquement.
Ne jamais l'utiliser dans une analyse burn-in ou calibration.
Il ne sera jamais lu par le système (paper_trades.jsonl actif est vide).
