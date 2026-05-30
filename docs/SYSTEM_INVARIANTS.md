# SYSTEM INVARIANTS — Garanties non-négociables

> Date: 2026-05-29 | Source: audit Phase 4

Chaque invariant a: ID · condition · module responsable · mécanisme · niveau d'enforcement · log · test.

**Légende enforcement:**
- `HARD` — exception levée ou return `rejected`, jamais silencieux
- `SOFT` — valeur clampée ou None retourné, appelant doit vérifier
- `LOGGED` — tracé mais non bloquant (amélioration future)

---

## I-01 — Size ≤ 0 = REJECT

| Champ | Valeur |
|-------|--------|
| **Condition** | `size <= 0` ou `size > 1e9` avant tout envoi d'ordre |
| **Module** | `quant_hedge_ai/agents/execution/execution_engine.py:285` |
| **Mécanisme** | Alerte critique + auto-heal à 1.0 USD (jamais transmis tel quel) |
| **Enforcement** | **SOFT** (auto-heal, non rejeté — alert critique levée) |
| **Log** | `AlertManager.raise_alert("order_size_anomaly", "critical")` |
| **Test** | `test_invariants.py::test_i01_size_zero_auto_healed` |

---

## I-02 — Drawdown session > seuil = HALT

| Champ | Valeur |
|-------|--------|
| **Condition** | Drawdown session > `EXEC_MAX_DD` (défaut 5%) |
| **Module** | `quant_hedge_ai/agents/risk/session_guard.py:131` |
| **Mécanisme** | `SessionGuard.check_order()` lève `SessionHaltedError` |
| **Enforcement** | **HARD** |
| **Log** | `[ExecutionEngine] Order rejected by SessionGuard: ...` |
| **Test** | `test_invariants.py::test_i02_session_halt_on_drawdown` |

---

## I-03 — Pertes consécutives > seuil = HALT

| Champ | Valeur |
|-------|--------|
| **Condition** | N pertes consécutives > `EXEC_MAX_CONSEC_LOSSES` (défaut 3) |
| **Module** | `quant_hedge_ai/agents/risk/session_guard.py` |
| **Mécanisme** | `record_loss()` + `check_order()` → `SessionHaltedError` |
| **Enforcement** | **HARD** |
| **Log** | Inclus dans `SessionHaltedError.reason` |
| **Test** | `test_invariants.py::test_i03_session_halt_on_consecutive_losses` |

---

## I-04 — Ordre dupliqué dans la fenêtre = BLOCK

| Champ | Valeur |
|-------|--------|
| **Condition** | Même (symbol, action, size) dans les 30s |
| **Module** | `quant_hedge_ai/agents/execution/order_deduplicator.py` |
| **Mécanisme** | `OrderDeduplicator.is_duplicate()` → `{"mode": "rejected"}` |
| **Enforcement** | **HARD** |
| **Log** | `log_rejected("duplicate order within Xs window")` |
| **Test** | `test_invariants.py::test_i04_duplicate_order_blocked` |

---

## I-05 — Cache stale > TTL = NONE (pas de données périmées)

| Champ | Valeur |
|-------|--------|
| **Condition** | Âge cache > `max_age_seconds` |
| **Module** | `startup_cache.py:50` |
| **Mécanisme** | `load_config()` / `load_runtime_state()` retournent `None` |
| **Enforcement** | **SOFT** (appelant gère le None) |
| **Log** | `[StartupCache] Config trop ancienne (Xs > Xs), ignorée` |
| **Test** | `test_invariants.py::test_i05_cache_stale_returns_none` |

---

## I-06 — Signal timestamp toujours défini

| Champ | Valeur |
|-------|--------|
| **Condition** | Tout `SignalResult` doit avoir `timestamp > 0` |
| **Module** | `quant_hedge_ai/agents/execution/live_signal_engine.py:58` |
| **Mécanisme** | `field(default_factory=time.time)` — jamais None |
| **Enforcement** | **SOFT** (auto-généré, pas de validation explicite) |
| **Log** | `signal_age_sec` calculé à chaque cycle |
| **Test** | `test_invariants.py::test_i06_signal_timestamp_always_set` |

---

## I-07 — Gate `allowed=False` → trade bloqué

| Champ | Valeur |
|-------|--------|
| **Condition** | `GateResult.allowed == False` |
| **Module** | `quant_hedge_ai/agents/risk/global_risk_gate.py` + `advisor_loop.py:3603` |
| **Mécanisme** | `gate.allowed` vérifié avant `ExecutionEngine.create_order()` |
| **Enforcement** | **HARD** (au niveau loop) |
| **Log** | `[GlobalRiskGate] BLOCKED: ...` |
| **Test** | `test_invariants.py::test_i07_gate_blocked_result_is_not_allowed` |

