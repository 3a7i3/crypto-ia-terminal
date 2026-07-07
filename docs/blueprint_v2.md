# Blueprint V2 — crypto_ai_terminal
# Architecture institutionnelle en 7 niveaux + couche L3.5
#
# Référence normative pour toutes les sessions.
# Mis à jour à chaque franchissement de jalon.
# Version : 2.2   Date : 2026-07-01

---

## Vue d'ensemble

```
L7   ── Scientific Intelligence Core  [0/100]  ← connaissance scientifique long terme
L6   ── Live Operations               [36/100] ← paper trading + monitoring
L5   ── Digital Twin                  [0/100]  ← simulation shadow complète
L4   ── Research Lab                  [0/100]  ← hypothèses auto-générées
L3.5 ── Scientific Intelligence Layer [0/100]  ← langage scientifique du DIP
L3   ── Scientific Governance         [10/100] ← audit, traçabilité, reproductibilité
L2   ── Scientific Validation         [35/100] ← preuve statistique de l'edge
L1   ── Engineering                   [100/100]← infrastructure ✅

PMI-7 Capability Score  = 181 / 700 = 26%    [baseline 2026-06-30]
PMI-7 Evidence Score    =   0 / 700 =  0%    [aucune donnée certifiée]
SDOS Capability Score   = 181 / 800 = 22.6%  [inclut L3.5, baseline 2026-07-01]
```

**Règle de progression :** un niveau ne démarre pleinement que quand le niveau inférieur
atteint sa gate ADG. Les niveaux ne sont pas strictement séquentiels — L3 peut avancer
pendant L2 — mais ADG-02 bloque toute opération L4+ et bloque le capital réel.

**Règle SDOS :** L3.5 ne compte pas comme capacité runtime. Il formalise le langage
scientifique qui transforme les observations DIP en connaissance : Decision →
RootCause → Hypothesis → Dataset → Evidence → Confidence → ScientificConclusion →
RecommendedExperiment.

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

### Gate ADG-01 : FRANCHIE ✅
Contrat d'entrée L1 : infrastructure de trading minimale existante.
Contrat de sortie L1 : tous les tests verts + ADR-0007 approuvée + observabilité câblée.

---

## Niveau 2 — Scientific Validation  [EN COURS — 35/100]

### Mission
Prouver que le DecisionEngine a une edge statistiquement significative sur les
hypothèses H1-H4, avec données certifiées, avant tout passage en capital réel.

### Maturité L2

```
Maturity 0 : Aucun dataset (situation actuelle — N = 0 certifié)
     ↓
Maturity 1 : Dataset certifié — gate S1 (N >= 30, CERT-2026-Q3-001 non null)
     ↓
Maturity 2 : Hypothèses évaluées — gate S4 (N >= 100, p-value calculée pour H1+H2+H3)
     ↓
Maturity 3 : Evidence Strong — (H1+H2+H3 Confirmed/Rejected, evidence_level >= Strong)
     ↓
Maturity 4 : Validation complète — gate S5 (Go/No-Go positif opérateur)
```

### Sous-phases

#### S1 — Certification du Dataset (outil livré, données en attente)
```
Outil    : tools/dataset_certifier.py
Input    : databases/rejections/ + EXP-001.yaml manifest
Output   : CERT-2026-Q3-001 (niveau CERTIFIED ou PASS)
Gate S1  : certification_id non null dans EXP-001.yaml
Statut   : outil 100% livré — N trades = 0 (en cours d'accumulation)
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
Tests    :
  H1 (BUY sideways → expectancy négative) : t-test unilatéral, p < 0.05
  H2 (SELL bear → expectancy positive)    : t-test unilatéral, p < 0.05
  H3 (Score >= 75 → meilleure expectancy) : Mann-Whitney U, p < 0.05
  H4 (ATR% >= 1.5 → meilleur PF)         : Wilcoxon signed-rank, p < 0.05
Output   : hypothesis_registry.yaml §status + evidence_level mis à jour
Gate S4  : zéro Inconclusive H1+H2+H3 quand N >= min_n_required
           zéro conflit H1↔H3 et H2↔H3
```

#### S5 — Go/No-Go Decision
```
Outil    : tools/go_no_go.py  [À CRÉER — gate S4]
Métriques financières : PF >= 1.4, Expectancy > 0, DD < 10%, Sharpe > 0.5
Métriques scientifiques : CRI >= 90, certification CERTIFIED/PASS,
                          evidence_level >= Moderate pour H1+H2+H3
Sortie   : rapport GO (→ L6 capital réel Phase A $50) ou NO-GO
```

