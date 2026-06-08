# Spécification DecisionPacket — Audit des champs par agent

**Date :** 2026-06-01  
**Source :** `core/decision_packet.py` + grep exhaustif des agents

---

## 1. Structure du packet (core/decision_packet.py)

```python
@dataclass
class DecisionPacket:
    version: int = 1

    # Identité (immuables par convention)
    packet_id: str          # uuid4 généré à la création
    created_at: datetime
    created_cycle_id: Optional[str]
    context_id: Optional[str]

    # Instrument (immuables par convention)
    symbol: str
    timeframe: str

    # Signal
    side: DecisionSide      # LONG / SHORT / FLAT
    confidence: float       # 0–100, modifié via add_reasoning()
    expected_value: float

    # Contexte
    regime: MarketRegime    # TREND_BULL / TREND_BEAR / RANGE / VOLATILE / UNKNOWN

    # Prix
    entry_price, stop_loss, take_profit, r_multiple

    # Risk & sizing
    risk_score: float       # 0–100, produit par risk_gate
    allocation_pct: float   # % capital alloué
    conviction: ConvictionLevel

    # Veto
    veto: bool
    veto_reason: Optional[str]

    # Machine d'état
    lifecycle_state: DecisionState
    state_history: List[StateTransition]

    # Traçabilité
    source_agents: List[str]
    reasoning: List[ReasoningEntry]

    # Données
    features: Dict[str, float]    # quantitatif ML-ready (float uniquement)
    metadata: Dict[str, Any]      # debug/runtime (jamais parsé par agents)

    # Signature
    ed25519_signature: str
    signed_at: float
```

---

## 2. Graphe de transitions d'état

```
CREATED → SIGNAL_GENERATED → CONTEXT_ENRICHED → [REGIME_VALIDATED] → RISK_EVALUATED → APPROVED → EXECUTION_PENDING → EXECUTED → MONITORED → CLOSED → POSTMORTEM_ANALYZED

Branches terminales (depuis n'importe quel état non-terminal) :
    REJECTED | EXPIRED | CANCELLED | FAILED | VETOED
```

Règle graphe : `REGIME_VALIDATED` est optionnel (`CONTEXT_ENRICHED → RISK_EVALUATED` direct autorisé).

---

## 3. Tableau des champs par agent

### 3.1 LiveSignalEngine (`evaluate_as_packet`)

**Fichier :** `quant_hedge_ai/agents/execution/live_signal_engine.py` ligne 466  
**Transition produite :** `CREATED → SIGNAL_GENERATED → CONTEXT_ENRICHED`

| Champ | Opération | Valeur |
|---|---|---|
| `symbol` | Écrit (création) | symbol passé en arg |
| `timeframe` | Écrit (création) | `strategy["timeframe"]` |
| `side` | Écrit (création) | `LONG/SHORT/FLAT` selon signal |
| `confidence` | Écrit (création) | score brut signal |
| `regime` | Écrit (création) | régime détecté |
| `features` | Écrit (création) | composantes numériques (rsi, atr, ema_spread…) |
| `metadata["lse_actionable"]` | Écrit | `result.actionable` (ligne 583) |
| `metadata` | Écrit (création) | composantes non-numériques (mtf_tfs, signal_raw, mtf_confirmed…) |

---

### 3.2 ConvictionEngine (`enrich_packet`)

