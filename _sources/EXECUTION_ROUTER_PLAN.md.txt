# EXECUTION ROUTER — Plan de refactor post-burn-in

> **Statut :** EN ATTENTE — déployer uniquement après `closed_trades >= 100` (ALPHA_DISCOVERY_100)
> **Rédigé :** 2026-06-04
> **Objectif :** Brancher `ExecutionSimulator` comme seul moteur d'exécution pour backtest, paper et live.

---

## Contexte

### Problème actuel

Quatre modèles d'exécution coexistent sans partager de logique :

| Composant | Moteur d'exécution | Slippage | Fees | Latence |
|---|---|---|---|---|
| `BacktestEngine` | `VirtualExchange` | ❌ | ❌ | ❌ |
| `VirtualPortfolio` | propre | fixe 0.1% | ✅ fixe | ❌ |
| `PaperTradingEngine` | propre | ❌ | ❌ | ❌ |
| `ExecutionSimulator` | calibré | ✅ Almgren-Chriss | ✅ maker/taker | ✅ GBM |

Le `ExecutionRouter` existe déjà (`src/engine/execution_router.py`) mais est un stub 12 lignes, mode "sim" uniquement, wrappant `VirtualExchange`.

### État du router actuel

```python
# src/engine/execution_router.py — ÉTAT ACTUEL (stub)
class ExecutionRouter:
    def __init__(self, sim_engine):
        self.sim_engine = sim_engine   # toujours VirtualExchange
        self.mode = "sim"              # mode unique, jamais changé

    def execute(self, order: Order, price: float) -> Position:
        return self.sim_engine.place_order(order, price)
```

Problème secondaire : `BacktestEngine` accède directement à `router.sim_engine.close_position()` — couplage à l'implémentation.

---

## Architecture cible

```
                    ExecutionRouter
                    ┌─────────────┐
   BacktestEngine ──►             ├──► SimulatorAdapter ──► ExecutionSimulator (calibré)
  VirtualPortfolio ──►    router  ├──► SimulatorAdapter ──► ExecutionSimulator (calibré)
       LiveEngine ──►             ├──► CcxtAdapter       ──► Exchange réel (CCXT)
                    └─────────────┘
                          │
                          ▼
                     TradeEvent
                  (vérité unique PnL)
```

**Règle invariante post-refactor :**
> Aucun module ne calcule de PnL localement. Tout PnL dérive d'un `TradeEvent` produit par `ExecutionRouter`.

---

## Étapes de refactor (ordre strict)

### ÉTAPE 1 — Définir `TradeEvent` (structure de vérité unique)

**Fichier à créer :** `src/domain/trade_event.py`

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class TradeEvent:
    trade_id: str
    symbol: str
    side: Literal["buy", "sell"]
    entry_price: float
    exit_price: float
    size: float
    fees_usd: float
    slippage_bps: float
    latency_ms: float
    pnl_usd: float               # (exit - entry) * size * side_sign - fees
    pnl_pct: float
    execution_mode: Literal["backtest", "paper", "live"]
    regime: str = ""
    score: int = 0
    strategy_id: str = ""
    trace_id: str = ""
    opened_at: float = 0.0
    closed_at: float = 0.0
    metadata: dict = field(default_factory=dict)
```

**Règle :** `pnl_usd` ne doit JAMAIS être recalculé ailleurs. Le lire depuis `TradeEvent`.

---

### ÉTAPE 2 — Créer `SimulatorAdapter`

**Fichier à créer :** `src/engine/simulator_adapter.py`

Adapte l'interface `ExecutionSimulator` (OrderIntent/SimulatedFill) à l'interface attendue par le router (Order/Position + close).

```python
import time
import uuid
from src.domain.order import Order
from src.domain.position import Position
from src.domain.trade_event import TradeEvent
from execution_simulator.models import OrderIntent, MarketSnapshot
from execution_simulator.simulator import ExecutionSimulator


