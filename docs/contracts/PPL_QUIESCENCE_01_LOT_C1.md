# PPL-QUIESCENCE-01 — Lot C1 (C1a) — Contrat v0.3

**Implémentation : locale, lot C1a, GO opérateur du 2026-11-12T04:02Z sur ce contrat (sha256 du texte validé `eeb912f8…41be2`, conservé hors dépôt). Non fusionné, non déployé ; le GO d'implémentation ne vaut ni fusion ni déploiement. Notes d'implémentation au §16.**

**Statut : v0.3, erratum ciblé de v0.2 (sha256 `2ab37b67…3827`, GO CONDITIONNEL du 2026-11-12T03:54Z). Corrige uniquement trois points (§15) : §9, AC3d, H8. Protocole, architecture et D-C1a-1 à 7 inchangés. Aucun code écrit ; implémentation subordonnée à une validation explicite de l'opérateur.**
Historique v0.2 : addendum C-01, C-02, C-03 sur v0.1 (§14).
Sections modifiées par v0.2 : §0 (point 5), §3 (signature d’`admission_hold`), §4.1 (étape 9), §4.4 (point 2), §4.8 (nouveau), §5.2, §8.3 (scénarios 9, 18, 19, 20), §8.4 (I11), §8.5, §9, §10 (D-C1a-4), §11 (R6, R14, R15), §13, §14 (nouveau). D-C1a-1, 2, 3, 5, 6 et 7 inchangés.
Base source : `main@7cd4c4e9df540da0bde58726343d29c1c3b120ca` (dépôt local propre, `git status` vide).
Mission : III-R1.2, lot C1, étape C1a-0 (GO opérateur du 2026-11-12T02:33Z).
Emplacement : fichiers privés du projet. Rien sur GitHub. Le contrat rejoindra `docs/contracts/` seulement avec le code, après GO.

Ce contrat couvre **C1a** : `paper_trading/mexc_simulator.py`, deux méthodes de lecture dans `paper_trading/ppl_admission_gate.py`, l'adaptateur d'observation A (`ppl_quiescence_proof.py`, contrat A v1.3) et les tests. **C1b** (Advisor) reste dans le plan, mais son code n'est pas autorisé ; ce document n'en fixe que l'interface attendue (§9).

---

## 0. Résumé

1. **Le défaut de v0 est reconnu.** v0 libérait le flock de la gate après t3, avant `commit_open`. Un autre processus pouvait créer le marqueur entre les deux, et un OPEN devenait durable **après** la fermeture, sans que rien ne permette au fermeur de savoir quand cela cessait.
2. **Correction v0.1.** Le flock de la gate est tenu **de t1 jusqu'au retour de `commit_open`**, reprise sur OSError comprise. Une nouvelle méthode en lecture seule, `AdmissionGate.drain_barrier`, prend ce même flock **après** avoir constaté le marqueur. Quand elle réussit, tout OPEN admis avant la fermeture est déjà durable, et aucun OPEN ultérieur ne peut être admis par un processus qui consulte la gate. Aucune primitive persistante nouvelle : marqueur `O_EXCL`, flock `<journal>.lock`, `_records()`, plus la preuve d'arrêt du lot B pour l'interprocessus.
3. **Ce qui n'est pas garanti, et le reste.** Un OPEN peut encore être persisté *après* la création du marqueur, mais toujours *avant* la fin du drainage. La garantie de fermeture est donc **après drainage**, pas immédiate (§4.5). Des tests négatifs le démontrent.
4. **Quiescence.** Locale : observation O sous `sim._lock`, sans drainage nécessaire. Interprocessus : seulement par arrêt prouvé de chaque processus écrivain (lot B). Le drainage seul ne vaut jamais quiescence.
5. **Autres corrections.** `admission_hold` et `drain_barrier` ne créent ni fichier ni répertoire (§4.6). Les transitions inachevées bloquent la quiescence quelle que soit la lecture durable ; la comparaison durable/mémoire n'en est qu'une classification de diagnostic (§5.2, v0.2). La compatibilité de `REJECTED_GATE_CLOSED` est vérifiée lecteur par lecteur (§8.1).

---

## 1. Environnement D-ENV et relevé de référence (fait)

- **Environnement** : venv Python 3.11.18 créé dans le scratchpad de session, hors dépôt, sans aucune donnée d'autorité. Installé : `requirements-ci.txt` et `ruff==0.15.8`, sans cache pip.
- **Copie de travail** : les tests ont tourné sur une copie `git archive 7cd4c4e9` hors dépôt, avec `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` et un TMPDIR isolé. Le dépôt n'a reçu aucune écriture (`git status` vide après exécution).
- **Gate ruff** (`scripts/ci/ruff_baseline_gate.py check`) : 945 constats contre 957 en baseline, **0 nouveau**. Gate OK.
- **`tests/paper_trading`** (`-m "not performance and not slow"`) : **761 passed** en 40 s.
- **Journaux conservés** dans `d-env/` : `pip_freeze.txt` (versions résolues), `install.log`, `ruff_gate.log`, `pytest_paper_trading.log`.
- **Limite** : le corpus complet `tests/` n'a pas été relancé à ce stade. Il le sera au moment du code (AC11).

---

## 2. Faits de départ (lus à 7cd4c4e9)

- **`place_market_order`** (l. 845-940) :
  - rejets immédiats ;
  - `_enter_admission`, qui écrit dans le ledger d'admission et peut court-circuiter ;
  - `_fetch_price`, qui fait un appel réseau et peut rejeter (prix indisponible ou écart OHLCV) ;
  - `_fill_market`, puis `_exit_admission`.
  - **Toute cette séquence se déroule hors `_lock`.**
- **`_fill_market_ppl_authority`** (l. 1036) : sous `_lock`, contrôle des doublons mémoire et durables, sizing, `commit_open`, puis mise à jour mémoire. Si `commit_open` lève OSError alors que l'OPEN est déjà visible, l'appel est répété une fois avec les mêmes faits.
- **`_close_position_ppl_authority`** (l. 1363) : sous `_lock`, `_durable_close`, `commit_close`, puis mise à jour mémoire.
- **Runtime** : `commit_open` et `commit_close` prennent `runtime._lock` (RLock). `DurableEventStore` prend un flock interprocessus à l'append.
- **LIMIT et STOP_LIMIT** sont rejetés sous PPL_AUTHORITY. `_check_pending_orders` → `_fill_market` reste atteignable en principe mais n'a pas de source d'ordres sous l'autorité. Le contrôle de gate est placé dans `_fill_market_ppl_authority`, donc il couvre aussi ce chemin.
- **`AdmissionGate`** :
  - `state()` est sans verrou et fail-closed ;
  - `open()` prend le flock `<journal>.lock` de l'append jusqu'à la relecture ;
  - `close()` crée le marqueur `O_EXCL` sans verrou, puis ajoute CLOSE sous flock, avec un timeout d'une seconde.
  - Le module ne lit aucune variable d'environnement.
- **Lot A** :
  - `observe_runtime` prend `sim._lock` puis `runtime._lock` ;
  - `lifecycle_transitions_in_flight` vaut NOT_APPLICABLE et `admissions_in_flight` vaut UNKNOWN ;
  - `quiescent` exige `gate_marker_sha256` OBSERVED, donc un marqueur présent et non un simple CLOSED de journal.
- **Ordre persisté de `close()`** : le marqueur est créé **sans** verrou, puis l'enregistrement CLOSE est ajouté **sous** flock, avec un timeout d'une seconde. En cas de timeout, `close()` rend tout de même `True` si le marqueur est durable. Son retour ne dit donc rien du drainage.
- **Le fichier `<journal>.lock`** est créé par `_locked()` (`O_RDWR | O_CREAT`), qui crée aussi le répertoire parent. Il existe dès le premier `open()` réussi ou tenté.
- **Écart d'étiquetage existant** : `_exit_admission` classe tout rejet inconnu comme `REJECTED_INSUFFICIENT_CAPITAL`. Un refus de gate y serait donc mal étiqueté (voir D-C1a-3).

---

## 3. Interface proposée (C1a)

```
MexcSimulator.__init__(..., authority_runtime=None,
                       admission_gate=None,           # nouveau, défaut None
                       gate_wiring_code_sha=None)     # nouveau, défaut None
```

Refus à la construction, par une exception typée `GateWiringRefusal` :

- `admission_gate` est fourni alors que l'autorité n'est pas PPL_AUTHORITY ;
- `admission_gate` est fourni sans `authority_runtime` ;
- `gate.paper_epoch_id` ≠ `runtime.manifest.paper_epoch_id`, ou `gate.manifest_sha256` ≠ `authority_manifest_sha256(runtime.manifest)` (fonction existante) ;
- `gate_wiring_code_sha` est fourni sans gate, ou n'est pas un hexadécimal de 40 ou 64 caractères.

Une gate liée à une autre epoch est refusée plutôt que tolérée « fermée ». L'erreur de câblage doit être visible au démarrage, pas se traduire par un refus silencieux de tous les OPEN.

Deux méthodes additives dans `AdmissionGate`, sans aucune écriture (§4.6) :

```
AdmissionGate.admission_hold(*, lock_timeout_s) -> _AdmissionHold   # classe __enter__/__exit__ (v0.2, C-01)
    # contrôle t1..t3 ; si permitted, le flock reste tenu jusqu'à la sortie du with
AdmissionGate.drain_barrier(*, timeout_s) -> DrainResult
GateCheck   = (permitted: bool, code: str, detail: str)
DrainResult = (status: "DRAINED" | "NOT_CLOSED" | "DRAIN_TIMEOUT" | "DRAIN_ERROR",
               detail: str)
```

