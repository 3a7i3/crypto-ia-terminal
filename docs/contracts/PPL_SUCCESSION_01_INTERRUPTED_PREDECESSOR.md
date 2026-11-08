# PPL-SUCCESSION-01 — Succession après expérience interrompue (contrat v1)

Statut : **contrat source + tests isolés.** Aucune installation, aucune epoch réelle, aucun lancement
Advisor, aucune modification de `PB_MAX_POSITIONS`. Exception limitée à #286 pour ce développement et
ces tests uniquement (décision opérateur 2026-11-08) ; elle ne lève pas le garde-fou.

## 1. Objet
Représenter honnêtement un prédécesseur **clôturé documentairement comme expérience interrompue**
(ex. `BURN-IN-EPOCH-01-20260926T064144Z`, commentaire #282 6712166490) sans affaiblir la rotation normale.

## 2. Ce qui ne change pas
- `EpochRotationQuiescence`, `CutoverQuiescence` et les trois builders existants (`build_cutover_manifest`,
  `build_experiment_manifest`, `build_burn_in_experiment_manifest`) restent **inchangés** et refusent toujours une
  quiescence non prouvée.
- Manifestes v1/v2/v3 : mêmes champs, mêmes octets sérialisés, mêmes identités d'événements ; chargement inchangé.
- `PB_MAX_POSITIONS` n'est ni lu ni écrit par ce lot.

## 3. Voie distincte (version `PPL-SUCCESSION-INTERRUPTED-V1`)
Nouveau rôle de manifest `BURN_IN_SUCCESSOR_AFTER_INTERRUPTION`, `manifest_schema_version = 4`, domaine
d'événements `BURN-IN-SUCCESSOR-AUTHORITY-V1`, préfixe `burnsucc`. Champs : champs communs +
`predecessor_authority_epoch_id` + `interruption_succession_sha256`. Les autres rôles refusent ce dernier champ non vide.

### 3.1 Dossier d'interruption (entrée du builder)
Le builder `verify_interruption_evidence(...)` exige **des octets**, jamais un booléen ni une URL :
1. `ledger_bytes` du prédécesseur ; il est rechargé via le décodeur du `DurableEventStore` (intégrité complète),
   projeté (`project`) ; valeurs dérivées : nombre d'événements, dernière séquence, ouvertures/clôtures/unresolved,
   positions ouvertes (**doit être 0**), capital unresolved, `certified_equity`.
2. `dataset_files` : copie octet pour octet de l'arbre d'un export produit par `research_data.paper_exporter` (`manifest.json`, `authoritative/…`, `optional/…`), rejouée dans un répertoire temporaire nommé du `dataset_id` et validée par le validateur **natif** `research_data.burn_in_finalization._validate_dataset` (version/schéma du dataset, provenance PAPER/PPL_AUTHORITY, identités recalculées, empreinte de frontière complète et champs exacts, digests des composants, copies manifest/config d'autorité de rôle BURN_IN_EXPERIMENT v3, ensemble des composants d'identité). Le `dataset_id` égale la décision, l'epoch égale le prédécesseur, `authoritative/ppl_events.jsonl` égale `ledger_bytes`. Chemins non sûrs, fichiers manquants ou non-octets : refus. Un document cohérent avec ses seuls hashes est refusé. Limite : dépendance de ce module de vérification vers le code Research (import paresseux, lecture seule).
3. `operator_decision_bytes` : JSON `PPL-SUCCESSION-OPERATOR-DECISION-V1`, champs exacts (aucun champ inconnu) :
   `schema`, `decision_kind="INTERRUPTED_EXPERIMENT_DOCUMENTARY_CLOSURE"`, `predecessor_paper_epoch_id`,
   `predecessor_ledger_sha256`, `predecessor_dataset_id`, `predecessor_event_count`,
   `acknowledged_unknowns` = `{pending_order_count:"UNKNOWN", lifecycle_transitions_in_flight:"UNKNOWN"}`,
   `fin_status="UNRESOLVED"`, `certified_equity=null`, `unresolved_capital` (nombre), `evidence_sha256`
   (mapping rôle → sha256), `decided_by`, `decided_at_utc`.
4. `evidence_artifacts` : octets de chaque pièce citée (`closure_dossier`, `approved_archive`, `closure_comment_body`) ;
   chaque sha256 recalculé doit égaler la valeur de la décision.
Toute divergence entre la décision et les valeurs **dérivées** du ledger est un refus.

### 3.2 Inconnus et capital
- Les deux compteurs doivent valoir exactement la chaîne `"UNKNOWN"`. Tout entier (y compris `0`), `None`, booléen,
  ou autre chaîne est refusé : un compteur mesuré relève de la gate normale (quiescence), pas de cette voie.
- `fin_status` doit être `"UNRESOLVED"`, `certified_equity` `null`, `unresolved_capital` > 0 conservé dans l'enregistrement.
- Le capital du successeur est **déclaré** par l'opérateur (`capital_provenance.kind="OPERATOR_DECLARED_NOMINAL"`,
  avec le sha de la décision de capital) ; les provenances `PREDECESSOR_CASH`, `PREDECESSOR_EQUITY`,
  `WALLET_PAPER_CAPITAL`, `API_BALANCE` sont refusées. `predecessor_unresolved_capital_transfer = "NONE"` est figé.