class SimulatorAdapter:
    """
    Adapte ExecutionSimulator à l'interface place_order / close_position.
    Produit des TradeEvent canoniques.
    """

    def __init__(self, sim: ExecutionSimulator, execution_mode: str = "backtest"):
        self._sim = sim
        self._mode = execution_mode
        self._open_fills: dict = {}   # symbol → SimulatedFill d'entrée

    def place_order(self, order: Order, price: float) -> Position:
        intent = OrderIntent(
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            signal_price=price,
            order_type=order.metadata.get("order_type", "market"),
            direction=1 if order.side == "buy" else -1,
        )
        snapshot = MarketSnapshot(
            symbol=order.symbol,
            price=price,
            bid=price * 0.9999,
            ask=price * 1.0001,
            volume_24h=order.metadata.get("volume_24h", 1_000_000.0),
            timestamp=time.time(),
        )
        fill = self._sim.execute(intent, snapshot)
        if fill.is_rejected:
            # Fail-closed : on ne crée pas de position si le fill est rejeté
            return Position(symbol=order.symbol, size=0, entry_price=price, side="long")

        self._open_fills[order.symbol] = fill
        return Position(
            symbol=order.symbol,
            size=fill.filled_size,
            entry_price=fill.fill_price,
            side="long" if order.side == "buy" else "short",
        )

    def close_position(
        self, symbol: str, price: float, metadata: dict | None = None
    ) -> dict:
        entry_fill = self._open_fills.pop(symbol, None)
        if entry_fill is None:
            return {"symbol": symbol, "pnl": 0.0, "closed": False}

        intent = OrderIntent(
            symbol=symbol,
            side="sell" if entry_fill.side == "buy" else "buy",
            size=entry_fill.filled_size,
            signal_price=price,
            order_type="market",
            direction=-1 if entry_fill.side == "buy" else 1,
        )
        snapshot = MarketSnapshot(
            symbol=symbol,
            price=price,
            bid=price * 0.9999,
            ask=price * 1.0001,
            volume_24h=(metadata or {}).get("volume_24h", 1_000_000.0),
            timestamp=time.time(),
        )
        exit_fill = self._sim.execute(intent, snapshot)

        side_sign = 1.0 if entry_fill.side == "buy" else -1.0
        raw_pnl = (exit_fill.fill_price - entry_fill.fill_price) * entry_fill.filled_size * side_sign
        total_fees = entry_fill.fee_usd + exit_fill.fee_usd
        net_pnl = raw_pnl - total_fees

        event = TradeEvent(
            trade_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=entry_fill.side,
            entry_price=entry_fill.fill_price,
            exit_price=exit_fill.fill_price,
            size=entry_fill.filled_size,
            fees_usd=total_fees,
            slippage_bps=(entry_fill.slippage_bps + exit_fill.slippage_bps) / 2,
            latency_ms=(entry_fill.latency_ms + exit_fill.latency_ms) / 2,
            pnl_usd=net_pnl,
            pnl_pct=net_pnl / (entry_fill.fill_price * entry_fill.filled_size) * 100,
            execution_mode=self._mode,
            strategy_id=(metadata or {}).get("strategy_id", ""),
            trace_id=(metadata or {}).get("trace_id", ""),
        )

        return {
            "symbol": symbol,
            "pnl": net_pnl,
            "closed": True,
            "exit_price": exit_fill.fill_price,
            "trade_event": event,
        }
```

---

### ÉTAPE 3 — Étendre `ExecutionRouter`

**Fichier à modifier :** `src/engine/execution_router.py`

Remplacer le stub par un router multi-mode.

```python
from __future__ import annotations
from typing import Literal
from src.domain.order import Order
from src.domain.position import Position

ExecutionMode = Literal["backtest", "paper", "live"]


class ExecutionRouter:
    """
    Point d'entrée unique pour toute exécution d'ordre.
    Le mode (backtest/paper/live) détermine l'adapter utilisé.
    Aucun module ne doit appeler un adapter directement.
    """

    def __init__(self, adapter, mode: ExecutionMode = "backtest"):
        self._adapter = adapter
        self._mode = mode

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    def execute(self, order: Order, price: float) -> Position:
        return self._adapter.place_order(order, price)

    def close(self, symbol: str, price: float, metadata: dict | None = None) -> dict:
        return self._adapter.close_position(symbol, price, metadata)

    # Rétrocompat temporaire — à supprimer après migration BacktestEngine
    @property
    def sim_engine(self):
        return self._adapter
```

**Note :** La propriété `sim_engine` est conservée temporairement pour ne pas casser `BacktestEngine` avant la migration de l'étape 4. Elle sera supprimée à la fin.

---

### ÉTAPE 4 — Migrer `BacktestEngine`

**Fichier à modifier :** `src/backtest/engine.py`

Deux changements :
1. Remplacer `router.sim_engine.close_position()` par `router.close()`
2. Ajouter split train/test 70/30 et benchmark buy & hold

```python
# Ligne 39 — AVANT :
result = self.router.sim_engine.close_position(symbol, candle["close"], metadata=close_meta)

