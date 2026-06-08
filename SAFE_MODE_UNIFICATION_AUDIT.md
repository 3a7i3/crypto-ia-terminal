# SAFE_MODE_UNIFICATION_AUDIT.md

**Auteur :** Analyse automatique — 2026-06-02  
**Portée :** Tous les mécanismes d'arrêt, de blocage, de halt, de safe_mode, de veto et de kill_switch dans le dépôt `crypto_ai_terminal`.  
**Objectif :** Identifier les doublons, conflits, autorités concurrentes, risques de divergence d'état, et proposer une architecture à source de vérité unique.

---

## 1. INVENTAIRE COMPLET — 18 MÉCANISMES IDENTIFIÉS

### 1.1 Kill Switches (3 implémentations)

| # | Fichier | Classe | État persisté | Commandes |
|---|---------|--------|---------------|-----------|
| KS-1 | `supervision/kill_switch.py` | `TelegramKillSwitch` / `BotMode` | En mémoire uniquement | `/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME` |
| KS-2 | `supervision/telegram_kill_switch.py` | `TelegramKillSwitch` / `KillSwitchState` | En mémoire uniquement | Mêmes commandes |
| KS-3 | `supervision/killswitch_hardened.py` | `KillSwitchHardened` / `HardenedKSState` | `cache/startup/killswitch_state.json` | Mêmes + `/CONFIRM /CANCEL /HELP` |

**Utilisé en production :** `advisor_loop.py` importe via `advisor_runtime_adapters.AdvisorRuntime` → probablement KS-1 ou KS-2 (à clarifier).  
**KS-3** est câblé dans des tests séparés (`supervision/tests/test_e04_killswitch.py`) mais pas dans `advisor_loop.py`.

---

### 1.2 Machines d'états (5 implémentations)

| # | Fichier | Classe | États | Persistance |
|---|---------|--------|-------|-------------|
| SM-1 | `system/state_manager.py` | `SystemState` (Enum) | BOOTING / SYNCING / READY / TRADING / RISK_OFF / DEGRADED / RECOVERY / SHUTDOWN / PANIC | Mémoire |
| SM-2 | `system/state_machine.py` | `get_state_machine()` | NORMAL / DEGRADED / HALTED / RECOVERY / SAFE_MODE | `databases/system_state.json` |
| SM-3 | `quant_hedge_ai/runtime/runtime_state_machine.py` | `RuntimeStateMachine` / `SystemState` | NORMAL / DEGRADED / CRITICAL / SAFE_MODE / RECOVERY | Mémoire |
| SM-4 | `capital_deployment/operational_state.py` | `OperationalState` / `OpState` | RUNNING / DEGRADED / HALTED | Mémoire + callbacks |
| SM-5 | `quant_hedge_ai/agents/risk/risk_governor.py` | `RiskGovernor` / `RiskState` | NORMAL / DEFENSIVE / RISK_OFF / RECOVERY / AGGRESSIVE | Mémoire |

---

### 1.3 Gates et bloqueurs (7 mécanismes)

| # | Fichier | Classe | Condition de blocage | Durée |
|---|---------|--------|----------------------|-------|
| G-1 | `quant_hedge_ai/agents/risk/global_risk_gate.py` | `GlobalRiskGate` | 5 conditions (session/drawdown/score/MTF/regime) | Par ordre |
| G-2 | `quant_hedge_ai/agents/risk/session_guard.py` | `SessionGuard` | 4 hard limits (drawdown/loss/streak/size) | Par session |
| G-3 | `quant_hedge_ai/agents/risk/portfolio_brain.py` | `PortfolioBrain` | 7 checks (exposition/corrélation/levier/count/direction) | Par trade |
| G-4 | `quant_hedge_ai/agents/risk/executive_override.py` | `ExecutiveOverride` | 5 niveaux (CLEAR→VETO), drawdown/daily_loss/streak | Dynamique |
| G-5 | `governance/execution_approval.py` | `ExecutionApproval` | Veto/SystemState/confidence/rate_limit/dedup | Veto persistant |
| G-6 | `quant_hedge_ai/agents/intelligence/no_trade_layer.py` | `NoTradeIntelligence` | Score rejet ≥ 50 (market/FOMO/signal/tactical) | Par éval / pause configurable |
| G-7 | `capital_deployment/phase_gate.py` | `PhaseGate` | Emergency stop actif ou violation sécurité | Par phase |

