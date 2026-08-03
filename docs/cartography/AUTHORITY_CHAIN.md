# AUTHORITY_CHAIN.md — Qui possède l'autorité d'ouvrir une position ?
> **Document généré automatiquement.** Ne pas éditer à la main.
> Source : `artifacts/cartography.json` — régénérer via
> `python tools/runtime_cartographer.py && python tools/cartography_report.py`
> Généré le 2026-08-01 — commit `348e83d`

> **Portée de la mesure.** Graphe d'import statique (AST), imports paresseux
> inclus. `ACTIVE` signifie **atteignable par import** depuis le point d'entrée
> runtime, **pas** « exécuté ». Prouver l'exécution exige une trace runtime
> (`sys.settrace`/coverage sur le VPS) — **NON MESURÉ** en J1-J2.

## Réponse mesurée

> **Aucune entité unique ne possède cette autorité.**
> La décision est **calculée en un point** puis **révoquée en quatre autres**,
> tous situés dans le même fichier `core/advisor_loop.py`.

Cette réponse ne tient pas en une phrase affirmative parce que l'autorité n'est
pas détenue : elle est **distribuée sur plusieurs sites d'écriture successifs**.

## 1. Points d'écriture de `trade_allowed`

- Total mesuré dans le dépôt (hors tests et hors instrument) : **18**
- Dont situés dans du code atteignable par le runtime : **9**

| # | Fichier:ligne | Statut module | Code | Rôle |
|---|---|---|---|---|
| 1 | `core/advisor_loop.py:1983` | ENTRYPOINT | `trade_allowed = (` | CALCUL initial |
| 2 | `core/advisor_loop.py:5626` | ENTRYPOINT | `r["trade_allowed"] = False` | RÉVOCATION |
| 3 | `core/advisor_loop.py:5658` | ENTRYPOINT | `r["trade_allowed"] = False` | RÉVOCATION |
| 4 | `core/advisor_loop.py:5734` | ENTRYPOINT | `r["trade_allowed"] = False` | RÉVOCATION |
| 5 | `core/advisor_loop.py:5808` | ENTRYPOINT | `r["trade_allowed"] = False` | RÉVOCATION |
| 6 | `governance/auditor.py:196` | ACTIVE | `trade_allowed = bool(result.get("trade_allowed", False))` | lecture/relecture hors moteur |
| 7 | `governance/auditor.py:323` | ACTIVE | `trade_allowed = bool(result.get("trade_allowed", False))` | lecture/relecture hors moteur |
| 8 | `observability/decision_observation.py:448` | ACTIVE | `trade_allowed=bool(result.get("trade_allowed", False)),` | lecture/relecture hors moteur |
| 9 | `quant_hedge_ai/agents/intelligence/black_box.py:199` | ACTIVE | `trade_allowed = r.get("trade_allowed", False)` | lecture/relecture hors moteur |
| 10 | `tools/dataset_certifier.py:531` | TEST_ONLY | `trade_allowed = rec.get("trade_allowed")` | lecture/relecture hors moteur |
| 11 | `tools/instrumentation_validator.py:363` | TEST_ONLY | `trade_allowed = i % 3 != 0` | lecture/relecture hors moteur |
| 12 | `tools/instrumentation_validator.py:447` | TEST_ONLY | `trade_allowed = i % 2 == 0` | lecture/relecture hors moteur |
| 13 | `tools/instrumentation_validator.py:528` | TEST_ONLY | `trade_allowed = i % 2 == 0` | lecture/relecture hors moteur |
| 14 | `tools/instrumentation_validator.py:765` | TEST_ONLY | `trade_allowed = i % 3 != 0` | lecture/relecture hors moteur |
| 15 | `tools/live_observer_validator.py:738` | TEST_ONLY | `trade_allowed=(i % 3 != 0),` | lecture/relecture hors moteur |
| 16 | `tools/live_observer_validator.py:804` | TEST_ONLY | `trade_allowed=approved, blocker=blocker, packet_id=f"ivlive0` | lecture/relecture hors moteur |
| 17 | `visualization/decision_trace_service.py:324` | TEST_ONLY | `trade_allowed=entry.get("trade_allowed", False),` | lecture/relecture hors moteur |
| 18 | `visualization/decision_trace_service.py:417` | TEST_ONLY | `trade_allowed=entry.get("trade_allowed", False),` | lecture/relecture hors moteur |

## 2. Machines d'état

**3 classes mesurées.**

