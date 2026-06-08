# NEXT SESSION ROADMAP

> Généré le 2026-06-03. Basé sur l'audit SESSION_REPORT_20260603.md et ARCHITECTURE_STATE_20260603.md.  
> À mettre à jour après chaque session.

---

## ÉTAT DE DÉPART (ce qui est acquis)

- ✅ Gouvernance G0→G8-E formellement certifiée (160 tests, Z3 UNSAT)
- ✅ EIC v2 opérationnel (64 tests)
- ✅ ATC (GovernanceKernel) actif
- ✅ Paper trading MEXC livré (modules présents)
- ✅ VPS actif — advisor_loop P10 F-01
- ⚠️ I-14/I-15/I-16 Layer 3 : xfail (dette P1)
- ⚠️ MEXC câblage advisor_loop non confirmé
- ⚠️ Watchdog non déployé en service systemd

---

## CRITÈRES DE SUCCÈS DE LA PROCHAINE SESSION

1. **I-14/I-15/I-16 Layer 3** : 0 xfail dans tests/governance/ (actuellement 1)
2. **Paper trading actif** : première notification Telegram trade virtuel reçue
3. **Watchdog systemd** : `systemctl status watchdog_crypto` → active sur VPS
4. **MEXC connexion** : `MexcReader.spot.test_connection()` → status="ok" depuis VPS

---

## PHASE 1 — Fermeture dettes P1 (Sécurité Pipeline)

**Durée estimée :** 2h  
**Priorité :** BLOQUANTE pour live trading  
**Prérequis :** Aucun

### Objectif

Faire passer les 3 xfail `test_constitution_i14/i15/i16 Layer 3` en tests verts.

### Actions détaillées

#### A1 — I-14 Layer 3 : Exception agent → REJECTED (jamais fail-open)

**Fichier :** `core/advisor_loop.py` — fonction `analyze_symbol()`

**Problème :** Actuellement, si conviction_engine, portfolio_brain, awareness_engine, no_trade_layer, mistake_memory, executive_override, ou threat_radar lèvent une exception, le code peut retourner `None` → l'appelant interprète `None` comme "pas d'avis" → fail-open.

**Fix à implémenter :**
```python
# Chaque agent dans analyze_symbol() doit être wrappé :
try:
    conviction_result = conviction_engine.evaluate(packet)
    _conviction_ok = not conviction_result.blocks_trade()
except Exception as exc:
    log.error("[I-14] conviction_engine exception → REJECTED: %s", exc)
    packet.transition_to(DecisionState.REJECTED, actor="I14_guard", reason=f"agent_exception:{type(exc).__name__}")
    return _build_rejected_result(packet, "conviction_exception")
```

**Règle :** Toute exception agent → résultat de rejet canonique. Jamais `_agent_ok = True` après exception.

**Livrables :**
- `test_constitution_i14.py::TestPipelineFailClosed` Layer 3 → PASS
- Supprimer le marqueur `@pytest.mark.xfail` dans test_constitution_i14 Layer 3

#### A2 — I-15 Layer 3 : can_trade gate dans production DP

**Fichier :** `core/advisor_loop.py`

**Problème :** Le gate G1 est présent en pre-gate mais la validation `can_trade=False → packet.REJECTED` n'est pas câblée dans la production du DecisionPacket lui-même.

**Fix :**
```python
# En tête de produce_decision() ou analyze_symbol() :
authority = _get_authority()
if not authority.can_trade():
    if _dp is not None:
        _dp.transition_to(DecisionState.REJECTED, actor="G1_authority",
                          reason=f"can_trade=False state={authority.rsm_state()}")
    return _build_rejected_result(_dp, "governance_authority_blocked")
```

**Livrables :**
- `test_constitution_i15.py` Layer 3 → PASS

#### A3 — I-16 Layer 3 : trace_id obligatoire dans DP

**Fichier :** `core/advisor_loop.py`

**Problème :** trace_id est généré par `new_trace_id()` mais sa présence dans `packet.metadata["trace_id"]` n'est pas vérifiée avant toute transition vers EXECUTION_PENDING.

**Fix :**
```python
# Avant transition vers EXECUTION_PENDING :
if not packet.metadata.get("trace_id"):
    packet.transition_to(DecisionState.REJECTED, actor="G0_trace",
                         reason="trace_id_absent")
    return _build_rejected_result(packet, "missing_trace_id")
```

