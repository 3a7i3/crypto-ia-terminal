# SCIENTIFIC_PROTOCOL.md

> **Statut : conception.** Protocole normatif cible de la V5.
> Aucune étape n'est implémentée à ce jour.

---

## 0. Principe

> **Un résultat sans manifeste est une sortie de script, pas une preuve.**

Le protocole a une seule fonction : rendre un résultat **opposable**. Opposable
signifie qu'un tiers — humain ou modèle, aujourd'hui ou dans cinq ans — peut le
reproduire, le contester, et savoir exactement ce qu'il ne prouve pas.

### Les trois séparations non négociables

| Séparation | Règle | Pourquoi |
|---|---|---|
| **Proposer ≠ valider** | Celui qui formule l'hypothèse n'exécute pas l'expérience | protège du biais de confirmation |
| **Valider ≠ appliquer** | Celui qui rend le verdict ne fusionne pas | protège de l'auto-optimisation |
| **Prédire ≠ observer** | La prédiction est déposée avant le premier run | protège du p-hacking |

---

## 1. Vue d'ensemble des 13 étapes

```
 1 Observation      → ce qui a été vu
 2 Question         → ce qu'on ne sait pas
 3 Hypothèse        → une réponse falsifiable
 4 Baseline         → l'état de référence figé
 5 Expérience       → le protocole pré-enregistré
 6 Replay           → l'exécution déterministe
 7 Ablation         → l'attribution causale
 8 Walk-forward     → la stabilité hors échantillon
 9 Stress           → les conditions défavorables
10 Evidence         → le verdict signé
11 Publication      → l'entrée en connaissance
12 Proposition      → le changement demandé
13 Nouvelle baseline→ la référence mise à jour
```

**Règle d'arrêt.** Le protocole peut s'arrêter à toute étape avec un verdict
`INCONCLUSIVE`. Un arrêt précoce documenté vaut mieux qu'un parcours complet mal
fondé. Le verdict `INCONCLUSIVE` est un résultat de plein droit — il enregistre
ce qui manque.

---

## 2. Étape 1 — Observation

| | |
|---|---|
| **Entrées** | `Event` du ledger (L1), métriques dérivées |
| **Sorties** | `Observation` |
| **Artefacts** | `knowledge/observations/OBS-YYYY-NNN.json` |
| **Acteur** | tout — humain, agent, outil de mesure |

### Critères de validation
- L'observation décrit **ce qui a été vu**, jamais pourquoi. Toute phrase
  causale invalide l'observation et la reclasse en hypothèse.
- Elle référence les événements sources par identifiant, pas par description.
- Elle porte la borne d'époque sous laquelle elle a été faite.

### Anti-exemple mesuré
« Le score ne classe pas les trades » est une **inférence**.
« ρ = 0,16 entre score et rendement à 12-24 h, N = 139, époque V4 » est une
**observation**.

---

## 3. Étape 2 — Question

| | |
|---|---|
| **Entrées** | ≥ 1 `Observation` |
| **Sorties** | `Question` |
| **Artefacts** | `knowledge/questions/Q-YYYY-NNN.md` |

### Critères de validation
- La question admet au moins deux réponses possibles, toutes deux plausibles
  *a priori*. Une question dont une seule réponse est concevable n'est pas une
  question de recherche.
- Elle nomme la décision qu'elle informerait. **Une question qui ne changerait
  aucune décision est enregistrée mais non priorisée.**

---

## 4. Étape 3 — Hypothèse

| | |
|---|---|
| **Entrées** | `Question` |
| **Sorties** | `Hypothesis` + `NullHypothesis` |
| **Artefacts** | `knowledge/hypotheses/HYP-YYYY-NNN.md` |

### Critères de validation
- **Falsifiable** : la spec nomme explicitement le résultat qui la réfuterait.
- L'hypothèse nulle est formulée **et** c'est elle qui est testée.
- Effet minimal d'intérêt (MDE) déclaré : en dessous de quel effet le résultat
  n'a pas d'importance pratique, même s'il est statistiquement significatif.
- N minimal et puissance visée déclarés **avant** toute exécution.

### Note sur la friction
Pour ce projet, tout MDE doit être exprimé **net du plancher de friction mesuré
(0,194 %)**. Un effet brut inférieur à ce plancher n'a pas d'intérêt pratique,
quelle que soit sa significativité.

---

## 5. Étape 4 — Baseline

| | |
|---|---|
| **Entrées** | `Policy` actuellement en production |
| **Sorties** | `Baseline` figée |
| **Artefacts** | `knowledge/baselines/BL-YYYY-NNN.json` |

### Contenu obligatoire
`policy_version` · commit du code · `corpus_id` + hash · modèle de coûts ·
modèle de slippage · seed · métriques de référence avec intervalles de confiance.

