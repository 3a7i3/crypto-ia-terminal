# ADR-0012 — Époque SEC-01 : fin de la contamination `consecutive_losses`

- **Statut** : Accepté
- **Date** : 2026-07-09
- **Contexte** : Durcissement de l'exécution réelle (SEC-01,
  `ExecutionEngine.from_env()`/`_place_live_order()`) ayant révélé, en
  traçant sa chaîne de conséquences, une contamination du chemin de
  décision par du bruit d'exécution technique — active depuis au moins
  le Sprint T1 (2026-07-05), probablement avant.

## Contexte

Le Sprint T1 (2026-07-05) avait identifié une faille de code réelle mais
neutralisée en pratique : `ExecutionEngine` tentait des ordres réels sur
MEXC à chaque signal validé (`V9_ADVISOR_ONLY=false` sur le VPS), rejetés
uniquement grâce à une clé API en lecture seule (erreur MEXC `700007`).
Le sprint SEC-01 visait à corriger ce trou au niveau du code (gate
`PAPER_TRADING_ENABLED` + défense en profondeur `LIVE_TRADING_CONFIRMED`),
pas seulement compter sur un garde-fou externe.

En traçant la neutralité du gate (« le blocage doit produire exactement le
même résultat observable que le rejet 700007 actuel »), la question posée
a été : est-ce que `mode="live_failed"` (rejet 700007 ou futur gate SEC-01)
alimente autre chose qu'un compteur informatif ? Réponse : **oui, cinq
composants de décision**, tous nourris par le même compteur global
`_consecutive_losses["value"]` (`core/advisor_loop.py`), qui s'incrémente
aussi bien sur une vraie perte de trade (`pos.pnl_pct < 0`) que sur un
échec d'exécution technique (`mode in {"live_failed","futures_failed"}`)
— rien ne distingue les deux dans ce compteur.

### La chaîne des cinq consommateurs

1. **`RiskGovernor.update(consecutive_losses=...)`** (`advisor_loop.py:4990`)
   → `consecutive_losses>=3` (état DEFENSIVE/RECOVERY) transitionne vers
   `RISK_OFF` → `gate.set_governor_delta(+15)` (`advisor_loop.py:5001`)
   relève le score requis sur `GlobalRiskGate._effective_min_score()`
   (`global_risk_gate.py:565`), `allow_new_trades=False`,
   `size_multiplier=0.0`.
2. **`MetaStrategyEngine.select(consecutive_losses=...)`**
   (`advisor_loop.py:5137`) → `>=2` : `order_size_factor` ×0.7 ; `>=3` :
   ×0.4 et `min_score=max(min_score,80)` (`meta_strategy_engine.py:251-262`).
3. **`ExecutiveOverride.update(loss_streak=...)`** (`advisor_loop.py:4227-4228`,
   à la fermeture de position) → seuils 3/5/7/10 → REDUCE/CAREFUL/MINIMAL/VETO
   (`executive_override.py:29-32`) ; VETO bloque tout nouvel ordre.
4. **`MistakeMemory.record_trade_result(consecutive_losses=...)`**
   (`advisor_loop.py:4197`) → si perte réelle et `consecutive_losses>=3`,
   génère une `BlockRule` persistante `{"consecutive_losses_min":3,
   "max_score":84}` (`mistake_memory.py:446-451,517-523`). **Jamais
   atteint en pratique** : `databases/mistake_memory.jsonl` est absent du
   VPS, confirmé par le log de démarrage (`0 erreurs memorisees | 0
   regles actives`) — la contamination a freiné le moteur en temps réel
   sans jamais rien graver en mémoire long terme.
5. **`check_hard_limits(consecutive_losses=...)`** (`advisor_loop.py:5471-5483`)
   → `>=5` (`risk/risk_limits.py:62`) lève `HardLimitBreached`, bloque
   l'ordre en cours dans le même cycle.

`portfolio_brain.py` : aucune consommation de cette chaîne, confirmé par
recherche exhaustive — ses refus (majoritaires dans les MISSED_WIN, voir
plus bas) relèvent d'un mécanisme distinct et non contaminé.

### Quantification (lecture seule, VPS, avant toute décision — script exécuté
puis supprimé, `trade_log.sqlite` + `paper_trades.jsonl` + `regret_analysis.jsonl`)

Reconstruction de la trajectoire du compteur (réelle vs contrefactuelle
ignorant les échecs techniques), fenêtre `CLEAN_DATA_SINCE` v1
(2026-06-25 → 2026-07-09, 14.04 jours) :

| Métrique | Jours | % fenêtre |
|---|---|---|
| Sous `consecutive_losses>=3` à cause du bruit seul | 3.92 | **27.9 %** |
| Sous `consecutive_losses>=3` justifié par de vraies pertes | 2.69 | 19.1 % |
| **Total sous `>=3`** | 6.61 | **47.0 %** |
| Sous `>=2` à cause du bruit seul | 1.25 | 8.9 % |

Croisement avec `regret_analysis.jsonl` (1368 `MISSED_WIN` post-06-25) :
1269 (92.8 %) ont `refused_by` incluant `meta_strategy` ou `gate` — les
deux mécanismes prouvés contaminés ; **278 (20.3 %, plancher)** sont
survenus précisément pendant une fenêtre où le seuil `>=3` n'était atteint
qu'à cause du bruit technique. Plancher, pas mesure complète : exclut les
cas où le bruit a accéléré (sans être seul responsable) l'atteinte du
seuil.

