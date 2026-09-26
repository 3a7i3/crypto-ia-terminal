# BUGS

> Dernière revue forensique : 2026-09-26, contre `main@98082ef01e8bef93f86fe5e4d1d2af48dddec53e`.
> Chaque statut modifié ci-dessous est appuyé par une vérification de source
> datée, jamais par une reconduction d'un rapport antérieur.

## Regles

- Un bug = un item clair
- Indiquer le statut et l'impact
- Mettre a jour la ligne plutot que dupliquer l'information
- Un statut ne change que sur preuve (fichier + ligne/fonction, ou issue/PR)

## Statuts

- open
- in_progress
- blocked
- fixed

## Bugs suivis

| ID | Statut | Zone | Description | Impact | Notes |
|---|---|---|---|---|---|
| BUG-001 | fixed | documentation | Le `README.md` racine pointait vers plusieurs fichiers sans prefixe `docs\`, alors que les fichiers existent sous `docs\...` | eleve | Corrige le 2026-05-26 : liens visibles vers onboarding, quick start, config, index, roadmap, validation et rapports d'audit |
| BUG-002 | fixed | documentation | Les badges du `README.md` utilisaient encore les placeholders `<OWNER>` et `<REPO>` | faible | Corrige le 2026-05-26 avec `0xl1v/crypto-ai-terminal` |
| BUG-003 | open | architecture | Trois vocabulaires de régime coexistent ; les mappings de conversion sont dupliqués et non contractualisés | moyen | **Revérifié 2026-09-26 — partiellement résolu, pas clos.** Voir la matrice ci-dessous |
| BUG-004 | fixed | architecture | `blacklisted_regimes` n'utilisait pas un format unique entre l'API historique et le flux `DecisionPacket` | eleve | Corrige le 2026-05-26 : `GlobalRiskGate` normalise les regimes legacy et packet avant comparaison. Revérifié 2026-09-26 : `_normalize_regime()` + `_REGIME_ALIASES` présents et fonctionnels |
| BUG-005 | open | architecture | Deux enums `ConvictionLevel` coexistent avec des ensembles de valeurs incompatibles | moyen | **Revérifié 2026-09-26 — toujours actif.** `quant_hedge_ai/agents/intelligence/conviction_engine.py:46` = `minimal/low/medium/high/exceptional` ; `core/decision_packet.py:51` = `VERY_HIGH/HIGH/MEDIUM/LOW/SKIP`. Divergence sémantique, pas seulement de casse : `MINIMAL`/`EXCEPTIONAL` n'ont pas d'équivalent, `SKIP`/`VERY_HIGH` non plus. Aucune fonction de conversion trouvée |
| BUG-006 | open | tests | Quelques fichiers `test_*.py` racine restent a fiabiliser ou reclasser | moyen | Cas cites dans `ROOT_TEST_AUDIT.md` : `test_analyze_strategy_niches.py`, `test_fallbacks_intelligents.py`, `test_fullsuite.py`, `test_onboarding_feedback_playwright.py`, `test_plot_god_mode.py`, `test_security_permissions.py`. Non revérifié le 2026-09-26 |
| BUG-007 | open | environnement | La `.venv` locale pointe vers `C:\Users\WINDOWS\AppData\Local\Programs\Python\Python311\python.exe`, absent du poste courant | eleve | Poste de développement local uniquement ; sans effet sur la CI GitHub ni sur le VPS. Non revérifié le 2026-09-26 |

## BUG-003 — matrice de vocabulaire des régimes (relevé 2026-09-26)

| Producteur | Champ | Type | Valeurs autorisées | Consommateur | Canonique ? | Conversion |
|---|---|---|---|---|---|---|
| `core/decision_packet.py:43` `MarketRegime` | `DecisionPacket.regime` | enum str | `TREND_BULL`, `TREND_BEAR`, `RANGE`, `VOLATILE`, `UNKNOWN` | GlobalRiskGate, RL-DIAG (`packet_regime`) | ✅ **canonique** | aucune requise |
| `quant_hedge_ai/.../market_regime_classifier.py` (format détecteur) | `RegimeConfig.regime` | str libre | `bull_trend`, `bear_trend`, `sideways`, `high_volatility_regime`, `flash_crash`, `unknown` | `live_signal_engine._REGIME_MAP` | ❌ non canonique | `_REGIME_MAP` (6 entrées) → canonique |
| `src/domain/trade_event.py:26` `MarketRegime` | `TradeEvent.regime` | enum str | `unknown`, `trending`, `sideways`, `volatile` | `src/engine/virtual_exchange.py` (stack backtest/analytics) | ❌ non canonique | **aucune** |
| `core/decision_packet.py` `features.regime` | score numérique | float | continu | RL-DIAG (`features_regime_score`) | ✅ distinct du catégoriel | sans objet |
| `core/decision_packet.py` `conviction_dimensions.regime` | score numérique | float | continu | RL-DIAG (`conviction_dim_regime`) | ✅ distinct du catégoriel | sans objet |

**Ce qui est résolu**

- Le chemin décisionnel critique est normalisé : `GlobalRiskGate._normalize_regime()`
  (`quant_hedge_ai/agents/risk/global_risk_gate.py:91`) ramène 18 alias au jeu
  canonique avant toute comparaison de blacklist (BUG-004).
- RL-DIAG distingue déjà explicitement le régime **catégoriel** de haut niveau
  (`packet_regime`) et les **scores numériques** (`features_regime_score`,
  `conviction_dim_regime`) : `research_diag/factual.py:344,366,373`.
  BUG-003 n'est donc **pas** un bloqueur de RL-DIAG.

**Ce qui reste**

1. Deux tables de conversion indépendantes coexistent en runtime —
   `live_signal_engine._REGIME_MAP` (6 entrées, côté producteur) et
   `global_risk_gate._REGIME_ALIASES` (18 entrées, côté consommateur). Elles
   s'accordent sur les clés communes, mais aucun contrat unique n'en garantit
   la cohérence si l'une évolue.
2. Le vocabulaire de `src/domain/trade_event.py` n'est couvert par aucune des
   deux tables. Vérifié le 2026-09-26 :
   `_normalize_regime("trending") == "trending"` et
   `_normalize_regime("TRENDING") == "trending"` — passage en minuscules sans
   correspondance canonique. `TRENDING` perd de surcroît la direction que
   `TREND_BULL`/`TREND_BEAR` portent, et `SIDEWAYS` y double `RANGE`.
   Aucun chemin d'appel live prouvé entre la stack `src/` (backtest/analytics)
   et `GlobalRiskGate` : défaut **latent**, non observé en production.
3. `MarketRegime(...)` en désérialisation (`core/decision_packet.py:830`)
   échoue en `ValueError` sur toute valeur de vocabulaire legacy
   (`bull_trend`, `trending`, `sideways` — vérifié). Comportement *fail-closed*,
   donc sûr, mais il impose que la conversion soit appliquée **avant**
   désérialisation : c'est exactement la fragilité décrite à l'origine.

**Verdict 2026-09-26 : `PARTIALLY_RESOLVED`.**
Reste une dette de contrat (vocabulaire unique + table de conversion unique),
pas un défaut de sécurité décisionnelle. Aucune modification de sémantique
runtime n'a été faite dans cette revue. Un contrat formel n'est justifié que
si l'opérateur décide de fusionner les vocabulaires — décision hors périmètre
de l'audit.

## Tri rapide

- Priorite haute : BUG-007 (poste local)
- Priorite moyenne : BUG-003, BUG-005, BUG-006
- Corriges : BUG-001, BUG-002, BUG-004