**Fichier :** `quant_hedge_ai/agents/intelligence/conviction_engine.py` ligne 263  
**Transition produite :** `CONTEXT_ENRICHED → CONTEXT_ENRICHED` (enrichissement en place, pas de transition d'état)

> **Règle absolue (ligne 25) :** jamais de `reject()` ni `veto_by()` ici.

| Champ | Opération | Valeur |
|---|---|---|
| `confidence` | **Lu** | score signal brut (dim 1) |
| `features["mtf"]` | **Lu** | alignement MTF |
| `features["mtf_strength"]` | **Lu** | force signal MTF |
| `metadata["mtf_confirmed"]` | **Lu** | bonus confirmation |
| `metadata["signal_raw"]` | **Lu** | BUY/SELL/HOLD pour régime/malus HOLD |
| `regime` | **Lu** | adéquation régime (dim 3) |
| `conviction` | **Écrit** | `ConvictionLevel` calculé |
| `metadata["conviction_size_factor"]` | **Écrit** (ligne 433) | size_factor advisory [0, 1.5] |
| `metadata["conviction_score"]` | **Écrit** (ligne 434) | score composite arrondi |
| `metadata["conviction_level_local"]` | **Écrit** (ligne 435) | niveau local avant override |
| `metadata["conviction_dimensions"]` | **Écrit** (ligne 436) | dict des 5 scores dimensionnels |
| `reasoning` | **Écrit** | entrées par dimension significative |

---

### 3.3 GlobalRiskGate (`check_packet`)

**Fichier :** `quant_hedge_ai/agents/risk/global_risk_gate.py` ligne 291  
**Transitions produites :** `CONTEXT_ENRICHED → RISK_EVALUATED` (pass) ou `→ REJECTED` (fail)  

> **Souveraineté (ligne 15) :** c'est ici et **uniquement ici** que `packet.reject()` est appelé en flux normal.

| Champ | Opération | Valeur |
|---|---|---|
| `side` | **Lu** (ligne 328) | guard FLAT → rejet immédiat |
| `metadata["lse_actionable"]` | **Lu** (ligne 344) | advisory LSE |
| `conviction` | **Lu** (ligne 345) | niveau conviction (advisory) |
| `confidence` | **Lu** (ligne 386) | score pour condition ③ |
| `regime` | **Lu** (ligne 387) | seuil régime-aware |
| `metadata["mtf_confirmed"]` | **Lu** (ligne 411) | condition ④ MTF |
| `features["risk_drawdown_pct"]` | **Écrit** (ligne 362) | drawdown courant × 100 |
| `metadata["risk_conditions"]` | **Écrit** (ligne 438) | dict des 5 conditions |
| `metadata["risk_failed"]` | **Écrit** (ligne 439) | liste des conditions échouées |
| `metadata["risk_warnings"]` | **Écrit** (ligne 440) | liste des avertissements |
| `metadata["risk_conviction_advisory"]` | **Écrit** (ligne 441) | conviction level string |
| `reasoning` | **Écrit** | entrées par condition échouée/warning |

---

### 3.4 PortfolioBrain (`approve_packet`)

**Fichier :** `quant_hedge_ai/agents/risk/portfolio_brain.py` ligne 290  
**Transitions produites :** `RISK_EVALUATED → APPROVED` (pass) ou `→ REJECTED` (fail)

> **Souveraineté (ligne 22) :** produit la transition RISK_EVALUATED → APPROVED, ou appelle `packet.reject()`.

| Champ | Opération | Valeur |
|---|---|---|
| `conviction` | **Lu** (ligne 322) | _CONV_SCORE mapping |
| `side` | **Lu** (ligne 323) | is_long detection |
| `symbol` | **Lu** (ligne 324) | identification |
| `regime` | **Lu** (ligne 325) | paramètre régime |
| `features["pb_exposure_pct"]` | **Écrit** (ligne 334) | exposition totale estimée |
| `features["pb_symbol_pct"]` | **Écrit** (ligne 377) | concentration par symbole |
| `features["pb_corr_risk"]` | **Écrit** (ligne 435) | score risque corrélation |
| `features["pb_leverage_weighted"]` | **Écrit** (ligne 458) | levier pondéré |
| `metadata["pb_size_factor"]` | **Écrit** (ligne 583) | multiplicateur portefeuille |
| `metadata["pb_capital_available"]` | **Écrit** (ligne 584) | capital disponible arrondi |
| `metadata["pb_warnings"]` | **Écrit** (ligne 585) | liste warnings portefeuille |
| `reasoning` | **Écrit** | entrées par check (exposition/concentration/corrélation/levier) |

---

### 3.5 OrderSizer (`size_packet`)

**Fichier :** `quant_hedge_ai/agents/risk/order_sizer.py` ligne 217  
**Transition produite :** `APPROVED → EXECUTION_PENDING`

| Champ | Opération | Valeur |
|---|---|---|
| `confidence` | **Lu** (ligne 260) | signal_score proxy |
| `features["realized_volatility"]` | **Lu** (ligne 253) | volatilité réalisée |
| `metadata["conviction_size_factor"]` | **Lu** (ligne 258) | multiplicateur conviction |
| `metadata["pb_size_factor"]` | **Lu** (ligne 259) | multiplicateur portefeuille |
| `allocation_pct` | **Écrit** | fraction du capital allouée |
| `features["os_kelly"]` | **Écrit** (ligne 280) | fraction Kelly brute |
| `features["os_vol_factor"]` | **Écrit** (ligne 281) | facteur volatilité |
| `features["os_dd_factor"]` | **Écrit** (ligne 282) | facteur drawdown |
| `features["os_size_usd"]` | **Écrit** (ligne 283) | taille finale USD |
| `reasoning` | **Écrit** | entrée sizing |

---

### 3.6 AdvisorLoop (transitions directes)

**Fichier :** `core/advisor_loop.py`

| Ligne | Opération |
|---|---|
| 682 | `conviction_engine.enrich_packet(_dp, ...)` |
| 737 | `gate.check_packet(_dp, ...)` |
| 877 | `portfolio_brain.approve_packet(_dp, ...)` |
| 945 | `_dp.transition_to(DecisionState.EXECUTED, ...)` |
| 971 | `_dp.reject("capital_engine", ...)` |

---

## 4. Champs immuables et vérification des mutations

Les champs suivants sont **immuables par convention** (aucune mutation trouvée en production) :

| Champ | Règle | Vérification grep |
|---|---|---|
| `packet_id` | Généré une fois à la création | Aucune écriture `packet.packet_id =` trouvée ✓ |
| `symbol` | Identifie l'instrument tout au long du cycle | Aucune écriture `packet.symbol =` trouvée ✓ |
| `timeframe` | Immuable — contexte d'analyse | Aucune écriture `packet.timeframe =` trouvée ✓ |
| `side` | Seul `global_risk_gate` lit `packet.side == FLAT` (guard) — pas de mutation | Aucune écriture `packet.side =` trouvée ✓ |
| `created_at` | Timestamp de naissance | Non muté ✓ |

> Résultat grep sur `packet\.symbol\s*=|packet\.timeframe\s*=|packet\.packet_id\s*=|packet\.side\s*=` : **zéro occurrence** en dehors des tests.

---

## 5. Mutations dangereuses identifiées

### 5.1 confidence modifiée via add_reasoning() en aval du risk_gate

`confidence` est à la fois **score du signal** (lu par GlobalRiskGate ligne 386) et **score cumulatif** modifié par `add_reasoning()`. Le problème : ConvictionEngine s'exécute **avant** GlobalRiskGate et ajoute des `reasoning` avec `confidence_impact=0.0` (pas de mutation), mais le risque existe si un agent futur modifie `confidence` **après** que GlobalRiskGate a lu la valeur.

**Recommandation :** figer `confidence` à partir de `RISK_EVALUATED` en introduisant une propriété protégée ou un snapshot `signal_confidence_at_gate`.

### 5.2 metadata sans namespace dans portfolio_brain

`portfolio_brain` écrit `metadata["pb_warnings"]` (type `list[str]`), qui est lu par `order_sizer` via `metadata["pb_size_factor"]` (float). Ces clés ne sont pas parsées par d'autres agents actuellement, mais la règle "metadata jamais parsé dans la logique métier" (ligne 357 du spec) est **violée** : `order_sizer` lit explicitement `metadata["pb_size_factor"]` et `metadata["conviction_size_factor"]` (lignes 258-259).

**Justification acceptée :** les deux clés ont des noms préfixés (`pb_`, `conviction_`) et sont documentées ; la Constitution les tolère comme "advisory links inter-agents". Mais ils devraient migrer dans `features` (valeurs float) : `pb_size_factor` et `conviction_size_factor` sont des floats ML-ready.

### 5.3 packet.reject() appelé depuis portfolio_brain

Le header du `global_risk_gate.py` (ligne 15) dit : *"c'est ICI et UNIQUEMENT ICI que packet.reject() est appelé en flux normal"*. Or `portfolio_brain.approve_packet()` appelle aussi `packet.reject()` (lignes 348, 391, 482, 508, 564).

C'est une incohérence de documentation : en réalité, `reject()` est légitimement appelé par tout agent souverain. La phrase devrait lire "risk_gate est la seule couche RISK_GOVERNANCE qui appelle reject() pour les conditions pré-trade".

### 5.4 Transition CONTEXT_ENRICHED → RISK_EVALUATED court-circuitant conviction_engine

`VALID_TRANSITIONS` autorise `CONTEXT_ENRICHED → RISK_EVALUATED` directement (ligne 174). Si l'appelant dans `advisor_loop.py` saute `conviction_engine.enrich_packet()`, `packet.conviction` reste `SKIP` et `metadata["conviction_size_factor"]` est absent, ce qui fait que `order_sizer` utilise la valeur de fallback `1.0` (ligne 258) — comportement correct mais non-communiqué au traçage.

---

## 6. Recommandations

| Priorité | Recommandation |
|---|---|
| P1 | Migrer `metadata["pb_size_factor"]` et `metadata["conviction_size_factor"]` dans `features` (ce sont des floats ML-ready, pas du debug) |
| P1 | Corriger la documentation de `global_risk_gate.py` ligne 15 : `reject()` est appelé aussi par `portfolio_brain` |
| P2 | Ajouter un snapshot `signal_confidence_at_gate: float` (immuable après RISK_EVALUATED) pour éviter que la confiance post-gate soit confondue avec le score brut |
| P2 | Standardiser les prefixes de clés metadata : `lse_*`, `risk_*`, `pb_*`, `conviction_*`, `os_*` sont bien utilisés — les documenter dans une enum ou constantes |
| P3 | Valider que `conviction_engine.enrich_packet()` est toujours appelé avant `gate.check_packet()` dans advisor_loop via un test d'ordre d'exécution |
