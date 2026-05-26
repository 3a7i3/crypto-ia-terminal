# ARCHITECTURE_NOTES

Découvertes structurelles révélées par la migration DecisionPacket.
Chaque entrée = un couplage implicite, une ambiguïté, ou une responsabilité floue trouvée dans le code réel.

---

## [2026-05-08] Migration live_signal_engine → DecisionPacket

### Découverte 1 : `components` est un dict hétérogène

`LiveSignalEngine._score_mtf()` écrit dans `components["mtf_tfs"]` un `dict[str, str]` (signal par TF).
Tous les autres champs sont des `float`.

**Symptôme :** Le dict `components` mélange floats ML-ready et structures de debug.

**Conséquence :** `_split_components()` doit séparer à la main ce qui va dans `features` vs `metadata`.
Un futur dataset ML recevrait des types incohérents sans ce garde-fou.

**Action à terme :** `_score_mtf()` devrait retourner un objet typé au lieu d'écrire dans un dict partagé.

---

### Découverte 2 : Noms de régimes LSE ≠ MarketRegime enum

`AdvancedRegimeDetector.classify()` retourne des strings comme `"bull_trend"`, `"sideways"`, `"flash_crash"`.
`MarketRegime` utilise `"TREND_BULL"`, `"RANGE"`, `"VOLATILE"`.

**Symptôme :** Couplage implicite entre deux modules qui n'ont jamais de contrat commun.

**Conséquence :** Le mapping `_REGIME_MAP` dans `live_signal_engine.py` est nécessaire mais fragile —
si `AdvancedRegimeDetector` ajoute un régime, `_REGIME_MAP` ne le saura pas.

**Action à terme :** `AdvancedRegimeDetector` devrait retourner directement un `MarketRegime`.

---

### Découverte 3 : `actionable` mélange deux conditions distinctes

```python
# SignalResult.actionable
return self.score >= _DEFAULT_MIN_SCORE and self.signal in ("BUY", "SELL")
```

Ce sont deux contraintes de nature différente :
- `score >= threshold` : conviction quantitative
- `signal in (BUY, SELL)` : direction détectée

Un score de 95 avec signal HOLD est non-actionable — mais la raison est différente d'un score de 40 avec BUY.
Dans DecisionPacket, ces deux raisons doivent être loggées distinctement.

**Action à terme :** `reject()` devrait distinguer `SCORE_TOO_LOW` vs `NO_DIRECTION`.

---

### Découverte 4 : Responsabilité du seuil `min_score` mal localisée

`_DEFAULT_MIN_SCORE = int(os.getenv("SIGNAL_MIN_SCORE", "70"))` vit dans `live_signal_engine.py`.

Ce seuil est une règle de **risk governance**, pas une règle de signal.
La décision "70 points = actionable" appartient à `risk_gate` ou `global_risk_gate`, pas au moteur signal.

**Symptôme :** Le signal_engine prend une décision de risque implicitement.

**Action à terme :** `evaluate_as_packet()` ne devrait pas appeler `reject()` sur le score —
laisser `risk_gate` décider. Le packet passe en `SIGNAL_GENERATED` même à score=42,
et c'est `risk_gate` qui rejette.

**[CORRIGÉ 2026-05-08]** `evaluate_as_packet()` produit toujours `SIGNAL_GENERATED`.
`lse_actionable` (bool) mis en `metadata` pour que `risk_gate` lise la recommandation LSE
sans en être lié. Les faux négatifs sont maintenant traçables jusqu'au rejet final.

---

### Découverte 5 : `mtf_tfs` devrait être dans `features` sous forme encodée

Actuellement `components["mtf_tfs"] = {"1h": "BUY", "4h": "HOLD"}` va en metadata.
Pour le ML futur, le vote par TF est une feature utile — mais elle doit être encodée en float.

Exemple :
```python
features["mtf_vote_1h"]  = 1.0  # BUY=1, HOLD=0, SELL=-1
features["mtf_vote_4h"]  = 0.0
features["mtf_consensus"] = 0.5  # ratio TFs en accord
```

**Action à terme :** Encoder le vote MTF en floats dans features, garder le dict lisible en metadata.

---

---

## [2026-05-08] Migration conviction_engine → DecisionPacket

### Découverte 6 : ConvictionLevel dupliqué en deux endroits

`conviction_engine.ConvictionLevel` : `"minimal"/"low"/"medium"/"high"/"exceptional"`
`core.decision_packet.ConvictionLevel` : `"SKIP"/"LOW"/"MEDIUM"/"HIGH"/"VERY_HIGH"`

**Symptôme :** Deux enums pour le même concept, valeurs incompatibles.
Mapping `_LOCAL_TO_CORE_CONVICTION` temporaire dans conviction_engine.py.

**Conséquence :** Drift silencieux si l'un des deux évolue sans que l'autre suive.

**Action à terme :** Fusionner dans `core.decision_packet.ConvictionLevel`. Supprimer l'enum local.

---

### Découverte 7 : `blocks_trade()` — gouvernance cachée dans la conviction

`ConvictionResult.blocks_trade()` retourne True si niveau MINIMAL.
Nom de méthode à sémantique de gouvernance dans une couche d'enrichissement.

**Symptôme :** Tout appelant de `blocks_trade()` court-circuite `risk_gate`.

