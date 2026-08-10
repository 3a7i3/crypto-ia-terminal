# PHASE 3 — Refactor Métier : Rapport de Clôture

> Date: 2026-05-29

---

## Étape 3.1 — Inventaire des modules (surplus cognitif)

### Modules CONSERVÉS (7/10)

| Module | Raison | Capacité critique |
|--------|--------|-------------------|
| `self_awareness_engine.py` | 12 imports, branché advisor_loop | Bloque trading si dérive niveau 1-4 |
| `decision_quality_engine.py` | 7 imports, branché advisor_loop | Classifie VALIDATED/UNLUCKY/LUCKY/MISTAKE |
| `regret_engine.py` | 15 imports, branché advisor_loop | Ajuste seuil gate sur opportunités manquées |
| `meta_strategy_engine.py` | 12 imports, branché advisor_loop | Persona par régime + vote AgentVote |
| `decision_arbitrator.py` | 4 imports, branché advisor_loop | Agrège AgentVotes → décision finale |
| `no_trade_layer.py` | 13 imports, branché advisor_loop | Veto pré-trade intelligent |
| `chief_officer.py` | 9 imports, lazy dans advisor_loop | Briefing COO → Telegram (informatif) |

### Modules ARCHIVÉS (3/10)

| Module | Motif d'archivage | Destination |
|--------|-------------------|-------------|
| `proactive_alerts.py` | Seulement dans `main_v91.py` (non déployé) | `_ARCHIVE_2026/proactive_alerts.py` |
| `unified_learning_layer.py` | Référencé uniquement par `adaptive_calibration_engine` (lui-même mort) | `_ARCHIVE_2026/unified_learning_layer.py` |
| `adaptive_calibration_engine.py` | 0 import dans tout le projet | `_ARCHIVE_2026/adaptive_calibration_engine.py` |

Test associé archivé: `tests/test_proactive_alerts.py` → `_ARCHIVE_2026/`

---

## Étape 3.2 — Dashboard unique

**Dashboard actif en production:** `command_center_dashboard.py`
- Port: 8501
- Lancé par: `START_DASHBOARD.bat` + `deploy/setup_vps.sh`
- Technologie: Streamlit

**Verdict:** Déjà unique — aucun conflit de port détecté. Pas d'action requise.

Autres fichiers UI présents (non actifs en prod):
- `crypto_quant_v16/ui/quant_dashboard.py` — legacy
- `streamlit_dashboard.py` — prototype
- `tune.py` — outil de tuning interne

---

## Vérification pipeline core

```
Pipeline core intact:
  ConvictionEngine     ✓
  GlobalRiskGate       ✓
  PortfolioBrain       ✓
  OrderSizer           ✓
  ExecutionEngine      ✓
```

---

## Bilan archivage global (Phases 1-3)

| Phase | Fichiers archivés |
|-------|-------------------|
| Phase 1 (Gel arch.) | `mvp/`, `_legacy/`, `_sim_full.py` |
| Phase 2 (Truth map) | `hmm_regime_engine.py`, `global_risk_gate.py` (racine) |
| Phase 3 (Refactor)  | `proactive_alerts.py`, `unified_learning_layer.py`, `adaptive_calibration_engine.py`, `test_proactive_alerts.py` |

Tous les originaux conservés dans `_ARCHIVE_2026/` pour rollback.
