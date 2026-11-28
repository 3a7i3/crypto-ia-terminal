# MEO-01 — Capture bornée des transactions Kraken Spot BTC/USDT (protocole)

Statut : **source seulement, SYNTHETIC.** Ce document décrit le protocole du lot
L1. La capture réelle (L2) exige un GO opérateur séparé. Rien ici n'autorise une
connexion, un déploiement, une modification runtime ou une mutation d'expérience
gelée (#286 actif).

Plan accepté : `CAT_MEO_01_PLAN_RACCORDEMENT_TRANSACTIONS.md`
(SHA-256 `6a065be84a63fa32105fab5ae2352cf20e33e3ca223304a3718cd30d586abea9`),
décisions D1–D7 du 2026-11-28.

## Périmètre

- Une venue, un instrument : Kraken Spot, symbole WebSocket `BTC/USDT`
  (paire REST `XBTUSDT`, actif de base `XXBT`, alias `XBT`, cotation `USDT`).
- Un seul canal public : `trade` de `wss://ws.kraken.com/v2`, avec `snapshot=true`.
  Aucun canal privé, aucune clé, aucun jeton, aucun ordre.
- Le carnet n'est pas capturé : l'acquis B03 (`BOOK_AT_RECEIPT`, 29 557 observations)
  n'est ni répété ni modifié.

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `observability/market_flow/kraken_trades.py` | Pur : lecture JSON à littéraux préservés, décodeur des trames `trade`, convention TAKER, couverture, rejeu du journal, contrôle croisé REST. Aucun réseau, horloge, fichier ou flottant. |
| `observability/radar_composite/kraken_trade_pilot.py` | Capture bornée. Réutilise `bbo_wire`, `bbo_pilot` (connexion, journal, chien de garde) et le préflight d'identité L3. `dry-run` sans réseau ; `run` verrouillé. |
| `observability/meo_trades_replay.py` | CLI opérateur : `verify` et `replay` d'un dossier scellé vers un fichier nouveau. |
| `tests/meo_01/` | Tests T1–T11 (SYNTHETIC, hors réseau). |

`observability/market_flow/trades.py` est réutilisé **sans modification**
(empreinte épinglée par un test). `artifact.py`, `contract.py`, l'Operator API et
la route `market-flow` ne changent pas.

## Deux axes de temps, jamais confondus

| Axe | Origine | Qualification |
| --- | --- | --- |
| Temps natif | champ `timestamp` RFC 3339 (µs) de chaque transaction | `NATIVE_UNQUALIFIED` : la documentation le décrit comme « book order update timestamp » ; son sens exact n'est pas attesté. Les barres sont rangées sur cet axe. |
| Réception | horloge UTC de l'hôte, en ns (`recv_wall_ns`) + horloge monotone (`recv_mono_ns`) | `HOST_UTC_RECEIPT` : bornée seulement par l'écart mesuré avec `GET /0/public/Time` (résolution 1 s, tolérance 2 000 ms) au début et à la fin. |

Aucun ordre fin n'est déduit d'un temps. L'ordre fournisseur est celui des
`trade_id` (hypothèse H2/H5).

La relation entre temps natif et réception **n'est pas démontrée**
(`native_to_receipt_relation = NOT_DEMONSTRATED`). Toute comparaison entre les
deux axes reste conditionnelle (`CONDITIONAL_ON_UNPROVEN_NATIVE_UTC_ALIGNMENT`) :
l'exclusion `future_event_time` de `trades.build_bars`, le choix de la fenêtre de
sortie (après l'abonnement, dans un intervalle de transport) et l'écart
descriptif réception − natif. Aucune ne prouve un alignement UTC.

## Continuité du transport ≠ couverture des transactions

- **Continuité du transport** (axe réception) : commence à l'accusé d'abonnement
  réussi avec écho `trade`/`BTC/USDT` ; chaque trame reçue atteste `[r, r + 2 000 ms)` ;
  se termine à la fermeture, à l'erreur, à l'arrêt ou à la borne `as_of`. C'est un
  diagnostic : il ne prouve pas qu'aucune transaction ne manque.
- **Couverture effective des transactions** (axe natif) : dérivée uniquement des
  `trade_id` acceptés et contigus (+1) dont le temps natif ne décroît pas. Une suite
  contiguë de A à Z couvre `[t(A) + 1 ns, t(Z))`. Toute lacune d'identifiant,
  transaction refusée, conflit, temps absent ou postérieur à la réception, ou
  inversion de temps coupe la couverture. La queue après la dernière transaction
  n'est jamais couverte. **Ambiguïté (MEO-L1-RV01)** : une inversion (identifiant
  k+1 plus ancien que k) rend `[t(k+1), t(k)]` ambigu ; une transaction d'une autre
  suite située dans l'intervalle d'une suite le rend ambigu du côté contredit ; un
  temps revendiqué par deux suites est ambigu. Le temps ambigu est retiré de la
  couverture : une fenêtre qui le touche n'est jamais entièrement couverte. Cas de
  régression : identifiants 1, 2, 3, 4 aux temps 0, 600, 100, 400 s → ambigu
  `[100 s, 600 s]`. Sans suite contiguë, la couverture vaut `UNKNOWN` :
  une couverture inconnue n'est jamais présentée comme complète, et une barre non
  couverte vaut `NOT_COVERED`, jamais zéro.

## Budget de la capture (L2)

| Poste | Valeur |
| --- | --- |
| Observation | 15 min après l'ouverture de la connexion |
| Plafond dur (chien de garde) | 1 080 s |
| WebSocket | 1 connexion, 0 reconnexion ; une coupure arrête la capture |
| REST | `Time` ×2, `AssetPairs` ×1, `Assets` ×1, `Trades` ×3 au plus (contrôle croisé) |
| Stockage | 20 Mio (`frames.bin` + `events.jsonl` + `manifest.json`) |
| Trames | 50 000 au plus |

Verrou : `run` exige `--confirm-public-collection MEO01-TRADES` et
`--code-sha256` égal à l'empreinte calculée du code de capture.

## Hypothèses pré-enregistrées

Statuts possibles : `CONFIRMED_ON_CAPTURE`, `REFUTED`, `UNKNOWN`, `DOCUMENTARY`.

| # | Hypothèse | Évaluation au rejeu |
| --- | --- | --- |
| H1 | `side` est le côté du taker | Documentaire (extrait ci-dessous) ; accord avec REST rapporté à part |
| H2 | `trade_id` augmente de 1 exactement par transaction du livre | Lacunes WS confrontées aux identifiants REST |
| H3 | Sens du `timestamp` | Toujours `UNKNOWN` ; écarts réception − natif publiés |
| H4 | `price`/`qty` en décimal simple, sans exposant | Refus `DECIMAL_TEXT_REFUSED` |
| H5 | Ordre dans une trame = ordre des `trade_id` ; temps natif non décroissant avec l'identifiant | Inversions comptées |
| H6 | Écho exact du symbole `BTC/USDT` | Accusé d'abonnement et symbole de chaque transaction |
| H7 | Une ligne WS = une ligne REST (même identifiant, prix, quantité, côté) | Comparaison sur la fenêtre de sortie |

## Sortie

Rapport canonique `meo-01-trades-report/1` (JSON trié, SHA-256), sans verdict
d'admission (MEO-02) ni lecture scientifique (MEO-03). Fenêtres de 5 min alignées
UTC sur l'axe natif, barres de 60 s produites par `trades.build_bars`, delta borné
par `trades.rolling_delta`. La fenêtre de sortie est la première fenêtre
entièrement couverte par des identifiants contigus, commençant après l'accusé
d'abonnement et comprise dans un seul intervalle de continuité du transport.
Une fenêtre couverte seulement grâce au snapshot (transactions antérieures à
l'abonnement) reste publiée mais ne sert pas de sortie. Les données brutes ne
sont jamais commitées (D6).

## Extrait documentaire Kraken (évidence de la convention TAKER)

Source : `https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/trade.md`,
lue le 2026-11-28 (UTC). L'empreinte ci-dessous porte sur le texte compris entre
les deux marqueurs, à l'octet près ; elle est recopiée dans
`kraken_trades.EVIDENCE_EXCERPT_SHA256` et vérifiée par un test.

<!-- KRAKEN-EXCERPT-BEGIN -->
source: https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/trade.md
read_utc: 2026-11-28
channel: "The `trade` channel generates a trade event when orders are matched in the book."
batching: "Multiple trades may be batched in a single message but that does not mean that these trades resulted from a single taker order."
subscribe.snapshot: boolean, default false, "Request a snapshot after subscribing."
snapshot: "The snapshot reflects the most recent 50 trades."
schema: "The snapshot and update responses share the same schema. An update message is streamed on a trade event."
data.side: "The side of the taker order." values "buy", "sell"
data.ord_type: "The order type of the taker order." values "limit", "market"
data.qty: float, "Size of the trade."
data.price: float, "Average price of the trade."
data.trade_id: integer, "Trade identifier is a sequence number, unique per book."
data.timestamp: string, "Format: RFC3339", example "2022-12-25T09:30:59.123456Z", "The book order update timestamp."
<!-- KRAKEN-EXCERPT-END -->
