# DIP — Decision Intelligence Platform
## Manual of Operations v1.0

> Document permanent — mis à jour à chaque évolution certifiée du DIP.
> Ce n'est pas un document de conception. C'est la référence opérationnelle.
>
> Baseline : 2026-06-30 | Modules : D01–D14 | Tests : 136 | PMI-7 : 181/700 | SDOS : 181/800

---

## Table des matières

1. [Architecture](#1-architecture)
2. [Flux de données](#2-flux-de-données)
3. [Protocole d'investigation](#3-protocole-dinvestigation)
4. [Rapports standard](#4-rapports-standard)
5. [Référence CLI](#5-référence-cli)
6. [SLA de performance](#6-sla-de-performance)
7. [Certification et évolution](#7-certification-et-évolution)
8. [Connexion production](#8-connexion-production)
9. [DIP Capability Matrix](#9-dip-capability-matrix)
10. [SDOS et Scientific Intelligence](#10-sdos-et-scientific-intelligence)

---

## 1. Architecture

### Principe fondateur (ADR-0007)

Le DIP est **strictement passif**. Il ne peut jamais modifier, intercepter,
retarder ou filtrer un `DecisionPacket`. Il observe, enregistre, explique.
Toute évolution qui violerait ce principe est rejetée sans discussion.

### Composants principaux

```
observability/decision_event_bus.py   ← Bus existant (moteur)
     │
     │  subscribe (lecture seule)
     ▼
dip/core/observer.py   DIPObserver    ← Singleton abonné au bus
     │
     │  dispatch vers handlers enregistrés
     ▼
dip/modules/                          ← D01–D14 (handlers)
     │
     ▼
dip/core/store.py   DIPStore          ← SQLite WAL (append-only)
     │
     ▼
dip/cli.py                            ← Interface opérateur
```

### Modules D01–D14

| ID  | Module                  | Fichier                          | Rôle |
|-----|-------------------------|----------------------------------|------|
| D01 | Decision Graph          | `modules/decision_graph.py`      | DAG décisionnel, couches traversées, confidence flow |
| D02 | Decision Timeline       | `modules/decision_timeline.py`   | Chronologie temporelle par couche |
| D03 | Causal Tree             | `modules/causal_tree.py`         | Arbre causal, cause racine, facteurs contributifs |
| D04 | Counterfactual Engine   | `modules/counterfactual.py`      | Simulation "que se passerait-il si…" |
| D05 | Explainability Score    | `modules/explainability.py`      | Score 5 dimensions [0,1], grade A–F |
| D06 | Heatmap                 | `modules/decision_heatmap.py`    | Taux de rejet par (symbol × layer) ou (regime × layer) |
| D07 | Replay Engine           | `modules/decision_replay.py`     | Replay step-by-step, mode interactif |
| D08 | Sankey                  | `modules/decision_sankey.py`     | Funnel décisionnel, goulots d'étranglement |
| D09 | Knowledge Base          | `modules/knowledge_base.py`      | Patterns statistiques (N≥50), règles d'association |
| D10 | AI Investigator         | `modules/ai_investigator.py`     | Narrative IA (claude-sonnet-4-6), fallback template |
| D11 | Decision Diff           | `modules/decision_diff.py`       | Comparaison side-by-side de deux décisions |
| D12 | Alert Engine            | `modules/decision_alert.py`      | 5 règles (R01–R05), cooldown 5 min, sévérité HIGH/CRITICAL |
| D13 | Export Engine           | `modules/decision_export.py`     | Export JSON / CSV / Markdown |
| D14 | Audit Trail             | `modules/audit_trail.py`         | Journal append-only SHA-256, hash-chain |

### Couche L3.5 — Scientific Intelligence Layer

Les modules D01-D14 restent des outils d'observation et d'investigation. Le
niveau L3.5 définit le langage scientifique qui transforme leurs sorties en
connaissance structurée : Decision → RootCause → Hypothesis → Dataset → Evidence
→ Confidence → ScientificConclusion → RecommendedExperiment.

Références :
- `docs/adr/0008-scientific-intelligence-layer.md`
- `docs/dip/SCIENTIFIC_INTELLIGENCE_LAYER.md`
- `docs/blueprint_v2.md`

L3.5 n'ajoute aucun handler au bus et ne modifie jamais le moteur. C'est une
couche passive de compréhension.

### Stockage

```
databases/dip/dip.sqlite   (SQLite WAL, append-only)
│
├── dip_decisions           ← Index de chaque DecisionObservation
├── dip_observations        ← Données brutes par module
├── dip_alerts              ← Alertes D12
├── dip_knowledge           ← Patterns D09
├── dip_audit_trail         ← Journal D14
└── dip_counterfactuals     ← Simulations D04
```

---

## 2. Flux de données

### Chemin nominal d'une observation

```
advisor_loop.py
    │
    │  _decision_event_bus.publish(obs)          ← déjà en prod
    ▼
DecisionEventBus (observability/)
    │
    │  bus.subscribe(DIPObserver._on_observation) ← start_dip() à appeler
    ▼
DIPObserver._on_observation(obs)
    │
    ├─► D01 GraphEngine.on_observation(obs)       ← construit le DAG
    │       └─► DIPStore.upsert_decision()
    │
    ├─► D02 TimelineEngine.on_observation(obs)    ← chronologie
    │
    ├─► D03 CausalTreeEngine.on_observation(obs)  ← cause racine
    │       └─► lit le graph D01
    │
    ├─► D05 ExplainabilityEngine.on_observation() ← score 5D
    │       └─► lit graph D01 + causal D03
    │
    ├─► D09 KnowledgeBase.on_observation(obs)     ← accumule patterns
    │
    ├─► D12 AlertEngine.on_observation(obs)       ← vérifie R01–R05
    │       └─► DIPStore.insert_alert() si déclenchée
    │
    └─► D14 AuditTrail (lambda bootstrap)         ← log immuable
```

### Modules à la demande (non-temps-réel)

Ces modules sont appelés explicitement via CLI ou via code :

- **D04** Counterfactual — calcul à la demande (`engine.simulate_without_layer()`)
- **D06** Heatmap — agrégation sur fenêtre horaire (`engine.generate_symbol_layer_heatmap()`)
- **D07** Replay — session interactive (`engine.build_replay()`)
- **D08** Sankey — funnel agrégé (`engine.generate_sankey()`)
- **D10** AI Investigator — investigation narrative (`engine.investigate()`)
- **D11** Diff — comparaison deux packets (`engine.diff()`)
- **D13** Export — rapport JSON/CSV/MD (`engine.export_json()`)

---

## 3. Protocole d'investigation

Chaque investigation suit ce protocole. Aucune improvisation.

### INV-XXX — Template standard

```
INV-{numéro}   {date}   {symbole}   {packet_id[:8]}
```

**Étape 1 — Vérifier le graph**
```bash
python -m dip graph <packet_id>
```
→ Identifier la couche bloquante, le delta de confiance.

**Étape 2 — Identifier la cause racine**
```bash
python -m dip causal <packet_id>
```
→ Confirmer `causing_layer`, lire `description`, vérifier `confidence`.

**Étape 3 — Mesurer l'explicabilité**
```bash
python -m dip explain <packet_id>
```
→ Score < 0.6 = investigation insuffisante, relancer avec D10.

**Étape 4 — Simuler le contrefactuel**
```bash
python -m dip counterfactual <packet_id> --layer <layer>
```
→ Si `outcome_changed=OUI` : la couche est causalement responsable.
→ Si `outcome_changed=NON` : chercher upstream.

**Étape 5 — Replay pour confirmation**
```bash
python -m dip replay <packet_id>
```
→ Vérifier la séquence step-by-step. Annoter les étapes anormales.

**Étape 6 — Investigation narrative (si nécessaire)**
```bash
python -m dip investigate <packet_id>
```
→ Utilise l'IA uniquement si les étapes 1–5 restent ambiguës.
→ Résultat = OBSERVATION, jamais une décision de calibration.

**Étape 7 — Export**
```bash
python -m dip export <packet_id> --output investigations/INV-XXX.md
```

**Critères de clôture :**
- [ ] Cause racine identifiée avec confiance ≥ 0.7
- [ ] Counterfactuel confirme la responsabilité causale
- [ ] Explainability score ≥ 0.6
- [ ] Aucune calibration sans CRI ≥ 90 et N ≥ 500 (règle statisticien)

---

## 4. Rapports standard

Le DIP produit 8 rapports standardisés. Chaque rapport est reproductible.

| Rapport | Commande | Fréquence recommandée |
|---------|----------|-----------------------|
| Decision Report (MD) | `python -m dip report --format md` | Quotidien |
| Root Cause Summary | `python -m dip causal <id>` | Par trade suspect |
| Layer Heatmap (7j) | `python -m dip heatmap --hours 168` | Hebdomadaire |
| Sankey Funnel (24h) | `python -m dip sankey --hours 24` | Quotidien |
| Replay Report | `python -m dip replay <id>` | Par investigation |
| Counterfactual Report | `python -m dip counterfactual <id>` | Par investigation |
| Explainability Report | `python -m dip explain <id>` | Par investigation |
| Audit Trail (24h) | `python -m dip audit --hours 24` | Quotidien |

### Rapport quotidien automatisé (cible)

```bash
# À exécuter chaque matin sur VPS
python -m dip report --format md --hours 24 --output reports/daily_$(date +%Y%m%d).md
python -m dip heatmap --hours 24
python -m dip alerts
python -m dip metrics --hours 24
```

---

## 5. Référence CLI

Point d'entrée : `python -m dip <commande> [options]`

### Commandes d'investigation

```
graph <packet_id>
    Affiche le DAG décisionnel : couches traversées, statuts, confidence flow.
    Identifie le bloqueur principal.

causal <packet_id>
    Arbre causal : cause racine (causing_layer), facteurs contributifs,
    confiance de la cause.

explain <packet_id>
    Score d'explicabilité sur 5 dimensions (causal_clarity, confidence_drop,
    reasoning_coverage, layer_attribution, reasoning_readability).
    Grade A (≥0.9) à F (<0.4).

counterfactual <packet_id> [--layer <layer>]
    Simulation "sans cette couche". Retourne outcome_changed, confidence_delta,
    estimated_pnl_impact. Confiance max = 0.85 (jamais certitude).

replay <packet_id> [--step]
    Replay linéaire (défaut) ou interactif (--step).
    Mode interactif : ENTER=suivant, b=précédent, B=sauter au bloqueur, q=quitter.

investigate <packet_id>
    Investigation narrative (claude-sonnet-4-6, temperature=0.0).
    Fallback template si LLM indisponible.
    Résultat = OBSERVATION — jamais une décision.

diff <packet_id_a> <packet_id_b>
    Comparaison side-by-side. Identifie la couche de divergence,
    les deltas de confiance, les changements de contexte.
```

### Commandes agrégées

```
heatmap [--hours 168] [--type symbol|regime]
    Heatmap des taux de rejet par (symbol × layer) ou (regime × layer).
    Identifie hot spots et cold spots.

sankey [--hours 24] [--symbol BTCUSDT]
    Funnel décisionnel : taux de conversion par couche, biggest_bottleneck.

alerts [--severity HIGH|CRITICAL]
    Liste les alertes actives. 5 règles :
      R01 — Burst rejet >80% sur 10 obs
      R02 — Layer z-score >3 sigma
      R03 — Spike rejet global >50%
      R04 — Explainability faible (<0.4)
      R05 — Instabilité régime (>5 changements / 30 min)
```

### Commandes de reporting

```
report [--hours 168] [--format json|csv|md] [--output <fichier>]
    Rapport complet : résumé, par statut, par layer, par régime.

export <packet_id> [--output <fichier>]
    Export complet d'un packet : graph JSON, causal tree, audit trail,
    counterfactuals.

audit [--hours 24]
    Journal d'audit DIP : entrées par module et par action.
    Contrôle d'intégrité SHA-256.
```

### Commandes de santé

```
kb [--symbol BTCUSDT] [--regime SIDEWAYS] [--drift]
    Knowledge Base : patterns (N≥50), règles d'association,
    détection de dérive.

health
    État du DIP : décisions indexées, alertes actives, entries KB.

metrics [--hours 24]
    Métriques agrégées : taux approbation/rejet, top couches bloquantes.
```

---

## 6. SLA de performance

Mesurés sur données réelles. À valider lors de la certification.

| Opération | SLA cible | Mesure actuelle |
|-----------|-----------|-----------------|
| `on_observation()` complet (D01+D03+D05) | < 50 ms | Non mesuré (0 trades réels) |
| `get_graph()` depuis cache SQLite | < 10 ms | — |
| `build_causal_tree()` | < 30 ms | — |
| `compute_score()` explainability | < 20 ms | — |
| `simulate_without_layer()` counterfactual | < 500 ms | — |
| `generate_symbol_layer_heatmap()` 168h | < 2 s | — |
| `generate_sankey()` 24h | < 1 s | — |
| `build_replay()` | < 200 ms | — |
| `investigate()` LLM | < 30 s | — |
| `investigate()` template fallback | < 100 ms | — |

> **Note** : les SLA ne peuvent être certifiés qu'après accumulation de données
> de production. Cible minimale : N ≥ 500 décisions (cohérent avec la règle statisticien).

---

## 7. Certification et évolution

### Checklist avant tout commit DIP

```
[ ] Tests verts (python -m pytest tests/dip/ -v)
[ ] Architecture respectée (DIP passif — zéro write dans le moteur)
[ ] ADR-0007 respectée (lecture seule)
[ ] ADR-0015 respectée (append-only DIPStore)
[ ] Pas de dépendance circulaire
[ ] Pas de modification du moteur (DecisionPacket, advisor_loop, etc.)
[ ] SLA de performance respectés
[ ] Documentation mise à jour (ce manuel)
[ ] Rollback possible (module supprimable sans casser le reste)
```

### Rapport post-commit obligatoire

```
Résumé      : [une phrase — ce qui a changé]
Pourquoi    : [hypothèse H1-H6 qui justifie le changement]
Ajouté      : [liste des fichiers nouveaux]
Non modifié : [liste des modules moteur confirmés intacts]
Tests       : [N tests / N passés]
Performance : [mesures avant/après si applicable]
Risques     : [risques identifiés et mitigation]
Restant     : [travail restant]
Prochaine phase : [description de la suite]
```

### Règle Scientific Debt appliquée au DIP

Toute nouvelle fonctionnalité DIP doit pointer vers :
- une hypothèse H1-H6 existante, **ou**
- un besoin de mesure/audit directement lié aux données de production.

Interdiction d'ajouter un module DIP "parce que ce serait utile".

---

## 8. Connexion production

### État actuel

Le `advisor_loop.py` publie déjà les `DecisionObservation` sur le `DecisionEventBus`
(lignes ~5540-5555). Le `DIPObserver` est prêt à s'abonner via `start_dip()`.

**Il manque une seule ligne dans `advisor_loop.py`** pour activer le DIP en production :

```python
# Dans advisor_loop.py — bloc FEATURE_EVENT_BUS (~ligne 3709)
# Après _decision_event_bus = _get_obs_bus()

if FEATURE_DIP:                        # nouvelle feature flag
    from dip.bootstrap import start_dip
    start_dip()
```

### Feature flag recommandée

```bash
# .env / config VPS
FEATURE_DIP=true
```

Valeur par défaut : `false` (sécurité — activation explicite requise).

### Vérification post-activation

```bash
# Sur VPS, après un cycle de trading :
python -m dip health
python -m dip metrics --hours 1
```

Si `Décisions indexées > 0` : le DIP reçoit bien les données.

---

## 9. DIP Capability Matrix

Mise à jour à chaque session. Référence opérationnelle de l'état réel du DIP.

### Légende

| Symbole | Signification |
|---------|---------------|
| ✅ | Complet et vérifié |
| ⏳ | En attente de données / validation |
| ❌ | Non démarré / non applicable |

### Matrice au 2026-06-30

| Module | Implémenté | Testé | Intégré bus | En prod VPS | Certifié sur données réelles | Utilisé en investigation |
|--------|:----------:|:-----:|:-----------:|:-----------:|:----------------------------:|:------------------------:|
| D01 Decision Graph | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| D02 Decision Timeline | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| D03 Causal Tree | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| D04 Counterfactual | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D05 Explainability | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| D06 Heatmap | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D07 Replay | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D08 Sankey | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D09 Knowledge Base | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| D10 AI Investigator | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D11 Decision Diff | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D12 Alert Engine | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| D13 Export Engine | ✅ | ✅ | ❌ (à la demande) | ⏳ | ❌ | ❌ |
| D14 Audit Trail | ✅ | ✅ | ✅ | ⏳ | ❌ | ❌ |
| **CLI** | ✅ | ✅ | — | ⏳ | — | ❌ |

### Progression vers certification

```
Evidence Score DIP = 0/14 modules certifiés sur données réelles

Prochain gate : FEATURE_DIP=true sur VPS → N ≥ 50 décisions indexées
Gate certification : N ≥ 500 décisions (cohérent règle statisticien CLAUDE.md)
```

### Historique des mises à jour de la matrice

| Date | Événement | Changement matrice |
|------|-----------|--------------------|
| 2026-06-30 | D01-D14 implémentés, 136 tests verts | Baseline |

---

## 10. SDOS et Scientific Intelligence

Le DIP est désormais positionné comme le socle d'un **Scientific Decision
Operating System (SDOS)**. Le moteur de trading reste le premier cas d'usage, mais
l'objectif architectural plus durable est de produire des connaissances fiables
sur un système de décision.

### Question cible

Avant L3.5, le DIP répond principalement :

> Pourquoi cette décision a-t-elle été refusée ?

Avec L3.5, le SDOS doit pouvoir répondre :

> Que savons-nous réellement du comportement du moteur ?

### Moteurs L3.5

| ID | Moteur | Réponse attendue |
|----|--------|------------------|
| SI-01 | Decision Knowledge Graph | Quelle connaissance relie cette décision à une hypothèse ? |
| SI-02 | Causal Memory | Quels motifs causaux reviennent dans le temps ? |
| SI-03 | Evidence Engine | L'evidence s'accumule-t-elle, se contredit-elle ou s'affaiblit-elle ? |
| SI-04 | Scientific Timeline | Comment la connaissance a-t-elle évolué ? |
| SI-05 | Contradiction Detector | Deux conclusions confirmées sont-elles compatibles ? |
| SI-06 | Knowledge Confidence | Peut-on faire confiance à la connaissance produite ? |
| SI-07 | Scientific Drift | Une conclusion confirmée vieillit-elle avec le marché ? |
| SI-08 | Decision DNA | Quelles familles de décisions apparaissent ? |

### Distinction OCS / Knowledge Confidence

| Score | Question |
|-------|----------|
| Observer Confidence Score (OCS) | Peut-on faire confiance à l'observateur ? |
| Knowledge Confidence | Peut-on faire confiance à la connaissance produite ? |

### Règle opérationnelle

Tant que `SI-G1` n'est pas franchie (Observer Certification Level 3 + dataset
CERTIFIED/PASS), L3.5 reste une architecture cible et ne produit aucune conclusion
scientifique utilisable dans un Go/No-Go.

---

## Annexe A — Rollback complet du DIP

Le DIP est conçu pour être supprimable sans impact sur le moteur.

**Procédure de rollback :**

1. Retirer `start_dip()` de `advisor_loop.py` (si ajouté)
2. Supprimer `FEATURE_DIP=true` du `.env`
3. Supprimer `databases/dip/dip.sqlite`
4. Supprimer le dossier `dip/`
5. Supprimer `tests/dip/`

**Aucun module du moteur n'est modifié par le DIP.**
Le rollback ne crée aucune régression.

---

## Annexe B — Règles invariantes

Ces règles ne peuvent pas être overridées :

1. **ADR-0007** : DIP read-only. Jamais de write dans le moteur.
2. **ADR-0015** : DIPStore append-only. Jamais d'UPDATE/DELETE sur données.
3. **Scientific Debt Rule** : Zéro nouveau module sans hypothèse H1-H6 qui le justifie.
4. **Règle statisticien** : Zéro calibration sans N ≥ 500, CRI ≥ 90.
5. **Disclaimer D10** : Toute investigation IA porte la mention "OBSERVATION — pas une décision".

---

*Dernière mise à jour : 2026-07-01*
*Prochain révision attendue : après première activation FEATURE_DIP=true sur VPS*
