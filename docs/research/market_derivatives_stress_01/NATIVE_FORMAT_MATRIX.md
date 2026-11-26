# Matrice des formats natifs MEXC et Kraken — BTC et ATOM

Mission : préparer MARKET-DERIVATIVES-STRESS-01 ([contrat](../../contracts/MARKET_DERIVATIVES_STRESS_01.md))
avant tout adaptateur. Relevé du **2026-11-20**, **lecture de documentation uniquement** :
aucun endpoint de cotation, de catalogue ou de transactions n'a été appelé, aucune clé utilisée,
aucune collecte ni accès VPS. Statut : `SOURCE_ONLY / DOCUMENTAIRE / NON_DEPLOYED`.
La matrice dit **ce que la documentation officielle affirme**, pas ce que les plateformes
renvoient aujourd'hui : elle ne prouve ni mapping, ni fraîcheur, ni disponibilité.

Légende : **[DOC]** affirmé explicitement · **[PARTIEL]** champ documenté mais unité ou sémantique
non précisée · **[NON DOC]** absent de la doc lue · **[NON LU]** page non lue · **[ABSENT]** la doc
ne propose pas ce produit.

## 1. Sources lues, fraîcheur et réserves

| Source | Réf. | Réserve |
|---|---|---|
| Kraken Futures REST (OpenAPI : tickers, instruments, history, historical funding) | [docs.kraken.com](https://docs.kraken.com/api-reference/market-data/get-tickers.md) | Pages en date du relevé. Limites de débit **[NON LU]**. |
| Kraken Futures WebSocket (`ticker`, `trade`, `book`) | [ticker](https://docs.kraken.com/exchange/api-reference/futures-websocket/ticker.md) | **WebSocket dérivés déprécié, retrait annoncé le 1ᵉʳ mars 2027** ; migration vers le WebSocket unifié **[NON LU]**. |
| Kraken Spot REST (Ticker, Trades, AssetPairs) et WebSocket v2 (`ticker`, `trade`) | [docs.kraken.com](https://docs.kraken.com/api-reference/market-data/get-ticker-information.md) | `book` v2, limites de débit **[NON LU]** (le checksum `book` est déjà couvert par MARKET_BBO_COMPOSITE_01). |
| MEXC Spot v3 | [mexcdevelop.github.io/apidocs/spot_v3_en](https://mexcdevelop.github.io/apidocs/spot_v3_en) | Base `https://api.mexc.com`. Fraîcheur de ce miroir non datée. |
| MEXC Futures (contract v1) | [mexcdevelop.github.io/apidocs/contract_v1_en](https://mexcdevelop.github.io/apidocs/contract_v1_en) | **Dernière entrée du journal : 2025-04-09 ; base `https://contract.mexc.com`.** Voir ci-dessous. |

**Réserve majeure MEXC Futures.** `www.mexc.com/api-docs/futures/*` répond « Access Denied »
aux clients automatisés ; ce refus n'a pas été contourné. Une recherche web a rapporté (snippet,
**non vérifié**) que le journal officiel de cette page mentionnerait un changement de domaine de
base au 2026-01-19 vers `api.mexc.com` et une réouverture au 2026-03-31. Le miroir lu ne le dit pas.
**Domaine de base, statut `apiAllowed` et champs récents (`idxPrice`/`fairPrice` dans le funding)
sont donc UNRESOLVED** tant qu'un opérateur n'a pas relu la page officielle. L'exemple
`BTC_USDT` du miroir porte `"apiAllowed": false` (« whether support api »), sans lien établi avec
la lecture publique.

## 2. Identité des instruments

| | MEXC Spot | Kraken Spot | MEXC perpétuel | Kraken Futures |
|---|---|---|---|---|
| **BTC** | `BTCUSDT` | REST `XBTUSDT` (alias XBT↔BTC, déjà gardé par preuve de catalogue), WS `BTC/USDT` | `BTC_USDT` **[DOC]** (exemple `…SWAP`, base BTC, cote et règlement USDT) | **[PARTIEL]** exemples `PF_BTCUSD`, `PF_XBTUSD`, `PI_XBTUSD` : trois graphies selon la page ; cote **USD** dans toute la doc lue |
| **ATOM** | `ATOMUSDT` | `ATOMUSDT` / `ATOM/USDT` | `ATOM_USDT` : absent de la doc, **présent au catalogue du 2026-11-20** | `PF_ATOMUSD` : absent de la doc, **présent au catalogue du 2026-11-20** |

Les symboles spot viennent des liaisons déjà revues du dépôt (`observability/radar_composite/pilot.py`,
MARKET_BBO_COMPOSITE_01). La lecture de catalogue du 2026-11-20 (autorisée séparément) a confirmé les dérivés et leurs tailles de
contrat : voir [CATALOGUE_FICHES_20261120](CATALOGUE_FICHES_20261120.md). Elle ne remplace pas les unités d'OI ni l'intervalle de funding.

## 3. Prix, carnet et prix de marque

| Donnée | MEXC Spot | Kraken Spot | MEXC perpétuel | Kraken Futures |
|---|---|---|---|---|
| Dernier prix | `ticker/price` `price` (chaîne) **[DOC]**, sans heure ; `ticker/24hr` `lastPrice` | REST Ticker `c[0]` (chaîne) **[DOC]**, sans heure ; WS v2 `last` (« only guaranteed if traded within the past 24 hours ») | `ticker` `lastPrice` (décimal) | `last` + `lastTime` (heure du **dernier fill**, ISO) |
| Meilleur bid/ask | `ticker/bookTicker` : prix et quantités (chaînes), **sans heure** | REST Ticker `a`/`b` : `[prix, lot entier, volume du lot]`, sans heure ; WS `bid`/`ask` + `*_qty` | `ticker` `bid1`/`ask1` **sans tailles** ; tailles seulement dans la profondeur (en contrats) | `bid`/`ask` + `bidSize`/`askSize` (unité de taille **[PARTIEL]**) |
| Profondeur | `depth` : `lastUpdateId`, `[prix, quantité]`, limite 5000, **sans heure** | REST Depth non relu ; WS `book` couvert par #BBO | `depth` : `[prix, contrats, nb ordres]`, `version`, `timestamp` (« system timestamp ») | REST orderbook **[NON LU]** ; WS `book` : `seq`, `timestamp` ms, `qty` |
| Prix de marque | **[ABSENT]** | **[ABSENT]** | `fairPrice` (ticker, `fair_price`) ; `priceCoefficientVariation` | `markPrice` (« price to which Kraken Futures currently marks the Futures for margining ») |
| Prix d'indice | **[ABSENT]** | **[ABSENT]** | `indexPrice` (ticker, `index_price`) ; composition dans `contract/detail.indexOrigin` (exemple : Binance, GATEIO, HUOBI, MXC) | `indexPrice` (champ requis des tickers marché) ; WS `index` (« real time index ») |
| Prime publiée par la plateforme | — | — | **[NON DOC]** | WS `premium` : « percentage difference between the futures price and the index price » (**[PARTIEL]** : de quel prix, en % ou en fraction) |

## 4. Funding et open interest

| Donnée | MEXC perpétuel | Kraken Futures (perpétuels `tag=perpetual`) |
|---|---|---|
| Taux | `fundingRate` (décimal), `maxFundingRate`, `minFundingRate` | `fundingRate` = taux **absolu** ; `relativeFundingRate` = taux **relatif** « when available » ; leurs prédictions « can be highly inaccurate » ; WS : champ « not populated » si zéro |
| Intervalle | `collectCycle` (entier, « charge cycle ») : exemple `8`, **unité non écrite** → UNRESOLVED (heures probables) | **[NON DOC]** dans les tickers. L'historique donne `timestamp` = « Start of the period », espacés de 4 h **dans l'exemple seulement** → UNRESOLVED |
| Prochaine échéance | `nextSettleTime` (ms) | WS `next_funding_rate_time` : « time until next funding rate in milliseconds » (durée restante, pas un instant) ; REST tickers : **[NON DOC]** |
| Historique | `funding_rate/history` (pagination) | `GET /historical-funding-rates` : `fundingRate`, `relativeFundingRate`, `timestamp` |
| Open interest | `holdVol` (« total holdings ») : ticker REST et WS ; **unité non écrite** (contrats ? `contractSize` 0,0001 dans l'exemple BTC) | `openInterest` (« current open interest of the market ») : REST et WS ; **unité non écrite** ; plafond `maxOpenInterestUsd` en USD dans `instruments` |
| Taille de contrat | `contract/detail.contractSize` (« contract value » ; **unité non écrite**), `priceUnit`, `volUnit`, `state` (0 actif, 1 livraison, 2 terminé, 3 hors ligne, 4 pause) | `instruments.contractSize` (« contract size » ; unité non écrite), `tickSize`, `type` (`flexible_futures`, `futures_inverse`, `futures_vanilla`), `base`, `quote`, `suspended`, `isExpired` |
| Linéaire / inverse | `quoteCoin`/`settleCoin` distincts de la base : USDT pour `BTC_USDT` → **linéaire** | `futures_inverse` = inverse ; `flexible_futures` et `futures_vanilla` listés sans définition de marge ni de règlement (lien avec les marchés « multi-collatéral » non écrit) **[PARTIEL]** |

## 5. Heures : ce que chaque champ date

La règle du dépôt exige une heure **d'exchange qualifiée** ; une heure de réception ne la remplace
jamais. « Qualifiable » signifie : la documentation définit l'événement daté.

| Flux | Champ d'heure | Définition par la doc | Verdict |
|---|---|---|---|
| MEXC Spot `ticker/24hr` | `closeTime` ms | « Close time » | PARTIEL : dernier événement de la fenêtre, pas l'heure du carnet |
| MEXC Spot `bookTicker`, `depth` | aucun | — | **Pas de date de carnet** (cohérent avec #536) |
| MEXC Spot WS `aggre.deals` | `time` (trade) et `sendtime` | « Trade time » / « Event time » | `time` qualifiable pour une transaction ; `sendtime` = envoi |
| MEXC Spot `trades`/`aggTrades` | `time` / `T` ms | « Trade time » / « Timestamp » | qualifiable (ms) |
| Kraken Spot REST Ticker | aucun | — | pas de date |
| Kraken Spot REST Trades | 3ᵉ élément, **secondes à décimales** | non défini dans la description | PARTIEL ; précision sub-ms à tronquer explicitement |
| Kraken Spot WS v2 `ticker` | `timestamp` RFC3339 µs | « The ticker data timestamp » | qualifiable comme publication de ticker |
| Kraken Spot WS v2 `trade` | `timestamp` RFC3339 µs | libellé « The book order update timestamp » (**formulation ambiguë** pour une transaction) | PARTIEL |
| MEXC perpétuel `ticker`/`index_price`/`fair_price`/`funding_rate` | `timestamp` ms | « transaction timestamp » (ticker), « system timestamp » (autres) | UNRESOLVED : un champ vague, pas une heure de calcul définie |
| MEXC perpétuel `depth` | `timestamp` + `version` | « system timestamp » | PARTIEL (version utilisable pour la continuité) |
| MEXC perpétuel `deals` / WS `push.deal` | `t` ms | « transaction time » | qualifiable |
| Kraken Futures REST `tickers` | `lastTime` (dernier fill) ; `serverTime` de la **réponse** | « date and time at which `last` was observed » / « Server time » | **Aucune heure propre à mark, index, funding, OI** : seule l'heure de réponse |
| Kraken Futures WS `ticker` | `time` ms | « The UTC time of the server in milliseconds » | publication de ticker qualifiable (toutes les valeurs du message ; messages différentiels toutes les 1 s) |
| Kraken Futures `history` / WS `trade` | `time` ISO / ms | « date and time of a trade » / « UTC … time of the trade » | qualifiable ; `sequence_id` et `uid` pour la continuité |
| Kraken Futures WS `book` | `timestamp` ms + `seq` | « Timestamp in milliseconds » | qualifiable |

## 6. Transactions : pour le flux et la périodicité

| | MEXC Spot | Kraken Spot | MEXC perpétuel | Kraken Futures |
|---|---|---|---|---|
| Source | REST `trades` (max 1000, poids 5), `aggTrades` (1000, startTime/endTime) ; WS `aggre.deals` protobuf | REST `Trades` (1000 par défaut, `since`) ; WS v2 `trade` (snapshot de 50) | REST `deals` (max 100) ; WS `push.deal` | REST `history` (100 dernières, 7 jours) ; WS `trade` |
| Heure | ms | secondes à décimales (REST), RFC3339 µs (WS) | ms | ISO (REST), ms (WS) |
| Quantité | `qty` chaîne, base **[DOC]** | `volume`/`qty`, base | `v` « quantity » : **contrats** probable, **non écrit** | `size`/`qty` : unité **[PARTIEL]** |
| Côté | `isBuyerMaker` / `m` : « Was the buyer the maker ? » → côté preneur dérivable **[DOC]** ; WS `tradetype` 1 achat / 2 vente, **non défini comme preneur** | REST `b`/`s` : **non défini comme preneur** ; WS : « The side of the taker order » **[DOC]** | `T` 1 achat / 2 vente : « deal type », **non défini comme preneur** ; `O` ouverture/fermeture, `M` auto-transaction | `side` : « classification of the taker side » **[DOC]** (+ `type` : fill, liquidation, unwind…) |
| Identité | `id` peut être `null` dans l'exemple | `trade_id` | aucun identifiant | `trade_id`, `sequence_id` (chaîne, `uid`) |

## 7. Quelles comparaisons sont valides

| Comparaison | Verdict | Raison et condition de levée |
|---|---|---|
| Spot MEXC BTC/USDT ↔ Spot Kraken BTC/USDT | **VALIDE, déjà couvert** | même cote ; la fraîcheur repose sur la continuité de carnet (#BBO), pas sur une heure source (aucune des deux REST n'en a) |
| Perpétuel MEXC `BTC_USDT` ↔ Spot MEXC `BTCUSDT` (base) | **VALIDE SOUS CONDITION** | même cote USDT. Condition : fixer ce que vaut la date de `fairPrice` (UNRESOLVED) ; ne pas lire la base contre l'**indice**, composé d'autres plateformes |
| Prime (marque − indice) MEXC | **VALIDE SOUS CONDITION** | `fairPrice` et `indexPrice` arrivent dans le **même** ticker : une seule date, mais son sens est vague (« transaction timestamp ») |
| Perpétuel Kraken Futures ↔ Spot Kraken **BTC/USDT** | **BLOQUÉ** | dérivé coté **USD**, spot suivi coté **USDT** : le dépôt ne fusionne jamais USD et USDT. Levée : ajouter Kraken spot **BTC/USD** comme jambe de référence (non suivie aujourd'hui) |
| Kraken Futures ↔ MEXC perpétuel (écart de prix) | **BLOQUÉ (structurel)** | cotes USD et USDT, indices distincts ; le catalogue Kraken ne contient **aucun** contrat USDT (218 instruments, tous USD). Levée : décision explicite sur le traitement de la base USD/USDT (hors périmètre de l'interface) |
| Funding MEXC ↔ Kraken (équivalent 8 h) | **BLOQUÉ** | intervalle Kraken **[NON DOC]** ; `collectCycle` sans unité ; taux absolu vs relatif. Le builder exige un intervalle entier explicite et refuse sinon (`FUNDING_INTERVAL_UNKNOWN`) : correct, pas à contourner. Levée : intervalle attesté + usage du taux **relatif** |
| Open interest MEXC ↔ Kraken, total multi-plateformes | **BLOQUÉ** | unités non écrites des deux côtés (contrats, base ou cote ?). Le total n'est publié qu'en couverture complète ; sans unité exacte, aucune somme. Levée : unité attestée + `contractSize` d'unité attestée |
| Variations prix/OI sur 1 h, 4 h, 24 h | **POSSIBLE APRÈS CAPTURE** | aucune API documentée ici ne donne l'historique d'OI ; il faut des échantillons capturés par le producteur (mêmes nature de prix et unité d'OI) |
| Périodicité aux quarts d'heure, Kraken Futures et MEXC perpétuel | **VALIDE SOUS CONDITION** | heure de transaction documentée (ms). Condition : attester que cette heure est celle de l'appariement ; capture bornée ≥ 1 000 transactions par fenêtre |
| Périodicité Kraken Spot | **PARTIEL** | REST en secondes décimales, WS à libellé ambigu ; troncature explicite à la milliseconde à déclarer |
| CVD / côté preneur MEXC (WS, perpétuel) | **BLOQUÉ** | `T`/`tradetype` non définis comme côté preneur. Levée : REST spot `isBuyerMaker` est exploitable ; perpétuel : attestation de convention |
| Prime publiée Kraken (`premium`) contre notre calcul | **ÉCART À DOCUMENTER** | la doc ne dit pas le prix de référence, ni l'unité ; ne pas la substituer à la mesure du dépôt |

## 8. Ce que cette matrice implique pour les adaptateurs

1. **Kraken Futures : cibler le WebSocket unifié, pas `ws/v1`** (retrait annoncé le 2027-03-01). Lire sa doc avant tout décodeur.
2. **Aucun champ d'heure ne date mark / index / funding / OI** côté REST Kraken Futures : le producteur ne peut fournir que l'heure de réponse (`serverTime`) ou, en WebSocket, le `time` du message. La publication utilise `TICKER_PUBLICATION` ; il faut décider si cela suffit.
3. **Unités à attester avant le code** (OI, `contractSize`, quantités de transactions) : sinon `CONTRACT_SIZE_UNKNOWN` et notionnel indisponible, comme prévu par le builder.
4. **Intervalle de funding** : exigé par le builder ; à obtenir d'une source documentaire, jamais supposé.
5. **Ajouter la jambe Kraken spot BTC/USD** si la base Kraken Futures est souhaitée ; pour ATOM, vérifier d'abord l'existence des dérivés.

## 9. Vérifications ouvertes et leur gate

| À lever | Moyen | Autorisation requise |
|---|---|---|
| Journal et base de l'API Futures MEXC (2026), `apiAllowed` | relecture par un humain de `www.mexc.com/api-docs/futures` | aucune (lecture de page) |
| Pages Kraken non lues : limites de débit, WebSocket unifié, orderbook REST, WS `book` v2 | lecture documentaire | aucune |
| ~~Existence de `ATOM_USDT` (MEXC) et d'un dérivé ATOM (Kraken)~~ | **LEVÉ le 2026-11-20** : lecture de catalogue autorisée et réalisée ([fiches](CATALOGUE_FICHES_20261120.md)) | — |
| Unité exacte de `holdVol`, `openInterest`, `contractSize`, quantités | recoupement d'une capture bornée avec la valeur affichée par la plateforme | oui : capture bornée |
| Intervalle de funding Kraken | doc complémentaire ou capture de `fundingRate` sur plusieurs périodes | doc : non ; capture : oui |

Aucune de ces étapes n'est autorisée par ce document. Il ne modifie ni runtime, ni epoch, ni #286.

## 10. Source complémentaire Kraken pour marque, indice, funding et OI (2026-11-20)

Décision de l'opérateur : prioriser cette source avant tout code d'adaptateur. Ce chapitre sépare ce
que la documentation officielle confirme, ce que l'opérateur rapporte, et la lecture publique
proposée, **non autorisée à ce jour** (les quatre GET de catalogue déjà autorisés sont terminés).

### Ce que la documentation officielle confirme (relue le 2026-11-20)

| Besoin | Source | Constat |
|---|---|---|
| Marque, indice, OI, funding actuel | REST `GET /tickers` (`futures.kraken.com/derivatives/api/v3`) | `markPrice`, `indexPrice` et `openInterest` présents ; `fundingRate` (absolu) et `relativeFundingRate` « when available » (perpétuels) ; `lastTime` date le dernier fill ; `serverTime` date la réponse (§3-§5) |
| Historique d'OI et de funding | **`GET /analytics/{symbol}/{analytics_type}`**, base `https://futures.kraken.com/api/charts/v1` (« Market Analytics », « Analytics data divided into time buckets ») | `analytics_type` ∈ `open-interest`, `funding`, `future-basis`, `cvd`, `long-short-ratio`, `liquidation-volume`, `aggressor-differential`, `trade-volume`, `trade-count`, … ; `since` **requis**, « epoch time in seconds » ; `interval` **requis**, en secondes : 60, 300, 900, 1800, **3600, 14400, 86400**, 43200, 604800 ; `to` optionnel (« default now ») ; réponse `{timestamp[], data, more}` avec `more` = « True if there are more candles in time range » (la pagination est donc à gérer) |
| Funding historique par bucket | analytique `funding` | `data.rate` et `data.relativeRate` : séries de quadruplets **OHLC** (ouverture, plus haut, plus bas, clôture) |

### Ce que la documentation ne dit pas (à lever par la lecture proposée)

- **Unité et signification des points `open-interest`** : le schéma accepte, pour `data`, des nombres, des
  décimaux en chaîne ou des quadruplets OHLC ; la page ne précise ni lequel s'applique à `open-interest`,
  ni son unité (contrats, base, USD), ni si le point est une valeur de fin de bucket.
- **Unité des `timestamp`** de la réponse (le paramètre `since` est en secondes ; la réponse n'est pas
  décrite) et **sens de l'instant** (début ou fin de bucket).
- **Définition de `fundingRate` absolu** (unité de cote) et rapport avec `relativeFundingRate`.
- **Intervalle de funding** : voir ci-dessous.

### Rapporté par l'opérateur, non revérifié ici

- Les spécifications Kraken des perpétuels linéaires multi-collatéral indiqueraient un **règlement de funding
  horaire** et distingueraient taux relatif et absolu. Cette source (page de spécifications) n'est **pas
  lue** : elle n'est pas dans la documentation d'API et son hôte n'est pas autorisé. Tant qu'elle n'est pas
  lue, l'intervalle Kraken reste **UNRESOLVED dans la matrice** : le builder continue de refuser
  (`FUNDING_INTERVAL_UNKNOWN`) et ne reçoit jamais un 1 h supposé.
- Le comparatif de funding avec MEXC exige en plus l'unité de `collectCycle` MEXC et la présence du taux
  relatif Kraken.

Dans les catalogues déjà lus, `fundingRateCoefficient=8` figure sur `PF_XBTUSD` et `PF_ATOMUSD` ; ce champ
n'est pas défini et **ne tranche pas** l'intervalle.

### Lecture publique proposée (NON AUTORISÉE, NON EXÉCUTÉE)

Périmètre soumis à l'opérateur : GET publics, sans clé, une fois chacun, sur `PF_XBTUSD` uniquement,
réponses brutes hors dépôt avec empreintes, heure de requête UTC enregistrée.

| # | Requête | Objet |
|---|---|---|
| 1 | `GET futures.kraken.com/derivatives/api/v3/tickers?symbol=PF_XBTUSD` | instantané : `markPrice`, `indexPrice`, `fundingRate`, `relativeFundingRate`, `openInterest`, `lastTime`, `serverTime` |
| 2 | `GET futures.kraken.com/api/charts/v1/analytics/PF_XBTUSD/open-interest?since=<T−26 h>&to=<T>&interval=3600` | série d'OI couvrant ≥ 24 h au pas d'1 h |
| 3 | même route, `interval=14400` | série au pas de 4 h, pour recouper les fenêtres 4 h et 24 h |

Options à inclure **seulement sur demande explicite** : `analytics/PF_XBTUSD/funding?interval=3600` et
`GET …/historical-funding-rates?symbol=PF_XBTUSD`, qui montreraient empiriquement la période de funding.
Aucune requête sur ATOM, aucun autre produit, aucun polling.

**Critère d'acceptation** (celui de l'opérateur) : pouvoir rattacher chaque valeur à son instrument, à son
unité et à un horodatage dont le sens est explicite. Contrôles prévus : (a) le dernier point de la série
d'OI se recoupe avec `openInterest` du ticker (même unité, écart borné) ; (b) l'ordre de grandeur
`openInterest × contractSize × markPrice` est comparé à une valeur indépendante si une est documentée,
sinon l'unité reste UNRESOLVED ; (c) les `timestamp` sont ramenés à une heure UTC avec un sens écrit
(début ou fin de bucket) établi par recoupement avec `since`, `interval` et l'heure de requête ; (d) la
pagination (`more`) est observée sur la fenêtre demandée.

Cette lecture ne remplace ni la qualification d'heure ni la revue de binding ; elle ne modifie ni
runtime, ni epoch, ni #286.