`admission_check` (v0) devient `admission_hold`, un gestionnaire de contexte : c'est lui qui porte la durée de tenue du flock. `open()` et `close()` ne changent pas.

---

## 4. Point 1 — Linéarisation de l'OPEN face à la fermeture

### 4.1 Procédure `admission_hold`

1. **t0** : `lstat(<journal>.lock)` sans le suivre. Absent → refus `GATE_NEVER_OPENED` (un `open()` le crée toujours). Lien symbolique ou fichier non régulier → `GATE_LOCK_INVALID`.
2. **t1** : `_marker_present()`. Présent → refus `GATE_CLOSED_MARKER`.
3. Ouverture du verrou en `O_RDONLY | O_NOFOLLOW | O_CLOEXEC`, **sans `O_CREAT`**, puis `flock(LOCK_EX | LOCK_NB)` en boucle jusqu'à `lock_timeout_s`. Échec → `GATE_LOCK_TIMEOUT`.
4. **Contrôle d'identité du verrou**, sous flock : `fstat(fd)` et `lstat(chemin)` doivent donner le même `(st_dev, st_ino)`. Sinon le fichier a été remplacé et l'exclusion mutuelle n'est plus prouvée → `GATE_LOCK_IDENTITY_CHANGED`.
5. **t2**, sous flock : `_records()`. `None` → `GATE_JOURNAL_INVALID` ; `[]` → `GATE_NEVER_OPENED` ; dernier enregistrement autre que OPEN → `GATE_CLOSED_JOURNAL`.
6. **t3**, sous flock : `_marker_present()` et `_forced_closed`. Positif → `GATE_CLOSED_MARKER`.
7. `__enter__` rend `GateCheck(True, "GATE_OPEN")`. **Le flock reste tenu** pendant tout le corps du `with`.
8. À la sortie du `with`, quelle qu'elle soit (retour, exception, `BaseException`), `__exit__` ferme le descripteur, ce qui libère le flock, et rend faux.
9. Pour tout refus, `GateCheck(False, code)` est rendu sans flock tenu.

**Frontière des exceptions (v0.2, C-01).** `admission_hold` est un gestionnaire de contexte à deux phases strictement séparées :

- **Phase d'acquisition et de validation** (étapes 1 à 6, dans `__enter__`). Seules les exceptions de classe `Exception` levées par ces étapes sont converties en refus : `OSError` sur `lstat`, `open`, `fstat` ou `flock` → code de l'étape, ou `GATE_READ_ERROR` ; toute autre `Exception` → `GATE_READ_ERROR`. `KeyboardInterrupt`, `SystemExit` et toute autre `BaseException` ne sont **jamais** converties : elles sont propagées telles quelles, après fermeture du descripteur s'il a été ouvert.
- **Phase du corps** (le bloc `with`, donc `commit_open` et sa reprise). Aucune exception du corps n'est interceptée, convertie, journalisée comme refus de gate ni remplacée. `__exit__` rend toujours une valeur fausse (aucune suppression). L'exception sort avec le même objet et la même trace.
- **Libération** : la fermeture du descripteur, qui libère le flock, a lieu dans un `finally` de `__exit__`, et dans un `finally` de `__enter__` pour tout chemin de refus ou d'exception qui ne rend pas `GATE_OPEN` avec le verrou tenu. Si `os.close` lève lui-même une `OSError`, celle-ci est absorbée et notée en log : sous Linux, le descripteur est libéré même dans ce cas, et l'absorber évite de **remplacer** une exception du corps en cours de propagation.
- **Forme imposée** : une classe avec `__enter__`/`__exit__` explicites, pas un générateur `@contextmanager`. Avec un générateur, un `try/except Exception` autour du `yield` capturerait les exceptions du corps et les transformerait en refus. La classe rend cette erreur impossible par construction.
- La méthode ne lève jamais d'`Exception` **de son propre fait**. Elle laisse passer les `BaseException` d'acquisition et toutes les exceptions du corps.

La relecture du marqueur à t3 n'est **pas** la correction du défaut, elle réduit seulement les cas où un OPEN déjà condamné irait jusqu'au commit. La correction vient de la tenue du flock jusqu'au commit (§4.2) combinée à `drain_barrier` (§4.3).

### 4.2 Position dans le simulateur

Dans `_fill_market_ppl_authority`, sous `self._lock`, après les contrôles de doublon et de capital et le calcul des faits :

```
with gate.admission_hold(lock_timeout_s=_GATE_LOCK_TIMEOUT_S) as chk:   # si gate injectée
    if not chk.permitted:
        order.status = REJECTED ; order.reject_code = chk.code ; return order
    commit_open(**facts)            # + reprise sur OSError, mêmes faits
# flock libéré ici ; la mise à jour mémoire suit, toujours sous self._lock
```

- `_GATE_LOCK_TIMEOUT_S` est une constante de module (0,25 s), jamais lue dans l'environnement.
- La reprise sur OSError s'exécute **dans** le `with`, sans nouveau contrôle : elle réaffirme de façon idempotente le même fait, déjà admis.
- Sans gate injectée, le code est celui de 7cd4c4e9.

### 4.3 Procédure `drain_barrier` (lecture seule)

1. `_marker_present()` faux → `NOT_CLOSED`. Le drainage n'a de sens qu'après la fermeture.
2. `lstat(<journal>.lock)` : absent → `DRAINED`. Aucun `admission_hold` n'a pu réussir, puisqu'il exige ce fichier (§4.1, t0).
3. Ouverture `O_RDONLY | O_NOFOLLOW` sans `O_CREAT`, `flock(LOCK_EX | LOCK_NB)` en boucle jusqu'à `timeout_s`. Échec → `DRAIN_TIMEOUT`.
4. Contrôle d'identité du verrou comme en §4.1, puis relecture du marqueur. Tout écart → `DRAIN_ERROR`.
5. Libération. Retour `DRAINED`.

`drain_barrier` n'écrit rien, ne ferme rien et ne change pas `close()`. C'est l'appelant qui l'invoque après `close()` (procédure opérateur, lot B ou C1b). En C1a, seuls les tests l'appellent.

### 4.4 Quatre notions distinguées

1. **Linéarisation logique de l'admission : t3.** Un OPEN est *admis* si et seulement si `admission_hold` rend `GATE_OPEN` à t3. Une fermeture est *effective* à la création du marqueur. Un OPEN admis avant la fermeture reste légitime, même s'il est persisté après.
2. **Ordre réel des écritures persistées.** Pour un OPEN admis et un marqueur créé après t3 :
   - le marqueur peut être persisté **avant** l'événement OPEN du ledger PPL (il ne prend pas de verrou) ;
   - **si `commit_open` est revenu normalement**, l'événement OPEN est persisté (fsync du store) **avant** la fin de tout `drain_barrier` qui rend `DRAINED`, et avant tout enregistrement CLOSE ajouté au journal par `close()` (les deux prennent le flock tenu pendant le commit). Si l'admetteur meurt pendant le commit, `DRAINED` ne dit **rien** de l'état du ledger (§4.8) ;
   - `opened_at` est fixé avant t3 : l'horodatage d'un événement n'est **jamais** une preuve d'ordre. Les preuves d'ordre sont la séquence du ledger, le retour de `drain_barrier` et l'ordre du journal de gate.
3. **Garantie de fermeture.** Immédiate : tout contrôle qui atteint t1 ou t3 après la création du marqueur refuse. Après drainage seulement : « aucun OPEN durable n'apparaîtra plus », établi par un `drain_barrier` rendu `DRAINED`, et seulement pour les processus qui consultent la gate.
4. **Quiescence locale et interprocessus** (§4.5).

### 4.5 Critères de quiescence

- **Locale (un processus, observation O du lot A).** O prend `sim._lock`. Or le contrôle et le commit s'exécutent dans une seule section critique sous `sim._lock`. O voit donc soit l'état antérieur au contrôle (et tout contrôle ultérieur verra le marqueur, P1), soit l'état postérieur au commit (la position est alors dans `durable_open_positions`). **Aucun drainage n'est nécessaire.** Les critères du lot A sont inchangés : marqueur OBSERVED, trois compteurs OBSERVED à 0, aucune position ouverte ni non résolue, mémoire = durable, déclaration de câblage valide.
- **Interprocessus.** Les compteurs d'un autre processus ne sont pas visibles. `drain_barrier` DRAINED prouve seulement l'absence de futur OPEN *de la part de processus qui consultent la gate*. Il ne dit rien d'un processus sans gate (par exemple le runtime gelé `116634be` ou `admission_gate=None`), ni des CLOSE à venir. **La quiescence interprocessus ne s'établit que par l'arrêt prouvé de chaque processus écrivain** : sentinelle et témoin du lot B, verrou d'identité stable de C1b. C1a ne revendique aucune quiescence interprocessus.

### 4.6 Zéro écriture dans `admission_hold` et `drain_barrier`

Appels système autorisés : `lstat`, `open(O_RDONLY | O_NOFOLLOW | O_CLOEXEC)` **sans** `O_CREAT`, `fstat`, `flock`, `read`, `close`. Interdits : `O_CREAT`, `O_WRONLY`, `O_RDWR`, `O_TRUNC`, `mkdir` et `Path.mkdir`, `unlink`, `rename`, `fsync`, `ftruncate`, `utime`. En conséquence, un répertoire parent absent donne `GATE_NEVER_OPENED`, sans création. Seul effet de bord possible : la mise à jour de l'`atime` par le noyau à la lecture (selon les options de montage), qui n'est pas une écriture du code et qui est exclue des comparaisons.

