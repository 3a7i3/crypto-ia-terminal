# DATA GOVERNANCE SPECIFICATION v1.0

**Statut :** Référence normative active  
**Date :** 2026-06-30  
**Commit :** 6d250b7  
**Auteur :** opérateur + Claude Sonnet 4.6  

---

## 0. Portée et autorité

Ce document est la **référence normative** de toutes les données produites par le moteur
`crypto_ai_terminal`. Tout module qui consomme, analyse ou certifie des données
(S1/Data Quality Audit, S2/Statistical Readiness, S3/CRI, Phase 4/ACE, Strategy Lab,
AI Governance, Digital Twin) doit se conformer à cette spécification.

Aucun module ne peut définir ses propres critères de validité. Si un critère manque,
ce document est amendé (nouvelle version `v1.x`), pas le module.

---

## 1. Hiérarchie des données

```
DecisionEvent          ← produit par advisor_loop.py à chaque cycle
        ↓
DecisionObservation    ← contrat immuable (frozen dataclass, DecisionEventBus)
        ↓
RejectedSignal         ← persisté par RejectionStore (JSONL quotidien)
        ↓
RegretEvaluation       ← produit par RegretScheduler (7 horizons)
        ↓
CertifiedDataset       ← après passage S1 (Dataset Health Score ≥ 99%)
        ↓
ScientificExperiment   ← référence un CertifiedDataset, jamais un JSONL brut
        ↓
HypothesisResult       ← lié à un ScientificExperiment, immuable à la clôture
```

**Règle fondamentale :** Une hypothèse (H1-H6) ne peut être évaluée que sur un
`CertifiedDataset`. Lire directement un JSONL brut pour une conclusion statistique
est une violation de cette spécification.

---

## 2. Critères de validité — 24 critères DG-xxx

### Catégorie A — Identité (DG-001 → DG-006)

| ID | Critère | Validation | Sévérité |
|----|---------|-----------|---------|
| DG-001 | `observation_id` unique dans le dataset | Aucun doublon sur l'ensemble du fichier | ERROR |
| DG-002 | `dataset_uuid` présent et conforme RFC-4122 | Regex `[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}` | ERROR |
| DG-003 | `engine_version` présent et non vide | `len(engine_version) > 0` | ERROR |
| DG-004 | `git_commit` présent (7 chars minimum) | Regex `[0-9a-f]{7,40}` | ERROR |
| DG-005 | `observability_version` présent et ≥ 2 | `int(observability_version) >= 2` | ERROR |
| DG-006 | `feature_flags_hash` présent (12 chars hex) | Regex `[0-9A-F]{12}` | WARNING |

### Catégorie B — Temps (DG-007 → DG-010)

| ID | Critère | Validation | Sévérité |
|----|---------|-----------|---------|
| DG-007 | `ts` présent et > 0 | `float(ts) > 0` | ERROR |
| DG-008 | `ts_iso` conforme ISO-8601 UTC | Parse `datetime.fromisoformat(ts_iso)`, `tz == UTC` | ERROR |
| DG-009 | `ts` cohérent avec `ts_iso` (±1s) | `abs(ts - ts_iso_epoch) < 1.0` | ERROR |
| DG-010 | Timestamps monotones dans le fichier | `ts[i+1] >= ts[i]` pour toutes les paires | WARNING |

### Catégorie C — Intégrité structurelle (DG-011 → DG-014)

| ID | Critère | Validation | Sévérité |
|----|---------|-----------|---------|
| DG-011 | JSON valide | `json.loads()` sans exception | ERROR |
| DG-012 | Schéma conforme à `DecisionObservation v1` | Tous les champs obligatoires présents et typés | ERROR |
| DG-013 | Aucun champ `null` sur les champs ERROR-obligatoires | Voir liste §2.1 | ERROR |
| DG-014 | Types conformes | `score` float, `cycle` int, `all_blockers` list, etc. | ERROR |

### Catégorie D — Cohérence métier (DG-015 → DG-019)

