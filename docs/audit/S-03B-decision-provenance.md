# S-03B — Contrat de provenance de décision

Statut : remédiation source-only, observability/audit uniquement (ADR-0007).
Ne modifie ni stratégies, ni signaux, ni seuils, ni sizing, ni math Regret.

## 1. Entités de décision

| Entité | Rôle | Où |
|---|---|---|
| `DecisionPacket` | Objet interne au moteur de décision, source de vérité pour le `side` (`LONG`/`SHORT`/`FLAT`) et le trail d'états | `core/decision_packet.py` |
| `DecisionObservation` | Snapshot immutable publié après chaque cycle, consommé par tous les observateurs | `observability/decision_observation.py` |
| `BlackBoxEntry` | Enregistrement indestructible, chiffré, de chaque décision/événement système | `quant_hedge_ai/agents/intelligence/black_box.py` |
| `RejectionRecord` | Sous-ensemble des observations = refus actionnables | `observability/rejection_store.py` |
| `RegretCandidate` | Sous-ensemble évalué a posteriori pour le regret | `observability/regret_scheduler.py` |

## 2. Identité — constitution

Ces identifiants sont **distincts et non-interchangeables** :

- `packet_id` : uuid4 du `DecisionPacket`, généré par le moteur. Identifiant canonique d'un cycle de décision au niveau moteur.
- `trace_id` : identifiant canonique du cycle produit par `advisor_loop.py` (I-16), injecté post-construction dans `dp.metadata["trace_id"]` — PAS un champ natif de `DecisionPacket`.
- `observation_id` : identifiant de l'objet `DecisionObservation` publié — voir §3 pour le format avant/après.
- `cycle` : entier, numéro de cycle de la boucle `advisor_loop`. Pas un identifiant unique global (se répète entre process/redémarrages) — usage: corrélation temporelle intra-session uniquement.
- `order_id` : identifiant de l'ordre exécuté (futures_result), distinct de tout ce qui précède — n'existe que si `trade_allowed=True` et exécution réussie.
- `BlackBox.decision_id` : `uuid4()[:8]` généré localement par `BlackBoxEntry`, **non corrélé** à `packet_id`/`trace_id`/`observation_id`. Historiquement le seul identifiant de la BlackBox — désormais complété (pas remplacé) par `packet_id`/`trace_id` (voir §6).

Aucun de ces identifiants ne doit être confondu avec un autre dans une jointure — la jointure canonique inter-systèmes est **`packet_id`** (voir §5).

## 3. `observation_id` — avant / après (S-03B item 2)

AVANT (non résistant aux collisions — 6 hex chars = 16.7M combinaisons tronquées) :
```python
short = (packet_id or str(uuid.uuid4())).replace("-", "")[-6:].upper()
obs_id = f"{date_str}-{sym_short}-{short}"
```

APRÈS (entropie complète, aucune troncature) :
```python
full_uuid = uuid.uuid4().hex
obs_id = f"{date_str}-{sym_short}-{full_uuid}"
```

Compatibilité : les lecteurs historiques (RegretScheduler dedup par dict-key, RejectionStore) ne valident aucun format d'`observation_id` — un ID ancien (6 hex) et un ID nouveau (32 hex) cohabitent sans erreur dans les mêmes fichiers/structures.

## 4. Vocabulaire `side`

Deux vocabulaires coexistent, jamais renommés :
- `DecisionObservation.side` / `RejectionRecord.side` : `"BUY" | "SELL" | "HOLD"`.
- `DecisionPacket.side` (enum `DecisionSide`) : `LONG | SHORT | FLAT`.

Mapping pur, fourni pour usage futur/optionnel (`observability/decision_observation.py`) :
```python
def normalize_side(value: str) -> str: ...          # LONG/SHORT/FLAT -> BUY/SELL/HOLD
def side_to_packet_vocabulary(value: str) -> str: ... # BUY/SELL/HOLD -> LONG/SHORT/FLAT
```
`BlackBoxEntry.packet_side` (nouveau champ optionnel) préserve le vocabulaire `LONG/SHORT/FLAT` d'origine à côté de `signal` (`BUY/SELL/HOLD`).

