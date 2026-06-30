# Blueprint V2 — crypto_ai_terminal
# Architecture institutionnelle en 7 niveaux
#
# Référence normative pour toutes les sessions.
# Mis à jour à chaque franchissement de jalon.
# Version : 2.0   Date : 2026-06-30

---

## Vue d'ensemble

```
L7 ── Meta Intelligence        [0/100]  ← auto-évolution longue durée
L6 ── Live Operations          [36/100] ← paper trading + monitoring
L5 ── Digital Twin             [0/100]  ← simulation shadow complète
L4 ── Research Lab             [0/100]  ← hypothèses auto-générées
L3 ── Scientific Governance    [10/100] ← audit, traçabilité, reproductibilité
L2 ── Scientific Validation    [35/100] ← preuve statistique de l'edge
L1 ── Engineering              [100/100]← infrastructure ✅

PMI (Project Maturity Index) = 181 / 700 = 26%  [baseline 2026-06-30]
```

**Règle de progression :** un niveau ne démarre pleinement que quand le niveau inférieur
atteint sa gate. Les niveaux ne sont pas strictement séquentiels — L3 peut avancer
pendant L2 — mais la gate L2 bloque toute opération L4+ et bloque live trading.

---

## Niveau 1 — Engineering  [COMPLÉTÉ — 100/100]

### Mission
Construire l'infrastructure de trading déterministe, testable, observable.

### Composants livrés
| Module | Fichier | Garantie |
|---|---|---|
| DecisionEngine v9 | core/advisor_loop.py | 12 couches, PacketDecision souverain |
| EventBus | observability/decision_event_bus.py | pub/sub non-bloquant, ThreadPoolExecutor |
| DecisionObservation | observability/decision_observation.py | frozen dataclass, 40+ champs |
| RejectionStore | observability/rejection_store.py | JSONL atomic flush+fsync |
| RegretScheduler | observability/regret_scheduler.py | 7 horizons (5m→24h), daemon |
| DecisionExplainer | observability/decision_explainer.py | rapport lisible ≤ 4000 chars |
| Feature Flags | config/feature_flags.py | FEATURE_AUTO_CALIBRATION=false permanent |
| Formal Governance | governance/ | EIC_v2, ATC, DPSS, SEP, STI — 388 tests |
| Data Gov Spec | docs/data_governance_spec_v1.md | 24 DG-xxx, 4 niveaux certification |
| Dataset Certifier | tools/dataset_certifier.py | CLI, DG-001→DG-024, 32 tests |

### Gate L1 → L2 : FRANCHIE ✅

---

## Niveau 2 — Scientific Validation  [EN COURS — 35/100]

### Mission
Prouver que le DecisionEngine a une edge statistiquement significative sur les
hypothèses H1-H4, avec données certifiées, avant tout passage en capital réel.

### Sous-phases

#### S1 — Certification du Dataset (outil livré, données en attente)
```
Outil    : tools/dataset_certifier.py
Input    : databases/rejections/ + EXP-001.yaml manifest
Output   : CERT-2026-Q3-001 (niveau CERTIFIED ou PASS)
Gate S1  : certification_id non null dans EXP-001.yaml
Statut   : outil 100% livré — N trades = 0 (données en cours d'accumulation)
```

#### S2 — Statistical Readiness
```
Outil    : tools/statistical_readiness.py  [À CRÉER — gate S1]
Checks   :
  □ N totaux >= 100 (gate EXP-001)
  □ Distribution BUY/SELL/HOLD équilibrée (tolérance 80/10/10)
  □ Couverture régimes (sideways / bull / bear : N >= 30 chacun)
  □ Absence de data drift (test Kolmogorov-Smirnov sur features ts > 50%)
  □ Couverture temporelle (>= 7 jours calendaires)
Gate S2  : statistical_readiness.py exit 0
```

#### S3 — Calibration Readiness Index (CRI)
```
Outil    : tools/cri_calculator.py  [À CRÉER — gate S2]
Formule  : CRI = (w1*N_score + w2*coverage_score + w3*drift_score + w4*balance_score) / 100
Gate S3  : CRI >= 90/100
```

#### S4 — Hypothesis Testing
```
Outil    : analysis/hypothesis_tester.py  [À CRÉER — gate S3]
Input    : databases/rejections/ certifié + analysis/hypothesis_registry.yaml
Tests    :
  H1 (BUY sideways → expectancy négative) : t-test unilatéral, p < 0.05
  H2 (SELL bear → expectancy positive)    : t-test unilatéral, p < 0.05
  H3 (Score >= 75 → meilleure expectancy) : Mann-Whitney U, p < 0.05
  H4 (ATR% >= 1.5 → meilleur PF)         : Wilcoxon signed-rank, p < 0.05
Output   : hypothesis_registry.yaml §status mis à jour + evidence_level
Gate S4  : zéro Inconclusive sur H1+H2+H3 quand N >= min_n_required
           zéro conflit H1↔H3 et H2↔H3
```

