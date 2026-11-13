# PPL-QUIESCENCE-01 — Lot C1b — Contrat v0 rev1

Statut : contrat source local v0, rédigé avant le code (étape P1 du plan A3),
complété par les ajustements d'implémentation du §12, puis **amendé par la
révision bornée rev1 (§13)**, texte écrit avant le code de rev1. Le §13 amende
explicitement le plan A3 §4.6 (mécanisme de signal), qui était erroné.
Plan A3 sha256
`2eb013ca…0cb6fc`, approuvé par l'opérateur le 2026-11-12T16:26Z, GO C1b-LOCAL).
Base : `main@87155f3aacb11d266ae45ffb95810f698c0db3cf`. Aucun commit, push, PR,
fusion, VPS, systemd, démarrage réel de l'Advisor, epoch ni exchange.
Dérogation #286 limitée aux modifications locales de `core/advisor_loop.py`
décrites au §7. D-EPOCH-PATH (III-R8.0) reste **ouvert** : ce lot ne choisit
aucun rôle de manifest et ne touche aucun mécanisme d'activation successeur.

Références : lot A v1.3 (`PPL_QUIESCENCE_01_PERSISTED_PROOF.md`), lot B v2
(`PPL_QUIESCENCE_01_EXTERNAL_WITNESS.md`), C1a v0.3 (`PPL_QUIESCENCE_01_LOT_C1.md`,
texte d'autorité sha256 `eeb912f8…41be2`). Aucun de ces modules n'est modifié.

## 1. Objet

Rendre l'Advisor capable, **sur configuration explicite**, de :

1. passer au simulateur la gate d'admission de son epoch et une identité de code
   déclarée, seulement si l'autorité et les identités concordent ;
2. tenir pendant toute sa vie un verrou d'identité stable, inspectable par le
   témoin B ;
3. convertir SIGTERM et SIGINT en arrêt ordonné qui écrit une observation O puis
   une sentinelle (lot A).

C1b ne prouve rien par lui-même. Il produit les entrées que le lot A (`assess`)
et le lot B (témoin externe) savent juger. Il ne ferme pas la gate, ne draine
pas, n'ouvre rien, ne crée pas d'epoch.

## 2. Configuration (mode opt-in, tout ou rien)

| Variable | Contenu |
|---|---|
| `PPL_ADMISSION_GATE_JOURNAL` | chemin absolu du journal de gate de l'epoch |
| `PPL_QUIESCENCE_PROOF_DIR` | répertoire de preuve dédié (lot A) |
| `PPL_ADVISOR_IDENTITY_LOCK` | fichier de verrou d'identité |

- **Aucune** variable non vide : chemin legacy. Le module C1b n'est pas importé,
  aucun gestionnaire de signal n'est installé, `MexcSimulator` reçoit
  `admission_gate=None` et `gate_wiring_code_sha=None`. Comportement identique à
  `87155f3a`.
- Une ou deux variables : `C1bConfigRefusal`, démarrage refusé.
- Les trois : validation (§3), puis acquisition du verrou d'identité et
  installation des gestionnaires **au début de `main()`**, juste après le verrou
  legacy et le contrôle des dépendances, donc avant tout service et avant le
  bootstrap d'autorité PPL ; puis câblage (§4) **après** ce bootstrap.

Le module ne lit aucune autre variable d'environnement que ces trois-là et,
pour les contrôles de recouvrement, `PPL_AUTHORITY_STORE_ROOT` et
`PAPER_TRADE_LOG`. Il ne lit jamais `PB_MAX_POSITIONS`, les frais, le capital ni
une variable de stratégie.

## 3. Validation des chemins (sans aucune création)

Refus (`C1bConfigRefusal`) si :

- un chemin n'est pas absolu, ou contient `..` ;
- un composant existant du chemin (ancêtre ou feuille) est un lien symbolique ;
- le journal de gate existe et n'est pas un fichier régulier ; le répertoire de
  preuve existe et n'est pas un répertoire ; le verrou d'identité existe et n'est
  pas un fichier régulier ;
- le répertoire parent du verrou d'identité n'existe pas (le module ne crée
  aucun répertoire) ;
- deux zones se recouvrent (égalité ou inclusion) parmi : répertoire de la gate
  (parent du journal), répertoire de preuve, verrou d'identité, racine du store
  d'autorité, `PAPER_TRADE_LOG`, verrou legacy `ADVISOR_LOCK_FILE`.

La validation ne crée, n'ouvre en écriture ni ne modifie aucun fichier.

## 4. Câblage de la gate et identité de code

Préconditions, sinon refus (`C1bConfigRefusal` ou `C1bIdentityRefusal`) :

- autorité `PPL_AUTHORITY` et runtime d'autorité lié ;
- identité de code : `capture_source_evidence()` (HEAD git du checkout, capturé
  une fois dans le helper C1b) avec `source_sha` présent, au format hexadécimal
  minuscule de 40 ou 64 caractères, `worktree_state == "CLEAN"` et
  `source_sha == runtime.manifest.code_sha`.

La valeur n'est **jamais** lue dans le manifest : le manifest ne sert qu'à la
comparaison. Provenance : `GIT_HEAD_AT_BOOT`, statut `CLAIMED_ONLY`. Ce n'est
**pas** une attestation : les octets réellement importés peuvent différer
(fichier modifié après l'import, `.pyc`, `PYTHONPATH`). Aucun champ produit par
C1b ne porte `VERIFIED` ni `ATTESTED`.

Gate : `AdmissionGate(journal, paper_epoch_id=runtime.manifest.paper_epoch_id,
manifest_sha256=authority_manifest_sha256(runtime.manifest))`. Les identités
viennent du runtime lié, jamais de l'environnement. Le simulateur reçoit
`admission_gate=gate` et `gate_wiring_code_sha=<source_sha>` ; son refus de
câblage (`GateWiringRefusal`, C1a) reste fatal sous PPL_AUTHORITY.

État de la gate au démarrage : lu par `state()` et journalisé, **jamais
bloquant**. Une gate CLOSED, invalide ou jamais ouverte n'empêche pas le
démarrage, pour que les CLOSE (TP, SL, TIMEOUT) des positions ouvertes restent
possibles ; les OPEN sont refusés par C1a (fail-closed).

Neutralité de rôle : C1b ne lit pas `epoch_role`, n'émet ni ne valide aucune
clearance, n'appelle jamais `AdmissionGate.open`, `close` ni `drain_barrier`.
Pour un rôle non successeur, la gate reste `GATE_NEVER_OPENED` tant que
D-EPOCH-PATH n'a pas défini d'ouverture ; ce fait est journalisé, pas corrigé.

## 5. Verrou d'identité

- Fichier dédié, distinct de `ADVISOR_LOCK_FILE` (dont la sémantique, les
  lecteurs et le marqueur BOOT sont inchangés).
- Acquisition, avant le bootstrap d'autorité :
  `open(path, O_RDONLY | O_CREAT | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0o600)`
  (`O_NONBLOCK` : une FIFO déposée au chemin ne bloque pas le démarrage) ; contrôle
  `S_ISREG` ; `(st_dev, st_ino)` du descripteur égal à celui du chemin ; refus si
  le fichier est inscriptible par le groupe ou les autres ; puis
  `flock(LOCK_EX | LOCK_NB)`. Échec du verrou : `C1bIdentityRefusal` (une autre
  instance tient l'identité), démarrage refusé, aucune écriture PPL.
- Le fichier n'est **jamais** écrit, tronqué, renommé ni supprimé par C1b. Le
  descripteur est conservé pour la vie du processus ; le noyau libère le flock à
  la mort du processus, quelle qu'en soit la cause.
- Avant l'observation d'arrêt, l'identité est recontrôlée : `(dev, ino, ctime,
  mtime)` du descripteur égal à celui du chemin, chemin régulier. Écart :
  aucune O, aucune sentinelle, résultat `IDENTITY_LOCK_CHANGED`.
- Limite : si le fichier est supprimé puis recréé pendant la vie du processus,
  une seconde instance pourrait prendre le nouveau fichier ; le verrou legacy
  reste la garde d'unicité, et le témoin rendra `UNKNOWN` (sens sûr).

## 6. Arrêt ordonné et preuve

- Gestionnaires installés dans le thread principal, en mode C1b seulement, pour
  SIGTERM et SIGINT. **rev1 (§13.1)** : le gestionnaire ne fait qu'**une
  affectation d'attribut** (premier signal reçu) ; aucun appel, donc aucun verrou
  direct ou indirect, aucune entrée-sortie, aucune exception. Le texte v0
  (« lever un `threading.Event` ») est **retiré** : `Event.set()` prend un verrou
  interne et pouvait s'interbloquer. Thread non principal : refus **avant**
  l'ouverture du verrou d'identité (§13.2).
- Boucle : la demande est testée en tête de cycle et dans l'attente de reprise du
  kill switch ; l'attente entre cycles devient `wait_stop(interval)`, attente
  bornée par tranches de `POLL_S = 0,1 s` hors gestionnaire (§13.1) (en mode
  C1b, le paramètre de test `_sleep` de `main()` n'est donc pas utilisé). Un
  cycle commencé se termine ; la logique de cycle n'est pas modifiée. Un arrêt
  demandé pendant l'attente du kill switch ne déclenche pas le message « Kill
  Switch levé » : le kill switch n'a pas été levé.
- Séquence, à la sortie de boucle sur signal ou sur `max_cycles` :
  1. `_stop_runtime_services()` (existant) ; pour SIGINT seulement, le message
     Telegram existant « arrêté manuellement » ; pour SIGTERM, aucun message ;
  2. `simulator.stop()` (existant, sans join) ;
  3. contrôle d'identité du verrou (§5) ;
  4. O : `observe_runtime(...)` avec `current_process_identity(lock_fd=<verrou
     d'identité>)` et `source_sha=<HEAD capturé>`, appelé sans aucun verrou tenu ;
  5. `ProofStore(proof_dir, forbidden_roots=[store_root, gate_dir])`,
     `write_observation`, puis `write_seal` ; le verrou d'écriture de preuve n'est
     jamais pris sous `sim._lock`.
- Résultat typé `ShutdownOutcome.status` :

| Statut | Sens | Code de sortie |
|---|---|---|
| `SEALED` | O et sentinelle confirmées, reçu durable | 0 |
| `SEALED_RECEIPT_NOT_DURABLE` | sentinelle visible et confirmée, dernier fsync du répertoire en échec | 3 |
| `NO_SIMULATOR` | aucun simulateur ou runtime : rien à observer | 3 |
| `IDENTITY_LOCK_CHANGED` | le verrou d'identité n'est plus celui tenu | 3 |
| `OBSERVATION_FAILED` | `observe_runtime` a levé | 3 |
| `PROOF_STORE_REFUSED` | répertoire de preuve refusé ou indisponible | 3 |
| `OBSERVATION_NOT_PERSISTED` / `OBSERVATION_UNCERTAIN` | `PersistBlocked` / `PersistUncertain` sur O | 3 |
| `SEAL_NOT_PERSISTED` / `SEAL_UNCERTAIN` / `SEAL_REFUSED` | idem sur la sentinelle, ou `QuiescenceRefusal` | 3 |

- Trois notions distinctes, jamais confondues :
  - **sortie normale** : le processus s'est terminé par son propre chemin de
    sortie (code 0 ou 3). Elle ne dit rien de la preuve ;
  - **échec de persistance** : tout statut autre que `SEALED` ; aucune
    sentinelle valide n'existe, le témoin conclura `INTERRUPTED`,
    `UNCERTAIN_PROOF`, `UNRESOLVED_CHAIN` ou `UNKNOWN` ;
  - **arrêt propre attesté** : seulement un verdict du lot A obtenu après le
    témoin B externe : `SEALED_THEN_STOPPED` au mieux. `CLEAN_STOP_CONFIRMED`
    exige un statut de sortie fourni par un superviseur, absent ici. Le code 0
    du processus n'est **jamais** une attestation.
- Le chemin « 5 erreurs consécutives » (crash) n'écrit ni O ni sentinelle :
  inchangé, le témoin conclura `INTERRUPTED`.

## 7. Modifications de `core/advisor_loop.py` (dérogation #286)

1. Avant `_bootstrap_paper_lifecycle_authority` : si une variable C1b est non
   vide, import paresseux du module, validation de la configuration, acquisition
   du verrou d'identité, installation des gestionnaires.
2. Après lui : câblage (§4). Le corps de `_bootstrap_paper_lifecycle_authority`
   n'est pas modifié.
3. Construction du simulateur : deux arguments en plus (`None` sans C1b).
4. Boucle : test de l'événement en tête de cycle et dans l'attente du kill
   switch ; attente interruptible entre cycles en mode C1b.
5. Après la boucle : séquence §6 en mode C1b ; code de sortie 3 si la preuve
   n'est pas `SEALED`.

## 8. Écritures tardives du moniteur

Le thread `MEXC-SIM` peut fermer une position après O. Aucune fausse preuve
n'en résulte : `write_seal` recopie le digest du ledger de O ; `assess` exige
O = sentinelle = témoin = ledger courant. Une écriture entre O et la sentinelle,
ou entre la sentinelle et le témoin, donne `INTERRUPTED` ; après le témoin,
`STALE`. De plus, la quiescence exige zéro position ouverte, auquel cas le
moniteur n'a rien à fermer.

## 9. Ordre des verrous

```
démarrage : advisor.lock (legacy) → verrou d'identité (tenu à vie, jamais attendu ensuite)
OPEN      : sim._lock → flock gate → runtime._lock → flock store   (C1a, inchangé)
CLOSE     : sim._lock → runtime._lock → flock store               (inchangé)
O         : sim._lock → runtime._lock, relâchés, puis .writer.lock du ProofStore
signal    : aucun verrou (rev1 : une affectation d'attribut, aucun appel)
```

## 10. Tests (matrice du plan A3, §6)

B1–B13 et L1–L7, en variante thread et processus réel (driver synthétique sans
réseau ni Advisor), le témoin B étant lancé en sous-processus isolé comme
oracle. Non-régression : `tests/paper_trading/` complet, tests Advisor existants,
corpus non-root, gate Ruff.

Fichiers de test : `tests/paper_trading/test_ppl_quiescence_c1b.py` (module,
variantes thread, L6), `tests/paper_trading/test_ppl_quiescence_c1b_process.py`
(processus réels via `tests/paper_trading/c1b_driver.py`, témoin B en
sous-processus), `tests/test_advisor_loop_c1b_wiring.py` (intégration Advisor).

## 11. Limites (rappel)

- La déclaration de code reste `CLAIMED_ONLY` (R-E4).
- `CLEAN_STOP_CONFIRMED` inatteignable ; témoin B `NOT_QUALIFIED` (R-E2).
- Un écrivain sans gate n'est pas couvert par le drainage ; seule la preuve
  d'arrêt de chaque écrivain compte (R-E5).
- `EpochRotationQuiescence` reste constructible à la main (R-E3), hors périmètre.
- Un SIGTERM pendant un cycle plus long que `TimeoutStopSec` mène au SIGKILL de
  systemd, donc à `INTERRUPTED` (R-E1, condition VPS-P5).
- Valeur opérationnelle conditionnée à D-EPOCH-PATH (R-C1).
- Les gestionnaires étant installés au début de `main()`, un SIGTERM reçu
  pendant le bootstrap (avant la boucle) n'est pris en compte qu'en tête du
  premier cycle ; si le bootstrap dépasse `TimeoutStopSec`, systemd tue le
  processus (`INTERRUPTED` ou `UNKNOWN`, sens sûr).
- `bind_wiring` appelle `capture_source_evidence()` une seconde fois (la première
  est celle du coordinateur opérateur) : deux lectures `CLAIMED_ONLY` du même
  checkout, dépendantes du répertoire courant du processus.

## 12. Ajustements d'implémentation (après le texte pré-code)

Texte pré-code : sha256 `959a55aa9c0d5e603ca65f045db876973b02817526025a435f198496a9ac7d6e`.

1. Placement de la préparation C1b au début de `main()` (au lieu de « juste avant
   le bootstrap ») : des services (session primer, univers) démarrent entre les
   deux ; un refus doit les précéder. Ordre des verrous inchangé (§9).
2. `O_NONBLOCK` à l'ouverture du verrou d'identité (FIFO au chemin : refus au
   lieu d'un blocage), découvert par le test du fichier non régulier.
3. `C1bWiring.stop_by_sigint` : choix du message existant, sans importer
   `signal` dans `advisor_loop.py`.
4. Une gate jamais ouverte est lue `CLOSED` par `state()` ; elle est journalisée
   en CRITICAL avec la mention D-EPOCH-PATH, sans blocage (§4).
5. D-C1b-8 : code de sortie 0 seulement pour `SEALED`, 3 sinon (§6).
6. Les trois étapes C1b de `main()` sont des fonctions définies **après** `main()`
   (`_c1b_check_deps_and_prepare`, qui appelle d'abord `_check_critical_deps()` ;
   `_c1b_bootstrap`, qui appelle `_bootstrap_paper_lifecycle_authority` inchangé
   puis `bind_wiring` ; `_c1b_shutdown_or_exit`). Chaque appel remplace une ligne
   existante de `main()` à nombre de lignes égal : aucune ligne de `main()` n'est
   décalée avant la construction du simulateur, ce qui préserve les numéros de
   ligne cités par la documentation et par un test documentaire existant
   (`test_pre_t1_c_portfolio_provider_read_only.py`), qui échouait sinon.

## 13. Révision bornée rev1 (2026-11-13) — amendements écrits avant le code

Origine : contre-revue indépendante du 2026-11-12 (constats R1–R4) et mandat de
révision bornée de l'opérateur. Note hors dépôt : `C1B_PLAN_AMENDMENT_R1_SIGNAL.md`.
Le plan A3 et le candidat original restent conservés avec leurs empreintes.

### 13.1 Mécanisme de signal (amende plan A3 §4.6 et §6 ci-dessus)

- Erreur de conception reconnue : le plan affirmait que `stop_event.set()` ne
  prend aucun verrou. En CPython 3.11, `Event.set()` et `Event.wait()` prennent le
  verrou de leur `Condition` ; un gestionnaire qui interrompt le thread principal
  pendant qu'il le tient (dans `wait()` ou `set()`, y compris lors d'une salve de
  signaux) s'interbloque.
- Gestionnaire rev1 : `if self._signum is None: self._signum = signum`. Aucun
  appel de fonction (vérifié par AST), aucun verrou, aucune entrée-sortie, aucune
  exception. Le premier signal reçu fait foi (choix du message SIGINT existant).
- Lecture : `requested` lit l'attribut. Attente : `wait(timeout)` boucle hors
  gestionnaire sur `time.sleep(min(POLL_S, restant))` tant que rien n'est
  demandé ; `time.sleep` ne prend aucun verrou Python et reprend après le
  gestionnaire (PEP 475).
- Borne : prise en compte en ≤ `POLL_S` (0,1 s) dans l'attente entre cycles,
  ≤ 0,5 s dans l'attente du kill switch (boucle existante) ; annoncée et testée
  à 1,0 s pour la marge d'ordonnancement.
- Limites : pendant un cycle ou le bootstrap, la demande n'est vue qu'en tête du
  cycle suivant (aucun changement de décision ni de transition) ; au-delà de
  `TimeoutStopSec`, SIGKILL et verdict `INTERRUPTED`/`UNKNOWN` (sens sûr).
- Écartés : `RLock` substitué dans `Event` (détails privés), `set_wakeup_fd`
  (global au processus, concurrence asyncio), `sigwait` dans un thread dédié
  (disposition globale des signaux).
- Régression : sonde déterministe qui envoie un SIGTERM à chaque ligne exécutée
  sous `StopSignals.wait` et dans le gestionnaire (salve réentrante, borne de
  200 signaux) ; l'original s'interbloque (watchdog), la révision revient.

### 13.2 Garanties de refus (remplace toute formulation « tout refus sans création »)

1. **Avant toute création** : configuration absente/partielle/invalide (§2, §3)
   et appel hors du thread principal, désormais contrôlé avant l'ouverture du
   verrou. C1b ne crée aucun fichier ni répertoire.
2. **Après acquisition/création du verrou d'identité** : verrou tenu par une
   autre instance, contrôles de type/mode après ouverture, installation des
   gestionnaires en échec. Le fichier de verrou peut avoir été créé ; il n'est
   jamais supprimé ni tronqué.
3. **Après le bootstrap/bind d'autorité** (`bind_wiring`) : autorité non PPL,
   runtime absent, recouvrement avec le store lié, HEAD inconnu, DIRTY ou
   différent du manifest. Effets antérieurs admis, non niés : verrou d'identité
   (classe 2), dans l'Advisor `logs/`, `databases/shadow_execution/`,
   enregistrements d'observabilité, session primer et service d'univers s'ils
   sont activés, scanners, `MarketDatabase` si activée ; le bootstrap d'autorité
   lui-même (PPL : création/rejeu de l'epoch par `bind` ; legacy :
   `_gate_paper_dataset`). C1b n'écrit ni gate, ni preuve, ni position, ni
   admission avant ces refus.

Aucune refonte du bootstrap n'est faite ; la garantie « zéro création pour tout
refus » n'est pas revendiquée.

### 13.3 Preuves (R3, R4)

- B3 est rejoué sur le chemin câblé, en processus réel : OPEN bloqué au commit
  par une barrière synthétique, fermeture et drainage depuis un autre processus
  de test (`DRAIN_TIMEOUT` puis `DRAINED`), aucune admission durable après la
  barrière, CLOSE préservé. Les appels `close`/`drain_barrier` restent dans
  l'orchestration de test, jamais dans C1b ni l'Advisor.
- B5b, B11e, L5 : couverture par tests existants nommés et limites déclarées dans
  le rapport rev1.

Ajout après le code (constaté pendant la révision, sans changer de mécanisme) :
- B5b est aussi rejoué en processus câblé C1b (échec de `fsync` injecté une ou
  deux fois sur le `.jsonl` d'epoch, miroir de C1a `tt3`/`tt4`) : FILLED et zéro
  transition en vol, ou `APPLIED_DURABLE_NOT_MEMORY`, témoin code 10, adaptateur
  refusant.
- B11e : une `AuthorityManifestError` levée par le bootstrap d'autorité (inchangé)
  traverse `_c1b_bootstrap` sans être capturée ni réemballée ; `bind_wiring`
  n'est pas appelé.
- L5 : en plus du contrôle structurel, la vraie `main()` de l'Advisor est
  exécutée (stubs du smoke test, PAPER désactivé, gestionnaires réels) : SIGTERM
  n'ajoute aucune notification, SIGINT ajoute le seul message existant, et un
  signal reçu pendant un cycle laisse ce cycle se terminer. Limite : le chemin
  d'arrêt avec un vrai simulateur PPL n'est pas exécuté dans l'Advisor (il l'est
  dans le driver synthétique).

### 13.4 Révision rev2 (2026-11-13) — R5 : installation transactionnelle des gestionnaires

Écrit avant le code. Réserve de la contre-revue rev1 : `StopSignals.install()`
installait SIGTERM puis SIGINT ; un échec du second laissait le premier en place.

- `install()` est transactionnel : si une installation échoue, chaque
  gestionnaire déjà posé par cet appel est remis à sa disposition précédente,
  dans l'ordre inverse, puis l'exception **originale** est relancée telle quelle
  (même objet, même traceback). Un échec de restauration n'écrase jamais
  l'exception originale : il lui est attaché en note (`add_note`).
- Aucun gestionnaire partiel ne subsiste ; `_previous` n'est renseigné qu'après
  un succès complet.
- Le refus reste de classe 2 (§13.2) : le verrou d'identité est relâché, son
  fichier peut subsister, aucune preuve n'est écrite.
- Le gestionnaire lui-même (§13.1) est inchangé.