Preuve exigée par les tests (§8.3, scénario 16) :
- une sonde enveloppe `os.open`, `os.mkdir`, `os.makedirs`, `Path.mkdir`, `os.unlink`, `os.rename`, `os.replace`, `os.fsync`, `os.ftruncate` et `os.utime`, et refuse tout drapeau ou appel interdit ;
- un instantané du répertoire de la gate (noms, types, tailles, `st_ino`, `mtime_ns`, `ctime_ns`, sha256 du contenu), avant et après **chaque** code de refus et le cas `GATE_OPEN`, doit être identique ;
- même chose pour `drain_barrier` dans ses quatre statuts.

### 4.7 Ordre des verrous

```
simulator._lock → gate flock (de t1 jusqu'au retour de commit_open)
                → runtime._lock (RLock) → flock du DurableEventStore
```

Aucun code ne prend un verrou de rang inférieur en tenant un verrou de rang supérieur : `AdmissionGate.open`, `close` et `drain_barrier` ne prennent que le flock de la gate, `runtime` et le store ne touchent ni au simulateur ni à la gate, et `observe_runtime` prend `sim → runtime` sans le flock de la gate.

---

### 4.8 Interruption pendant l'append et état récupéré (v0.2, C-03)

**Libération du flock ≠ intégrité durable.** Un `drain_barrier` rendu `DRAINED` établit une seule chose : plus aucun processus ne tient le flock de la gate, donc aucune admission n'est en cours d'exécution chez les processus qui la consultent. Il ne dit **rien** de l'état du ledger PPL. Le noyau libère le flock d'un processus tué, quel que soit l'état de son append.

**États possibles du fichier d'epoch après un SIGKILL pendant `store.append`** (fait à 7cd4c4e9 : `_durable_append` fait `write`, `flush`, puis `fsync` ; `load_epoch` refuse tout le fichier, sans préfixe ni réparation, si une ligne est invalide ou si la ligne finale n'a pas de saut de ligne) :

| État | Contenu | `load_epoch` | Classification |
|---|---|---|---|
| E0 | rien d'écrit | réussit, OPEN absent | `NOT_APPLIED` |
| E1 | ligne partielle (sans `\n` final) | `StoreCorruptionError` | `LEDGER_CORRUPT` |
| E2 | ligne complète, `fsync` non fait | réussit, OPEN présent | `VISIBLE_DURABILITY_UNCONFIRMED` |
| E3 | ligne complète, `fsync` fait | réussit, OPEN présent | `VISIBLE_DURABILITY_UNCONFIRMED` du point de vue d'un lecteur : aucun lecteur ne peut distinguer E2 et E3 |

