# MC-001 — Canonical Regret Dataset

**Statut : ACTIF** (2026-07-21) · Embodiment : `tools/regret_repository.py` · Adopté par ADR-0018

## Objet

Un *Measurement Contract* définit la source **canonique** d'une donnée de
certification, indépendamment de tout chemin de fichier concret. Il existe
parce que le 2026-07-10 la chaîne de certification du regret s'est **rompue
silencieusement** : le producteur a changé (nouveau schéma, nouveau stockage),
le consommateur (CRI) a continué de lire l'ancien fichier mort et de renvoyer 0
pendant 11 jours, sans alarme. Ce n'était pas une erreur de mesure — une
**rupture de traçabilité**.

## Contrat

| Champ | Valeur |
|---|---|
| **Producteur officiel** | `observability/regret_scheduler.py` (RegretScheduler, event-bus, multi-horizon) |
| **Stockage** | `databases/regret/regret_horizons_YYYY-MM-DD.jsonl` |
| **Version dataset** | `regret-v2` |
| **Horizon canonique** | `1h` (pré-enregistré ; matche la durée de détention courte du moteur) |
| **Accesseur unique** | `tools.regret_repository.read_canonical_regrets(since)` |
| **Consommateurs** | CRI, dossier Go/No-Go, audits, dashboards — **jamais** de chemin en dur |

## Invariants

1. **Producteur unique / définition unique.** Aucun consommateur ne choisit son
   fichier ; tous passent par l'accesseur.
2. **Fraîcheur (le plus important).** `is_fresh()` : dernier écrit ≤
   `REGRET_MAX_STALE_H` (défaut 6 h). Un consommateur de certification **doit
   signaler bruyamment** (`validity=PARTIAL`) si la source est périmée. C'est ce
   qui transforme une panne muette en alarme.
3. **Version déclarée.** Toute sortie de certification embarque `dataset_version`
   + `canonical_horizon` → reproductibilité (un CRI de 2026 reste recalculable).
4. **Pas de splicing inter-instruments.** `regret-v2` ≠ l'ancien `regret-v1`
   (`RegretEngine` → `regret_analysis.jsonl`, mort le 2026-07-10). Comparaison
   V1↔V2 (`scratchpad/compare_regret_v1_v2.py`) : V2 **n'est pas** un sur-ensemble
   de V1 (recouvrement 6-10/07 : V1=3621 vs V2=449, 12 % appariés, ~85 % d'accord
   de classification sur les appariés). Ce sont **deux instruments distincts** ;
   on ne recolle jamais leurs séries. L'époque V4 (≥ 2026-07-17T01:30Z) étant
   entièrement dans la vie de `regret-v2`, aucune réconciliation n'est nécessaire.

## Horizon canonique — justification

À 15m les verrous regret échouent (MW=58/GR=75), à 1h ils passent (MW=158/GR=141),
à 4h aussi (261/220). `1h` est retenu comme équilibre entre bruit court-terme et
durée de détention réelle (TP/SL ~1-2 %). Tout changement d'horizon = nouvel
addendum à ce contrat (jamais silencieux).