## Décision

### 1. SEC-01 déployé aux deux niveaux, sans compromis de neutralité

Le gate `PAPER_TRADING_ENABLED` (neutralité stricte vs 700007) ET la
défense en profondeur `LIVE_TRADING_CONFIRMED` (absent par défaut) sont
déployés ensemble. Argument constitutionnel : le gel scientifique protège
la mesure du système *tel que conçu*, pas la reproduction fidèle d'un
système *bogué*. Préserver à l'identique un comportement dont on vient de
prouver qu'il dépend d'un accident externe (permissions d'une clé API) et
contamine cinq mécanismes de décision n'a aucune valeur scientifique.

### 2. Nouvelle borne canonique : `CLEAN_DATA_SINCE_V2`

`CLEAN_DATA_SINCE_V2 = 2026-07-09T01:16:00Z` (`scripts/data_quality.py`),
timestamp du restart déployant SEC-01 — documentée dans le code AVANT le
restart et avant toute observation des résultats post-fix (règle du
statisticien respectée à la lettre). Contient strictement
`CLEAN_DATA_SINCE` v1 (2026-06-25) : tout ce que v1 excluait, v2 l'exclut
aussi, plus la fenêtre contaminée qui vient d'être quantifiée. v1 n'est
pas contredite, seulement remplacée comme borne active — elle reste
documentée pour l'audit qualité de données (tokens toxiques, bypass
`meta_allowed`, un problème différent, toujours vérifié par
`scripts/data_quality.py` check #9).

`tools/cri_calculator.py` importe désormais `CLEAN_DATA_SINCE_V2` depuis
`scripts/data_quality.py` (source unique) au lieu d'une copie locale —
dette notée au Sprint T2 (2026-07-07), soldée ici. **Aucune définition ni
pondération du CRI n'est modifiée** (ADR-0011 tient intégralement) : seule
la borne change.

### 3. Règle induite — ticket CAL-003

Les compteurs de risque doivent distinguer structurellement perte de
marché et échec technique — pas seulement cesser de contaminer par
extinction du bruit (ce que fait SEC-01 en empêchant `_place_live_order`
d'être atteint). `_consecutive_losses` reste aujourd'hui un compteur
unique alimenté par deux sources sémantiquement différentes dans
`core/advisor_loop.py` ; SEC-01 supprime la source de bruit dominante
mais ne refactore pas le compteur lui-même. **CAL-003** (calibration,
hors gel scientifique tant que non validé statistiquement) : séparer
`_consecutive_losses` (pertes réelles) de `_consecutive_exec_errors`
(déjà existant, jamais consommé par une décision — voir audit ci-dessus)
de façon structurelle, pour qu'un futur bug d'exécution ne puisse plus
se rejouer silencieusement dans une métrique de décision.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Niveau 1 seul (gate neutre vs 700007, sans `LIVE_TRADING_CONFIRMED`) | Préserve la contamination à l'identique — neutralité envers un bug n'est pas neutralité scientifique |
| Garder `CLEAN_DATA_SINCE` v1 comme unique borne | Compterait comme "propre" une fenêtre prouvée contaminée à 47 % sur le seuil `>=3` |
| Fixer la borne V2 après avoir observé le débit post-fix | Biais rétrospectif — exactement ce que la règle du statisticien interdit |
| Purger les `BlockRules` de MistakeMemory | Inventaire confirmé vide (`0 erreurs memorisees | 0 regles actives`) — rien à purger |

## Conséquences

**Positives :**
- Le moteur mesuré à partir de `CLEAN_DATA_SINCE_V2` est, pour la première
  fois depuis au moins le 2026-07-05, celui réellement conçu — sans frein
  auto-infligé par du bruit technique.
- Le débit de trades propres devrait augmenter (gate à son seuil nominal,
  meta-strategy hors `capital_protection` par défaut), donc le prochain
  gate N≥50 pourrait arriver plus vite que les 23 trades manquants ne
  l'auraient fait sous contamination.

**Négatives / compromis :**
- Le compteur N repart à 0 sous la borne v2 — les 27 trades comptés sous
  v1 ne sont plus canoniques pour le CRI (ils restent lisibles, non
  supprimés, juste hors fenêtre active).
- CAL-003 (séparation structurelle des compteurs) reste un ticket ouvert,
  pas résolu ici — SEC-01 traite le symptôme dominant (bruit d'exécution),
  pas l'architecture du compteur partagé.

**Règles induites :**
- Toute référence à "N trades propres" ou aux seuils du tableau
  statisticien filtre désormais par `CLEAN_DATA_SINCE_V2`.
- Tout module comptant des trades propres délègue à
  `tools.cri_calculator.load_clean_trades()` — jamais de copie locale de
  la borne (vérifié 2026-07-09 : `system_intel_reporter.py` s'y conforme
  déjà ; aucun autre consommateur trouvé).
- CAL-003 est un ticket de calibration (hors gel tant que non validé
  statistiquement, cf. Règle du statisticien, CLAUDE.md) — pas une
  autorisation de modifier `_consecutive_losses` sans nouvel examen.
