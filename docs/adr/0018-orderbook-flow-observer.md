# ADR-0018 — Observatoire orderbook & flux de transactions (observer passif)

**Date :** 2026-08-20
**Statut :** Proposé
**Auteur :** Mathieu

---

## Contexte

L'opérateur souhaite disposer d'un observatoire temps réel du flux de
transactions et de la profondeur de carnet sur les symboles tradés, afin
d'améliorer sa compréhension du marché (murs de liquidité, imbalance
bid/ask, delta, flux en temps réel). Ce besoin est purement visuel et
analytique — il ne doit en aucun cas alimenter le moteur de décision
(ADR-0007 : passivité absolue des observers).

Le gel Phase II (CLAUDE.md §"Scientific Debt Rule") autorise les outils
de mesure, d'audit et de visualisation à condition qu'ils ne créent pas
de nouvelles variables expérimentales. Ce module est un outil de mesure
descriptif — il observe, enregistre et affiche, mais ne produit aucun
signal actionnable.

## Décision

Créer un module `orderbook_observer` strictement passif, isolé dans son
propre processus (service systemd `crypto-orderbook-observer.service`),
avec sa propre base SQLite (`databases/orderbook_flow.sqlite`), exposé
en lecture seule au dashboard existant via de nouveaux endpoints REST.

### Invariants obligatoires (repris de la roadmap)

1. **Aucun code de décision** (`quant_hedge_ai/engine/`, `core/advisor_loop.py`
   hot path, `risk/global_risk_gate.py`) ne lit les données produites par
   ce module.
2. **Stockage dédié** — `databases/orderbook_flow.sqlite`, jamais
   `market_data.sqlite`. Lecture seule pour tout consommateur hors module
   et dashboard.
3. **Aucune méthode publique** ne retourne de signal `BUY`/`SELL`/`SCORE` —
   uniquement des mesures descriptives (prix, quantité, delta, %).
4. **Feature flag** `ORDERBOOK_OBSERVER_ENABLED` (défaut `false`) — activation
   manuelle opérateur.
5. **Isolation process** — service systemd séparé. Une panne WebSocket ne
   fait jamais tomber la décision.

### Interdits explicites

- Toute injection dans le decision engine, même via "hint" ou "features enrichies".
- Toute règle de gate qui dépend de metrics orderbook.
- Toute config runtime qui bascule automatiquement en fonction du flux.

### Paramètres approuvés

- **Exchanges cibles** : MEXC (exchange principal du système)
- **Symboles** : `UNIVERSE_PINNED_SYMBOLS` (les 135 paires épinglées ADR-0017)
- **Rétention données** : 7 jours (configurable, `ORDERBOOK_RETENTION_DAYS=7`)
- **Budget disque estimé** : ~1 GB/jour pour orderbook complet, rotation automatique

## Alternatives rejetées

| Alternative | Raison du rejet |
|------------|----------------|
| Intégrer dans `advisor_loop.py` comme thread | Viole l'isolation process (invariant 5). Une panne WebSocket crasherait la décision. |
| Utiliser `market_data.sqlite` existant | Viole l'isolation stockage (invariant 2). Risque de contention et de pollution du dataset OHLCV propre. |
| Produire des "hints" passifs au moteur | Viole ADR-0007. Un hint est une influence, même optionnelle. |

## Conséquences

**Positives :**
- Compréhension humaine améliorée du marché en temps réel
- Détection visuelle de murs de liquidité, manipulations, squeeze
- Zéro impact sur le moteur de décision ni sur les métriques scientifiques

**Négatives / compromis :**
- Consommation réseau additionnelle (WebSocket streams)
- Charge disque ~1 GB/jour (rotation 7j = ~7 GB max)
- Nouveau service systemd à superviser

**Règles induites :**
- `ORDERBOOK_OBSERVER_ENABLED=false` dans `.env` par défaut
- Toute PR du module doit être auditée contre les 5 invariants ci-dessus
- Si un invariant est enfreint, la PR est rejetée — pas de dérogation sans nouvel ADR
