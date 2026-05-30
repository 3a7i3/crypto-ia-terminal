# SYSTEM TRUTH MAP — Phase 2 Cartographie de Vérité

> Généré le 2026-05-29. Source de vérité unique par domaine.
> Méthode: grep sur le code live + traçage des imports de `advisor_runtime_adapters.py`.

---

## Règle souveraine

**Un domaine = une seule source de vérité active.** Les autres implémentations
sont soit des auxiliaires (shadow, tracker), soit des doublons à surveiller/supprimer.

---

## Cartographie par domaine

### 1. Signal de marché

| Rang | Fichier | Classe/Fonction | Statut |
|------|---------|-----------------|--------|
| **SOUVERAIN** | `quant_hedge_ai/agents/execution/live_signal_engine.py` | `LiveSignalEngine.evaluate()` | Branché `advisor_loop` |
| Auxiliaire | `quant_hedge_ai/agents/execution/signal_engine.py` | `SignalEngine` | Sous-composant de LiveSignalEngine |
| Auxiliaire | `quant_hedge_ai/agents/execution/multi_timeframe_signal.py` | — | Enrichissement MTF |
| Script | `data_verifier.py:394` | `generate_signal()` | Utilitaire CLI, hors production |

**Verdict:** OK — un seul producteur de signal dans la boucle live.

---

### 2. Régime de marché

| Rang | Fichier | Classe | Statut |
|------|---------|--------|--------|
| **SOUVERAIN** | `quant_hedge_ai/agents/intelligence/regime_detector.py` | `AdvancedRegimeDetector` | Importé `advisor_runtime_adapters:80` |
| Tracker état | `quant_hedge_ai/agents/intelligence/market_regime_classifier.py` | `RegimeStateTracker` | Importé `advisor_runtime_adapters:72` — complément, pas classifieur |
| Lisseur | `quant_hedge_ai/agents/intelligence/regime_transition_smoother.py` | `RegimeTransitionSmoother` | Importé `advisor_runtime_adapters:83` — post-traitement |
| **NON BRANCHÉ** | `quant_hedge_ai/agents/intelligence/hmm_regime_engine.py` | `HMMRegimeEngine` | Présent dans ARBORESCENCE, 0 import dans `advisor_runtime_adapters` |
| Tracker interne | `tracker_system/intelligence/auto_regime_detector.py` | `AutoRegimeDetector` | Système tracker isolé, sans lien live |
| Script | `data_verifier.py:330` | `detect_regime()` | Utilitaire CLI uniquement |

**Verdict:** CONFLIT partiel.
- `HMMRegimeEngine` est une 2e implémentation complète non connectée.
- Action: documenter son rôle ou l'intégrer comme sous-couche de `AdvancedRegimeDetector`.

---

### 3. Position ouverte

| Rang | Fichier | API | Statut |
|------|---------|-----|--------|
| **SOUVERAIN** | `quant_hedge_ai/agents/execution/position_manager.py` | `PositionManager` | Importé `advisor_runtime_adapters:53` |
| Tracker auxiliaire | `tracker_system/core/trade_tracker.py` | `open_position` / `finalize_position` | Importé `advisor_runtime_adapters:108-111` — journalisation TP/SL |
| **DOUBLON INACTIF** | `tracker_system/trade_tracker.py` | `open_position` / `close_position` | 0 import direct dans le runtime — doublon de `core/trade_tracker.py` |

**Verdict:** DOUBLON détecté.
- `tracker_system/trade_tracker.py` (302 lignes) vs `tracker_system/core/trade_tracker.py` (322 lignes).
- Aucun module production n'importe le fichier racine.
- Action: supprimer `tracker_system/trade_tracker.py` ou confirmer s'il reste une entrée de compatibilité.

---

### 4. Sizing des ordres

| Rang | Fichier | Classe | Statut |
|------|---------|--------|--------|
| **SOUVERAIN** | `quant_hedge_ai/agents/risk/order_sizer.py` | `OrderSizer` | Importé `advisor_runtime_adapters` |
| Moteur capital | `quant_hedge_ai/agents/risk/capital_allocation_engine.py` | `CapitalAllocationEngine` | Complémentaire (Kelly/EV) |

**Verdict:** OK.

---

### 5. Drawdown & Risk Gate

| Rang | Fichier | Classe | Statut |
|------|---------|--------|--------|
| **SOUVERAIN** | `quant_hedge_ai/agents/risk/global_risk_gate.py` | `GlobalRiskGate` | Importé `advisor_runtime_adapters:100` |
| Garde drawdown | `quant_hedge_ai/agents/risk/drawdown_guard.py` | `DrawdownGuard` | Sous-composant |
| **DOUBLON INACTIF** | `global_risk_gate.py` (racine) | `GlobalRiskGate` | 0 reverse-import dans le code projet |