---

### 1.4 Arrêts d'urgence (3 mécanismes)

| # | Fichier | Classe | Critères | Reprise |
|---|---------|--------|----------|---------|
| E-1 | `capital_deployment/emergency_stop_manager.py` | `EmergencyStopManager` | 8 critères (drawdown/erreurs/API/connexion/anomalies/BlackBox/signature/KS) | `reset()` manuel |
| E-2 | `risk/circuit_breaker.py` | `CircuitBreaker` | Mémoire/latence/erreurs (seuils warnings/critiques) | Auto avec backoff |
| E-3 | `supervision/circuit_breaker_robust.py` | `ComponentCircuitBreaker` | Failures par composant (backoff exponentiel) | Auto, délais croissants |

---

### 1.5 Surveillance comportementale (2 mécanismes)

| # | Fichier | Classe | Déclencheur | Action |
|---|---------|--------|-------------|--------|
| W-1 | `quant_hedge_ai/agents/intelligence/self_awareness_engine.py` | `SelfAwarenessEngine` | Dérive performance/comportement/marché/infra | CAUTION→CRITICAL (niveau 4 = kill switch) |
| W-2 | `quant_hedge_ai/agents/risk/anomaly_governance.py` | `AnomalyGovernance` | 4 types anomalies (spike/score/drift/burst) | Suspension N cycles |

---

### 1.6 Le vrai interrupteur runtime

```python
# core/advisor_loop.py:1760
_halt_requested = {"value": False}
```

Ce dict mutable est la **seule vérification** qui suspend réellement la boucle principale (ligne 3225). Il est écrit par :

| Source | Ligne | Contexte |
|--------|-------|---------|
| `_on_stop_all()` | 1765 | Callback Telegram `/STOP_ALL` |
| `_on_close_all()` | 1769 | Callback Telegram `/CLOSE_ALL` |
| `_p10_emergency.halt_fn` | 1973 | EmergencyStopManager |
| `_on_op_halted()` | 2000 | OperationalState HALTED callback |

**Il est effacé uniquement par** `_on_resume()` (ligne 1773) — le callback `/RESUME` Telegram.

---

## 2. DOUBLONS IDENTIFIÉS

### D-1 — Triple implémentation du kill switch Telegram

`kill_switch.py`, `telegram_kill_switch.py` et `killswitch_hardened.py` font la même chose : écouter Telegram et exposer `is_halted()`. Deux ont le même nom de classe `TelegramKillSwitch`. Aucune coordination entre elles.

**Risque :** Un `/RESUME` sur KS-1 ne désactive pas KS-3 (qui persiste sur disque). Le système peut penser être repris alors que l'état disque dit `halted: True`.

### D-2 — Cinq machines d'états pour « le système est-il en trading ? »

SM-1 (`system/state_manager.py`) a 9 états. SM-2 (`system/state_machine.py`) en a 5. SM-3 (`runtime_state_machine.py`) en a 5. Aucune n'est l'autorité finale — la boucle consulte `_halt_requested` (un dict) pas une machine d'état.

**Collision de noms :** SM-1 et SM-3 exportent toutes deux une classe `SystemState`. `advisor_loop.py` importe :
```python
from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine, SystemState
```
mais `system/kernel.py` utilise `system/state_manager.py`. Ces deux `SystemState` ne sont pas compatibles.

### D-3 — Double circuit breaker

`risk/circuit_breaker.py` et `supervision/circuit_breaker_robust.py` implémentent des machines CLOSED/OPEN/HALF_OPEN et HEALTHY/UNSTABLE/DEGRADED/DISABLED respectivement. Pas de coordination. Un composant peut être OPEN dans l'un et HEALTHY dans l'autre.

### D-4 — Quatre mesures de drawdown concurrentes