| ID | Critère | Validation | Sévérité |
|----|---------|-----------|---------|
| DG-015 | `score` dans [0, 100] | `0.0 <= score <= 100.0` | ERROR |
| DG-016 | `side` valide | `side in {"BUY","SELL","LONG","SHORT","HOLD"}` | ERROR |
| DG-017 | `price` > 0 si `side != HOLD` | `price > 0.0` | ERROR |
| DG-018 | `all_blockers` cohérent avec `trade_allowed` | Si `trade_allowed=False` et `actionable=True` → `len(all_blockers) >= 1` | WARNING |
| DG-019 | `regime` dans les régimes connus | `regime in {"bull_trend","bear_trend","sideways","volatile","unknown"}` | WARNING |

### Catégorie E — Reproductibilité (DG-020 → DG-024)

| ID | Critère | Validation | Sévérité |
|----|---------|-----------|---------|
| DG-020 | `state_history` présent (liste, peut être vide) | `isinstance(state_history, list)` | ERROR |
| DG-021 | `features` présent (dict, peut être vide) | `isinstance(features, dict)` | ERROR |
| DG-022 | `packet_id` présent et non vide | `len(packet_id) > 0` | ERROR |
| DG-023 | `config_hash` présent dans le Dataset Manifest | Présent dans le fichier de manifest associé | WARNING |
| DG-024 | Replay théoriquement possible | `state_history` non vide OU `features` non vide (au moins un des deux) | WARNING |

---

### 2.1 Champs ERROR-obligatoires (DG-013)

Ces champs ne peuvent jamais être `null` sur une observation `actionable=True` :

```
observation_id, packet_id, ts, ts_iso, symbol, side, score, price,
regime, cycle, engine_version, trade_allowed, all_blockers, human_verdict,
gate_allowed, state_history, features
```

---

## 3. Niveaux de certification

```
CERTIFIED  ── 100% critères ERROR satisfaits + 0 WARNING
    ↓
PASS       ── 100% critères ERROR satisfaits + ≤ 5 WARNINGs
    ↓
WARNING    ── 100% critères ERROR satisfaits + > 5 WARNINGs
    ↓
FAIL       ── au moins 1 critère ERROR non satisfait
```

**Seuls les datasets CERTIFIED ou PASS peuvent alimenter une hypothèse.**  
Un dataset WARNING peut alimenter une analyse exploratoire, jamais une décision.  
Un dataset FAIL est invalide pour tout usage analytique.

### Certification ID

Format : `CERT-{YYYY}-Q{Q}-{NNN}`  
Exemple : `CERT-2026-Q3-001`

Le certificat est immuable après délivrance. Toute correction des données
produit un nouveau dataset avec un nouveau UUID et un nouveau certificat.

---

## 4. Dataset Manifest

Chaque campagne produit un manifest qui identifie précisément le contexte de
production des données. Le manifest accompagne le dataset comme une étiquette
de laboratoire.

### Schéma obligatoire

```yaml
dataset_manifest:
  # Identité
  uuid: ""                         # RFC-4122 v4, généré à l'ouverture du dataset
  name: ""                         # Nom humain (ex: "Burn-in 2026-Q3")
  experiment_id: ""                # Lien vers experiments/EXP-xxx.yaml

  # Traçabilité technique
  engine_version: ""               # ex: "v9"
  git_commit: ""                   # commit au démarrage (7 chars min)
  git_branch: ""                   # ex: "main"
  observability_version: 2         # Version du système d'observabilité
  config_hash: ""                  # SHA-256[:12] des paramètres clés (en majuscules)
  feature_flags_hash: ""           # SHA-256[:12] du snapshot feature_flags (en majuscules)
  schema_version: 1                # Version du schéma DecisionObservation

  # Contexte marché
  exchange: ""                     # ex: "MEXC"
  mode: ""                         # ex: "paper_trading" | "live"
  trading_universe_size: 0         # Nombre de paires au démarrage
  symbol_blacklist: []

  # Dates
  date_opened: ""                  # ISO-8601 UTC
  date_closed: null                # null si toujours actif

  # Certification
  certified: false
  certification_id: null           # CERT-{YYYY}-Q{Q}-{NNN} après S1
  certification_date: null

  # Filiation
  parent_dataset_uuid: null        # Si dérivé d'un autre dataset

  # Replay
  replay_supported: true
  replay_instructions: ""          # Comment reproduire les conditions
```

### Règle de filiation

