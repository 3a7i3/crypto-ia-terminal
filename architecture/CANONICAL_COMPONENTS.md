# CANONICAL COMPONENTS — crypto_ai_terminal
**Établi : 2026-06-11 | Phase P1**

## Règle d'architecture

> Une responsabilité → une interface publique → une implémentation canonique → plusieurs extensions possibles via plugins ou stratégies.

Toute nouvelle implémentation d'une responsabilité listée ici constitue une violation d'architecture.
Toute revue de code doit vérifier qu'aucune implémentation concurrente n'est introduite.

---

## Table des composants canoniques

| Responsabilité | Implémentation canonique | Chemin | Statut | Migration P1 |
|---|---|---|---|---|
| Event Bus | `EventBus` | `event_bus/bus.py` | ✅ Canonique | Migrer 3 stubs de test |
| Kill Switch | `KillSwitchHardened` | `supervision/killswitch_hardened.py` | ✅ Canonique | Migrer 9 stubs de test |
| Runtime State | `RuntimeStateMachine` | `system/state_machine.py` | ✅ Canonique | — |
| Execution Engine | `ExecutionEngine` | `quant_hedge_ai/agents/execution/execution_engine.py` | ✅ Canonique | Archiver stub src/ |
| Regime Detector | `AdvancedRegimeDetector` | `quant_hedge_ai/agents/intelligence/regime_detector.py` | ✅ Canonique | Archiver src/analytics/regime_detector.py |
| Feature Pipeline | `FeatureMaterializer` + `FeatureStore` | `quant_hedge_ai/features/` | ✅ Canonique | — |
| Decision Engine | `DecisionEngine` | `quant_hedge_ai/engine/decision_engine.py` | ⚠️ Canonique (à enrichir) | Étude auto_decision_engine |
| Configuration | — | à créer : `config/settings.py` (Pydantic) | ❌ À créer | Unifier 4 sources |

---

## Détail par verticale

---

### Event Bus

**Canonique :** `event_bus/bus.py`
- Thread-safe, singleton, support async, replay, stats
- 100+ lignes, production-ready

**Stubs de compatibilité à migrer (P1) :**
- `src/events/event_bus.py` — 21 lignes, importé par 3 tests et `src/telegram/sim_bot.py`
- Interface différente (sync simple vs async+singleton) — migration requise avant suppression

**Complémentaire (conserver) :**
- aucun

**Critères d'acceptation P1 :**
```
✓ 1 seule implémentation de production
✓ 0 wrapper legacy avec interface différente
✓ 0 import legacy dans les tests
```

---

### Kill Switch

**Canonique :** `supervision/killswitch_hardened.py`
- Thread-safe, Telegram, state persistence, acknowledgement
- 150+ lignes, production-ready

**Stubs de compatibilité à migrer (P1) :**
- `src/risk/kill_switch.py` — 9 lignes, importé par 9 tests, `src/analytics/edge_scorer.py`, `src/telegram/sim_bot.py`, `src/agent/codex_agent.py`
- Interfaces différentes (stub vs hardened) — migration requise avant suppression

**Complémentaire (conserver) :**
- `supervision/telegram_kill_switch.py` — Variante Telegram (rôle différent)

**Critères d'acceptation P1 :**
```
✓ 1 seul moteur de sécurité
✓ 1 seule interface publique (KillSwitchHardened)
✓ 0 import du stub dans le code production
```

---

### Execution Engine

**Canonique :** `quant_hedge_ai/agents/execution/execution_engine.py`
- 555 lignes, multi-mode (paper/live/testnet/futures), safety layer complète
- `OrderDeduplicator`, `SessionGuard`, `TradeLogger`
- Point d'entrée unique depuis `main_v91` et `advisor_loop`

**Stubs à archiver (P1) :**
- `src/engine/execution_router.py` — 11 lignes, jamais utilisé en production, 8 tests en dépendent

**Complémentaire (conserver, rôle distinct) :**
- `paper_trading/` — 2 677 lignes, simulateur avec friction réaliste (slippage, latence, fees). Utilisé pour E2E testing et sandbox, PAS dans le runtime principal. Relation : route alternative de test, non chemin d'exécution.

**Critères d'acceptation P1 :**
```
✓ 1 seule API d'exécution pour le runtime
✓ 1 seul routeur (paper/live/testnet auto-détectés)
✓ 0 stub execution_router en production
```

---

### Regime Detector

**Canonique :** `quant_hedge_ai/agents/intelligence/regime_detector.py`
- `AdvancedRegimeDetector` — 5 régimes (bull_trend, bear_trend, sideways, high_volatility, flash_crash)
- 51 lignes, importé par 15+ fichiers via un shim de rétro-compatibilité

