# Fiches de catalogue MEXC et Kraken — BTC et ATOM (2026-11-20)

Suite de la [matrice des formats natifs](NATIVE_FORMAT_MATRIX.md). Lecture ponctuelle de
**catalogues publics**, autorisée par l'opérateur le 2026-11-20 pour ce périmètre exact :
quatre requêtes GET sans clé, une fois chacune, aucun endpoint de cotation ni de transactions,
aucune publication. Statut : `SOURCE_ONLY / DOCUMENTAIRE / NON_DEPLOYED`.
Valeurs exactes dans [`catalogue_sheets_20261120.json`](catalogue_sheets_20261120.json).
Une fiche de catalogue n'est ni une certification de mapping, ni une cotation, ni une preuve runtime.

## Provenance

| Source | Requête (UTC) | HTTP | Octets | SHA-256 de la réponse |
|---|---|---|---|---|
| MEXC Futures `GET api.mexc.com/api/v1/contract/detail` | 21:25:02 | 200 | 2 277 760 (1 170 contrats) | `f676de48e2b83240e9a76c48a02d5f16caa39c79afcebafab9ad104d422a5ee9` |
| MEXC Spot `GET api.mexc.com/api/v3/exchangeInfo?symbols=BTCUSDT,ATOMUSDT` | 21:25:02 | 200 | 1 661 | `3db48f71d54edc73b32c65456cb27a4ec177ef742b827b23a296d3e8b23c9747` |
| Kraken Spot `GET api.kraken.com/0/public/AssetPairs?pair=XBTUSDT,ATOMUSDT` | 21:25:00 | 200 | 1 012 | `3236a8d797c512243a1154d9bf542902610ddb2455c88063acb055d4bad2f9c9` |
| Kraken Futures `GET futures.kraken.com/derivatives/api/v3/instruments` | 21:25:01 | 200 | 822 105 (218 instruments) | `c5c58723cbc6976aded3e85bd076806dcd23a396390873709fa9eb93ea182eb8` |

Les réponses brutes et leurs en-têtes sont conservées **hors dépôt** (répertoire de travail de la
session, éphémère) ; seules les empreintes ci-dessus et les champs extraits sont versionnés. Une
relecture identique n'est pas garantie : un catalogue évolue.

## Fiches par contrat

| Plateforme · produit | Symbole natif | Base / cote / règlement | Statut | Taille de contrat et pas |
|---|---|---|---|---|
| MEXC · perpétuel BTC | `BTC_USDT` (« BTC_USDT PERPETUAL ») | BTC / USDT / USDT | `state=0` (actif), `apiAllowed=true` | `contractSize=0.0001`, `priceUnit=0.1`, `volUnit=1`, `minVol=1`, `maxVol=400000` |
| MEXC · perpétuel ATOM | `ATOM_USDT` (« ATOM_USDT PERPETUAL ») | ATOM / USDT / USDT | `state=0`, `apiAllowed=true` | `contractSize=0.1`, `priceUnit=0.001`, `volUnit=1`, `minVol=1`, `maxVol=5000000` |
| MEXC · spot BTC | `BTCUSDT` | BTC / USDT | `status="1"`, `isSpotTradingAllowed=true` | `baseSizePrecision="0.000001"`, `quoteAssetPrecision=2` |
| MEXC · spot ATOM | `ATOMUSDT` | ATOM / USDT | `status="1"`, `isSpotTradingAllowed=true` | `baseSizePrecision="0.001"`, `quoteAssetPrecision=3` |
| Kraken · spot BTC | clé `XBTUSDT`, altname `XBTUSDT`, wsname `XBT/USDT` | `XXBT` / `USDT` | `online` | `tick_size="0.1"`, `lot_decimals=8`, `ordermin="0.00006"`, `costmin="0.5"` |
| Kraken · spot ATOM | clé `ATOMUSDT`, wsname `ATOM/USDT` | `ATOM` / `USDT` | `online` | `tick_size="0.0001"`, `lot_decimals=8`, `ordermin="3.5"`, `costmin="0.5"` |
| Kraken · perpétuel BTC | `PF_XBTUSD`, type `flexible_futures` | `BTC` / `USD` (`pair=BTC:USD`) | `tradeable=true`, `suspended=false`, `isExpired=false` | `contractSize=1`, `tickSize=1`, `contractValueTradePrecision=4`, `maxPositionSize=1200` |
| Kraken · perpétuel ATOM | `PF_ATOMUSD`, type `flexible_futures` | `ATOM` / `USD` (`pair=ATOM:USD`) | `tradeable=true`, `suspended=false`, `isExpired=false` | `contractSize=1`, `tickSize=0.001`, `contractValueTradePrecision=1`, `maxPositionSize=1200000` |

