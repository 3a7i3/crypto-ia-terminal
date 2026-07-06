# Scientific Intelligence Layer - L3.5
## Specification v0.1

> Document de reference du niveau L3.5.
> Statut : architecture cible, zero effet runtime.
> Autorite : ADR-0007, ADR-0008, Data Governance Spec v1.0, Observer Certification Standard v1.0.

---

## 1. Mission

Le **Scientific Intelligence Layer** transforme les observations du DIP en
connaissance scientifique structurée.

Le DIP D01-D14 repond a des questions operationnelles :

- Que s'est-il passe ?
- Quelle couche a bloque ?
- Quelle est la cause racine ?
- Que donnerait un contrefactuel ?

L3.5 repond a une question plus haute :

> Que savons-nous reellement du comportement du moteur de decision ?

Ce niveau ne cherche pas a ajouter des fonctionnalites de trading. Il definit le
langage scientifique qui permettra de relier decisions, causes, hypotheses,
datasets, evidence, confiance et experiences recommandees.

---

## 2. Position dans l'architecture

```
L4    Research Lab                  genere de nouvelles hypotheses testables
      ^
      |
L3.5  Scientific Intelligence Layer  structure la connaissance produite
      ^
      |
L3    Scientific Governance          certifie donnees, observateur, lineage
      ^
      |
DIP   D01-D14                        observe, explique, rejoue, exporte
      ^
      |
Engine de decision                   produit les DecisionObservation
```

L3.5 consomme uniquement des artefacts deja produits ou certifies :

- DecisionObservation
- DecisionGraph
- CausalTree
- DecisionTimeline
- CounterfactualResult
- KnowledgeEntry D09
- CertifiedDataset
- HypothesisResult
- ObserverCertification

Il ne publie jamais vers le moteur de decision.

---

## 3. Non-objectifs

L3.5 ne doit pas :

- ajouter une strategie de trading ;
- ajouter un indicateur technique ;
- modifier un seuil ;
- activer l'auto-calibration ;
- envoyer un ordre ;
- remplacer la validation operateur ;
- conclure une hypothese sans dataset certifie ;
- produire une recommandation d'action sans niveau d'evidence explicite.

---

## 4. Langage scientifique commun

Le graphe logique cible est :

```
Decision
  -> RootCause
  -> Hypothesis
  -> Dataset
  -> Evidence
  -> Confidence
  -> ScientificConclusion
  -> RecommendedExperiment
```

### Primitives

| Primitive | Definition |
|-----------|------------|
| Decision | Une decision observee par le moteur, identifiee par `packet_id` |
| RootCause | Cause causale principale issue de D03 |
| Hypothesis | Enonce falsifiable versionne, issu de `analysis/hypothesis_registry.yaml` |
| Dataset | Donnees certifiees, tracées par UUID et certification ID |
| Evidence | Niveau empirique Weak, Moderate, Strong, VeryStrong, plus confirmations et contradictions |
| Confidence | Confiance dans la connaissance, distincte de la confiance de decision |
| ScientificConclusion | Synthese falsifiable : Confirmed, Rejected, Inconclusive, Contradicted ou Stale |
| RecommendedExperiment | Experience proposee pour reduire l'incertitude restante |

---

## 5. Moteurs SI-01 a SI-08

### SI-01 - Decision Knowledge Graph

**But :** relier les decisions individuelles aux hypotheses, datasets et
conclusions scientifiques.

**Sortie cible :**

```yaml
knowledge_edge:
  decision_id: "<packet_id>"
  root_cause_layer: "meta_strategy"
  hypothesis_id: "H3"
  dataset_uuid: "<uuid>"
  evidence_level: "Moderate"
  confidence: 0.71
  conclusion_id: "SC-2026-0001"
  recommended_experiment: "EXP-002"
```

### SI-02 - Causal Memory

**But :** transformer les motifs repetes en memoire causale.

Exemple de connaissance cible :

```yaml
causal_memory:
  pattern: "SELL + bear_trend + ATR>2 + score>78"
  window: "8w"
  refusals_pct: 0.74
  regret_class: "MISSED_WIN"
  evidence: "Strong"
  n: 160
```

### SI-03 - Evidence Engine

**But :** suivre l'accumulation de preuves et les evenements qui renforcent ou
affaiblissent une hypothese.

Etats possibles :

```
NoEvidence -> Weak -> Moderate -> Strong -> VeryStrong
                \-> Contradicted
                \-> Inconclusive
                \-> Stale
```

Chaque transition doit reference :

- un dataset UUID ;
- une experience ;
- une taille d'echantillon ;
- un test statistique ;
- un effet observe ;
- une date d'evaluation.

### SI-04 - Scientific Timeline

