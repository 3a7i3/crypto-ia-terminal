# MARKET-MULTI-VENUE-01 — préparation de la comparaison de cotations

Mission #535, suite de #533 / PR #534.
Statut : **SOURCE_ONLY / OFFLINE / NON_DEPLOYED**.
Le [registre de 25 candidats](../research/market_multi_venue_01/venue_candidates.json)
est un document de conception, pas une configuration de collecte.

## 1. Résultat recherché et frontière

Comparer des observations de prix de plusieurs plateformes avec leurs dates,
instruments et limites. Ne pas fusionner les scores CryptoRadar avec ces
cotations, ni produire une recommandation d’exécution.

Trois mesures sont distinctes, en points de base (1 bp = 0,01 %) :

| Mesure | Définition pour une référence A et une autre venue B |
| --- | --- |
| Spread interne A | `(ask_A - bid_A) / mid_A × 10000` |
| Écart des milieux | `(mid_B - mid_A) / mid_A × 10000` |
| Écart brut achat A / vente B | `(bid_B - ask_A) / ask_A × 10000` |

`mid=(bid+ask)/2`. La direction inverse a son propre dénominateur.
Un écart brut positif n’établit pas un bénéfice : frais, profondeur exécutable,
latence, funding, transferts et conversions ne sont pas intégrés ici.
La quantité au meilleur prix n’est pas la profondeur totale du carnet.

## 2. Ce que le catalogue historique permet

La capture v1.0 de 20 lignes ne contient ni venue native, ni contrat, ni bid/ask.
Les 8 825 paquets récupérés des 28/29 octobre comportent des symboles et des
scores, sans identifiant d’exchange reconnu. La venue et le type de marché
restent **UNRESOLVED**.

La source actuelle prévoit MEXC par défaut, mais le code du producteur historique
et ses paramètres ne sont pas attestés par cette archive. Une configuration
par défaut n’est pas une preuve de provenance de chaque paquet.
Le frontend indique donc explicitement la plateforme et le type non attestés.

Le catalogue v1.1 candidat peut être préparé en lecture seule, à l’ancre
historique `2026-10-29T05:32:36Z`. Il ne peut fournir ni un spread historique
fiable, ni des prix actuels, ni les comparaisons de cette spécification.

## 3. Sélection progressive, sans classement mondial inventé

Première tranche documentaire : MEXC, Bybit, OKX, Kraken, Bitfinex, KuCoin,
Coinbase Exchange et Hyperliquid. Ces huit sources ont une documentation
officielle examinée ; **aucun adaptateur réseau ni collecteur n’est démarré
ou déclaré implémenté** dans le registre.

Extension candidate : Binance, Bitget, Gate, Crypto.com, Bitstamp, Gemini,
HTX, Upbit, Bithumb, BitMart, WhiteBIT, Poloniex, LBank, Phemex, Deribit,
dYdX et OpenSea. Couverture, accès, restrictions, schémas, coûts et cadences
restent à examiner pour cette deuxième tranche. Les 25 noms ne constituent
pas un classement des « 25 plus gros » attesté à une date de marché.

L’ordre d’admission sera fondé sur couverture utile des symboles, métadonnées
d’instrument, qualité temporelle, profondeur, stabilité et coût mesuré.
Ajouter des plateformes n’améliore pas automatiquement la précision d’un spread.

## 4. Particularités documentées du pilote

