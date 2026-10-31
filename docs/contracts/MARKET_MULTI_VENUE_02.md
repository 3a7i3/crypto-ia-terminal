# MARKET-MULTI-VENUE-02 — snapshots offline et comparaison dans Marché

Mission [#536](https://github.com/3a7i3/crypto-ia-terminal/issues/536), suite de [MARKET-MULTI-VENUE-01](MARKET_MULTI_VENUE_01.md).
Statut de cette tranche : **SOURCE_ONLY / OFFLINE / NON_DEPLOYED**.
Revue documentaire : 31 octobre 2026, America/Mexico_City.
Le registre des 25 candidats reste documentaire : aucun classement mondial ni connexion n’est attesté.

## Placement et parcours dans l’app

**Marché → Scanner | Comparaison des plateformes**. Le scanner reste l’onglet initial.
Le second onglet monte son propre lecteur ; une source CryptoRadar absente ne bloque pas sa consultation.
Le navigateur ne reçoit ni JSONL, ni clé, ni accès direct à une plateforme.

1. Choisir un **instrument** et une **plateforme de référence**. BTC/USD, BTC/USDT, UBTC/USDC et les dérivés sont des groupes distincts.
2. Lire les bid/ask, le spread interne et l’écart des milieux déjà publiés, dans l’ordre du roster fourni. Aucun classement ni score nouveau.
3. Ouvrir le **détail source** : symbole natif, dates, qualité, horloge, endpoint logique, séquence, empreintes de réponse et de mapping, contrat et quantités disponibles.

L’interface montre les dates absentes, les raisons d’indisponibilité, les publications périmées et le caractère synthétique des exemples. « — » ne vaut jamais zéro. Les prix exacts restent des chaînes décimales ; le frontend ne recalcule pas les mesures.
Les onglets sont navigables au clavier ; le détail reçoit le focus et Échap le referme. Le tableau dispose de son propre défilement horizontal sur mobile.

## Classement des fichiers

| Emplacement | Rôle |
| --- | --- |
| `observability/market_venues/decoders.py` | Huit décodeurs purs de réponses natives déjà fournies en bytes |
| `observability/market_venues/publication.py` | Construction pure d’une publication depuis un roster explicite |
| `observability/market_venues/schema.py` | Validation fermée du contrat, sans recalcul économique |
| `observability/operator_api/venue_comparison_reader.py` | Lecture bornée d’un artifact préparé séparément |
| `frontend/src/views/MarketVenuesView.tsx` | Instruments, tableau comparatif et détails de provenance |
| `frontend/src/lib/venueComparison*.ts` | Contrat frontend et client GET-only |
| `docs/research/market_multi_venue_01/venue_candidates.json` | Registre documentaire des 25 candidats |
| `docs/research/market_multi_venue_02/` | Mode d’emploi de la préparation offline |
| `tests/market_venues/`, `tests/cross_stack/`, `frontend/src/test/` | Exemples inventés et contrôles de la chaîne réelle |

## Formats documentés, limites conservées

Les URLs suivantes servent à examiner les schémas ; aucun endpoint de cotation n’a été appelé depuis la VM pour cette tranche.

| Plateforme / format décodé | Temps et identité retenus | Source officielle |
| --- | --- | --- |
| MEXC Spot depth V3 | Symbole fourni par le contexte de requête ; `lastUpdateId` conservé ; pas de date de carnet inventée | [Spot depth](https://mexcdevelop.github.io/apidocs/spot_v3_en/#order-book) |
| Bybit V5 orderbook | Catégorie spot/linear/inverse et écho `s` vérifiés ; `ts` = génération/publication ; `cts` n’est pas substitué | [Orderbook](https://bybit-exchange.github.io/docs/v5/market/orderbook) |
| OKX V5 books | Contexte d’instrument explicite ; `ts` = génération du carnet ; `seqId` si présent | [Get order book](https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-order-book) |
| Kraken REST Depth | Clé native de réponse vérifiée, sans alias XBT/BTC implicite ; dates par niveau non transformées en date globale | [REST Depth](https://docs.kraken.com/api-reference/market-data/get-order-book) |
| Bitfinex trading book P0 | Identifiants `t…` uniquement ; signe positif bid, négatif ask ; funding et R0 refusés ; date absente | [Public Book](https://docs.bitfinex.com/reference/rest-public-book) |
| KuCoin Spot level1 | BBO `bestBid`/`bestAsk`, jamais `price` du dernier trade ; `time` conservé avec sémantique UNRESOLVED | [Get ticker](https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-ticker) |
| Coinbase Exchange L2 | Contexte produit et séquence ; `time` optionnel conservé avec sémantique UNRESOLVED ; aucune heure de trade de remplacement | [Product book](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-book) |
| Hyperliquid info l2Book | Écho `coin`, deux côtés du carnet ; `time` conservé avec sémantique UNRESOLVED ; UBTC ne devient pas BTC par alias | [Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) |

Le choix BOOK_PUBLICATION pour Bybit/OKX permet une comparaison au même niveau sémantique dans l’exemple. Il ne prouve ni synchronisation physique des horloges exchange, ni latence, ni prix exécutable. Les autres formats restent décodables mais non qualifiés pour les métriques tant que leur temps de carnet n’est pas attesté.
Les tailles dérivées peuvent être des contrats : elles restent indisponibles en unité de base dans cette tranche, sans conversion par renommage.

## Entrées et publication fermée

`Binding` impose plateforme, symbole natif, `InstrumentKey`, identifiant de mapping et SHA-256 de mapping. La requête fournie doit correspondre au binding ; Bybit exige aussi sa catégorie. Ces champs sont des **déclarations du fournisseur**, pas une certification de mapping, de custody ou d’origine par leur seule présence.
`decode_snapshot()` accepte uniquement des bytes JSON bornés à 512 000 octets, refuse les clés dupliquées/non-finies et décode en Decimal avant toute perte de précision. Les niveaux ambigus et les valeurs invalides sont refusés ; aucun transport, client réseau, ordonnanceur ou fichier brut n’est créé.

`build_publication(bindings, observations, as_of, max_age_ms, max_skew_ms, evidence_kind)` exige un roster indépendant explicite. Une source attendue absente conserve une ligne SOURCE_NOT_SUPPLIED. Doublons, changement de binding et observation étrangère sont refusés, sans reconstruire la population depuis les réponses reçues.
L’identité de groupe est une empreinte des cinq champs d’InstrumentKey. Chaque paire orientée du même groupe est publiée ; changer la référence choisit la paire déjà calculée. Maximum 1 000 lignes et 10 000 paires, avec refus plutôt que troncature.

La publication v1.0.0 MarketVenueComparison contient :

- `authority=OBSERVATIONAL_TELEMETRY`, `execution_authority=false`, `costs_funding_fx_included=false` ;
- `evidence_kind=OBSERVATION|SYNTHETIC`, date de génération, politique de qualité explicite et décompte attendu/reçu/qualifié ;
- groupes d’instrument, lignes de cotation, provenance et toutes les paires orientées ;
- bid/ask/tailles/métriques en chaînes décimales exactes, dates UTC et valeurs manquantes null ;
- `valid_until_utc`, minimum des dates de carnet qualifiées + âge maximal ; null si aucune cotation qualifiée.

Le calcul réutilise `observability/venue_quote_comparison.py` : spread interne, écart des milieux et écarts bruts directionnels, en points de base. Aucun score, seuil scientifique ou règle de trading n’est modifié.
L’âge doit être admissible ; une paire exige même instrument, même horloge observatrice, même sémantique temporelle, carnets qualifiés et écart temporel admissible. Les paramètres d’âge/skew sont obligatoires, sans défaut de trading.
Une métrique valide à la publication reste historique après expiration, avec avertissement explicite. Une date de publication récente ne rajeunit jamais une cotation ancienne.

## Boundary Operator API

GET `/api/operator/v1/venue-comparison`, `Cache-Control: no-store`.
Le lecteur est **non configuré par défaut** et retourne 503 VENUE_COMPARISON_NOT_CONFIGURED.
Un futur chemin explicite pourra être fourni via OPERATOR_VENUE_COMPARISON_PATH après sa propre admission. Aucun fichier actif ni variable du runtime n’est ajouté ici.

Le lecteur accepte au maximum 4 Mo, un fichier régulier sans lien symbolique dans sa chaîne de chemins, stable pendant la lecture. JSON/schema invalide, source absente, date future, horloge invalide ou mutation détectée produisent un diagnostic d’indisponibilité. Il ne collecte rien et ne lit aucune base/JSONL/exchange.
Il ajoute uniquement l’âge de publication et FRESH/STALE/UNRESOLVED selon valid_until ; les prix et mesures publiés ne sont pas recalculés. Le frontend valide à son tour le contrat fermé.

## Preuves et prochaine admission

Les exemples de tests sont entièrement inventés. Ils empruntent la chaîne réelle décodeur → publication → fichier de test → lecteur → route FastAPI → validateur React → vue.
La preuve navigateur intercepte les seuls GET d’artifacts et les assets du build, sans serveur HTTP ni API active ; Chromium conserve son sandbox. Les états synthétique, périmé, non résolu, 503 et invalide sont inspectés en clair/sombre, 1440/768/393 px. La CI conserve captures et checks.json pendant 14 jours.

Une prochaine tranche doit encore décider, avant toute collecte/publication : bindings natifs revus, univers indépendant, accès et restrictions par plateforme, fréquences/rate limits et coûts, horloges et signification des temps, transport snapshot/deltas et synchronisation, custody/erreurs, chemin isolé, recette puis publication et rollback bornés. Aucun abonnement payant, clé, collecte, fusion ou activation n’est autorisé par ce document.
