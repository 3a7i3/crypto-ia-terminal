# ADR-0020 — Contrat de confiance `OperatorDecision` (D5B-R2, prototype hors runtime)

**Date :** 2026-09-28
**Statut :** Proposé — **BLOQUÉ pour certification** (aucune autorité de confiance réelle désignée)
**Portée :** `observability/operator_decisions/` uniquement (prototype isolé, issue #315, PR #316)
**Complète :** ADR-0019 (stockage durable), qui laissait l'authenticité en gate ouvert.
**Origine :** commentaire du propriétaire PR #316 (comment_id 5864337478), étape 1 ;
révisé après l'analyse d'écart de la mission « fermer les critères
d'authenticité et d'autorité » (§12).

> Note de numérotation : le fichier `0020-deterministic-durable-idempotent-order-submission.md`
> existe déjà (même situation que les deux ADR-0019). Le nom de ce fichier a
> été imposé par la mission ; la désambiguïsation se fait par le slug.

---

## 1. Pourquoi ce contrat précède le code

ADR-0019 prouve l'**intégrité interne** du journal (chaîne de hash, transactions
SQLite), pas son **authenticité** ni l'**autorité** de ceux qui l'alimentent.
Toute implémentation cryptographique sans contrat préalable reviendrait à
choisir implicitement qui a le droit de signer. Ce document fixe d'abord les
règles ; le code (`trust.py`, `durable_store.py`) ne fait que les appliquer.

## 2. Modèle de menace

