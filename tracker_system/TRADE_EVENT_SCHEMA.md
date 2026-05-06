# Canonical Trade Event Schema

Version 1.0 | Last updated: 2026-05-05

This document defines the canonical schema for trade entry and exit events logged to `logs/trades.jsonl`. All loggers (MVP, structured tracker) must produce events conforming to this schema. All readers must accept both canonical fields and legacy aliases.

---

## Entry Events

### Canonical Structure

```json
{
  "type": "entry",
  "id": "BTCUSDT_1714926000000",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "direction": "long",
  "entry_price": 100.0,
  "size": 50.0,
  "size_usd": 50.0,
  "regime": "bullish",
  "confidence": 0.8,
  "signal_type": "momentum",
  "score": 77.0,
  "atr_pct": 0.5,
  "paper": true,
  "stop_loss": 95.0,
  "take_profit": 110.0,
  "timestamp": "2026-05-05T10:00:00+00:00",
  "logged_at": "2026-05-05T10:00:00.123456+00:00"
}
```

### Mandatory Fields (all callsites must provide)

| Field | Type | Range/Enum | Example | Notes |
|-------|------|-----------|---------|-------|
| `type` | string | `"entry"` | - | Event discriminator |
| `symbol` | string | "XXUSDT" format | "BTCUSDT" | Trading pair |
| `side` | string | BUY, SELL, LONG, SHORT | "BUY" | Will be normalized internally |
| `entry_price` | float | > 0 | 100.0 | Entry price in quote currency |
| `size` | float | > 0 | 50.0 | Numeric quantity |
| `stop_loss` | float | **Required** | 95.0 | Hard SL level; zero triggers exit logic |
| `take_profit` | float | **Required** | 110.0 | Hard TP level; zero triggers exit logic |

### Optional Fields (defaults provided if missing)

| Field | Type | Default | Range | Example |
|-------|------|---------|-------|---------|
| `id` | string | Generated (symbol_timestamp_ms) | - | "BTCUSDT_1714926000000" |
| `regime` | string | "unknown" | bull/bear/range/bullish/bearish/sideways | "bullish" |
| `confidence` | float | 0.0 | 0.0–1.0 | 0.8 |
| `signal_type` | string | "unknown" | - | "momentum" |
| `score` | float | 0.0 | -100 to 100 | 77.0 |
| `atr_pct` | float | 0.0 | 0–1 | 0.5 |
| `paper` | boolean | true | - | true |

### Legacy Aliases (for backward compatibility)

When reading events, accept both canonical and legacy names:

| Canonical | Legacy Alias | Conversion |
|-----------|------------|-----------|
| `side` | `direction` (legacy: "long"/"short") | Normalize "long"→"BUY", "short"→"SELL" |
| `size` | `size_usd` | Use first available; store both in output |
| (none) | `entry_ts` | Treat as `timestamp` if `timestamp` missing |

### Generated Fields (added by logger)

- `direction`: Computed from `side` normalization ("BUY"→"long", "SELL"→"short")
- `size_usd`: Copy of `size` for legacy compatibility
- `logged_at`: ISO8601 UTC timestamp when event was written
- `timestamp`: If not provided, set to `logged_at`

---

## Exit Events

### Canonical Structure

```json
{
  "type": "exit",
  "id": "BTCUSDT_1714926000000",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "direction": "long",
  "entry_price": 100.0,
  "exit_price": 102.0,
  "size": 50.0,
  "size_usd": 50.0,
  "pnl_pct": 0.02,
  "pnl_usd": 1.0,
  "win": true,
  "mfe": 0.04,
  "mae": -0.01,
  "exit_reason": "TP",
  "duration_min": 45.0,
  "duration_minutes": 45.0,
  "regime": "bullish",
  "confidence": 0.8,
  "signal_type": "momentum",
  "price_path": [100.0, 100.5, 101.0, 101.5, 102.0],
  "attribution": "validated",
  "fee_usd": 0.02,
  "timestamp": "2026-05-05T10:45:00+00:00",
  "logged_at": "2026-05-05T10:45:00.654321+00:00"
}
```

