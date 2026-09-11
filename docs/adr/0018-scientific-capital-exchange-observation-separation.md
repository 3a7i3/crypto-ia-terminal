# ADR-0018 — Séparation structurelle capital scientifique / observation d'exchange

**Statut :** Accepté
**Date :** 2026-09-11
**Mission :** O-02W-PRE-T1-D remediation (fixe les défauts établis par l'audit
PRE-T1-D, PR #134, `docs/contracts/O-02W-PRE-T1-D_REAL_CAPITAL_BOUNDARY.md`).
**Contexte gouvernance :** fenêtre de stabilisation VPS
(`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`). Cette ADR
documente une correction architecturale d'un défaut déjà audité — ce n'est
**pas** une nouvelle fonctionnalité, ni un signal/indicateur/stratégie
nouveau, ni une activation de trading réel.

---

## 1. Décision

Le capital utilisé par toute calculation de décision (sizing, risque,
Kelly/EV, drawdown, throttle) provient **exclusivement** du portefeuille
scientifique/paper (`WALLET_PAPER_CAPITAL` + cumul PnL du ledger
`databases/paper_trades.jsonl`). Cette valeur est calculée par
`infra.wallet_sync.get_scientific_capital()` — une fonction pure, sans
dépendance à `EXCHANGE_MODE`, `PAPER_TRADING_ENABLED`,
`LIVE_TRADING_CONFIRMED`, à l'état du singleton `WalletSync`, ni à un
quelconque client exchange.

Les soldes d'exchange réels (spot/futures via `ccxt`) restent une
information **strictement observationnelle**, exposée par
`WalletSync.observe_exchange_balance()` (nouvel accesseur, retournant un
`ExchangeBalanceObservation` explicite : `FRESH` / `ZERO` / `STALE_CACHE` /
`ERROR` / `ABSENT`) et par `observability/real_accounts.py` (déjà
structurellement indépendant, propre client `ccxt`, aucune dépendance à
`WalletSync`). Ces deux chemins peuvent alimenter l'affichage
(cockpit/Telegram) mais **jamais** une calculation de décision.

`ExecutionEngine.fetch_available_capital()` — le point d'entrée décisionnel
historique — appelle désormais `get_scientific_capital()` exclusivement et
ne fait plus aucun appel exchange, ne touche plus `self._exchange`,
`self._mode`, ni le singleton `WalletSync`.

## 2. Rationale scientifique

L'audit PRE-T1-D (PR #134, mergé `2f226d09`) a établi, par preuve
hermétique, que l'ancien mécanisme (`ExecutionEngine.fetch_available_capital()`
→ `get_wallet_sync(mode=wallet_mode)` → `WalletSync.get_balance()`)
souffrait de 10 défauts confirmés (voir §7 ci-dessous), tous dérivant d'une
seule cause racine : le capital utilisé pour la décision dépendait de
l'état mutable d'un singleton (`WalletSync._mode`, figé au premier appel de
`get_wallet_sync()`), lui-même dépendant de l'ordre d'initialisation du
processus — pas d'une formule stable et reproductible.

Le Scientific Debt Rule (CLAUDE.md) interdit toute nouvelle couche
décisionnelle et exige que toute correction soit justifiée par une
hypothèse ou un besoin de validation existant — ici, l'audit PRE-T1-D lui-
même constitue ce besoin : la validation scientifique (CRI, H1-H6, gates
S1→S5) exige que le capital d'entrée du sizing soit reproductible et
indépendant de variables opérationnelles non contrôlées (mode d'exchange,
ordre de boot). Un capital de décision qui varie silencieusement avec
l'ordre d'appel contamine toute mesure ultérieure (drawdown, ROI%, EV) sans
qu'aucun opérateur ne l'ait décidé — violation directe de la Règle du
statisticien (validation empirique).

## 3. Séparation des domaines

