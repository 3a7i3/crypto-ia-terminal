# ADR-0005 — Regret Intelligence : évaluation multi-horizon asynchrone

**Date :** 2026-06-29
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

Le `RegretEngine` existant évalue les refus N cycles après le signal (cycle-based, ~4 cycles).
Il ne mesure que la direction et la magnitude du mouvement. Il ne calcule pas de métriques
financières (Sharpe, PF, Expectancy, MFE/MAE). Il évalue sur un seul horizon (4 cycles ≈ 20-40
min selon la cadence). L'appel `get_threshold_delta()` applique automatiquement un ajustement de
seuil en production — ce qui viole le principe de passivité (voir ADR-0007).

## Décision

Créer `observability/regret_scheduler.py` : un scheduler background thread qui évalue
chaque `RejectionRecord` sur 7 horizons temporels (5 min, 15 min, 30 min, 1h, 4h, 12h, 24h)
en utilisant les prix disponibles dans le cache du scanner. Pour chaque horizon, calcule :
rendement théorique, drawdown max, MFE (maximum favorable excursion), MAE (maximum adverse
excursion), Sharpe simplifié, regret_score [0,1], type (MISSED_WIN / GOOD_REFUSAL / NEUTRAL).
Les résultats sont persistés dans `databases/regret/regret_horizons_YYYY-MM-DD.jsonl`.

Le `RegretEngine` existant est conservé intact pour la compatibilité. `get_threshold_delta()`
est transformé en recommendation-only (voir ADR-0007).

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Évaluation synchrone dans le cycle | Bloquerait le pipeline pendant les lookups de prix (latence ×7 horizons) |
| asyncio | Complexity incompatible avec le threading model de advisor_loop ; pas de bénéfice ici |
| Étendre RegretEngine en place | Risque de régression sur l'interface existante utilisée dans advisor_loop.py |
| Évaluation offline (script séparé) | Perd le contexte mémoire des candidats en cours ; nécessite reconstruction à partir de JSONL |

## Conséquences

**Positives :**
- Zéro impact sur la latence du cycle de trading (thread daemon séparé)
- 7 horizons = vue complète du coût réel d'un refus
- MFE/MAE permettent d'identifier les "lucky refusals" vs "unlucky refusals"
- La périodicité du wakeup correspond aux horizons — pas de polling inutile

**Négatives / compromis :**
- Requiert que le cache de prix soit accessible depuis le thread background (partagé via dict thread-safe)
- L'évaluation 24h est différée de 24h — le regret n'est connu que le lendemain
- Les horizons courts (5-15 min) peuvent manquer si le cycle du scanner est lent (>5 min)

**Règles induites :**
- Le scheduler ne modifie jamais de paramètre du moteur de décision
- Les résultats sont disponibles en lecture pour les analyses humaines et la Phase 4 (ACE) uniquement
- Le cache de prix partagé doit être thread-safe (verrou ou structure atomique)
- Le scheduler doit s'arrêter proprement sur SIGTERM (daemon thread)