### 3.3 Enregistrement de succession
`InterruptedSuccessionRecord` (immuable) : version de contrat, identités prédécesseur (epoch, dataset, ledger sha,
comptes), valeurs dérivées, inconnus, successeur (epoch id ≠ prédécesseur), provenance du capital, hashes des pièces ;
`record_sha256` = SHA-256 du JSON canonique. Le manifest successeur porte ce hash.

## 4. Preuve d'exclusivité (séparée, requise avant activation)
Une clôture documentaire **ne constitue pas** cette preuve. `AuthorityExclusivityProof` (JSON, octets + artefacts) porte
des observations nommées, chacune `PASS` avec un `evidence_sha256` vérifié contre un artefact fourni, datées et fraîches
(`max_age_s`) : `no_process_on_predecessor_store`, `no_open_descriptor_on_predecessor_store`, `no_store_lock_held`,
`former_host_stopped_control_plane`, `successor_store_empty_or_absent`, `no_environment_references_predecessor`.
Vérifications locales supplémentaires : racines successeur/prédécesseur résolues, distinctes et non imbriquées, non
symboliques ; ledger prédécesseur re-haché = hash enregistré ; store successeur sans aucun événement.
Résultat : `ActivationClearance` (immuable), d'objet `BOOTSTRAP` ou `RESUME`, scellée (HMAC à clé locale au processus, jamais sérialisée : non reconstructible
à partir de champs, non copiable entre processus), liée à l'epoch, aux octets du manifest, au record, à la racine du store
successeur et à une durée de validité explicite (`max_age_s`, 900 s par défaut). Elle est **validée au point d'usage**
(`validate_clearance_for_use`) : sceau, epoch, manifest, record, store. Politique :
- *premier bootstrap* (`issue_activation_clearance`, aucun événement de l'epoch dans le store) : preuve `purpose=BOOTSTRAP`, six observations, store successeur sans ledger ; usage : clearance fraîche (`0 ≤ now − issued_at ≤ max_age_s`) ;
- *reprise* après redémarrage de processus (`issue_resume_clearance`, la clé de scellé est propre au processus et n'est jamais persistée) : nouvelle preuve `purpose=RESUME` datée et fraîche, cinq observations (l'observation « store successeur vide » est remplacée par une vérification locale en lecture seule que le store porte exactement l'événement de naissance de ce manifest : identifiant, séquence 1, horodatage, capital, code, config), mêmes liaisons (manifest, record, racines, ledger prédécesseur inchangé). Aucune écriture ; aucune seconde naissance ; une clearance `BOOTSTRAP` n'autorise jamais une reprise et inversement ;
Sans clearance valide,
`PPLAuthorityRuntime.bind()` **refuse** le rôle successeur (fail-closed), et `build_authority_runtime_from_env` n'en
fournit pas : le lancement Advisor sur un manifest successeur reste impossible tant qu'un lot d'activation ne câble pas la clearance.

## 5. Gate d'admission dédiée
`paper_trading/ppl_admission_gate.py` : journal append-only chaîné (hash du record précédent), **fermé par défaut**
(absence, corruption, rupture de chaîne, mauvaise epoch/manifest ⇒ fermé). Ouverture unique (une seule fois par
epoch+manifest) par `AdmissionOpenDecision` (octets JSON vérifiés : epoch, manifest sha, clearance sha, `decided_by`),
fermeture possible à tout moment (la fermeture n'est jamais refusée). L'ouverture valide la clearance à l'usage (sceau, epoch, manifest, fraîcheur) avec un `now` fini obligatoire (NaN, ±inf, booléen, type invalide : refus avant toute écriture).
Concurrence et fermeture : toute mutation du journal est sérialisée par `flock` sur `<journal>.lock` avec relecture de la chaîne
sous verrou ; `close()` crée d'abord le marqueur `<journal>.closed` (`O_EXCL`, atomique, sans verrou) : tant qu'il existe la gate
lit FERMÉ quel que soit le journal, donc une fermeture l'emporte sur toute ouverture concurrente ou ultérieure. Le marqueur est
permanent pour cette epoch+manifest (pas de réouverture ; une fermeture avant ouverture est définitive). Défaut de persistance :
une ouverture non écrite durablement ou non relue OUVERTE lève et laisse FERMÉ (fermeture durable tentée) ; une fermeture ne renvoie `True`
que sur preuve de persistance : un marqueur préexistant n'est jamais cru sur sa seule présence (fichier régulier, corps complet lié à
l'epoch/manifest, réécrit s'il est incomplet, puis fsync fichier et répertoire) ; un CLOSE valide sans marqueur ne vaut durable que si le
journal et son répertoire se synchronisent à nouveau. Sinon `False` : l'instance est fermée, mais le **futur consommateur doit alors
suspendre/arrêter explicitement** le processus (le lot non câblé ne protège pas encore un Advisor).
**Indépendante de `PB_MAX_POSITIONS`** et de toute
variable d'environnement. Le câblage dans `advisor_loop` est hors de ce lot.

## 6. Critères de tests (tous hors réseau, données synthétiques, stores temporaires)
| # | Critère | Attendu |
|---|---|---|
| T1 | Builders existants avec quiescence incomplète | refus inchangé |
| T2 | Manifests v1/v2/v3 : octets écrits identiques à une référence figée ; round-trip ; identités d'événements identiques | inchangé |
| T3 | Rôle v4 : round-trip écriture/chargement ; champs exacts ; rôle autre + champ succession ⇒ refus | OK/refus |
| T4 | Dossier valide synthétique (ledger avec 2 UNRESOLVED) | record déterministe (2 constructions identiques) |
| T5 | Preuve absente (artefact, décision, manifest dataset, ledger) | refus |
| T6 | Preuve altérée (1 octet du ledger, de la décision, d'un artefact) | refus |
| T7 | Preuve incohérente (comptes, epoch, dataset, sha, capital unresolved ≠ dérivé) | refus |
| T8 | URL seule / booléen seul à la place d'octets ou de hash ; champ inconnu | refus |
| T9 | Compteur `0`, `None`, `False`, `"0"` à la place de `"UNKNOWN"` | refus |
| T10 | Position ouverte dans le ledger prédécesseur | refus |
| T11 | `fin_status` ≠ UNRESOLVED ; `certified_equity` non nul ; unresolved_capital = 0 | refus |
| T12 | Provenance de capital prédécesseur/wallet/API | refus ; transfert = `NONE` |
| T13 | Successeur = prédécesseur (epoch id) ; store successeur = store prédécesseur / imbriqué / symlink / non vide | refus |
| T14 | Clearance sans preuve d'exclusivité (décision seule) | impossible |
| T15 | Preuve d'exclusivité périmée, observation FAIL, hash d'artefact faux, ledger prédécesseur modifié depuis | refus |
| T16 | `bind()` successeur sans clearance / avec clearance d'un autre manifest | refus, store vide |
| T17 | Gate : fermée par défaut ; corruption/rupture de chaîne ⇒ fermée ; double ouverture refusée ; ouverture avec clearance autre ⇒ refus | OK |
| T18 | Gate indépendante de `PB_MAX_POSITIONS` (0, 2, 99) | même état |
| T19 | Un manifest successeur ne peut pas porter l'epoch id du prédécesseur ; le store successeur ne peut pas être celui du prédécesseur | refus. **Ne protège pas** contre la reprise de l'ancienne epoch v3 par son propre manifest v3 : scénario non couvert par ce lot |
| T20 | Clearance : non reconstructible, champs modifiés, autre store/record/manifest, périmée ou future au bootstrap, reprise sans fraîcheur mais avec identité, store successeur non vide | refus / OK |
| T21 | Gate : fermeture avant ouverture définitive, marqueur plus fort que le journal, ouvertures concurrentes multi-processus (une seule), course ouverture/fermeture (fermé), timeout de verrou, échec de persistance à l'ouverture / à la fermeture | fermé |
| T22 | Export natif réel (produit par l'exporteur) accepté ; schéma/version absents ou inconnus, identité partielle, provenance contradictoire, frontière cohérente mais non native, copies d'autorité altérées, chemins non sûrs : refus même après recalcul de tous les hashes | OK / refus |
| T23 | Reprise : deux processus successifs (naissance puis reprise), une seule naissance, octets du store inchangés ; mauvaise racine / record / manifest / naissance / ledger prédécesseur / observations périmées : refus | OK / refus |
| T24 | Gate : `now` NaN/±inf/bool/type invalide ; durabilité du marqueur (échecs répétés fichier/répertoire sur deux instances, rétablissement, écritures courtes, marqueur symlink) | refus / `False` puis `True` |

Décision opérateur (recommandée par la revue) : la fermeture est **terminale et irréversible** par epoch+manifest, y compris avant la première ouverture ; aucune réouverture par effacement du marqueur.

## 7. Hors de ce lot
Observation persistée des compteurs, outil de capture de configuration, installateur, câblage `advisor_loop`/gate,
lancement Advisor, activation, création d'epoch réelle, SHA final et capital initial (décisions opérateur).
