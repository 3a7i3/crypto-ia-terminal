# CANONICAL_RUNTIME_SPEC.md — Autorités uniques du système V5

> **Statut.** Document **rédigé**, pas généré : c'est une cible architecturale.
> Mais chaque « état actuel » cité est **mesuré**, avec sa preuve.
>
> **Ce document ne décrit pas ce qui est. Il décrit ce vers quoi converger.**
> Il devient la référence normative de la V5 une fois validé par l'opérateur.

Mesures de référence : `artifacts/cartography.json`,
`artifacts/prod_executed_modules.txt` (processus de production PID 62316,
démarré 2026-08-01 20:53:48), commit de production `f427895`.

---

## 0. Principe fondateur

> **Une préoccupation, une autorité. Un état, un écrivain.**

Toute violation de ce principe est mesurable : deux implémentations d'un même
concept simultanément chargées dans le processus, ou deux sites d'écriture d'un
même état. Le tableau ci-dessous liste les violations **prouvées par exécution**.

### Violations mesurées à ce jour

| Concept | Implémentations simultanément **exécutées** en production | Preuve |
|---|---|---|
| Décision d'ouverture | **5 sites d'écriture** de `trade_allowed` | `advisor_loop.py:1983` (calcul) + `:5626`, `:5658`, `:5734`, `:5808` (révocations) |
| État runtime | **2 machines d'état** | `quant_hedge_ai/runtime/runtime_state_machine.py` **et** `system/state_machine.py` — toutes deux dans les `.pyc` de production |
| Arrêt d'urgence | **2 modules kill switch** | `supervision/kill_switch.py` **et** `supervision/killswitch_hardened.py` — tous deux exécutés |
| Étranglement du capital | **2 `CapitalThrottle`** | `capital_deployment/capital_throttle.py` **et** `quant_hedge_ai/agents/risk/capital_throttle.py` |
| Position | **2 classes `Position`** | `.../execution/position_manager.py:60` **et** `.../risk/portfolio_intelligence.py:38` |
| Snapshot portefeuille | **2 `PortfolioSnapshot`** | `observability/system_snapshot.py:56` **et** `.../risk/portfolio_brain.py:64` |
| Snapshot marché | **2 `MarketSnapshot`** | `execution_simulator/models.py:53` **et** `observability/system_snapshot.py:92` |
| Alerte | **2 classes `Alert`** | `observability/alerting.py:51` **et** `supervision/alert_manager.py:15` |
| Rejeu | **0 exécuté**, 2 définis | `audit/replay_engine.py`, `market_data/replay_engine.py` — aucun `.pyc` |

**Neuf concepts, aucun avec une autorité unique.**

---

## 1. `TradeAuthority` — autorité d'ouverture de position

### État actuel (mesuré)
La décision est calculée en un point puis révoquée en quatre autres. Aucune
entité ne détient l'autorité ; elle est distribuée sur cinq sites d'écriture du
même fichier.

### Spécification cible

```
TradeAuthority.evaluate(market_state, policy) -> TradeVerdict
```

| Propriété | Exigence |
|---|---|
| Unicité | **Une seule** implémentation dans tout le dépôt |
| Pureté | Aucune E/S, aucune horloge, aucun réseau. Même entrée → même sortie |
| Totalité | Retourne toujours un `TradeVerdict`, jamais `None`, jamais d'exception non capturée |
| Attribution | Le verdict porte la contribution **de chaque** couche, pas seulement du premier bloqueur |
| Fail-closed | Une couche en erreur produit un refus explicite, jamais un accord implicite |

`TradeVerdict` :

```
TradeVerdict:
    allowed        : bool
    size_usd       : float
    policy_version : str          # version de la Policy appliquée
    contributions  : list[LayerContribution]   # TOUTES les couches, toujours
    blocking       : list[str]    # couches ayant refusé — peut contenir >1 élément
    trace_id       : str
```