| Classe | Fichier:ligne | Statut |
|---|---|---|
| `class WarmupStateMachine:` | `cold_start/warmup_state_machine.py:113` | **TEST_ONLY** |
| `class RuntimeStateMachine:` | `quant_hedge_ai/runtime/runtime_state_machine.py:53` | **ACTIVE** |
| `class SystemStateMachine:` | `system/state_machine.py:69` | **ACTIVE** |

## 3. Kill switches

**6 classes mesurées.**

| Classe | Fichier:ligne | Statut |
|---|---|---|
| `class KillSwitch:` | `src/risk/kill_switch.py:1` | **TEST_ONLY** |
| `class TelegramKillSwitch:` | `supervision/kill_switch.py:42` | **ORPHAN** |
| `class KillSwitchHardened:` | `supervision/killswitch_hardened.py:87` | **ACTIVE** |
| `class KillSwitchState:` | `supervision/telegram_kill_switch.py:39` | **ORPHAN** |
| `class TelegramKillSwitch:` | `supervision/telegram_kill_switch.py:52` | **ORPHAN** |
| `class AlphaKillSwitch:` | `system/alpha_kill_switch.py:49` | **TEST_ONLY** |

## 4. Gates

**18 classes mesurées.**

| Classe | Fichier:ligne | Statut |
|---|---|---|
| `class PhaseGate:` | `capital_deployment/phase_gate.py:47` | **TEST_ONLY** |
| `class GateCheck:` | `certification/final_gate.py:39` | **TEST_ONLY** |
| `class FinalGateResult:` | `certification/final_gate.py:46` | **TEST_ONLY** |
| `class FinalGate:` | `certification/final_gate.py:89` | **TEST_ONLY** |
| `class GlobalRiskGateResult:` | `core/contracts.py:233` | **TEST_ONLY** |
| `class ConfidenceGateResult:` | `core/contracts.py:252` | **TEST_ONLY** |
| `class GateResult:` | `governance/confidence_gate.py:74` | **ORPHAN** |
| `class ConfidenceGate:` | `governance/confidence_gate.py:83` | **ORPHAN** |
| `class _FakeGate:` | `quant_hedge_ai/agents/execution/shadow_engine.py:243` | **ACTIVE** |
| `class GateResult:` | `quant_hedge_ai/agents/risk/global_risk_gate.py:158` | **ACTIVE** |
| `class GlobalRiskGate:` | `quant_hedge_ai/agents/risk/global_risk_gate.py:183` | **ACTIVE** |
| `class GlobalRiskGate:` | `risk/global_risk_gate.py:63` | **ORPHAN** |
| `class GateFunnel:` | `scripts/burnin_calibration_v3.py:77` | **TEST_ONLY** |
| `class GateResult:` | `scripts/prelive_gate.py:112` | **TEST_ONLY** |
| `class LiveGate:` | `src/risk/live_gate.py:4` | **TEST_ONLY** |
| `class RegimeGate:` | `src/risk/regime_gate.py:11` | **TEST_ONLY** |
| `class BootGateReport:` | `system/boot_gate.py:35` | **TEST_ONLY** |
| `class BootGate:` | `system/boot_gate.py:76` | **TEST_ONLY** |

## 5. SAFE_MODE

**18 fichiers de production mentionnent `SAFE_MODE`, dont 8 atteignables par le runtime.**

| Fichier | Statut |
|---|---|
| `capital_deployment/command_center_bot.py` | **ACTIVE** |
| `core/advisor_loop.py` | **ENTRYPOINT** |
| `core/formal_proof.py` | **ORPHAN** |
| `core/initialization_contract.py` | **TEST_ONLY** |
| `core/invariants.py` | **ORPHAN** |
| `governance/auditor.py` | **ACTIVE** |
| `governance/authority_state.py` | **ORPHAN** |
| `governance/status_dashboard.py` | **ORPHAN** |
| `governance/trading_authority.py` | **ORPHAN** |
| `quant_hedge_ai/agents/intelligence/black_box.py` | **ACTIVE** |
| `quant_hedge_ai/agents/intelligence/self_awareness_engine.py` | **ACTIVE** |
| `quant_hedge_ai/runtime/chaos_orchestrator.py` | **TEST_ONLY** |
| `quant_hedge_ai/runtime/runtime_state_machine.py` | **ACTIVE** |
| `supervision/kill_switch.py` | **ORPHAN** |
| `supervision/killswitch_hardened.py` | **ACTIVE** |
| `supervision/telegram_kill_switch.py` | **ORPHAN** |
| `system/invariant_checker.py` | **TEST_ONLY** |
| `system/state_machine.py` | **ACTIVE** |

## 6. DecisionPacket

**1 définition(s) mesurée(s).**

- `core/decision_packet.py:381` — statut **ACTIVE**
