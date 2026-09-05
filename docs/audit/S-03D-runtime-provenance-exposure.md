# S-03D — Runtime Provenance Exposure

Statut : S-03D-R1 — remédiation des deux blockers scientifiques de la revue
MASTER appliquée (DIP: plus d'instanciation d'observateur inactif ;
BlackBox: dénominateur de refus canonique découplé du label
`decision_type`), en attente de nouvelle revue MASTER.
Parent : S-03 — Decision Provenance & Scientific Truth.
Précède : une future fenêtre de certification runtime bornée (post-merge,
hors scope de cette mission).

## 1. Pourquoi S-03D existe

S-03A/B/B-R1 ont instrumenté et remédié la provenance des décisions **côté
source** : `DecisionObservation`, `DecisionEventBus`, `RejectionStore`,
`RegretScheduler`, `DIPObserver` et `BlackBox` portent tous des compteurs de
provenance depuis ces missions.

S-03C a exécuté une certification **runtime** sur le SHA `38826da5...` et
conclu :

```
ZERO RUNTIME PROVENANCE DEFECTS OBSERVED
```

RejectionStore 565/565 packet_id et trace_id complets, 83/83 candidats Regret
avec provenance complète, accord inter-store 83/83 sur packet_id/trace_id/
first_blocker/side/symbol/score, zéro skip de provenance invalide observé sur
RejectionStore/Regret/DIP, zéro échec d'écriture BlackBox.

Mais la conclusion finale portait la mention :

```
S03_RUNTIME_INCONCLUSIVE
```

Le problème n'était **pas** un défaut de provenance — c'était que plusieurs
compteurs scientifiques déjà en mémoire (au sein du processus advisor_loop
en cours) n'avaient **aucun point d'observation externe sûr** : pas de
fichier, pas d'endpoint, rien à `cat`. Un auditeur externe ne pouvait
confirmer "zéro défaut" qu'en croisant des journaux JSONL et en supposant
que les compteurs en mémoire du processus correspondaient. C'est l'écart
**source instrumenté / runtime non exposé**.

S-03D ferme uniquement cet écart d'exposition. Elle ne crée aucun nouveau
compteur scientifique, ne modifie aucune sémantique de décision, de risque,
de régime ou de regret (ADR-0007, gel Phase II).

## 2. Ce qui existait déjà (préservé tel quel)

| Composant | Getter canonique | Compteurs |
|---|---|---|
| `DecisionObservation` | `get_provenance_failure_stats()` (module-level) | `missing_packet_id`, `missing_trace_id` |
| `DecisionEventBus` | `.get_stats()` sur le singleton `get_bus()` | `observations_published`, `listener_deliveries_submitted/succeeded/failed`, `deliveries_dropped_during_shutdown` |
| `RejectionStore` | `.stats()` sur l'instance live | `writes`, `errors`, `skipped_provenance` |
| `RegretScheduler` | `.stats()` sur l'instance live | `pending_candidates`, `horizons_evaluated`, `running`, `skipped_invalid_provenance` |
| `DIPObserver` | `.get_stats()` sur le singleton `DIPObserver.instance()`, **uniquement si `dip.bootstrap.is_running()`** (S-03D-R1, voir §3.2/§7) | `handler_count`, `skipped_invalid_provenance` |
| `BlackBox` | `.get_write_stats()` / `.get_load_stats()` | `write_attempts/successes/failures` |

Aucun de ces getters n'a été renommé ni dupliqué.

## 3. Ce que S-03D ajoute

### 3.1 Agrégat de provenance BlackBox (process-epoch)

`BlackBox.get_provenance_stats()` — nouveau, ajouté dans
`quant_hedge_ai/agents/intelligence/black_box.py`. Compte, **uniquement pour
les types de décision porteurs du contrat de provenance S-03**
(`TRADE_EXECUTED`, `TRADE_REFUSED`, `HOLD` — produits par
`record_decision()`) :

