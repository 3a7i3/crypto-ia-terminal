# ADR-0004 — Rejection Observatory : JSONL atomique plutôt que SQLite ou CSV

**Date :** 2026-06-29
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

Chaque signal refusé représente une décision analytiquement exploitable. Aujourd'hui,
`gate_rejections.csv` capture partiellement les refus de la couche Gate uniquement. Il n'existe
pas de store unifié capturant tous les refus (toutes couches) avec le contexte complet (score
décomposé, conviction, sizing, raison humaine). La base `databases/decision_packets.jsonl`
contient l'audit trail mais est lourde (tous les packets, pas uniquement les refus) et non
optimisée pour l'analyse statistique des rejections.

## Décision

Créer `observability/rejection_store.py` avec :
- `RejectionRecord` : dataclass typée avec tous les champs nécessaires à l'analyse de regret et à
  l'Adaptive Calibration Engine futur
- `RejectionStore` : écriture JSONL atomique (write-then-rename pattern sur POSIX, flush explicite
  sur Windows), rotation quotidienne, validation de schéma, zéro perte silencieuse
- Fichiers : `databases/rejections/rejections_YYYY-MM-DD.jsonl`, un fichier par jour, rotation 90j

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| SQLite | Verrou fichier incompatible avec les redémarrages rapides du bot sur Windows ; migration de schéma fragile |
| CSV | Pas de types, pas de structures imbriquées (liste de bloqueurs, dict de features) sans sérialisation custom |
| Étendre `decision_packets.jsonl` | Trop volumineux, tous les packets (pas seulement les refus), format couplé au lifecycle packet |
| PostgreSQL | Dépendance externe, coût opérationnel sur VPS, overkill pour volume actuel |
| Ajouter à `gate_rejections.csv` | Capture seulement la couche Gate, pas les 11 autres couches |

## Conséquences

**Positives :**
- Chaque refus est persisté de manière atomique — zéro perte même en cas de crash process
- Rotation automatique — aucune intervention opérateur nécessaire
- Format JSONL directement exploitable par pandas, jq, scripts d'analyse
- Schéma versionné (`schema_version` field) — migration forward-compatible
- Coût CPU/mémoire minimal : une seule écriture de ~500 bytes par refus

**Négatives / compromis :**
- Pas de requêtes SQL — agrégations nécessitent un script Python ou pandas
- Duplication partielle avec `decision_packets.jsonl` pour les packets REJECTED

**Règles induites :**
- `RejectionStore` ne lève jamais d'exception vers l'appelant (try/except + log critique)
- Le champ `schema_version` doit être incrémenté à chaque rupture de schéma
- Aucun outil de monitoring ne doit écrire dans ce store — lecture seule pour les consommateurs
- La rotation ne supprime pas les fichiers — elle ferme proprement et crée un nouveau fichier
