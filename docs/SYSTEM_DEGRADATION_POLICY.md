# SYSTEM DEGRADATION POLICY

> Version: 1.0 | Date: 2026-05-29 | Auteur: Phase 5 Chaos Testing
> Modules: `quant_hedge_ai/runtime/runtime_state_machine.py`, `fault_containment.py`

Ce document définit le contrat opérationnel de la machine d'état runtime.
Il répond à trois questions :
1. **Quand** le système change d'état ?
2. **Quoi** chaque composant doit faire dans chaque état ?
3. **Comment** revenir à NORMAL ?

---

## 1. Les 5 états et leurs sémantiques

| État | Sémantique | `can_trade` | `can_fetch` | `size_factor` |
|------|-----------|------------|------------|--------------|
| `NORMAL` | Fonctionnement nominal | ✅ | ✅ | 1.0 |
| `DEGRADED` | Erreurs isolées, système sous surveillance | ✅ | ✅ | **0.5** |
| `CRITICAL` | Multiples failures, lecture seule | ❌ | ✅ | 0.0 |
| `SAFE_MODE` | Blocage total, intervention requise | ❌ | ❌ | 0.0 |
| `RECOVERY` | Silence confirmé, retour progressif | ❌ | ✅ | 0.0 |

**Règle fondamentale :** les états sont strictement ordonnés. On ne passe jamais de DEGRADED directement à SAFE_MODE sans passer par CRITICAL. On ne revient jamais directement de SAFE_MODE à NORMAL.

---

## 2. Transitions automatiques

### 2.1 Transitions montantes (dégradation)

Toutes basées sur un compteur d'erreurs en **fenêtre glissante de 60 secondes**.

```
NORMAL → DEGRADED    :  erreurs ≥ 3  dans la fenêtre
DEGRADED → CRITICAL  :  erreurs ≥ 7  dans la fenêtre
CRITICAL → SAFE_MODE :  erreurs ≥ 10 dans la fenêtre
```

**Règle de non-skip :** SAFE_MODE ne quitte pas l'état même si de nouvelles erreurs arrivent.
Les transitions montantes sont **immédiates** dès que le seuil est franchi.

### 2.2 Transitions descendantes (recovery)

```
DEGRADED|CRITICAL → RECOVERY  :  0 erreurs dans la fenêtre ET silence ≥ 30s
SAFE_MODE         → RECOVERY  :  0 erreurs dans la fenêtre ET silence ≥ 60s
RECOVERY          → NORMAL    :  aucune erreur depuis 60s en RECOVERY
```

Les transitions descendantes sont **lazy** : elles ne se déclenchent que sur `report_ok()`.
Un background ticker appelant `report_ok()` toutes les 10s est recommandé.

### 2.3 Overrides manuels

| Méthode | Usage | Condition |
|---------|-------|-----------|
| `force_safe_mode(reason)` | KillSwitch, opérateur | Toujours disponible |
| `force_recovery()` | Post-incident confirmé | Vide le compteur d'erreurs |
| `reset()` | Tests uniquement | Remet à NORMAL immédiatement |

---

## 3. Comportement par composant dans chaque état

### 3.1 ExecutionEngine / PaperTradingEngine

| État | Comportement |
|------|-------------|
| NORMAL | Exécute normalement, taille nominale |
| DEGRADED | Exécute avec `size_factor = 0.5` (réduction automatique) |
| CRITICAL | Rejette tous les nouveaux ordres. Continue à surveiller les positions ouvertes |
| SAFE_MODE | Rejette tout. Positions ouvertes conservées (pas de liquidation forcée automatique) |
| RECOVERY | Rejette les nouveaux ordres. Surveille les positions ouvertes |

### 3.2 LiveSignalEngine / SignalEngine

