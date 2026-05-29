# Plan d'accréditation 100% cybertechnique

## crypto_ai_terminal — Du système stateful au robot cybernétique autonome

**Référence** : commit `948a6bc` | **Tests** : 1 866 collectés / 1 866 verts / 13 skipped
**Phases couvertes** : P1-P9 + P10-A/B/C/D/E/F(infra) complètes | **Cible** : P10-F validation live (74+ jours)
**Date du plan** : 2026-05-27 | **Dashboard** : 38/43 modules certifiés — 88%

---

## Structure du plan (Annexe B — ordre d'exécution)

```
P10-A (Cold Start) ──> P10-B (Orchestrateur) ──> P10-C (Cryptographie)
                                                       │
                                                       v
P10-D (Stress Tests) <── P10-C terminé
       │
       v
P10-E (Supervision 24/7) ──> P10-F (Montée Capitale)
                                      │
                                      v
                               P10-G (Certification)
```

**Durées estimées** :
- P10-A : 3-4 jours | P10-B : 5-7 jours | P10-C : 3-4 jours | P10-D : 2-3 jours
- P10-E : 3-4 jours | P10-F : 72+ jours (7+14+21+30) | P10-G : 2-3 jours
- Total construction : ~20 jours | Total avec validation P10-F : ~92 jours

Vérification unifiée : `python certification/p10_checker.py`

---

## P10-A — Cold Start Protocol [COMPLETED — 7/7]

> Garantir que le système refuse d'être dangereux tant qu'il n'est pas prêt.
> Confiance opérationnelle, pas un timer.

### Modules certifiables

| Module | Code | Fragilité | Tests |
|--------|------|-----------|-------|
| `cold_start/cold_start_manager.py` | A-01 | ÉLEVÉE | [COMPLETED] |
| `cold_start/warmup_state_machine.py` | A-02 | ÉLEVÉE | [COMPLETED] |
| `cold_start/warmup_scenarios.py` | A-03 | MOYENNE | [COMPLETED] |
| `cold_start/warmup_metrics.py` | A-04 | MOYENNE | [COMPLETED] |
| `cold_start/warmup_invariants.py` | A-05 | ÉLEVÉE | [COMPLETED] |
| `cold_start/warmup_report.py` | A-06 | MOYENNE | [COMPLETED] |
| `cold_start/market_warmup_estimator.py` | A-07 | MOYENNE | [COMPLETED] |
| `cold_start/warmup_signer.py` | support A-01 | — | [COMPLETED] |
| `cold_start/bypass_detector.py` | support A-01 | ÉLEVÉE | [COMPLETED] |

### Critères de complétion

- [x] 8 états : BOOTING → FETCHING_MARKET_DATA → BUILDING_FEATURES → STABILIZING_REGIMES → VALIDATING_RISK → SHADOW_MODE → LIVE_READY / FAILED
- [x] 12 scénarios CS-01→CS-12 (3 must_fail, 6 must_not_reach_live, 3 success)
- [x] 13 invariants système (9 critiques, 4 warnings)
- [x] Faux positifs live_ready = 0 garanti (4 guards absolus MarketWarmupEstimator)
- [x] Tous artefacts signés HMAC-SHA256 (rapport, état, scénarios, estimator output)
- [x] Token LIVE_READY signé + assert_no_bypass() → BlackBox si contournement
- [x] Alerte durée > 30 min, alerte stuck > 5 min
- [x] 112/112 tests verts

### Commande de vérification

```
python -m pytest cold_start/tests/test_cold_start.py -v
```

---

## P10-B — Orchestrateur / Refactor [COMPLETED — 5/4 modules livrés]

> Pattern strangler : 4 composants runtime + boucle principale ≤ 500 lignes.
> advisor_loop.py reste en place (legacy) ; runtime/advisor_main.py est la nouvelle
> boucle propre qui le remplacera progressivement.

### Modules certifiables

