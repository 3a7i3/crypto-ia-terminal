# ADR-0014 — Brancher `StrategyRanker`/`MetaStrategyEngine` sur les clôtures MexcSim

- **Statut** : Proposé (en attente de validation Mathieu)
- **Date** : 2026-07-13
- **Contexte** : Réconciliation des panneaux Telegram 2026-07-12/13 — deux
  correctifs d'affichage déjà appliqués (`90a7311`, `59b6eec`) montrent que
  `win_rate`/`avg_sharpe` figés à 0% dans `PhaseKPITracker` et
  `StrategyRanker` ont la même cause : leurs callbacks d'alimentation sont
  branchés sur `pos_manager`, qui ne clôture jamais rien en paper trading.
  Les deux correctifs déjà livrés sont de l'affichage pur (ADR-0007
  respecté) ; ce document couvre l'option non appliquée — brancher les
  composants eux-mêmes, pas seulement leur affichage.

## Contexte

### Ce qui est déjà corrigé (hors périmètre de cet ADR)

`_kpi_snapshot_with_canonical_n()` et `_top_strategies_for_display()`
(`core/advisor_loop.py`) recalculent `win_rate`/`sharpe` à l'affichage à
partir du dataset canonique (`tools.cri_calculator.load_clean_trades()`),
sans toucher à l'état interne de `PhaseKPITracker` ni de `StrategyRanker`.
Le panneau Telegram ment moins ; le moteur, lui, continue de tourner avec
des composants qui n'ont jamais rien appris depuis la migration MexcSim-only.

### Ce qui reste cassé, et pourquoi c'est plus qu'un problème d'affichage

`StrategyRanker.record_trade()` et `MetaStrategyEngine.record_trade_result()`
ne sont appelés que depuis `_on_position_close_rank()`
(`core/advisor_loop.py:4320-4347`), lui-même enregistré exclusivement via
`pos_manager.on_close(_on_position_close_rank)` (`core/advisor_loop.py:4494`).
`MexcSimulator` (`paper_trading/mexc_simulator.py`) — qui exécute et clôture
réellement les positions en paper trading, seul générateur de
`paper_trades.jsonl` — n'expose aucun hook de callback équivalent (recherche
exhaustive : zéro occurrence de `on_close`/callback dans le fichier). Les 36
trades canoniques actuels n'ont donc **jamais** atteint `ranker`/`meta_engine`.

Contrairement au panneau KPI (pur affichage), ce que `ranker`/`meta_engine`
retournent alimente directement le chemin de décision :

- `LiveSignalEngine._score_memory()` (`quant_hedge_ai/agents/execution/live_signal_engine.py:455`)
  consomme `memory_sharpe = ranker.best_sharpe(regime)` (`core/advisor_loop.py:1323`)
  — **20 points sur 100** du score composite (le "Mémoire (20pts)" du Guide
  de lecture envoyé aux utilisateurs Telegram). `best_sharpe()` retourne
  `0.0` tant qu'aucune stratégie n'a ≥3 trades enregistrés
  (`StrategyScore.composite_score()`, `strategy_ranker.py:87-88`) — donc
  systématiquement `None`/`0.0` depuis toujours en pratique : **20% du
  score composite n'a jamais varié avec la performance réelle.**
- `ConvictionEngine` reçoit le même `memory_sharpe` et ne peut donc jamais
  produire le boost/malus de conviction basé sur l'historique.
- `MetaStrategyEngine.select()` — qui détermine la personnalité active
  affichée dans META-STRATEGY (`capital_protection`, `momentum`, etc.) —
  n'a jamais reçu de résultat réel pour apprendre quelle personnalité
  performe par régime.
- `ranker.size_factor(strategy_name, regime)` retourne toujours `1.0`
  (neutre) tant que `trades < MIN_TRADES_RANK=5`
  (`strategy_ranker.py:158,268`) — le sizing par performance de stratégie
  n'a jamais eu d'effet.

En clair : un sous-système censé représenter 20% du scoring plus la
sélection de personnalité et une partie du sizing tourne à vide, en
silence, depuis le passage à MexcSim comme seul exécuteur paper. Le
"blocking module: ExecutionEngine" et "meta_strategy:122/715 blocages"
vus dans les rapports `Crypto_ia_quant` reflètent donc en partie un
apprentissage qui n'a jamais eu lieu, pas seulement des refus de gate.

## Décision proposée