### Ce qui ne doit PAS être créé pendant L2
- Nouveaux indicateurs techniques
- Nouvelles couches décisionnelles ou stratégies
- Toute modification de seuil existant
- ACE (Auto-Calibration Engine) — interdit jusqu'à CRI >= 90

### Gate ADG-02
Contrat d'entrée L2 : ADG-01 FRANCHIE + EXP-001.yaml manifeste signé.
Contrat de sortie L2 : Dataset certifié + CRI >= 90 + Evidence >= Strong sur H1+H2+H3 + Go opérateur.

---

## Niveau 3 — Scientific Governance  [EMBRYONNAIRE — 10/100]

### Mission
Infrastructure institutionnelle pour gérer la connaissance scientifique accumulée :
traçabilité, reproductibilité, audit, détection des dérives, rapport de maturité.

### Maturité L3

```
Maturity 0 : Gouvernance logicielle uniquement (governance/ existant — couches EIC/ATC)
     ↓
Maturity 1 : G-01 + G-02 opérationnels (DataQualityMonitor + StatPower)
     ↓
Maturity 2 : G-01→G-05 opérationnels (monitoring + lineage + drift)
     ↓
Maturity 3 : G-01→G-10 opérationnels (audit complet automatisé)
     ↓
Maturity 4 : Premier ScientificAuditReport généré et validé par l'opérateur
```

### 10 G-modules (vision — à créer post-gate ADG-02)

| ID | Module | Fichier cible | Fonction |
|---|---|---|---|
| G-01 | DataQualityMonitor | governance/science/dq_monitor.py | Surveille les métriques DG-xxx en temps réel |
| G-02 | StatPowerCalculator | governance/science/stat_power.py | Calcule la puissance statistique atteinte |
| G-03 | HypothesisConflictDetector | governance/science/conflict_detector.py | Détecte H_i↔H_j contradictoires |
| G-04 | EvidenceLevelTracker | governance/science/evidence_tracker.py | Trace l'évolution des evidence_level |
| G-05 | ExperimentLineageVerifier | governance/science/lineage_verifier.py | Vérifie la filiation des datasets |
| G-06 | DatasetDriftDetector | governance/science/drift_detector.py | Détecte le drift entre datasets successifs |
| G-07 | CRICalculator | governance/science/cri_calculator.py | CRI automatisé à chaque N%50 |
| G-08 | ScientificAuditReport | governance/science/audit_report.py | Rapport Markdown complet à la demande |
| G-09 | GoNoGoEngine | governance/science/go_no_go_engine.py | Moteur décisionnel automatique (recommande) |
| G-10 | PMIUpdater | governance/science/pmi_updater.py | Met à jour le PMI et CLAUDE.md |

### Gate ADG-03
Contrat d'entrée L3 : ADG-02 FRANCHIE.
Contrat de sortie L3 : G-01→G-10 opérationnels + au moins une Release scientifique validée.

---

## Niveau 3.5 — Scientific Intelligence Layer  [CIBLE — 0/100]

### Mission
Transformer les observations et artefacts certifiés du DIP en connaissance
scientifique structurée. L3.5 ne crée pas de nouvelles fonctionnalités de
trading : il crée le langage qui relie décisions, causes, hypothèses, datasets,
evidence, confiance, conclusions et expériences recommandées.

Référence normative : `docs/dip/SCIENTIFIC_INTELLIGENCE_LAYER.md`.
ADR fondatrice : `docs/adr/0008-scientific-intelligence-layer.md`.

### Maturité L3.5

```
Maturity 0 : Spécification publiée (ADR-0008 + spec L3.5)
     ↓
Maturity 1 : Sources fiables (Observer Certification Level 3 + dataset CERTIFIED/PASS)
     ↓
Maturity 2 : Decision Knowledge Graph initial (SI-01)
     ↓
Maturity 3 : Evidence Engine + Contradiction Detector opérationnels (SI-03 + SI-05)
     ↓
Maturity 4 : Première Knowledge Release validée par l'opérateur
```

### 8 moteurs SI (vision — passifs)

| ID | Moteur | Fonction |
|---|---|---|
| SI-01 | Decision Knowledge Graph | Relie Decision, RootCause, Hypothesis, Dataset, Evidence, Confidence, Conclusion, Experiment |
| SI-02 | Causal Memory | Accumule les motifs causaux récurrents et leur valeur empirique |
| SI-03 | Evidence Engine | Suit confirmations, contradictions, invalidations et niveaux d'evidence |
| SI-04 | Scientific Timeline | Visualise l'évolution temporelle de la connaissance |
| SI-05 | Contradiction Detector | Détecte les hypothèses incompatibles ou bloquantes |
| SI-06 | Knowledge Confidence | Mesure la confiance dans la connaissance produite |
| SI-07 | Scientific Drift | Détecte le vieillissement ou la dégradation d'une conclusion |
| SI-08 | Decision DNA | Encode les décisions en séquences comparables |