**Invariant TA-1.** `TradeVerdict.contributions` contient exactement autant
d'entrées qu'il y a de couches déclarées dans la `Policy`. Une couche qui n'a
pas été évaluée porte `evaluated=False` et une raison.
*Rationale : c'est ce qui rend l'attribution du refus décidable — impossible
aujourd'hui, cf. le ET de 12 termes.*

**Invariant TA-2.** Aucune couche autre que `TradeAuthority` ne produit de
verdict d'exécution. Les couches produisent des `LayerContribution`.

**Invariant TA-3.** Toute couche déclare son type dans la `Policy` :
`VETO_DUR` | `SCORE` | `OBSERVATEUR`. **Trois `VETO_DUR` au maximum.**
Le nombre actuel mesuré est de 12.

**Contrôle CI.** Un test échoue si `grep` trouve une écriture de la décision
hors de `TradeAuthority`, ou si la `Policy` déclare plus de trois `VETO_DUR`.

---

## 2. `DecisionWriter` — écrivain unique de la décision

### État actuel (mesuré)
5 sites d'écriture de `trade_allowed` dans `core/advisor_loop.py`.

### Spécification cible

Un seul site d'écriture dans tout le dépôt. Les révocations actuelles
(`risk_governor`, `safety_auditor`, `decision_packet`, et le site non nommé de
la ligne 5734) deviennent des `LayerContribution` de type `VETO_DUR` évaluées
**à l'intérieur** de `TradeAuthority`, jamais après elle.

**Invariant DW-1.** La décision est **immuable** après émission. Aucune mutation
d'un champ de `TradeVerdict` n'est permise.
*Rationale : les révocations post-hoc actuelles rendent l'objet non fiable comme
enregistrement scientifique.*

**Invariant DW-2.** Tout `TradeVerdict` est journalisé avant toute action
d'exécution, avec son `policy_version` et son `trace_id`.

**Contrôle CI.** Test statique : exactement une affectation de la décision dans
le dépôt hors tests.

---

## 3. `RuntimeState` — machine d'état unique

### État actuel (mesuré)
Deux machines d'état **simultanément chargées en production** :
`RuntimeStateMachine` et `SystemStateMachine`. **NON MESURÉ** : laquelle prévaut
en cas de désaccord sur `SAFE_MODE`. `SAFE_MODE` apparaît dans 18 fichiers de
production.

### Spécification cible

Une machine d'état, un jeu d'états, un journal de transitions.

```
RuntimeState: BOOTING | WARMUP | RUNNING | DEGRADED | SAFE_MODE | HALTED
```

**Invariant RS-1.** Une seule instance dans le processus. Toute transition passe
par elle et est journalisée avec cause, acteur et horodatage.

**Invariant RS-2.** `TradeAuthority` **lit** `RuntimeState` ; elle ne l'écrit
jamais. Symétriquement, `RuntimeState` ne connaît pas la décision.

**Invariant RS-3.** L'état est fail-closed : tout état autre que `RUNNING`
interdit l'ouverture de position. C'est le premier `VETO_DUR`.

**Contrôle CI.** Test : une seule classe de machine d'état atteignable depuis le
point d'entrée.

---

## 4. `EmergencyStop` — arrêt d'urgence unique

### État actuel (mesuré)
Six classes de kill switch dans le dépôt ; **deux modules exécutés en
production** (`supervision/kill_switch.py` et `supervision/killswitch_hardened.py`).
Identité trompeuse : deux classes se nomment `TelegramKillSwitch` et **aucune des
deux n'est instanciée** — celle qui tourne est `KillSwitchHardened`, portant ce
nom par aliasing (`core/advisor_runtime_adapters.py:109`).

### Spécification cible

Une classe, un nom, aucun alias.

**Invariant ES-1.** L'arrêt d'urgence agit **uniquement** en demandant une
transition à `RuntimeState`. Il n'écrit jamais la décision et ne touche jamais
l'exécution directement.
*Rationale : aujourd'hui l'arrêt d'urgence et la décision partagent des chemins,
ce qui rend le comportement en incident non déterministe.*