### Mandatory Fields

| Field | Type | Computation | Example | Notes |
|-------|------|-----------|---------|-------|
| `type` | string | - | "exit" | Event discriminator |
| `id` | string | - | "BTCUSDT_1714926000000" | Must match entry ID |
| `symbol` | string | - | "BTCUSDT" | From position |
| `side` | string | - | "BUY" | From position |
| `entry_price` | float | - | 100.0 | From position |
| `exit_price` | float | - | 102.0 | User-provided |
| `size` | float | - | 50.0 | From position |
| `pnl_pct` | float | `(exit_price - entry_price) / entry_price` for LONG, `(entry_price - exit_price) / entry_price` for SHORT | 0.02 | As decimal (0–1 range) |
| `pnl_usd` | float | `size * pnl_pct` | 1.0 | Signed: negative for losses |
| `win` | boolean | `pnl_usd > 0` | true | Profit/loss indicator |
| `mfe` | float | Max Favorable Excursion; see calculation below | 0.04 | As decimal |
| `mae` | float | Max Adverse Excursion; see calculation below | -0.01 | As decimal (typically negative) |
| `exit_reason` | string | - | "TP" | "TP", "SL", "TIME_EXIT", "MANUAL", etc. |
| `duration_min` | float | Minutes from entry to exit | 45.0 | Must be ≥ 0 |
| `regime` | string | - | "bullish" | From position |

### Optional Fields

| Field | Type | Default | Example | Notes |
|-------|------|---------|---------|-------|
| `direction` | string | Computed from `side` | "long" | Legacy alias |
| `size_usd` | float | Copy of `size` | 50.0 | Legacy alias |
| `duration_minutes` | float | Copy of `duration_min` | 45.0 | Legacy alias |
| `confidence` | float | None | 0.8 | From position (recommended) |
| `signal_type` | string | "unknown" | "momentum" | From position |
| `price_path` | array[float] | [] | [100.0, 102.0] | Last 150 prices; truncated if longer |
| `attribution` | string | None | "validated" | Trade review classification (MVP-only) |
| `fee_usd` | float | None | 0.02 | Execution fee (MVP-only) |

### Generated Fields

- `direction`: Computed from `side` normalization
- `size_usd`: Copy of `size`
- `duration_minutes`: Copy of `duration_min`
- `logged_at`: ISO8601 UTC timestamp when event was written
- `timestamp`: If not provided, set to `logged_at`

---

## MFE / MAE Calculation

### MFE (Max Favorable Excursion)

Best price reached during holding period (in percentage).

**LONG position:**
```
mfe = max(price_path) - entry_price
mfe_pct = mfe / entry_price
```

**SHORT position:**
```
mfe = entry_price - min(price_path)
mfe_pct = mfe / entry_price
```

### MAE (Max Adverse Excursion)

Worst price reached during holding period (in percentage).

**LONG position:**
```
mae = min(price_path) - entry_price
mae_pct = mae / entry_price  (typically negative)
```

**SHORT position:**
```
mae = entry_price - max(price_path)
mae_pct = mae / entry_price  (typically negative)
```

---

## Backward Compatibility

### Reading Legacy MVP Events

Legacy MVP logger produces events without `stop_loss` / `take_profit` and without MFE/MAE. When reading:

- **Reader behavior**: Use `event.get("field", default_value)` to handle missing fields
- **Dashboard & Analytics**: Default missing MFE/MAE to 0.0; missing SL/TP to 0.0
- **Core Tracker**: Fail with clear error if reading legacy entry without SL/TP for position re-opening

### Writing Mixed Events

If both old and new loggers write to the same JSONL:
- All new events use canonical schema (both `side` and `direction`, both `size` and `size_usd`)
- All readers must handle both old and new formats
- No validation error for missing fields (silent defaults only)

---

## Validation Rules

### At Write Time (Logger)

