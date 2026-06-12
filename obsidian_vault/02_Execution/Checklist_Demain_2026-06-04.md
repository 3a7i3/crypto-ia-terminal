# Checklist — Reste à faire (depuis 2026-06-04)

## Self-heal exchange (P2)

- [ ] Ajouter ExecutionEngine.reconnect()
- [ ] Ajouter retry CCXT (3 essais + reconnect + dernier essai)
- [ ] Brancher restart_fn exchange reel dans advisor_loop
- [ ] Verifier logs de reconnexion attendus

## Corrections VPS mineures

- [ ] Supprimer `_notify()` pour rejets "position deja ouverte" dans `paper_trading/mexc_simulator.py`
- [ ] Nettoyer `databases/runtime_config.json` — supprimer GATE_MIN_SCORE_OVERRIDE=0

## Persistance paper trading

- [ ] Brancher `PaperTradeRecorder` dans `MexcSimulator._fill_market()` et `_close_position()`

## Observation passive (pas de code)

- [ ] Surveiller Telegram @QuantCrpto_bot — trades SIM fermes (TP/SL)
- [ ] Compter N trades fermes vers objectif 100

## Notes

- Conserver mode paper/simule tant que burn-in non valide
- Ne pas toucher GATE_MIN_SCORE_OVERRIDE ni PB_MIN_POSITION_USD (gel ALPHA_DISCOVERY_100)