**Invariant ES-2.** Aucun aliasing de nom de classe dans la façade runtime. Le
nom lu dans le code d'appel est le nom de la classe définie.

**Contrôle CI.** Test : aucun `import X as Y` où `Y` est le nom d'une autre
classe existante du dépôt.

---

## 5. `ReplayEngine` — rejeu déterministe

### État actuel (mesuré)
Deux implémentations définies, **aucune exécutée** — aucun `.pyc` en production
pour `audit/replay_engine.py` ni `market_data/replay_engine.py`.

### Spécification cible

```
ReplayEngine.replay(market_state_stream, policy, seed) -> list[TradeVerdict]
```

**Invariant RE-1 — déterminisme strict.** Même `MarketState`, même `Policy`,
même `seed` → verdicts identiques **octet pour octet**. Vérifié par un test de
non-régression sur un corpus figé et versionné.

**Invariant RE-2.** Le rejeu n'a accès à aucune source vivante : ni réseau, ni
horloge système, ni fichier d'état mutable. Toute lecture de `datetime.now()`
ou d'un socket dans le chemin de rejeu fait échouer le test.

**Invariant RE-3.** `ReplayEngine` et le runtime de production appellent
**exactement la même** `TradeAuthority`. Aucune duplication de la logique de
décision pour les besoins du rejeu.
*Rationale : c'est la condition sans laquelle un résultat de rejeu ne prouve
rien sur la production.*

**Contrôle CI.** Le test de déterminisme est bloquant au merge.

---

## 6. `MarketStateProvider` — état de marché unique

### État actuel (mesuré)
Deux classes `MarketSnapshot` simultanément exécutées ; deux
`PortfolioSnapshot` ; deux `Position`.

### Spécification cible

Un type `MarketState`, sérialisable, hashable, versionné.

**Invariant MS-1.** `MarketState` est **la seule** entrée de `TradeAuthority`.
Aucune couche ne lit une source de marché en direct pendant l'évaluation.
*Rationale : condition nécessaire du rejeu — une couche qui interroge le réseau
pendant la décision rend le rejeu impossible.*

**Invariant MS-2.** Un `MarketState` porte un hash de contenu. Deux exécutions
sur le même hash doivent produire le même verdict.

---

## 7. `CapitalAuthority` — sizing unique

### État actuel (mesuré)
Deux `CapitalThrottle` simultanément exécutés en production. **NON MESURÉ** :
s'ils sont cohérents entre eux, ou s'ils se composent.

### Spécification cible

Une autorité de sizing. `TradeAuthority` lui délègue la taille ; aucune autre
couche ne multiplie `order_size_usd`.

**Invariant CA-1.** La taille finale est produite en un seul endroit. Les
facteurs de réduction (`ExecutiveOverride`, conviction, arbitrage) deviennent des
entrées déclarées de `CapitalAuthority`, pas des mutations successives.
*État actuel mesuré : `order_size_usd` est muté en cascade à au moins trois
endroits de `analyze_symbol`.*

**Invariant CA-2.** La base de sizing est explicite et versionnée
(`WALLET_PAPER_CAPITAL` aujourd'hui, par décision constitutionnelle). Tout
changement de base est une décision de calibration, jamais un effet de
redémarrage.

---

## 8. `EvidenceLedger` — registre de preuve

### État actuel (mesuré)
`experiments/` contient un fichier YAML et **zéro module Python**. Aucun format
de verdict. Aucun chemin de la preuve vers le paramètre :
`FEATURE_AUTO_CALIBRATION=False` et `FEATURE_ADAPTIVE_CALIBRATION=False`
(`config/feature_flags.py:47,50`), et l'unique consommateur retourne un delta nul.

### Spécification cible

**Invariant EL-1.** Un changement de `Policy` n'est mergeable qu'accompagné :
d'un `spec.yaml` **pré-enregistré** (hypothèse et prédiction déposées avant
exécution), d'un `run_manifest.json` (commit, hash du corpus, seed, coûts,
versions), d'un verdict `PASS` / `FAIL` / `INCONCLUSIVE`, et d'une preuve de
rejeu déterministe.

