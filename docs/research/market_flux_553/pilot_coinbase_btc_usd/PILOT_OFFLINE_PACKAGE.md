# Pilote Coinbase Advanced BTC-USD spot — paquet hors réseau (#553)

**Verdict : `OFFLINE_READY`, avec les limites de la section 8.** Source seulement : rien n'a été fusionné,
déployé, démarré ni appelé. Aucun appel à Coinbase, aucun accès VPS. #286 ACTIVE, #397 HOLD, #374 PARKED.
Le contrat Flux garde `synthetic=true` : une capture n'entre pas dans Flux (décision ultérieure, GO séparé).

## 1. Base et identité du paquet testé

| Élément | Valeur |
|---|---|
| Base | `main@2009c62f94f053db4f170b6a13065cc018618b7a` |
| Référence auditée (crypto-restore-01) | `2009c62f94f053db4f170b6a13065cc018618b7a` : **identique à main, aucun écart de source** |
| Empreinte du paquet (`package_digest`) | `a44c5c83288a5873f28cf115d73c0006aa50a72b8aa587660be4d7258cf82538` |
| Commit de la branche | voir la PR (le SHA ne peut pas figurer dans le commit qu'il identifie) |
| Python | tests passés sous 3.13 (local) et 3.11 (cible CI) |

`package_digest` = SHA-256 des octets de tous les `.py` de `observability/flux_collection_pilot/` (chemins triés) ;
il est ce qu'un manifeste de collecte doit épingler. Il ne couvre ni l'interpréteur ni les bibliothèques.
La release du VPS n'a pas été inspectée (hors périmètre) : elle contient `2009c62f…`, **pas ce paquet**. Toute collecte
exige donc une release qui l'intègre, épinglée par sa propre exception #286.

## 2. Plan exécuté (fichiers, dépendances, commande de test)

Nouveau paquet isolé `observability/flux_collection_pilot/` (stdlib seule ; `websockets` n'est importé qu'au moment
d'ouvrir une connexion live autorisée). Dépendances de code : seulement `observability.market_venues.pilot.capture`
(`Instant`, `SystemClock`, déjà en place pour #539). Aucun fichier existant modifié.

| Fichier | Rôle |
|---|---|
| `protocol.py` | cible fixe, plafonds (`Caps`, un manifeste ne peut que les abaisser), motifs d'arrêt, `package_digest` |
| `transport.py`, `simulated.py` | interface injectable ; transport simulé scripté, horloge simulée, générateur de flux synthétique |
| `live_gate.py`, `live_transport.py` | verrou live avant DNS/socket ; transport WebSocket (non exécuté) |
| `runner.py` | automate de collecte borné (2 connexions, coupure 60 s, plafonds, arrêts de sécurité) |
| `store.py` | stockage privé, budget d'octets exact + réserve, reçus durables, vérificateur |
| `messages.py`, `sequence.py` | décodage tolérant sur le temps, quatre domaines de compteur candidats |
| `analysis.py` | analyse hors ligne : séquences, heures, carnet par session, trades dédupliqués, empreintes |
| `memory.py` | garde mémoire vérifiable |
| `exactjson.py` | copies locales de 3 utilitaires Flux, épinglées par test (voir §3) |
| `__main__.py` | CLI : `demo`, `replay`, `verify`, `live` (verrouillé) |
| tests | `tests/flux_collection_pilot/` (113 tests) |
| gabarits | `OPERATOR_COLLECTION_MANIFEST.template.json`, `SYNTHETIC_FINAL_RECEIPT_EXAMPLE.json` |

```
python -m pytest -q tests/flux_collection_pilot                       # le paquet (≈ 9 s)
python -m pytest -q tests/market_flow tests/market_venues tests/cross_stack/test_market_flow_integration.py \
                    tests/flux_collection_pilot                       # + régressions Flux
```

## 3. Réutilisé / non réutilisé, et pourquoi

- **Non importé : le cœur Flux (`observability/market_flow`).** Un test existant
  (`test_package_has_no_transport_clock_write_or_float_and_nobody_imports_it`) n'admet que le reader/API comme
  consommateur ; je l'ai respecté au lieu d'étendre sa liste. Trois utilitaires (JSON strict, RFC 3339 → ns, contexte
  décimal exact) sont donc **copiés** dans `exactjson.py` et épinglés à leurs originaux par un test différentiel
  (`test_pinned_copies.py`), selon le précédent de `interval.py`.
- **`L2Connection` non réutilisé** : il suppose un compteur commun à la connexion (A-SEQ-CONN, précisément l'ambiguïté à
  conserver), refuse un message sur heure invalide au lieu de la recenser, et le pilote doit analyser par session et canal.
- **`TradeLedger` non réutilisé** : il garde la première variante d'un conflit ; la mission exige d'exclure *toutes* les variantes.
- Réutilisés : `Instant`/`SystemClock` (#539), les conventions du `RunStore` (répertoire exclusif 0700, budget, réserve).

## 4. Lecture documentaire (2026-11-05) et incertitudes conservées

Extraits obtenus par un outil de lecture qui **résume** les pages (pas d'octets bruts datés ni hachés) : ils ne
suffisent pas à attester A-LAYOUT. L'opérateur devra joindre des extraits datés/hachés au manifeste.

- **`sequence_num` : ambiguïté confirmée, non levée.** Le guide général : « increasing integer values *for each product* ».
  L'AsyncAPI : « *Per-connection* message sequence number ». Le paquet suit donc quatre candidats en parallèle
  (`PER_CONNECTION`, `PER_CHANNEL`, `PER_PRODUCT`, `PER_CHANNEL_PRODUCT`) : chacun est **réfuté** ou non réfuté par
  les données, jamais « confirmé ».
- `heartbeats` : AsyncAPI = « every second », même hôte que les autres canaux ; le guide dit que ce canal est sur le
  endpoint *user* (`advanced-trade-ws-user`), avec `advanced-trade-ws` en repli. **Non tranché** : si les heartbeats
  ne sont pas servis sans authentification sur l'hôte prévu, la collecte s'arrêtera à 5 s (`SILENCE_HEARTBEAT`), sans dommage.
- `market_trades.side` = « The maker's side of the trade » (AsyncAPI). Le paquet garde la valeur brute et ne dérive un
  côté agresseur que par une inversion explicite, testée et marquée `attested=false`.
- Abonnement public sans `jwt`, un message par canal, déconnexion si aucun abonnement sous 5 s ; `l2_data` : quantité
  absolue, « 0 » = niveau retirable ; `market_trades` groupe 250 ms ; `event_time` L2 = « as recorded by the trading engine » ;
  `timestamp` = heure serveur d'envoi.
- **Aucune taille maximale de message documentée.** Le plafond de 512 000 octets (celui du prototype L2) est une
  hypothèse : un snapshot BTC-USD plus gros provoquerait `MESSAGE_TOO_LARGE` dès le début (arrêt sûr, mais collecte perdue).
- Admissibilité régionale et conditions d'usage : **non lues** ; prérequis humain avant tout appel (§9).

## 5. Limites réellement appliquées et à configurer

| Limite | Statut | Mécanisme |
|---|---|---|
| 2 connexions | **Appliquée en code** | `ConnectionBudget` ; aucune reconnexion implicite (le transport n'en a pas) |
| Coupure à 60 s | **Appliquée** | horloge monotone ; seulement si la session 1 est saine (≥ 1 heartbeat et ≥ 1 snapshot) |
| 180 s globales | **Appliquée** | monotone ; vérifiée avant chaque `recv`, dont le délai est borné par le temps restant (le transport live doit l'honorer) |
| 100 000 messages | **Appliquée** | arrêt à l'atteinte ; le 100 001ᵉ n'est jamais lu (testé à la valeur réelle) |
| 64 Mio écrits | **Appliquée** | comptage exact de chaque octet ; 4 Mio de réserve pour déclencheur + reçu final ; pas de quota noyau |
| Taille de message | **Partielle** | revérifiée après réception ; le transport live passe `max_size` (non testé contre le serveur) |
| 256 Mio de mémoire | **Partielle** | (1) RSS comparé au plafond à l'ouverture de session et tous les 256 messages, valeur illisible = arrêt ; (2) `RLIMIT_DATA` posée par le lanceur et relue (vérifiée en sous-processus) ; (3) **`MemoryMax` cgroup/systemd : à configurer par l'opérateur, hors paquet** |
| Silence 5 s | **Appliquée** | monotone depuis le dernier heartbeat (ou l'ouverture) ; seul le canal `heartbeats` le remet à zéro |

Règles de égalité (testées) : une trame qui arrive exactement à une échéance est lue avant que l'échéance soit jugée ;
un silence de exactement 5 s passe, 5 s + 1 ns arrête ; une réception à exactement 180 s est acceptée, la suivante non.

## 6. Matrice test → preuve (tous exécutés, hors réseau, aucun saut)

| Cas de la mission | Tests (`tests/flux_collection_pilot/…`) | Ce qui est affirmé |
|---|---|---|
| Doublon identique puis contradictoire, entre sessions | `test_analysis::test_duplicates_exact_once_and_contradictions_excluded_in_every_variant_across_sessions` | exact compté 1 fois (dans la session et entre sessions) ; conflit (même ID, taille ou heure différente) : **toutes** les variantes, y compris la première vue, exclues du volume ; variantes et emplacements consultables |
| Côté maker / inversion | `test_maker_side_is_kept_raw_and_the_aggressor_inversion_is_explicit_and_unattested` | brut conservé ; inversion explicite ; côté inconnu → bornes, jamais un défaut ; `attested=false` |
| Trou, répétition, retour arrière | `test_capture_protocol::test_l2_gap_repeat_rewind_stop_with_trigger_and_exact_reason`, `test_analysis::test_gap_invalidates_at_the_suspect_message…`, `test_repeat_and_rewind_are_not_applied…`, `test_other_channels_never_fill_an_l2_hole…` (×2) | message déclencheur et motif exacts (`expected`/`got`), carnet invalidé au message suspect, rien publié depuis un état invalide, compteurs des autres canaux sans effet sous la politique par défaut |
| Reconnexion sans snapshot | `test_analysis::test_reconnection_without_snapshot_invalidates_the_old_book_and_updates_alone_prime_nothing` | ancien carnet non hérité, mises à jour seules n'amorcent rien, 0 carnet exploitable |
| Reconnexion avec snapshot | `test_analysis::test_reconnection_with_a_valid_snapshot_builds_a_fresh_book_with_no_inherited_level` | niveau hérité absent ; remplacement de quantité ; retrait par zéro ; empreinte = celle de la session seule ; deux relectures (objets neufs puis autre processus) à l'empreinte égale |
| Horodatages | `test_analysis::test_time_inventory_counts_missing_invalid_sentinel_and_after_cut_separately`, `test_capture_protocol::test_utc_and_monotonic_receipts_are_distinct_fields…` | manquants / invalides / sentinelles (epoch, an 1) / postérieurs à la coupe comptés à part ; UTC et monotone distincts |
| Silence 5 s | `test_heartbeat_silence_of_five_seconds_with_simulated_clock` (4,9 s, 5 s, 5 s + 1 ns), `…counts_from_session_open…`, `…non_heartbeat_channel_does_not_reset…` | arrêt exactement à 5 s monotones, horloge simulée |
| Bornes connexions / durée / messages / octets | `test_connection_cap…`, `test_peer_close_after_reconnect…`, `test_full_protocol…` (180 s exactes), `test_message_cap_boundary…`, `…real_protocol_value_100000`, `test_disk_cap…`, `test_store_durability::test_exact_byte_boundary…` | limite et dépassement d'un cran |
| Mémoire | `test_memory_guard_cap_unverifiable_and_runner_integration`, `test_live_lock::test_data_limit_is_applied_and_read_back_in_a_subprocess…` | plafond, valeur illisible = arrêt, `RLIMIT_DATA` relue et effective (MemoryError) |
| Refus, perte locale | `test_refused_access_at_open_and_midstream_local_loss_and_peer_close…`, `test_format_anomalies_stop_and_keep_the_triggering_message`, `test_oversized_message…`, `test_unhealthy_first_session_at_cut…` | arrêt sans reconnexion, déclencheur conservé, `complete=false` |
| Écriture interrompue / état incomplet | `test_store_durability` : `…write_failure_ends_incomplete…`, `…total_write_failure_leaves_no_final_receipt…`, `…interrupted_write_is_reported_incomplete…`, `…closure_is_durable_hash_bound_and_tamper_evident`, `…short_writes…`, `…storage_is_private_exclusive_and_outside_git` | clôture fsync + rename + fsync répertoire ; ligne tronquée jamais lue ; falsification détectée ; hors Git, 0700/0600 |
| Verrou live | `test_live_lock` : `…cli_live_without_authorisation_is_blocked_before_dns_or_socket…`, `…each_missing_or_wrong_element_locks_for_its_own_reason` (15 cas), `…positive control`, `…acknowledgement_must_be_bound…`, `…template_is_not_an_approval`, `…importing_the_package…touch_no_network` | 0 appel réseau, 0 objet socket, `websockets` non importé ; chaque élément manquant échoue pour **sa** raison (le témoin positif passe) |
| Garde réseau lui-même | `test_the_guard_itself_works_and_cannot_be_swallowed` | le garde compte et lève une `BaseException` que `except Exception` n'avale pas |
| Copies épinglées | `test_pinned_copies` | JSON strict, RFC 3339, contexte exact identiques aux originaux |

**Mécanisme du garde réseau** (`conftest.py`, automatique) : `socket.socket.connect/connect_ex/sendto`,
`socket.create_connection` et tous les résolveurs DNS sont remplacés ; chaque appel est compté et lève `NetworkAttempt`
(`BaseException`) ; une assertion de fin de test exige un compteur nul. Couvre les tentatives Python du processus de test ;
ne couvre pas un sous-processus (deux tests lancent un Python local qui n'importe aucun client), ni un canal hors socket.
**Contrôles par mutation** : j'ai cassé volontairement six points (domaine de séquence, exclusion des conflits, ACK du
verrou, ignorance des mises à jour sans snapshot, seuil de silence, réserve disque) ; chacun fait échouer la suite.

Résultats : paquet 113 passés ; avec les régressions Flux (`tests/market_flow`, `tests/market_venues`, intégration
cross-stack) **672 passés, 1 sauté** (le saut est préexistant : preuve Landlock sur VM cible, `test_public_us_sandbox.py:62`).
Les suites TypeScript ne sont pas concernées (aucun changement frontend).

## 7. Reçus, replay, manifeste

- Exemple de reçu synthétique : `SYNTHETIC_FINAL_RECEIPT_EXAMPLE.json` (compteurs, motif de fin, complet/incomplet, SHA-256 de
  chaque fichier, plafonds, statut de chaque limite, hypothèses non prouvées, `evidence_kind=SYNTHETIC`).
- Replay reproductible (aucun réseau, aucune horloge) :
  ```
  python -m observability.flux_collection_pilot demo   --out <dossier privé hors Git> --id demo-1
  python -m observability.flux_collection_pilot verify <dossier>/demo-1     # COMPLETE_VERIFIED
  python -m observability.flux_collection_pilot replay <dossier>/demo-1     # report_sha256
  ```
  Empreinte attendue pour la démo synthétique : `d214f42f6d7d63503a6d4cdfeadadb6fd99003144f5ec793b3c707f24f213ccc`
  (reproduite sur deux campagnes indépendantes).
- Manifeste opérateur à compléter : `OPERATOR_COLLECTION_MANIFEST.template.json` (cible, plafonds, politique de séquence,
  horloge observateur avant/après, stockage, arrêt, preuves d'autorisation, admissibilité, conditions d'usage). Gabarit =
  `TEMPLATE_NOT_APPROVED` ; il ne vaut aucune autorisation. Le verrou exige en plus `FLUX_PILOT_LIVE_GO` = SHA-256 des octets du manifeste.

## 8. Écarts et limites restantes (à ne pas effacer)

1. **Verrou ≠ autorisation.** Il impose des références (exception #286, admissibilité, conditions, horloge) mais n'en
   authentifie aucune : c'est une garde nécessaire, pas suffisante. Le GO reste humain.
2. **`LiveTransport` jamais exécuté** contre un serveur ni contre `websockets` 16.0 (absent de cet environnement ; le VPS
   le fige à 16.0). Testé seulement avec une fausse bibliothèque (arguments, mappage des refus). À vérifier hors réseau
   (signature `connect`, classes d'exception) avant tout GO.
3. **Politique de séquence par défaut `PER_CHANNEL`** (conservatrice : aucun autre canal ne comble un trou L2). Si le
   fournisseur numérote par connexion ou par produit, la collecte s'arrêtera tôt, `INCOMPLETE`, avec la réfutation
   enregistrée. Le choix de `PER_PRODUCT` ou `PER_CONNECTION` revient à l'opérateur, motivé par la documentation.
4. Mémoire : RSS vérifié tous les 256 messages, pas à chaque message ; `RLIMIT_DATA` 256 Mio non éprouvée avec les
   vraies bibliothèques ; cgroup non configuré.
5. fsync des fichiers bruts toutes les 1 000 messages et à la clôture : une coupure brutale peut perdre jusqu'à 999 messages
   non synchronisés (le vérificateur les signale comme reçu final absent / ligne tronquée).
6. La session 2 n'est pas limitée à 60 s : elle court jusqu'au plafond global de 180 s.
7. Le carnet : un snapshot de la **même** session reconstruit un carnet invalidé (choix documenté ; la mission parle du
   snapshot de la nouvelle session après coupure). La CVD n'est pas calculée (aucun ancrage ni barre dans ce paquet).
8. Doublons : l'égalité de contenu compare les textes natifs ; `1.0` contre `1` est une variante contradictoire
   (conservateur : exclu et visible).
9. « Coupe » de l'inventaire d'heures = fin de campagne (reçu final) ou paramètre `cut_utc_ns`.
10. Une horloge locale synchronisée ne certifie aucune latence fournisseur : décalage et incertitude restent `UNKNOWN`.
11. Aucune extraction brute de la documentation Coinbase n'est conservée (outil de lecture résumant).

## 9. Après ce paquet (hors mission, rien n'est autorisé ici)

1. Vérifier par sources officielles l'admissibilité régionale et les conditions d'usage (machine + conservation privée).
2. Fusion source (revue indépendante) puis release épinglée portant ce paquet, exception #286 propre.
3. GO de collecte épinglé au `package_digest` et au manifeste complété (sections 5 et 7).
4. Après collecte seulement : admission dans Flux = contrat de provenance réelle, tests Python et TypeScript, GO séparé ;
   le validateur Flux conserve `synthetic=true` dans cette tranche.