### Gate ADG-03.5
Contrat d'entrée L3.5 : ADG-03 FRANCHIE + Observer Certification Level 3.
Contrat de sortie L3.5 : SI-01→SI-08 spécifiés, SI-01/SI-03/SI-05 opérationnels,
première Knowledge Release append-only validée par l'opérateur.

---

## Niveau 4 — Research Lab  [NON DÉMARRÉ — 0/100]

### Mission
Laboratoire quantitatif avec génération automatique d'hypothèses, backtesting
sur données historiques certifiées, simulation Monte Carlo.

### Maturité L4

```
Maturity 0 : Aucun outil de recherche
     ↓
Maturity 1 : Backtester opérationnel sur datasets certifiés
     ↓
Maturity 2 : Monte Carlo + Walk Forward validation conformes
     ↓
Maturity 3 : Génération automatique d'hypothèses testables
     ↓
Maturity 4 : Première hypothèse auto-générée confirmée (evidence_level >= Moderate)
```

### Prérequis stricts
- Gate ADG-03.5 FRANCHIE
- N >= 500 trades certifiés (backtesting significatif)
- hypothesis_quality.yaml : >= 2 évaluations par hypothèse principale

### Modules prévus
```
research/hypothesis_generator.py  — propose H_new basées sur les résidus d'erreur
research/backtester.py            — backtesting sur datasets certifiés (jamais live)
research/monte_carlo.py           — simulation distribution des outcomes
research/regime_lab.py            — Axe 2 : taxonomie hiérarchique des régimes
research/alpha_decay_tracker.py   — mesure la durée de vie des hypothèses confirmées
```

### Gate ADG-04
Contrat d'entrée L4 : ADG-03.5 FRANCHIE + N >= 500 trades certifiés.
Contrat de sortie L4 : Backtests + Walk Forward conformes + hypothèse auto-générée validée.

---

## Niveau 5 — Digital Twin  [NON DÉMARRÉ — 0/100]

### Mission
Jumeau numérique complet du système : replay temps réel, shadow mode,
A/B testing de configurations, stress testing sur scénarios extrêmes.

### Maturité L5

```
Maturity 0 : Aucune simulation
     ↓
Maturity 1 : Replay déterministe sur datasets certifiés
     ↓
Maturity 2 : Twin exécuté en parallèle du live (shadow passif)
     ↓
Maturity 3 : A/B testing de configurations sur historique certifié
     ↓
Maturity 4 : Twin reproduit les métriques live à ± 5% sur 30 jours
```

### Prérequis stricts
- Gate ADG-04 FRANCHIE
- Modèle de marché calibré (N >= 1000 trades certifiés)

### Architecture cible
```
digital_twin/
  ├── market_simulator.py      — simulation OHLCV avec régime injecté
  ├── twin_engine.py           — clone du DecisionEngine (version gelée)
  ├── shadow_runner.py         — exécution parallèle twin vs live (passive)
  ├── ab_tester.py             — compare config A vs B sur historique certifié
  └── stress_tester.py         — scénarios extrêmes (krach, flash crash)
```

**Invariant ADR-0007 étendu :** le Digital Twin ne peut jamais interagir avec l'engine live.
Il est observateur passif sur le DecisionEventBus.

### Gate ADG-05
Contrat d'entrée L5 : ADG-04 FRANCHIE.
Contrat de sortie L5 : Shadow Trading validé — twin à ± 5% sur 30 jours consécutifs.

---

## Niveau 6 — Live Operations  [PARTIEL — 36/100]

### Mission
Trading réel progressif avec monitoring temps réel, alertes, failsafe, et
progression contrôlée du capital déployé.

### Maturité L6

