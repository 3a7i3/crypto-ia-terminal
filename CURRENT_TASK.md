# CURRENT_TASK

## Focus actuel

P9 — Meta Governance : supervision globale, détection de dérives comportementales, ajustement haut niveau.

## Contexte utile

- P8 fermé (2026-05-26) : StrategyAllocator, ProbationSystem, ConfidenceScorer, CorrelationMonitor — 34/34 tests
- SweepDetector + SweepOutcomeTracker câblés dans advisor_loop.py
- anara_context v1.4 : 46 modules indexés, topologie complète
- Branch active : feat/stack-unification
- 1563/1563 tests verts avant démarrage P9

## Composants P9 à implémenter

1. **SystemHealthMonitor** — métriques latence/erreurs/CPU par composant, états GREEN/YELLOW/RED
2. **BehavioralDriftDetector** — dérive distributions décisions vs baseline, écart > 2σ → alerte
3. **Self-Monitoring Loop** — meta_health_score = santé composants + absence dérive + stabilité transitions
4. **AnomalyGovernance** — détection patterns anormaux (+10× trades, score -20pts, transitions RG > 3/10 cycles)
5. **PerformanceSupervisor** — Sharpe glissant 20/50/100 trades, comparaison réel vs Shadow Engine
6. **PortfolioIntelligence** — concentration exchange/stratégie, exposition nette > 80% → réduction forcée

## Modules partiellement existants (à consolider)

- `behavioral_stability_monitor.py` → base pour BehavioralDriftDetector (P9.2)
- `activity_tracker.py` → input pour Self-Monitoring Loop (P9.3)
- `proactive_alerts.py` → base pour AnomalyGovernance (P9.4)
- `chief_officer.py` → base pour PerformanceSupervisor (P9.5)

## Critères de succès P9

- [ ] Dérive simulée détectée (threshold poussé à 80 pendant 30 cycles)
- [ ] Suspension avant 3 pertes consécutives sur dérive
- [ ] Sharpe glissant calculé en temps réel
- [ ] 0 faux positif sur 100 cycles en régime stable

## Prochaines actions

1. Implémenter SystemHealthMonitor (P9.1) + tests
2. Implémenter BehavioralDriftDetector (P9.2) en consolidant behavioral_stability_monitor.py
3. Implémenter Self-Monitoring Loop (P9.3)
4. Implémenter AnomalyGovernance (P9.4)
5. Implémenter PerformanceSupervisor (P9.5)
6. Implémenter PortfolioIntelligence (P9.6)
7. Câbler dans advisor_loop.py
8. Tests de validation P9

## Notes

Cette page doit rester courte, concrete et orientée exécution.