**Livrables :**
- `test_constitution_i16.py` Layer 3 → PASS
- 0 xfail dans `tests/governance/`

---

## PHASE 2 — Activation Paper Trading VPS

**Durée estimée :** 2h  
**Priorité :** P2 — paper trading actif  
**Prérequis :** Phase 1 recommandée mais non bloquante

### Objectif

VirtualPortfolio et MexcSimulator opérationnels sur VPS avec données réelles MEXC et notifications Telegram.

### Actions détaillées

#### B1 — Vérifier/câbler VirtualPortfolio dans advisor_loop

**Fichier :** `core/advisor_loop.py`

**Vérifier :**
1. VirtualPortfolio est-il instancié dans `main()` ?
2. `vp.start()` est-il appelé ?
3. Le bloc `if trade_ok:` appelle-t-il `vp.open_position(symbol, side, price, tp_pct, sl_pct, score, personality)` ?

**Si non, câbler :**
```python
# Dans main() après boot :
from paper_trading.virtual_portfolio import VirtualPortfolio
_vp = VirtualPortfolio(mexc_reader=_mexc_reader, telegram_fn=_telegram_alert)
_vp.start()

# Dans analyze_symbol() bloc trade_ok :
if _PAPER_TRADING_ENABLED and _vp is not None:
    _vp.open_position(symbol=symbol, side=side, price=current_price,
                      tp_pct=tp_pct, sl_pct=sl_pct,
                      score=score, personality=personality)
```

#### B2 — Configurer clés MEXC sur VPS

**Sur VPS 34.171.188.99 :**
```bash
# Dans .env ou /etc/environment :
MEXC_API_KEY=<clé_lecture_seule>
MEXC_API_SECRET=<secret>
VIRTUAL_CAPITAL_USD=100
```

**Vérification :**
```bash
python3 -c "from infra.mexc_reader import MexcReader; r = MexcReader(); print(r.spot.test_connection())"
# Attendu : [MEXC] OK | spot | lat=...ms | ...
```

#### B3 — Déployer watchdog_vps.py en service systemd

**Sur VPS :**
```bash
# /etc/systemd/system/watchdog_crypto.service
[Unit]
Description=Crypto AI Terminal Watchdog
After=network.target

[Service]
Type=simple
User=<user>
WorkingDirectory=/path/to/crypto_ai_terminal
ExecStart=/usr/bin/python3 watchdog_vps.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Déploiement :
systemctl daemon-reload
systemctl enable watchdog_crypto
systemctl start watchdog_crypto
systemctl status watchdog_crypto
```

#### B4 — Valider première notification paper trading

**Critère de succès :** Recevoir sur Telegram une notification du type :
```
[VP] OUVERT BTC/USDT LONG
  Prix : 65 430 USDT | Taille : 15.00 USD
  TP : 67 143 (+2.5%) | SL : 64 122 (-2.0%)
  Score : 75 | Stratégie : momentum
```

---

## PHASE 3 — Burn-in KPIs et décision P13

**Durée estimée :** Observation 7 jours (asynchrone — pas de code à écrire)  
**Priorité :** P3 — avant tout capital réel

### Objectif

Valider les KPIs burn-in sur 7 jours minimum avant de décider du passage live (Phase 2 Spot P13).

### KPIs à surveiller

| KPI | Seuil minimal | Seuil cible | Source |
|-----|--------------|-------------|--------|
| Win Rate | > 40% | > 50% | VirtualPortfolio |
| Sharpe (7j) | > 0 | > 0.5 | MexcSimulator |
| Max Drawdown (7j) | < 25% | < 15% | MexcSimulator |
| missed_win_rate | ≥ 55% | — | advisor_loop (P3 Buffer) |
| Trades N | ≥ 30 | ≥ 50 | advisor_loop |
| Uptime VPS | > 95% | > 99% | watchdog logs |

### Décision P13 (tableau)

| Condition | Décision |
|-----------|---------|
| Tous les KPIs cibles atteints (N≥50, Win>50%, DD<15%, Sharpe>0.5) | CAPITAL_ACTIF Phase 2 Spot |
| KPIs minimaux atteints (N≥30, Win>40%, DD<25%) | Prolonger burn-in 7j supplémentaires |
| missed_win_rate ≥ 55% ET N≥30 | Abaisser seuil score 60→58 |
| Drawdown > 25% sur 7j | Analyser causes, NE PAS libérer capital |

