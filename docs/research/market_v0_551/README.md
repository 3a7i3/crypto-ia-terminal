# Prototype marché V0 hors réseau — #551

**DESIGN_ONLY / OFFLINE / NON_ADMIS.** Suite de #546/#548. Pas de collecte, pas de flux, pas de publication.

- [Revue indépendante, verdicts et conditions](REVIEW_551.md)
- [Décision structurée](DECISION.json)
- [Prototype L2 (stdlib)](l2_reconstruction_prototype.py)
- [Fixtures inventées](SYNTHETIC_L2_FIXTURES.json)
- Tests : `tests/market_venues/test_l2_prototype_551.py`

```bash
python -B -m pytest tests/market_venues/test_l2_prototype_551.py -p no:cacheprovider
```

Le prototype n'est importé par aucun producteur, reader, API ou frontend (test dédié).
Les valeurs inconnues restent `None` avec une raison ; aucune sortie ne contient de mid, spread ou métrique.