| Mécanisme | Dénominateur | Déclenchement |
|-----------|--------------|---------------|
| `SessionGuard` | Équité en début de session | DD > 5% |
| `ExecutiveOverride` | Équité de référence interne | DD > 3/5/7/10% |
| `RiskGovernor` | Équité courante | DD > 3/6% |
| `EmergencyStopManager` | Phase limit × 1.5 | Variable par phase |

Ces quatre calculs peuvent retourner des valeurs différentes pour le même instant. Dans un scénario de drawdown 6%, RiskGovernor peut être en RISK_OFF pendant qu'ExecutiveOverride est en CAREFUL — logiques opposées sur la taille autorisée.

---

## 3. CONFLITS POSSIBLES

### C-1 — RESUME partiel

`/RESUME` Telegram efface `_halt_requested["value"]` et appelle `awareness_engine.reset()` et `op_state.reset()`. Il **ne réinitialise pas** :
- `EmergencyStopManager` (nécessite `reset()` explicite)
- `RuntimeStateMachine` (attend decay des erreurs)
- `system/state_machine.py` (nécessite `transition()`)
- `KillSwitchHardened` (état sur disque non effacé)

**Résultat :** La boucle principale reprend, mais les gates en aval (GlobalRiskGate vérifie `SessionGuard.is_halted()`) peuvent toujours rejeter tous les ordres silencieusement.

### C-2 — ExecutiveOverride dit « commandement suprême » mais n'est qu'un vote

`executive_override.py` doc : *"Le commandement suprême. Domine TOUTES les autres couches."*  
En réalité, dans `advisor_loop.py` il est traduit en `AgentVote` et soumis à l'arbitrateur V2 (ligne 1027–1029). KillSwitch, EmergencyStop et OperationalState peuvent halter indépendamment sans passer par EO.

### C-3 — SelfAwarenessEngine niveau CRITICAL déclenche un kill_switch, lequel ?

`self_awareness_engine.py` indique niveau 4 = "Kill switch + Telegram alert". Il appelle une référence interne (`_kill_switch_fn`) injectée à la construction. Si elle n'est pas injectée, l'action est silencieuse. Si elle est injectée avec KS-1 mais que la boucle écoute KS-2, le halt n'atteint pas la boucle.

### C-4 — PhaseGate et EmergencyStopManager : autorité sur le même flag

`PhaseGate.set_emergency(True)` ferme le gate. `EmergencyStopManager.trigger_stop()` déclenche son propre flag. Ni l'un ni l'autre n'écrit dans `_halt_requested`. Un EmergencyStop déclenché n'arrête la boucle que si son `halt_fn` est câblé (ligne 1973), ce qui n'est vrai que si le bloc conditionnel P10 est actif.

### C-5 — `system/state_machine.py` est un fantôme

`system_state.json` contient `trading_enabled` mais ce champ **n'est pas consulté** dans la boucle de trading principale. Il est mis à jour dans le heartbeat (ligne 4896) et sert uniquement au forensic. Le dashboard peut afficher `trading_enabled: false` alors que la boucle trade normalement.

---

## 4. AUTORITÉS CONCURRENTES

```
          ┌─────────────────────────────────────────────────┐
          │  Qui dit "le trading est autorisé" ?            │
          ├───────────────────┬─────────────────────────────┤
          │ _halt_requested   │ dict local advisor_loop.py  │ ← VRAI interrupteur
          │ kill_switch       │ KS-1 ou KS-2 (ambigu)      │ ← consulté L3225
          │ ExecutiveOverride │ VETO = size_factor 0.0      │ ← vote dans arbitrateur
          │ GlobalRiskGate    │ gate.allowed = False        │ ← vote dans arbitrateur
          │ OperationalState  │ OpState.HALTED              │ ← callback → _halt_requested
          │ RuntimeStateMachine│ CRITICAL / SAFE_MODE       │ ← consulté... où ?
          │ SessionGuard      │ is_halted()                 │ ← check dans GlobalRiskGate
          │ NoTradeIntelligence│ score ≥ 50                 │ ← vote dans arbitrateur
          │ EmergencyStop     │ is_emergency_active()       │ ← câblé si P10 actif seulement
          │ system/state_machine│ trading_enabled           │ ← NON consulté (forensic)
          └───────────────────┴─────────────────────────────┘
```