| # | Adversaire / défaillance | Capacité supposée | Contre-mesure du prototype | Résiduel |
|---|---|---|---|---|
| M1 | Demandeur (appelant de `admit`/`project`) malveillant ou bogué | Construit librement tout objet Python passé en argument | Aucun champ de la requête n'établit d'autorité ; seules les signatures vérifiées contre la politique du **constructeur** comptent | — |
| M2 | Demandeur qui substitue le candidat après approbation | Modifie titre, priorité, source, révision… | L'approbation signe l'empreinte canonique du candidat exact + champs liés ; tout écart → refus sans écriture | — |
| M3 | Demandeur qui rejoue une approbation ou une attestation ancienne | Possède des objets signés authentiques mais périmés | Fenêtre de validité (`issued_at`/`expires_at`), horloge injectée, checkpoint monotone persisté par le vérificateur | Voir §8 (retour arrière du fichier entier) |
| M4 | Clé compromise | Signe n'importe quoi au nom d'une identité | Révocation par identifiant de clé dans la politique ; rotation par nouvelle version de politique | La fenêtre entre compromission et révocation n'est pas couverte |
| M5 | Accès disque en écriture au fichier SQLite | Réécrit, tronque, réordonne, recalcule toute la chaîne | Chaîne de hash (intégrité) + attestation signée du hash de tête + ancre anti-retour | Sans attestation fraîche, une réécriture cohérente complète reste indétectable (§9) |
| M6 | Confusion de rôles | Utilise une clé d'un rôle pour signer au nom d'un autre (approbateur se faisant passer pour le propriétaire, autorité de disponibilité pour l'accès aux preuves, etc.) | Quatre rôles disjoints (§4) ; une clé = un rôle ; une identité = un seul rôle ; chaque énoncé est vérifié pour SON rôle | — |
| M8 | Approbateur ou propriétaire qui sort de son périmètre | Signe pour un autre registre, un autre type de source ou une autre finalité | Permissions par triplet exact (registre, type de source, finalité), sans joker (§4) | Les triplets réels restent à désigner (§3) |
| M9 | Fuite de références de preuves sensibles par la projection | Lit la projection (ou une réponse d'API future) | Classification signée par le propriétaire, masquage fail-closed, lecture séparée sous droit signé (§4.2) | Aucune détection automatique de secret dans les champs texte libres (§10) |
| M7 | Horloge locale fausse | Avance/recul de l'horloge | Horloge injectée, tolérance de dérive bornée, validité maximale bornée | Un vérificateur dont l'horloge est contrôlée par l'attaquant n'est pas protégé |

Hors modèle : compromission du processus vérificateur lui-même, de la
politique de confiance passée au constructeur, ou du code source.

## 3. Propriétaire de la politique de confiance — BLOCAGE DE CERTIFICATION

**Constat :** aucune autorité opérationnelle réelle n'existe aujourd'hui pour
ce domaine. Les registres propriétaires listés par le contrat D5B
(`docs/contracts/WEB_DIR_01_D5B_OPERATOR_DECISION_PRODUCER_ARCHITECTURE.md`,
§2 : futur Problem Registry, futur Bounty Registry, etc.) sont **tous
futurs** ; aucun n'est déployé, certifié, ni n'a donné son accord. Ce
prototype n'en invente aucun.

**Conséquence :** la politique de confiance utilisée dans les tests est une
**FIXTURE non opérationnelle** (`TrustPolicy(operational=False)`). Aucune
sortie de ce prototype ne peut être présentée comme certifiée tant que la
décision humaine suivante n'a pas été prise et consignée dans un ADR signé
par l'opérateur :

1. **Désigner le propriétaire de la politique de confiance** (personne ou rôle
   humain responsable de la liste des clés, des révocations et des versions de
   politique).
2. **Désigner les identités signataires** pour chaque rôle
   (`ADMISSION_APPROVER` par registre propriétaire, `AVAILABILITY_AUTHORITY`
   pour le journal), et leur périmètre (registres autorisés).
3. **Choisir le canal de distribution des clés publiques** (ex. fichier de
   politique versionné et signé dans un dépôt distinct, revu par le
   propriétaire) et le lieu de garde des clés privées (hors de ce dépôt, hors
   du processus vérificateur).
4. **Désigner, pour chaque source de la matrice D5B §2, l'identité du
   propriétaire habilité à signer un transfert** (`SOURCE_OWNER`) et les
   triplets (registre, type de source, finalité) qu'elle couvre. Aucun de ces
   registres n'existe : cette désignation dépend de leur création et de leur
   accord.
5. **Désigner qui classe les références de preuves (public/sensible) et qui
   peut accorder l'accès aux références sensibles** (`EVIDENCE_ACCESS_AUTHORITY`),
   ainsi que le mécanisme d'authentification réelle du lecteur (couche
   d'identité opérateur de D5A, hors de ce prototype).
6. **Choisir l'emplacement de l'ancre anti-retour** (§8), hors de portée d'un
   attaquant disposant du disque du journal.

Tant que ces six décisions n'existent pas : statut **BLOQUÉ pour
certification**, quelle que soit la couleur de la CI.

## 4. Identités, rôles et permissions

La politique (`TrustPolicy`) déclare, pour une `policy_version` donnée, une
liste de clés publiques Ed25519
`TrustedKey(key_id, role, identity, public_key, grants)` :

| Rôle | Signe | Permissions (`grants`) |
|---|---|---|
| `SOURCE_OWNER` | `OWNER_TRANSFER` : le transfert explicite du fait source vers l'admission (D5B §2), avec la classification de chaque référence de preuve | triplets exacts (registre, type de source, finalité) |
| `ADMISSION_APPROVER` | `ADMISSION_APPROVAL` : le contrôle d'admission, lié au candidat ET à l'empreinte du transfert présenté ; porte le statut et la priorité approuvés | triplets exacts (registre, type de source, finalité) |
| `AVAILABILITY_AUTHORITY` | `AVAILABILITY_ATTESTATION` du journal (§8, §9) | aucune (l'attestation lie le journal) |
| `EVIDENCE_ACCESS_AUTHORITY` | `EVIDENCE_ACCESS_GRANT` : droit de lire les références sensibles d'UNE décision d'UN journal | aucune (le droit lie décision et journal) |

Règles vérifiées à la construction : une clé n'a qu'un rôle ; **une même
identité ne peut détenir deux rôles** (le propriétaire ne peut donc pas être
son propre approbateur) ; **un matériau de clé publique ne peut figurer
qu'une seule fois dans la politique** — ni cumul de rôles par le même
matériau sous des `key_id` et des identités différents, ni alias : sans ce
contrôle, une seule clé privée porterait deux rôles, et une clé révoquée sous
un `key_id` resterait valable via un alias du même matériau (révocation
contournée) ; les permissions sont des triplets exacts non vides,
sans joker `*` ; `SOURCE_OWNER` et `ADMISSION_APPROVER` doivent en déclarer au
moins un ; les deux autres rôles n'en portent pas. `identity` doit égaler
`owner_id` / `approver_id` / `authority_id` de l'énoncé signé.

**Limite :** l'unicité du matériau ne prouve pas que deux clés distinctes sont
détenues par deux personnes distinctes ; cette séparation des détenteurs reste
une décision opérationnelle (§3.2). Le contrôle porte sur les octets de clé
publique : une clé dérivée de la même clé privée par une opération de
signature manuelle sur la courbe (point opposé) serait un autre matériau
détenu par le même opérateur, hors de portée d'un contrôle de configuration.

### 4.1 Admission : deux énoncés, un candidat

`admit(candidate, owner_transfer=..., approval=..., command_id=...)` exige :

1. le seuil de candidature D5B (`GovernedProducer._validate`, inchangé) ;
2. un `OWNER_TRANSFER` authentique, dont la clé est autorisée pour le triplet
   du candidat, lié au candidat exact (empreinte canonique, registre, type,
   `source_id`, révision, `source_sha`, finalité) et classant **chaque**
   référence de preuve ;
3. une `ADMISSION_APPROVAL` authentique, autorisée pour le même triplet, liée
   au même candidat et à l'empreinte du transfert (`owner_transfer_digest`) ;
   statut et priorité sont lus ici, jamais dans des arguments libres ;
   promotion au-delà de la priorité demandée refusée.

Tout échec a lieu **avant** toute écriture (ni événement, ni résultat de
commande). L'admission gouvernée n'est pas une décision humaine D5D.

**Rejeu et fraîcheur.** Authenticité (signature, clé non révoquée, rôle,
permissions, liens, empreinte identique) et fraîcheur (fenêtre de validité)
sont séparées. La fraîcheur n'est exigée que pour écrire un **nouvel**
événement. Un rejeu d'une commande déjà commitée, avec les mêmes énoncés,
reste possible après expiration — sinon l'idempotence persistante ne vaudrait
que dans la fenêtre de validité et une réponse perdue deviendrait
irrécupérable. Un rejeu avec un énoncé falsifié, une clé désormais révoquée ou
une autre approbation signée est refusé.

### 4.2 Références de preuves sensibles (D5B §5)

- Le propriétaire signe une classification `PUBLIC` / `SENSITIVE` pour chaque
  référence (clé = empreinte de la référence) ; classification incomplète,
  avec référence inconnue ou valeur invalide → refus sans écriture.
- `project()` n'expose que les références explicitement `PUBLIC` ; toute autre
  (classe absente ou inconnue comprise) est remplacée par
  `{"redacted": true, "ref_digest": ...}` (échec fermé).
- `read_sensitive_evidence(decision_id, grant=...)` exige un droit signé par un
  `EVIDENCE_ACCESS_AUTHORITY`, lié au journal et à la décision demandée,
  frais ; le journal est vérifié avant toute lecture.
- **Limites :** le droit est une capacité au porteur — `accessor_id` est
  consigné mais l'authentification réelle du lecteur n'existe pas ici
  (§3.5) ; la classification est déclarative (aucune détection de secret dans
  les champs texte libres, §10) ; le journal SQLite contient les références
  brutes, donc le fichier journal et ses sauvegardes sont eux-mêmes sensibles.

**Registre actuel : FIXTURE.** Les seules clés existantes sont générées à la
volée dans les tests (`Ed25519PrivateKey.generate()`), marquées
`NON_OPERATIONNELLE`, jamais persistées, jamais réutilisables hors test. Une
politique `operational=True` est refusée à la construction.

## 5. Distribution des clés publiques

- La politique est un **paramètre du constructeur** de `DurableGovernedStore`
  (configuration du vérificateur). Elle n'est jamais lue depuis la requête,
  ni depuis la base SQLite, ni depuis une variable d'environnement implicite.
- Aucune clé publique « jointe » à une approbation ou une attestation n'est
  prise en compte : seule la référence `key_id` est lue, puis résolue dans la
  politique du constructeur.
- Le canal opérationnel de distribution reste à décider (§3.3).

## 6. Séparation signataire / demandeur

Principe : **une clé publique, un booléen ou une référence fournis dans la
requête n'établissent jamais leur propre autorité.**

- L'ancien `AvailabilityProof(producer_certified=True, ...)` est retiré du
  chemin d'autorité : `project()` n'accepte plus qu'une attestation signée.
- `admit()` ne reçoit plus `approved_status`/`approved_priority`/
  `admission_approval_ref` libres : ces valeurs sont **lues depuis
  l'approbation vérifiée**.
- `trust_root_ref` et `deployment_evidence_ref` restent des pointeurs
  d'audit, jamais une preuve. L'ancien `transfer_ref` (chaîne libre signée par
  l'approbateur) est remplacé par un transfert signé par le propriétaire.

## 7. Révocation et rotation

- **Révocation :** `TrustPolicy(revoked_key_ids=...)`. Une signature par une
  clé révoquée est refusée, même si elle a été produite avant la révocation
  (pas de date de révocation fiable sans autorité réelle — choix fail-closed).
  Conséquence documentée : les événements déjà admis restent dans le journal
  (append-only) ; seules les nouvelles vérifications échouent — y compris le
  rejeu d'une commande dont un énoncé a été signé par une clé révoquée depuis
  (§4.1). Une révocation datée exigerait une source de temps de confiance
  (§9) ; elle reste un gate ouvert.
- **Rotation :** nouvelle clé (nouveau matériau) dans la politique, l'ancienne
  révoquée ; une clé révoquée ne peut pas réapparaître sous un autre `key_id`
  (matériau unique, §4). Nouvelle `policy_version` contenant la nouvelle clé. Chaque
  énoncé signé porte la `policy_version` sous laquelle il a été émis ; une
  version inconnue du vérificateur est refusée. Le vérificateur n'accepte
  qu'**une** version courante (pas de période de coexistence dans ce
  prototype — limite volontaire, plus stricte).

## 8. Anti-retour (rollback)

- Chaque attestation porte un **numéro de checkpoint monotone** signé, lié au
  `journal_id`, au nombre d'événements et au hash de tête.
- Le vérificateur **persiste lui-même** le dernier checkpoint accepté
  (table `accepted_checkpoint`) ; cette valeur n'est **jamais** fournie par
  l'appelant.
- Règles : checkpoint inférieur au dernier accepté → rejet ; checkpoint égal
  mais compte/hash différents → rejet ; checkpoint supérieur avec moins
  d'événements que le dernier accepté → rejet ; journal réel dont le préfixe
  ne reproduit pas le hash de tête accepté (troncature, réécriture) → rejet.
- **L'ancre est exigée dans un fichier distinct du journal** (`anchor_path`) :
  le constructeur refuse une ancre colocalisée sauf
  `allow_colocated_anchor=True`. Colocalisée, une restauration du fichier
  entier à un état ancien ferait reculer l'ancre avec lui ; le rejeu d'une
  ancienne attestation encore dans sa fenêtre de validité serait alors accepté
  (comportement démontré par
  `test_ancre_colocalisee_explicite_laisse_passer_une_restauration_complete`).
- **Limite honnête :** un fichier d'ancre distinct ne démontre pas un domaine
  de protection indépendant : sur le même hôte et avec les mêmes droits
  d'écriture, il protège contre la restauration du seul journal, pas contre un
  attaquant qui restaure aussi l'ancre. Une ancre hors de portée de cet attaquant (autre hôte, registre
  externe) reste une décision opérationnelle ouverte (§3.6).

## 9. Politique d'horloge

- Horloge **injectée** au constructeur (`clock: Callable[[], datetime]`),
  jamais `datetime.now()` implicite dans la vérification.
- Validité : `issued_at_utc - dérive ≤ maintenant < expires_at_utc`.
- Tolérance de dérive : `max_clock_skew_seconds` (défaut 60 s).
- Durée de validité maximale d'une attestation/approbation :
  `max_validity_seconds` (défaut 3600 s) ; au-delà, refus même si signé.
- Limites : aucune source de temps de confiance (NTP authentifié, horodatage
  tiers) n'est branchée ; l'horloge du vérificateur est supposée honnête.

## 10. Ce qui reste indétectable sans autorité réelle

- Une réécriture complète du journal avec recalcul de la chaîne est
  **détectée** si une attestation fraîche signée du hash de tête réel est
  exigée (le hash ne correspond plus) ou si l'ancre persistée ne correspond
  plus. Elle reste **indétectable** pour `verify()` seul (intégrité interne)
  et pour tout lecteur qui n'exige pas d'attestation.
- Une clé de test compromise est, par construction, compromise : elle vit
  dans le code de test. D'où le statut FIXTURE.

## 11. Frontières

Aucun raccordement Operator API/D5C, aucune action humaine D5D (la décision
humaine future reste distincte de l'admission gouvernée), aucun service,
déploiement, restart, lecture de données runtime, aucune mutation
PAPER/PPL/FIN/Research/Watchdog/TESTNET/LIVE/epoch/config/risk/sizing. Aucun
verdict R2.

## 12. Écarts corrigés depuis 203d02b (analyse de la mission d'authenticité)

Constatés en lisant le code livré contre le contrat D5B et la mission :

| Écart | Source de l'exigence | Correction | Test (exemples) |
|---|---|---|---|
| Le « transfert » n'était qu'une chaîne signée par l'approbateur : aucune signature du propriétaire | D5B §2 : « transfert explicite approuvé par son propriétaire » | Rôle `SOURCE_OWNER`, énoncé `OWNER_TRANSFER`, approbation liée à son empreinte (§4.1) | `test_transfert_*`, `test_approbation_liee_a_un_autre_transfert_refusee` |
| Permissions limitées au registre | mission : « identités autorisées par registre, rôle et finalité » | Triplets exacts (registre, type, finalité), sans joker (§4) | `test_*_non_autorise_pour_le_triplet_exact_refuse`, `test_permissions_invalides_refusees_a_la_construction` |
| Rejeu impossible après expiration des énoncés | mission : idempotence persistante, réponse perdue | Authenticité séparée de la fraîcheur (§4.1) | `test_rejeu_apres_expiration_*`, `test_nouvelle_admission_avec_enonces_expires_refusee_sans_ecriture` |
| Références de preuves exposées telles quelles ; `test_preuve_sensible_non_autorisee_*` ne testait que le mauvais rôle | D5B §5 : contrôle d'accès distinct des références sensibles | Classification signée, masquage fail-closed, lecture sous droit signé (§4.2) | `test_projection_masque_*`, `test_lecture_sensible_*` |
| Ancre anti-retour colocalisée par défaut | mission : rejeu d'un ancien état signé | Ancre exigée hors du fichier journal (§8) | `test_ancre_colocalisee_*` |

Ajoutés après la revue complémentaire du HEAD `a74ce54` :

| Écart | Source | Correction | Test (exemples) |
|---|---|---|---|
| Une même clé publique acceptée sous deux rôles, deux `key_id` et deux identités ; conséquence : une clé révoquée restait valable via un alias | ADR-0020 §4 « une clé n'a qu'un rôle » ; revue du propriétaire | Matériau de clé public unique dans la politique (§4) | `test_meme_cle_privee_sous_deux_roles_et_deux_identites_refusee`, `test_aucun_cumul_de_roles_par_materiau_cryptographique`, `test_alias_de_cle_du_meme_role_refuse_*`, `test_rotation_par_nouvelle_cle_reste_valide` |
| Le refus des anciennes versions de schéma reposait sur une erreur SQLite opaque (colonne absente) pour un journal 1.0.0, et n'était testé qu'avec `9.9.9` | revue du propriétaire : conserver explicitement le refus | Refus explicite à l'ouverture (`_refuse_legacy_layout`), sans altérer le fichier | `test_journal_v1_sans_journal_id_refuse_explicitement_et_reste_intact`, `test_base_d_une_version_anterieure_refusee_a_l_ouverture`, `test_evenements_d_une_version_anterieure_refuses_sans_ajout` |

Conservés inchangés : seuil de candidature D5B, séparation demandée/approuvée,
distinction `NON DÉPLOYÉ` / `UNKNOWN` / zéro authentifié, anti-retour par
checkpoint, index lié au journal, instantané transactionnel unique.
