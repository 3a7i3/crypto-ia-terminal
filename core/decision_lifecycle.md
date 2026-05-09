# Decision Lifecycle

Référence canonique du cycle de vie d'un `DecisionPacket`.  
Source de vérité : `core/decision_packet.py` — `DecisionState`, `VALID_TRANSITIONS`.

---

## États et leurs définitions

| État | Couche propriétaire | Définition |
|---|---|---|
| `CREATED` | — | Existence runtime initiale. Packet construit, aucune analyse effectuée. |
| `SIGNAL_GENERATED` | `live_signal_engine` | Opportunité statistique détectée. Le signal engine *constate*, il ne juge pas le risque. |
| `CONTEXT_ENRICHED` | `conviction_engine` | Intention contextualisée cognitivement. Conviction, dimensions, size_factor (advisory). |
| `REGIME_VALIDATED` | *(optionnel)* | Validation de régime par une couche dédiée. Court-circuitable si absent du pipeline. |
| `RISK_EVALUATED` | `global_risk_gate` | Confrontation à la souveraineté risque. Verdict rendu. Le packet a survécu aux 5 conditions. |
| `APPROVED` | `portfolio_brain` | Autorisation d'engagement capital accordée. Allocation décidée. |
| `EXECUTION_PENDING` | `order_sizer` | En file d'attente d'exécution. Espace pour async, throttling, failover, routing. |
| `EXECUTED` | `execution_engine` | Capital engagé sur le marché. Ordre confirmé par l'exchange. |
| `MONITORED` | `position_manager` | Position ouverte sous surveillance. TP/SL/trailing actifs. |
| `CLOSED` | `position_manager` | Position fermée. PnL réalisé connu. |
| `POSTMORTEM_ANALYZED` | `postmortem_engine` | Analyse causale terminée. VALIDATED / LUCKY / UNLUCKY / MISTAKE. |

### États terminaux (irréversibles)

Accessibles depuis **n'importe quel état vivant** — veto, expiry, panne peuvent survenir à tout moment.

| État | Émis par | Cause typique |
|---|---|---|
| `REJECTED` | `global_risk_gate` | Condition de gouvernance non satisfaite (score, drawdown, régime, session). |
| `VETOED` | tout agent | Veto exceptionnel — kill switch, anomalie système, règle absolue. |
| `EXPIRED` | `lifecycle_monitor` | Packet trop vieux pour être exécuté (conditions de marché changées). |
| `CANCELLED` | `portfolio_brain` / opérateur | Annulation explicite avant exécution. |
| `FAILED` | `execution_engine` | Erreur technique à l'exécution (exchange, réseau, fonds insuffisants). |

---

## Graphe de transitions

```
CREATED
  └─► SIGNAL_GENERATED
        └─► CONTEXT_ENRICHED
              ├─► REGIME_VALIDATED (optionnel)
              │     └─► RISK_EVALUATED
              └─► RISK_EVALUATED
                    └─► APPROVED
                          └─► EXECUTION_PENDING
                                └─► EXECUTED
                                      └─► MONITORED
                                            └─► CLOSED
                                                  └─► POSTMORTEM_ANALYZED

Depuis tout état vivant :
  └─► REJECTED | VETOED | EXPIRED | CANCELLED | FAILED
```

---

## Responsabilités par couche

### `live_signal_engine` — Couche signal
- **Produit :** `CREATED → SIGNAL_GENERATED`
- **Règle :** constate une opportunité statistique, ne juge jamais le risque
- **Advisory dans metadata :** `lse_actionable` (opinion, non-contraignante)
- **Ne peut pas :** appeler `reject()`, `veto_by()`

### `conviction_engine` — Couche intelligence
- **Produit :** `SIGNAL_GENERATED → CONTEXT_ENRICHED`
- **Règle :** enrichit uniquement — 5 dimensions de conviction, reasoning causal
- **Advisory dans metadata :** `conviction_size_factor`, `conviction_dimensions`
- **Ne peut pas :** appeler `reject()`, `veto_by()`

### `global_risk_gate` — Couche gouvernance
- **Produit :** `CONTEXT_ENRICHED → RISK_EVALUATED` ou `REJECTED`
- **Règle :** seule couche autorisée à appeler `reject()` en flux normal
- **Vérifie :** session, drawdown, score minimum, MTF confirmation, régime
- **Lit en advisory :** `lse_actionable`, `conviction`, `conviction_size_factor`
- **Écrit :** `packet.features["risk_drawdown_pct"]`, `packet.metadata["risk_conditions"]`