#### S5 — Go/No-Go Decision
```
Outil    : tools/go_no_go.py  [À CRÉER — gate S4]
Métriques financières : PF >= 1.4, Expectancy > 0, DD < 10%, Sharpe > 0.5
Métriques scientifiques : CRI >= 90, certification CERTIFIED/PASS,
                          evidence_level >= Moderate pour H1+H2+H3
Sortie   : rapport GO (→ L6 capital réel Phase A $50) ou NO-GO (→ ajustements, nouvel EXP)
```

### Ce qui ne doit PAS être créé pendant L2
- Nouveaux indicateurs techniques
- Nouvelles couches décisionnelles
- Nouvelles stratégies / personnalités
- Nouvelles règles de filtrage
- ACE (Auto-Calibration Engine) — interdit jusqu'à CRI >= 90

### Gate L2 → capital réel
Toutes les gates S1→S5 VERTES + décision Go/No-Go opérateur → Phase A ($50 réel).

---

## Niveau 3 — Scientific Governance  [EMBRYONNAIRE — 10/100]

### Mission
Infrastructure institutionnelle pour gérer la connaissance scientifique accumulée :
traçabilité, reproductibilité, audit, détection des dérives, rapport de maturité.

### 10 G-modules (vision — à créer post-gate L2)

| ID | Module | Fichier cible | Fonction |
|---|---|---|---|
| G-01 | DataQualityMonitor | governance/science/dq_monitor.py | Surveille les métriques DG-xxx en temps réel |
| G-02 | StatPowerCalculator | governance/science/stat_power.py | Calcule la puissance statistique atteinte |
| G-03 | HypothesisConflictDetector | governance/science/conflict_detector.py | Détecte H_i↔H_j contradictoires |
| G-04 | EvidenceLevelTracker | governance/science/evidence_tracker.py | Trace l'évolution des evidence_level par hypothèse |
| G-05 | ExperimentLineageVerifier | governance/science/lineage_verifier.py | Vérifie la filiation des datasets (parent_uuid chain) |
| G-06 | DatasetDriftDetector | governance/science/drift_detector.py | Détecte le drift entre datasets successifs |
| G-07 | CRICalculator | governance/science/cri_calculator.py | CRI automatisé à chaque N%50 |
| G-08 | ScientificAuditReport | governance/science/audit_report.py | Rapport PDF/Markdown complet à la demande |
| G-09 | GoNoGoEngine | governance/science/go_no_go_engine.py | Moteur décisionnel automatique (recommandation) |
| G-10 | PMIUpdater | governance/science/pmi_updater.py | Met à jour le PMI et CLAUDE.md |

### Gate L3
G-01→G-10 livrés + premier ScientificAuditReport généré sur EXP-001.

---

## Niveau 4 — Research Lab  [NON DÉMARRÉ — 0/100]

### Mission
Laboratoire quantitatif avec génération automatique d'hypothèses, backtesting
sur données historiques certifiées, et simulation Monte Carlo.

### Prérequis stricts
- Gate L2 FRANCHIE (edge prouvée)
- N >= 500 trades certifiés (pour backtesting significatif)
- hypothesis_quality.yaml : >= 2 évaluations par hypothèse principale

### Modules prévus (liste non exhaustive)
```
research/hypothesis_generator.py  — propose H_new basées sur les résidus d'erreur
research/backtester.py            — backtesting sur datasets certifiés (jamais live)
research/monte_carlo.py           — simulation distribution des outcomes
research/regime_lab.py            — Axe 2 : taxonomie hiérarchique des régimes
research/alpha_decay_tracker.py   — mesure la durée de vie des hypothèses confirmées
```

### Gate L4
Première hypothèse auto-générée confirmée avec evidence_level >= Moderate.

---

## Niveau 5 — Digital Twin  [NON DÉMARRÉ — 0/100]

### Mission
Jumeau numérique complet du système : replay temps réel, simulation shadow,
A/B testing de configurations, stress testing sur scénarios extrêmes.

### Prérequis stricts
- Gate L4 FRANCHIE
- Research Lab opérationnel (hypothèses générées + validées)
- Modèle de marché calibré sur données certifiées (N >= 1000)

### Architecture cible
```
digital_twin/
  ├── market_simulator.py      — simulation OHLCV avec régime injecté
  ├── twin_engine.py           — clone du DecisionEngine (version gelée)
  ├── shadow_runner.py         — exécution parallèle twin vs live (passive)
  ├── ab_tester.py             — compare config A vs B sur historique certifié
  └── stress_tester.py         — scénarios extrêmes (krach, flash crash, faible liquidité)
```

### Passivité ADR-0007 étendue au twin
Le Digital Twin ne peut jamais interagir avec l'engine live. Il est en lecture seule
sur les DecisionObservations publiées sur le bus (observer passif).

### Gate L5
Twin reproduit les métriques live à ± 5% sur 30 jours en shadow mode.

---

## Niveau 6 — Live Operations  [PARTIEL — 36/100]

### Mission
Trading réel progressif avec monitoring temps réel, alertes, failsafe, et
progression contrôlée du capital déployé.

