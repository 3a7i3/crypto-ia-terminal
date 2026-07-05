# Audit trade_log.sqlite

```
==============================================================
SQLITE AUDIT — trade_log.sqlite (LECTURE SEULE)
Base   : databases\trade_log.sqlite
Généré : 2026-07-04 15:25:56 UTC
==============================================================

Tables : trades

── Observations ─────────────────────────────────────────
Trades total ....... 70
Premier ............ 2026-05-01 01:13:47 UTC
Dernier ............ 2026-07-03 06:04:50 UTC
Répartition mode   : rejected=52, futures_demo=15, live=2, live_failed=1
Répartition status : rejected=52, ok=17, error=1
Répartition action : BUY=53, ∅=17
Symboles (top 15) .. BTC/USDT(55), BTC/USDT:USDT(10), ETH/USDT:USDT(5)

── Détection de contamination ───────────────────────────
[INFO    ]    53  notional NULL (champ jamais rempli par le flux réel ?)
            ids: 1, 3, 23, 29, 34, 36, 37, 41, 49, 53, 57, 61 … (+41)
(aucune heuristique CRITICAL/HIGH déclenchée)

── Conclusion ───────────────────────────────────────────
Trades total ....... 70
Authentiques ....... 70
Suspects (C/H) ..... 0

RÉSULTAT : PASS
```