Alimenter `ranker.record_trade()` et `meta_engine.record_trade_result()`
depuis les CLOSE réels de `MexcSimulator`, pas seulement depuis
`pos_manager`. Deux implémentations possibles, **à trancher par
l'opérateur, pas par ce document** :

**Option A — callback direct.** Ajouter un mécanisme d'abonnement à
`MexcSimulator` (nouveau, n'existe pas aujourd'hui) et y brancher
`ranker.record_trade()`/`meta_engine.record_trade_result()` en plus (pas à
la place) de `pos_manager.on_close()`. Réactif, cohérent avec le patron
existant (`_on_position_close_rank`), mais **ajoute une capacité** à
`MexcSimulator` — à évaluer contre la Scientific Debt Rule (CLAUDE.md) :
justifié ici par l'élimination d'une variable expérimentale silencieuse
(20% du score qui ne varie jamais), pas par une opportunité technique.

**Option B — lecture différée par cycle.** À chaque cycle principal, lire
les nouveaux CLOSE de `paper_trades.jsonl` (déjà fait pour l'affichage via
`load_clean_trades()`) et rejouer ceux non encore vus dans
`ranker.record_trade()`/`meta_engine.record_trade_result()`. Aucune
nouvelle capacité sur `MexcSimulator` ; latence d'un cycle (≤300s) avant
qu'un trade fermé influence le scoring suivant — négligeable à l'échelle
du problème actuel (36 trades sur 4 jours).

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Ne rien faire (statu quo) | 20% du score composite et la sélection de personnalité restent des composants silencieusement inertes indéfiniment — contradictoire avec l'objectif de calibration future (CRI, gate N≥100) qui suppose que le moteur affiché est le moteur qui apprend |
| Se contenter des correctifs d'affichage déjà livrés (`90a7311`, `59b6eec`) | Corrige ce que Mathieu *voit*, pas ce que le moteur *fait* — le déséquilibre reste entier côté décision |
| Fusionner `pos_manager` et `MexcSimulator` en un seul tracker de position | Refonte de portée bien plus large que le problème posé ; risque élevé en gel fonctionnel, hors périmètre de cet ADR |

## Conséquences

**Positives :**
- Le score composite (`LiveSignalEngine`), la conviction et la sélection
  de personnalité (`MetaStrategyEngine`) redeviennent des composants
  réellement informés par la performance passée, au lieu de tourner sur
  une composante figée à zéro depuis le début.
- `ranker.size_factor()` peut enfin moduler la taille par stratégie/régime
  une fois `MIN_TRADES_RANK=5` atteint par combinaison.

**Négatives / compromis :**
- **Change le comportement de scoring en cours d'accumulation du dataset
  N≥100.** Les trades avant et après ce branchement ne seraient plus
  gouvernés par le même algorithme effectif (le score composite change de
  définition dès que `memory_sharpe` cesse d'être structurellement nul) —
  c'est exactement le type de rupture de stationnarité que la règle du
  statisticien (CLAUDE.md) est censée empêcher de traiter comme un non-
  événement. **Si cet ADR est accepté, il doit fixer explicitement** : (a)
  une nouvelle borne `CLEAN_DATA_SINCE_V4` au moment du déploiement, sur
  le même principe que V1→V2→V3, ou (b) l'acceptation documentée de la
  discontinuité comme caveat supplémentaire sur N (à la suite du caveat
  déjà acté dans `project_mexcsim_vs_gated_dataset_20260709`). Ce choix
  n'est pas tranché ici — décision d'opérateur.
- Option A ajoute une nouvelle capacité à `MexcSimulator` (justification
  Scientific Debt Rule à documenter dans la décision finale). Option B
  n'en ajoute aucune mais introduit une latence d'un cycle.
- `meta_strategy` a bloqué 122 signaux cette session / 715 depuis
  toujours (rapport `Crypto_ia_quant` du 13/07) sur un apprentissage nul
  — une fois branché, ce chiffre de blocage va probablement évoluer, sans
  qu'on puisse aujourd'hui prédire dans quel sens.

**Règles induites (si accepté) :**
- Toute future source de trades fermés (au-delà de `pos_manager` et
  `MexcSimulator`) qui voudrait alimenter `ranker`/`meta_engine` doit
  documenter explicitement si elle passe par le même point d'entrée
  choisi ici (Option A ou B), pour éviter une troisième source
  silencieuse.
- Ce document doit être validé explicitement par Mathieu avant toute
  implémentation (règle constitutionnelle ADR-0007) — aucun code n'a été
  modifié pour ce sujet au moment de la rédaction.