**Résultat :** Pour savoir si un trade est possible, il faut interroger au minimum 6 objets distincts. Il n'existe pas de méthode `can_trade()` globale à source unique.

---

## 5. RISQUES DE DIVERGENCE D'ÉTAT

| Scénario | Divergence |
|----------|-----------|
| `/RESUME` reçu alors que `EmergencyStop` actif | Boucle reprend, EmergencyStop non réinitialisé → prochaine vérification re-halte (si câblé) ou ignore (si non câblé) |
| `RuntimeStateMachine` → SAFE_MODE (10 erreurs) | Aucune écriture dans `_halt_requested` → boucle continue à trader |
| `KillSwitchHardened` persiste `halted: True` sur disque | Après restart, KS-3 est halted mais boucle utilise KS-1/KS-2 → trading reprend |
| `ExecutiveOverride.VETO` + `RiskGovernor.RISK_OFF` simultanément | Deux size_factor=0 appliqués indépendamment, taille finale = 0, mais via deux chemins différents, pas de trace unifiée |
| `system/state_machine.py` dit HALTED, boucle en RUNNING | Dashboard incohérent, alarmes fausses |
| `SessionGuard` halted, mais `_halt_requested=False` | GlobalRiskGate bloque silencieusement, boucle tourne en "zombie" (aucun trade mais aucune alerte de halt) |

---

## 6. ARCHITECTURE PROPOSÉE — SOURCE DE VÉRITÉ UNIQUE

### Principe

Un seul objet `TradingGate` est l'**unique source de vérité** sur l'autorisation de trading. Toutes les couches écrivent dans `TradingGate`. La boucle consulte uniquement `TradingGate.is_open()`.

### Structure proposée

```
core/trading_gate.py
```

```python
class HaltLevel(IntEnum):
    CLEAR = 0        # trading autorisé
    REDUCED = 1      # taille réduite (ExecOverride REDUCE/CAREFUL)
    SUSPENDED = 2    # trading suspendu (KillSwitch SAFE_MODE, NoTrade)
    HALTED = 3       # halt complet (SessionGuard, OperationalState)
    EMERGENCY = 4    # halt d'urgence (EmergencyStop, KS STOP_ALL)

class TradingGate:
    """Source de vérité unique pour l'autorisation de trading."""

    def is_open(self) -> bool:
        """False si level >= SUSPENDED."""

    def can_open_new_position(self) -> tuple[bool, str]:
        """False si level >= HALTED. Retourne raison."""

    def halt(self, source: str, level: HaltLevel, reason: str,
             duration_s: float | None = None) -> None:
        """N'importe quel mécanisme appelle halt() pour élever le niveau."""

    def resume(self, source: str, min_level: HaltLevel = HaltLevel.EMERGENCY) -> None:
        """Réduit le niveau si tous les locks >= min_level sont levés."""

    def size_factor(self) -> float:
        """Facteur de taille agrégé (0.0 si HALTED+)."""

    def snapshot(self) -> dict:
        """État complet pour dashboard et forensic."""
```

### Règles d'intégration

```
KillSwitch (tous)           → gate.halt("kill_switch", EMERGENCY)
EmergencyStopManager        → gate.halt("emergency", EMERGENCY)
OperationalState.HALTED     → gate.halt("operational_state", HALTED)
OperationalState.DEGRADED   → gate.halt("operational_state", REDUCED)
RuntimeStateMachine.CRITICAL→ gate.halt("runtime_sm", HALTED)
RuntimeStateMachine.SAFE_MODE → gate.halt("runtime_sm", SUSPENDED)
ExecutiveOverride.VETO      → gate.halt("exec_override", HALTED, duration_s=...)
SelfAwareness.DANGER        → gate.halt("self_awareness", HALTED, duration_s=30*60)
SelfAwareness.CRITICAL      → gate.halt("self_awareness", EMERGENCY)
NoTradeIntelligence.pause   → gate.halt("no_trade", SUSPENDED, duration_s=N*60)
SessionGuard.halt()         → gate.halt("session_guard", HALTED)
/RESUME Telegram            → gate.resume("telegram", min_level=HALTED)
```

### Vérification dans la boucle

