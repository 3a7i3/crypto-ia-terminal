# DECISION_PATH.md — Chemin exact de la décision
> **Document généré automatiquement.** Ne pas éditer à la main.
> Source : `artifacts/cartography.json` — régénérer via
> `python tools/runtime_cartographer.py && python tools/cartography_report.py`
> Généré le 2026-08-01 — commit `348e83d`

> **Portée de la mesure.** Graphe d'import statique (AST), imports paresseux
> inclus. `ACTIVE` signifie **atteignable par import** depuis le point d'entrée
> runtime, **pas** « exécuté ». Prouver l'exécution exige une trace runtime
> (`sys.settrace`/coverage sur le VPS) — **NON MESURÉ** en J1-J2.

Toutes les lignes ci-dessous sont **sondées dans le fichier**, pas recopiées d'une documentation.

| # | Étape | Fichier | Ligne(s) mesurée(s) | Code sondé |
|---|---|---|---|---|
| | 0. Autorité — court-circuit d'entrée | `core/advisor_loop.py` | 1112, 1933 | `if not _auth.can_trade():` |
| | 1. Régime de marché | `core/advisor_loop.py` | 1126, 1190, 1326, 1328 | `regime="unknown",` |
| | 2. Features | `core/advisor_loop.py` | 1448, 1461, 1638, 1649 | `features=features,` |
| | 3. Personnalité (Meta-Strategy) | `core/advisor_loop.py` | 1446 | `personality = meta_engine.select(` |
| | 4. Signal | `core/advisor_loop.py` | 1460 | `signal = engine.evaluate(` |
| | 5. DecisionPacket (parallèle) | `core/advisor_loop.py` | 1481 | `_dp = _to_decision_packet(signal, cycle_id=str(cycle))` |
| | 6. Validation Meta-Strategy | `core/advisor_loop.py` | 1521 | `meta_allowed, meta_reason = meta_engine.validate_signal(` |
| | 7. Conviction | `core/advisor_loop.py` | 1072, 1109, 1150, 1211 | `conviction_engine: Any = None,` |
| | 8. MistakeMemory | `core/advisor_loop.py` | 1155, 1216, 1628, 1632 | `"mm_check": None,` |
| | 9. PortfolioBrain | `core/advisor_loop.py` | 1662, 1665 | `pb_verdict = None` |
| | 10. CapitalAllocationEngine | `core/advisor_loop.py` | 1690, 1707, 5604 | `allocation = None` |
| | 11. ExecutiveOverride | `core/advisor_loop.py` | 1782 | `eo_verdict = executive_override.check_trade(` |
| | 12. Arbitrage V2 | `core/advisor_loop.py` | 1860 | `arbitration_result = v2_arbitrator.arbitrate(arb_votes)` |
| | 13. Timing V2 | `core/advisor_loop.py` | 1877 | `timing_signal = v2_timing_engine.evaluate(` |
| | 14. DÉCISION | `core/advisor_loop.py` | 1983 | `trade_allowed = (` |
| | 15. Révocations | `core/advisor_loop.py` | 5626, 5658, 5734, 5808 | `r["trade_allowed"] = False` |
| | 16. Exécution | `core/advisor_loop.py` | 1960, 3396, 3402, 3486 | `# Sinon les logs affichent $0.00 et l'execution_engine fallback` |

## Les 12 termes de la conjonction finale

Mesuré à `core/advisor_loop.py:1983`.

```python
    trade_allowed = (
        _authority_ok
        and meta_allowed
        and gate_result.allowed
        and _awareness_ok
        and _conviction_ok
        and _notrade_ok
        and _pb_ok
        and _cae_ok
        and _mm_ok
        and _eo_ok
        and _radar_ok
        and _arb_ok
    )
```

**Nombre de termes mesurés : 12**

## Étapes du flux non démontrables en J1-J2


| Étape | Statut |
|---|---|
| Ordre d'exécution réel des couches à l'exécution | **IMPOSSIBLE À DÉMONTRER AVEC LES ÉLÉMENTS ACTUELS** — exige une trace runtime |
| Fréquence de déclenchement de chaque révocation | **NON MESURÉ** — exige une instrumentation de compteurs en production |
| Effet marginal de chaque couche sur le débit | **NON MESURÉ** — exige un moteur d'ablation |
| Moteur de replay déterministe | **NON MESURÉ** — aucun module correspondant identifié dans le graphe runtime |
