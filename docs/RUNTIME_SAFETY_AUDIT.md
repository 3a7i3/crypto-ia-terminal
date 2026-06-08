# Audit de Sécurité Runtime — crypto_ai_terminal

**Date :** 2026-06-01  
**Périmètre :** mécanismes d'urgence, safe_mode, halt, size_factor

---

## 1. Inventaire des mécanismes d'urgence

Le système dispose de **4 systèmes de sécurité indépendants**, non coordonnés entre eux :

| Système | Fichier | Niveau d'abstraction | Déclencheur |
|---|---|---|---|
| **KillSwitch (Telegram)** | `supervision/telegram_kill_switch.py` | Opérateur humain | Commandes `/STOP_ALL`, `/SAFE_MODE`, `/RESUME` |
| **SelfAwarenessEngine** | `quant_hedge_ai/agents/intelligence/self_awareness_engine.py` | Agent IA autonome | Dérive perf/comportementale/marché/infra |
| **GlobalRiskGate._safe_mode** | `quant_hedge_ai/agents/risk/global_risk_gate.py` | Couche risk pré-trade | Constructeur (`safe_mode=True`) ou var env `P6_SAFE_MODE` |
| **RuntimeStateMachine** | `quant_hedge_ai/runtime/runtime_state_machine.py` | Machine d'état infra | Compteur d'erreurs en fenêtre glissante |
| **system/state_machine.py** | `system/state_machine.py` | Persistance JSON | Transitions manuelles depuis advisor_loop |

> Note : `supervision/kill_switch.py` et `supervision/killswitch_hardened.py` sont des variantes du même mécanisme Telegram.

---

## 2. Inventaire détaillé des occurrences safe_mode

### 2.1 system/state_machine.py (lignes 34, 129)
```python
_VALID_STATES = {"NORMAL", "DEGRADED", "HALTED", "RECOVERY", "SAFE_MODE"}
# ...
elif new_state == "SAFE_MODE":
    self._state["trading_enabled"] = False  # ligne 130
```
**Effet :** `trading_enabled=False`, persiste dans `databases/system_state.json`. Pas de recovery automatique.

### 2.2 quant_hedge_ai/runtime/runtime_state_machine.py (lignes 39, 161–165, 169–173)
```python
class SystemState(str, Enum):
    SAFE_MODE = "SAFE_MODE"  # ligne 39

# Politique :
_POLICIES[SystemState.SAFE_MODE] = (False, False, 0.0)
#                                    can_trade, can_fetch_data, size_factor

# Recovery depuis SAFE_MODE (ligne 161) :
elif self._state == SystemState.SAFE_MODE:
    if len(self._errors) == 0 and silence >= self._silence_s * 2:
        self._set_state(SystemState.RECOVERY, now)  # double silence requis
```
**Effet :** bloque trading ET fetch de données ; size_factor=0.0 ; recovery possible après `2 × silence_s` sans erreur.

### 2.3 quant_hedge_ai/agents/risk/global_risk_gate.py (lignes 198, 489, 508, 523)
```python
self._safe_mode = safe_mode  # ligne 198 — constructeur

def apply_regret_delta(self, delta):
    if self._safe_mode:  # ligne 489
        return  # ignore l'ajustement

def set_transition_threshold(self, value):
    if self._safe_mode:  # ligne 508
        return

def set_adaptive_delta(self, delta):
    if self._safe_mode:  # ligne 523
        return
```
**Effet :** `_safe_mode=True` fige les seuils adaptatifs (pas de modification via ATE/RegretEngine/RegimeSmoother). Ne bloque **pas** le trading directement — le gate évalue quand même.

### 2.4 SelfAwarenessEngine / AwarenessState (lignes 63, 544, 553)
```python
@dataclass
class AwarenessState:
    safe_mode: bool = False  # ligne 63

# WARNING → safe_mode=True + size×0.25 (ligne 553)
elif level == DangerLevel.WARNING:
    self._state.size_factor = 0.25
    self._state.safe_mode = True

# DANGER → halt_until + 30 min (ligne 559)
elif level == DangerLevel.DANGER:
    self._state.size_factor = 0.0
    self._state.safe_mode = True
    self._state.halt_until = time.time() + self.HALT_DURATION_L3 * 60  # SA_HALT_MINUTES=30
```
**Effet :** `safe_mode` interne à l'objet — pas connecté aux autres systèmes.