**Règles avant toute conclusion sur l'état récupéré :**
1. Aucune conclusion (« OPEN présent », « OPEN absent », « aucune position ouverte ») n'est tirée sans validation préalable de la chaîne complète : `DurableEventStore(root).load_epoch(epoch)` réussi (décodage strict, séquences contiguës, liaison à l'epoch, identités d'événements uniques, saut de ligne final), **et** cohérence d'empreinte du lot A (`_fingerprint_from` : nombre de lignes égal au nombre d'événements, dernier `event_id` présent dans la dernière ligne).
2. Si la validation échoue (E1, ou toute autre erreur de lecture), l'état récupéré est **UNRESOLVED**. Il n'existe alors ni valeur d'OPEN, ni position, ni quiescence. Le lot A rend les champs de ledger UNRESOLVED et `assess` n'est pas quiescent.
3. Une lecture réussie ne prouve pas la durabilité (E2 et E3 sont indiscernables). La durabilité n'est reconfirmée que par le chemin d'écriture existant (`_durably_confirm_existing` lors d'une reprise idempotente), jamais par C1a ni par un lecteur.
4. C1a ne répare, ne tronque, ne renomme et ne resynchronise jamais le ledger. Toute remédiation relève d'une procédure opérateur distincte, hors périmètre.
5. Une coupure d'alimentation ou un crash noyau (perte du cache de pages) ne sont pas simulés par ces tests (R14).

## 5. Point 2 — Couverture des compteurs

Les deux compteurs sont des attributs du simulateur, modifiés **et** lus uniquement sous `self._lock`. Ils sont maintenus en mode PPL_AUTHORITY, avec ou sans gate. L'observateur ne les publie qu'en présence d’une déclaration de câblage valide (§6 et §9, D-C1a-5).

### 5.1 `admissions_in_flight` (entier `_ppl_admissions_in_flight`)

**Définition** : nombre d'appels `place_market_order` en mode PPL_AUTHORITY qui ont passé les rejets immédiats et ne sont pas encore revenus.

- **Incrément** : sous `_lock`, juste après `_reject_legacy_admission_if_frozen` et avant `_enter_admission`.
- **Décrément** : sous `_lock`, dans un `finally` qui enveloppe tout le reste de la méthode. Cela couvre tous les retours et toutes les exceptions, y compris `BaseException`.
- **Non comptés** : le rejet « runtime absent » (`_reject_legacy_mutation_under_ppl_authority`), les ordres LIMIT et STOP_LIMIT (rejetés sans fenêtre), les fermetures, et le mode LEGACY (aucun changement).

Chemins de sortie couverts par le `finally` :

| Sortie | Valeur après |
|---|---|
| court-circuit admission (REJECTED_ADMISSION, REJECTED_STALE) | −1 |
| prix indisponible | −1 |
| écart OHLCV/ticker | −1 |
| refus de gate (tout code) | −1 |
| doublon ou capital insuffisant | −1 |
| FILLED | −1 |
| exception dans `_enter_admission`, `_fetch_price`, `_fill_market` ou `_exit_admission` | −1, puis l'exception est propagée telle quelle |
| `KeyboardInterrupt` / `SystemExit` | −1, puis propagation |

**Invariant** : la valeur est ≥ 0. Un décrément qui rendrait la valeur négative est un défaut de programmation, testé et signalé par une assertion dans les tests uniquement : le runtime ne lève pas d'exception dans le `finally`.

**Limite** : une pile de thread tuée sans déroulement (`os._exit`, SIGKILL) ne passe pas par le `finally`. C'est sans objet, puisque le processus meurt avec la mémoire, et relève du verdict INTERRUPTED du lot A.

### 5.2 `lifecycle_transitions_in_flight` (ensemble `_ppl_started_transitions`) — révisé v0.2 (C-02)

**Trois notions, sans recouvrement :**

| Notion | Définition | Où |
|---|---|---|
| **commencée** | la clé `(kind, trade_id)`, `kind ∈ {OPEN, CLOSE}`, a été ajoutée à `_ppl_started_transitions` sous `sim._lock`, juste avant le premier `commit_open` ou `commit_close` | simulateur |
| **inachevée** | commencée, et la mise à jour mémoire de **cette même** transition n'a pas été terminée. Sous `sim._lock`, une transition inachevée est toujours une transition **interrompue par une exception**, puisque la section critique ne peut pas être observée en cours | simulateur |
| **divergente** | classification de diagnostic d'une transition inachevée, par comparaison durable/mémoire | observateur |

**Valeur publiée** : `lifecycle_transitions_in_flight = len(_ppl_started_transitions)`, c'est-à-dire le **nombre de transitions inachevées**. Elle est lue sous `sim._lock` et **ne dépend d'aucune lecture durable**.

- **Ajout** : sous `sim._lock`, juste avant le premier appel de commit.
- **Retrait** : uniquement sous `sim._lock`, après la mise à jour mémoire réussie de la **même** transition, que ce soit au premier essai ou lors d'une reprise idempotente ultérieure de la même clé.
- **Aucun autre retrait.** En particulier, il n'y en a **pas** après un refus avant l'append, ni après une relecture durable, ni à l'observation. Une transition inachevée bloque la quiescence pour toute la vie du processus, sauf reprise réussie de la même clé.
- **Sur exception** : aucune action sur l'ensemble ; l'exception est propagée inchangée.

**Classification de diagnostic** (champ informatif `lifecycle_transitions_detail`, non requis par `assess`), calculée par l'observateur sous `sim._lock` puis `runtime._lock`, après validation de la chaîne (§4.8, règle 1) :

| Classe | Condition |
|---|---|
| `NOT_APPLIED` | chaîne valide ; événement de la clé absent ; mémoire inchangée pour `trade_id` |
| `APPLIED_DURABLE_NOT_MEMORY` | chaîne valide ; événement présent ; mémoire pas à jour |
| `UNRESOLVED` | chaîne invalide ou illisible, runtime en erreur, ou toute combinaison non listée |

Toutes les classes comptent dans la valeur publiée. Aucune classe, et surtout pas `UNRESOLVED`, ne réduit la valeur. Une lecture durable incertaine ne peut donc que laisser la classification bloquante.

**Cas de reprise :**
- **Refus sémantique avant l'append** (le runtime passe en `DEGRADED`, fait à 7cd4c4e9) : valeur 1, classe `NOT_APPLIED`. La clé **reste** et la quiescence est bloquée jusqu'à l'arrêt du processus.
- **OPEN déchiré** (événement durable, mémoire non mise à jour) : valeur 1, classe `APPLIED_DURABLE_NOT_MEMORY`. Aucune reprise dans le processus, puisque l'ordre a disparu et que le contrôle de doublon durable refuse tout nouvel OPEN sur le symbole. Conséquence existante, visible, non corrigée : la position n'est pas surveillée par ce processus.
- **CLOSE déchiré** : valeur 1. Si TP, SL ou TIMEOUT se redéclenche, `_durable_close` rejoue les mêmes faits : `ALREADY_EXISTS` côté store, mise à jour mémoire, retrait de la clé, valeur 0, aucun second événement. Sinon, la valeur 1 persiste.
- **OSError après append, puis reprise réussie dans la même section** (chemin existant de `commit_open`) : la mise à jour mémoire se fait, retrait, valeur 0.

**Compatibilité exacte avec le lot A (contrat A v1.2 → v1.3) :**
- Nom de champ inchangé : `lifecycle_transitions_in_flight`, dans `ORDER_FIELDS` et `ZERO_COUNTER_FIELDS`.
- Avec déclaration valide (D-C1a-5) : `OBSERVED`, valeur `int` strict ≥ 0 (jamais `bool`), provenance `"len(simulator._ppl_started_transitions) under sim._lock (PPL-QUIESCENCE-COUNTERS-V1)"`. Le prédicat existant `_count` l'accepte, et `quiescent` exige 0.
- Sans déclaration : `NOT_APPLICABLE`, texte identique à 7cd4c4e9. Les tests du lot A (l. 241-244 et 1018) restent inchangés.
- `to_epoch_rotation_quiescence` reporte la valeur dans `EpochRotationQuiescence.authority_transitions_in_flight`, dont la sémantique (0 exigé) est compatible.
- Verdict `INTERRUPTED` : `historical_unknowns` contient toujours ce champ. Le compteur d'un processus mort n'est jamais une preuve.
- `ppl_interrupted_succession` : la preuve d'un prédécesseur interrompu garde `lifecycle_transitions_in_flight = UNKNOWN` (`_UNKNOWN_FIELDS`). C1a ne l'alimente pas.
- Le texte du contrat A v1.3 définira le champ comme « transitions inachevées (y compris interrompues) », et non plus « en cours d'exécution ».

**Limite** : en régime normal, l'ensemble est vide à chaque lecture. La mesure détecte des transitions interrompues ; elle ne capture pas une transition en cours.

**Chemins couverts** : inchangés par rapport à v0.1 (`_fill_market_ppl_authority` et `_close_position_ppl_authority`, seuls sites de commit hors tests).

---

## 6. Point 3 — Provenance et limites de `code_sha`

Trois provenances sont distinguées et ne se substituent jamais l'une à l'autre :

| Provenance | Source | Nature |
|---|---|---|
| `MANIFEST_DECLARED` | `manifest.code_sha` | configuration de l'epoch |
| `CONSTRUCTOR_DECLARED` | `gate_wiring_code_sha` passé au simulateur | configuration du processus |
| `FILE_BYTES_AT_CONSTRUCTION` | sha256 des fichiers `mexc_simulator.py` et `ppl_admission_gate.py` lus au moment de la construction | empreinte informative |

**Règles :**

- Le simulateur **ne copie jamais** `manifest.code_sha` dans sa déclaration. Sinon, l'égalité vérifiée par `gate_wiring_value` deviendrait une tautologie. La valeur vient de l'appelant (en C1b, le bootstrap, avec une source à décider à ce moment-là). Sans valeur, aucune déclaration : `UNKNOWN`.
- La déclaration est publiée seulement si gate **et** `code_sha` sont présents :
  ```
  ppl_gate_wiring_v1 = {
    "protocol": "PPL-GATE-WIRING-V1",
    "code_sha": <CONSTRUCTOR_DECLARED>,
    "code_sha_provenance": "CONSTRUCTOR_DECLARED",
    "consults_gate_under_lock": True,
    "counters_protocol": "PPL-QUIESCENCE-COUNTERS-V1",
    "module_sha256": {"paper_trading/mexc_simulator.py": "...",
                      "paper_trading/ppl_admission_gate.py": "..."},
    "module_sha256_provenance": "FILE_BYTES_AT_CONSTRUCTION",
  }
  ```
  Les clés en plus sont compatibles avec `gate_wiring_value` à 7cd4c4e9, qui lit avec `.get`.
- `consults_gate_under_lock` est une constante du code qui contient effectivement l'appel. Il ne dépend d'aucune configuration. Sa vérité est démontrée par les tests à ce SHA source (SOURCE PROOF), jamais par la déclaration elle-même.
- **Limites, en toutes lettres :**
  - la déclaration est une affirmation du code testé, pas une attestation ;
  - l'égalité avec le manifeste prouve seulement la cohérence de deux configurations ;
  - les empreintes de fichiers ne prouvent pas que ces octets ont été importés (le fichier a pu changer après l'import, `.pyc` ou chemin d'import différent) ;
  - aucune de ces valeurs ne vaut RUNTIME PROOF.
- Une identité de code réellement attestée (release immuable, signature, empreinte des modules importés via `module.__spec__`) est **hors périmètre** de C1a (R1).

---

## 7. Point 4 — Défaut sans gate, et CLOSE toujours possible

- **Sans gate** (`admission_gate=None`, le défaut) :
  - aucune lecture de gate ;
  - aucune nouvelle écriture ;
  - aucune déclaration ;
  - le ledger PPL, le ledger d'admission, les notifications et la mémoire restent identiques, octet pour octet, à 7cd4c4e9 pour la même séquence synthétique, à uuid et horloge figés (AC1).
  - Les compteurs sont maintenus en mémoire mais non publiés. `observe_runtime` rend exactement ce qu'il rend aujourd'hui (NOT_APPLICABLE et UNKNOWN) : les tests du lot A, l. 241-244 et 1018, restent valides sans modification.
- **Mode LEGACY** : inchangé. Une gate fournie est refusée à la construction.
- **CLOSE** : `_close_position_ppl_authority`, `_check_positions` (TP, SL, TIMEOUT) et la reprise `_durable_close` n'appellent **jamais** la gate. Une gate fermée, absente, corrompue ou verrouillée n'empêche aucune fermeture. Seul le compteur de transitions s'applique au CLOSE.
- **Aucun autre effet** : aucune lecture de `PB_MAX_POSITIONS`, des frais (`_TAKER_FEE`, `_SLIPPAGE`), du capital ou de l'environnement dans le nouveau code. Aucun changement de sizing, de seuils, de stratégie, de manifeste ou d'epoch.

---

## 8. Point 5 — Fail-closed, ordre des verrous, scénarios

### 8.1 Conditions fail-closed (OPEN refusé, aucune écriture PPL)

| Code | Condition |
|---|---|
| `GATE_NEVER_OPENED` | verrou, répertoire ou journal absent, ou journal vide |
| `GATE_LOCK_INVALID` | `<journal>.lock` en lien symbolique ou non régulier |
| `GATE_LOCK_TIMEOUT` | flock non obtenu dans `_GATE_LOCK_TIMEOUT_S` |
| `GATE_LOCK_IDENTITY_CHANGED` | `(dev, ino)` du descripteur ≠ chemin |
| `GATE_CLOSED_MARKER` | marqueur présent à t1 ou t3, `lstat` en erreur, ou `_forced_closed` |
| `GATE_CLOSED_JOURNAL` | dernier enregistrement CLOSE |
| `GATE_JOURNAL_INVALID` | chaîne cassée, champs invalides, autre epoch ou manifeste, lien symbolique, non régulier, lecture déchirée |
| `GATE_READ_ERROR` | toute autre exception |

**Effet d'un refus :**
- `order.status = REJECTED`, `order.reject_code = <code>`. Champ nouveau, optionnel, `None` par défaut. `MexcOrder` n'est sérialisé nulle part (grep).
- `_exit_admission` enregistre `WriteResult.REJECTED_GATE_CLOSED` (valeur additive) avec `anomaly=<code>`.
- Notification `[SIM] REJETE <symbol> — gate d'admission <code>`.
- Aucun appel au runtime, aucun incrément de génération.

**Compatibilité de `REJECTED_GATE_CLOSED` : inventaire exhaustif à 7cd4c4e9.** `grep` sur `.py .ts .tsx .js .sh .sql`, hors `node_modules`, pour `write_result`, `ADMISSION_OUTCOME`, `REJECTED_*`, `WriteResult` et `admission_ledger`.

| Lecteur | Usage de `write_result` | Effet de la nouvelle valeur |
|---|---|---|
| `paper_trading/admission_ledger.py` (`events`, `pairs`) | aucun ; JSON brut, appariement par `attempt_id` | aucun |
| `paper_trading/admission_types.py` | définition de l'enum ; aucun parseur depuis le JSON | valeur ajoutée, aucune retirée ni renommée |
| `research_data/stress_d1_capture.py` | appariement ATTEMPT/OUTCOME, métriques de paires | aucun |
| `research_data/stress_d1_snapshot_audit.py` | appariement, cohérence de symbole et d'horodatage | aucun |
| `research_data/stress_d1_operator_stage.py` | copie par préfixe d'octets (`ts`) | aucun |
| `research_data/paper_exporter.py`, `operator.py`, `burn_in_finalization.py` | statut déclaré de la source `admission_ledger`, sans matérialiser les lignes | aucun |
| `observability/ppl_comparison.py` | lit l'état de gel Legacy du simulateur, pas le ledger | aucun |
| frontend (`src/`) | « admission » y désigne l'admission de décision, pas ce ledger | aucun |
| tests (`test_admission_*`, `test_historical_admission_matrix`, `test_ppl_comparison`, `test_stress_d1_*`, `test_rl_data_01_*`) | assertions sur des valeurs précises existantes | aucun ; ces tests ne produisent pas la nouvelle valeur |
| documents (`docs/research/paper_stress_404/*`, `RL_DATA_01_F00_SOURCE_STATUSES.json`, audits) | descriptifs, aucun vocabulaire fermé de `write_result` | aucun ; à mentionner au journal des valeurs à la fusion |

Aucun lecteur n'énumère un ensemble fermé de valeurs. Les lignes historiques étiquetées `REJECTED_INSUFFICIENT_CAPITAL` ne sont **pas** réinterprétées. Une future Research qui classerait ces rejets devra traiter la nouvelle valeur explicitement ; c'est consigné ici, pas anticipé dans le code.

Preuve exigée (§8.3, scénario 17) : chaque lecteur exécutable est passé sur deux ledgers synthétiques identiques, à l'exception de la valeur `write_result` (`REJECTED_GATE_CLOSED` contre `REJECTED_INSUFFICIENT_CAPITAL`). Les sorties doivent être égales à cette valeur près, et aucun lecteur ne doit lever d'exception ni signaler de défaut.

**Preuve obtenue, lecteur par lecteur (après contre-revue C1a, 2026-11-12).** Les jumeaux sont produits par le simulateur réel (une paire `FILLED`, une paire refusée par la gate), puis dupliqués en remplaçant seulement les octets de l'étiquette. L'inventaire a été refait par `grep` sur l'arbre C1a : aucun nouveau lecteur.

| Lecteur | Portée de la preuve | Test |
|---|---|---|
| `AdmissionLedger.events`, `AdmissionLedger.pairs` | **exécuté** : sorties égales hors `write_result` | `test_s17_ledger_readers_are_label_invariant` |
| `stress_d1_capture._coverage` (appariement et métriques de paires) | **exécuté** : sorties égales, aucun défaut `ADMISSION_ORPHAN_OR_UNPAIRED` | idem |
| `stress_d1_snapshot_audit.count_summary` | **exécuté** : sorties égales | idem |
| `stress_d1_operator_stage.acquire_one` (copie par préfixe) | **exécuté** dans `tmp_path` (`SOURCE` redirigé) : résultats égaux hors empreintes et tailles, copie verbatim, étiquette jamais interprétée | `test_s17_operator_stage_copy_is_label_invariant` |
| `WriteResult` (`admission_types`) | **exécuté** : `WriteResult("REJECTED_GATE_CLOSED")` se résout | `test_s17_ledger_readers_are_label_invariant` |
| `stress_d1_capture.capture`, `stress_d1_snapshot_audit.audit` (points d'entrée complets) | **borné, non exécuté** : ils enveloppent les fonctions ci-dessus de contrôles de fichiers, de manifeste et d'empreintes qui ne lisent pas `write_result` (grep) ; un manifeste signé de la capture D1 serait nécessaire | — |
| `stress_d1_operator_stage.main` | **borné, non exécuté** : exige root et écrit sous `/var/lib` ; il n'appelle `acquire_one` qu'avec les mêmes paramètres | — |
| `paper_exporter`, `operator`, `burn_in_finalization` | **borné, non exécuté** : ne lisent que le statut déclaré de la source `admission_ledger` ou l'empreinte du fichier, jamais ses lignes (grep) ; une empreinte diffère naturellement entre deux contenus différents | — |
| `observability/ppl_comparison.py`, frontend `src/` | **hors périmètre** : ne lisent pas ce ledger (grep) | — |

### 8.2 Ordre des verrous (unique)

Voir §4.7. Attentes ajoutées :
- sous `sim._lock`, jusqu'à `_GATE_LOCK_TIMEOUT_S` (0,25 s) pour obtenir le flock, plus la durée de `commit_open` (fsync) pendant laquelle le flock est tenu ;
- `drain_barrier` et la partie journal de `close()` attendent au plus la durée d'un commit en cours ;
- le `close()` existant garde son timeout d'une seconde. S'il expire pendant un commit anormalement long, le marqueur reste effectif et seul l'enregistrement CLOSE manque, comme à 7cd4c4e9.

### 8.3 Scénarios à tester

Tous les tests sont synthétiques et hors réseau. Ils s'exécutent dans `tmp_path` et dans la copie isolée. Il n'y a ni exchange ni Telegram.

1. **Défaut identique (AC1).** Séquence fixe (OPEN, TP, SL, TIMEOUT, doublon, capital insuffisant, prix indisponible), uuid et `time.time` figés. Les ledgers PPL et d'admission et la liste des notifications sont comparés à une référence produite par le code de 7cd4c4e9 dans le même venv.
2. **Matrice de gate (AC2).** Journal absent, vide, CLOSE final, marqueur présent, ligne corrompue, ligne tronquée, journal en lien symbolique, marqueur en répertoire, autre epoch, autre manifeste, flock tenu par un autre processus, `lstat` en erreur (injection, car les permissions sont inopérantes en root). Résultats attendus : OPEN refusé avec le bon code, empreinte du store PPL inchangée, outcome `REJECTED_GATE_CLOSED`.
3. **Gate OPEN (AC3a).** OPEN accepté, ledger conforme.
4. **Fermeture pendant la récupération du prix (AC3b).** `_fetch_price` est bloqué sur un `threading.Event`, `close()` est appelé, puis l'évènement est relâché : refus.
5. **Course au point de linéarisation (AC3c).** Détaillée par la matrice d'interleaving déterministe (§8.4, I1–I13).
6. **Fermeture depuis un autre processus (AC3d), corrigé v0.3.** Un processus fils exécute `close()` pendant que le parent, qui consulte la gate, enchaîne les tentatives d'OPEN. Le test n'exige **pas** l'absence d'écriture durable au retour de `close()` : un OPEN admis avant la fermeture peut encore être persisté (N1, N2). Il exige, dans le domaine des processus qui consultent la gate :
   - (a) **aucun nouvel OPEN admissible après la fermeture** : toute tentative dont le contrôle commence (t1) après le retour de `close()` rend un code de refus de gate, et le nombre d'admissions `GATE_OPEN` cesse de croître ;
   - (b) puis, après `drain_barrier` = `DRAINED` (chaîne du ledger validée selon §4.8, règle 1), **aucun OPEN durable supplémentaire** : le nombre d'événements `POSITION_OPENED` relevé juste après `DRAINED` est identique après de nouvelles tentatives et après l'arrêt du parent ;
   - (c) le nombre d'OPEN durables entre le retour de `close()` et `DRAINED` est consigné (0 ou 1 par processus admetteur) et n'est pas une erreur.
7. **CLOSE avec gate fermée (AC4).** TP, SL et TIMEOUT sont committés, le compteur de transitions revient à 0.
8. **Compteur d'admissions (AC5).** On vérifie 1 pendant la récupération bloquée, lu sous `sim._lock` depuis un autre thread, puis 0 après chacune des sorties du tableau du §5.1, y compris une exception injectée dans `commit_open` et un `KeyboardInterrupt` injecté.
9. **Compteur de transitions (AC6), révisé v0.2.**
   - TT1 : OPEN puis CLOSE normaux. Ensemble vide, valeur `OBSERVED 0`, type `int`.
   - TT2 : refus sémantique avant l'append. Valeur **1**, clé **conservée**, classe `NOT_APPLIED`, empreinte du store inchangée, non quiescent.
   - TT3 : `OSError` après un append visible, reprise réussie. Valeur 0.
   - TT4 : `OSError` après un append visible, reprise en échec. Valeur 1, classe `APPLIED_DURABLE_NOT_MEMORY`, `memory_matches_durable` faux, non quiescent.
   - TT5 : CLOSE déchiré, même déclenchement au tick suivant. `ALREADY_EXISTS`, aucun second événement, valeur 1 → 0.
   - TT6 : CLOSE déchiré sans nouveau déclenchement. Valeur 1 maintenue.
   - TT7 : store rendu illisible (ligne finale tronquée) au moment de l'observation, avec une clé inachevée. Valeur toujours 1, classe `UNRESOLVED`, champs de ledger UNRESOLVED, non quiescent.
   - TT8 : sans déclaration. `NOT_APPLICABLE`, texte identique à 7cd4c4e9 ; tests du lot A inchangés.
   - TT9 : `to_epoch_rotation_quiescence` reporte exactement la valeur ; un `bool` injecté est refusé par `_count`.
   - TT10 : verdict `INTERRUPTED` et preuve de succession interrompue : le champ reste `UNKNOWN`.
10. **Déclaration (AC7).**
    - Gate et `code_sha` égal au manifeste : `runtime_consults_gate` OBSERVED à true.
    - `code_sha` différent du manifeste : UNRESOLVED.
    - Sans `code_sha` ou sans gate : UNKNOWN, et les compteurs ne sont pas publiés.
    - Le simulateur ne recopie jamais `manifest.code_sha`.
11. **Quiescence de bout en bout (AC8).** Gate fermée, positions drainées par TP et SL, O, sentinelle, puis témoin synthétique : `quiescent` vrai. Chaque condition est ensuite retirée une à une, et l'état doit redevenir non quiescent.
12. **Environnement neutre (AC9).** On fait varier `PB_MAX_POSITIONS`, `MEXC_SIM_FEE` et `MEXC_SIM_SLIP` (noms réels, lus à l’import du module ; correction de v0) ; le résultat du contrôle de gate ne change pas. Une sonde sur `os.environ` et `os.getenv` pendant `admission_hold` et `drain_barrier` ne relève aucun accès.
13. **Ordre des verrous (AC10).** Stress concurrent OPEN, CLOSE, observation O et `close()` de gate, avec des `join(timeout)` bornés. Aucun interblocage, invariants des compteurs respectés.
14. **Refus à la construction.** Gate en mode LEGACY, gate sans runtime, gate d'une autre epoch, gate d'un autre manifeste, `code_sha` sans gate, `code_sha` mal formé.
15. **Non-régression (AC11, AC12).** `tests/paper_trading` complet, puis le corpus `pytest -m "not performance and not slow" tests/`, et enfin la gate ruff 0.15.8. Les journaux sont conservés.

---

16. **Zéro écriture (D-C1a-2).** Sonde d'appels système et instantané du répertoire (§4.6), pour chaque code de §8.1, pour `GATE_OPEN` et pour les quatre statuts de `drain_barrier`. Cas dédiés : répertoire parent absent, verrou absent avec journal OPEN.
17. **Compatibilité du ledger (D-C1a-3).** Lecteurs passés sur les ledgers jumeaux (§8.1).
18. **Transitions inachevées (D-C1a-4), révisé v0.2.** Chaque classe du tableau de §5.2, au moins une fois (TT2, TT4, TT7). OPEN déchiré : valeur 1 et nouvel OPEN sur le symbole refusé. Aucun test n'attend un retrait de clé hors d'une mise à jour mémoire réussie de la même transition.
19. **Frontière des exceptions d'`admission_hold` (C-01).** Pour chaque cas, on vérifie : (a) l'exception sortant de `place_market_order` est **le même objet** (`is`) que celle injectée ; (b) le flock est libre (un autre processus obtient `LOCK_EX | LOCK_NB` aussitôt) ; (c) aucun descripteur ne fuit (`/proc/self/fd` identique) ; (d) `order.reject_code` n'est pas un code de gate ; (e) `admissions_in_flight` revient à 0. Cas :
   - H1 : `OSError` dans `commit_open`, OPEN non visible → propagée ;
   - H2 : `OSError` visible, puis reprise en `OSError` → la seconde est propagée ;
   - H3 : `KeyboardInterrupt` dans `commit_open` → propagée ;
   - H4 : `SystemExit` dans `commit_open` → propagée ;
   - H5 : `KeyboardInterrupt` pendant l'attente du flock (`fcntl.flock` enveloppé) → propagée, **pas** convertie en `GATE_LOCK_TIMEOUT` ;
   - H6 : `SystemExit` pendant `_records()` → propagée ;
   - H7 : `OSError` sur `os.open` du verrou → refus `GATE_READ_ERROR`, sans exception ;
   - H8, corrigé v0.3 : `os.close` lève `OSError` dans `__exit__` alors qu'une exception du corps se propage → l'exception du corps est conservée, **et la libération réelle est prouvée** :
     - injection fidèle à Linux (`close(2)` libère le descripteur même en cas d'erreur) : l'enveloppe appelle d'abord le vrai `os.close(fd)`, **puis** lève `OSError(EIO)` ;
     - preuve de libération du descripteur : aucune entrée de `/proc/self/fd` ne résout (`os.stat` sur le lien) vers le `(st_dev, st_ino)` de `<journal>.lock` relevé à l'acquisition (comparer l'inode, pas le numéro de descripteur, qui peut être réutilisé) ;
     - preuve de libération du flock : un **processus distinct** obtient `flock(LOCK_EX | LOCK_NB)` sur le verrou immédiatement, sans attente ; un `drain_barrier(timeout_s=0)` rend `DRAINED` ;
     - le code ne refait **jamais** `os.close` après une erreur : le numéro pourrait déjà appartenir à un autre thread ;
     - une `OSError` simulée **avant** la vraie fermeture ne correspond à aucun comportement de Linux et **ne vaut pas preuve**. Elle n'est utilisée qu'en test négatif documentaire (H8-neg), qui montre que le flock resterait alors tenu, et qui n'est pas un critère d'acceptation ;
   - H9 : `RuntimeError` arbitraire dans le corps → propagée, `__exit__` rend faux.
20. **Récupération après interruption pendant l'append (C-03).** Processus fils réel, store et gate dans `tmp_path`. `_durable_append` est enveloppé **dans le fils** pour écrire `k` octets de la ligne puis s'envoyer `SIGKILL`, avec `k` ∈ {0, moitié, ligne complète sans `fsync`, ligne complète avec `fsync`}. Dans le parent :
   - `drain_barrier` → `DRAINED` dans les quatre cas ; le test affirme explicitement que ce résultat **ne** sert **pas** de preuve d'intégrité ;
   - validation de la chaîne (§4.8, règle 1) **avant** toute assertion sur le contenu ;
   - `k=0` : chaîne valide, OPEN absent, `NOT_APPLIED` ;
   - `k=moitié` : `StoreCorruptionError`, état `UNRESOLVED`, observation du lot A non quiescente, aucune conclusion sur l'OPEN ;
   - lignes complètes : chaîne valide, OPEN présent, `VISIBLE_DURABILITY_UNCONFIRMED` ;
   - empreinte sha256 du fichier d'epoch identique avant et après les contrôles du parent : aucune réparation ;
   - variante : `SIGKILL` pendant `open()` ou `close()` de la gate, journal de gate tronqué → `admission_hold` rend `GATE_JOURNAL_INVALID`.

### 8.4 Matrice d'interleaving déterministe

**Méthode.** Le code de production ne reçoit aucun crochet de test. Les points de rendez-vous sont obtenus en enveloppant, dans les tests, `gate._marker_present`, `gate._records`, `os.open` et `fcntl.flock` (pour le module de la gate seulement), `runtime.store.append` et `runtime.commit_open`. Chaque point bloque sur un `threading.Event`, ou sur un tube pour un autre processus. Le fermeur est un thread, ou un processus fils piloté par tube. L'ordre est imposé et aucune attente n'est temporisée, à part des timeouts de garde.

Points de l'admission : **P1** après t1 ; **PF** après l'obtention du flock, avant le contrôle d'identité ; **P2** après t2 ; **P3** après t3 ; **P4** dans `store.append`, avant l'écriture ; **P5** après le fsync du store, avant le retour de `commit_open` ; **P6** après la libération du flock.

| # | Marqueur créé (thread ou processus fils) | Résultat d'admission | Événement OPEN | `drain_barrier` lancé juste après le marqueur | Enregistrement CLOSE (`close()`) |
|---|---|---|---|---|---|
| I1 | avant t0 | `GATE_CLOSED_MARKER` | absent | DRAINED immédiat | après rien |
| I2 | à P1 | `GATE_CLOSED_JOURNAL`, refus à **t2** (révisé après contre-revue : le flock est libre à P1, `close()` ajoute CLOSE avant t2) | absent | DRAINED après P6 | **ajouté** avant t2 |
| I3 | à P2 | `GATE_CLOSED_MARKER`, refus à t3 | absent | DRAINED après P6 | **absent** : `close()` expire (1 s) sur le flock de l'admetteur et rend True sans enregistrement |
| I4 | à P3 | **admis** | présent, persisté **après** le marqueur | bloqué jusqu'à P6 ; DRAINED ; ledger contient l'OPEN à ce moment | ajouté après l'OPEN |
| I5 | à P4 | admis | idem I4 | idem I4 | idem I4 |
| I6 | à P5 | admis | persisté **avant** le marqueur | DRAINED après P6 | après l'OPEN |
| I7 | à P6 | admis | avant le marqueur | DRAINED immédiat | après l'OPEN |
| I8 | `drain_barrier` tient le flock avant t1 (marqueur posé) | `GATE_CLOSED_MARKER` à t1 | absent | — | — |
| I9 | autre processus tient le flock > 0,25 s, sans marqueur | `GATE_LOCK_TIMEOUT` | absent | `NOT_CLOSED` | — |
| I10 | à P4, puis commit bloqué > 1 s | admis | présent | `drain_barrier(timeout=0,1)` → `DRAIN_TIMEOUT` ; `timeout=5` → DRAINED | `close()` rend True, **sans** enregistrement CLOSE (timeout 1 s) |
| I11 | à P4, puis SIGKILL du processus admetteur | inconnu | E0, E1 (partiel), E2 ou E3 (§4.8) ; aucune conclusion sans validation de la chaîne | DRAINED (flock libéré par le noyau) ; **ne prouve pas l'intégrité** | — |
| I12 | remplacement de `<journal>.lock` (unlink puis recréation) **à PF**, après l'obtention du flock et avant le contrôle d'identité (révisé après contre-revue) | `GATE_LOCK_IDENTITY_CHANGED` | absent | `DRAIN_ERROR` si le remplacement survient au point PF du drainage | — |
| I12b | même remplacement **à P1**, avant l'`open` du verrou par l'admetteur | **admis** : l'admetteur ouvre et verrouille le nouvel inode, l'identité concorde | présent | — | — |
| I13 | thread observateur O du lot A à P1…P5 | O attend `sim._lock` ; sa lecture suit P6 et voit la position | — | — | — |

Chaque ligne est jouée en variante thread et en variante processus fils, sauf I11 (processus seulement), I13 et I12b (thread seulement). Pour I12, la variante porte sur l'auteur du remplacement (thread ou processus).

### 8.5 Tableau des garanties réellement obtenues

| Garantie | Statut | Condition | Test |
|---|---|---|---|
| Un contrôle atteignant t1, t2 ou t3 après la création du marqueur refuse | **OBTENUE** | gate consultée | I1–I3, I8 |
| Aucun OPEN persisté après la création du marqueur | **NON OBTENUE** | — | négatif : I4, I5 démontrent un OPEN persisté après |
| Tout OPEN admis est durable avant un `drain_barrier` DRAINED postérieur au marqueur | **OBTENUE** | processus consultant la gate, verrou non remplacé, flock local respecté, **`commit_open` revenu normalement** | I4–I7, I10 |
| `DRAINED` ⇒ ledger intègre ou OPEN durable | **NON OBTENUE** | — | négatif N7 (I11, scénario 20) |
| Exceptions du corps propagées inchangées, flock libéré | **OBTENUE** | — | scénario 19 |
| État récupéré conclu seulement sur chaîne valide | **OBTENUE** (règle de test et d'observation) | — | scénario 20 |
| Aucun OPEN après un `drain_barrier` DRAINED | **OBTENUE pour les processus consultant la gate** | idem | I4–I7 ; négatif N3 |
| Retour de `close()` = drainage fait | **NON OBTENUE** | — | négatif : I10 |
| Enregistrement CLOSE du journal après tout OPEN admis | **OBTENUE quand il existe** | `close()` a eu le flock | I4–I7 ; négatif : I10 (absent) |
| Horodatage `opened_at` < création du marqueur ⇒ admis avant | **NON OBTENUE** (horodatage non probant) | — | négatif N4 |
| Quiescence locale par O | **OBTENUE** | critères du lot A | I13, scénario 11 |
| Quiescence interprocessus | **NON OBTENUE par C1a** | exige l'arrêt prouvé (lot B, C1b) | négatif N3 |
| CLOSE jamais bloqué par la gate | **OBTENUE** | — | scénario 7 |
| Zéro écriture des lectures de gate | **OBTENUE** | — | scénario 16 |
| Fermeture terminale face à une altération du disque | **NON OBTENUE** | frontière de confiance A §7 | négatif N5 |

**Tests négatifs** (ils doivent démontrer la limite, pas l'infirmer) :
- **N1** (I4) : un OPEN est persisté après la création du marqueur. Le test affirme qu'il existe et qu'il est antérieur au DRAINED.
- **N2** (I10) : `close()` rend True alors qu'un commit admis est encore en cours, et le journal n'a pas d'enregistrement CLOSE.
- **N3** : un second simulateur **sans** gate, sur un autre store mais le même fichier de gate, persiste un OPEN après un DRAINED. Le drainage ne couvre que les processus qui consultent la gate.
- **N4** : un OPEN admis avec un `opened_at` antérieur à la création du marqueur est persisté après lui. L'horodatage ne prouve pas l'ordre.
- **N5** : supprimer le marqueur, journal OPEN, rouvre la gate (`GATE_OPEN`). Limite de confiance documentée, non corrigée.
- **N6** (I12) : le remplacement du verrou casse l'exclusion. `admission_hold` le détecte. `open()` et `close()` existants ne le détectent pas (R12).
- **N7** (I11, scénario 20, `k=moitié`) : `drain_barrier` rend `DRAINED` alors que le ledger est corrompu et illisible. Le drainage ne prouve pas l'intégrité.

## 9. Adaptateur A (contrat v1.3) et interface attendue pour C1b

**Lot A v1.3**, seulement des ajouts :

- `observe_runtime` lit `_ppl_admissions_in_flight` et `len(_ppl_started_transitions)` (valeur autoritaire de `lifecycle_transitions_in_flight`, §5.2) sous `sim._lock`, sans lecture durable, **uniquement** si `gate_wiring_value` rend OBSERVED à true et que la déclaration porte `counters_protocol == "PPL-QUIESCENCE-COUNTERS-V1"`. La provenance enregistrée est « simulator counter under sim._lock (PPL-QUIESCENCE-COUNTERS-V1) ». Les divergences durable/mémoire ne sont **jamais** cette valeur : elles forment le diagnostic indépendant `lifecycle_transitions_detail`, qui ne l'augmente ni ne la réduit (erratum v0.3).
- Sinon, les valeurs restent celles de 7cd4c4e9.
- `code_sha_provenance` et `module_sha256` sont copiés dans le corps de l'observation comme champs informatifs, non requis.
- `lifecycle_transitions_in_flight` = `len(_ppl_started_transitions)`, lu sous `sim._lock`, sans dépendre d'une lecture durable. Le diagnostic `lifecycle_transitions_detail` est calculé à partir de la même vue cohérente que `durable_open_positions`, sous `sim._lock` puis `runtime._lock` (§5.2, v0.2).
- `drain_barrier` n'est **pas** appelé par `observe_runtime` : il est inutile pour la quiescence locale (§4.5).
- Aucune règle d'`assess`, aucun champ requis et aucun format de preuve ne changent.

**C1b**, interface seulement, code non autorisé : le bootstrap Advisor construirait `AdmissionGate` à partir d'un chemin configuré explicitement et passerait `admission_gate` et `gate_wiring_code_sha`. Sans configuration, il passerait `None`. La source du `code_sha` côté Advisor reste à décider en C1b.

---

## 10. Choix techniques soumis à la contre-revue

| ID | Choix v0.1 | État après contre-revue v0 |
|---|---|---|
| D-C1a-1 | flock de la gate tenu de t1 jusqu'au retour de `commit_open` (timeout d'acquisition 0,25 s) + `drain_barrier` en lecture seule ; garantie de fermeture « après drainage » | **RÉVISÉ**, à revoir |
| D-C1a-2 | API publique en lecture seule : `admission_hold` (remplace `admission_check`) et `drain_barrier`, zéro écriture démontrée (§4.6) | GO sous réserve ; preuve spécifiée |
| D-C1a-3 | `REJECTED_GATE_CLOSED` + `MexcOrder.reject_code` ; inventaire des lecteurs (§8.1) | GO conditionnel ; compatibilité spécifiée |
| D-C1a-4 | valeur = transitions inachevées (indépendante de toute lecture durable) ; divergence durable/mémoire en diagnostic seulement (§5.2, v0.2) | GO conditionnel ; corrigé en v0.2 (C-02) |
| D-C1a-5 | compteurs publiés seulement avec une déclaration valide | GO |
| D-C1a-6 | `code_sha` en argument du constructeur, jamais copié du manifeste | GO |
| D-C1a-7 | pas de contrôle anticipé avant le prix | GO |

**Alternatives écartées pour D-C1a-1 :**
- *Seconde lecture du marqueur après le commit* : elle laisse la même fenêtre, et un OPEN déjà durable ne peut pas être retiré (ledger en ajout seul).
- *Faire prendre le flock à `close()` avant de poser le marqueur* : la fermeture pourrait alors être retardée ou échouer sur timeout, contraire au contrat PPL-SUCCESSION-01 §5 (« closing is never refused »).
- *Écrire une intention dans PPL avant la gate* : c'est une mutation du schéma PPL, hors périmètre.
- *Faire de `close()` une barrière (`close` rend « drained »)* : cela change la sémantique de retour d'une API existante. `drain_barrier` séparé la laisse intacte.

---

## 11. Risques résiduels

- **R1, déclaration non attestée.** `consults_gate_under_lock` et `code_sha` sont des affirmations de configuration. Seuls les tests au SHA source les étayent. Aucune preuve runtime.
- **R2, fermeture non terminale contre une altération du disque.** Supprimer le marqueur, journal OPEN, rouvre la gate (N5). Frontière de confiance du lot A §7.
- **R3, compteurs et drainage limités.** Les compteurs sont locaux au processus. Le drainage ne couvre que les processus qui consultent la gate (N3). La quiescence interprocessus reste exclusivement prouvée par l'arrêt (lot B, C1b).
- **R4, attente sous `sim._lock`.** Jusqu'à 0,25 s pour le flock, plus la durée d'un commit pendant laquelle le flock est tenu. TP, SL et TIMEOUT peuvent être retardés d'autant. `drain_barrier` et la partie journal de `close()` attendent au plus un commit.
- **R5, ledger d'admission.** Une exception laisse une tentative sans outcome. Comportement existant, non corrigé.
- **R6, transitions inachevées persistantes.** Toute transition interrompue, y compris un refus avant l'append, bloque la quiescence du processus jusqu'à son arrêt, sauf reprise réussie de la même clé. Un OPEN déchiré n'a pas de reprise et la position durable n'est pas surveillée par ce processus. Un CLOSE déchiré ne se résout que si le déclenchement se reproduit. Visible, bloquant, non corrigé (Scientific Debt Rule).
- **R7, système de fichiers.** flock, `O_EXCL` et fsync sont supposés locaux et respectés. Sur NFS, flock est émulé par des verrous `fcntl`, et un verrou exclusif sur un descripteur `O_RDONLY` peut y échouer : le résultat serait `GATE_LOCK_TIMEOUT` ou `DRAIN_ERROR`, donc fail-closed, mais non testé.
- **R8, portée de la preuve.** Rien ne s'applique au runtime gelé `116634be`. Une fusion source ne vaut pas déploiement.
- **R9, prix récupéré avant le contrôle.** Inchangé.
- **R10, environnement de test.** Tests exécutés en root : les refus par permission sont simulés par injection.
- **R11, horodatages.** `opened_at` est antérieur à t3. Il ne doit jamais servir à ordonner un OPEN par rapport à la fermeture (N4).
- **R12, remplacement du verrou.** `admission_hold` et `drain_barrier` détectent un `<journal>.lock` remplacé. `open()` et `close()` existants ne le font pas : un OPEN de gate et un CLOSE de journal pourraient se croiser sur deux inodes différents. Le marqueur, sans verrou, reste prioritaire, donc la fermeture n'est pas affectée.
- **R13, `atime`.** La lecture peut mettre à jour l'`atime` selon le montage. Ce n'est pas une écriture du code, et il est exclu de la preuve de zéro écriture.
- **R14, perte du cache de pages.** Une coupure d'alimentation ou un crash noyau ne sont pas simulés. Les états E2 et E3 sont indiscernables pour un lecteur. Aucune affirmation de durabilité n'est tirée d'une lecture.
- **R15, ledger corrompu après interruption.** Un état E1 rend l'epoch illisible dans son ensemble (comportement existant de `load_epoch`). C1a ne répare rien. L'état est UNRESOLVED jusqu'à une procédure opérateur distincte.

---

## 12. Ce qui reste interdit à ce stade

- Pas de code source, ni pour C1a ni pour C1b, avant la contre-revue de ce v0.
- Pas de commit, de push, de PR ou de branche distante.
- Pas de VPS, pas d'Advisor, pas d'epoch.
- Pas d'écriture dans PPL, FIN ou PAPER.
- Pas de TESTNET, de LIVE ni d'ordre.
- #286 et #282 sont préservés intégralement.
- Aucun changement de stratégie, de sizing, de capital, de frais ou de `PB_MAX_POSITIONS`.

---

## 13. Journal des versions

- **v0** (`2cd05bc0…fe38`) : flock de la gate libéré après t3, avant `commit_open` (défaut relevé par la contre-revue) ; transitions avec relecture au moment de l'exception ; compatibilité du ledger affirmée sur trois lecteurs.
- **v0.1** (ce document) : flock tenu jusqu'au retour de `commit_open` ; `admission_hold` et `drain_barrier` ; quatre notions distinguées (§4.4) ; critères de quiescence locale et interprocessus (§4.5) ; zéro écriture spécifiée et testée (§4.6) ; transitions par cohérence de clé (§5.2) ; inventaire complet des lecteurs (§8.1) ; matrice d'interleaving I1–I13 et tests négatifs N1–N6 (§8.4, §8.5) ; R11–R13 ; noms réels des variables de frais au scénario 12.
- **v0.2** (`2ab37b67…3827`) : addendum C-01, C-02 et C-03 (§14), sans changement de protocole ni d'architecture.
- **v0.3** (ce document) : erratum §9, AC3d, H8 (§15).

---

## 14. Addendum v0.2 — corrections C-01, C-02, C-03 et critères d'acceptation

| ID | Problème relevé sur v0.1 | Modification exacte | Critère d'acceptation |
|---|---|---|---|
| C-01 | « Toute exception interne donne `GATE_READ_ERROR` » pouvait capturer les exceptions du corps du `with` (dont `commit_open`) | §4.1 : deux phases ; seules les `Exception` d'acquisition et de validation sont converties ; `BaseException` jamais convertie ; corps jamais intercepté ; `__exit__` rend faux ; fermeture dans `finally` ; `os.close` en erreur absorbé ; classe explicite, pas de générateur | AC-C01 : scénario 19 (H1–H9), tous verts ; la même exception (`is`) sort de `place_market_order` ; flock libre et aucun descripteur en fuite après chaque cas |
| C-02 | Valeur dépendante d'une relecture durable ; scénario 9 hérité de v0 annonçant un retrait de clé après refus avant append | §5.2 : commencée, inachevée et divergente distinguées ; valeur = nombre d'inachevées, sans lecture durable ; retrait uniquement après mise à jour mémoire réussie de la même transition ; divergence en diagnostic (`NOT_APPLIED`, `APPLIED_DURABLE_NOT_MEMORY`, `UNRESOLVED`), jamais réductrice ; compatibilité lot A et succession ; scénarios 9 et 18 réécrits | AC-C02 : TT1–TT10 verts ; aucun test n'attend un retrait hors mise à jour mémoire réussie ; tests du lot A existants inchangés et verts ; `UNRESOLVED` n'abaisse jamais la valeur |
| C-03 | I11 assimilait la libération du flock à un état sûr (« jamais partiel ») | §4.8 : DRAINED ≠ intégrité ; états E0–E3 ; validation de la chaîne obligatoire avant toute conclusion ; UNRESOLVED sinon ; aucune réparation ; I11, §8.5 (N7), R14, R15 | AC-C03 : scénario 20 vert pour les quatre valeurs de `k` ; la validation de chaîne précède toute assertion ; le fichier d'epoch reste identique octet pour octet après les contrôles ; N7 démontre DRAINED avec un ledger corrompu |

**Inchangé** : protocole D-C1a-1 accepté (flock tenu pendant `commit_open`, `drain_barrier` distinct, fermeture garantie après drainage) ; D-C1a-2, 3, 5, 6 et 7 ; interface du simulateur ; ordre des verrous ; périmètre ; interdictions du §12.

---

## 15. Erratum v0.3 — ajustements obligatoires de la contre-revue du 2026-11-12T03:54Z

| # | Défaut de v0.2 | Correction exacte | Critère d'acceptation |
|---|---|---|---|
| 1 | §9, premier point : « le nombre de clés divergentes de `_ppl_started_transitions` », en contradiction avec §5.2 | §9 : valeur autoritaire = `len(_ppl_started_transitions)`, lue sous `sim._lock` sans lecture durable ; divergences = diagnostic indépendant `lifecycle_transitions_detail` qui n'altère jamais la valeur | TT2, TT4 et TT7 : la valeur publiée égale `len(_ppl_started_transitions)` quelle que soit la classe ; aucun chemin d'`observe_runtime` ne dérive la valeur du diagnostic |
| 2 | AC3d (scénario 6) exigeait l'absence d'OPEN écrit dès le retour de `close()`, ce que le protocole ne garantit pas (§8.5, N1, N2) | Scénario 6 : (a) aucun nouvel OPEN admissible après la fermeture ; (b) aucun OPEN durable supplémentaire après `DRAINED`, chaîne validée ; (c) OPEN persistés entre `close()` et `DRAINED` consignés, non fautifs ; domaine = processus qui consultent la gate | Scénario 6 (a), (b) et (c), en variante thread et processus |
| 3 | H8 simulait l'erreur sans prouver la libération | H8 : erreur injectée **après** le vrai `close` ; libération du descripteur prouvée par l'inode via `/proc/self/fd` ; flock prouvé libre par un processus distinct et `drain_barrier(timeout_s=0)` ; jamais de second `close` ; erreur simulée avant fermeture = H8-neg documentaire, pas une preuve | H8 vert avec les trois preuves ; H8-neg exclu des critères d'acceptation |

**Inchangé** : tout le reste de v0.2, dont D-C1a-1 à 7, l'interface, l'ordre des verrous, les scénarios 1 à 5 et 7 à 20, I1–I13, N1–N7, H1–H7, H9, TT1–TT10 et les interdictions du §12.

**Périmètre d'implémentation proposé par la contre-revue, à n'ouvrir qu'après validation explicite de l'opérateur** : C1a seul (`mexc_simulator.py`, `ppl_admission_gate.py`, `ppl_quiescence_proof.py`, contrats C1 et A v1.3, tests C1a et non-régression), dans un arbre local isolé (Python 3.11, Ruff 0.15.8). Aucun commit, push, PR, fusion, VPS, Advisor, C1b, exchange ni Telegram ; #282 non muté, #286 actif.

---

## 16. Notes d'implémentation (C1a, sans changement de contrat)

- Fichiers : `paper_trading/ppl_admission_gate.py` (`admission_hold`, `drain_barrier`, codes), `paper_trading/mexc_simulator.py` (injection, compteurs, déclaration, `reject_code`), `paper_trading/admission_types.py` (valeur additive `REJECTED_GATE_CLOSED`, exigée par D-C1a-3), `paper_trading/ppl_quiescence_proof.py` (lot A v1.3), tests `tests/paper_trading/test_ppl_quiescence_c1.py`.
- I2 (marqueur à P1) : le flock n'est pas encore tenu, donc `close()` ajoute aussi l'enregistrement CLOSE ; le refus a lieu à t2 (`GATE_CLOSED_JOURNAL`) et non à t3. I3 (P2) refuse à t3 (`GATE_CLOSED_MARKER`). Dans les deux cas : refus, rien de durable, DRAINED.
- I12 : un remplacement du verrou **à P1** précède l'`open` de l'admetteur, qui verrouille alors le nouvel inode : admission acceptée et cohérente. Le remplacement détecté (`GATE_LOCK_IDENTITY_CHANGED`) est celui qui survient **après** l'obtention du flock (point PF).
- Les tests synthétisent un journal de gate OPEN valide (`_open_gate`) : un vrai `open()` exige une clearance de succession, couverte par `test_ppl_succession_01`.
- S1/AC1 : empreintes du ledger PPL, du ledger d'admission et des notifications produites par le même scénario figé sur `main@7cd4c4e9` et intégrées au test ; comparaison directe avec un arbre de base possible via `C1A_BASELINE_ROOT`.

### 16.1 Correctif après contre-revue indépendante (2026-11-12T05:38Z, PASS PARTIEL)

- **D-01** : `admission_types.py` reste limité aux 3 lignes additives de `REJECTED_GATE_CLOSED`. Ratification de l'opérateur au titre de #286 requise.
- **D-02** : le diff initial (`71684148…`) changeait le comportement **sans déclaration** : une vue d'autorité illisible ne levait plus `StoreCorruptionError` dans `observe_runtime`. C'est corrigé : la capture de l'exception n'a lieu qu'avec une déclaration valide nommant `PPL-QUIESCENCE-COUNTERS-V1`. Sans déclaration, le comportement v1.2 de 7cd4c4e9 est conservé (tests TT8b, TT8c).
- **D-03** : la matrice §8.4 est alignée sur les observations (I2 refusé à t2 avec CLOSE ajouté ; I3 sans CLOSE ; I12 à PF ; I12b à P1 admis). Le protocole n'a pas changé. Le test I2/I3 affirme désormais aussi l'enregistrement CLOSE observé.
- **S17** : preuve lecteur par lecteur et bornes explicites au §8.1.

