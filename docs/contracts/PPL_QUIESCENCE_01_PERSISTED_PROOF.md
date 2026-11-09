# PPL-QUIESCENCE-01 — Preuve persistée de quiescence (contrat v1.2, lot A)

Statut : **contrat source + module pur + tests isolés.** Exception #286 limitée à la source et aux tests (décision de l'opérateur, 2026-11-09). Aucun câblage : ni `mexc_simulator.py`, ni `advisor_loop.py`, ni VPS, ni installation, ni activation, ni epoch, ni modification de l'autorité #282. Les lots B (témoin exécutable) et C (câblage) sont distincts.

Module : `paper_trading/ppl_quiescence_proof.py` · Tests : `tests/paper_trading/test_ppl_quiescence_01.py`.

## 1. Principes

- Une observation cohérente (**O**) prouve un accord mémoire/durable à un instant d'un processus vivant. Elle ne prouve ni l'arrêt ni l'état ultérieur.
- Un état scellé (**sentinelle**) est une déclaration du processus. Elle n'est pas une sortie : un `SIGKILL` juste après ne la contredit pas et ne la transforme pas en arrêt propre.
- L'arrêt n'est établi que par un **témoin externe (S)**, pour l'instant T de son inspection.
- Toute valeur est `{status, value, provenance}` avec `status ∈ OBSERVED | UNKNOWN | NOT_AVAILABLE | NOT_APPLICABLE | UNRESOLVED`. Hors `OBSERVED`, `value` vaut `null` (imposé à la lecture). Aucun défaut numérique ; aucune valeur non observée n'est convertie en `0`/`False`, y compris pour les adaptateurs existants.
- `quiescent` est **interdit pour le runtime actuel non câblé**.

## 2. Preuve d'arrêt : identité, pas chemin libre (point 1)

Un `flock` libre n'atteste que la disponibilité du verrou inspecté. L'observation O enregistre, côté processus (`fstat` sur son propre descripteur de verrou) : `lock_path`, `lock_dev`, `lock_ino`, `lock_ctime_ns`, `lock_mtime_ns` ; et `process_instance_id`, `pid`, `pid_starttime` (`/proc/<pid>/stat`, champ 22), `pid_namespace`, `boot_id`. Un numéro d'inode est recyclé après `unlink` : l'identité du fichier est donc `(dev, ino, ctime, mtime)`.

Le témoin ouvre le chemin sans créer ni suivre de lien (`O_RDONLY|O_NOFOLLOW`), compare `fstat(fd)` et `lstat(chemin)` puis l'identité enregistrée, et tente `flock(LOCK_SH|LOCK_NB)` relâché aussitôt. Résultat `lock_probe` :

| Constat | `lock_probe` |
|---|---|
| fichier absent, non inspectable, lien symbolique, remplacé, modifié (ctime/mtime), identité ambiguë, identité enregistrée incomplète, erreur du `flock` | **UNKNOWN** |
| même identité, verrou refusé | `HELD` |
| même identité, verrou obtenu puis relâché | `FREE_SAME_IDENTITY` |

`process_stopped` (jamais déduit du seul chemin libre) :

| Condition | Valeur |
|---|---|
| verrou `HELD`, ou pid vivant avec le `starttime` enregistré | `OBSERVED false` |
| `boot_id` courant ≠ enregistré | `OBSERVED true` (le processus enregistré ne peut plus exister) |
| pid disparu (absent, ou réutilisé avec un autre `starttime`), **même espace de noms pid**, **et** `FREE_SAME_IDENTITY` | `OBSERVED true` |
| tout autre cas, dont verrou absent/remplacé et espace de noms différent | **UNKNOWN** |