| Module | Code | Rôle | Fragilité | Tests |
|--------|------|------|-----------|-------|
| `runtime/runtime_coordinator.py` | B-01 | Orchestration couches, cycle signé, timeout par couche | ÉLEVÉE | [COMPLETED] |
| `runtime/lifecycle_manager.py` | B-02 | start/stop/restart/health, journal signé HMAC | MOYENNE | [COMPLETED] |
| `runtime/execution_context.py` | B-03 | Contexte cycle immuable, cohérence capital, signé | ÉLEVÉE | [COMPLETED] |
| `runtime/system_state_bus.py` | B-04 | Pub/sub thread-safe, dead letter, saturation detection | ÉLEVÉE | [COMPLETED] |
| `runtime/advisor_main.py` | B-05 | Nouvelle boucle principale 404 lignes, 6 couches | CRITIQUE | [COMPLETED] |

### Critères de complétion

- [x] RuntimeCoordinator orchestre les couches avec timeout individuel par couche
- [x] Aucune décision orpheline : couche critique échouée → decision = None
- [x] LifecycleManager : journal append-only signé HMAC sur tous les événements
- [x] SystemStateBus : 11 canaux standards, livraison best-effort, dead letter queue
- [x] ExecutionContext : cohérence capital vérifiable, freeze() pour cycle immutable
- [x] advisor_main.py ≤ 500 lignes (actuel : 404), 6 couches enregistrées
- [x] Tests intégration end-to-end SIGNAL → EXECUTED via RuntimeCoordinator (20 tests)
- [x] 81/81 tests verts (61 unitaires + 20 intégration)

### Commande de vérification

```
python -m pytest runtime/tests/ -v
```

---

## P10-C — Cryptographie [COMPLETED — 6/6]

> Chiffrer les données patrimoniales critiques et signer chaque décision.
> Aucune clé en clair sur disque. Aucune décision sans signature vérifiable.

### Modules certifiables

| Module | Code | Protection | Tests |
|--------|------|------------|-------|
| `crypto/key_derivation.py` | support C | HKDF-SHA256 + PBKDF2-SHA256, 6 contextes | [COMPLETED] |
| `crypto/blackbox_encryption.py` | C-01 | AES-256-GCM, nonce aléatoire, AEAD | [COMPLETED] |
| `crypto/decision_signer.py` | C-02 | Ed25519, clé privée AES-256-GCM sur disque | [COMPLETED] |
| `crypto/api_key_vault.py` | C-03 | AES-256-GCM, zérolisation mémoire, rotation | [COMPLETED] |
| `crypto/secure_channels.py` | C-04 | TLS 1.3 minimum, certificate pinning SHA-256 | [COMPLETED] |
| `crypto/audit_trail.py` | C-05 | SHA-256 chaîné, tamper détecté en O(n) | [COMPLETED] |
| `crypto/tamper_evident_logs.py` | C-06 | HMAC-SHA256 chaîné, 10k lignes < 1 s | [COMPLETED] |

### Critères de complétion

- [x] AES-256-GCM (AEAD) : modification du ciphertext → InvalidTag automatique
- [x] Ed25519 : chaque DecisionPacket signé, clé privée chiffrée sur disque
- [x] API Key Vault : zérolisation bytearray après usage, rotation rekey() atomique
- [x] TLS 1.3 minimum : ctx.minimum_version = TLSv1_3, certificate pinning SHA-256
- [x] Audit trail SHA-256 chaîné : prev_hash dans chaque bloc, verify_chain() O(n)
- [x] HMAC-SHA256 chaîné : 10 000 lignes vérifiées < 1 s (test de perf inclus)
- [x] Master secret : HKDF-SHA256 depuis P10_CRYPTO_MASTER_SECRET, jamais en dur
- [x] BlackBox (`black_box.py`) : chaque entrée chiffrée AES-256-GCM sur disque, fallback migration plaintext
- [x] DecisionPacket : champs `ed25519_signature` + `signed_at`, méthodes `seal(signer)` / `verify_signature(signer)`
- [x] 89/89 tests verts (79 unitaires + 10 intégration système)

### Commande de vérification

```
python -m pytest crypto/tests/test_crypto.py -v
```

---

## P10-D — Stress Tests [COMPLETED — 7/7]

> Valider que le système reste correct sous pression : exchanges en panne, latence extrême,
> données corrompues, reprise offline 72h, fuzz 10 000 itérations.

