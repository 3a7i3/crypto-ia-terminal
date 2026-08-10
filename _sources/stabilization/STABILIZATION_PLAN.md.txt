# STABILIZATION PLAN — crypto_ai_terminal
> Date: 2026-05-28 | Status: IN PROGRESS | Current: PHASE 0

## Objectif
Transformer un prototype IA expérimental en infrastructure quant pré-production déterministe.

```
stabilité → déterminisme → observabilité → résilience → sophistication
```

## Règle absolue
- Chaque phase se termine par des **tests de validation** avant passage à la suivante
- Chaque phase = **nouvelle session** (contexte propre, pas d'accumulation)
- Aucun commit > 300 lignes sans preuve runtime
- Pas de suppression sans grep d'import vérifié

---

## PHASE 0 — FORENSIC FREEZE ✅ COMPLETE
**Objectif :** Cartographier les imports réels, dépendances, entrypoints runtime **avant** toute suppression.

**Livrables :**
- [x] `docs/stabilization/RUNTIME_DEPENDENCY_MAP.md` — carte complète imports + risques réels
- [x] `tests/phase0/test_phase0_validation.py` — 59 tests validation

**Résultats clés :**
- 3 entrypoints concurrents identifiés (advisor_loop / main_v91 / main_system)
- 4 risques immédiats documentés (R1→R4)
- 5 modules dupliqués confirmés par AST
- `mvp/` confirmé non importé par le runtime principal

**Validation :** `pytest tests/phase0/ -v` → **59/59 PASSED**

---

## PHASE 0.5 — RUNTIME FORENSICS ✅ COMPLETE
**Objectif :** Prouver ce qui tourne VRAIMENT (vs ce qui existe statiquement).

**Livrables :**
- [x] `tools/runtime_tracer.py` — script import dry-run
- [x] `docs/stabilization/RUNTIME_ACTIVE_MAP.md` — carte runtime réelle
- [x] `tests/phase0/test_phase05_validation.py` — 60 tests (dont R1→R4)

**Résultats :**
- Production : **45/45 importables (100%)**
- Optionnel : **8/8 importables (100%)**
- Concordance statique/runtime : **100%**

**Risques requalifiés :**
| Risque | Initial | Réalité vérifiée | Action |
|--------|---------|-----------------|--------|
| R1 `_legacy` importable | HAUT | TRAITE — `raise ImportError` ajouté | FAIT |
| R2 `execution_v2` fork | HAUT | FAIBLE — non câblé, code utile | Décision Phase 1 |
| R3 `DecisionArbitrator` conflit | MOYEN | REQUALIFIE — optionnel (Any=None) | Pas d'action |
| R4 `market.regime_detector` | MOYEN | REQUALIFIE — uniquement dans main_system.py obsolète | Supprimer Phase 1 |

**Validation :** `pytest tests/phase0/ -v` → **126/126 PASSED**

---

## PHASE 1 — GEL ARCHITECTURAL
**Objectif :** Supprimer forks, legacy, débris, dossiers v2.

**Branche :** `stabilization/freeze_2026`

**Règle :** Aucun commit > 300 lignes modifiées. Aucune suppression sans `grep -r "import <module>"` vert.

**Cibles confirmées Phase 0 :**

| Cible | Action | Risque |
|-------|--------|--------|
| `S2/`, `S3/` | SUPPRIMER | Faible — non importés |
| `crypto_quant_v16/` | SUPPRIMER | Faible — non importé |
| `mvp/` | SUPPRIMER | ZERO — confirmé non importé |
| `quant_hedge_ai/main_system.py` | SUPPRIMER | Faible |
| `quant_hedge_ai/main_v91.py` | SUPPRIMER | Moyen — vérifier usage VPS |
| `main.py` (root) | SUPPRIMER | Faible — evolution_core + visualization uniquement |
| `quant_hedge_ai/_legacy/` | ARCHIVER | Faible — `__init__` sans exports |
| `execution_v2/` | DÉCIDER | Moyen — fork actif non utilisé |
| Scripts `.bat` orphelins (>20) | SUPPRIMER | Faible |
| Scripts génération/export (10) | SUPPRIMER | Faible |

**Validation :** `pytest tests/` → pas de régression

---

## PHASE 2 — CARTOGRAPHIE DE VÉRITÉ
**Objectif :** `SYSTEM_TRUTH_MAP.md` + chemin SIGNAL→EXECUTION unique + STATE OWNERSHIP.

**Livrables :**
- `docs/stabilization/SYSTEM_TRUTH_MAP.md`
- `docs/stabilization/STATE_OWNERSHIP_MAP.md`
- Path unique documenté et testé

**State Ownership requis :**
| Domaine | Read | Write (unique) |
|---------|------|---------------|
| Positions | tous les modules | `ExecutionEngine` uniquement |
| Drawdown | tous les modules | `RiskEngine` uniquement |
| Runtime state | observateurs | `advisor_loop` uniquement |
| Régime marché | tous les modules | `RegimeDetector` unique (résoudre R4) |

**Validation :** Chaque module du path a un test d'interface contractuel

---

## PHASE 3 — REFACTOR PAR MÉTIER
**Objectif :** Architecture orientée domaine, surplus cognitif supprimé, dashboards fusionnés.

**Domaines :**
| Domaine | Modules | Write owner |
|---------|---------|-------------|
| Signal | market_scanner, feature_engineer, regime_detector | SignalEngine |
| Decision | conviction, risk_gate, portfolio_brain | DecisionLayer |
| Execution | order_sizer, execution_engine, position_manager | ExecutionEngine |
| Monitoring | observability, supervision, cold_start | MonitoringLayer |

**Architecture Contracts requis :**
```python
class SignalPacket(BaseModel):
    trace_id: str
    symbol: str
    side: str
    confidence: float
    timestamp: datetime
```
Plus aucun dict sauvage. Pydantic/dataclasses obligatoires sur toutes les interfaces.

**Validation :** Aucun dict sauvage — tous les exchanges via Pydantic/dataclass

---

## PHASE 4 — INVARIANTS SYSTÈME
**Objectif :** `SYSTEM_INVARIANTS.md` + assertions runtime + garde-fous.

**Livrables :**
- `docs/stabilization/SYSTEM_INVARIANTS.md`
- Assertions dans chaque module critique
- Tests associés

**Assertions requises (exemples) :**
```python
assert position.size >= 0
assert packet.trace_id is not None
assert 0.0 <= confidence <= 1.0
assert regime in ("momentum", "range", "short", "scalp", "neutral")
```

Les systèmes quant meurent sur des corruptions silencieuses, pas des crashes francs.
Les assertions stoppent la propagation à la source.

**Validation :** `pytest tests/invariants/` → 100% pass

---

## PHASE 5 — CHAOS TESTING
**Objectif :** `tests/chaos/` — scénarios de panne obligatoires.

**Scénarios network/exchange :**
- Exchange offline
- WebSocket freeze / reconnect
- Rate limit hit
- Redis down
- Telegram down

**Scénarios temporels (TIME CHAOS — sous-estimé) :**
- Timestamp futur (+1h)
- Timestamp passé (-24h)
- Clock drift progressif
- Candles out-of-order
- Duplicate WebSocket sequence
- Delayed fills (ACK après 30s)
- Partial fills probabilistes
- Rejects exchange aléatoires

Les systèmes trading meurent souvent à cause du temps, pas du réseau.

**Validation :** Tous les chaos tests passent sans crash

---

## PHASE 6 — MODE DÉGRADÉ
**Objectif :** Fail-soft validé pour chaque module critique.

**Livrable :** `docs/stabilization/DEGRADED_MODE_MATRIX.md`

| Module mort | Fallback | Risque accepté |
|-------------|----------|----------------|
| RegimeEngine | neutral regime | leverage réduit |
| Redis | cache disabled | latence ↑ |
| Telegram | notifications bufferisées | aucune |
| ExchangeAPI | paper mode | pas de live |

**Validation :** Chaque fallback testé en isolation

---

## PHASE 7 — PAPER REALITY CHECK
**Objectif :** Écart paper/réel mesuré et documenté.

**Injections réalistes :**
- Slippage dynamique
- Spread variable
- Orderbook depth simulation
- Partial fills probabilistes
- Latency aléatoire
- Rejects exchange
- Rate limits

**Validation :** `paper_PnL vs market_PnL` gap < seuil documenté

---

## PHASE 8 — OBSERVABILITÉ TOTALE
**Objectif :** Auditabilité complète, logging structuré, state store unique.

**Invariant :** Chaque décision traçable via `trace_id` du signal au fill.

```
signal → conviction → risk → sizing → execution → fill → pnl
```

**Livrables :**
- `trace_id` propagé dans toute la chaîne
- State store unique (plus d'états distribués)
- `duration_ms` cognitif sur chaque couche
- `docs/stabilization/OBSERVABILITY_CONTRACT.md`

**Validation :** 100% des rejets visibles, 100% des décisions traçables

---

## Métrique de succès globale
```
NON : "combien d'IA j'ai"
OUI : "combien de comportements sont déterministes sous stress"
```