# APRÈS :
result = self.router.close(symbol, candle["close"], metadata=close_meta)
```

Ajout train/test dans la méthode `run()` :

```python
def run(self, train_ratio: float = 0.7) -> dict:
    all_candles = self.data_feed.candles   # lire avant reset
    split_idx = int(len(all_candles) * train_ratio)
    # ... exécution normale sur all_candles[split_idx:] (test set)
    # ... benchmark buy & hold : pnl = (last_close - first_close) / first_close
```

---

### ÉTAPE 5 — Migrer `VirtualPortfolio`

**Fichier à modifier :** `paper_trading/virtual_portfolio.py`

`VirtualPortfolio` a son propre modèle de fees (0.10% hardcodé). Remplacer par `SimulatorAdapter` en mode `paper`.

Changement minimal (ne pas réécrire le module, juste injecter l'adapter) :

```python
# Dans VirtualPortfolio.__init__ :
def __init__(self, mexc_reader, telegram_fn, router=None):
    self._router = router   # injection optionnelle — garde compat si None

# Dans _close_position() :
if self._router is not None:
    result = self._router.close(symbol, exit_price, metadata={...})
    net_pnl = result["pnl"]
else:
    # fallback legacy (fee fixe 0.1%)
    ...
```

---

### ÉTAPE 6 — Supprimer les doublons

Une fois les étapes 1-5 validées par les tests :

| Fichier | Action |
|---|---|
| `src/engine/virtual_exchange.py` | Marquer deprecated, supprimer à T+30j |
| `paper_trading/engine.py` | Vérifier si utilisé — si non, supprimer |
| `execution_router.sim_engine` (compat shim) | Supprimer la propriété |

---

### ÉTAPE 7 — Tests de non-régression

**Fichiers à créer :**

- `tests/test_execution_router.py` — vérifie que BACKTEST/PAPER produisent des `TradeEvent` cohérents
- `tests/test_simulator_adapter.py` — vérifie slippage/fees/latence non nuls sur fill réaliste
- `tests/test_backtest_pnl_consistency.py` — vérifie que PnL backtest = somme des `TradeEvent.pnl_usd`

**Critère de succès :**
```
BacktestEngine avec VirtualExchange → win_rate X%
BacktestEngine avec SimulatorAdapter → win_rate <= X% (jamais supérieur — slippage/fees réduisent)
```

Si le backtest avec simulateur est *meilleur* que sans, c'est un bug.

---

## Checklist de déploiement

```
[ ] closed_trades >= 100 (ALPHA_DISCOVERY_100 débloqué)
[ ] BURNIN_CALIBRATION_V3 produit le FillErrorMetric de référence
[ ] Paramètres ExecutionSimulator recalibrés sur données réelles (eta, noise_bps, taker_rate)
[ ] Étape 1 : TradeEvent défini et testé
[ ] Étape 2 : SimulatorAdapter testé (slippage/fees non nuls)
[ ] Étape 3 : ExecutionRouter étendu, tests existants verts
[ ] Étape 4 : BacktestEngine migré, plus de `router.sim_engine` direct
[ ] Étape 5 : VirtualPortfolio accepte router injecté
[ ] Étape 6 : VirtualExchange deprecated
[ ] Étape 7 : 3 nouveaux tests créés et verts
[ ] Benchmark buy & hold ajouté aux rapports backtest
[ ] Tests governance/ toujours verts (63 passés, 1 xfail)
```

---

## Ce qui NE change PAS

- `execution_simulator/` — aucune modification (c'est la vérité)
- `core/advisor_loop.py` — aucune modification (hors périmètre)
- Paramètres gelés ALPHA_DISCOVERY_100 (GATE_MIN_SCORE_OVERRIDE, PB_MIN_POSITION_USD)
- Gouvernance G0→G8-E — aucune modification

---

## Estimation de charge

| Étape | Fichiers | Durée estimée |
|---|---|---|
| 1 — TradeEvent | 1 nouveau | 30 min |
| 2 — SimulatorAdapter | 1 nouveau | 1h |
| 3 — ExecutionRouter étendu | 1 modif | 30 min |
| 4 — BacktestEngine migré | 1 modif | 1h |
| 5 — VirtualPortfolio injecté | 1 modif | 45 min |
| 6 — Suppression doublons | 2 suppressions | 30 min |
| 7 — Tests | 3 nouveaux | 1h30 |
| **Total** | | **~6h** |