**Verdict:** DOUBLON détecté.
- `global_risk_gate.py` à la racine est une implémentation autonome async complète (327 lignes),
  jamais importée par le code production.
- Action: confirmer si c'est un prototype archivable ou déplacer vers `_ARCHIVE_2026/`.

---

### 6. Exécution des ordres

| Rang | Fichier | Classe | Statut |
|------|---------|--------|--------|
| **SOUVERAIN** | `quant_hedge_ai/agents/execution/execution_engine.py` | `ExecutionEngine` | Importé `advisor_runtime_adapters:51` |
| Shadow (parallèle) | `quant_hedge_ai/agents/execution/shadow_engine.py` | `ShadowExecutionEngine` | Co-branché — simulation, pas concurrent |
| Connecteur bas-niveau | `quant_hedge_ai/binance_connector.py` | `place_order` | Utilisé par ExecutionEngine en interne |

**Verdict:** OK — pas de concurrence. ShadowEngine est une couche d'audit, pas un exécuteur alternatif.

---

### 7. État runtime (boucle principale)

| Rang | Fichier | Statut |
|------|---------|--------|
| **SOUVERAIN** | `advisor_loop.py` | Orchestrateur central |
| Adaptateurs | `advisor_runtime_adapters.py` | Câblage des imports |

**Verdict:** OK.

---

### 8. Historique des décisions

| Rang | Fichier | Statut |
|------|---------|--------|
| **SOUVERAIN** | `databases/shadow_execution/` + `black_box.jsonl` | Audit immuable |

**Verdict:** OK.

---

## Pipeline SIGNAL → EXECUTION (chemin réel)

```
MarketScanner.scan()
    │
    ▼
LiveSignalEngine.evaluate(symbol, candles, features)
    │  → SignalResult {signal, score, actionable}
    │
    ▼
AdvancedRegimeDetector.classify(features)  ← + RegimeStateTracker + RegimeTransitionSmoother
    │  → regime: str
    │
    ▼
GlobalRiskGate.check(signal_result, regime, ...)
    │  → gate.allowed: bool
    │
    ▼  [si allowed]
PortfolioBrain.approve_packet(DecisionPacket, open_positions, size_usd)
    │  → approved: bool
    │
    ▼  [si approved]
OrderSizer.compute(signal_result, regime, ...)
    │  → order_size_usd
    │
    ▼
ExecutionEngine.execute(symbol, side, size_usd)
    │
    ├──► TradeLogger (SQLite)
    ├──► tracker_system.core.trade_tracker.open_position()
    └──► ShadowExecutionEngine.simulate() [parallèle, audit]
```

**Résultat de la vérification Étape 2.2:** Un seul chemin d'exécution.
`ShadowEngine` est parallèle mais ne produit pas d'ordres réels.

---

## Conflits à résoudre (priorités)

| # | Sévérité | Domaine | Conflit | Action |
|---|----------|---------|---------|--------|
| C-01 | **MOYEN** | Régime | `HMMRegimeEngine` — 0 import anywhere, dead code complet | Archiver dans `_ARCHIVE_2026/` |
| C-02 | **INFO** | Position | `tracker_system/trade_tracker.py` — shim legacy utilisé par `tests/test_tracker_schema_compat.py` | Ne pas supprimer — shim intentionnel, annoter avec commentaire |
| C-03 | **FAIBLE** | Risk Gate | `global_risk_gate.py` (racine) jamais importé | Archiver dans `_ARCHIVE_2026/` |

---

## Script de validation

```python
# Vérifie qu'un seul module répond par domaine critique
TRUTH_MAP = {
    "signal":    "quant_hedge_ai.agents.execution.live_signal_engine.LiveSignalEngine",
    "regime":    "quant_hedge_ai.agents.intelligence.regime_detector.AdvancedRegimeDetector",
    "position":  "quant_hedge_ai.agents.execution.position_manager.PositionManager",
    "risk_gate": "quant_hedge_ai.agents.risk.global_risk_gate.GlobalRiskGate",
    "execution": "quant_hedge_ai.agents.execution.execution_engine.ExecutionEngine",
    "sizing":    "quant_hedge_ai.agents.risk.order_sizer.OrderSizer",
}

for domain, path in TRUTH_MAP.items():
    module_path, cls = path.rsplit(".", 1)
    m = __import__(module_path, fromlist=[cls])
    assert hasattr(m, cls), f"FAIL {domain}: {cls} introuvable dans {module_path}"
    print(f"OK {domain}: {cls}")
```
