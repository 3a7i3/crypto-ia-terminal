# Tracker Schema Mismatch — Audit Complet

**Date:** 2026-05-05  
**Status:** CRITICAL DUPLICATION + SILENT FIELD DRIFT RISK

---

## Executive Summary

Two parallel `trade_logger.py` modules coexist with **incompatible schemas** and no canonical event format. This creates:
- Silent field drift in JSONL (same file, mismatched rows)
- Risk of data loss if readers only implement one schema
- No way to validate new implementations against the canonical format

---

## The Two Loggers

### 1. Legacy: `mvp/trade_logger.py`
- **Origin:** MVP trade orchestration
- **Caller:** `mvp/mvp_orchestrator.py` line 228
- **File:** `logs/trades.jsonl`
- **Signature:** Strict positional params

```python
def log_entry(
    symbol: str,
    direction: str,              # ← "long"/"short"
    signal_type: str,
    regime: str,
    entry_price: float,
    size_usd: float,             # ← USD value
    stop_loss: float,
    take_profit: float,
    score: float,
    confidence: float,
    atr_pct: float,
    paper: bool,
) -> None
```

**Produces:**
```json
{
  "type": "entry",
  "symbol": "BTCUSDT",
  "direction": "long",
  "signal_type": "momentum",
  "regime": "bullish",
  "entry_price": 100.0,
  "size_usd": 50.0,
  "stop_loss": 95.0,
  "take_profit": 110.0,
  "score": 77.0,
  "confidence": 0.8,
  "atr_pct": 0.5,
  "paper": true,
  "timestamp": "ISO8601"
}
```

### 2. Structured: `tracker_system/core/trade_logger.py`
- **Origin:** tracker_system refactor
- **Caller:** `tracker_system/core/trade_tracker.py::open_position()` (indirectly via tests)
- **File:** `logs/trades.jsonl` (same!)
- **Signature:** Flexible with `**extra`

```python
def log_entry(
    symbol: str,
    side: str,                   # ← "BUY"/"SELL"
    entry_price: float,
    size: float,                 # ← numeric quantity
    regime: str | None = None,
    confidence: float | None = None,
    log_file: Path = TRADES_LOG_FILE,
    **extra: Any,               # ← Accepts arbitrary fields
) -> dict[str, Any]
```

**Produces:**
```json
{
  "type": "entry",
  "symbol": "BTCUSDT",
  "side": "BUY",                 # ← DIFFERENT from legacy
  "direction": "long",           # ← Added as alias
  "entry_price": 100.0,
  "size": 50.0,                  # ← DIFFERENT from legacy
  "size_usd": 50.0,              # ← Added as alias
  "regime": "bullish",
  "confidence": 0.8,
  "signal_type": "momentum",     # From **extra
  "score": 0.0,                  # From **extra (may be 0!)
  "atr_pct": 0.5,                # From **extra
  "paper": true,                 # From **extra
  "logged_at": "ISO8601",
  "timestamp": "ISO8601"
}
```

---

## Field Mismatch Matrix

### Entry Events

| Field | Legacy (mvp) | Structured (tracker_system) | Status |
|-------|--------------|------------------------------|--------|
| `symbol` | ✅ | ✅ | Match |
| `direction` | Required (`long`/`short`) | Added as alias from `side` | ⚠️ Alias |
| `side` | ❌ Not produced | ✅ Primary (`BUY`/`SELL`) | ⚠️ New |
| `entry_price` | ✅ | ✅ | Match |
| `size` | ❌ | ✅ Primary | ⚠️ New |
| `size_usd` | ✅ Required | ✅ Added as alias | ⚠️ Alias |
| `stop_loss` | ✅ Required | ❌ Via `**extra` only | 🔴 Risk |
| `take_profit` | ✅ Required | ❌ Via `**extra` only | 🔴 Risk |
| `signal_type` | ✅ Required | Via `**extra` (should match) | ⚠️ Optional |
| `regime` | ✅ Required | ✅ | Match |
| `score` | ✅ Required | Via `**extra` (defaults to 0.0!) | 🔴 Silent default |
| `confidence` | ✅ Required | ✅ | Match |
| `atr_pct` | ✅ Required | Via `**extra` (defaults to 0.0!) | 🔴 Silent default |
| `paper` | ✅ Required | Via `**extra` (defaults to True) | ⚠️ May differ |

### Exit Events

| Field | Legacy (mvp) | Structured (tracker_system) | Status |
|-------|--------------|------------------------------|--------|
| `symbol` | ✅ | ✅ | Match |
| `direction` | ✅ Required | ✅ Added as alias | ⚠️ Alias |
| `entry_price` | ✅ | ✅ | Match |
| `exit_price` | ✅ | ✅ | Match |
| `size_usd` | ✅ | ✅ Added as alias | Match |
| `pnl_usd` | ✅ | ✅ | Match |
| `pnl_pct` | ✅ | ✅ | Match |
| `win` | ❌ Computed | ✅ Computed | Differs slightly (logic?) |
| `exit_reason` | ✅ | ✅ | Match |
| `duration_minutes` | ✅ | ✅ (also `duration_min`) | ⚠️ Alias |
| `mfe` / `mae` | ❌ Not in mvp | ✅ In structured | 🔴 Missing in legacy |
| `attribution` | ✅ In mvp | ❌ In structured | 🔴 Missing in structured |
| `fee_usd` | ✅ In mvp | ❌ In structured | 🔴 Missing in structured |

---

## Critical Risks