---

## I-08 — ExecutiveOverride VETO terminal

| Champ | Valeur |
|-------|--------|
| **Condition** | `AgentVote(veto=True)` d'un ExecutiveOverride |
| **Module** | `advisor_loop.py:947` + `quant_hedge_ai/agents/intelligence/decision_arbitrator.py` |
| **Mécanisme** | Un veto `AgentVote` bloque indépendamment du score agrégé |
| **Enforcement** | **HARD** (arbitrator) |
| **Log** | `[ExecutiveOverride] ... taille x0%` |
| **Test** | `test_invariants.py::test_i08_veto_vote_blocks_decision` |

---

## I-09 — OrderSizer toujours dans [min, max]

| Champ | Valeur |
|-------|--------|
| **Condition** | `min_size_usd ≤ output ≤ max_size_usd` |
| **Module** | `quant_hedge_ai/agents/risk/order_sizer.py:150-158` |
| **Mécanisme** | Clamping explicite après Kelly/fraction |
| **Enforcement** | **SOFT** (clamping, pas d'exception) |
| **Log** | `os_size_usd` dans `packet.features` |
| **Test** | `test_invariants.py::test_i09_order_sizer_output_clamped` |

---

## I-10 — DrawdownGuard factor ≥ 0.1 (jamais zéro)

| Champ | Valeur |
|-------|--------|
| **Condition** | `adjust_position_size()` ne retourne jamais 0 |
| **Module** | `quant_hedge_ai/agents/risk/drawdown_guard.py:8` |
| **Mécanisme** | `max(0.1, 1.0 - drawdown * 2.5)` — plancher à 10% |
| **Enforcement** | **SOFT** (clamping) |
| **Log** | Via OrderSizer qui appelle DrawdownGuard |
| **Test** | `test_invariants.py::test_i10_drawdown_guard_floor` |

---

## I-11 — trace_id présent à chaque cycle

| Champ | Valeur |
|-------|--------|
| **Condition** | Chaque cycle `advisor_loop` a un `trace_id` unique non-vide |
| **Module** | `advisor_loop.py:420` + `observability/json_logger.py` |
| **Mécanisme** | `new_trace_id()` appelé en tête de cycle, propagé dans tous les logs |
| **Enforcement** | **LOGGED** (pas de rejet si absent) |
| **Log** | `[trace] symbol=... trace_id=...` |
| **Test** | `test_invariants.py::test_i11_trace_id_generated_unique` |

---

## I-12 — Ordre oversized = REJECT

| Champ | Valeur |
|-------|--------|
| **Condition** | `size_usd > EXEC_MAX_ORDER_USD` (défaut 10 000 USD) |
| **Module** | `quant_hedge_ai/agents/risk/session_guard.py:141` |
| **Mécanisme** | `check_order()` lève `OrderTooLargeError` → `{"mode": "rejected"}` |
| **Enforcement** | **HARD** |
| **Log** | `[ExecutionEngine] Order rejected by SessionGuard: OrderTooLargeError` |
| **Test** | `test_invariants.py::test_i12_oversized_order_rejected` |

---

## Tableau de synthèse

| ID | Invariant | Enforcement | Module |
|----|-----------|-------------|--------|
| I-01 | Size ≤ 0 = alert + auto-heal (jamais 0 transmis) | SOFT | ExecutionEngine |
| I-02 | Drawdown session = HALT | HARD | SessionGuard |
| I-03 | Pertes consécutives = HALT | HARD | SessionGuard |
| I-04 | Dupliqué 30s = BLOCK | HARD | OrderDeduplicator |
| I-05 | Cache stale = NONE | SOFT | StartupCache |
| I-06 | Signal timestamp ≠ None | SOFT | LiveSignalEngine |
| I-07 | Gate blocked = trade impossible | HARD | GlobalRiskGate/loop |
| I-08 | VETO = terminal | HARD | DecisionArbitrator |
| I-09 | Size dans [min,max] | SOFT | OrderSizer |
| I-10 | DrawdownGuard factor ≥ 0.1 | SOFT | DrawdownGuard |
| I-11 | trace_id présent par cycle | LOGGED | advisor_loop |
| I-12 | Order > MAX = REJECT | HARD | SessionGuard |

**Résumé:** 6 HARD · 5 SOFT · 1 LOGGED
