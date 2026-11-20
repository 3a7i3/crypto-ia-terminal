# MARKET-LAST-TRADE-COMPOSITE-01 — derniers trades MEXC + Kraken, composite M5

Mission CAT-RADAR-KRAKEN-MEXC-01, lot L1. Statut : **SOURCE_ONLY / OFFLINE / NON_DEPLOYED**.
Base auditée : `main@5420a1e308d39b13d10110145e5b6d88b34b00a4`.
Ce document n'autorise aucune collecte, aucun lecteur API, aucune vue, aucun service ni déploiement.
Le Radar reste une observation : aucun pont vers Advisor, stratégies, PAPER, PPL ou FIN.

## Pourquoi un produit distinct

`MarketVenueComparison` 1.0.0 (`/api/operator/v1/venue-comparison`, contrat #536) décrit des **carnets** :
bid/ask, mid, spread interne, `timestamp_kind` de carnet. Un dernier trade n'a ni bid ni ask.
`MarketLastTradeComposite` est donc un produit frère. Il réutilise `InstrumentKey`, la règle
d'identité de groupe (`sha256(InstrumentKey)[:24]`) et la convention de signe de `mid_basis_bps`.
Le contrat de carnet n'est pas modifié.

## Fichiers

| Emplacement | Rôle |
|---|---|
| `observability/radar_composite/m5.py`, `README.md` | Prototype v1 SYNTHETIC MEXC/OKX, conservé octet pour octet comme référence |
| `observability/radar_composite/instruments.py` | Identité Spot, bindings natifs, alias Kraken justifiés |
| `observability/radar_composite/decoders.py` | Décodeurs purs MEXC `/api/v3/trades` et Kraken `/0/public/Trades`, tentatives de lecture |
| `observability/radar_composite/coverage.py` | `MarketVenueCoverage` 1.0.0 liée à une sélection Radar datée |
| `observability/radar_composite/composite.py` | `MarketLastTradeComposite` 1.0.0, méthode `cat.last-trade.equal-weight` v1 |
| `observability/radar_composite/schema.py` | Validation fermée des deux publications |
| `tests/radar_composite/` | Entrées inventées au format natif, non-régression v1 |

## Identité et couverture

- Instrument : `(base, quote, SPOT, settlement=quote, SPOT)`. USD et USDT sont des cotations distinctes.
  Un instrument perpétuel ou à terme est refusé.
- Binding : plateforme, symbole natif demandé, clé native de réponse, preuve d'alias.
  MEXC : `BASEQUOTE`, sans alias. Kraken : `altname` de la paire et clé `AssetPairs`.
  BTC→XBT et DOGE→XDG ne sont admis qu'avec la preuve `kraken.Assets:<clé>.altname=<alias>`.
- Couverture : une ligne par symbole de la sélection, dans son ordre, sans doublon.
  Catégories : `EXACT_COMMON_PAIR`, `MAPPING_TO_VERIFY`, `MEXC_ONLY`, `KRAKEN_ONLY`,
  `NO_VENUE_LISTED`, `SOURCE_UNAVAILABLE`. Les totaux couvrent exactement la sélection.
- Un catalogue absent, illisible, mal formé ou en erreur donne `SOURCE_UNAVAILABLE` :
  ce n'est jamais une absence confirmée et aucune ligne ne disparaît.
- Les revues d'identité sont des entrées explicites (ex. `BCH: MEXC_NAME_BITCOIN_CASH_NODE_UNVERIFIED`) :
  la paire reste `MAPPING_TO_VERIFY` tant que la revue n'est pas levée par décision.
- La publication porte `snapshot_id`, `selection_sha256`, `server_time_ms` et le SHA-256 des octets
  du scanner et de chaque catalogue. `replayable=true` seulement si tous ces octets ont été fournis.

## Temps

| Champ | Sens |
|---|---|
| `trade_ms` | heure d'exécution déclarée par la plateforme (Kraken : secondes décimales tronquées à la ms, valeur native conservée dans `native_time`) |
| `first_received_ms` | première réception de ce trade par l'observateur |
| `instant_ms` | instant d'évaluation sur la grille |
| `trade_age_ms` | `instant_ms − trade_ms` |
| `receipt_lag_ms` | `first_received_ms − trade_ms` (peut être négatif dans la tolérance d'horloge) |

L'âge d'un ticker (`closeTime` du ticker 24 h du Radar) n'est **pas** un âge de trade.
Il n'est jamais accepté comme entrée : le décodeur refuse un payload de ticker.

## Règles de calcul (méthode v1)

Fenêtre M5 alignée UTC, `step_ms × points = 300 000`. Paramètres **explicites et obligatoires** ;
valeurs de départ (hypothèses à éprouver) : 10 000 ms × 30, âge maximal 5 000 ms par source,
écart maximal entre sources 5 000 ms, avance d'horloge tolérée 1 000 ms.

À chaque instant, pour chaque source, on retient le trade le plus récent par `trade_ms`
parmi ceux reçus au plus tard à l'instant. Motifs d'exclusion, par priorité :

1. `CLOCK_INCONSISTENT` : `trade_ms > first_received_ms + max_clock_lead_ms` ;
2. aucun trade reçu : `LATE_RECEIPT` si un trade frais existe mais est arrivé après l'instant,
   sinon `FETCH_ERROR` si la dernière tentative a échoué, sinon `NO_OBSERVATION` ;
3. trade trop ancien : `LATE_RECEIPT` si un trade frais est arrivé après l'instant, sinon `STALE_TRADE`.

Chaque source porte aussi `last_poll_status` : une panne ne se confond pas avec un marché calme.

Deux contrôles distincts :
- **fraîcheur** par source : `trade_age_ms ≤ max_trade_age_ms[source]` (borne incluse) ;
- **synchronisation** entre sources : `|trade_ms_A − trade_ms_B| ≤ max_inter_source_skew_ms`,
  sinon `pair_reason = EVENTS_NOT_SYNCHRONIZED` ; les deux sources restent valides en mono-source.

Écart (référence = MEXC) : `spread_abs = P_kraken − P_mexc` (devise de cotation) ;
`spread_bps = (P_kraken − P_mexc) / P_mexc × 10 000`, arrondi bancaire à 8 décimales.
**Positif = Kraken au-dessus de MEXC.** Sémantique : `LAST_TRADE_DIFFERENCE_NOT_EXECUTABLE`.
Un spread exécutable exigerait des cotations bid/ask (contrat de carnet).

Composite : moyenne arithmétique à poids égaux, Decimal précision 34, publiée seulement si toutes
les plateformes couvertes sont éligibles et synchronisées. Chaque point liste ses `contributors`.

Séries publiées séparément :
- `series.composite` : `COMPLETE` uniquement avec 30 points composites valides ; sinon `INCOMPLETE`,
  sans OHLC ; `NOT_APPLICABLE_SINGLE_VENUE_COVERAGE` quand une seule plateforme cote la paire ;
- `series.single_venue.<plateforme>` : libellée « MEXC seule · pas un composite » ou « Kraken seule · pas un composite ».

OHLC = premier, maximum, minimum, dernier **point échantillonné** (`candle: SAMPLED_POINTS_ONLY`) :
ce n'est pas la bougie native de la plateforme.

## Doublons, retards, provenance

- Clé de trade : `(venue, native_symbol, ID, trade_id)` ; sans identifiant natif (MEXC renvoie souvent `id: null`),
  `(venue, native_symbol, APPROX, trade_ms, price, qty, side)` — clé approximative documentée.
- Une nouvelle réception conserve `trade_ms` et la première réception ; elle ne rajeunit jamais un point.
  Même clé avec prix, quantité, côté ou heure différents : paquet refusé.
- Un trade arrivé après l'instant n'est pas utilisé pour cet instant (`LATE_RECEIPT`).
- `evidence_kind ∈ {OBSERVATION, SYNTHETIC}` sur le paquet et sur chaque trade : tout mélange est refusé.
- `venue` (lieu d'exécution) et `provider` (transmetteur) sont deux champs distincts, prêts pour un futur agrégateur.
- La publication porte `input_sha256` (JSON canonique du paquet) : même paquet, même publication,
  quel que soit l'ordre des trades.

## Limites connues

- Aucune donnée réelle n'a été décodée dans ce lot : formats natifs reproduits d'après la documentation
  publique et l'audit du 2026-11-20 ; le pilote doit confirmer `id` MEXC et la ligne Kraken à 7 champs.
- La matrice du 2026-11-20T01:08Z n'est **pas rejouable** octet pour octet : seuls les SHA-256 et la
  transcription ont été conservés. Une nouvelle matrice rejouable exige une lecture conservant les octets.
- Les seuils sont des hypothèses ; le pilote borné doit mesurer leur effet avant toute décision.
- Pas de lecteur API, pas de vue, pas de collecteur : lots ultérieurs, GO distincts.