### Modules certifiables

| Module | Scénario | Tests |
|--------|----------|-------|
| `tests/stress/test_d01_cold_start_scenarios.py` | D-01 : 12 scénarios CS-01→CS-12 automatisés | [COMPLETED] |
| `tests/stress/test_d02_exchange_failure.py` | D-02 : 1/2/tous exchanges down → dégradation contrôlée | [COMPLETED] |
| `tests/stress/test_d03_memory_corruption.py` | D-03 : corruption mémoire évolutive / checkpoints | [COMPLETED] |
| `tests/stress/test_d04_latency_cascade.py` | D-04 : latence API 5s/30s → timeout couche, pas de deadlock | [COMPLETED] |
| `tests/stress/test_d05_lm_studio_failure.py` | D-05 : LM Studio down/incohérent/timeout → fallback | [COMPLETED] |
| `tests/stress/test_d06_offline_recovery.py` | D-06 : reprise après 72h offline → données périmées rejetées | [COMPLETED] |
| `tests/stress/test_d07_fuzz_testing.py` | D-07 : fuzz 10 000 iter. invariants + 1 000 tick + 2 000 JSON | [COMPLETED] |

### Critères de complétion

- [x] D-01 : 12 scénarios CS-01→CS-12 verts, rapport JSON génerable, digest HMAC vérifié
- [x] D-02 : exchange(s) down → dégradation contrôlée, score réduit, jamais de faux LIVE_READY
- [x] D-03 : corruption mémoire évolutive → détectée, isolation, pas de crash
- [x] D-04 : timeout par couche respecté (≤ timeout_ms + overhead), pas de deadlock entre cycles
- [x] D-05 : LM Studio down/timeout → fallback activé, aucun blocage décision
- [x] D-06 : régime 72h périmé → bloqué ; positions inconnues → FAILED ; données fraîches → progressio
- [x] D-07 : 0 crash sur 10 000 snapshots aléatoires (WarmupInvariants), 0 crash sur 1 000 tick() fuzz
- [x] AIRouter : catch httpx.HTTPError → fallback en mode auto (fix robustesse)
- [x] _build_metrics() : safe_int/safe_float — robuste à None/str invalide
- [x] 86/86 tests verts

### Commande de vérification

```
python -m pytest tests/stress/ -q
```

---

## P10-E — Supervision 24/7 [COMPLETED — 7/7]

> Garantir que le système surveille sa propre santé et peut alerter + s'arrêter
> proprement sans intervention humaine, à n'importe quelle heure.

### Modules certifiables

| Module | Code | Rôle | Fragilité | Tests |
|--------|------|------|-----------|-------|
| `supervision/ops_watchdog_hardened.py` | E-01 | Watchdog daemon + heartbeat file + auto-restart subprocess + self-monitor | ÉLEVÉE | [COMPLETED] |
| `supervision/healing_actions.py` | E-02 | 5 actions certifiées + journal HMAC-SHA256 immuable | ÉLEVÉE | [COMPLETED] |
| `supervision/escalation_engine.py` | E-03 | 5 niveaux d'escalade + auto-escalade sur timeout | ÉLEVÉE | [COMPLETED] |
| `supervision/killswitch_hardened.py` | E-04 | KillSwitch Telegram ACK + état persistant JSON + daemon thread | CRITIQUE | [COMPLETED] |
| `supervision/recovery_playbooks.py` | E-05 | 4 playbooks (crash/exchange/LM/DB) + simulate + measure_recovery_time | ÉLEVÉE | [COMPLETED] |
| `supervision/proactive_alerts.py` | E-06 | 4 seuils proactifs + time_to_critical + anti-faux-positifs + cooldown | ÉLEVÉE | [COMPLETED] |
| `supervision/latency_baseline_monitor.py` | E-07 | Baseline 50+ samples + anomalie 3σ + historique 30j + persistance JSON | ÉLEVÉE | [COMPLETED] |

### Critères de complétion

