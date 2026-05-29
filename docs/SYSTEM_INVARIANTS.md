# SYSTEM INVARIANTS — crypto_ai_terminal

**Règle :** 1 invariant sécurisé > 10 nouvelles features.

## Invariants absolus

| # | Invariant | Module responsable | Garde-fou | Log associé | Test |
|---|-----------|-------------------|-----------|-------------|------|
| 1 | Pas de double position ouverte | ExecutionEngine | Vérifier doublon avant place_order | `DOUBLE_POSITION_BLOCKED` | `test_invariant_no_duplicate_position` |
| 2 | Position sans stop = REJECT | ExecutionEngine | `assert stop_loss is not None` | `POSITION_WITHOUT_STOP_REJECTED` | `test_invariant_stop_required` |
| 3 | Execution sans approval = REJECT | GlobalRiskGate | Vérifier approved_by dans DecisionPacket | `EXECUTION_WITHOUT_APPROVAL` | `test_invariant_approval_required` |
| 4 | Drawdown > limite = FREEZE | drawdown_guard | Kill switch automatique | `DRAWDOWN_LIMIT_EXCEEDED` | `test_invariant_drawdown_limit` |
| 5 | Signal sans timestamp = DROP | LiveSignalEngine | `assert timestamp is not None` | `SIGNAL_WITHOUT_TIMESTAMP` | `test_invariant_signal_timestamp` |
| 6 | Ordre expiré jamais exécuté | ExecutionEngine | Vérifier TTL avant envoi | `EXPIRED_ORDER_REJECTED` | `test_invariant_expired_order` |
| 7 | Position size <= 0 = REJECT | OrderSizer | `assert size > 0` | `INVALID_SIZE_REJECTED` | `test_invariant_positive_size` |
| 8 | Packet sans trace_id = REJECT | advisor_loop | Généré à CREATED | `PACKET_WITHOUT_TRACE_ID` | `test_invariant_trace_id` |
| 9 | Cache stale > TTL = REFRESH | Module concerné | Vérifier timestamp | `STALE_CACHE_REFRESHED` | `test_invariant_cache_ttl` |
| 10 | Ordre après HALTED = IMPOSSIBLE | RuntimeStateMachine | Transition interdite | `HALTED_EXECUTION_BLOCKED` | `test_invariant_halted_state` |
| 11 | Ordre sans correspondance exchange = ALERT | PositionManager | Reconciliation post-execution | `POSITION_MISMATCH_ALERT` | `test_invariant_exchange_reconciliation` |
| 12 | Décision sans FINAL_AUTHORITY = REJECT | DecisionPipeline | Vérifier signature | `DECISION_WITHOUT_AUTHORITY` | `test_invariant_decision_authority` |

## Tests associés

Chaque invariant a son test unitaire dans `tests/test_invariants.py`.