## 5. Populations — bornes strictement emboîtées

```
DecisionPacket (tout cycle du moteur)
  ⊇ DecisionObservation publiée (actionable AND NOT safe_mode — INCHANGÉ)
      ⊇ RejectionStore (actionable AND refused AND side∈{BUY,SELL,LONG,SHORT} AND provenance_valid — INCHANGÉ + nouveau skip provenance)
      ⊇ RegretScheduler candidates (dédup sur observation_id — INCHANGÉ)
```

Compteurs **non comparables** à ce qui précède (déjà documentés, hors scope de cette remédiation) :
- `gate_rejections.csv` (`observability/operator/domains/attrition.py` / `quant_hedge_ai/agents/risk/global_risk_gate.py`) : loggue CHAQUE invocation GlobalRiskGate (pass+fail), pas seulement les rejets.
- `activity_tracker.execution_ratio` : ratio d'activité, dénominateur différent.

## 6. `first_blocker` — source unique de vérité (S-03B item 3)

`DecisionObservation.first_blocker`/`all_blockers` (dérivés de `result["blockers"]`) est **canonique**. `RejectionStore` et `RegretScheduler` copient déjà ce champ depuis `DecisionObservation` — inchangé.

`BlackBox.record_decision()` — AVANT : calculait indépendamment `refused_by`/`passed_by` via son propre `_check()` interne, aucune référence à `result["blockers"]`.

APRÈS : ajoute `canonical_first_blocker`/`canonical_all_blockers` sur `BlackBoxEntry`, dérivés de la même source (`result["blockers"]`) que `DecisionObservation`. `refused_by`/`passed_by` sont **conservés tels quels** mais documentés comme diagnostic d'ordre interne à `BlackBox._check()`, jamais la vérité causale.

## 7. Missing-provenance guard (S-03B item 1)

Dans `build_from_result()` : si `packet_id` est vide (pas de packet, ou packet sans `packet_id`) :
- WARNING structuré loggué (`observability.decision_observation`).
- Compteur `get_provenance_failure_stats()["missing_packet_id"]` incrémenté (module-level, protégé par lock).
- `DecisionObservation.provenance_valid = False` sur l'instance résultante.

`RejectionStore.on_observation()` saute (avec son propre compteur `stats()["skipped_provenance"]` et un WARNING) toute observation avec `packet_id` vide ou `provenance_valid=False`, au lieu de la persister comme si elle était normalement jointe.

Les lecteurs de données historiques (fichiers JSONL déjà écrits) ne sont **pas** soumis à cette validation — seule la construction de nouvelles observations l'est.

## 8. Schéma `BlackBoxEntry` — avant / après (S-03B item 4)

Nouveaux champs optionnels, tous avec défaut sûr (compat ascendante — `BlackBoxEntry(**data)` sur une ligne historique sans ces clés continue de fonctionner) :

| Champ | Type | Défaut |
|---|---|---|
| `schema_version` | `int` | `1` (stampé `2` sur les nouveaux writes) |
| `packet_id` | `str` | `""` |
| `trace_id` | `str` | `""` |
| `experiment_id` | `Optional[str]` | `None` |
| `canonical_first_blocker` | `str` | `""` |
| `canonical_all_blockers` | `list` | `[]` |
| `packet_side` | `str` | `""` |
| `event_payload` | `Optional[dict]` | `None` |

## 9. Writers bypass — avant / après (S-03B item 5)

Trois writers écrivaient du JSON en clair directement dans `databases/black_box.jsonl` (que `BlackBox._append()` chiffre) :
- `cold_start/warmup_report.py::archive_to_black_box` (`event=WARMUP_COMPLETE`), utilisait `BLACK_BOX_PATH` (incohérent avec `BB_PATH` de `black_box.py` — corrigé).
- `cold_start/bypass_detector.py::_archive_bypass_event` (`event=BYPASS_DETECTED`).
- `certification/audit_trail_final.py::store_in_blackbox` (`type=P10_AUDIT_TRAIL`).