### Critères de validation
- La baseline est **immuable**. Elle n'est jamais recalculée après coup.
- Elle est reproductible : rejouer la baseline doit redonner ses métriques
  bit-à-bit.

**Rationale mesurée.** Quatre changements d'époque en six semaines ont détruit
la comparabilité inter-période. Une baseline figée et versionnée est la seule
protection contre ce phénomène.

---

## 6. Étape 5 — Expérience (pré-enregistrement)

| | |
|---|---|
| **Entrées** | `Hypothesis`, `Baseline`, `Corpus` |
| **Sorties** | `ExperimentSpec` scellée |
| **Artefacts** | `experiments/EXP-YYYY-NNN/spec.yaml` |

### Contenu obligatoire de `spec.yaml`

```
id, hypothesis_id, null_hypothesis
baseline: {policy_version, commit}
intervention: {module, change, scope}     # UNE seule intervention
corpus: {corpus_id, content_hash, time_range, symbols, regimes}
metrics:
  primary: [...]      # UNE métrique primaire
  secondary: [...]
design:
  min_n, target_power, alpha, mde
  stopping_rule                            # explicite, jamais « quand ça marche »
validation:
  replay: required
  ablation: required
  walk_forward: required
  stress: required
  cost_model: realistic
promotion:
  human_approval_required: true
submitted_at                               # scelle le pré-enregistrement
```

### Critères de validation
- **Une seule intervention par expérience.** Deux changements simultanés
  produisent un résultat non attribuable.
- **Une seule métrique primaire.** Les autres sont secondaires et ne peuvent
  jamais fonder un verdict `PASS`.
- La règle d'arrêt est explicite et ne dépend pas du résultat observé.
- `submitted_at` antérieur à tout `run_started_at` — vérifié mécaniquement
  (INV-G07).

---

## 7. Étape 6 — Replay

| | |
|---|---|
| **Entrées** | `ExperimentSpec`, `Corpus`, `Policy` A et B |
| **Sorties** | `ReplayResult` (deux jeux de `TradeVerdict`) |
| **Artefacts** | `experiments/EXP-.../replay/{baseline,variant}.jsonl`, `run_manifest.json` |

### Contenu obligatoire de `run_manifest.json`
commit git · hash du corpus · versions de dépendances · seed · paramètres de
simulation · modèle de coûts · modèle de slippage · résultats train / validation
/ OOS · erreurs rencontrées · artefacts produits · date et environnement.

### Critères de validation
- **Déterminisme bit-à-bit** : deux exécutions identiques produisent des
  fichiers identiques (INV-G05).
- Le rejeu appelle **la même `TradeAuthority`** que la production (INV-G06).
- Aucun accès réseau, aucune horloge système, aucun état mutable pendant le
  rejeu.

### Limite à déclarer dans chaque manifeste
> La fidélité du simulateur d'exécution est **NON MESURÉE** à ce jour. Tout
> verdict porte donc une incertitude non bornée sur la marche réelle. Cette
> mention reste obligatoire jusqu'à quantification de l'écart fills simulés /
> fills réels.

---

## 8. Étape 7 — Ablation

| | |
|---|---|
| **Entrées** | `Policy`, `Corpus`, liste des couches |
| **Sorties** | `AblationResult` — effet marginal par couche |
| **Artefacts** | `experiments/EXP-.../ablation.json` |

### Protocole
Pour chaque couche et chaque groupe de couches : rejouer le corpus avec la
couche désarmée, comparer à la baseline sur les mêmes données et les mêmes
coûts. Produire l'effet marginal sur : débit de trades, PF, WR, drawdown,
regret.

### Critères de validation
- Toutes les ablations utilisent **le même corpus et le même seed**.
- Les groupes sont déclarés dans la spec, jamais choisis après lecture des
  résultats.

### Pourquoi cette étape est le cœur du protocole
La décision actuelle est une conjonction de 12 booléens
(`core/advisor_loop.py:1983`) plus 4 révocations. Quand une telle conjonction
refuse, **l'attribution du refus n'est pas estimable à partir des données
observationnelles** : on ne sait pas ce que les autres couches auraient dit sur
des candidats qu'elles n'ont jamais vus. Seule l'intervention — désarmer et
rejouer — rend la question décidable.

---

## 9. Étape 8 — Walk-forward / hors échantillon

| | |
|---|---|
| **Entrées** | `Corpus` segmenté |
| **Sorties** | `WalkForwardResult` |
| **Artefacts** | `experiments/EXP-.../walk_forward.json` |

### Critères de validation
- Segmentation déclarée dans la spec **avant** exécution.
- Aucun lookahead : vérifié par un test dédié, pas par relecture.
- Le résultat OOS est rapporté même — surtout — s'il contredit l'in-sample.
- Le nombre de segments et leur taille sont fixés a priori.

