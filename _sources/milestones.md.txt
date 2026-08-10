# Milestones — crypto_ai_terminal
# Jalons officiels du projet. Immuables après signature.
# Référence normative : docs/blueprint_v2.md, docs/mission_statement.md

---

## M1 — Scientific Baseline Established

| Champ | Valeur |
|---|---|
| **Date** | 2026-06-30 |
| **Nom** | Scientific Baseline Established |
| **Git tag** | v0.9.0-baseline-scientific |
| **Commit** | f8fd3fe |
| **Blueprint** | V2.1 |
| **Mission Statement** | V1.0 |
| **Status** | FROZEN |
| **Next Objective** | Dataset Certification (gate S1) |

### Périmètre du gel

À partir de ce jalon, les composants suivants sont **gelés jusqu'à CRI >= 90 ET PMI L2 complet** :

- `core/advisor_loop.py`
- `core/decision_packet.py`
- `quant_hedge_ai/agents/intelligence/` (Conviction, MetaStrategy, PortfolioBrain)
- `quant_hedge_ai/agents/risk/` (Gate, RiskGovernor)
- Tous les seuils de décision (`score_threshold`, `pb_min`, paramètres RECOVERY)

**Autorisés exclusivement (conformes au Blueprint V2.1 Phase II) :**
outils de mesure S1→S5, tableaux de bord d'observation, rapport scientifique.

### Métriques au moment du jalon

| Métrique | Valeur |
|---|---|
| PMI Capability Score | 181 / 700 = 26% |
| PMI Evidence Score | 0 / 700 = 0% |
| Tests passants | 3463 / 3467 |
| Échecs préexistants identifiés | 4 (non régressés) |
| Hypothèses actives | H1, H2, H3, H4 (en attente de données) |
| N trades certifiés | 0 (accumulation en cours sur VPS) |
| CRI | N/A (N < seuil minimum) |

### Architecture livrée à ce jalon

| Module | Statut |
|---|---|
| DecisionEngine v9 (12 couches) | ✅ |
| DecisionEventBus (pub/sub) | ✅ |
| DecisionObservation (40+ champs) | ✅ |
| RejectionStore (JSONL atomic) | ✅ |
| RegretScheduler (7 horizons 5m→24h) | ✅ |
| DecisionExplainer (Telegram) | ✅ |
| Feature Flags (FEATURE_AUTO_CALIBRATION=false) | ✅ |
| Formal Governance (EIC_v2, ATC, DPSS, SEP, STI) | ✅ |
| Data Governance Spec v1.0 (24 DG-xxx) | ✅ |
| Dataset Certifier (CLI, DG-001→DG-024) | ✅ |
| Hypothesis Registry v1.1 (H1→H4) | ✅ |
| Experiment Registry EXP-001 (manifeste signé) | ✅ |
| Hypothesis Quality (Axe 1 Meta Science) | ✅ |
| CLAUDE.md (Constitution) | ✅ |
| Blueprint V2.1 (7 niveaux, ADG, Horizons) | ✅ |
| Mission Statement V1.0 | ✅ |

### Raison scientifique du gel

> Toute modification du moteur après le démarrage de l'accumulation de données
> invalide la comparabilité des observations. L'UUID du dataset `fb61deac` est lié
> à un état précis de l'architecture (commit `ff49c2a`, observabilité `6d250b7`).
> Modifier le moteur = créer un nouveau dataset, invalider EXP-001, recommencer.

---

## M1.1 — SDOS Architecture Rebaseline

| Champ | Valeur |
|---|---|
| **Date** | 2026-07-01 |
| **Nom** | SDOS Architecture Rebaseline |
| **Blueprint** | V2.2 |
| **Mission Statement** | V1.0 + SDOS |
| **ADR** | ADR-0008 |
| **Status** | ARCHITECTURE ONLY |
| **Next Objective** | Observer Certification puis dataset certification |

### Changement acté

Le projet est repositionné comme **Scientific Decision Operating System (SDOS)**.
Le trading reste le premier cas d'usage, mais l'identité durable devient la
production de connaissances fiables sur un moteur de décision.

### Ajout architectural

| Niveau | Nom | Score |
|---|---|---|
| L3.5 | Scientific Intelligence Layer | 0 / 100 |
| L7 | Scientific Intelligence Core | 0 / 100 |

### Métriques rebaselinées

| Métrique | Valeur |
|---|---|
| PMI-7 Capability Score | 181 / 700 = 26% |
| SDOS Capability Score | 181 / 800 = 22.6% |
| Evidence Score | 0 / 800 = 0% |
| Changement runtime | Aucun |
| Changement moteur | Aucun |

### Raison scientifique

Ce jalon ne livre pas une nouvelle fonctionnalité. Il fixe le langage de
connaissance qui permettra de relier Decision, RootCause, Hypothesis, Dataset,
Evidence, Confidence, ScientificConclusion et RecommendedExperiment.

---

## Jalons futurs prévus (non datés)

| Jalon | Condition | Description |
|---|---|---|
| M2 | gate S1 | Premier dataset certifié — `CERT-2026-Q3-001` obtenu |
| M3 | gate S3 | CRI >= 90 atteint |
| M4 | gate S5 | Go/No-Go EXP-001 — décision capital réel |
| M5 | ADG-02 + 30j live | Phase A capital réel validée |
| M6 | ADG-03 | Scientific Governance complète (G-01→G-10) |
| M6.5 | ADG-03.5 | Scientific Intelligence Layer — première Knowledge Release |
| M7 | ADG-07 | Live Operations Phase C — capital total |