```python
# advisor_loop.py — remplace les ~8 vérifications dispersées
if not trading_gate.is_open():
    snap = trading_gate.snapshot()
    log.critical("[gate] Trading suspendu — level=%s source=%s reason=%s",
                 snap["level"], snap["active_halts"][0]["source"], snap["reason"])
    _telegram(f"GATE CLOSED — {snap['level']}: {snap['reason']}")
    # attendre que le gate s'ouvre
    while not trading_gate.is_open():
        time.sleep(5)
    continue
```

### Persistance unifiée

Un seul fichier : `cache/startup/trading_gate_state.json`  
Remplace : `killswitch_state.json` + `system_state.json` + états en mémoire épars.

---

## 7. PLAN DE MIGRATION (PRIORITÉ DÉCROISSANTE)

### Phase A — Court terme (sans régression)

1. **Créer `core/trading_gate.py`** avec `TradingGate` et `HaltLevel`.
2. **Adapter `advisor_loop.py`** : remplacer le check `kill_switch.is_halted() or _halt_requested["value"]` par `trading_gate.is_open()`.
3. **Brancher KS-1** (kill switch actif) sur `trading_gate.halt()` via ses callbacks.
4. **Brancher `_on_op_halted`** sur `trading_gate.halt()`.
5. **`_halt_requested`** devient un alias `trading_gate.halt("_compat", EMERGENCY)` puis disparaît.

### Phase B — Consolidation kill switches

6. **Élire KS-3 (killswitch_hardened)** comme implémentation canonique (persistance disque + confirmation).
7. **Supprimer KS-1 et KS-2** une fois KS-3 câblé dans `advisor_loop.py`.
8. Vérifier que `/RESUME` appelle `trading_gate.resume()`.

### Phase C — Machines d'états

9. **Élire SM-1 (`system/state_manager.py`)** comme machine d'état canonique (9 états, transitions définies, `system/kernel.py` l'utilise déjà).
10. **Supprimer SM-2 (`system/state_machine.py`)** ou le réduire à un logger forensic (pas d'autorité).
11. **SM-3 (`runtime_state_machine.py`)** → renommer son `SystemState` en `RuntimeState` pour éviter la collision de noms.
12. **SM-4 (`operational_state.py`)** → ses transitions écrivent dans SM-1 et dans `TradingGate`, sa propre enum devient interne.

### Phase D — Drawdown

13. **Créer `core/drawdown_tracker.py`** : source unique, un seul dénominateur documenté.
14. `SessionGuard`, `ExecutiveOverride`, `RiskGovernor`, `EmergencyStopManager` lisent tous depuis `DrawdownTracker`.

### Phase E — Nettoyage

15. **Supprimer** le champ `trading_enabled` de `system_state.json` (fantôme).
16. **Documenter** `system/kernel.py` comme point d'entrée du panic (PANIC = EMERGENCY dans la nouvelle grille).
17. **Mettre à jour les tests** pour mocker `TradingGate` plutôt que chaque mécanisme séparément.

---

## 8. TABLEAU RÉCAPITULATIF — ÉTAT ACTUEL vs. CIBLE

| Dimension | État actuel | État cible |
|-----------|-------------|------------|
| Source de vérité trading | `_halt_requested` dict + `kill_switch.is_halted()` | `TradingGate.is_open()` |
| Kill switches | 3 implémentations non coordonnées | 1 (KillSwitchHardened) |
| Machines d'états | 5, noms conflictuels | 1 canonique (SM-1) + SM-3 renommée |
| Drawdown | 4 mesures indépendantes | 1 `DrawdownTracker` |
| `/RESUME` | Efface 2 flags sur 6+ | `TradingGate.resume()` notifie tous |
| Forensic dashboard | `system_state.json` non consulté | `trading_gate_state.json` = source unique |
| Collision `SystemState` | 2 classes du même nom | Renommée `RuntimeState` dans SM-3 |
| `executive_override` "suprême" | Non, c'est un vote | Documenté comme "size advisor" uniquement |

---

*Ce document ne propose aucune suppression immédiate. Toute migration suit les phases A→E dans l'ordre et est accompagnée de tests de régression sur la suite existante.*