---

## 10. Étape 9 — Stress

| | |
|---|---|
| **Entrées** | `Policy`, scénarios adverses |
| **Sorties** | `StressResult` |
| **Artefacts** | `experiments/EXP-.../stress.json` |

### Scénarios minimaux obligatoires
coûts × 2 · slippage × 3 · latence dégradée · régime de marché absent du corpus
d'entraînement · panne d'exchange · données manquantes · redémarrage à froid.

### Critère de validation
Un `PASS` obtenu uniquement sous coûts nominaux est **downgradé en
`INCONCLUSIVE`**. La robustesse aux coûts n'est pas optionnelle sur un edge dont
le plancher de friction mesuré est de 0,194 %.

---

## 11. Étape 10 — Evidence

| | |
|---|---|
| **Entrées** | tous les résultats précédents |
| **Sorties** | `Verdict` ∈ {`PASS`, `FAIL`, `INCONCLUSIVE`} |
| **Artefacts** | `experiments/EXP-.../verdict.json` (signé, immuable) |

### Grille de décision

| Condition | Verdict |
|---|---|
| Effet ≥ MDE, significatif, stable en OOS, survit au stress, N ≥ min_n | `PASS` |
| Effet < MDE **ou** non significatif avec N ≥ min_n | `FAIL` |
| N < min_n **ou** puissance insuffisante **ou** rejeu non déterministe **ou** stress non passé | `INCONCLUSIVE` |

### Critères de validation
- Le verdict porte ses **limites explicites** : ce qu'il ne prouve pas.
- Il est **immuable**. Une révision produit un nouveau verdict qui référence
  l'ancien (contrat C-04).
- `INCONCLUSIVE` enregistre ce qui manque pour conclure — c'est ce qui rend le
  manque interrogeable dans le graphe.

---

## 12. Étape 11 — Publication

| | |
|---|---|
| **Entrées** | `Verdict` |
| **Sorties** | `Publication`, arêtes du Knowledge Graph |
| **Artefacts** | `knowledge/publications/PUB-YYYY-NNN.md` |

### Critères de validation
- Rédigée pour un lecteur **sans accès à l'historique de conversation** — c'est
  la contrainte A5.
- Relie explicitement : observation → question → hypothèse → expérience →
  verdict → conséquence.
- Déclare ce qui reste ouvert.
- **Publication obligatoire y compris pour `FAIL` et `INCONCLUSIVE`.** Le biais
  de publication est le principal risque d'un laboratoire automatisé : si seuls
  les succès sont enregistrés, le graphe devient un générateur de faux positifs.

---

## 13. Étape 12 — Proposition

| | |
|---|---|
| **Entrées** | `Publication` avec verdict `PASS` |
| **Sorties** | `Proposal` — pull request |
| **Artefacts** | diff de `Policy` + verdict + preuve de rejeu |

### Critères de validation (contrôle CI, avant revue humaine)
- Verdict `PASS` attaché.
- Preuve de rejeu déterministe.
- N ≥ min_n déclaré dans la spec.
- Solde en variables expérimentales ≤ 0 (INV-G12).
- Aucun agent ne fusionne. **Signature humaine obligatoire.**

---

## 14. Étape 13 — Nouvelle baseline

| | |
|---|---|
| **Entrées** | `Proposal` fusionnée |
| **Sorties** | nouvelle `Baseline`, nouvelle époque |
| **Artefacts** | `knowledge/baselines/BL-YYYY-NNN+1.json`, ADR d'époque |

### Critères de validation
- L'époque précédente est close et scellée, jamais modifiée.
- L'ADR d'époque explicite ce qui a changé et pourquoi la comparabilité
  inter-époque est rompue ou préservée.
- La baseline précédente reste rejouable indéfiniment.

**Rationale mesurée.** Quatre époques en six semaines, chacune remettant N à
zéro. Sans déclaration formelle et sans conservation de la rejouabilité, chaque
changement détruit le capital statistique accumulé.

---

## 15. Ce que le protocole ne garantit pas

**15.1** Il ne garantit pas qu'une question soit intéressante. Il garantit
qu'une réponse soit opposable.

**15.2** Il ne compense pas un simulateur infidèle. Tant que l'écart fills
simulés / fills réels est **NON MESURÉ**, tout verdict de rejeu porte une
incertitude non bornée. C'est la dépendance critique du protocole entier.

**15.3** Il ne protège pas contre le sur-apprentissage sur le corpus. Un corpus
réutilisé par cent expériences finit par être appris. Un budget d'usage par
corpus, et une réserve de données jamais touchée, devront être définis avant que
le débit d'expériences ne devienne significatif.