### 2.5 TelegramKillSwitch (lignes 41, 224)
```python
@dataclass
class KillSwitchState:
    safe_mode: bool = False  # ligne 41

def _cmd_safe_mode(self):
    self._state.safe_mode = True  # ligne 224
```
**Effet :** `kill_switch.is_safe_mode()` est vérifié dans `advisor_loop.py` (lignes 3271, 3735, 4077, 4555) — bloque l'exécution des ordres en mode observation.

---

## 3. Inventaire halt_until / HALT_MINUTES

| Localisation | Variable | Valeur par défaut | Effet |
|---|---|---|---|
| `self_awareness_engine.py` ligne 112 | `SA_HALT_MINUTES` (env) | 30 minutes | `halt_until = now + 30 × 60` au niveau DANGER |
| `self_awareness_engine.py` ligne 572 | Hardcodé | 86400 s (24h) | `halt_until = now + 86400` au niveau CRITICAL |
| `tests/test_stability_accelerated.py` ligne 136 | `state.halt_until` | — | Avance l'horloge de test si halt actif |

**Recovery DANGER :** automatique après expiry de `halt_until` (checked dans `is_safe_to_trade()` ligne 261 et `evaluate()` ligne 210).  
**Recovery CRITICAL :** 24h hardcodé — **aucune recovery automatique avant expiry**. Seul `engine.reset()` peut forcer le retour à OK.

---

## 4. Inventaire size_factor

| Source | Valeur | Condition |
|---|---|---|
| `RuntimeStateMachine` NORMAL | 1.0 | Nominal |
| `RuntimeStateMachine` DEGRADED | 0.5 | 3+ erreurs / 60s |
| `RuntimeStateMachine` CRITICAL/SAFE_MODE/RECOVERY | 0.0 | 7+/10+ erreurs ou silence insuffisant |
| `ExecutiveOverride` CLEAR | 1.0 | Pas de conditions déclenchées |
| `ExecutiveOverride` REDUCE | 0.5 | DD > 3% ou streak >= 3 |
| `ExecutiveOverride` CAREFUL | 0.25 | DD > 5% ou streak >= 5 |
| `ExecutiveOverride` MINIMAL | 0.10 | DD > 7% ou streak >= 7 |
| `ExecutiveOverride` VETO | 0.0 | DD > 10% ou streak >= 10 |
| `SelfAwarenessEngine` CAUTION | 0.5 | Dérive détectée niveau 1 |
| `SelfAwarenessEngine` WARNING | 0.25 | Dérive détectée niveau 2 |
| `SelfAwarenessEngine` DANGER/CRITICAL | 0.0 | Dérive sévère (halt actif) |
| `GlobalRiskGate._safe_mode=True` | N/A (pas size_factor) | Fige les seuils adaptatifs uniquement |
| `PortfolioBrain` 8 checks | 0.0 à 1.0 | Exposition/concentration/corrélation |
| `tracker_system` exit_config | Variable | Regime + profit_factor |

**Dans advisor_loop.py,** les facteurs sont **multipliés successivement** :
- Ligne 868-869 : `order_size_usd × pb_verdict.size_factor`
- Ligne 984-985 : `order_size_usd × eo_verdict.size_factor`
- Ligne 1249-1250 : `eff_size × conviction.size_factor × awareness_engine.effective_size_factor()`

**Risque :** si EO dit size=0.5 ET SelfAwareness dit size=0.5, l'ordre final est à 0.25 — comportement correct. Mais si l'un bloque à 0.0 et l'autre à 0.5, le résultat est 0.0 — la traçabilité doit indiquer quelle couche a forcé 0.

---

## 5. Analyse : ExecutiveOverride._compute_level()

**Fichier :** `quant_hedge_ai/agents/risk/executive_override.py` lignes 294–342

### Flux de transitions
```
CLEAR → REDUCE  : DD >= 3% OU daily_loss >= 2% OU streak >= 3 OU overtrading
REDUCE → CAREFUL: DD >= 5% OU daily_loss >= 3% OU streak >= 5 OU open_pnl <= -5%
CAREFUL → MINIMAL: DD >= 7% OU daily_loss >= 5% OU streak >= 7 OU open_pnl <= -8%
MINIMAL → VETO  : DD >= 10% OU daily_loss >= 8% OU streak >= 10 OU open_pnl <= -12%
VETO → MINIMAL  : DD <= 4% ET daily_loss <= 2% (auto-recovery)
MINIMAL/CAREFUL/REDUCE → CLEAR : toutes conditions disparaissent
```