| Plateforme | Source officielle | Conséquence de normalisation |
| --- | --- | --- |
| MEXC | [Spot API](https://mexcdevelop.github.io/apidocs/spot_v3_en/#order-book) | Conserver le produit et la venue ; ne pas inventer un timestamp de carnet absent d’une réponse |
| Bybit | [Orderbook V5](https://bybit-exchange.github.io/docs/v5/market/orderbook) | Spot/linéaire/inverse distincts ; `cts` moteur et `ts` publication distincts ; RPI non inclus dans ce flux |
| OKX | [API V5](https://www.okx.com/docs-v5/en/), [guide](https://www.okx.com/docs-v5/trick_en/) | `instId`, type et canal de carnet explicites ; couverture RPI/ELP documentée par canal |
| Kraken | [Book v2](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/book) | Snapshot/deltas, checksum et devises natives conservés |
| Bitfinex | [Public Book](https://docs.bitfinex.com/reference/rest-public-book) | Signe des tailles des carnets trading ; ne pas utiliser les conventions des carnets funding |
| KuCoin | [Ticker Spot](https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-ticker) | BBO, temps et séquence ; Spot/Futures/UTA ne sont pas interchangeables |
| Coinbase Exchange | [Product Book](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-book) | Identité produit, niveau/séquence ; le timestamp d’un dernier trade n’est pas celui du carnet |
| Hyperliquid | [Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) | Spot/perp et indices natifs via métadonnées ; les alias UI peuvent désigner UBTC ; `allMids` peut retomber sur un dernier trade si le carnet est vide |

Ces documents décrivent des interfaces, pas un test réseau effectué depuis la VM.
Aucun exemple de clé ou d’ordre n’est exécuté.

[OpenSea](https://docs.opensea.io/reference/api-overview) expose aussi des tokens
et des devis de swap, en plus des NFT. Son accès requiert une clé d’après
l’aperçu examiné. Il sera étudié séparément avec chaîne, adresse du token,
montant, route, frais/gas et slippage ; un devis de swap et un floor NFT ne sont
pas assimilés au BBO d’un carnet BTC/USDT. Aucune clé n’est créée ou lue.

## 5. Identité minimale d’une cotation normalisée

`Quote` contient venue canonique, symbole natif, bid/ask décimaux exacts,
tailles normalisées en unité de base si connues, heure exchange, heure de
réception, identité de l’horloge observatrice, sémantique du timestamp et état
du carnet. Pas de substitution par `last`, mark, index ou heure de lecture.

`InstrumentKey` exige des identifiants d’actifs canoniques, la devise de
cotation, le type de marché, la devise de règlement et l’identité du contrat.
Cette dernière couvre échéance, linéarité/inversion, multiplicateur et convention
de prix lorsque pertinents. Un mapping source revu lie le symbole natif à cette
identité ; le prototype ne découvre ni ne certifie ce mapping.

- BTC/USD, BTC/USDT et BTC/USDC ne sont pas comparés sans conversion attestée.
- Spot, perpétuel, inverse et échéances distinctes restent séparés.
- BTC natif, tokens enveloppés et alias UI ne sont pas fusionnés par leur libellé.
- Les nombres reçus en JSON doivent être décodés en Decimal avant perte
  de précision ; les floats binaires ne sont pas acceptés comme cotations exactes.

## 6. Qualité et états du prototype offline

`observability/venue_quote_comparison.py` ne fait aucun I/O réseau ou fichier.
Il mesure uniquement des cotations normalisées explicitement fournies.

Les limites d’âge et d’écart temporel doivent être passées en millisecondes ;
elles sont des critères de qualité des données, sans seuil de trading implicite.
La même horloge observatrice et la même sémantique de timestamp sont exigées.
Une heure exchange absente, future, antérieure non comparable, un carnet
désynchronisé/croisé ou un instrument inconnu rendent la comparaison indisponible.

Une absence reste null/NOT_AVAILABLE avec sa raison, jamais zéro.
Un vrai carnet verrouillé bid=ask donne un spread nul.
Les tailles inconnues restent null, même si les prix permettent une comparaison.
Les sorties conservent les métriques de chaque source, l’écart temporel, les
unités et `execution_authority=false`. Aucun rang ou score CryptoRadar ne change.

## 7. Architecture cible et gates

Flux futur : collecteur public dédié → observations immuables et mapping
d’instruments → contrôle qualité/comparaison → publication → API GET → app.
L’API opérateur n’appelle pas les exchanges ; son confinement actuel reste
bouclé sur localhost. Le frontend ne lit ni exchange ni JSONL et ne recalcule
pas le classement.

Avant admission d’une venue :
1. vérifier produits, accès régional, conditions de données et limites actuelles ;
2. valider mapping, unités, bid/ask, tailles, timestamps et séquences/checksums ;
3. borner débit et stockage, prévoir reconnexion/backoff et trous visibles ;
4. mesurer CPU/RAM/réseau/disque par source sous une mission séparée ;
5. prouver frais/couverture/latence pertinents avant une interprétation économique ;
6. obtenir une décision d’activation distincte, avec procédures et rollback.

La VM n’est pas déclarée capable d’absorber 25 ou 50 flux sans ce test.
Aucun collecteur, service, clé, port, alerte, compte ou stratégie n’est activé
par le registre, le prototype, la CI ou une fusion source.