APRÈS : les trois routent via `BlackBox.record_structured_event(event_type, payload)` — écriture chiffrée canonique, tous les champs d'origine préservés dans `event_payload`.

## 10. Lecteur legacy-aware (S-03B item 6)

`BlackBox._ensure_loaded()` reconnaît désormais les 3 formes plaintext historiques (`event in {WARMUP_COMPLETE, BYPASS_DETECTED}`, `type == P10_AUDIT_TRAIL`) et les enveloppe en `BlackBoxEntry(decision_type=SYSTEM_EVENT, event_payload=<données brutes>)` au lieu de les laisser disparaître silencieusement (`TypeError` swallowed). Compteurs exposés via `get_load_stats()` : `encrypted_records`, `legacy_plaintext_records`, `invalid_records`, `unrecognized_records`.

## 11. Observabilité des échecs BlackBox (S-03B item 7)

`core/advisor_loop.py` : les deux `except Exception: pass` autour de `black_box.record_decision(...)` et `black_box.record_position_closed(...)` sont remplacés par un `except Exception as exc: log.warning(...)` avec contexte (`packet_id`, `trace_id`, `cycle`, `symbol`). Le pipeline ne plante jamais — comportement fonctionnel inchangé, seule la visibilité change.

`BlackBox._append()` expose `get_write_stats()` : `write_attempts`, `write_successes`, `write_failures`.

## 12. API BlackBox (S-03B item 8)

`infra/api/api_server.py` :
- `BLACK_BOX` pointait sous `infra/api/databases/black_box.jsonl` (jamais peuplé) — corrigé vers `databases/black_box.jsonl` à la racine repo, via `Path(__file__).resolve().parents[2]` (même convention que `visualization/api/burnin_api.py`).
- `read_jsonl()` faisait un `json.loads` brut, ne décryptait jamais rien. Remplacé pour les deux endpoints concernés (`/api/decisions`, `/api/raw/blackbox`) par `read_blackbox_records()`, qui instancie `BlackBox` et utilise son `.query()` + `.to_dict()` — même pipeline de déchiffrement que partout ailleurs dans le code.
- Posture sécurité : les champs renvoyés sont ceux de `BlackBoxEntry` (déjà exposés au dashboard interne) — aucun secret, aucune clé de chiffrement.

## 13. `decision_ledger.py` (S-03B item 10)

`audit/decision_ledger.py` — classification : **UNUSED**. Grep exhaustif (`grep -rn decision_ledger`) : aucun import/appel réel ailleurs dans le repo ; seule référence externe = prose de commentaire dans `project_os/test_scanner.py` (documentation d'un algorithme de résolution de module, pas un appel). Ne produit aucune donnée de décision actuellement lue par un chemin canonique — non modifié.

## 14. EventBus — sémantique et compteurs (S-03B item 9)

`DecisionEventBus` reste **best-effort / at-most-once**, sans retry, sans blocage — inchangé. Nouveaux compteurs exposés via `get_stats()` : `observations_published`, `listener_deliveries_submitted`, `listener_deliveries_succeeded`, `listener_deliveries_failed`, `deliveries_dropped_during_shutdown`.

## 15. S-03C — contrat de mesure runtime (à exécuter plus tard, PAS ici)

Checklist des mesures à produire lors de S-03C (aucune n'est exécutée par S-03B) :
- N décisions (BlackBox), N observations publiées (EventBus `observations_published`), N écritures BlackBox (`write_successes`/`write_failures`), N rejections persistées, N candidats Regret.
- Taux de jointure par `packet_id` entre BlackBox ↔ DecisionObservation ↔ RejectionStore.
- Taux de `packet_id`/`observation_id` manquants ou dupliqués.
- Taux de désaccord `first_blocker` : `DecisionObservation.first_blocker` vs `BlackBoxEntry.canonical_first_blocker` vs `refused_by[0]` (diagnostic).
- Taux de désaccord de normalisation `side` (`normalize_side(packet_side)` vs `signal`).
- Compteurs d'échec de livraison EventBus par listener.
- Compteurs d'enregistrements non appariés (BlackBox sans `packet_id` correspondant à une `DecisionObservation` connue, et inversement).