Conséquence assumée : l'Advisor actuel supprime `logs/advisor.lock` à la sortie propre (`_release_instance_lock`). Une sortie propre donne donc `UNKNOWN` pour l'arrêt tant que le redémarrage de machine ou le lot C (verrou conservé, ou preuve d'arrêt par superviseur) ne fournit pas une preuve d'identité. Ce n'est pas corrigé en affaiblissant la règle.

## 3. Trois états distincts, plus l'interruption (point 3)

| Verdict | Conditions (toutes) | Ne dit pas |
|---|---|---|
| `RUNNING` | témoin : verrou tenu ou pid vivant | — |
| `INTERRUPTED` | arrêt établi par S ; aucune sentinelle valide liée à la dernière O et au digest courant (absente, ou ledger a avancé après elle) | compteurs : `pending_order_count`, `lifecycle_transitions_in_flight`, `admissions_in_flight` restent **UNKNOWN** (cas #282) |
| `SEALED_THEN_STOPPED` | arrêt établi par S ; sentinelle valide (même O, même digest du ledger, même identité de processus) | sortie propre |
| `CLEAN_STOP_CONFIRMED` | `SEALED_THEN_STOPPED` **et** `exit_status` `OBSERVED 0` fourni indépendamment (superviseur), lié au `pid` et au `pid_starttime` enregistrés | — |
| `STALE` / `UNCERTAIN_PROOF` / `UNRESOLVED_CHAIN` / `UNKNOWN` | voir §5, §6 | — |

Une sentinelle suivie d'un `SIGKILL` donne `SEALED_THEN_STOPPED`, jamais `CLEAN_STOP_CONFIRMED` (test dédié).

## 4. Champs requis par verdict, et provenance de `runtime_consults_gate`

Tous les champs requis doivent être `OBSERVED`, sinon le verdict est dégradé en `UNKNOWN` avec la liste `missing`.

- Identité : `paper_epoch_id`, `manifest_sha256`, `config_snapshot_hash`, `code_sha`, `source_sha`, `authority_store_root`.
- Frontière PPL : `ledger_last_sequence`, `ledger_last_event_id`, `ledger_size_bytes`, `ledger_sha256`, `ledger_event_count` (octets du fichier d'epoch, recoupés avec le décodeur du store).
- Processus : `process_instance_id`, `pid`, `pid_starttime`, `pid_namespace`, `boot_id`, `lock_path`, `lock_dev`, `lock_ino`, `lock_ctime_ns`, `lock_mtime_ns`.
- Positions : `durable_open_positions`, `durable_unresolved_positions`, `memory_open_positions`, `memory_matches_durable`. Une divergence mémoire/durable est rapportée, jamais corrigée.
- Autres : `simulator_generation` (historique, local au processus), `gate_state`, `gate_marker_sha256` (marqueur de fermeture ; `NOT_AVAILABLE` s'il n'existe pas).

| Résultat | Requis |
|---|---|
| `INTERRUPTED` | identité + frontière + processus |
| `SEALED_THEN_STOPPED`, `CLEAN_STOP_CONFIRMED` | ci-dessus + positions + génération + `gate_state` + `gate_marker_sha256` |
| drapeau `quiescent` | ci-dessus + les **trois** compteurs `pending_order_count`, `lifecycle_transitions_in_flight` et `admissions_in_flight`, chacun `OBSERVED` avec un `int` strictement typé, non négatif et **égal à 0** (booléen, flottant, chaîne, `None`, négatif, UNKNOWN, NOT_APPLICABLE, NOT_AVAILABLE, UNRESOLVED : refus) + `runtime_consults_gate` observé `true` ; en plus : `gate_state == CLOSED`, aucune position ouverte ni non résolue (enregistrée **et** recalculée depuis le ledger courant), `memory_matches_durable == true` |

`runtime_consults_gate` n'est jamais déduit. Il vient d'une déclaration `ppl_gate_wiring_v1` exposée par le simulateur (`protocol == PPL-GATE-WIRING-V1`, `code_sha` égal au manifeste, booléen `consults_gate_under_lock`), enregistrée avec la provenance `RUNTIME_DECLARATION:PPL-GATE-WIRING-V1@<code_sha>`. Le runtime actuel n'expose aucune déclaration (et ne référence pas `ppl_admission_gate`, audit de `main@3ce529fc`) : la valeur est `UNKNOWN`. Une déclaration d'un autre `code_sha` ou malformée est `UNRESOLVED`. Une déclaration est une affirmation du code testé, pas une preuve indépendante : limite assumée, c'est le lot C qui devra la rendre vérifiable.

`lifecycle_transitions_in_flight` est `NOT_APPLICABLE` sous PPL_AUTHORITY : le compteur legacy n'y est jamais incrémenté (tout se passe sous `simulator._lock`) et sa valeur `0` n'est jamais lue. Tant qu'un compteur dédié n'existe pas, `quiescent` reste faux et l'adaptateur `EpochRotationQuiescence` refuse (`QuiescenceRefusal`) au lieu de fabriquer un zéro.

Ordre de verrous de l'observation O : `simulator._lock` puis `runtime._lock` (ordre de l'OPEN/CLOSE autoritaire). Lecture seule : aucune fermeture, aucun redémarrage, aucun écrit dans le store d'autorité.

## 5. Persistance, publication incertaine, reprise (point 2)

Répertoire de preuve dédié, refusé s'il est égal, parent ou enfant d'une racine d'autorité (`forbidden_roots`, ancêtres et liens symboliques résolus), ou lien symbolique. **Le contrôle précède toute création** : un refus ne laisse aucun répertoire dans l'autorité. Enregistrements chaînés (`prev_record_sha256`, `record_sha256` = SHA-256 du JSON canonique), nommés `quiescence-<seq:08d>-<sha[:16]>.json`.

**Écrivains sérialisés** par `flock` exclusif sur `.writer.lock`, attente bornée (`PersistBlocked` à l'échéance). La séquence est calculée sous verrou comme `n+1` du dernier enregistrement visible.

Protocole : fichier temporaire (`O_EXCL`) → écriture complète en boucle → `fsync(fichier)` → publication par `link` (jamais d'écrasement) → `fsync(répertoire)` → **reçu** `.ok` (même protocole, puis `fsync` du répertoire). Un enregistrement est *confirmé* seulement si son reçu est visible et correspond ; le reçu n'est créé qu'après un `fsync` de répertoire réussi, donc un reçu visible affirme un fait déjà vrai (enregistrement durable).

Sémantique des quatre points de synchronisation (numérotés dans l'ordre des `fsync`) :

| `fsync` en échec | Résultat de `append` | État vu par un autre processus | Reprise |
|---|---|---|---|
| 1 fichier de l'enregistrement | `PersistBlocked`, rien de publié | chaîne vide, séquence non consommée | sans objet |
| 2 répertoire après l'enregistrement | `PersistUncertain` | enregistrement visible, **non confirmé** | `recover()` |
| 3 fichier du reçu | `PersistUncertain` (aucun reçu visible) | **non confirmé** | `recover()` |
| 4 répertoire après le reçu | **succès**, `AppendResult.receipt_durable == False` | confirmé (le reçu est visible ; l'enregistrement était déjà durable) | si un crash emporte le reçu : retour à non confirmé (sens sûr), puis `recover()` |

`PersistUncertain` ne signifie donc que « la durabilité de l'enregistrement n'est pas prouvée » ; le dernier cas est un reçu dont la présence future n'est pas garantie, jamais un enregistrement douteux accepté.

| Défaillance | Effet |
|---|---|
| avant publication (disque plein, `EIO`, lecture seule, `link` refusé, `fsync` fichier) | `PersistBlocked` ; rien de visible ; **séquence non consommée** (pas de trou) ; le temporaire est supprimé ou ignoré |
| crash (SIGKILL) avant ou pendant la publication | temporaire orphelin ignoré par les lecteurs ; aucune séquence consommée |
| après publication : `fsync` du répertoire ou du fichier de reçu en échec (points 2 et 3 ci-dessus) | `PersistUncertain(seq, sha)` ; l'enregistrement reste visible, **sans reçu** : tout lecteur (autre processus compris) le traite comme non confirmé ; la séquence est conservée (ni suppression, ni trou, ni fourche) |
| reprise | `recover()` ou prochain `append()` : sous verrou d'écriture, re-hash, `fsync` fichier, `fsync` répertoire, reçu `recovered: true`. Échec ⇒ `PersistBlocked`, état inchangé ; aucun ajout tant que le dernier enregistrement n'est pas confirmé |
| anomalie de lecture (JSON tronqué, hash ou nom incohérent, clé dupliquée, `NaN`, lien symbolique, trou, fourche, valeur hors triplet) | chaîne `UNRESOLVED` : jamais ignorée, aucun ajout, aucun « rien à signaler » |

`assess()` refuse (`UNCERTAIN_PROOF`) toute chaîne contenant un enregistrement non confirmé, et `UNRESOLVED_CHAIN` toute chaîne anormale. Le lecteur n'accepte donc jamais comme preuve durable ce que l'écrivain a déclaré incertain.

## 6. Invalidation, fraîcheur, vérification après disparition du processus (point « post-mortem »)

Auto-invalidation par liaison, sans liste de révocation. `assess(store, manifest, manifest_sha256, store_root, now, max_age_s)` :

1. chaîne confirmée et intacte ; dernières O, sentinelle (postérieure à O) et témoin ;
2. fraîcheur `0 ≤ now − observed_at ≤ min(max_age_s, max_age_s de l'enregistrement)`, `now` fini, `observed_at` non futur ⇒ sinon `STALE` ;
3. liaisons : epoch, `manifest_sha256`, `config_snapshot_hash`, `code_sha`, racine du store ⇒ sinon `STALE` ;
4. le ledger d'autorité est **relu maintenant** (octets du fichier + décodeur ; jamais créé ni modifié : un store sans fichier de verrou est « non inspecté ») et son digest doit égaler celui du témoin (`ledger_sha256_recomputed`) ⇒ sinon `STALE` ;
5. le témoin doit suivre la dernière O, lui être lié (`bound_observation_sha256`) et porter la même identité de processus ⇒ sinon `UNKNOWN` (un redémarrage produit une nouvelle O, antérieure à aucun témoin ⇒ ancien témoin sans effet) ;
6. sentinelle valide seulement si elle scelle cette O et si les digests de ledger sont **tous égaux** : O = sentinelle = témoin = ledger courant, pour la même identité de processus. Sinon `INTERRUPTED` (jamais un verdict scellé).

`write_seal` et `write_witness` ne se fient pas à un corps fourni : ils retrouvent dans la chaîne l'OBSERVATION désignée (même séquence, même `record_sha256`, type OBSERVATION), exigent qu'elle soit **confirmée** et **la plus récente**, et dérivent leur contenu de son corps persisté ; un corps fourni doit lui être identique octet pour octet, sinon `QuiescenceRefusal`. Un mélange de deux instantanés est donc refusé à l'écriture et, par défense en profondeur, à la lecture.

Après la disparition du processus, **rien de sa mémoire n'est relu**. Les champs issus de la mémoire (`pending_order_count`, `simulator_generation`, `memory_open_positions`) sont des déclarations historiques datées, liées au digest du ledger : elles ne sont retenues que tant que ce digest est inchangé et que la sentinelle les scelle ; les positions ouvertes sont de plus recalculées depuis le ledger courant. Sans sentinelle valide ces champs restent inconnus (`INTERRUPTED`).

Le témoin n'établit l'arrêt qu'à T. Un redémarrage silencieux sans écriture au ledger après T est indétectable post-mortem : la fraîcheur du témoin (`max_age_s`, 900 s par défaut) est le contrôle, et le consommateur doit exiger un témoin récent.

## 7. Frontière de confiance

- **Admis** : le code observé mesure fidèlement sa mémoire sous verrou ; le témoin partage l'espace de noms pid et de montage de l'Advisor ; `/proc` et `boot_id` sont fiables.
- **Non couvert** : authenticité face à un acteur pouvant écrire sur le disque (intégrité par hash et chaîne, pas de signature) ; vérité de l'horloge (enregistrée en provenance) ; état après T ; recyclage d'inode au sein d'un même tick noyau avec mêmes ctime/mtime (le verrou est conservé tel quel pendant la vie du processus ; toute modification donne UNKNOWN, direction sûre).
- **Micro-fenêtre du témoin** : le probe acquiert brièvement un `LOCK_SH`. Un démarrage d'Advisor concurrent à cet instant pourrait voir « instance déjà active » ; relève du lot B (exécution du témoin sous gate opérateur).
- Jamais : décision, fermeture de gate, redémarrage, alimentation de Research, PnL/equity, lecture de `PB_MAX_POSITIONS`.

## 8. Tests (102)

Revue v1 : compteurs non strictement nuls (3 compteurs × 10 formes), mélange de deux instantanés, scellé d'une observation non confirmée ou remplacée, scellé forgé hors API, refus de racine interdite sans création (enfant, profond, parent, égalité, lien symbolique), chacun des quatre points de `fsync` avec lecture par un autre processus, perte du reçu et reprise. Valeurs et absence de défauts ; observation sur runtime réel (`MexcSimulator` PPL_AUTHORITY + `PPLAuthorityRuntime`) ; ordre de verrous `sim → runtime` ; cohérence sous OPEN/CLOSE concurrents ; écrivains concurrents (threads, 3 processus) sans trou ; écriture partielle/corrompue/fourche/lien ; disque indisponible ; **publication visible puis échec de `fsync` du répertoire, lecture par un autre processus (non confirmé), échec de reprise, reprise par un troisième processus, séquence suivante sans trou** ; échec de reçu ; crash par `SIGKILL` pendant la publication ; stop : verrou tenu, chemin libre avec pid vivant, `SIGKILL`, **fichier de verrou remplacé / inode recyclé / touché / absent / lien symbolique**, identité incomplète, autre espace de noms pid, changement de `boot_id`, réutilisation de pid ; verdicts : RUNNING, INTERRUPTED, **sentinelle puis `SIGKILL`**, CLEAN avec statut de sortie lié au pid, statut d'un autre pid ignoré, sentinelle invalidée par un événement ultérieur, champs manquants, témoin absent, preuves périmées (âge, futur, ledger, manifeste, racine), redémarrage, vérification sans objet simulateur, falsification ; `quiescent` interdit sans câblage ; adaptateur qui refuse l'inconnu ; isolation (le store d'autorité n'est pas touché ni créé) ; `PB_MAX_POSITIONS` jamais lu.

## 9. Historique du dossier (correction)

Le delta de tests `f2beb9fc…` (commit 4a76e1e8 de #565) **a bien été relu et testé indépendamment avant la fusion**. Cette revue n'avait toutefois pas réexécuté la suite complète ni Ruff. La cause du blocage initial de TEST REGRESSION GATE reste non démontrée.

## 10. Revue indépendante du patch v1 (42d9968a…) et corrections de cette v1.2

R1 (P1) : `admissions_in_flight` n'était pas contrôlé à zéro → exigé comme les deux autres compteurs, type strict ; l'adaptateur refuse tout compteur non nul. R2 (P1) : une sentinelle pouvait sceller une observation différente de celle persistée → écrivains dérivés de l'OBSERVATION confirmée et la plus récente, et égalité O = sentinelle = témoin = ledger exigée à la lecture. R3 (P2) : `mkdir` précédait le contrôle des racines interdites → contrôle avant toute création. R4 (P2) : sémantique du dernier `fsync` (reçu) incohérente avec `PersistUncertain` → table du §5. Chaque correction a un test qui échoue sur le patch v1 (12 échecs vérifiés).

## 11. Hors périmètre (lots B et C et décisions opérateur)

Exécution du témoin (VPS), détention du verrou pendant le scellement, lecture de la gate sous `_lock` dans `_fill_market_ppl_authority`, écriture de la sentinelle à l'arrêt, compteur de transitions réel, déclaration de câblage vérifiable, répertoire de preuve de production, installation, epoch, activation, levée de #286.