Champs de funding du catalogue Kraken (perpétuels BTC et ATOM identiques) : `maxRelativeFundingRate=0.005`,
`fundingRateCoefficient=8`, `minRelativeFundingRate` absent. Le sens de `fundingRateCoefficient` **n'est
pas documenté** : ne pas en déduire un intervalle de funding.

## Ce que ces fiches établissent

1. **`ATOM_USDT` existe sur MEXC Futures**, linéaire coté et réglé en USDT, actif. Le dérivé ATOM de Kraken existe aussi (`PF_ATOMUSD`).
2. **`api.mexc.com` sert bien le catalogue Futures** (HTTP 200, 1 170 contrats). C'est un fait d'accès constaté à cet instant ; la **documentation** officielle du changement de domaine reste à relire (`www.mexc.com` refuse les clients automatisés).
3. **`apiAllowed=true`** pour `BTC_USDT` et `ATOM_USDT` (1 165 contrats sur 1 170 ; 5 à `false`). L'exemple du miroir de documentation (`false`) est donc périmé pour BTC.
4. **Kraken Futures ne propose aucun contrat coté en USDT** : les 218 instruments sont cotés en USD, tous de type `flexible_futures` (aucun inverse `futures_inverse` listé). Le blocage USD/USDT de la matrice (§7) est donc **structurel**, pas temporaire : mesurer une base Kraken exige un spot **USD**.
5. **Pas de valeur de calendrier BTC** à ignorer : `FF_XBTUSD_261127`, `261225`, `270326` et `270625` sont listés (échéances datées, non traitées dans le premier lot).
6. **Ordre de grandeur des contrats MEXC** : un contrat vaut 0,0001 BTC et 0,1 ATOM. Pour Kraken, `contractSize=1` avec une précision de trade de 4 décimales sur BTC est **cohérent avec** une taille exprimée en BTC, sans que la documentation l'atteste.

## Ce qu'elles n'établissent pas

- **Aucune unité d'open interest** : ni `holdVol` (MEXC) ni `openInterest` (Kraken) ne sont dans un catalogue. Le notionnel reste indisponible tant qu'une unité n'est pas attestée.
- **Aucun intervalle de funding** pour Kraken, et `collectCycle` MEXC n'est pas dans le catalogue.
- Les codes MEXC `futureType=1` et `type=1`/`2` ne sont pas définis par la documentation lue ; les deux perpétuels portent `futureType=1`, `type=1`.
- `indexOrigin` (MEXC) montre un indice **composite de plusieurs plateformes** (BITGET, BYBIT, BINANCE, HTX, OKX, MEXC, KUCOIN, plus UPBIT pour BTC), distinct du spot MEXC : une prime contre l'indice n'est pas une base contre le spot MEXC.
- Les noms de symboles ne valent pas mapping revu : une liaison reste une déclaration à qualifier.

## Effet sur le plan d'intégration

Premier test de bout en bout confirmé comme **MEXC `BTC_USDT` perpétuel ↔ MEXC `BTCUSDT` spot** : même cote USDT, les deux contrats actifs et ouverts à l'API. Les décisions de l'opérateur rapportées le 2026-11-20 sont retenues telles quelles pour le plan :
`api.mexc.com` comme domaine Futures, WebSocket unifié Kraken pour les transactions, source complémentaire à identifier pour marque, indice, funding et OI Kraken. Elles n'ont pas été revérifiées ici, à l'exception de l'accès au catalogue ci-dessus.
