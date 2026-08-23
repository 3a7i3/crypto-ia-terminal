# Liquidity Engine (Binance + MEXC)

Composant **passif** de collecte et d’analyse microstructure en temps réel.

## Objectif

- Collecter trades + book publics Binance/MEXC via WebSocket.
- Normaliser dans un schéma commun (`MarketEvent`).
- Détecter `NORMAL` / `LARGE` / `WHALE` via `TradeFilter` configurable.
- Agréger en fenêtres `1s/5s/10s/30s/1m` avec métriques de liquidité.
- Construire des `LiquidityPocket` (clusters prix/temps).
- Publier un flux indépendant de Panel (`DataPublisher`).

## Architecture

`BinanceWebSocketClient` / `MexcWebSocketClient` → `EventBus` (queue bornée) → `TradeFilter` → `LiquidityAggregator` → `DataPublisher`

## Lancement

```bash
python -m market_data.liquidity_engine.main
```

Variables principales:

- `LIQ_BINANCE_ENABLED`, `LIQ_MEXC_ENABLED`
- `LIQ_SYMBOLS=BTCUSDT,ETHUSDT`
- `LIQ_LARGE_TRADE_THRESHOLD_USD`, `LIQ_WHALE_TRADE_THRESHOLD_USD`
- `LIQ_AGG_WINDOWS=1,5,10,30,60`
- `LIQ_PRICE_BUCKET_SIZE`, `LIQ_TIME_WINDOW_S`
- `LIQ_QUEUE_MAX_SIZE`, `LIQ_WS_TIMEOUT_S`

## Exemple d’événement produit

```json
{
  "type": "BIG_TRADE_EVENT",
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "size_level": "WHALE",
  "notional_usd": 245000.0,
  "price": 70000.0,
  "quantity": 3.5,
  "side": "BUY",
  "timestamp_exchange": "2026-08-23T06:00:00+00:00",
  "timestamp_received": "2026-08-23T06:00:00.120000+00:00",
  "timestamp_processed": "2026-08-23T06:00:00.121000+00:00",
  "latency_ms": 120.0
}
```

## Métriques exposées

- `messages_received`
- `messages_processed`
- `messages_rejected`
- `big_trades_detected`
- `reconnect_count`
- `websocket_latency_avg`
- `processing_latency_avg`
- `queue_depth`
- `dropped_events`
- `dropped_noncritical_events`
- `dropped_critical_events`