### Problème identifié : piège VETO
La condition de recovery VETO→MINIMAL (lignes 307–313) :
```python
if self._level == OverrideLevel.VETO:
    if (m.drawdown_pct <= self.DD_RECOVERY  # 4%
        and m.daily_loss_pct <= self.DAILY_RECOVERY):  # 2%
        return OverrideLevel.MINIMAL
    return OverrideLevel.VETO  # ← reste VETO sinon
```

Si le drawdown oscille autour de 4% (4.1%, 3.9%, 4.1%…), l'EO oscille entre VETO et MINIMAL à chaque cycle — **pas de deadlock mais un comportement oscillatoire** potentiellement perturbant. Recommandation : ajouter une hysterèse (ex: `DD_RECOVERY - 0.5%` pour le seuil de sortie stable).

---

## 6. Analyse : SelfAwarenessEngine niveaux et effets

**Fichier :** `quant_hedge_ai/agents/intelligence/self_awareness_engine.py`

### Niveaux et effets (lignes 539–573)
| Niveau | size_factor | safe_mode | halt_until | Telegram |
|---|---|---|---|---|
| OK | 1.0 | False | — | — |
| CAUTION | 0.5 | False | — | — |
| WARNING | 0.25 | True | — | — |
| DANGER | 0.0 | True | +30 min (`SA_HALT_MINUTES`) | — |
| CRITICAL | 0.0 | True | +24h | OUI — `_send_telegram_critical()` |

### Anti-deadlock FREEZE_OVERRIDE (lignes 215–225)
Après `SA_FREEZE_HALTS=3` halts DANGER consécutifs sans trade, le niveau est capé à WARNING (size×0.25) pour éviter le gel permanent. C'est un mécanisme de recovery implicite.