### `portfolio_brain` — Couche allocation
- **Produit :** `RISK_EVALUATED → APPROVED`
- **Vérifie :** corrélation portefeuille, concentration, exposition totale
- **Peut :** appeler `reject()` si le portefeuille ne peut absorber la position

### `order_sizer` — Couche sizing
- **Produit :** `APPROVED → EXECUTION_PENDING`
- **Lit :** `conviction_size_factor` (advisory), Kelly, volatilité
- **Écrit :** `allocation_pct`, `risk_score` final

### `execution_engine` — Couche exécution
- **Produit :** `EXECUTION_PENDING → EXECUTED` ou `FAILED`
- **Engage :** capital réel sur l'exchange

---

## Séparations institutionnelles critiques

```
Intelligence produit des hypothèses.
Risk autorise l'exposition.
Execution engage le capital.
```

| Séparation | Pourquoi elle compte |
|---|---|
| `RISK_EVALUATED ≠ APPROVED` | L'évaluation et l'autorisation sont deux actes distincts. `portfolio_brain` peut refuser après `risk_gate`. |
| `APPROVED ≠ EXECUTED` | Espace pour async, queues, failover, throttling, shadow approval. |
| `lse_actionable` advisory ≠ rejet | Le signal engine donne une opinion. Le risk_gate décide. Les opinions sont traçables sans être contraignantes. |
| États terminaux globaux | Une panne, un veto, une expiration peuvent survenir depuis n'importe quel état vivant — pas seulement à certains points. |

---

## Exemples de flows

### Flow nominal — signal fort, tout passe

```
CREATED
  → SIGNAL_GENERATED    [lse]          score=82, BUY, régime=TREND_BULL
  → CONTEXT_ENRICHED    [conviction]   HIGH, size×1.0
  → RISK_EVALUATED      [risk_gate]    5/5 conditions OK
  → APPROVED            [portfolio]    allocation 2% capital
  → EXECUTION_PENDING   [order_sizer]  450 USD queued
  → EXECUTED            [exec_engine]  filled @ 94,230
  → MONITORED           [position]     SL=93,100 TP=96,500
  → CLOSED              [position]     SL touché, PnL=-1.2%
  → POSTMORTEM_ANALYZED [postmortem]   UNLUCKY (signal était correct)
```

### Flow rejeté — score insuffisant

```
CREATED
  → SIGNAL_GENERATED    [lse]       score=54, BUY, lse_actionable=False
  → CONTEXT_ENRICHED    [conviction] SKIP, size×0.0
  → REJECTED            [risk_gate]  signal_score (54<70), signal_confirmed
```
*Traçabilité : le signal à score=54 est visible dans l'audit trail. Avant D4, il mourrait silencieusement dans `live_signal_engine`.*

### Flow rejeté — régime blacklisté

```
CREATED
  → SIGNAL_GENERATED    [lse]       score=88, SELL, régime=VOLATILE
  → CONTEXT_ENRICHED    [conviction] MEDIUM, size×0.6
  → REJECTED            [risk_gate]  regime_blacklisted (VOLATILE)
```
*Signal valide, conviction correcte, mais le régime est hors politique de risque.*

### Flow vetoé — kill switch système

```
CREATED
  → SIGNAL_GENERATED    [lse]       score=91, BUY
  → VETOED              [kill_switch] halte système — drawdown -15% détecté
```
*Le veto est accessible depuis tout état vivant.*

### Flow HOLD — rejet direction

```
CREATED
  → SIGNAL_GENERATED    [lse]       score=71, HOLD, side=FLAT
  → CONTEXT_ENRICHED    [conviction] SKIP (plafond HOLD=35)
  → REJECTED            [risk_gate]  side=FLAT — aucune direction tradeable
```
*Le signal HOLD arrive jusqu'à `risk_gate` (D4 corrigée). C'est là que la direction est jugée, pas dans `live_signal_engine`.*

---

## Ce que ce graphe révèle

- `REGIME_VALIDATED` est actuellement orphelin — aucune couche ne l'émet. À implémenter ou supprimer.
- `CONTEXT_ENRICHED` porte à la fois conviction et enrichissement contextuel. Si une couche de contexte de marché distincte émerge, un état `MARKET_CONTEXTUALIZED` pourrait la précéder.
- La distance `RISK_EVALUATED → APPROVED` est actuellement zéro latence. Quand `portfolio_brain` sera migré, cet espace sera comblé.
- `reasoning[*].category` permet une analytics future : quelle famille de raisonnement (trend_alignment, risk_governance, signal_quality…) corrèle avec le PnL réel.

---

*Dernière mise à jour : 2026-05-08 — après migration LSE, conviction, risk_gate, formalisation VALID_TRANSITIONS.*
