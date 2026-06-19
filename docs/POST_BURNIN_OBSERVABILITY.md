# POST_BURNIN_OBSERVABILITY.md

## Objectif

Ce document définit les métriques d'observabilité qui seront ajoutées **après validation du burn-in ALPHA_DISCOVERY_100**.

Aucune de ces métriques ne doit être intégrée pendant le burn-in en cours afin de préserver la comparabilité des résultats.

---

# Métrique 1 — scan_wall_ms

## Objectif

Mesurer le temps total d'un cycle `MarketScanner.scan()`.

## Point de mesure

Début :

* `MarketScanner.scan()`

Fin :

* Retour de `scan()`

## Utilisation

Permet de déterminer :

* si le scanner devient le goulot d'étranglement ;
* si le nombre de symboles dégrade la latence ;
* si une nouvelle architecture est nécessaire.

## Décision d'architecture

Principal indicateur pour **P0**.

---

# Métrique 2 — lock_wait_p99_ms

## Objectif

Mesurer la contention provoquée par `exchange_call_lock`.

## Point de mesure

Autour de :

* acquisition de `exchange_call_lock`

Calcul :

* moyenne
* P95
* P99

## Utilisation

Permet de déterminer :

* si le verrou HTTP limite réellement le débit ;
* si un scheduler avec rate limiting devient prioritaire.

## Décision d'architecture

Principal indicateur pour **P1**.

---

# Métrique 3 — snapshot_skew_ms

## Objectif

Mesurer l'écart temporel entre la première et la dernière donnée OHLCV utilisée dans un même cycle de décision.

## Point de mesure

Dans `MarketScanner.scan()` :

* timestamp de la première bougie collectée ;
* timestamp de la dernière bougie collectée.

Calcul :

```
snapshot_skew_ms = max_timestamp - min_timestamp
```

## Utilisation

Permet de vérifier que toutes les décisions reposent sur un état de marché cohérent.

## Décision d'architecture

Principal indicateur pour **P2**.

---

# Métrique 4 — decision_age_ms

## Objectif

Mesurer l'âge des données au moment où une décision est effectivement prise.

## Point de mesure

Dans `advisor_loop.py`.

Début :

* timestamp de la dernière bougie renvoyée par `MarketScanner.scan()`

Fin :

* instant où le Decision Engine émet la décision finale

Calcul :

```
decision_age_ms = decision_timestamp - candle_timestamp
```

## Utilisation

Mesure la fraîcheur réelle des données utilisées par le moteur de décision.

Cette métrique reste valide même si la collecte est séparée du moteur de décision.

## Décision d'architecture

Indicateur principal pour **P0** et **P2**.

---

# Format JSONL cible

Chaque cycle de scan produira une entrée du type :

```json
{
  "timestamp": "...",
  "scan_wall_ms": 0,
  "lock_wait_p99_ms": 0,
  "snapshot_skew_ms": 0,
  "decision_age_ms": 0
}
```

---

# Tableau de synthèse

| Métrique           | Point de mesure                  | Décision débloquée |
| ------------------ | -------------------------------- | ------------------ |
| `scan_wall_ms`     | `MarketScanner.scan()`           | P0                 |
| `lock_wait_p99_ms` | autour de `exchange_call_lock`   | P1                 |
| `snapshot_skew_ms` | `MarketScanner.scan()`           | P2                 |
| `decision_age_ms`  | `advisor_loop.py`                | P0 / P2            |

---

# Priorités post-burn-in

**P0** — Découpler collecte et décision.

**P1** — Remplacer le verrou HTTP global par un ordonnanceur avec rate limiting.

**P2** — Introduire un cache partagé avec snapshots cohérents.

**P3** — Réévaluer la granularité du Circuit Breaker (si métriques le justifient).

**P4** — Découpage SRP du `MarketScanner`.

Aucune implémentation ne sera réalisée avant la validation complète du burn-in **ALPHA_DISCOVERY_100**.