**Problème identifié : CRITICAL sans recovery automatique**  
Au niveau CRITICAL, `halt_until = now + 86400`. La seule sortie est :
1. Attendre 24h (l'horloge expire)
2. Appeler `engine.reset()` manuellement

**Aucune commande Telegram ne mappe vers `awareness_engine.reset()`** dans le code actuel. L'opérateur qui envoie `/RESUME` sur Telegram ne déverrouille que le KillSwitch, **pas** le SelfAwarenessEngine CRITICAL.

---

## 7. Analyse : GlobalRiskGate._safe_mode

**Fichier :** `quant_hedge_ai/agents/risk/global_risk_gate.py`

`_safe_mode` dans GlobalRiskGate est un **mode de gel des seuils adaptatifs**, pas un mode de blocage du trading. Il affecte uniquement :
- `apply_regret_delta()` — feedback RegretEngine
- `set_transition_threshold()` — ramp RegimeSmoother
- `set_adaptive_delta()` — delta ATE

Il est activé via `P6_SAFE_MODE=true` (env var, ligne 85 advisor_loop) ou le constructeur. En `P6_SAFE_MODE`, les seuils de score restent figés à leur valeur de base — le gate continue à évaluer normalement.

**Ce comportement est correct mais mal nommé** : `_safe_mode` de GlobalRiskGate n'est pas le même concept que `safe_mode` du KillSwitch ou de SelfAwareness.

---

## 8. Tableau des deadlocks et états sans recovery

| Situation | Système | Gravité | Recovery disponible |
|---|---|---|---|
| CRITICAL (SelfAwareness) — halt 24h | SelfAwarenessEngine | HAUTE | `engine.reset()` — non exposé via Telegram ❌ |
| VETO oscillant autour du seuil 4% DD | ExecutiveOverride | MOYENNE | Hysterèse absente — oscillation possible ⚠️ |
| SAFE_MODE (system/state_machine.py) | SystemStateMachine | HAUTE | Transition manuelle — pas de recovery auto ❌ |
| SAFE_MODE (RuntimeStateMachine) | RuntimeStateMachine | MOYENNE | Recovery auto après `2 × silence_s` sans erreur ✓ |
| kill_switch.is_halted() + boucle while | advisor_loop | BASSE | `/RESUME` Telegram ✓ |
| awareness DANGER pendant 30 min | SelfAwarenessEngine | BASSE | Expiry automatique `halt_until` ✓ |
| 3 FREEZE_OVERRIDE halts | SelfAwarenessEngine | BASSE | Cap automatique à WARNING ✓ |

---

## 9. Incohérences entre les 3 systèmes de safe mode

| Dimension | KillSwitch.safe_mode | SelfAwareness.safe_mode | GlobalRiskGate._safe_mode |
|---|---|---|---|
| **Sémantique** | Observation seule (pas d'ordres) | Flag interne état de dérive | Gel seuils adaptatifs |
| **Effet sur trading** | Bloque l'exécution (advisor_loop ligne 3735) | Bloque via `is_safe_to_trade()` (ligne 783) | Aucun effet sur trading |
| **Persistance** | En mémoire (`KillSwitchState.safe_mode`) | En mémoire (`AwarenessState.safe_mode`) | En mémoire (`self._safe_mode`) |
| **Recovery** | `/RESUME` Telegram | Automatique si drift disparaît OU `engine.reset()` | Constructeur / `P6_SAFE_MODE` |
| **Coordonné ?** | Non | Non | Non |

**Problème structurel :** les 3 systèmes sont indépendants. Un opérateur peut envoyer `/RESUME` sur Telegram et croire avoir tout déverrouillé, alors que SelfAwareness est toujours en CRITICAL et bloque les trades. Le dashboard affiche `safe_mode: kill_switch.is_safe_mode()` (ligne 4768) — ne reflète qu'un des trois états.

---

## 10. Hiérarchie recommandée

```
[1] KillSwitch (Telegram)     — autorité opérateur humain, priorité absolue
[2] SelfAwarenessEngine        — autonomie IA, surveillance dérive
[3] ExecutiveOverride          — protection capital, 5 niveaux automatiques
[4] GlobalRiskGate             — gouvernance pré-trade, seuils adaptatifs
[5] PortfolioBrain             — vérification exposition portefeuille
[6] OrderSizer                 — taille finale (Kelly + multiplicateurs)
```

La hiérarchie implicite actuelle est la même, mais **non documentée formellement** et non forcée par code (chaque système peut décider indépendamment).

---

## 11. Chemin vers une RuntimeStateMachine centralisée

L'architecture actuelle contient deux machines d'état partiellement redondantes :
- `system/state_machine.py` : persistance JSON, transitions manuelles (`NORMAL/DEGRADED/HALTED/RECOVERY/SAFE_MODE`)
- `quant_hedge_ai/runtime/runtime_state_machine.py` : transitions automatiques par compteur d'erreurs (`NORMAL/DEGRADED/CRITICAL/SAFE_MODE/RECOVERY`)

Le fichier `core/runtime_state_machine.py` existe dans l'arbre (non modifié) — vérifier s'il s'agit d'une troisième implémentation ou d'un proxy.

**Migration recommandée (3 étapes) :**

1. **Phase A — Observabilité unifiée**  
   Exposer un endpoint unique (ex: `GET /runtime/state`) qui agrège les 4 états :
   `{ "kill_switch": ..., "awareness": ..., "risk_gate": ..., "runtime_sm": ..., "system_sm": ... }`

2. **Phase B — Source de vérité unique**  
   Élire `RuntimeStateMachine` (qhai) comme source de vérité système. Faire transitionner `system/state_machine.py` depuis les callbacks de `RuntimeStateMachine.on_transition()`. Supprimer la duplication de transitions dans advisor_loop.

3. **Phase C — Commande Telegram unifiée**  
   Mapper `/RESUME` sur `kill_switch.resume() + awareness_engine.reset() + runtime_sm.force_recovery()` pour garantir que l'opérateur déverrouille réellement tout le système.

---

## 12. Recommandations prioritaires

| Priorité | Action |
|---|---|
| P0 | Exposer `awareness_engine.reset()` via la commande `/RESUME` Telegram — CRITICAL actuel est un piège sans sortie |
| P1 | Ajouter une hysterèse dans `ExecutiveOverride._compute_level()` pour éviter l'oscillation VETO↔MINIMAL autour du seuil 4% |
| P1 | Dashboard : afficher les 4 états de safe_mode simultanément (KillSwitch + SelfAwareness + RuntimeSM + SystemSM) |
| P2 | Unifier `system/state_machine.py` et `quant_hedge_ai/runtime/runtime_state_machine.py` — deux implémentations parallèles créent un risque de divergence silencieuse |
| P2 | Renommer `GlobalRiskGate._safe_mode` en `_freeze_adaptive_thresholds` pour éviter la confusion sémantique avec les autres safe_mode |
| P3 | Documenter la hiérarchie des couches de sécurité dans le code source (commentaire en tête de `advisor_loop.py`) |