```
Maturity 0 : Paper trading uniquement
     ↓ [actuel]
Maturity 1 : Monitoring complet (Dashboard + Alerting opérationnels)
     ↓ [gate ADG-02]
Maturity 2 : Phase A — $50 capital réel (Go/No-Go positif)
     ↓ [30j Phase A + PF >= 1.3]
Maturity 3 : Phase B — $200 capital réel
     ↓ [90j Phase B + DD < 5%]
Maturity 4 : Phase C — capital total
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

### Composants manquants pour Maturity 4
| Composant | Prérequis |
|---|---|
| LiveMonitorDashboard | gate S1 |
| AlertingEngine (drawdown/stall) | gate S1 |
| Capital réel Phase A | gate ADG-02 |
| PositionReconciler live | gate ADG-02 |
| Levier dynamique | gate ADG-04 (interdit avant) |

### Gate ADG-06
Contrat d'entrée L6 Phase A : ADG-02 FRANCHIE + Go opérateur.
Contrat de sortie Phase A→B : 30 jours live + PF >= 1.3 + capital protégé.

### Gate ADG-07
Contrat d'entrée Phase B→C : 90 jours Phase B + DD < 5% + performance stable.

---

## Niveau 7 — Scientific Intelligence Core  [VISION — 0/100]

### Mission
Produire des connaissances fiables sur le comportement du moteur de décision,
les maintenir dans le temps, détecter leur vieillissement, proposer des
expériences et signaler les contradictions scientifiques.

Le trading reste un cas d'usage. Le coeur L7 vise une plateforme scientifique
d'analyse décisionnelle réutilisable.

### Maturité L7

```
Maturity 0 : Aucun core scientifique intégré
     ↓
Maturity 1 : Scientific Knowledge Graph opérationnel
     ↓
Maturity 2 : Evidence Engine + Scientific Memory + Drift actifs
     ↓
Maturity 3 : Research Planner + Experiment Generator validés par l'opérateur
     ↓
Maturity 4 : Première release scientifique multi-dataset validée
```

### Prérequis stricts
- Gates ADG-05 + ADG-07 FRANCHIES
- N >= 2000 trades certifiés en live

### Composition cible

```
Scientific Intelligence Core =
  Knowledge Graph
  + Evidence Engine
  + Scientific Memory
  + Research Planner
  + Experiment Generator
  + Contradiction Detector
  + Knowledge Confidence
  + Scientific Drift
  + Observer Certification
  + Dataset Certification
  + Hypothesis Engine
```

### Invariant L7
`FEATURE_AUTO_CALIBRATION=true` n'est autorisé qu'ici, avec ADR signé par l'opérateur.
C'est le seul contexte où l'engine peut recevoir une influence externe automatisée,
et seulement après validation opérateur explicite.

---

## Architecture Decision Gates (ADG)

Chaque transition entre niveaux est contrôlée par un contrat formel ADG.
**Aucune progression sans gate verte.**

| Gate | Transition | Contrat d'entrée | Contrat de sortie |
|---|---|---|---|
| ADG-01 | Engineering → Validation | Infrastructure trading minimale | Tests verts + ADR-0007 + observabilité câblée |
| ADG-02 | Validation → Governance | EXP-001 manifeste signé | Dataset certifié + CRI >= 90 + Evidence >= Strong + Go opérateur |
| ADG-03 | Governance → Scientific Intelligence | ADG-02 verte | G-01→G-10 + Release scientifique validée |
| ADG-03.5 | Scientific Intelligence → Research Lab | ADG-03 + Observer Certification Level 3 | SI-01/SI-03/SI-05 opérationnels + Knowledge Release validée |
| ADG-04 | Research → Digital Twin | ADG-03.5 + N >= 500 | Backtests + Walk Forward conformes |
| ADG-05 | Twin → Live ops réelles | ADG-04 | Shadow trading ± 5% sur 30j |
| ADG-06 | Live Phase A → B | ADG-02 + Go opérateur | 30j live + PF >= 1.3 + capital protégé |
| ADG-07 | Live Phase B → C | ADG-06 | 90j + DD < 5% + performance stable plusieurs mois |

**ADG-01 est la seule gate franchie.** ADG-02 est le blocant actuel.

---

## PMI — Project Maturity Index

### Double lecture

Le PMI se lit sur deux axes indépendants :

| Score | Signification | Baseline 2026-06-30 |
|---|---|---|
| **PMI-7 Capability Score** | Ce que le système est capable de faire dans l'ancien référentiel 7 niveaux | 181 / 700 = 26% |
| **PMI-7 Evidence Score** | Ce qui a été démontré par les données | 0 / 700 = 0% |
| **SDOS Capability Score** | Même lecture, mais avec L3.5 ajouté au dénominateur | 181 / 800 = 22.6% |

```
Capability Score = (L1_cap + L2_cap + L3_cap + L4_cap + L5_cap + L6_cap + L7_cap) / 700
Evidence Score   = (L1_ev  + L2_ev  + L3_ev  + L4_ev  + L5_ev  + L6_ev  + L7_ev)  / 700
SDOS Capability  = (L1_cap + L2_cap + L3_cap + L3_5_cap + L4_cap + L5_cap + L6_cap + L7_cap) / 800
```

**Capability** progresse en livrant des outils, des gates, des modules.
**Evidence** progresse uniquement quand des données certifiées confirment ou infirment une hypothèse.

Aujourd'hui : PMI-7 Capability = 26%, SDOS Capability = 22.6%, Evidence = 0%.
Le projet avance sur les deux axes en parallèle mais de manière indépendante.
L'architecture mature peut coexister avec zéro preuve scientifique — c'est l'état actuel.

### Historique

| Date | Cap | Ev | Notes |
|------|-----|-----|-------|
| 2026-06-30 | 181/700 | 0/700 | Baseline — architecture complète, aucune donnée certifiée |
| 2026-07-01 | 181/800 | 0/800 | Rebaseline SDOS — ajout L3.5, aucune régression de capacité |

### Règle de mise à jour
Le PMI Capability se met à jour à chaque franchissement de gate.
Le PMI Evidence se met à jour à chaque certification de dataset (N >= seuil) ou conclusion d'hypothèse.
Le SDOS Capability inclut L3.5 et se met à jour avec les gates SI.
**Les scores avancent avec les données et les gates, jamais avec le code ajouté seul.**

---

## Roadmap Horizons

### H1 — 0 à 3 mois : Validation Scientifique

**Objectif :** franchir ADG-02. Accumuler les données. Prouver l'edge.

```
Maintenant       : accumulation passive (VPS actif, paper MEXC)
Gate S1 (N=30)   : dataset_certifier.py → CERT-2026-Q3-001
                   → L2 Maturity 0 → 1