```python
def validate_entry_event(event: dict) -> None:
    assert event.get("type") == "entry", "type must be 'entry'"
    assert event.get("symbol"), "symbol required"
    assert event.get("side"), "side required"
    assert event.get("entry_price", 0) > 0, "entry_price must be positive"
    assert event.get("size", 0) > 0, "size must be positive"
    assert event.get("stop_loss") is not None and event.get("stop_loss") >= 0, "stop_loss required (≥0)"
    assert event.get("take_profit") is not None and event.get("take_profit") >= 0, "take_profit required (≥0)"

def validate_exit_event(event: dict) -> None:
    assert event.get("type") == "exit", "type must be 'exit'"
    assert event.get("id"), "id required"
    assert event.get("symbol"), "symbol required"
    assert event.get("exit_price", 0) > 0, "exit_price must be positive"
    assert event.get("pnl_usd") is not None, "pnl_usd required"
    assert event.get("mfe") is not None, "mfe required"
    assert event.get("mae") is not None, "mae required"
    assert event.get("duration_min", 0) >= 0, "duration_min must be ≥ 0"
```

### At Read Time (Readers)

```python
def safe_read_entry(event: dict) -> dict:
    return {
        "symbol": event.get("symbol"),
        "side": event.get("side", event.get("direction", "BUY")).upper(),
        "entry_price": float(event.get("entry_price", 0)),
        "size": float(event.get("size", event.get("size_usd", 0))),
        "stop_loss": float(event.get("stop_loss", 0)),  # Default: 0 = disabled
        "take_profit": float(event.get("take_profit", 0)),  # Default: 0 = disabled
        # ... optional fields with defaults
    }

def safe_read_exit(event: dict) -> dict:
    return {
        "symbol": event.get("symbol"),
        "pnl_usd": float(event.get("pnl_usd", 0)),
        "mfe": float(event.get("mfe", 0)),  # Default: 0 if missing
        "mae": float(event.get("mae", 0)),  # Default: 0 if missing
        # ... other fields
    }
```

---

## Migration Notes

### From MVP Logger to Unified Logger

All MVP callsites switch to `tracker_system.core.trade_logger` via adapter wrapper:

```python
from tracker_system.core.event_writer import record_entry_from_mvp

# Old (MVP logger):
mvp.trade_logger.log_entry(
    symbol, direction, signal_type, regime,
    entry_price, size_usd, stop_loss, take_profit,
    score, confidence, atr_pct, paper
)

# New (Unified logger via adapter):
record_entry_from_mvp(
    symbol, direction, signal_type, regime,
    entry_price, size_usd, stop_loss, take_profit,
    score, confidence, atr_pct, paper
)
```

### Legacy `mvp/trade_logger.py`

**Status**: DEPRECATED (2026-05-05)

The old `mvp/trade_logger.py` is kept for archive purposes only. All new code must use `tracker_system.core.trade_logger` via adapter wrapper `event_writer.py`.

Do not add new callsites to `mvp/trade_logger.py`.

---

## Examples

### Writing Entry

```python
from tracker_system.core.trade_logger import log_entry

log_entry(
    symbol="BTCUSDT",
    side="BUY",                 # Canonical
    entry_price=100.0,
    size=50.0,                  # Canonical
    stop_loss=95.0,             # Mandatory
    take_profit=110.0,          # Mandatory
    regime="bullish",           # Optional
    confidence=0.8,             # Optional
    signal_type="momentum",     # Optional
    score=77.0,                 # Optional
)
# Output → logs/trades.jsonl (one JSON line)
```

### Reading Entry

```python
import json

with open("logs/trades.jsonl") as f:
    for line in f:
        event = json.loads(line)
        if event.get("type") != "entry":
            continue
        
        # Safe reading (handles legacy)
        symbol = event.get("symbol")
        side = event.get("side", event.get("direction", "BUY")).upper()
        entry_price = float(event.get("entry_price", 0))
        size = float(event.get("size", event.get("size_usd", 0)))
        stop_loss = float(event.get("stop_loss", 0))
        take_profit = float(event.get("take_profit", 0))
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-05 | Initial canonical schema (SL/TP mandatory, MFE/MAE in exit, backward-compatible aliases) |
