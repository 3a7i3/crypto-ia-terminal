# ADR-0018 — Source canonique de regret = `regret-v2` (pour V4+)

**Statut : ACCEPTÉ** (2026-07-21, opérateur) · Voir MC-001 · Implémenté :
`tools/regret_repository.py`, patch `tools/cri_calculator.py`

## Contexte

Le dossier Go/No-Go V4 lisait `MISSED_WIN = 0`, `GOOD_REFUSAL = 0`. Audit
2026-07-21 : ce n'est **pas** une observation, c'est une **rupture de
traçabilité**. Deux pipelines de regret ont coexisté :

- **v1** — `RegretEngine` → `databases/regret_analysis.jsonl` (mono-évaluation).
  **Mort le 2026-07-10T14:23Z** (dernier record). C'est ce que lisait le
  `cri_calculator` → d'où les zéros.
- **v2** — `observability/regret_scheduler.py` → `databases/regret/regret_horizons_*.jsonl`
  (event-bus, multi-horizon 5m→24h). **Vivant**, 849 observations sur l'époque V4.

## Décision

1. **`regret-v2` est la source canonique de regret pour l'époque V4 et au-delà.**
2. **Horizon canonique = `1h`** (pré-enregistré, voir MC-001).
3. Le `cri_calculator` (et tout consommateur) lit via `tools.regret_repository`,
   plus jamais un chemin en dur. Sortie enrichie de `dataset_version`,
   `canonical_horizon`, `regret_fresh`, `validity`.
4. **v1 est retiré** comme source de certification (chemin explicite conservé
   pour audit historique uniquement).

## Justification (pas « superset » — la donnée le réfute)

La comparaison V1↔V2 (`scratchpad/compare_regret_v1_v2.py`, recouvrement 6-10/07)
montre que **v2 n'est pas un sur-ensemble de v1** : V1=3621 vs V2=449 événements,
12 % appariés, ~82-86 % d'accord de classification sur les appariés (divergences
explicables par des seuils v2 plus bas). Ce sont donc **deux instruments
distincts, non réconciliables**. L'adoption se justifie non par un superset mais
par : (a) v1 est mort ; (b) v2 est le successeur intégral, plus riche
(multi-horizon, blockers, régime) ; (c) l'époque V4 est **entièrement** dans la
vie de v2 → aucune réconciliation ni splicing requis.

## Conséquences

- Une fois repointé, la couverture regret V4 passe de 0 à réel ; les verrous
  MISSED_WIN/GOOD_REFUSAL (100/100) sont atteints à l'horizon 1h (158/141).
- **Le verdict Go/No-Go reste NO-GO** — le goulot est N=30 trades *pris* (axe
  alpha), distinct de la couverture des *refus*. On passe d'un « no-go aveugle »
  à un « no-go propre ».
- Invariant de fraîcheur ajouté : une future panne silencieuse d'un producteur
  déclenchera désormais `validity=PARTIAL` au lieu de zéros trompeurs.