**Invariant EL-2 — séparation proposer / valider / appliquer.** L'agent qui
propose ne valide pas. L'agent qui valide n'applique pas. L'application exige
une signature humaine. **Aucun agent ne ferme la boucle sur lui-même.**

**Invariant EL-3.** Les résultats sont immuables. Un verdict n'est jamais
réécrit ; il est remplacé par un nouveau verdict qui le référence.

**Contrôle CI.** Une PR modifiant une `Policy` sans verdict attaché est refusée
automatiquement.

---

## 9. `ConfigAuthority` — paramètres uniques

### État actuel (mesuré)
`FORCE_TEST_EXECUTION` (`advisor_loop.py:1943-1980`) force huit couches à `True`
depuis une variable d'environnement, **sans marquer les trades produits**. Un
trade émis sous ce drapeau est indiscernable d'un trade nominal dans
`paper_trades.jsonl`.

### Spécification cible

**Invariant CF-1.** Aucune variable d'environnement ne peut désarmer une couche
de décision. Les bypass de test appartiennent au harnais de test, jamais au
chemin de production.

**Invariant CF-2.** Tout enregistrement de trade porte le `policy_version` sous
lequel il a été produit. Un dataset ne mélange jamais deux versions sans
étiquette.
*Rationale : c'est ce qui aurait évité la contamination ayant coûté l'époque v2.*

---

## 10. Ce que la V5 n'introduit pas

Conformément à la Scientific Debt Rule, cette spécification est **soustractive**.
Elle n'ajoute aucune couche de décision, aucun indicateur, aucune stratégie,
aucun agent IA, aucun modèle RL.

| Cible | Élimine |
|---|---|
| `TradeAuthority` | 5 sites d'écriture → 1 ; 12 vétos → 3 max |
| `RuntimeState` | 2 machines d'état → 1 |
| `EmergencyStop` | 6 classes → 1, aliasing supprimé |
| `CapitalAuthority` | 2 `CapitalThrottle` → 1 ; mutations en cascade → 1 site |
| `MarketStateProvider` | 2 `MarketSnapshot`, 2 `Position`, 2 `PortfolioSnapshot` → 1 chacun |
| `ReplayEngine` | 2 implémentations mortes → 1 vivante |

**Solde net en variables expérimentales : négatif.**

---

## 11. Ordre de convergence contraint

Les dépendances sont techniques, pas préférentielles.

```
1. RuntimeState unique          (aucune dépendance)
2. EmergencyStop unique          (dépend de 1)
3. MarketStateProvider unique    (aucune dépendance)
4. TradeAuthority pure           (dépend de 1 et 3)
5. DecisionWriter unique         (dépend de 4)
6. ReplayEngine                  (dépend de 3 et 4)
7. CapitalAuthority unique       (dépend de 4)
8. EvidenceLedger                (dépend de 6)
9. ConfigAuthority               (dépend de 5)
```

L'étape 6 est le pivot : sans elle, aucune des suivantes ne peut être **prouvée**
plutôt que décidée d'opinion.

---

## 12. Conditions de validation de ce document

Ce document ne devient normatif qu'après :

1. Validation explicite de l'opérateur.
2. Levée des questions encore **NON MESURÉES** listées ci-dessous, car chacune
   peut modifier une spécification.

| Question ouverte | Impact sur la spec |
|---|---|
| Laquelle des 2 machines d'état prévaut aujourd'hui | détermine laquelle survit en §3 |
| Les 2 `CapitalThrottle` se composent-ils ? | détermine si §7 est une fusion ou une suppression |
| Le simulateur MEXC est-il fidèle ? | conditionne la valeur de tout rejeu (§5) |
| Quels modules se chargent en incident / recovery ? | peut reclasser des `DEAD` en `ACTIVE` |
| Les 4 couches `governance/` chargées sont-elles appelées ou seulement importées ? | détermine si `governance/` est à brancher ou à retirer |
