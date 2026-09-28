# ADR-0019 — Stockage durable et projection gouvernée `OperatorDecision` (D5B-R2, prototype hors runtime)

**Date :** 2026-09-28
**Statut :** Proposé (prototype isolé, soumis à revue indépendante — issue #315)
**Auteur :** Mathieu (via session Claude)

---

## Contexte

Le noyau source D5B-R1 (`observability/operator_decisions/producer.py`,
PR #314, certifié `WEB_DIR_01_D5B_R1_GOVERNED_PRODUCER_SOURCE_CERTIFIED`)
admet des candidats gouvernés et journalise des événements append-only, mais
**uniquement en mémoire** : un redémarrage de processus perd tout l'état, et
rien ne garantit qu'une écriture concurrente ou une coupure au milieu d'une
admission ne corrompe le journal ni ne duplique une décision.

L'issue #315 (D5B-R2) exige une décision documentée de stockage durable
avant tout raccordement futur à l'Operator API ou à D5C, avec des preuves
empiriques (tests de crash, de concurrence, de corruption) plutôt qu'une
promesse d'architecture.

Ce prototype reste strictement hors runtime : aucun endpoint, aucun service,
aucun branchement à l'Advisor, aucune lecture de JSONL/DB/Telegram réels.
Conformément au gel architectural (Scientific Debt Rule), il ne crée qu'une
seule variable nouvelle — le mécanisme de persistance — et n'ajoute aucune
règle de décision, aucun indicateur, aucune stratégie.

## Alternatives comparées

| Critère | (a) SQLite, transaction explicite | (b) Journal append-only fichier (JSONL + fsync) |
|---|---|---|
| **Atomicité** | Native : `BEGIN IMMEDIATE` … `COMMIT`/`ROLLBACK` garantit qu'un événement, son index d'idempotence et l'accusé de commande sont écrits ensemble ou pas du tout (test ACID du moteur SQLite). | Nécessite d'implémenter soi-même l'atomicité multi-écriture (ex: écrire dans un fichier temporaire + `rename` atomique), fragile dès qu'on doit associer plusieurs faits (événement + index d'idempotence + réponse de commande) dans une seule opération. |
| **Reprise après crash** | Le fichier `-wal`/`-journal` de SQLite permet un rollback automatique d'une transaction interrompue à la réouverture ; démontré par nos tests (`test_crash_avant_commit_ne_laisse_aucune_trace`, `test_crash_apres_commit_avant_reponse_est_durable_et_rejouable`). | Une écriture JSONL interrompue au milieu d'une ligne laisse une ligne tronquée illisible ; il faut détecter et tronquer la queue corrompue soi-même à chaque redémarrage, ce qui est justement le risque que l'issue #315 demande d'éliminer, pas de recréer. |
| **Intégrité** | Contraintes `UNIQUE` natives (clé d'idempotence, hash d'événement) + vérification applicative de la chaîne de hash à la lecture. | Chaîne de hash applicative seule ; aucune contrainte d'unicité imposée par le système de fichiers, donc une réécriture partielle peut passer inaperçue plus longtemps. |
| **Concurrence** | Verrouillage natif au niveau fichier (`BEGIN IMMEDIATE` sérialise les écrivains) ; démontré par nos tests d'admissions simultanées identiques/conflictuelles. | Nécessite un verrou applicatif externe (fichier `.lock`, `flock`) réimplémentant ce que SQLite fournit déjà, avec plus de surface de bug. |
| **Sauvegarde** | `sqlite3.Connection.backup()` ou copie du fichier après `PRAGMA wal_checkpoint(TRUNCATE)` : opération standard, testable. | Copie de fichier simple, mais sans garantie de cohérence si une écriture est en cours au moment de la copie (pas de point de cohérence natif). |
| **Migration** | Schéma relationnel versionné (`schema_meta`), colonnes typées, migrations via scripts SQL classiques (ADD COLUMN, nouvelle table) sans réécrire l'historique. | Migration = réécriture de tout le fichier JSONL ligne par ligne vers un nouveau format, ce qui casse la propriété "append-only, jamais réécrit" que l'on cherche justement à garantir. |

## Décision

**Retenu : (a) SQLite avec transaction explicite (`BEGIN IMMEDIATE` /
`COMMIT` / `ROLLBACK`)**, jamais un simple `commit()` implicite en fin de
script. Chaque admission est une transaction unique qui :

1. vérifie la chaîne d'événements existante (fail-closed) ;
2. cherche d'abord un résultat déjà committé pour la commande de l'appelant
   (`command_id`) — garantit qu'une réponse perdue après commit ne produit
   jamais un doublon lors d'un rejeu ;
3. cherche ensuite une admission déjà committée pour la même clé métier
   (`owner_registry`, `source_type`, `source_id`, `owner_record_version`,
   `decision_purpose`) — identique → même `decision_id` ; différente →
   `ContractError("collision ...")` ;
4. insère l'événement, son hash de chaîne et l'accusé de commande dans la
   même transaction.

Le module ne réimplémente pas la logique de validation du candidat : il
appelle `GovernedProducer._validate`/`_payload` du noyau R1 pour ne pas
dupliquer une décision déjà gouvernée (gel architectural).

### Limite explicite — authenticité, pas seulement intégrité

Le hash de chaîne (`event_hash`/`previous_event_hash`) est un contrôle
**d'intégrité interne** : il détecte une réécriture, une troncature ou un
réordonnancement *après coup*, dans le même fichier. Ce n'est **pas** une
preuve d'**authenticité** externe — quiconque a un accès en écriture au
fichier SQLite peut réécrire tout le journal et recalculer une chaîne interne
cohérente. Une racine de confiance externe serait nécessaire pour fermer ce
trou :

- une signature cryptographique (clé privée détenue hors de ce processus,
  p. ex. HSM ou coffre de secrets), vérifiée à la lecture ; ou
- un ancrage périodique du hash de tête dans un registre faisant autorité et
  hors de portée du même compte/processus (ex: commit signé dans un dépôt
  séparé, service d'horodatage tiers).

Aucun de ces mécanismes n'est disponible dans ce dépôt aujourd'hui (pas de
gestion de clés de signature, pas de service d'ancrage). **Ce point reste
donc un gate ouvert, non résolu par ce prototype** — voir la table
« exigence → preuve → limite restante » de la PR associée.

De même, `AvailabilityProof` reste une attestation fournie par l'appelant.
Ce module ne l'authentifie jamais : un appelant malveillant ou bogué peut
fabriquer une preuve à `producer_certified=True` avec le bon compte
d'événements et obtenir `AVAILABLE`. La seule garantie apportée ici est que
**l'absence de preuve, une preuve invalide structurellement, ou un watermark
incohérent avec le journal réel ne produisent jamais `AVAILABLE` ni un
compte zéro implicite** — mais l'authenticité de la preuve elle-même exige la
même racine de confiance externe que ci-dessus.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Journal append-only fichier (JSONL) | Reprise après crash et concurrence beaucoup plus fragiles à implémenter correctement soi-même ; migration = réécriture, contraire à la propriété recherchée. Voir tableau ci-dessus. |
| SQLite avec `isolation_level` implicite (autocommit par instruction) | Ne garantit pas qu'un événement + son index d'idempotence + l'accusé de commande soient durables ensemble ; une coupure entre deux `INSERT` autocommit peut laisser un état incohérent. Rejeté au profit d'une transaction explicite unique. |
| Base de données externe (Postgres, etc.) | Introduirait une dépendance de service supplémentaire (processus, réseau, secrets) hors du périmètre "prototype isolé hors runtime" de #315, et une nouvelle surface expérimentale non justifiée par une hypothèse H1-H6. |

## Conséquences

**Positives :**
- Propriétés ACID démontrées par des tests réels de crash simulé (avant/après
  commit), de concurrence (admissions simultanées identiques/conflictuelles)
  et de corruption (troncature, réordonnancement, version de schéma inconnue).
- Idempotence de commande : une réponse perdue après commit ne peut jamais
  être rejouée en double.
- Projection reconstruite uniquement depuis le journal SQLite, jamais depuis
  un état en mémoire séparé.

**Négatives / compromis :**
- Un seul fichier SQLite est un point de défaillance unique tant qu'aucune
  procédure de sauvegarde n'est exécutée régulièrement (voir
  `docs/runbooks/OPERATOR_DECISION_STORE_MIGRATION_BACKUP.md`).
- L'authenticité (racine de confiance externe pour la chaîne de hash et pour
  `AvailabilityProof`) n'est pas résolue par ce prototype — gate distinct.

**Règles induites :**
- Aucune écriture ne doit contourner `DurableGovernedStore.admit` (pas
  d'accès SQL direct en dehors des tests de corruption, qui simulent
  explicitement une attaque/incident).
- Toute nouvelle version de schéma doit être ajoutée à
  `KNOWN_SCHEMA_VERSIONS` avec un plan de migration documenté (voir
  runbook), jamais par réécriture des événements existants.