```
decision_records_persisted
packet_id_present / packet_id_missing
trace_id_present  / trace_id_missing
schema_v2         / schema_non_v2
packet_side_present / packet_side_missing
```

Et, dénominateur séparé, pour `TRADE_REFUSED` uniquement :

```
refused_records_persisted
canonical_first_blocker_present / canonical_first_blocker_missing
```

`SYSTEM_EVENT`, `POSITION_CLOSED`, `HALT_TRIGGERED`, `REGIME_CHANGE` (produits
par `record_system_event`/`record_position_closed`/`record_halt`/
`record_regime_change`) sont **exclus** de cet agrégat : ils n'ont
légitimement jamais de `packet_id`/`trace_id`, et les compter comme
"manquants" produirait un faux signal de défaut de provenance. Voir tests
`test_system_event_without_packet_id_not_counted_as_missing` et
`test_position_closed_not_provenance_applicable`.

### 3.2 Module d'exposition `observability/runtime_provenance_snapshot.py`

Compose et écrit un instantané sanitizé à partir des instances **LIVE**
passées en paramètre (`RuntimeProvenanceInputs`). N'instancie **jamais** un
`RejectionStore()`, `RegretScheduler()`, `DecisionEventBus()`,
`DIPObserver()` ou `BlackBox()` frais pour lire `.stats()` — un tel objet
n'aurait rien observé et produirait des zéros scientifiquement faux (mission
S-03D §2).

**S-03D-R1 (remédiation blocker 1)** : `DIPObserver.instance()` avait été
documenté à tort comme une "exception" sans risque parce que c'est un
singleton process-wide. C'est faux : `DIPObserver.instance()` est un pattern
create-if-missing (`if cls._instance is None: cls._instance = cls()`) — si le
DIP n'a jamais été démarré, l'appeler inconditionnellement **crée** un objet
frais que ce module n'a pas le droit de créer (exactement le défaut que ce
paragraphe prétend éviter pour les autres composants). Le wiring
`core/advisor_loop.py` interroge désormais l'état de lifecycle canonique du
DIP via `dip.bootstrap.is_running()` **avant** tout accès à `DIPObserver` :
si le DIP n'est pas démarré, `DIPObserver.instance()` n'est jamais appelé et
`dip_observer` reste `None` (bloc exposé : `{"status": "NOT_STARTED"}`, voir
§7). Seul un DIP réellement démarré fait récupérer le singleton existant et
exposer ses vraies `get_stats()`. Aucun démarrage, aucun enregistrement de
handler, aucune modification du lifecycle DIP n'est effectué par ce module.

### 3.3 Wiring dans `core/advisor_loop.py`

Deux points d'intégration, minimaux :

1. Juste après le bloc d'initialisation des listeners d'observabilité
   (event bus / RejectionStore / RegretScheduler, ~ligne 4600) : capture des
   références déjà existantes (`_decision_event_bus`, `_obs_rejection_store`,
   `_obs_regret_scheduler`, `black_box`) plus, uniquement si
   `dip.bootstrap.is_running()` renvoie `True`, `DIPObserver.instance()` (voir
   §3.2/§7 pour la remédiation S-03D-R1) — et création d'un
   `RuntimeProvenanceSnapshotWriter`.
2. Au point "Watchdog fin de cycle" existant (`watchdog.end_cycle(cycle)`) :
   appel de `writer.maybe_refresh(...)`, enveloppé dans un `try/except` qui
   avale toute exception (jamais de propagation vers la boucle de décision).

