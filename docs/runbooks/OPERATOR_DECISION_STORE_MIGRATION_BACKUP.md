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
   `durable_store.py` (ex: `{"3.0.0", "3.1.0"}`).
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

### 1.3 État courant : schéma 3.0.0

`SCHEMA_VERSION = "3.0.0"`. Le corps d'événement embarque désormais le
transfert propriétaire signé, sa classification des références de preuves et
l'approbation signée. Un journal d'une version antérieure est refusé
(`CorruptedJournalError`, échec fermé) dès l'ouverture, **sans altérer le
fichier** : `_refuse_legacy_layout` refuse une base dont la version est
inconnue ou dont `schema_meta` n'a pas de `journal_id` (cas d'un journal
1.0.0), et `verify()` refuse des événements d'une version non reconnue.
Aucun ajout n'est possible sur un journal ancien (tests
`test_journal_v1_sans_journal_id_refuse_explicitement_et_reste_intact`,
`test_base_d_une_version_anterieure_refusee_a_l_ouverture`,
`test_evenements_d_une_version_anterieure_refuses_sans_ajout`). Aucun journal
hors tests n'existe à ce jour, donc aucune migration de données n'est à
exécuter. Si un journal
antérieur existait un jour, ses événements ne pourraient PAS être rejoués en
3.0.0 sans un transfert signé du propriétaire pour chacun : on ne fabrique
jamais une signature rétroactive.

### 1.4 Ce qui n'est PAS une migration valide

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

### 2.2 Ancre anti-retour et sensibilité des sauvegardes

- **L'ancre anti-retour est un fichier distinct** (`anchor_path`). Elle est la
  mémoire du vérificateur : **ne jamais la restaurer à un état plus ancien en
  même temps que le journal**, sinon la protection contre le retour arrière
  disparaît. Sauvegarder l'ancre séparément, dans un emplacement que
  l'attaquant qui peut restaurer le journal ne contrôle pas (décision
  ADR-0020 §3.6, non prise).
- **Le journal contient les références de preuves brutes**, y compris les
  références classées sensibles (la projection les masque, pas le fichier).
  Une sauvegarde est donc aussi sensible que le journal : permissions
  restreintes, jamais partagée, jamais copiée hors du périmètre autorisé.

### 2.3 Fréquence et rétention (à valider par l'opérateur)

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
3. Instancier `DurableGovernedStore(path, owners, trust_policy=..., clock=...,
   anchor_path=...)` sur le fichier restauré, avec l'ancre COURANTE (jamais une
   ancre restaurée) et appeler `verify()` : journal (chaîne de hash,
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
   `accepted_checkpoint`, fichier distinct), une restauration à un état
   antérieur est refusée
   (`UNKNOWN`, « retour arrière détecté ») — c'est voulu. Une restauration
   légitime à un état antérieur exige une décision humaine explicite et une
   nouvelle attestation de l'autorité ; aucune procédure automatique ne
   contourne l'ancre.

Procédure exercée par le test exécutable
`tests/test_web_dir_d5b_r2_durable_store.py::test_sauvegarde_restauration_puis_rejeu_idempotent`
(`Connection.backup()`, `verify()`, rejeu idempotent, projection attestée) ;
reconstruction : `test_reconstruction_de_l_index_depuis_le_journal` ;
restauration frauduleuse : `test_restauration_complete_du_fichier_detectee_avec_ancre_externe` ;
limite d'une ancre colocalisée :
`test_ancre_colocalisee_explicite_laisse_passer_une_restauration_complete`.

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

## 5. Limites non résolues

Ni la migration ni la sauvegarde décrites ici ne prouvent l'authenticité
d'origine : la politique de confiance est une FIXTURE non opérationnelle et
aucune autorité réelle n'est désignée (ADR-0020 §3, blocage de
certification). Une restauration réussie prouve la cohérence interne du
fichier restauré ; seule une attestation fraîche d'une autorité réelle, et une
ancre anti-retour hors de portée d'un attaquant disposant du disque,
fermeraient ce gate. L'emplacement de l'ancre, la désignation des
propriétaires de sources et de l'autorité d'accès aux références sensibles
restent des décisions humaines (ADR-0020 §3.4 à §3.6).
