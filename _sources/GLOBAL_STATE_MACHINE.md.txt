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
| NORMAL → SAFE_MODE | commande manuelle | KillSwitch / Telegram |
| DEGRADED → HALTED | drawdown > 5% ou loss_streak ≥ 5 | AutoDecisionEngine |
| HALTED → RECOVERY | drawdown < 3% ET loss_streak ≤ 1 ET cooldown 1h | AutoDecisionEngine (RESUME_TRADING) |
| RECOVERY → NORMAL | 10 cycles propres consécutifs | SystemStateMachine.to_normal_if_stable() |
| RECOVERY → HALTED | nouvelle dégradation | AutoDecisionEngine |
| SAFE_MODE → NORMAL | commande manuelle | KillSwitch / Telegram |

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
