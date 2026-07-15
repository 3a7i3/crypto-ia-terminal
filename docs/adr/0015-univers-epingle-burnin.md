# ADR-0015 — Univers de trading épinglé pendant le burn-in

- **Statut** : Accepté (décision opérateur Mathieu, 2026-07-14 — « je préfère
  que tu épingles l'univers pendant le burn-in »)
- **Date** : 2026-07-14
- **Contexte** : Famine de trading 2026-07-13/14 — 26h+ sans aucun trade,
  N canonique figé à 36, burn-in suspendu de fait sans qu'aucune décision
  explicite n'ait été prise.

## Contexte

### Ce qui s'est passé

Au restart du 2026-07-13 17:59:08Z, deux mécanismes de sélection dynamique
ont recomposé l'univers de trading :

1. **MarketUniverseRanker au boot** (`core/advisor_loop.py::__main__`,
   `RANKER_ENABLED=true` sur le VPS) : re-scan MEXC + scoring 6 critères →
   nouvelle liste à chaque redémarrage du process.
2. **PerpUniverseService en continu** (`core/perp_universe_service.py`) :
   rafraîchit l'univers toutes les `UNIVERSE_REFRESH_H` (6h) et injecte de
   nouveaux symboles en cours de cycle.

Résultat : ANSEM/USDT, PARK/USDT, TRUMP/USDT, LAB/USDT — les paires
volatiles qui produisaient les candidats au-dessus des seuils de régime
(68-75 vs bull=72/high_vol=68/sideways=66, cf.
`market_regime_classifier.py::_REGIME_CONFIGS`) — sont sorties de la
sélection. Les entrants (TAO, INJ, SUI, USDGO…) plafonnent à ~58. En 26h,
seuls 41 signaux ≥66 ont été produits (ETH 70×21, CASHCAT 66×20), tous
sous leur seuil de régime : `signal_score (66<72)`. **Zéro trade, N figé,
burn-in à l'arrêt — par effet de redémarrage, pas par décision.**

### Pourquoi c'est un problème scientifique

La composition de l'univers est une **variable expérimentale majeure** :
elle détermine quels régimes et quels profils de volatilité alimentent le
dataset. La laisser tourner à chaque restart :

- casse la stationnarité exigée pour l'accumulation de N (règle du
  statisticien, CLAUDE.md) ;
- rend le débit de trades dépendant du hasard des redémarrages ;
- introduit un biais de composition invisible entre les tranches du dataset
  (les trades pré/post-restart ne mesurent pas le même univers).

C'est exactement le type de variable que le Scientific Debt Rule impose
d'éliminer, pas d'ajouter.

## Décision

1. **Nouvelle variable d'environnement `UNIVERSE_PINNED_SYMBOLS`**
   (liste séparée par espaces, même convention que `V9_SYMBOLS`).
   Quand elle est non vide :
   - la liste est utilisée telle quelle au boot (`__main__`) — le
     MarketUniverseRanker est ignoré même si `RANKER_ENABLED=true` ;
   - le `PerpUniverseService` n'est pas démarré — aucune injection
     dynamique en cours de session (la sync par cycle est gardée par
     `_universe_service is not None`).
   Vide = comportement historique inchangé (ranker + découverte actifs).

2. **Pendant toute la durée du burn-in** (jusqu'aux gates de calibration,
   N≥500 et CRI≥90, CLAUDE.md), `UNIVERSE_PINNED_SYMBOLS` doit être défini
   dans le `.env` du VPS. Toute modification de la liste est une décision
   opérateur explicite, tracée par commit du présent ADR (section
   « Liste épinglée » ci-dessous mise à jour).

3. **Liste épinglée v1 (recommandée, à confirmer par l'opérateur au
   déploiement)** : l'union des 25 paires actuellement scannées et des
   symboles présents dans le dataset propre (qui ont produit N=36) :

   ```
   ANSEM/USDT PARK/USDT TRUMP/USDT LAB/USDT ANTFUN/USDT ETHFI/USDT
   TAO/USDT LTC/USDT DOT/USDT WXT/USDT BTC/USDT INJ/USDT XRP/USDT
   ETH/USDT BTC/USDC SUI/USDT ETH/USDC SOL/USDT DOGE/USDT BNB/USDT
   ADA/USDT ZEC/USDT TRX/USDT CASHCAT/USDT VELVET/USDT USD1/USDT
   EVAA/USDT USDGO/USDT
   ```

   Rationale : conserve la continuité avec le dataset existant (ANSEM/PARK/
   TRUMP/LAB ont généré la majorité des trades propres) tout en gardant les
   majors pour la couverture de régimes. La `SYMBOL_BLACKLIST` existante
   (tokens toxiques, ADR-0011/data_quality) reste prioritaire et inchangée.

## Conséquences

- **Gain** : une variable expérimentale éliminée ; le débit de trades ne
  dépend plus du hasard des restarts ; N peut recommencer à s'accumuler
  sur un univers constant et documenté.
- **Coût assumé** : l'univers ne suit plus le marché (une paire qui meurt
  reste scannée, une nouvelle opportunité n'entre pas). Pendant une phase
  de VALIDATION c'est le comportement voulu — l'objectif est de mesurer le
  système, pas de maximiser le rendement.
- **Réversibilité** : retirer `UNIVERSE_PINNED_SYMBOLS` du `.env` + restart
  → comportement historique restauré à l'identique.
- Si une paire épinglée est délistée par MEXC, elle produit des erreurs de
  fetch silencieuses déjà gérées (score 0, aucun trade) — dégradation
  douce, pas de panne.

## Implémentation

- `core/advisor_loop.py::_universe_pinned_symbols()` — helper unique,
  lu au boot (`__main__`) et au démarrage du `PerpUniverseService`.
- Tests : `tests/test_advisor_loop_message_helpers.py` (parsing, vide,
  espaces).
- Application VPS : ajouter la ligne `UNIVERSE_PINNED_SYMBOLS="…"` au
  `.env` du VPS (hors git, geste opérateur), puis déploiement
  (`deploy_vps.sh --confirm`) et restart systemd (ADR-0013). Le `.env`
  n'étant jamais écrasé par le déploiement (filtre d'exclusion), la liste
  survit aux déploiements suivants.

## Liens

- ADR-0011 (borne dataset propre, règle du statisticien)
- ADR-0012 (époque SEC-01, stationnarité du dataset)
- ADR-0014 (proposé — brancher ranker/meta sur MexcSim ; indépendant)
- Mémoire d'incident : famine de trading 2026-07-13/14 (session Claude
  Code, non versionnée)
