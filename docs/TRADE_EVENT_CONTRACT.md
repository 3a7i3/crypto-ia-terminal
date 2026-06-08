# TRADE EVENT CONTRACT

> Statut : ACTIF — définit la source de vérité unique pour tout PnL.
> Rédigé : 2026-06-04
> Ne pas modifier sans mettre à jour les tests `test_trade_event.py`.

---

## Structure canonique

```python
@dataclass(frozen=True)
class TradeEvent:
    trade_id: str
    symbol: str
    side: str                # "buy" | "sell"
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl_usd: float
    fees_usd: float
    slippage_usd: float
    execution_mode: str      # "backtest" | "paper" | "live"
    strategy_id: str
    run_id: str
    opened_at: datetime
    closed_at: datetime

    @property
    def net_pnl_usd(self) -> float:
        return self.gross_pnl_usd - self.fees_usd - self.slippage_usd
```

---

## Invariant fondamental

```
net_pnl_usd = gross_pnl_usd - fees_usd - slippage_usd
```

Toujours. Partout. Sans exception.

`net_pnl_usd` est une propriété dérivée — elle ne peut pas être fixée indépendamment.
C'est la garantie structurelle que l'invariant ne sera jamais violé.

---

## Producteurs autorisés

Seuls ces modules peuvent instancier un `TradeEvent` :

| Module | Mode |
|--------|------|
| `ExecutionRouter` | tous modes |
| `ExecutionSimulator` (via `SimulatorAdapter`) | `backtest`, `paper` |
| `LiveExchange` (via `CcxtAdapter`) | `live` |

Aucun autre module ne crée de `TradeEvent`.

---

## Consommateurs autorisés

Les consommateurs lisent le `TradeEvent`. Ils ne recalculent rien.

| Module | Rôle |
|--------|------|
| `Portfolio` | mise à jour du solde (balance += net_pnl_usd) |
| `TradeLogger` | persistance SQLite / JSONL |
| `Analytics` / `EdgeScorer` | métriques PF, Sharpe, WR |
| `Telegram bots` | affichage — lecture seule |
| `RiskLayer` | mise à jour drawdown, streak |
| `MistakeMemory` / `RegretEngine` | apprentissage post-trade |

---

## Interdictions absolues

**Un consommateur ne modifie jamais un `TradeEvent`.**

`frozen=True` l'interdit au niveau Python. C'est intentionnel.

**Un consommateur ne recalcule jamais le PnL.**

Si un module calcule `(exit - entry) * qty`, c'est un bug.
Il doit lire `trade_event.net_pnl_usd`.

**Telegram ne calcule rien.**

Les bots sont des écrans. Ils affichent des champs du `TradeEvent`.

---

## Ce qui n'appartient PAS à TradeEvent

Les détails d'implémentation du simulateur vont dans `ExecutionMetadata` (structure séparée, non encore créée) :

```
eta             — impact de marché Almgren-Chriss
noise_bps       — bruit d'exécution ENL
latency_ms      — latence simulée
fill_rate       — fraction exécutée
noise_model     — modèle utilisé
```

`TradeEvent` est un événement métier.
`ExecutionMetadata` est un rapport d'exécution.
Les deux sont liés par `trade_id`, jamais fusionnés.

---

## Relation avec les types Position existants

Trois types `Position` coexistent aujourd'hui (dette connue) :

| Type | Fichier | Action future |
|------|---------|---------------|
| `Position` | `src/domain/position.py` | garder — position ouverte |
| `VirtualPosition` | `paper_trading/virtual_portfolio.py` | produire `TradeEvent` à la clôture, supprimer le calcul PnL interne |
| `MexcPosition` | `paper_trading/mexc_simulator.py` | idem |

`Position` représente un état ouvert.
`TradeEvent` représente une clôture.
Ce sont deux concepts distincts — ne pas les fusionner.

---

## Gate de migration

La migration des simulateurs existants vers `TradeEvent` est conditionnée à :

```
closed_trades >= 100   (ALPHA_DISCOVERY_100)
```

Raison : les paramètres ENL (`eta`, `noise_bps`, `taker_rate`) doivent être
calibrés sur données réelles avant que `ExecutionSimulator` devienne référence.

Ce contrat peut être défini et les tests écrits avant ce gate.
L'implémentation dans les simulateurs attend le gate.

---

## Checklist d'adoption (post-100 trades)

```
[ ] test_trade_event.py — invariant net = gross - fees - slip
[ ] SimulatorAdapter produit TradeEvent à chaque close_position
[ ] VirtualPortfolio._close_position émet TradeEvent via router
[ ] MexcSimulator._close_position émet TradeEvent via router
[ ] Portfolio.update(event: TradeEvent) remplace tous les recalculs PnL
[ ] TradeLogger.log(event: TradeEvent) remplace les logs custom
[ ] Telegram bots lisent TradeEvent — supprimer calculs locaux
```