Aucun thread de fond n'a été ajouté — la frontière de fin de cycle
d'advisor_loop existait déjà et suffit comme point de rafraîchissement
périodique (mission §10 : préférer l'intégration la moins invasive).

## 4. Chemin et schéma du snapshot

Chemin par défaut :

```
databases/observation/runtime_provenance_snapshot.json
```

(surchargable via `RUNTIME_PROVENANCE_SNAPSHOT_PATH`). `databases/observation/`
est déjà le répertoire canonique d'état d'observation du dépôt (utilisé par
`core/topk_scheduler.py:_LATEST_TICK_PATH`, `observation/market_observer.py`).

Schéma (version 1) :

```json
{
  "schema_version": 1,
  "generated_at_utc": "2026-09-05T12:00:00Z",
  "process": {
    "pid": 12345,
    "invocation_id": null,
    "exposure_epoch_id": "…uuid4…",
    "uptime_s": 123.456
  },
  "decision_observation": {
    "status": "ACTIVE",
    "missing_packet_id": 0,
    "missing_trace_id": 0
  },
  "event_bus": {
    "status": "ACTIVE",
    "observations_published": 0,
    "listener_deliveries_submitted": 0,
    "listener_deliveries_succeeded": 0,
    "listener_deliveries_failed": 0,
    "deliveries_dropped_during_shutdown": 0
  },
  "rejection_store": {
    "status": "ACTIVE",
    "writes": 0,
    "errors": 0,
    "skipped_provenance": 0
  },
  "regret_scheduler": {
    "status": "ACTIVE",
    "pending_candidates": 0,
    "horizons_evaluated": 0,
    "running": true,
    "skipped_invalid_provenance": 0
  },
  "dip": {
    "status": "NOT_STARTED"
  },
  "black_box": {
    "status": "ACTIVE",
    "write_attempts": 0,
    "write_successes": 0,
    "write_failures": 0,
    "provenance": {
      "decision_records_persisted": 0,
      "packet_id_present": 0,
      "packet_id_missing": 0,
      "trace_id_present": 0,
      "trace_id_missing": 0,
      "schema_v2": 0,
      "schema_non_v2": 0,
      "packet_side_present": 0,
      "packet_side_missing": 0,
      "refused_records_persisted": 0,
      "canonical_first_blocker_present": 0,
      "canonical_first_blocker_missing": 0
    }
  }
}
```

Si un composant est indisponible (feature flag désactivé, module non
chargé), son bloc est réduit à `{"status": "UNAVAILABLE"}` — **jamais** de
compteurs numériques à zéro fabriqués à côté (voir §6).

## 5. Dénominateurs exacts

- `packet_id_present/missing`, `trace_id_present/missing`,
  `schema_v2/schema_non_v2`, `packet_side_present/missing` : dénominateur =
  `decision_records_persisted` (TRADE_EXECUTED + TRADE_REFUSED + HOLD
  persistés avec succès).
- `canonical_first_blocker_present/missing` : dénominateur =
  `refused_records_persisted`.

  **S-03D-R1 (remédiation blocker 2)** : ce dénominateur n'est **pas** le
  label `BlackBoxEntry.decision_type == TRADE_REFUSED`. Le classement
  `record_decision()` marque `TRADE_REFUSED` toute décision `actionable`
  qui n'aboutit pas à un `TRADE_EXECUTED` — y compris une décision
  `actionable=True, trade_allowed=True` mais sans résultat
  `futures_result.mode == "futures_demo"` (ex. exécution non tentée pour
  une raison hors provenance). Une telle décision peut légitimement n'avoir
  aucun `canonical_first_blocker` sans que ce soit un défaut de provenance ;
  compter ce cas comme refus canonique aurait fabriqué un
  `canonical_first_blocker_missing` scientifiquement faux. Le dénominateur
  réel — calculé dans `record_decision()` à partir du résultat d'analyse
  original, jamais rederivé de `decision_type` — est la sémantique
  canonique de refus : `actionable AND trade_allowed == False`. Ce booléen
  (`is_canonical_refusal`) est transmis explicitement à `_append()` puis
  `_record_provenance()`, uniquement sur la branche de succès de
  persistance disque (voir §8) ; il ne modifie ni `decision_type`, ni
  `trade_allowed`, ni le classement BlackBox existant — uniquement ce
  dénominateur d'exposition. Un `HOLD` ou un `TRADE_EXECUTED` sans
  first_blocker n'est **jamais** compté ici — la mission interdit
  explicitement d'appliquer l'exigence "first_blocker doit exister"
  globalement, car `canonical_first_blocker=None` est légitime pour une
  décision non refusée. Voir
  `tests/test_black_box_provenance.py::test_trade_allowed_non_futures_demo_labeled_refused_but_not_canonical`.

## 6. Sémantique process-epoch

Ces compteurs sont des compteurs **de durée de vie du processus**, jamais
initialisés depuis l'historique chiffré de la BlackBox (mission §9). Un
redémarrage du processus advisor_loop remet tous les compteurs de
`BlackBox.get_provenance_stats()` à zéro. Le snapshot rend cette frontière
explicite via :

- `process.pid`
- `process.invocation_id` (repris de la variable d'environnement
  `INVOCATION_ID` si le lifecycle du processus la définit — aucune
  fabrication multi-module ; `null` si absente)
- `process.exposure_epoch_id` — UUID généré **une seule fois**, au premier
  import du module d'exposition dans le processus. Ce n'est ni un
  `packet_id`, ni un `trace_id`, ni un `decision_id`, ni un `experiment_id` —
  c'est un identifiant de la couche d'exposition elle-même (mission §6).
- `process.uptime_s` — secondes écoulées depuis l'import du module.

Cela permet une future certification bornée sans aucune décryption
historique :

```
SNAPSHOT_START  (lire le fichier, noter pid + exposure_epoch_id + compteurs)
attendre un intervalle borné (le processus continue de tourner)
SNAPSHOT_END    (relire le fichier — vérifier même pid/exposure_epoch_id)
DELTA = END - START
```

Un changement de `pid` entre START et END signale un redémarrage du
processus pendant la fenêtre — la delta n'est alors plus valide sans
segmentation par epoch.

## 7. Sémantique UNAVAILABLE

Conformément à la préservation de la sémantique O-01 (UNAVAILABLE != ZERO,
STALE != HEALTHY) :

- Un composant jamais initialisé dans le processus (feature flag désactivé,
  échec d'import non bloquant) apparaît comme `{"status": "UNAVAILABLE"}`,
  sans aucun champ numérique.
- Un composant présent mais dont la lecture des stats échoue apparaît comme
  `{"status": "ERROR"}`.
- `DIPObserver` (**corrigé en S-03D-R1**) : la version initiale de ce
  paragraphe affirmait qu'appeler `DIPObserver.instance()` inconditionnellement
  et lire `handler_count=0` sur le singleton ainsi créé produisait un "zéro
  véridique". C'était faux : `DIPObserver.instance()` crée l'objet s'il
  n'existe pas encore (`if cls._instance is None: cls._instance = cls()`).
  Si le DIP n'a jamais été démarré, ces zéros n'étaient pas l'observation
  d'un composant vivant — ils appartenaient à un objet que le module
  d'exposition venait de fabriquer pour l'occasion, exactement la violation
  que ce document prétendait éviter. Le comportement correct : le wiring
  interroge `dip.bootstrap.is_running()` avant tout accès à `DIPObserver`.
  DIP non démarré → `DIPObserver.instance()` n'est **jamais appelé**, et le
  bloc exposé est `{"status": "NOT_STARTED"}` sans `handler_count` ni
  `skipped_invalid_provenance`. DIP réellement démarré → le singleton
  existant est récupéré (jamais créé par ce module — il l'a déjà été par
  `dip.bootstrap.start_dip()`) et ses vraies `get_stats()` sont exposées
  sous `"status": "ACTIVE"`. Voir tests
  `tests/test_s03d_dip_gating.py::test_inactive_dip_does_not_call_dip_observer_instance`,
  `::test_inactive_dip_snapshot_has_no_numeric_counters` et
  `::test_active_dip_exposes_real_live_singleton_stats`.

## 8. Durabilité BlackBox

Invariant préservé depuis S-03B-R1 : une entrée BlackBox n'entre dans la vue
en mémoire persistée (`self._entries`, donc `query()`) qu'**après** succès de
l'écriture disque chiffrée (`_append()`). L'agrégat de provenance S-03D suit
exactement le même invariant : `_record_provenance(entry)` n'est appelé que
dans la branche de succès de `_append()`, sous le même `_stats_lock` que
`write_successes`. Un échec d'écriture incrémente `write_failures` mais
**aucun** compteur de `get_provenance_stats()`. Voir
`tests/test_black_box_provenance.py::test_failed_persistence_does_not_increment_persisted_aggregate`.

Aucun `fsync` n'a été ajouté (hors scope, mission §8).

## 9. Frontière secrets

Le snapshot ne contient jamais : contenu de `.env`/`.env.secrets`, dump
`os.environ`, tokens, mots de passe, clés API,
`P10_CRYPTO_MASTER_SECRET`, clé dérivée, information SSH, tokens Telegram,
identifiants exchange. Le module utilise une whitelist explicite de champs
(`build_snapshot()` construit un dict littéral champ par champ) — jamais de
sérialisation générique d'un objet Python ni de `vars()`/`__dict__`.

`assert_no_secret_material()` grep le JSON sérialisé contre une liste de
sous-chaînes interdites (`secret`, `token`, `password`, `api_key`,
`credential`, `ssh`, `private_key`) et est exercée par
`tests/test_runtime_provenance_snapshot.py::test_snapshot_no_secret_material`.

## 10. Écriture atomique et cadence

Pattern identique à `observability/regret_scheduler.py::_save_spool()` (déjà
canonique dans ce dépôt) : écriture dans `<path>.tmp` puis `os.replace()`
vers le chemin final — jamais d'écriture directe, jamais d'append, jamais de
croissance JSONL.

Cadence cible : ~30-60s (`DEFAULT_MIN_REFRESH_INTERVAL_S = 30.0`), pilotée
par le rafraîchissement en fin de cycle advisor_loop plutôt que par un thread
dédié — un cycle typique dure largement plus de 30s ; `maybe_refresh()`
ignore silencieusement les appels trop rapprochés (retourne `False` sans
écrire).

## 11. Comment un futur auditeur runtime doit lire ce fichier

1. `cat databases/observation/runtime_provenance_snapshot.json` — sûr,
   secret-free, borné.
2. Vérifier `process.pid` et `process.exposure_epoch_id` restent stables
   pendant toute la fenêtre d'observation (sinon : redémarrage, traiter comme
   nouvel epoch).
3. Pour chaque bloc, vérifier `status` avant de lire les compteurs :
   `UNAVAILABLE`/`ERROR`/`NOT_STARTED` signifient "pas de donnée", jamais
   "zéro défaut".
4. Comparer deux instantanés à `SNAPSHOT_START` et `SNAPSHOT_END` du même
   epoch : `DELTA = END - START` pour chaque compteur donne l'activité de la
   fenêtre, sans jamais toucher au fichier BlackBox chiffré.
5. Le dénominateur de chaque taux (voir §5) doit toujours être cité
   explicitement dans un rapport de certification — jamais un compteur brut
   présenté sans son dénominateur.

## 12. Ce que S-03D ne fait pas

Aucun nouveau serveur HTTP, endpoint, port, mécanisme d'authentification,
commande Telegram. Aucune modification de `scripts/dashboard_api.py` ni
`infra/api/api_server.py`. Aucune modification de signal, stratégie,
feature, régime, décision Meta, risque, portefeuille, sizing, exécution,
mathématiques/seuils/horizons de regret, autorité d'apprentissage adaptatif,
architecture Telegram, Quant Observer, systemd, ou scripts de déploiement
VPS. Purement observabilité passive (ADR-0007).