**Shim à conserver (puis supprimer) :**
- `quant_hedge_ai/agents/market/regime_detector.py` — 9 lignes, re-exporte `AdvancedRegimeDetector as RegimeDetector`. Conserver pendant la migration, supprimer après passage complet aux imports directs.

**Legacy à archiver (P1) :**
- `src/analytics/regime_detector.py` — 86 lignes, 3 régimes seulement, 0 import production

**Critères d'acceptation P1 :**
```
✓ 1 seule implémentation : AdvancedRegimeDetector
✓ 0 implémentation alternative active
✓ Shim supprimé après migration des imports directs
```

---

### Feature Pipeline

**Canonique (trading runtime) :** `quant_hedge_ai/features/`
- `FeatureMaterializer` (188L) + `FeatureStore` (199L) + `FeatureValidator` (107L)
- V2 architecture, versioning, TTL cache, drift detection
- Utilisé dans `advisor_loop` via Signal Engine

**Complémentaire (conserver, rôle distinct) :**
- `src/analytics/` — Alpha research, validation post-trade (AlphaPipeline, BootstrapStability, EdgeScorer). Route analysis, pas trading live. Les deux doivent coexister avec des responsabilités claires.

**Clarification de rôle obligatoire (P1) :**
```
quant_hedge_ai/features/   →  features en temps réel pour le runtime
src/analytics/             →  analyse post-trade et validation alpha
```
Ces deux packages ne sont PAS en concurrence : ils ont des responsabilités différentes.

**Critères d'acceptation P1 :**
```
✓ 1 seul pipeline pour le feature vector live
✓ Rôles documentés (runtime vs research)
✓ 0 confusion entre les deux pipelines
```

---

### Decision Engine

**Canonique actuel :** `quant_hedge_ai/engine/decision_engine.py`
- 80 lignes, `DecisionEngine` + `StrategyRanker`
- Intégré dans `main_v91` et `main_system` — c'est le point d'entrée runtime

**Candidat à l'intégration (étude requise) :**
- `tracker_system/autonomous/auto_decision_engine.py` — 435 lignes, `AutoDecisionOrchestrator`, système complet avec guards, audit trail, state machine. 2 tests dédiés. **N'est PAS dans le runtime principal** — fonctionne en parallèle. Peut devenir la prochaine version du canonique ou un mode avancé.

**Action P1 :**
Étude fonctionnelle requise avant toute décision :
1. Quelles responsabilités d'`auto_decision_engine` ne sont pas couvertes par le canonique ?
2. Peut-il devenir l'implémentation de référence après enrichissement du canonique ?
3. Ou ses responsabilités doivent-elles être absorbées par d'autres couches (Risk, Governance) ?

**Critères d'acceptation P1 :**
```
✓ Étude fonctionnelle auto_decision_engine documentée
✓ Décision d'intégration ou d'archivage prise et justifiée
✓ 1 seul point d'entrée décisionnel dans le runtime
```

---

### Configuration

**Canonique :** inexistant — **À créer en P1**

**4 sources actuelles à unifier :**
- `.env` — variables d'environnement
- `runtime_config.json` — configuration runtime
- `runtime_config.py` — configuration Python
- `telegram_config.json` — configuration Telegram

**Cible :** `config/settings.py` avec Pydantic `BaseSettings`
- Lecture des variables d'environnement en priorité
- Valeurs par défaut documentées
- Validation au démarrage (fail-fast)
- Une seule source de vérité importée partout

**Critères d'acceptation P1 :**
```
✓ 1 seul objet settings importé depuis config/settings.py
✓ 0 json runtime en doublon
✓ 0 fichier .py de configuration parallèle
✓ Validation Pydantic au démarrage
```

---

## Composants sans doublon (ne pas toucher)

| Composant | Chemin | Note |
|---|---|---|
| Portfolio Brain | `quant_hedge_ai/agents/risk/portfolio_brain.py` | Monolithe (740L), à splitter en P2 |
| Market Scanner | `quant_hedge_ai/agents/market/market_scanner.py` | Monolithe (829L), à splitter en P2 |
| Global Risk Gate | `quant_hedge_ai/agents/risk/global_risk_gate.py` | Canonique unique |
| Governance | `governance/` | Canonique unique |
| Audit Trail | `governance/audit_trail.py` | Canonique unique |
| Error Bus | `errors/error_bus.py` | Canonique unique |
| Heartbeat | `observability/heartbeat_system.py` | Canonique unique |

---

## Processus d'ajout d'un nouveau composant

Avant de créer une nouvelle implémentation d'une responsabilité existante :

1. Vérifier si la responsabilité est déjà couverte dans ce document.
2. Si oui : utiliser le canonique ou créer un plugin/stratégie.
3. Si non : ajouter l'entrée dans ce document AVANT d'écrire le code.
4. Enregistrer le module dans `architecture/modules_registry.yaml`.

**Un composant non enregistré = dette technique par défaut.**