### 1. **Silent Field Defaults** (MVP → Structured)
If legacy `mvp/trade_logger.py` writes entry with `score=77.0` and `atr_pct=0.5`, but a tracker_system reader relies on `**extra`:
- ✅ Fields ARE present → reader will get correct values
- BUT: No validation that they arrived

### 2. **Missing Required Fields** (Structured → Legacy)
If `tracker_system/core/trade_logger.py` is called **without** passing `stop_loss` and `take_profit` via `**extra`:
```python
log_entry("BTCUSDT", "BUY", 100.0, 50.0, regime="bullish", confidence=0.8)
# Missing: stop_loss, take_profit
```

Then `legacy_trade_tracker.sync_from_log()` reads:
```python
stop_loss=ev["stop_loss"]        # ❌ KeyError or None!
take_profit=ev["take_profit"]    # ❌ KeyError or None!
```

→ **Position will be opened with SL=0.0, TP=0.0** (silent failure in risk management!)

### 3. **Field Name Confusion**
- `side` (BUY/SELL) vs `direction` (long/short) not consistently named
- `size` vs `size_usd` — numeric size vs USD value not clear in code
- Readers must implement fallback chains: `event.get("side") or event.get("direction")`

### 4. **New Exit Fields Missing in MVP Path**
If MVP logs exit and structured reader expects `mfe` / `mae`:
```python
exits = structured_tracker.load_exits()  # MVP-written exit lacks mfe/mae
mfe = exit.get("mfe", 0.0)              # Silent default to 0.0
```

→ **Dashboard metrics become invisible, not wrong**

---

## Current Test Coverage

✅ **test_tracker_schema_compat.py** tests:
- Structured logger `log_entry()` → Legacy reader `sync_from_log()` ✅
- Structured logger `log_exit()` → Legacy reader dashboard `load_exits()` ✅

❌ **NOT tested:**
- Legacy logger `mvp/trade_logger.py` → Any reader
- Mixed entries in same JSONL (one from mvp, one from structured)
- Missing `**extra` fields (e.g., calling `log_entry()` without `stop_loss`/`take_profit`)
- Exit fields `mfe`/`mae` consumed by legacy dashboard code

---

## Where Each Logger Is Used

### `mvp/trade_logger.py` callsites:
- `mvp/mvp_orchestrator.py::_handle_signal_entry()` line 228

### `tracker_system/core/trade_logger.py` callsites:
- `tracker_system/core/trade_tracker.py::open_position()` line 83
- `tracker_system/core/trade_tracker.py::close_position()` line 109
- Test `test_tracker_schema_compat.py` (only test usage!)

### Readers (expect merged schema):
- `tracker_system/trade_tracker.py::sync_from_log()` — legacy reader, very strict
- `tracker_system/tracker.py::load_exits()` — legacy dashboard, uses `.get()`
- `tracker_system/core/trade_tracker.py::sync_entries_from_log()` — structured sync, uses fallbacks

---

## Concrete Example of Silent Failure

**Scenario:** Operator runs `mvp_orchestrator.py`, then queries dashboard

```python
# mvp_orchestrator.py writes (via mvp/trade_logger.py):
{
  "type": "entry",
  "symbol": "BTCUSDT",
  "direction": "long",
  "size_usd": 100.0,
  "stop_loss": 95.0,
  "take_profit": 110.0,
  ...
}

# Later, structured tracker opens position (via tracker_system/core/trade_logger.py):
log_entry("BTCUSDT", "BUY", 105.0, 100.0, regime="bullish", confidence=0.9)
# ❌ Structured logger doesn't know about stop_loss / take_profit!

# Writes:
{
  "type": "entry",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "size": 100.0,
  "direction": "long",          # Generated from side
  "size_usd": 100.0,            # Generated from size
  "regime": "bullish",
  ...
}

# Later, legacy reader tries to sync:
structured_event = {...}       # From tracker_system logger
stop_loss=structured_event["stop_loss"]  # ❌ KeyError!
# OR falls back to structured reader which doesn't require it

# Result: Positions opened with SL=0.0, TP=0.0 
# Risk manager sees positions with no stops!
```

---

## Summary Table

| Aspect | Legacy (mvp) | Structured | Compatibility |
|--------|--------------|-----------|--|
| **Logger File** | `mvp/trade_logger.py` | `tracker_system/core/trade_logger.py` | ❌ Duplicate |
| **Field Names** | `direction`, `size_usd` | `side`, `size` + aliases | ⚠️ Aliased but confusing |
| **Strictness** | Strict params | Flexible `**extra` | ⚠️ Can miss required fields |
| **Test Coverage** | 1 caller (mvp_orch), no tests | 1 test (test_schema_compat) | ❌ Gaps |
| **Stop/TP Handling** | Required in signature | Optional in `**extra` | 🔴 RISK |
| **Exit Fields** | Includes `fee_usd`, `attribution` | Includes `mfe`, `mae` | ❌ Divergent |
| **Canonical Format** | None explicitly | None explicitly | ❌ CRITICAL |

---

## Recommended Next Steps

1. **Define one canonical schema** for `entry` and `exit` events in JSONL
2. **Choose an authoritative writer:** Either consolidate into one logger or define which logger is primary
3. **Add compatibility layer:** Either wrappers or readers with robust fallback chains
4. **Expand test coverage:** Round-trip tests for both entry and exit, missing fields, mixed schemas
5. **Document field responsibilities:** Which caller must provide `stop_loss`/`take_profit`? When are defaults OK?