### Phases de capital (inchangées depuis P13)
```
Phase A : $50 réel (gate L2 requise)
Phase B : $200 réel (30 jours Phase A + PF >= 1.3)
Phase C : capital total (90 jours Phase B + DD < 5%)
```

### Composants actifs (36/100)
| Composant | Statut | Fichier |
|---|---|---|
| MEXC paper trading | ACTIF | core/advisor_loop.py |
| Telegram alertes | ACTIF | scripts/telegram_alerts.py |
| DecisionExplainer → Telegram | ACTIF | observability/decision_explainer.py |
| RejectionStore | ACTIF | observability/rejection_store.py |
| RegretScheduler (7 horizons) | ACTIF | observability/regret_scheduler.py |
| VPS watchdog | ACTIF | watchdog_vps.py |
| Health check | ACTIF | analysis/health_check.py |
| Data quality | ACTIF | analysis/data_quality.py |

### Composants manquants pour 100/100
| Composant | Prérequis | Priorité |
|---|---|---|
| LiveMonitorDashboard (Streamlit) | gate S1 | Haute |
| AlertingEngine (drawdown/stall) | gate S1 | Haute |
| Capital réel Phase A | gate L2 | BLOQUÉ |
| PositionReconciler live | gate L2 | BLOQUÉ |
| Levier dynamique | gate L4 (interdit avant) | Long terme |

### Gate L6 → Phase A
Go/No-Go positif EXP-001 (gate L2 complète).

---

## Niveau 7 — Meta Intelligence  [VISION — 0/100]

### Mission
Le système apprend de ses propres décisions sur le long terme : patterns
d'erreurs récurrents, régimes non capturés, hypothèses auto-invalidées.

### Prérequis stricts
- N >= 2000 trades certifiés en live
- Axe 3 Knowledge Graph opérationnel (L4)
- Digital Twin stable en shadow mode (L5)
- Toutes gates L1→L6 FRANCHIES

### Vision (non implémentable avant H2 2027)
```
meta/knowledge_graph.py     — graphe Dataset→Exp→Hypothesis→Layer→Regime→Outcome
meta/mistake_memory_v3.py   — mémoire des patterns d'erreurs structurels
meta/auto_calibrator.py     — FEATURE_AUTO_CALIBRATION=true (unique activation autorisée)
meta/recommendation_engine.py — recommande des ajustements à l'opérateur (jamais auto)
```

### Gate L7
Première recommandation validée par l'opérateur et appliquée en production.

---

## PMI — Project Maturity Index

### Définition
PMI = (L1 + L2 + L3 + L4 + L5 + L6 + L7) / 700

Chaque niveau est noté de 0 à 100 selon ses propres critères de complétude.
Le PMI progresse avec les données accumulées et les gates franchies,
**jamais avec le nombre de lignes de code ajoutées**.

### Historique

| Date | L1 | L2 | L3 | L4 | L5 | L6 | L7 | PMI |
|------|----|----|----|----|----|----|----|----|
| 2026-06-30 | 100 | 35 | 10 | 0 | 0 | 36 | 0 | **181/700 = 26%** |

### Règle de mise à jour
Le PMI est mis à jour dans CLAUDE.md à chaque franchissement de gate.
PMI = 100% n'est pas un objectif à court terme. L'objectif immédiat est
**gate L2** (Go/No-Go EXP-001), qui débloque L6 Phase A.

---

## Roadmap concentrée

```
MAINTENANT        : accumuler N trades (VPS actif, paper trading MEXC)
Gate S1  (N=30)   : dataset_certifier.py → CERT-2026-Q3-001
Gate S2  (N=50)   : statistical_readiness.py exit 0
Gate S3  (N=100)  : cri_calculator.py → CRI >= 90
Gate S4  (N=100)  : hypothesis_tester.py → H1+H2+H3 concluantes
Gate S5  (N=100)  : go_no_go.py → GO ou NO-GO + rapport
                    ↓ SI GO
Phase A  (live)   : $50 capital réel, monitoring L6 complet
                    ↓ après 30j + PF >= 1.3
Phase B  (live)   : $200 capital réel
                    ↓ après 90j + DD < 5%
Phase C  (live)   : capital total → débloque L3/L4/L5/L7
```

---

## Principes architecturaux invariants

1. **ADR-0007 Passivité absolue** : observabilité, gouvernance, lab, twin = passifs.
   L'engine de trading est le seul à décider.

2. **Scientific Debt Rule** : zéro feature sans hypothèse préexistante.

3. **Immutabilité scientifique** : dataset référencé par une expérience close = immuable.
   Les corrections créent un nouveau UUID.

4. **Evidence-first** : aucun paramètre modifié sans p-value + n + effect size documentés.

5. **Séquentialité des gates** : L4/L5/L7 ne démarrent pas avant gate L2 VERTE.

6. **FEATURE_AUTO_CALIBRATION=false** : défaut permanent. Seul L7 (meta_intelligence)
   peut l'activer, avec ADR signé par l'opérateur.