| | Capital de décision scientifique | Observation d'exchange |
|---|---|---|
| Accesseur | `infra.wallet_sync.get_scientific_capital()` | `WalletSync.observe_exchange_balance()`, `observability/real_accounts.py` |
| Formule | `WALLET_PAPER_CAPITAL` + cumul PnL ledger (inchangée, héritée de `WalletSync._base_capital()`/`get_balance()` mode paper) | solde `ccxt` réel, caché TTL |
| Dépendances | aucune (ni env exchange, ni singleton, ni réseau) | `EXCHANGE_MODE`/clés API, réseau |
| Consommateurs autorisés | `order_size`, `PortfolioBrain`, `CapitalAllocationEngine`, `ExecutiveOverride`, P10 `CapitalThrottle` (pinné, ADR-0011, inchangé) | cockpit, Telegram, `RealAccountsObserver` |
| Garantie structurelle | zéro appel réseau — testé par AST (invariant #20) | jamais consommé par le sizing — testé par AST (invariant #20) |

## 4. Conséquences

- `ExecutionEngine.fetch_available_capital()` ne fait plus de leak API →
  PAPER ni PAPER → LIVE/TESTNET (défauts #3, #4 fermés par construction :
  plus aucun branchement sur `self._mode`/`self._exchange`).
- `order_size` (`core/advisor_loop.py`) est désormais recalculé à chaque
  cycle avec le capital scientifique courant, plutôt que figé au bootstrap
  (défaut #8 fermé — voir §5 du contrat PRE-T1-D).
- L'échec/zéro/absence d'observation d'exchange est explicitement typé
  (`ExchangeObservationStatus`), éliminant le repli numérique ambigu
  (défauts #5, #6, #7 fermés).
- Le gate d'exécution réelle (`_place_live_order`, `PAPER_TRADING_ENABLED`,
  `LIVE_TRADING_CONFIRMED`, `SessionGuard`, kill-switch) est **inchangé** —
  cette ADR ne touche à aucune garantie de sécurité d'exécution (défaut #9
  documenté comme garantie indépendante, confirmé par les invariants F
  16-19).
- `RealAccountsObserver`/cockpit/Telegram restent purement observationnels,
  aucune modification requise (défaut #10, déjà conforme).
- Le throttle P10 `CapitalThrottle` (`capital_deployment/capital_throttle.py`)
  reste épinglé à `WALLET_PAPER_CAPITAL` (ADR-0011, ADR-0007) — **non
  modifié** par cette ADR, son rôle intentionnel est documenté et testé
  comme avant.

## 5. Alternatives rejetées

- **Faire muter `WalletSync._mode` après construction** (permettre à un
  appel `mode=` tardif de réellement changer le mode du singleton) : rejeté
  — ne corrige pas la dépendance à l'ordre d'appel, déplace simplement le
  moment où l'ambiguïté peut se produire ; ne satisfait pas l'invariance
  requise (identique quel que soit l'ordre).
- **Ajouter un sentinel `UNKNOWN`/`DEGRADED` au lieu d'un repli numérique
  dans `WalletSync.get_balance()`, en gardant `get_balance()` comme unique
  accesseur** : rejeté comme solution complète — corrige la défaut #6 mais
  laisse #1-#4 (le branchement sur le mode figé) intacts ; une séparation
  structurelle en deux accesseurs est plus mécaniquement vérifiable
  (exigence de la mission : « the boundary must be mechanically
  reviewable in the source structure »).
- **Fusionner les deux classes `CapitalThrottle` (P7/P10)** : rejeté —
  hors scope (voir contrainte G de la mission), le P10 est intentionnellement
  épinglé par ADR-0011 ; aucune nécessité de le fusionner pour satisfaire la
  séparation demandée ici.
- **Faire de `real_capital`/observation d'exchange une contrainte
  d'exécution finale post-sizing** (un plafond d'ordre basé sur le solde
  réel, appliqué après le sizing scientifique) : **explicitement hors
  scope de cette mission** — voir §6.

## 6. Hors scope — contrainte d'exécution future

Une mission future, séparément autorisée, pourra utiliser un solde
d'exchange observé (`WalletSync.observe_exchange_balance()`) comme
**contrainte d'exécution finale, en aval du sizing scientifique** — par
exemple un plafond dur empêchant un ordre réel de dépasser le solde
disponible. Cette contrainte ne doit **jamais** réinjecter cette
observation dans le calcul scientifique lui-même (elle resterait un
plafond d'exécution, jamais une entrée de décision). Aucune partie de ce
mécanisme n'est implémentée par cette ADR ou cette mission.

## 7. Statut des 10 défauts confirmés par l'audit PRE-T1-D

| # | Défaut | Statut |
|---|---|---|
| 1 | Mode du singleton figé au premier appel | `REMEDIATED_IN_PRE_T1_D` — la décision n'en dépend plus |
| 2 | Requête de mode tardive silencieusement ignorée | `REMEDIATED_IN_PRE_T1_D` — plus de requête de mode dans le chemin décisionnel |
| 3 | Singleton live/testnet peut exposer un solde API à une requête PAPER | `REMEDIATED_IN_PRE_T1_D` |
| 4 | Singleton paper peut exposer le capital paper à une requête LIVE/TESTNET | `REMEDIATED_IN_PRE_T1_D` |
| 5 | Erreur API live/testnet peut retourner `WALLET_PAPER_CAPITAL` silencieusement | `REMEDIATED_IN_PRE_T1_D` (`ExchangeObservationStatus.ERROR` explicite, jamais consommé par le sizing) |
| 6 | Zéro API et échec API peuvent produire le même résultat numérique | `REMEDIATED_IN_PRE_T1_D` (`ZERO` vs `ERROR` explicitement distincts) |
| 7 | `_x`/`_last_value` co-initialisés, mal décrits comme fallback ordinaire | `CURRENT_INVARIANT` — non modifié par cette mission, classification déjà corrigée par PR #134 (R1.2), reste hors du chemin scientifique |
| 8 | `order_size` peut rester figé après changement du capital scientifique | `REMEDIATED_IN_PRE_T1_D` (recalcul par cycle, `core/advisor_loop.py`) |
| 9 | Gate d'exécution et provenance du capital = garanties indépendantes | `CURRENT_INVARIANT` — confirmé inchangé, testé (invariants F16-F19) |
| 10 | `RealAccountsObserver`/cockpit/Telegram = observationnels seulement | `CURRENT_INVARIANT` — confirmé inchangé, aucune modification requise |

## 8. Non-autorisation explicite

Cette ADR et la mission qui l'accompagne n'autorisent **aucun** trading
réel, **aucun** déploiement VPS, **aucune** calibration alpha, **aucun**
nouveau signal/indicateur/stratégie. `PAPER_TRADING_ENABLED=true` et
`LIVE_TRADING_CONFIRMED=false` restent les défauts obligatoires et ne sont
modifiés par aucun changement de cette ADR.