| État | Comportement |
|------|-------------|
| NORMAL | Évalue normalement |
| DEGRADED | Évalue normalement (signal utilisé avec taille réduite par l'exécution) |
| CRITICAL | Continue d'évaluer (read-only). Résultats **non transmis** à l'exécution |
| SAFE_MODE | Suspendu (`can_fetch_data = False`). Retourne HOLD sans calcul |
| RECOVERY | Évalue normalement. Résultats en observation, non transmis |

### 3.3 PositionManager

| État | Comportement |
|------|-------------|
| NORMAL | Surveille TP/SL normalement |
| DEGRADED | Surveille normalement (taille du monitoring inchangée) |
| CRITICAL | Continue la surveillance TP/SL des positions **existantes**. Bloque `add_position()` |
| SAFE_MODE | Continue la surveillance TP/SL uniquement (les positions ouvertes doivent être protégées) |
| RECOVERY | Idem CRITICAL |

**Invariant critique :** JAMAIS fermer toutes les positions automatiquement lors d'une transition d'état. C'est une décision qui appartient à l'opérateur.

### 3.4 Dashboard / Monitoring / Telegram

| État | Comportement |
|------|-------------|
| Tous | Toujours en zone DASHBOARD (isolée). Les pannes du dashboard n'impactent jamais l'exécution |

Voir **Section 4 — Fault Containment Zones** pour le mécanisme d'isolation.

---

## 4. Fault Containment Zones

Les composants sont organisés en 5 zones d'isolation, par priorité décroissante.
Une panne dans une zone basse ne peut **jamais** bloquer une zone haute.

```
┌─────────────────────────────────────────────────────────────┐
│  ZONE EXECUTION   — timeout 200ms — échec = reject silencieux│
│    ExecutionEngine, OrderDeduplicator, PositionManager       │
├─────────────────────────────────────────────────────────────┤
│  ZONE RISK        — timeout 100ms — échec = ordre REJETÉ     │
│    SessionGuard, DrawdownGuard, RiskMonitor                  │
├─────────────────────────────────────────────────────────────┤
│  ZONE AI_SCORING  — timeout 500ms — échec = fallback HOLD   │
│    LiveSignalEngine, FeatureEngineer, RegimeDetector         │
├─────────────────────────────────────────────────────────────┤
│  ZONE MONITORING  — timeout 2s   — échec = silencieux        │
│    LatencyMonitor, MetricsBus, ErrorBus, EventJournal        │
├─────────────────────────────────────────────────────────────┤
│  ZONE DASHBOARD   — timeout 5s   — échec = totalement ignoré │
│    Telegram, Streamlit, dashboard_positions.py               │
└─────────────────────────────────────────────────────────────┘
```

**Règle d'isolation :** si une exception ou un timeout se produit dans la zone N,
elle est capturée, loggée (dans la zone MONITORING au niveau supérieur), et
`report_error()` est appelé sur la state machine. La zone N+1 (priorité supérieure)
n'est jamais affectée.

---

## 5. Recovery procedure opérationnelle

### Recovery automatique (incident de courte durée)

```
1. Les erreurs cessent
2. report_ok() est appelé régulièrement (heartbeat 10s)
3. Après 30s de silence → RECOVERY automatique
4. Après 60s stable en RECOVERY → NORMAL automatique
```

### Recovery manuelle (SAFE_MODE ou incident prolongé)

```
1. Opérateur identifie et résout l'incident
2. Appelle force_recovery() (via CommandCenter ou CLI)
3. Observe 60s de stabilité (dashboard RECOVERY)
4. Le système revient à NORMAL automatiquement
5. Si instable : rappeler force_safe_mode() et recommencer
```

### Recovery partielle (DEGRADED prolongé)

Si le système reste en DEGRADED > 10 minutes :
```
1. Vérifier fault_counts dans RuntimeStateMachine.snapshot()
2. Identifier le composant fautif (ex: "exchange_offline" × 8)
3. Résoudre le composant spécifique
4. Les erreurs cessent naturellement → transition RECOVERY → NORMAL
```

---

## 6. Thresholds recommandés par environnement

| Paramètre | Paper / Testnet | Production |
|-----------|----------------|------------|
| `degraded_threshold` | 3 | 5 |
| `critical_threshold` | 7 | 10 |
| `safe_threshold` | 10 | 15 |
| `window_s` | 60s | 120s |
| `silence_s` | 30s | 60s |
| `stability_s` | 60s | 120s |

En production, les seuils sont plus élevés pour éviter les faux positifs.
En testnet, les seuils serrés permettent de valider les transitions plus rapidement.

---

## 7. Métriques de surveillance

La state machine expose `snapshot()` à chaque tick :

```python
{
    "state": "DEGRADED",
    "can_trade": True,
    "size_factor": 0.5,
    "error_count_window": 4,
    "fault_counts": {"exchange_offline": 3, "ws_freeze": 1},
    "last_error_ago_s": 12.3
}
```

**Alertes recommandées :**
- `state == CRITICAL` → alert Telegram immédiate
- `state == SAFE_MODE` → alert Telegram critique + notification email
- `state == DEGRADED` pendant > 5 min → alerte modérée
- `error_count_window` croissant sans transition → anomalie (possible bug dans le compteur)

---

## 8. Ce que ce système ne fait PAS

**Ces comportements sont intentionnellement absents :**

- ❌ Fermeture automatique des positions à l'entrée en SAFE_MODE (risque d'aggravation)
- ❌ Retry automatique des ordres échoués (géré par OrderDeduplicator + Exchange)
- ❌ Escalade automatique vers un humain (hors scope système)
- ❌ Persistence de l'état runtime entre redémarrages (repart à NORMAL)
- ❌ Agrégation distribuée multi-process (fenêtre locale uniquement)

Le dernier point est le plus important : dans un contexte multi-process, la fenêtre
de la state machine est locale au processus. Un système de consensus distribué
(Redis, shared memory) sera nécessaire si plusieurs agents écrivent des ordres.

---

## 9. Références

| Module | Rôle |
|--------|------|
| `quant_hedge_ai/runtime/runtime_state_machine.py` | Machine d'état centrale |
| `quant_hedge_ai/runtime/fault_containment.py` | Isolation entre zones |
| `quant_hedge_ai/runtime/event_journal.py` | Traçabilité des transitions |
| `quant_hedge_ai/runtime/chaos_orchestrator.py` | Tests de pannes composées |
| `tests/chaos/` | 120 tests de résilience |
| `docs/SYSTEM_INVARIANTS.md` | Invariants systèmes complémentaires |
