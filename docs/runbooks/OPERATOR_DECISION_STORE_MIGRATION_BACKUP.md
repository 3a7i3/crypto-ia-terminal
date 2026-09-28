# Runbook — Migration de schéma et sauvegarde/restauration du stockage durable `OperatorDecision` (prototype D5B-R2)

Référence : ADR-0019, issue #315. Ce document couvre uniquement le
prototype isolé `observability/operator_decisions/durable_store.py`. Il ne
décrit aucune procédure de déploiement VPS ni de service runtime — aucun des
deux n'existe pour ce composant.

---

## 1. Contrat de migration de schéma

Le journal est **append-only : les événements déjà écrits ne sont jamais
modifiés ni réécrits**, y compris pendant une migration.

### 1.1 Ajout rétrocompatible (colonne optionnelle, nouveau champ de payload)

1. Ajouter la nouvelle version à `KNOWN_SCHEMA_VERSIONS` dans
   `durable_store.py` (ex: `{"1.0.0", "1.1.0"}`).
2. Les nouveaux événements sont écrits avec `schema_version="1.1.0"`.
3. `_verify_locked` et `project()` doivent savoir lire **les deux** versions
   pendant toute la période de transition (jamais une bascule brutale qui
   rendrait les anciens événements illisibles).
4. Les anciens événements gardent leur `schema_version` d'origine pour
   toujours — c'est une preuve d'audit, pas un défaut à corriger.

### 1.2 Changement non rétrocompatible (renommage, suppression de champ)

Un changement non rétrocompatible **n'est jamais appliqué en place**. Procédure :

1. Geler les écritures sur la base source (arrêter tout appelant du
   prototype — ce composant n'a aujourd'hui aucun appelant runtime, donc
   cette étape est un point de contrôle pour une mission future, pas une
   action à exécuter aujourd'hui).
2. Exécuter `verify()` sur la base source ; toute erreur d'intégrité arrête
   la migration (fail-closed).
3. Lire tous les événements via `events()` (jamais un accès SQL direct) et
   les rejouer, dans l'ordre de séquence, dans un **nouveau fichier** de
   base créé avec le nouveau schéma. Cela **régénère une nouvelle chaîne de
   hash** dans le nouveau fichier — la chaîne de hash de l'ancien fichier
   reste l'unique preuve d'intégrité pré-migration et doit être archivée
   telle quelle (voir §2), jamais supprimée.
4. Comparer `decision_count` et `counts_by_status` de la projection avant et
   après migration ; toute divergence bloque la bascule.
5. Ne basculer les appelants vers le nouveau fichier qu'après validation
   humaine explicite — cette étape reste un gate distinct, hors périmètre du
   prototype R2.

### 1.3 Ce qui n'est PAS une migration valide

- `UPDATE events SET ...` sur la base en production : interdit, casse la
  garantie append-only et la chaîne de hash.
- Suppression d'anciens événements pour "faire de la place" : interdit, la
  projection ne serait plus reconstructible depuis le seul journal.

---

## 2. Sauvegarde

### 2.1 Procédure recommandée (cohérente, sans arrêter les écritures)

```python
import sqlite3

source = sqlite3.connect("operator_decisions.db")
source.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # aligne le fichier principal
backup = sqlite3.connect("operator_decisions.backup.db")
with backup:
    source.backup(backup)  # API native SQLite, cohérente même si source est utilisée
backup.close()
source.close()
```

`Connection.backup()` est l'API standard de la bibliothèque `sqlite3` pour
une copie cohérente d'une base active — elle ne nécessite pas de figer les
écritures côté appelant.

### 2.2 Fréquence et rétention (à valider par l'opérateur)

Ce prototype ne définit pas de politique de rétention automatique — aucune
tâche planifiée, aucun cron, aucun script de déploiement n'est ajouté ici
(hors périmètre R2). La fréquence de sauvegarde et sa durée de rétention
restent une décision opérationnelle explicite pour une mission ultérieure.

---

## 3. Restauration

1. Arrêter tout accès en écriture sur le fichier cible (hors périmètre
   runtime aujourd'hui, mais impératif pour une future intégration).
2. Copier le fichier de sauvegarde vers l'emplacement de destination. Le
   `journal_id` (table `schema_meta`) est conservé : c'est le même journal.
3. Instancier `DurableGovernedStore(path, owners, trust_policy=..., clock=...)`
   sur le fichier restauré et appeler `verify()` : journal (chaîne de hash,
   cohérence colonnes/charge) ET index `command_results` (chaque ligne liée à
   séquence + `event_hash`) sont vérifiés. Toute `CorruptedJournalError`
   signale une sauvegarde invalide — ne jamais mettre en service une base
   restaurée sans ce contrôle.
4. Si seul l'index est altéré (journal sain), `rebuild_command_index()` le
   reconstruit depuis le journal vérifié (transaction unique ; refus et
   rollback si le journal lui-même est corrompu). Les commandes secondaires
   convergentes ne sont pas dans le journal : leur rejeu reconverge par la clé
   d'idempotence vers la même `decision_id`.
5. Rejouer un `command_id` connu : il doit renvoyer la même `decision_id`
   sans nouvel événement (idempotence).
6. `project(attestation)` n'est `AVAILABLE` qu'avec une attestation signée
   par l'`AVAILABILITY_AUTHORITY` couvrant l'état restauré. **Anti-retour :**
   si le vérificateur a déjà accepté un checkpoint plus récent (ancre
   `accepted_checkpoint`), une restauration à un état antérieur est refusée
   (`UNKNOWN`, « retour arrière détecté ») — c'est voulu. Une restauration
   légitime à un état antérieur exige une décision humaine explicite et une
   nouvelle attestation de l'autorité ; aucune procédure automatique ne
   contourne l'ancre.

Procédure exercée par le test exécutable
`tests/test_web_dir_d5b_r2_durable_store.py::test_sauvegarde_restauration_puis_rejeu_idempotent`
(`Connection.backup()`, `verify()`, rejeu idempotent, projection attestée) ;
reconstruction : `test_reconstruction_de_l_index_depuis_le_journal` ;
restauration frauduleuse : `test_restauration_complete_du_fichier_detectee_avec_ancre_externe`.

---

## 4. Retenues SQLite (état au commentaire propriétaire 5864337478)

- **Conservée, ciblée :** `PRAGMA journal_mode=WAL` dans `_connect()`,
  uniquement sur `OperationalError` contenant « database is locked », 5
  tentatives × 50 ms (reproduction locale déterministe : création concurrente
  de plusieurs stores sur un fichier neuf). Toute autre erreur remonte
  immédiatement ; la connexion est fermée sur tout échec (tests
  `test_connexion_fermee_*`, `test_retenue_wal_*`).
- **Retirée :** la retenue générique de `_read_events_verified` sur
  `DatabaseError`, dont le diagnostic CI a été réfuté (cause réelle :
  monkeypatch au niveau classe dans le test). Une erreur SQLite en lecture
  produit désormais `UNKNOWN` sans nouvelle tentative
  (`test_lecture_verifiee_sans_retenue_generique_echoue_ferme`).

---

## 5. Limite non résolue

Ni la migration ni la sauvegarde décrites ici ne prouvent l'authenticité
d'origine : la politique de confiance est une FIXTURE non opérationnelle et
aucune autorité réelle n'est désignée (ADR-0020 §3, blocage de
certification). Une restauration réussie prouve la cohérence interne du
fichier restauré ; seule une attestation fraîche d'une autorité réelle, et une
ancre anti-retour hors de portée d'un attaquant disposant du disque,
fermeraient ce gate.