**Conséquence :** Si un module lit `result.blocks_trade()` pour ne pas exécuter,
le rejet n'est pas tracé dans `state_history`. Les faux négatifs disparaissent.

**Action à terme :** Supprimer `blocks_trade()`. Les appelants doivent lire `packet.conviction == SKIP`
et laisser `risk_gate` décider de la suite.

---

### Découverte 8 : `size_factor` calculé dans conviction

`_SIZE_FACTORS[level]` retourne 0.0–1.5 dans `ConvictionEngine`.
C'est du sizing, pas de la conviction.

**Symptôme :** Une couche d'enrichissement signal calcule une allocation de capital.

**Conséquence :** Si `order_sizer` lit `conviction_size_factor` depuis metadata,
c'est advisory et correct. Mais si un module le lit comme décision finale, le sizing
échappe à la gouvernance du `portfolio_brain`.

**[CORRIGÉ partiellement 2026-05-08]** `size_factor` posé en `metadata["conviction_size_factor"]`
(advisory). `order_sizer` doit lire ce chiffre comme signal, pas comme directive.

**Action à terme :** Déplacer le calcul size_factor dans `order_sizer`. Conviction ne retourne
qu'un niveau (SKIP/LOW/MEDIUM/HIGH/VERY_HIGH), le sizing est une traduction distincte.

---

### Découverte 9 : `regime` string reverse-mapping nécessaire

`conviction_engine._regime_score()` attend `"bull_trend"` (format LSE).
`DecisionPacket.regime` est un `MarketRegime` enum (`"TREND_BULL"` etc.).

**Symptôme :** Deuxième reverse-mapping nécessaire en plus de `_REGIME_MAP` dans LSE.

**Conséquence :** Trois endroits maintenant font un mapping de régime.
Chaque ajout de régime dans `AdvancedRegimeDetector` risque de ne pas être reflété.

**Action à terme :** `AdvancedRegimeDetector` retourne directement `MarketRegime`.
Tous les reverse-mappings disparaissent. Un seul langage de régime dans tout le système.

---

## [2026-05-08] Migration global_risk_gate → DecisionPacket

### Découverte 10 : FLAT guard absent dans le flux original

`GlobalRiskGate.check()` ne vérifiait pas `side == FLAT` — elle supposait que
`live_signal_engine` ne transmettait que des signaux directionnels (BUY/SELL).

Ce contrat implicite a été rompu par la correction de la Découverte 4 :
maintenant tous les signaux (y compris HOLD/FLAT) produisent `SIGNAL_GENERATED`
et peuvent atteindre `risk_gate`.

**Symptôme :** Sans guard, un packet `side=FLAT` aurait pu passer `RISK_EVALUATED`
et descendre jusqu'à `order_sizer` avec une direction nulle.

**Conséquence :** Bug potentiel silencieux — ordre FLAT envoyé à l'exchange.

**[CORRIGÉ 2026-05-08]** `check_packet()` rejette immédiatement les packets FLAT
avec reasoning `category="risk_governance"`. Tracé dans `state_history`.

---

### Découverte 11 : `blacklisted_regimes` — format de string incompatible entre API

`check(signal_result)` compare `regime = getattr(signal_result, "regime", "unknown")`
(format LSE : `"bull_trend"`, `"flash_crash"`) contre `blacklisted_regimes`.

`check_packet(packet)` compare `packet.regime.value`
(format MarketRegime : `"TREND_BULL"`, `"VOLATILE"`) contre `blacklisted_regimes`.

**Symptôme :** Si un utilisateur configure `blacklisted_regimes={"flash_crash"}` et
utilise `check_packet()`, le check passe silencieusement (aucun match).

**Conséquence :** Régimes supposés blacklistés non filtrés dans le flux packet.
Risque de trade en régime interdit sans alerte.

**[CORRIGÉ 2026-05-26]** `GlobalRiskGate` normalise maintenant les régimes
legacy (`"flash_crash"`, `"bull_trend"`, `"sideways"`) et packet
(`"VOLATILE"`, `"TREND_BULL"`, `"RANGE"`) avant de comparer la blacklist.
Le correctif couvre `check()`, `check_packet()`, `blacklist_regime()` et
`unblacklist_regime()`.

**Action à terme :** Conserver la normalisation tant que le système accepte
les deux APIs, puis migrer progressivement vers un seul contrat de régime.

---

### Découverte 12 : Advisory vs Gouvernance — divergence tracée

Quand `lse_actionable=False` mais `score >= min_signal_score`, `check_packet()`
trace une entrée reasoning `category="risk_governance"` pour documenter la divergence.

Ce pattern — opinion externe ≠ décision de gouvernance — est précieux pour le
meta-learning : identifier quand le risk_gate approuve contre l'avis du signal engine,
et corréler avec le PnL réel.

**Ce n'est pas un bug.** C'est la séparation souveraineté / opinion qui fonctionne.
La trace est la preuve que le système ne court-circuite pas la gouvernance.

---

## Template pour nouvelles entrées

```
### Découverte N : [titre court]

[Description du problème trouvé dans le code réel]

**Symptôme :** [ce qu'on voit dans le code]
**Conséquence :** [ce qui casse ou peut casser]
**Action à terme :** [refactor recommandé — ne pas faire maintenant]
```
