# ADR-0020 — Contrat de confiance `OperatorDecision` (D5B-R2, prototype hors runtime)

**Date :** 2026-09-28
**Statut :** Proposé — **BLOQUÉ pour certification** (aucune autorité de confiance réelle désignée)
**Portée :** `observability/operator_decisions/` uniquement (prototype isolé, issue #315, PR #316)
**Complète :** ADR-0019 (stockage durable), qui laissait l'authenticité en gate ouvert.
**Origine :** commentaire du propriétaire PR #316 (comment_id 5864337478), étape 1.

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
| M6 | Confusion de rôles | Utilise une clé d'approbation pour attester la disponibilité (ou l'inverse) | Rôles disjoints dans la politique (`ADMISSION_APPROVER` ≠ `AVAILABILITY_AUTHORITY`) ; une clé = un rôle | — |
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

Tant que ces trois décisions n'existent pas : statut **BLOQUÉ pour
certification**, quelle que soit la couleur de la CI.

## 4. Identités et rôles autorisés

La politique (`TrustPolicy`) déclare, pour une `policy_version` donnée, une
liste de clés publiques Ed25519 `TrustedKey(key_id, role, identity, public_key, scopes)` :

- `ADMISSION_APPROVER` : signe une approbation d'admission. `identity` doit
  égaler `approver_id` dans l'approbation ; `scopes` restreint les
  `owner_registry` pour lesquels la clé peut approuver.
- `AVAILABILITY_AUTHORITY` : signe une attestation de disponibilité du
  journal. `identity` doit égaler `authority_id` de l'attestation.

Une clé n'a qu'un seul rôle. Une même identité ne peut pas être déclarée dans
les deux rôles (séparation des pouvoirs, vérifiée à la construction).

**Registre actuel : FIXTURE.** Les seules clés existantes sont générées à la
volée dans les tests (`Ed25519PrivateKey.generate()`), marquées
`NON_OPERATIONNELLE`, jamais persistées, jamais réutilisables hors test.

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
- `trust_root_ref`, `deployment_evidence_ref`, `transfer_ref` restent des
  pointeurs d'audit, jamais une preuve.

## 7. Révocation et rotation

- **Révocation :** `TrustPolicy(revoked_key_ids=...)`. Une signature par une
  clé révoquée est refusée, même si elle a été produite avant la révocation
  (pas de date de révocation fiable sans autorité réelle — choix fail-closed).
  Conséquence documentée : les événements déjà admis restent dans le journal
  (append-only) ; seules les nouvelles vérifications échouent.
- **Rotation :** nouvelle `policy_version` contenant la nouvelle clé. Chaque
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
- L'ancre peut être placée dans un fichier distinct (`anchor_path`) hors du
  fichier journal. **Limite honnête :** si l'ancre est dans le même fichier
  (défaut) et que l'attaquant restaure le fichier entier à un état ancien,
  l'ancre recule avec lui ; seule la fenêtre de validité de l'attestation
  borne alors le rejeu. Une ancre hors de portée de l'attaquant (autre hôte,
  registre externe) reste une décision opérationnelle ouverte.

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