Gate S2 (N=50)   : statistical_readiness.py exit 0
Gate S3 (N=100)  : cri_calculator.py → CRI >= 90
Gate S4 (N=100)  : hypothesis_tester.py → H1+H2+H3 concluantes
Gate S5 (N=100)  : go_no_go.py → GO ou NO-GO
                   → L2 Maturity 4
```

Livrables à créer : `tools/statistical_readiness.py`, `tools/cri_calculator.py`,
`analysis/hypothesis_tester.py`, `tools/go_no_go.py`.

### H2 — 3 à 9 mois : Scientific Governance + Scientific Intelligence

**Objectif :** franchir ADG-03 puis ADG-03.5. Gouvernance scientifique opérationnelle,
puis première couche de connaissance scientifique.

```
G-01→G-10        : governance/science/ (post ADG-02)
                   → L3 Maturity 3 → 4
SI-01/SI-03/SI-05: Knowledge Graph + Evidence + Contradictions (post ADG-03)
                   → L3.5 Maturity 2 → 4
Research Lab     : backtester + Monte Carlo (post ADG-03.5, N >= 500)
                   → L4 Maturity 1 → 2
Live Phase A     : $50 capital réel (post ADG-02)
                   → L6 Maturity 2
```

### H3 — 9 à 18 mois : Production Institutionnelle

**Objectif :** franchir ADG-05/ADG-07. Système stable en production réelle.

```
Digital Twin     : shadow mode + A/B testing (post ADG-04)
                   → L5 Maturity 3 → 4
Live Phase B+C   : capital total (post ADG-06 → ADG-07)
                   → L6 Maturity 4
Scientific Core  : Knowledge Graph + Evidence Engine + Scientific Memory (post ADG-07)
                   → L7 Maturity 1 → 2
```

---

## Principes architecturaux invariants

1. **ADR-0007 Passivité absolue** : observabilité, gouvernance, lab, twin = passifs.
   L'engine de trading est le seul à décider.

2. **Scientific Debt Rule** : zéro feature sans hypothèse préexistante.

3. **Immutabilité scientifique** : dataset référencé par une expérience close = immuable.
   Les corrections créent un nouveau UUID.

4. **Evidence-first** : aucun paramètre modifié sans p-value + n + effect size documentés.

5. **Séquentialité des ADG** : L4/L5/L7 ne démarrent pas avant ADG-02 verte.
   L4 nécessite désormais ADG-03.5.

6. **FEATURE_AUTO_CALIBRATION=false** : défaut permanent. Seul L7 peut l'activer,
   avec ADR signé par l'opérateur.

7. **Cohérence Mission** : toute nouvelle idée est évaluée d'abord contre
   `docs/mission_statement.md`, pas contre sa faisabilité technique.

8. **Knowledge Confidence distinct de l'OCS** : l'OCS mesure la confiance dans
   l'observateur ; L3.5 mesure la confiance dans la connaissance produite.
