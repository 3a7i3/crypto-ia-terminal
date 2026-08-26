# Roadmap — Orderbook Flow Analyzer

**Status** : PLANIFIÉ, non commencé
**Date création** : 2026-08-18
**Bloqueur pratique** : requiert un poste de travail stable (pas d'exécution/debug sérieux depuis mobile SSH — cf. justification section "Contraintes")
**Conformité gel Phase II** : **compatible sous conditions** — voir section "Cadrage ADR-0007"

---

## Intention opérateur

Ajouter un observatoire temps réel du flux de transactions sur les top-N symboles tradés, exploitable depuis le dashboard http://\<vps\>:8050/ :

- Flux transactions live par symbole (prix, quantité, side)
- Snapshot orderbook par exchange (Binance, MEXC, ...)
- Delta bid/ask en direct (imbalance, wall detection)
- Niveaux de liquidité (concentration ordres à certains prix)
- Requête déclarative : "si le prix passe sous P, quel % des positions ouvertes bascule en perte ?"

Objectif : améliorer la **compréhension humaine** du marché en direct, pas alimenter le moteur de décision.

---

## Cadrage ADR-0007 — observer strictement passif

CLAUDE.md §"Règle constitutionnelle" impose que tout composant hors moteur de décision reste passif. Ce module doit donc satisfaire les invariants suivants pour être autorisé sous le gel Phase II :

**Invariants obligatoires**
1. Aucun code de décision (`quant_hedge_ai/engine/`, `core/advisor_loop.py` hot path, `risk/global_risk_gate.py`) ne lit les données produites par ce module.
2. Le stockage (SQLite dédié, jamais `market_data.sqlite` déjà utilisé par l'observer PR #42) est en lecture seule pour tout consommateur autre que le module lui-même et le dashboard.
3. Aucune méthode publique du module ne peut retourner un signal `BUY`/`SELL`/`SCORE` — uniquement des mesures descriptives (prix, quantité, delta, %).
4. Feature flag `ORDERBOOK_OBSERVER_ENABLED` (défaut `false`), même pattern que `ADVISOR_OHLCV_PERSISTENCE` — activation manuelle opérateur.
5. Isolation process : idéalement un service systemd séparé (`crypto-orderbook-observer.service`), pas un thread dans `advisor_loop.py`. Une panne WebSocket ne doit jamais faire tomber la décision.

**Interdits explicites**
- Toute injection dans le decision engine, même via "hint" ou "features enrichies".
- Toute règle de gate qui dépend de metrics orderbook.
- Toute config runtime qui bascule automatiquement en fonction du flux.

Si l'un de ces invariants est enfreint, ce n'est plus un observer — c'est une nouvelle couche de décision, **interdite par le gel Phase II sans ADR signé par l'opérateur**.

---

## Architecture cible (esquisse)

```
                                                      +--------------------------+
       Binance WebSocket ─┐                           |  crypto-orderbook-       |
       MEXC WebSocket    ─┤─→ orderbook_observer.py ─→|  observer.service        |
       (top-N symbols)    │   (asyncio + websockets)  |  (systemd, isolé)        |
                          │                           +-----------┬--------------+
                          │                                       │
                          └─→ trades_observer.py ────────────────→│
                              (fills stream)                      │
                                                                  ▼
                                    +----------------------------------------------+
                                    |  databases/orderbook_flow.sqlite (NOUVEAU)   |
                                    |  - trades(ts, symbol, exchange, price, qty)  |
                                    |  - orderbook_snapshots(ts, symbol, ...)      |
                                    |  - liquidity_levels(symbol, price, side, qty)|
                                    +----------------┬-----------------------------+
                                                     │
                                                     │ read-only
                                                     ▼
                             +--------------------------------------------------+
                             | scripts/dashboard_api.py (existant, endpoints    |
                             | ajoutés)                                         |
                             |   GET /api/flow/trades/{symbol}?since=...        |
                             |   GET /api/flow/orderbook/{symbol}               |
                             |   GET /api/flow/liquidity/{symbol}               |
                             |   GET /api/flow/portfolio-impact?price=P&sym=S   |
                             +--------------------------------------------------+
                                                     │
                                                     ▼
                                        Dashboard UI (nouvel onglet "Flow")
```

---

## Découpage en PRs (à faire depuis PC)

| # | Titre | Scope | Estimation |
|---|---|---|---|
| P1 | Base module + schema SQLite + feature flag | `orderbook_observer.py` squelette, schema `orderbook_flow.sqlite`, flag `ORDERBOOK_OBSERVER_ENABLED`, tests unitaires | 1-2j |
| P2 | Trades stream (Binance) | `TradesStreamBinance` via `ccxt.pro` ou `python-binance`, reconnect auto, persistance `trades` table | 2-3j |
| P3 | Orderbook stream (Binance) | `OrderbookStreamBinance`, snapshots à intervalle configurable, dedup, table `orderbook_snapshots` | 2-3j |
| P4 | Aggregations liquidity levels | Analyse offline : détection walls, concentrations, ratios bid/ask, table `liquidity_levels` | 1-2j |
| P5 | Endpoints dashboard | 4 endpoints FastAPI (trades, orderbook, liquidity, portfolio-impact) | 1j |
| P6 | Onglet UI "Flow" | Composants chart temps réel (bookdepth, tape, liquidity map), auto-refresh WebSocket ou SSE | 3-5j |
| P7 | Systemd service + doc ops | `scripts/systemd/crypto-orderbook-observer.service`, README, procédure démarrage/arrêt/rotation | 0.5j |
| P8 | (Optionnel) Extension MEXC | Même stream, exchange différent — testable en //, non bloquant | 1-2j |

**Total** : 12-18 jours-personne. Trop pour un sprint mobile.

---

## Requête "portfolio-impact" (D+E dans la roadmap globale)

Cette requête est **découplée** du module orderbook — elle peut être implémentée immédiatement depuis mobile (lit `paper_trades.jsonl` et positions ouvertes, calcule le PnL projeté à un prix hypothétique). C'est le chantier D+E, qui est prévu comme PR séparée **hors** de cette roadmap.

Ce document reprend juste `portfolio-impact` comme endpoint dashboard consommateur du reste, pour cohérence architecturale future.

---

## Contraintes qui justifient de reporter au PC

1. **Debug WebSocket en direct** — les streams se déconnectent aléatoirement (heartbeat perdu, throttle exchange, panne réseau VPS). Observer les reconnexions demande un `tail -f` continu sur plusieurs heures, sans quoi les corner cases restent invisibles. Mobile SSH scrollback insuffisant et session qui timeout.
2. **Soak tests** — 30 min à 4h pour valider tenue mémoire et reconnexion. Mobile s'endort, connexion tombe, log perdu.
3. **Comparaison side-by-side** — chart live orderbook + logs backend + code source demande un vrai écran multi-fenêtres.
4. **Volume de données** — orderbook full à 20 niveaux × 10 symboles × 2 exchanges ≈ 1 GB/jour. Debug `htop`/`iotop`/`sqlite3` interactif difficile depuis mobile.
5. **Itérations rapides deploy → observe → fix** — un bug WebSocket typique = 5-10 redéploiements. Sur mobile chaque cycle est 3-5x plus long qu'au PC.
6. **Bandwidth du chat** — les logs WebSocket produisent beaucoup de bruit, saturer les échanges Claude Code depuis mobile devient coûteux.

---

## Références internes

- Observer précédent (autorisé) : PR #42 — `feat(observer): persistance OHLCV passive dans advisor_loop (ADR-0007)`
- Backfill compagnon : PR #47 — `scripts/backfill_ohlcv.py`
- Règle Phase II : CLAUDE.md §"Scientific Debt Rule — Gel architectural"
- ADR passivité : ADR-0007 (à référencer explicitement dans la PR P1)

---

## Décision opérateur attendue avant de démarrer

Signer un ADR ("ADR-XXXX-orderbook-observer.md") qui :
1. Rappelle les invariants de la section "Cadrage ADR-0007" ci-dessus.
2. Nomme les exchanges cibles (Binance seul ? +MEXC ? autre ?).
3. Fixe la liste initiale des symboles (top-10 tradés ? UNIVERSE_PINNED_SYMBOLS entier ?).
4. Approuve la création du service systemd isolé.
5. Confirme le budget disque (1 GB/j nominal, rétention 7/14/30j).

Sans cet ADR, la PR P1 ne peut pas être ouverte — le gel Phase II bloque toute nouvelle couche non validée.
