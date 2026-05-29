# Kill Switch Matrix

## Triggers et actions

| Trigger | Action | Niveau | Module responsable |
|---------|--------|--------|-------------------|
| Drawdown > 5% | Freeze trading | HALTED | drawdown_guard |
| Exchange stale > 30s | Cancel orders | SAFE_MODE | exchange_monitor |
| Position mismatch | Halt execution | HALTED | position_manager |
| Duplicate order detected | Lock symbol | DEGRADED | order_deduplicator |
| Missing stop loss | Reject trade | READY | execution_engine |
| Latence > 5s | Reduce leverage 50% | DEGRADED | performance_watchdog |
| Risk engine timeout | SAFE_MODE global | SAFE_MODE | circuit_breaker |

## State Machine Runtime

```
BOOTING → WARMING
WARMING → READY
READY   → DEGRADED  (panne partielle)
READY   → SAFE_MODE (drawdown > threshold)
READY   → HALTED    (kill switch)
DEGRADED → RECOVERING
RECOVERING → READY
HALTED → RECOVERING (intervention humaine UNIQUEMENT)
```

Interdiction absolue : HALTED → EXECUTION