Si le contexte change significativement (nouveau git commit qui modifie le pipeline,
changement de configuration, extension de l'univers de trading), un **nouveau dataset**
est créé avec `parent_dataset_uuid` pointant vers le précédent.  
Les données des deux datasets ne sont **jamais mélangées** dans une même analyse.

---

## 5. Scientific Lineage — Traçabilité des hypothèses

Chaque résultat d'hypothèse doit tracer précisément les données qui l'ont produit.

### Schéma de résultat

```yaml
hypothesis_result:
  hypothesis_id: ""                # ex: "H3"
  hypothesis_version: ""           # ex: "H3-v1.0"
  evaluation_date: ""              # ISO-8601 UTC
  evaluator: ""                    # "regime_audit.py v1.x"

  # Dataset source
  dataset_uuid: ""                 # UUID du CertifiedDataset
  dataset_certification_id: ""     # CERT-{YYYY}-Q{Q}-{NNN}
  dataset_certification_level: ""  # CERTIFIED | PASS

  # Expérience parente
  experiment_id: ""                # EXP-xxx

  # Contexte technique
  engine_version: ""
  git_commit: ""
  n_observations: 0

  # Résultat statistique
  status: ""                       # Confirmed | Rejected | Inconclusive
  evidence_level: ""               # Weak | Moderate | Strong | VeryStrong (voir §6)
  test_statistic: null
  p_value: null
  effect_size: null
  confidence_interval_95: null     # [lower, upper]
  result_summary: ""
```

---

## 6. Evidence Levels

Le statut `Confirmed` / `Rejected` ne suffit pas. La confiance dans un résultat
dépend de la taille d'échantillon et de la puissance statistique.

| Niveau | N minimum | p-value | Effect Size | Description |
|--------|-----------|---------|-------------|-------------|
| **Weak** | ≥ N_min de l'hypothèse | < 0.10 | Quelconque | Première confirmation, à surveiller |
| **Moderate** | ≥ 2× N_min | < 0.05 | ≥ 0.2 (Cohen's d) | Résultat reproductible probable |
| **Strong** | ≥ 5× N_min | < 0.01 | ≥ 0.5 | Confiance élevée |
| **VeryStrong** | ≥ 10× N_min | < 0.001 | ≥ 0.8 | Conclusion institutionnelle |

**Règle :** Une recommandation ACE (Phase 4) ne peut être formulée que sur un résultat
`Strong` ou `VeryStrong`. Un résultat `Weak` ou `Moderate` est informatif seulement.

---

## 7. Scientific Immutability Rule

> Une fois qu'un `CertifiedDataset` est référencé par un `HypothesisResult` ou un
> `ScientificExperiment` clos, il devient **immuable**.
>
> - Il ne peut plus être modifié, filtré ou enrichi.
> - Toute correction (données incorrectes découvertes après certification) produit
>   un nouveau dataset avec un nouveau UUID, un nouveau certificat, et une
>   `parent_dataset_uuid` pointant vers l'original.
> - Les analyses antérieures restent reproductibles sur l'original.
> - L'expérience est réévaluée sur le nouveau dataset si les corrections sont
>   matérielles (impact sur les conclusions).

**Corollaire :** La `certification_date` marque le début de l'immuabilité.
Avant certification, les données peuvent être corrigées sans créer un nouveau UUID.

---

## 8. Versioning de ce document

Ce document est lui-même versionné. Toute modification crée une nouvelle version `v1.x`.

| Version | Date | Changements |
|---------|------|------------|
| v1.0 | 2026-06-30 | Création — 24 critères, 4 niveaux certification, Dataset Manifest, Scientific Lineage, Evidence Levels, Scientific Immutability Rule |

Les modules implémentés sur `v1.0` doivent être adaptés si une nouvelle version
modifie un critère ERROR. Les modifications WARNING ne nécessitent pas de re-certification
des datasets existants.

---

## 9. Références

- [ADR-0004 — Rejection Store JSONL](adr/0004-rejection-store-jsonl.md)
- [ADR-0005 — Regret Scheduler Asynchrone](adr/0005-regret-scheduler-asynchrone.md)
- [ADR-0007 — Observabilité Passive](adr/0007-observabilite-passive-separation.md)
- [CLAUDE.md — Règle du statisticien](../CLAUDE.md)
- [analysis/hypothesis_registry.yaml](../analysis/hypothesis_registry.yaml)
- [experiments/EXP-001.yaml](../experiments/EXP-001.yaml)