- [x] E-01 : Watchdog daemon thread (ne bloque pas l'arrêt) + heartbeat file horodaté + auto-restart subprocess + self-monitor thread (relance watchdog mort) + max_restarts configurable + backoff
- [x] E-02 : 5 actions certifiées (restart_lifecycle, purge_cache, reinit_exchange, switch_lm_fallback, degrade_risk) + HealingJournal HMAC-SHA256 chaîné non modifiable + verify_integrity()
- [x] E-03 : 5 niveaux L1→L5 + auto-escalade si action échoue ou timeout + alerte à chaque palier + EscalationEngine.make_standard_escalation() factory
- [x] E-04 : KillSwitchHardened — daemon thread indépendant + état JSON persistant (survit aux crashes) + require_confirm=True (ACK dans 30s) + force_halt() programmatique + avg_response_time_ms()
- [x] E-05 : 4 playbooks (advisor_loop_crash / exchange_connection_lost / lm_studio_failure / database_error) + simulate() dry_run=True + measure_recovery_time() + last_result()
- [x] E-06 : 4 thresholds (drawdown/daily_budget/latency_ratio/exchange_error_rate) + time_to_critical() depuis rate + no_false_positives_on_stable() + cooldown anti-spam
- [x] E-07 : LatencyBaseline 50+ samples + is_anomaly() 3σ (cas std=0 géré) + historique 30 jours + save()/load() + _percentile() + baseline_age_hours() initialisé au record()
- [x] 92/92 tests verts (12+15+12+11+12+11+14 par module)

### Fixes robustesse inclus

- `_OperationBaseline.record()` : `_baseline_established_at` initialisé au premier franchissement de min_samples
- `_OperationBaseline.is_anomaly()` : cas std < 0.001 → synthetic_sigma depuis déviation absolue (pas de retour False systématique)

### Commande de vérification

```
python -m pytest supervision/tests/ -q
```

---

## P10-F — Montée en Capitale [INFRA COMPLETED — validation live requise]

> Validation progressive sur capital réel. Chaque palier doit durer le temps
> requis avant passage au suivant. Aucun raccourci.
>
> Infrastructure complète livrée (74/74 tests verts). La validation live (F-01→F-05)
> requiert l'exécution réelle sur les durées minimales.

### Modules infrastructure livrés (2026-05-27)

| Module | Code | Rôle | Tests |
|--------|------|------|-------|
| `capital_deployment/capital_throttle.py` | F-01 | Plafond capital par phase (F-01 = 100 EUR max) | [COMPLETED] |
| `capital_deployment/phase_kpi_tracker.py` | F-02 | Suivi win rate, Sharpe, drawdown, décisions signées | [COMPLETED] |
| `capital_deployment/phase_gate.py` | F-03 | Contrôle progression F-01→F-05, gate sécurité | [COMPLETED] |
| `capital_deployment/emergency_stop_manager.py` | F-06 | 8 critères d'arrêt immédiat + halt_fn | [COMPLETED] |
| `capital_deployment/phase_certifier.py` | F-05 | Certification HMAC-SHA256 par phase | [COMPLETED] |

### Paliers de validation live

| Palier | Durée | Capital | Critères | Statut |
|--------|-------|---------|----------|--------|
| F-01 | 7 jours | 1% / max 100 EUR | win_rate > 45%, Sharpe > 1.0, DD < 2% | [ ] EN ATTENTE |
| F-02 | 14 jours | 5% | win_rate > 45%, Sharpe > 1.2, DD < 4%, autonomie 7j | [ ] EN ATTENTE |
| F-03 | 21 jours | 25% | Sharpe > 1.5, DD < 8%, corrélation < 0.60 | [ ] EN ATTENTE |
| F-04 | 30 jours | 50% | Sharpe > 1.5, DD < 12%, P9 stable | [ ] EN ATTENTE |
| F-05 | Illimitée | 100% | Sharpe > 1.2, DD < 20%, autonomie 30j | [ ] EN ATTENTE |

### F-06 Emergency Stop — 8 critères testés

- [x] Drawdown > seuil phase + 50% → `DRAWDOWN_EXCEEDED`
- [x] 3 erreurs techniques consécutives → `CONSECUTIVE_TECH_ERRORS`
- [x] API key compromise → `API_KEY_COMPROMISED`
- [x] Exchange down > 5 min → `EXCHANGE_CONNECTION_LOST`
- [x] AnomalyGovernance > 3 suspensions/h → `ANOMALY_SUSPENSIONS`
- [x] BlackBox inaccessible > 2 cycles → `BLACKBOX_INACCESSIBLE`
- [x] Signature invalide → `INVALID_SIGNATURE`
- [x] KillSwitch déclenché → `KILLSWITCH_TRIGGERED`
- [x] Tous les critères ont des tests de déclenchement (pas de faux positifs sur métriques sûres)
- [x] reset() après révision humaine

### Critères de complétion infrastructure

- [x] CapitalThrottle : F-01 plafonné 100 EUR max, throttled_size(), is_within_limit()
- [x] PhaseKPITracker : win_rate, Sharpe annualisé (sqrt(252)), max_drawdown, unsigned_decisions
- [x] PhaseGate : gate_open/closed, can_advance(), advance(), violations(), time_remaining_days()
- [x] EmergencyStopManager : 8 critères, halt_fn appelé une seule fois, reset() préserve historique
- [x] PhaseCertifier : HMAC-SHA256, certify(force=), save()/load(), all_certified_to()
- [x] 74/74 tests verts (20+15+12+14+13 par module)

### Commande de vérification

```
python -m pytest capital_deployment/tests/ -q
```

---

## P10-G — Certification Finale [COMPLETED — 4/4 modules livrés]

> Checklist irreversible. P10-A à P10-F doivent être [COMPLETED].
> L'opérateur signe chaque point. Jugement humain requis.
>
> Infrastructure complète livrée (86/86 tests verts). La certification finale
> requiert la signature opérateur + validation live P10-F.

### Modules G-01→G-04 (2026-05-28)

| Module | Code | Rôle | Tests |
|--------|------|------|-------|
| `certification/module_certifier.py` | G-01 | Sceau COMPLETED par module (41 modules A-01→G-04) + SHA256 | [COMPLETED] |
| `certification/immutable_stamp.py` | G-02 | Scellement HMAC-SHA256 par module + détection drift | [COMPLETED] |
| `certification/doc_freeze.py` | G-03 | Gel documentaire (ARBORESCENCE, PLAN, scripts) signé | [COMPLETED] |
| `certification/audit_trail_final.py` | G-04 | Piste audit complète → BlackBox + AUDIT_TRAIL.json | [COMPLETED] |

### Modules support G (utilitaires)

| Module | Rôle |
|--------|------|
| `certification/prerequisite_checker.py` | Vérifie présence tous modules P10-A→F |
| `certification/live_kpi_auditor.py` | Audit KPI live WR/Sharpe/DD signé HMAC |
| `certification/operator_signoff.py` | Signature opérateur + persistance JSON |
| `certification/final_gate.py` | Gate go/no-go + CERTIFIED_{phase}.json |

### Prérequis techniques (automatiques)

| Critère | Vérification | Statut |
|---------|-------------|--------|
| P10-A Cold Start | 112/112 tests, 9 modules | [x] |
| P10-B Orchestrateur | 81/81 tests, 5 modules runtime | [x] |
| P10-C Cryptographie | 89/89 tests, 7 modules, 0 clé en clair | [x] |
| P10-D Stress Tests | 86/86 tests, 0 régression sous charge | [x] |
| P10-E Supervision | 92/92 tests, OpsWatchdog + Telegram actifs | [x] |
| P10-F Capital infra | 74/74 tests, 5 modules | [x] |
| P10-F Capital live | F-01→F-04 signés, 72+ jours validés | [ ] EN ATTENTE |

### Prérequis opérationnels (décision humaine)

| Critère | Valeur cible | Valeur mesurée | Signé |
|---------|-------------|----------------|-------|
| Shadow trading — durée | ≥ 7 jours continus | _____ jours | [ ] |
| Paper trading — Sharpe | > 0.8 | _____ | [ ] |
| Paper trading — max drawdown | < 8 % | _____ % | [ ] |
| Paper trading — win rate | > 52 % | _____ % | [ ] |
| Aucun FAILED non résolu | 0 FAILED actif | _____ | [ ] |
| KillSwitch testé en conditions réelles | Test manuel effectué | [ ] |
| Limites exchange configurées | `risk_limits.py` chargé | [ ] |
| MODE vérifié | `LIVE` ou `TESTNET` | _____ | [ ] |

### Décision opérateur (via OperatorSignoff)

```python
from certification.operator_signoff import OperatorSignoff
sf = OperatorSignoff(phase="F-01", operator="Mathieu")
sf.sign_phase(kpi_ok=True, mode="TESTNET", shadow_days=7, ...)
sf.save()  # -> certification/signoff_F-01.json
```

### Commande finale avant live

```
python certification/p10_checker.py --full
python certification/hash_verifier.py verify
python -c "from certification.final_gate import FinalGate; FinalGate(phase='F-01').run()"
```

---

## ANNEXE A — Carte des fragilités (référence)

| Composant | Valeur | Fragilité | Protection | Cryptage | Tests | 24/7 |
|-----------|--------|-----------|------------|----------|-------|------|
| API Key Vault (C-03) | CRITIQUE | EXTRÊME | AES-256 + isolation | OBLIGATOIRE | MAX | H24 |
| BlackBox Encryption (C-01) | CRITIQUE | EXTRÊME | AES-256 + HMAC | OBLIGATOIRE | MAX | H24 |
| ColdStartManager (A-01) | CRITIQUE | ÉLEVÉE | Signature + redondance | RECOMMANDÉ | MAX | H24 |
| SystemStateBus (B-04) | ÉLEVÉE | ÉLEVÉE | Canal chiffré | RECOMMANDÉ | MAX | H24 |
| Decision Signing (C-02) | ÉLEVÉE | ÉLEVÉE | ECDSA/Ed25519 | OBLIGATOIRE | MAX | H24 |
| Audit Trail (C-05) | ÉLEVÉE | MOYENNE | SHA256 | RECOMMANDÉ | STD | QUOTIDIEN |
| WarmupScenarios (A-03) | ÉLEVÉE | MOYENNE | Signature | OPTIONNEL | MAX | HEBDOMADAIRE |
| RuntimeCoordinator (B-01) | CRITIQUE | ÉLEVÉE | Redondance | RECOMMANDÉ | MAX | H24 |
| LifecycleManager (B-02) | ÉLEVÉE | MOYENNE | Journal non modifiable | OPTIONNEL | STD | H24 |
| MarketWarmupEstimator (A-07) | ÉLEVÉE | MOYENNE | Calibration | OPTIONNEL | STD | QUOTIDIEN |
| OpsWatchdog (E-01) | ÉLEVÉE | ÉLEVÉE | Auto-protection | OPTIONNEL | MAX | H24 |
| Telegram KillSwitch (E-04) | CRITIQUE | ÉLEVÉE | Redondance | OBLIGATOIRE | MAX | H24 |
| SelfHealingBot (E-02) | ÉLEVÉE | ÉLEVÉE | Non-dégradation | OPTIONNEL | MAX | H24 |
| WarmupInvariants (A-05) | CRITIQUE | ÉLEVÉE | Signature | RECOMMANDÉ | MAX | H24 |

---

## ANNEXE C — Dashboard de progression

| Phase | Modules | Certifiés | Statut |
|-------|---------|-----------|--------|
| P10-A Cold Start | 7 | 7/7 | [COMPLETED] |
| P10-B Orchestrateur | 5 | 5/5 | [COMPLETED] |
| P10-C Cryptographie | 7 | 7/7 | [COMPLETED] |
| P10-D Stress Tests | 7 | 7/7 | [COMPLETED] |
| P10-E Supervision | 7 | 7/7 | [COMPLETED] |
| P10-F Capital | 5 | 5/5 | INFRA COMPLETED — live en attente |
| P10-G Certification | 4 | 4/4 | [COMPLETED] — signature live en attente |
| **TOTAL** | **42** | **42/42** | **100 % — validation live seul blocant** |

---

**Accréditation complète = P10-A à P10-F [COMPLETED] + P10-G signé.**