**But :** afficher l'evolution de la connaissance, pas seulement la chronologie
des decisions.

Exemple :

```text
2026-05  H1 created
2026-06  30 trades  -> Evidence Weak
2026-07  80 trades  -> Evidence Moderate
2026-08  160 trades -> Evidence Strong
2026-08  H1 Confirmed
```

### SI-05 - Contradiction Detector

**But :** detecter les conclusions simultanees qui ne peuvent pas etre vraies
ensemble dans le cadre d'une recommandation.

Sources initiales :

- `experiments/EXP-001.yaml` -> `known_conflict_pairs`
- `analysis/hypothesis_registry.yaml`
- `analysis/hypothesis_quality.yaml`

Sortie cible :

```yaml
scientific_contradiction:
  pair: [H1, H3]
  severity: "BLOCKING"
  reason: "H3 Rejected invalide une recommandation de seuil fondee sur H1"
  required_action: "ouvrir une experience de resolution"
```

### SI-06 - Knowledge Confidence

**But :** mesurer la confiance dans la connaissance produite.

Difference normative :

| Score | Question |
|-------|----------|
| OCS | Peut-on faire confiance a l'observateur ? |
| Knowledge Confidence | Peut-on faire confiance a la connaissance produite ? |

Dimensions candidates :

- certification du dataset ;
- OCS au moment de la collecte ;
- taille d'echantillon ;
- puissance statistique ;
- reproductibilite ;
- absence de contradiction ;
- fraicheur temporelle ;
- couverture des regimes.

### SI-07 - Scientific Drift

**But :** detecter qu'une connaissance vieillit.

Une hypothese peut etre `Confirmed` sur un dataset, puis devenir moins fiable si :

- le regime de marche change ;
- les nouveaux datasets contredisent les anciens ;
- la performance se degrade hors intervalle attendu ;
- la reproductibilite tombe sous le seuil.

Sorties possibles :

```
Stable | Weakening | Drifted | Stale | Retired
```

### SI-08 - Decision DNA

**But :** encoder chaque decision en sequence comparable pour decouvrir des
familles de decisions.

Genome cible :

```yaml
decision_dna:
  packet_id: "<packet_id>"
  layer_sequence: ["authority", "meta_strategy", "gate", "..."]
  conviction: 0.75
  memory_signature: "mistake_memory:none"
  risk_signature: "portfolio:ok;capital:10usd"
  personality: "momentum"
  outcome: "REJECTED"
  regret_class: "MISSED_WIN"
  evidence_contribution: 0.03
```

---

## 6. Gates de maturite L3.5

| Gate | Nom | Condition |
|------|-----|-----------|
| SI-G0 | Specification | ADR-0008 + cette spec publies |
| SI-G1 | Sources fiables | Observer Certification Level 3 + dataset CERTIFIED/PASS |
| SI-G2 | Graphe initial | SI-01 lit decisions, hypotheses et datasets sans ecrire dans le moteur |
| SI-G3 | Evidence release | Premiere Knowledge Release avec contradictions et confidence documentees |
| SI-G4 | Drift release | Première conclusion confirmee puis re-evaluee sur dataset ulterieur |

Tant que SI-G1 n'est pas atteint, L3.5 reste une architecture cible.

---

## 7. Contrats d'integration

### Avec le DIP

L3.5 consomme les exports DIP ou lit le DIPStore en lecture seule. Les modules D01-D14
restent inchanges.

### Avec les hypotheses

Toute conclusion L3.5 pointe vers une hypothese versionnee. Une connaissance sans
hypothese falsifiable reste une observation, pas une conclusion scientifique.

### Avec les datasets

Toute evidence L3.5 pointe vers un dataset certifie. Une evidence issue de donnees
brutes peut exister en mode exploratoire, mais elle ne peut pas etre utilisee dans
un Go/No-Go.

### Avec l'operateur

L3.5 recommande des experiences et signale des contradictions. L'operateur decide
des changements de configuration.

---

## 8. Regles invariantes

1. L3.5 est strictement passif.
2. L3.5 ne modifie jamais un `DecisionPacket`.
3. L3.5 ne modifie jamais un seuil de decision.
4. L3.5 ne conclut jamais sans dataset certifie.
5. L3.5 distingue toujours observation, evidence, conclusion et recommandation.
6. L3.5 journalise les contradictions au lieu de les masquer.
7. L3.5 degrade la confiance d'une connaissance vieillissante.
8. L3.5 reste separable du cas d'usage trading.

---

## 9. Historique

| Version | Date | Changement |
|---------|------|------------|
| v0.1 | 2026-07-01 | Creation initiale L3.5, SI-01 a SI-08, gates SI-G0 a SI-G4 |
