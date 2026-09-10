# Global State Machine — Crypto AI Terminal

> Référence architecture — états du système, transitions, recovery
> Créé : 2026-05-18 — Post-incident "silent halt 12 jours"

---

## États du système

```
NORMAL → DEGRADED → HALTED → RECOVERY → NORMAL
           ↘                    ↗
            SAFE_MODE (lecture seule)
```

| État | `trading_enabled` | Description |
|------|-------------------|-------------|
| `NORMAL` | ✅ | Opération normale |
| `DEGRADED` | ✅ | Trading actif, contraintes actives (taille réduite) |
| `HALTED` | ❌ | Arrêt forcé — risk limit ou gouvernance |
| `RECOVERY` | ✅ | Post-HALT, trading prudemment repris |
| `SAFE_MODE` | ❌ | Lecture seule — signaux sans exécution |

### Transitions autorisées

| De → Vers | Condition | Déclencheur |
|-----------|-----------|-------------|
| NORMAL → DEGRADED | loss_streak ≥ 3 | AutoDecisionEngine / ExecutiveOverride |
| NORMAL → HALTED | drawdown > 5% | AutoDecisionEngine |
| NORMAL → SAFE_MODE | seuil d'erreurs atteint (auto) OU requête `SAFE_MODE` nommée active | `RuntimeStateMachine` (`quant_hedge_ai/runtime/runtime_state_machine.py`). **Chemins source-prouvés invoqués en production** (`core/advisor_loop.py`) : (a) auto — `report_error()`, appelé à chaque cycle sur exception (`runtime_authority.report_error("cycle_exception")`), déclenche `_evaluate_degradation()` → SAFE_MODE dès que le compteur d'erreurs en fenêtre glissante atteint `safe_threshold` (10 par défaut) ; (b) nommé — `request_safe_mode(source, reason)`, appelé par le flag de boot `P6_SAFE_MODE` (verrouillage I-1 à l'initialisation) et par le callback de changement d'état SelfAwareness (`_on_awareness_change`, invoqué quand `state.level >= DangerLevel.WARNING`). **Chemins source-prouvés câblés, mais NON source-prouvés invoqués en production** : les callbacks du kill switch programmatique `_on_stop_all` / `_on_close_all` / `_on_safe_mode` (et `_on_resume`, côté sortie) sont enregistrés sur l'instance `KillSwitchHardened` process-locale (`kill_switch = runtime.TelegramKillSwitch(on_stop_all=_on_stop_all, ...)`, résolu vers `KillSwitchHardened` via `core/advisor_runtime_adapters.py:109`). `on_stop_all` n'est invoqué que par `KillSwitchHardened.force_halt()` ; `on_safe_mode` que par `force_safe_mode()` ; `on_resume` que par `force_resume()` — **aucune invocation non-test/non-archive de `force_halt()`, `force_safe_mode()` ou `force_resume()` n'a été trouvée**. `on_close_all` est stocké au constructeur mais n'est appelé par aucune méthode de `KillSwitchHardened` (aucun `force_close_all()` n'existe) : `_on_close_all` est du code mort, inatteignable quel que soit l'état du kill switch. Ne jamais décrire l'enregistrement d'un callback (`on_stop_all=_on_stop_all`, etc.) comme une invocation runtime. `force_safe_mode()` (sur `RuntimeStateMachine` ou `KillSwitchHardened`) reste par ailleurs une API de convenance : **aucun appelant runtime de production de cette méthode précise** n'a été trouvé — seul `core/invariants.py` l'appelle, mais uniquement en auto-vérification sur une instance jetable nouvellement construite, jamais sur le runtime réel (`runtime_authority`) ; ne pas en conclure « aucun appelant » au sens large pour la classe entière, puisque `report_error()`/`request_safe_mode()` ont des appelants runtime prouvés. Aucune commande Telegram ni procédure opérateur manuelle documentée ne déclenche l'un ou l'autre chemin dans le code actuel : `TelegramKillSwitch` est aliasé à `KillSwitchHardened` (`core/advisor_runtime_adapters.py:109`), qui n'a aucune interface Telegram (son propre docstring : « sans interface Telegram ») et ne crée aucun thread de polling (`start()` est un no-op, `is_thread_alive()` retourne toujours `False`). |
| DEGRADED → HALTED | drawdown > 5% ou loss_streak ≥ 5 | AutoDecisionEngine |
| HALTED → RECOVERY | drawdown < 3% ET loss_streak ≤ 1 ET cooldown 1h | AutoDecisionEngine (RESUME_TRADING) |
| RECOVERY → NORMAL | 10 cycles propres consécutifs | `SystemStateMachine.to_normal_if_stable()` (`system/state_machine.py`) — implémentation distincte de `RuntimeStateMachine` ; ne pas conflater les deux classes. |
| RECOVERY → HALTED | nouvelle dégradation | AutoDecisionEngine |
| SAFE_MODE → RECOVERY | dernière requête nommée retirée, OU (sans requête active) silence ≥ 2×`silence_s` confirmé par `report_ok()` | `RuntimeStateMachine.clear_safe_mode_request(source)` / `clear_all_safe_mode_requests()` transitionnent directement vers RECOVERY dès qu'il ne reste plus de requête nommée active — jamais vers NORMAL directement. **Invocation source-prouvée en production** : par `_on_awareness_change` quand le niveau SelfAwareness repasse sous `WARNING`. **Câblée, mais non source-prouvée invoquée en production** : `_on_resume` (`core/advisor_loop.py`) appelle aussi `clear_all_safe_mode_requests()`, mais `_on_resume` lui-même n'est atteignable que via `KillSwitchHardened.force_resume()`, dont aucune invocation non-test/non-archive n'a été trouvée. Sans requête active, `report_ok()` (appelé à chaque cycle en production, `runtime_authority.report_ok()`) peut aussi déclencher SAFE_MODE → RECOVERY une fois le silence requis écoulé. **`RuntimeStateMachine` ne définit aucune transition directe SAFE_MODE → NORMAL** — le retour à NORMAL depuis SAFE_MODE passe toujours par RECOVERY (voir la ligne suivante). |
| RECOVERY → NORMAL *(RuntimeStateMachine)* | `report_ok()` stable pendant `stability_s` (60s par défaut) après l'entrée en RECOVERY | `RuntimeStateMachine.report_ok()`, appelé en production à chaque cycle sans exception (`runtime_authority.report_ok()`, `core/advisor_loop.py`). Cette ligne est distincte de la ligne `RECOVERY → NORMAL` ci-dessus, qui décrit `SystemStateMachine` (classe différente) — les deux machines à états coexistent dans le code et ne partagent pas d'état. |
| *(hors RuntimeStateMachine)* `KillSwitchHardened.force_resume()` / `force_halt()` / `force_safe_mode()` | appel direct | Ces méthodes mutent l'état interne du kill switch durci (`supervision/killswitch_hardened.py`, docstring : « sans Telegram ») et invoquent son callback (`on_resume`/`on_stop_all`/`on_safe_mode`) si défini — ce ne sont **pas** des transitions de `RuntimeStateMachine` : `_on_resume` (le callback câblé côté `advisor_loop.py`) appelle séparément `runtime_authority.clear_all_safe_mode_requests()` sur l'instance `RuntimeStateMachine`, mais `force_resume()` lui-même ne touche que l'état `KillSwitchHardened`. Ne pas conflater les deux états. Aucun appelant runtime de production de `force_resume()`/`force_safe_mode()` n'a été trouvé pour `KillSwitchHardened` — seuls des fichiers `tests/` y font appel ; le légataire `TelegramKillSwitch.force_resume()` (`supervision/telegram_kill_switch.py`) n'a également aucun appelant runtime de production. |

### Règle fondamentale
> **Toute transition HALTED doit avoir une condition de sortie explicite.**
> Un état HALTED sans timeout ou recovery condition = deadlock autonome.

---

## Sources de vérité — hiérarchie

```
1. EXCHANGE (Binance)      ← source de vérité absolue
        ↓ reconcile/h
2. PositionManager         ← état interne runtime
        ↓ sync/cycle
3. system_state.json       ← état gouvernance persisté
        ↓ lecture
4. tracker/trade_log.sqlite ← historique audit
        ↓ append-only
5. paper_trades.jsonl      ← cycles complets entry+exit
```

**Règle :** tout le reste dérive de l'exchange. Jamais l'inverse.

---

## Fichiers d'état — localisation

| Fichier | Contenu | Fréquence MAJ |
|---------|---------|---------------|
| `databases/system_state.json` | État machine, halt reason, heartbeat | Chaque cycle |
| `databases/live_snapshot.json` | Snapshot cycle courant (signaux, positions) | Chaque cycle |
| `databases/positions_snapshot.json` | Positions ouvertes runtime | Chaque ouverture/fermeture |
| `databases/paper_trades.jsonl` | Cycles complets entry+exit avec PnL | Sur trade OPEN/CLOSE |
| `databases/cycle_data.jsonl` | Historique cycles (rotation à 50MB) | Chaque cycle |
| `logs/decisions.jsonl` | Décisions autonomes (AutoDecisionEngine) | Sur décision |
| `logs/execution_audit/audit.jsonl` | Audit ordres (slippage, latence, fees) | Sur ordre |
| `databases/shadow_execution/shadow_log.jsonl` | Shadow trades (jamais envoyés) | Sur signal ≥ seuil |

---

## Lifecycle d'un trade — étapes obligatoires

```
SIGNAL_CREATED          → LiveSignalEngine produit score ≥ 70
        ↓
REGIME_VALIDATED        → RegimeDetector confirme la cohérence
        ↓
NO_TRADE_CHECK          → NoTradeLayer valide (pas FOMO, qualité marché OK)
        ↓
CONVICTION_EVALUATED    → ConvictionEngine note MEDIUM/HIGH/VERY_HIGH
        ↓
RISK_GATE_CHECKED       → GlobalRiskGate (8 checks portefeuille)
        ↓
SESSION_GUARD_OK        → SessionGuard vérifie drawdown/streak session
        ↓
EXECUTIVE_OVERRIDE_OK   → ExecutiveOverride niveau ≤ CAREFUL
        ↓
ORDER_VALIDATED         → ExchangeConstraints (qty, notional, precision)
        ↓
ORDER_SUBMITTED         → ExecutionEngine envoie à l'exchange
        ↓
POSITION_OPENED         → PositionManager enregistre + snapshot
        ↓ paper_trading/recorder.py → record_open()
TRACKER_UPDATED         → tracker_open_position()
        ↓
[position vivante — PositionManager surveille TP/SL/trailing]
        ↓
EXIT_TRIGGERED          → raison : take_profit / stop_loss / trailing / time_stop
        ↓
EXIT_SUBMITTED          → ordre de fermeture envoyé
        ↓ paper_trading/recorder.py → record_close()
TRADE_ARCHIVED          → tracker_finalize_position() + PnL calculé
        ↓
POSTMORTEM              → DecisionQualityEngine (VALIDATED/UNLUCKY/LUCKY/MISTAKE)
        ↓
LEARNING                → MistakeMemory + RegretEngine mis à jour
```

**À chaque étape :** log obligatoire avec `trace_id = packet_id`.

---

## Alertes critiques — matrice

| Alerte | Condition | Action système | Notification |
|--------|-----------|----------------|--------------|
| `STALL` | Signaux présents, 0 ordre depuis 30 min | Log WARNING | Telegram |
| `EXCHANGE_DOWN` | exchange_sync_ok = False | Log WARNING | Telegram |
| `HALTED` | state = HALTED | Blocage ordres | Telegram (à câbler) |
| `RECONCILE_DRIFT` | Ghost/orphan positions détectées | Log CRITICAL | Telegram |
| `STOP_TRADING` | drawdown > 5% | state → HALTED | Log CRITICAL |
| `RESUME_TRADING` | Recovery conditions remplies | state → RECOVERY | Log INFO |

---

## Post-incident : "silent halt 12 jours" (2026-05-05 → 2026-05-17)

### Chronologie
- **2026-05-05 06:44** — `AutoDecisionEngine` déclenche `STOP_TRADING` (drawdown > 5%, loss_streak = 4)
- **2026-05-05 → 2026-05-07** — `STOP_TRADING` se répète **35 fois** à chaque cycle car la condition reste vraie et qu'il n'existe pas d'état "already halted"
- **2026-05-07 → 2026-05-17** — Gel complet. `trading_enabled = False` en mémoire. Decision_packets continuent (1972 REJECTED). Aucune exécution.
- **~2026-05-17** — Redémarrage VPS. Config in-memory repart à défaut (`trading_enabled = True`). Trading reprend sur NEAR/USDT, INJ/USDT.

### Root cause
`STOP_TRADING` existait. `RESUME_TRADING` n'existait pas. État non persisté → gel jusqu'au prochain redémarrage.

### Fixes appliqués
1. `RESUME_TRADING` ajouté dans `AutoDecisionEngine` avec cooldown 1h + conditions de recovery
2. `_halted_at` persisté dans config pour survie aux redémarrages
3. `system/state_machine.py` — état global persisté dans `databases/system_state.json`
4. Heartbeat stall detection dans `advisor_loop.py` (alerte Telegram si stall > 30 min)
5. `system/position_reconciler.py` — réconciliation exchange vs interne toutes les heures

---

## Doctrine de gouvernance

> Toute décision de gouvernance **DOIT** avoir :
> 1. **Condition d'entrée** explicite
> 2. **Condition de sortie** explicite
> 3. **Timeout** ou TTL
> 4. **Chemin d'escalade** si non résolue
>
> Un état sans condition de sortie = deadlock autonome.