---

## PHASE 4 — Nettoyage de la dette technique (optionnel)

**Durée estimée :** 1.5h  
**Priorité :** P3-P4 — non bloquant

### Actions

#### C1 — Déplacer side-effects dans main()

**Fichier :** `core/advisor_loop.py`

Déplacer les 3 violations EIC de `compliant=False` → `compliant=True` :
- `os.makedirs("logs", exist_ok=True)` → dans `main()` avant FileHandler
- `load_dotenv(override=True)` → dans `main()` avant tout autre appel
- `logging.basicConfig(...)` → dans `main()`

**Impact :** EIC KNOWN_SIDE_EFFECTS passe à `compliant=True` pour les 3 entrées.

#### C2 — Corriger test_phase05_validation

**Fichier :** `tests/phase0/test_phase05_validation.py`

3 tests échouent car ils cherchent `advisor_loop.py` à la racine (avant refactoring vers `core/`).

**Fix :** Mettre à jour les références `ROOT / "advisor_loop.py"` → `ROOT / "core" / "advisor_loop.py"`.

#### C3 — Corriger test_restart_safety TestB4

**Fichier :** `tests/test_restart_safety.py`

2 tests `TestB4FullAdvisorRestart` échouent : positions ouvertes non persistées après restart simulé.

**Analyse requise :** Vérifier que `PositionReconciler` (P11-B) sauvegarde et restaure correctement les positions paper trading après restart.

---

## BACKLOG (sessions futures)

### B-01 — GovernanceAuditor intégration

**Fichier :** `core/advisor_loop.py`  
**Action :** Câbler `auditor.audit_cycle(result, rsm_state, cycle)` dans la boucle principale et logger les anomalies CRITICAL/FATAL.

### B-02 — TraceVerifier câblage

**Fichier :** `core/execution_trace.py`  
**Action :** Appeler `TraceVerifier.verify(trace)` à la fin de chaque cycle `analyze_symbol()` pour vérifier l'équivalence runtime↔modèle.

### B-03 — I-13 aliases dynamiques SEP

**Action :** Compléter la vérification des aliases dynamiques dans `ImportGraphChecker` pour les `importlib.import_module()` dynamiques.

### B-04 — Décision conscience comportementale

**Référence :** `project_decision_entropy.md`  
**Action :** Implémenter Decision Entropy + TRADING_STALLED/PARALYSED/ADAPTATION_INEFFECTIVE post burn-in validation.

### B-05 — MarketUniverseRanker KPIs dynamiques

**Action :** Passer les corrélations PortfolioBrain de statiques (hardcodées) à dynamiques (calculées sur données MEXC réelles rolling 30j).

---

## CHECKLIST AVANT DE COMMENCER

- [ ] Lire `ARCHITECTURE_STATE_20260603.md` (état réel du système)
- [ ] Vérifier que le VPS tourne (`ssh 34.171.188.99 && ps aux | grep advisor_loop`)
- [ ] Vérifier l'état Telegram (bot actif, channel joignable)
- [ ] Vérifier que `python -m pytest tests/governance/ -q` donne 160 passés, 1 xfail (baseline)
- [ ] Ne pas commencer la Phase 2 avant que Phase 1 soit verte

---

## CRITÈRES D'ARRÊT DE SESSION

Ne pas commencer une nouvelle feature si :
1. I-14 Layer 3 est toujours xfail — fermer avant tout
2. Tests governance/ regressent (< 160 passés)
3. Un nouveau test critique échoue sans explication

---

## DÉCISIONS EN SUSPENS

| Décision | Contexte | Critère |
|----------|---------|---------|
| Abaisser seuil score 60 → 58 | P3 Buffer | missed_win_rate ≥ 55% ET N ≥ 30 |
| CAPITAL_ACTIF Phase 2 Spot | P13 | Burn-in 7j + KPIs cibles |
| Intégrer Conviction dynamique | B-05 | Post burn-in validation |
| Live futures | P13 Phase 3 | Après validation complète Phase 2 |

---

*Document à mettre à jour en fin de chaque session. Conserver les versions précédentes en ajoutant la date (NEXT_SESSION_ROADMAP_YYYYMMDD.md).*
