# CH1-01 — Contrat de perception événementielle

Décision opérateur : contrat et admission en lecture seule du corpus Kraken Spot BTC/USDT.
Base source : `9e438c22d1d66ed7a86220442edd89598f8bef8b`. Autorités : #568, #286 et ADR-0007.
Le lot est source uniquement. Le raccord au lecteur Flux, le rejeu de perception,
l'interface et toute collecte relèvent de lots ultérieurs. Le contrat Flux V1
et les valeurs internes de ses états restent compatibles.

## Identité et ordre

Une session épingle la place, le type de marché, le symbole natif, la base,
la cotation, l'unité de quantité, le SHA de capture, le SHA de rejeu et la
version du décodeur. La clé du marché inclut la place et le type de marché.
Les variantes BTC/USD, BTC/USDT et les produits dérivés ont des identités distinctes.

La borne de rejeu est le dernier numéro de réception inclus dans le journal
épinglé. L'ordre canonique est le couple (numéro de réception, index natif
dans la trame). L'heure exchange n'ordonne pas la lecture du journal.
Les temps UTC et monotones de réception gardent leur précision d'origine.
Un timestamp natif absent vaut null. L'horloge de réception reste disponible
dans son propre champ. Une séquence fournisseur absente vaut null.

## Enregistrements fermés V1

Toutes les clés listées sont obligatoires. « Nullable » autorise la valeur null,
qui n'est jamais convertie en zéro. Les clés inconnues et dupliquées sont des
erreurs. Les prix et quantités sont des chaînes décimales finies, sans exposant.
Les prix sont positifs, les tailles de trades strictement positives, les tailles
L2 positives ou nulles. Les compteurs et temps sont des chaînes d'entiers
non négatifs pour conserver leur valeur au passage JSON/JavaScript.

| Enregistrement | Clés |
| --- | --- |
| RAW_EVENT | schema_version, session_id, venue, market_type, native_symbol, channel (nullable), kind, receipt_seq, receive_utc_ns, receive_mono_ns, native_time (nullable, forme originale), native_sequence (nullable), offset_bytes, length_bytes, payload_sha256 |
| NORMALIZED_TRADE | schema_version, receipt_seq, item_index, trade_id (nullable), price, quantity, aggressor_side (BUY, SELL ou UNKNOWN), side_basis (TAKER, MAKER_INVERTED ou UNKNOWN) |
| DEPTH_UPDATE | schema_version, receipt_seq, item_index, operation (SNAPSHOT ou UPDATE), bids, asks, checksum (nullable), native_sequence (nullable) |
| BOOK_STATE | schema_version, as_of_receipt_seq, last_book_receipt_seq (nullable), subscribed_depth, bids (nullable), asks (nullable), native_state, native_reason (nullable) |
| QUALITY_REPORT | schema_version, as_of_receipt_seq, evidence_kind, book_integrity, book_freshness, trade_coverage, event_time_quality |

Chaque enregistrement porte `schema_version="1"`. Chaque artefact ne contient
qu'une session et porte le manifeste et le SHA-256 du journal en référence.
Les enregistrements normalisés renvoient à RAW_EVENT par numéro de réception.
Un niveau est un tableau de deux chaînes, prix puis quantité. Une taille nulle
dans un delta supprime le niveau. Un snapshot remplace le carnet. Le carnet
publié trie les bids par prix décroissant et les asks par prix croissant et
respecte la profondeur souscrite. Un carnet croisé ou verrouillé est invalide.
Les trames rejetées restent référencées par leurs octets et leurs motifs.

Chaque résultat qualité contient `state`, `reason` (nullable) et
`evidence_receipt_seq` (nullable). États admis : VERIFIED, DEGRADED, RESYNCING,
INVALID, UNKNOWN, NOT_AVAILABLE, UNRESOLVED. Un état autre que VERIFIED porte
un motif. `evidence_kind` vaut SYNTHETIC ou HISTORICAL pour ce contrat de rejeu.
La validité du carnet, sa fraîcheur, la couverture des trades et la qualité
des temps sont indépendantes. Un heartbeat ne change ni le carnet ni l'heure
de sa dernière mise à jour. Une couverture absente interdit de publier des
volumes, un delta ou un CVD comme des zéros observés.

## Correspondance sans perte de provenance

| Origine | État natif | Projection qualité |
| --- | --- | --- |
| BBO | VALID, UNCHANGED_VERIFIED | Intégrité VERIFIED dans la profondeur attestée. Conserver la distinction actualisé/inchangé. |
| BBO | FRESHNESS_UNKNOWN | Fraîcheur UNKNOWN. Intégrité déterminée par les preuves de reconstruction disponibles à la borne. |
| BBO | CONTINUITY_LOST | Intégrité INVALID à la rupture, RESYNCING lorsque la reprise est explicitement engagée. |
| BBO | BOOK_INVALID | Intégrité INVALID. |
| BBO | NOT_INITIALIZED | Intégrité NOT_AVAILABLE, ou RESYNCING si un snapshot est explicitement attendu. |
| BBO | SOURCE_UNAVAILABLE | Disponibilité NOT_AVAILABLE, information transmise comme motif sur les dimensions affectées. |
| Flux L2 | NO_SNAPSHOT | Intégrité NOT_AVAILABLE, ou RESYNCING si un snapshot est explicitement attendu. |
| Flux L2 | INVALID | Intégrité INVALID. |
| Flux L2 | LIVE | Candidat à VERIFIED sous preuves de reconstruction admissibles. L'état natif seul n'atteste ni fraîcheur ni provenance en temps réel. |

Le code et le motif natifs restent attachés à la projection. UNRESOLVED
désigne des preuves disponibles mais insuffisantes pour résoudre un conflit.
UNKNOWN désigne une information dont la qualification est indéterminée.
NOT_AVAILABLE désigne une source, un état initial ou une valeur indisponible.
DEGRADED requiert une limitation qualifiée et explicite.

## Admission du corpus BTC

Corpus `BBO-BTC-20261120T070632Z`, producteur
`05872243c4e726d6ec8a599fb1149fae311a5dbf`. La source de rejeu prévue est la
base du lot ci-dessus. Le blob de `bbo_book.py` est identique entre les
deux commits. Aucun rejeu de perception au nouveau contrat n'est certifié ici.

| Preuve | SHA-256 |
| --- | --- |
| Archive tar.gz | `4fb6493a9b96b484cca47c351abf8908dbea007aed083dc4917809831fde04df` |
| manifest.json | `9ee3185daaf05faf646686466d6faf18374ba54ade5ae30a1bf883b3f58da910` |
| events.jsonl | `5929c95dd28fc2ce7068043f8bd9cefa006ae0a33feb6c0ef0bca5b8b4b1f62f` |
| frames.bin | `f071d2379752ed323e82afe6ac76ff6d73d07805c062dff02b4c480774f11b5a` |

Vérification en lecture seule sur les fichiers d'origine : empreinte archive
conforme au reçu existant, empreintes des fichiers conformes au manifeste,
39 388 entrées contiguës, SHA-256 par trame, offsets couvrant exactement
14 548 334 octets et ordre monotone cohérent avec l'ancre du manifeste.
Ces contrôles portent sur la copie scellée disponible, avec ses canaux observés.

Kraken : 1 snapshot book et 29 556 updates book, ainsi que 648 heartbeats,
650 pongs, 66 statuts et 1 acquittement. Aucune trame du canal trade.
Le corpus est admis comme entrée historique de carnet L2. La couverture des
trades vaut UNKNOWN avec le motif TRADE_CHANNEL_NOT_CAPTURED. Les données
MEXC contenues dans le même journal restent hors de la projection Kraken.

## Preuves attendues au lot de rejeu

- Même journal et même borne donnent les mêmes octets et le même SHA-256.
- Ajouter une trame après la borne ne modifie pas le résultat.
- Un checksum faux ou une rupture invalide le carnet dès l'observation.
  La reprise demande un snapshot valide.
- Une perte d'intégrité du journal bloque l'admission. Une trame fournisseur
  malformée dans un journal intact reste traçable avec son motif.
- Les fixtures de trades restent SYNTHETIC et ne complètent pas la
  couverture historique de ce corpus.

## Implémentation source de ce lot

Module : `observability/market_flow/perception.py`. Tests :
`tests/market_flow/test_perception_contract.py`. Le module reste dans le paquet
`market_flow` et respecte ses règles d'architecture (aucun flottant, aucune
horloge, aucune lecture de fichier, aucun transport). Il n'est importé par
aucun producteur, lecteur ou service : le contrat de consommateurs du paquet
est inchangé.

- `strict_loads` refuse les clés dupliquées, les nombres fractionnaires JSON
  et les constantes non finies.
- `validate_record` applique, par type d'enregistrement, les clés fermées,
  les nullables et les grammaires ci-dessus. Règles de cohérence explicites :
  `aggressor_side` et `side_basis` valent `UNKNOWN` ensemble ou pas du tout ;
  un BOOK_STATE a ses deux côtés null ensemble, sans taille nulle, trié
  strictement, borné par `subscribed_depth`, ni croisé ni verrouillé ;
  `last_book_receipt_seq` et `evidence_receipt_seq` ne dépassent pas la borne.
- `project_native_state` applique la table de correspondance. Le code et le
  motif natifs restent attachés ; seules les dimensions assignées par la table
  sont projetées. `LIVE` (Flux) et `FRESHNESS_UNKNOWN` (BBO) n'atteignent
  `VERIFIED` que si l'appelant fournit l'intégrité établie par des preuves de
  reconstruction ; à défaut l'intégrité vaut `UNKNOWN` avec un motif.

Ce lot ne rejoue pas le corpus, ne lit aucun journal et ne certifie aucune
admission : les empreintes ci-dessus sont la preuve de l'opérateur.

## Décision d'architecture du 2026-11-23

Décision opérateur consignée dans le fil de projet, sans URL publique :

- Le domaine Marché est conservé et recentré sur la recherche.
- CH1-02 devient une tranche « du carnet à l'expérience » : rejeu Kraken seul
  du corpus admis vers BOOK_STATE et QUALITY_REPORT, puis une table de
  recherche traçable (déséquilibre des quantités affichées au meilleur bid et
  au meilleur ask, mid à 30 secondes, motifs d'exclusion) et son rapport
  d'évaluation. Une session éprouve le pipeline ; elle ne juge pas la valeur
  prédictive, qui exige plusieurs sessions indépendantes.
- Les sorties LMI qui qualifient des baisses de quantité affichée
  d'« annulations » sont exclues des entrées de recherche. Leur qualification
  relève d'un chantier LMI séparé.
- Scanner/Radar, Flux/CVD/Heatmap et Footprint sont conservés ; leur raccord
  à la recherche attend une expérience qui le justifie (trades à couverture
  vérifiée pour Flux).

## CH1-02 étape 1 — rejeu Kraken seul (source)

Module : `observability/market_flow/kraken_replay.py`. Tests :
`tests/market_flow/test_kraken_replay.py`, sur des journaux SYNTHETIC produits
hors réseau par `bbo_pilot.dry_run`. Fonction pure : l'appelant fournit les
octets de `manifest.json`, `events.jsonl` et `frames.bin`. Le rejeu du corpus
réel reste un geste d'opérateur.

- Le sceau est vérifié comme dans `bbo_pilot.load` ; toute perte d'intégrité
  refuse le rejeu entier.
- Le carnet Kraken est reconstruit avec le CRC32 à chaque message (portage de
  `bbo_book.KrakenSource`, épinglé par un test différentiel). Les autres places
  sont ignorées et comptées.
- Sortie : un RAW_EVENT par événement Kraken, puis BOOK_STATE et QUALITY_REPORT
  après chaque événement qui peut changer le carnet ou son intégrité. Le
  résultat ne dépend que du préfixe du journal jusqu'à la borne.
- `native_state` reprend les codes BBO sans classe temporelle : `VALID` signifie
  synchronisé, deux côtés présents, non croisé, checksum vérifié au message
  `last_book_receipt_seq`. `UNCHANGED_VERIFIED` et `FRESHNESS_UNKNOWN` relèvent
  de l'étape de disponibilité.
- Fraîcheur du carnet : `UNKNOWN / BOOK_FRESHNESS_NOT_ATTESTED`. Trades :
  `UNKNOWN / TRADE_CHANNEL_NOT_CAPTURED` ; une trame du canal `trade` refuse le
  rejeu. Temps natifs : `UNKNOWN / NATIVE_TIME_NOT_ATTESTED`.
- `RESYNCING` n'apparaît qu'après une demande d'abonnement effectivement
  envoyée et journalisée après la rupture.
- Les temps de réception sont en millisecondes à l'origine ; la session déclare
  `receipt_time_resolution_ns = 1000000`.

### Politique de vivacité, déclarée avant tout rejeu réel

| Élément | Règle |
| --- | --- |
| Événements qui attestent la vivacité | `ws_open`, `ws_control`, trame texte `ws_message` au JSON valide (heartbeat, pong, statut, accusé, carnet) |
| Événements qui ne l'attestent pas | `sent`, `rest`, `checksum_mismatch`, `closed_by_pilot`, autres |
| Délai attesté par une preuve | 2 000 ms, valeur pré-enregistrée `liveness_max_ms` du pilote BBO |
| Axe de temps | `t_ms` en millisecondes entières (ancre du manifeste + délai monotone de réception) |
| Attestation | une preuve reçue en p atteste `[p, p + 2000)` ; le délai expire en p + 2000 |
| Écart entre deux preuves | si q − p > 2000 : `SILENCE_GAP_EXCEEDS_MAX` sur `[p + 2000, q)`, qui cite p et q |
| Déconnexion | `ws_close`, `ws_error` ou `gave_up` en c : `SILENCE_UNATTESTED_AFTER_DISCONNECT` sur `[c, preuve suivante)`, précédé d'un écart sur `[p + 2000, c)` si c − p > 2000 |
| Avant toute preuve | `SILENCE_UNATTESTED_BEFORE_FIRST_PROOF`, sans début |
| À la borne de rejeu | le silence ouvert, ou `SILENCE_UNATTESTED_AFTER_LAST_PROOF` à partir de p + 2000, est listé sans fin ; aucun événement après la borne n'est lu |
| Portée | vivacité de la connexion seulement ; elle ne rend pas le carnet frais et ne le valide pas |

Exemples fixés par les tests : deux preuves séparées de 2 001 ms donnent un
silence `[p + 2000, p + 2001)` qui cite la dernière preuve p et la preuve q qui
le ferme ; séparées de 2 000 ms, elles n'en donnent aucun. Un rejeu borné avant
la trame q donne le même verdict, octet pour octet, que q arrive à 2 000 ms ou
à 2 001 ms, et que le journal s'arrête ou non à la borne : la vivacité est
attestée jusqu'à p + 2000 exclu, puis le silence est ouvert et ne cite pas q.

Chaque silence a les clés `reason`, `starts_at_t_ms` (inclus, `null` avant toute
preuve), `ends_before_t_ms` (exclu, `null` s'il est encore ouvert à la borne),
`last_proof_receipt_seq`, `last_proof_t_ms`, `opened_by_receipt_seq` (la
déconnexion) et `closed_by_receipt_seq` (la preuve ou la déconnexion qui le
ferme). `bbo_book.source_state` compte encore l'instant p + 2000 comme vivant
(`t - alive > L`) ; ce rejeu ne le fait pas. La différence porte sur cet instant
seulement.

Un heartbeat établit la vivacité de la connexion ; le checksum atteste
l'intégrité du carnet au message vérifié ; la fraîcheur du carnet reste UNKNOWN.
L'effet des silences sur les fenêtres est décidé à l'étape de disponibilité.

### Commande de l'opérateur

Module : `observability/market_perception_replay.py`, hors de `market_flow`.
Le test d'architecture l'autorise comme consommateur précis : il n'importe que
`kraken_replay` du paquet, et aucun module réseau, horloge ou runtime. Tests :
`tests/market_flow/test_replay_cli.py`, sur journaux SYNTHETIC.

```
python -m observability.market_perception_replay verify \
    --manifest M --events E --frames F [--manifest-sha256 HEX]
python -m observability.market_perception_replay replay \
    --manifest M --events E --frames F --receipt-bound N \
    --corpus-id ID --evidence-kind {SYNTHETIC,HISTORICAL} --out FICHIER [--manifest-sha256 HEX]
```

- `verify` n'écrit rien ; il affiche le sceau et le nombre d'événements scellés,
  qui est la borne d'un rejeu complet.
- Les chemins, la borne, l'identifiant du corpus et le type de preuve sont
  explicites. `HISTORICAL` exige `--manifest-sha256` : le manifeste porte les
  empreintes des deux autres fichiers. Le rejeu exige aussi que cet identifiant
  et ce SHA figurent dans la référence d’admission versionnée.
- Le sceau est vérifié avant toute écriture. La destination ne doit pas exister
  et son dossier doit exister. Le document est écrit dans un fichier temporaire
  privé à côté, synchronisé et relu pour vérifier son SHA-256, puis lié à sa
  place sans remplacer un fichier.
- En cas de succès, la commande affiche le nombre d'enregistrements par type, la
  taille exacte en octets et le SHA-256 du document.
- Codes de sortie : 0 fait, 2 usage, 3 refus (rien d'écrit), 4 écriture en échec
  (rien laissé à la destination).
- Volume : quelques dizaines de Mo estimés pour le corpus Kraken admis ; le
  premier rejeu réel donnera la mesure.

### Exigences d’admission C2-R

Une session Kraken Spot vérifie que le symbole natif correspond exactement à
base/quote. La quantité est exprimée en unités de base et le prix en unités de
cotation par unité de base. Les autres places du journal sont hors projection.
Un état VALID ou UNCHANGED_VERIFIED exige deux côtés non vides et un reçu
strictement positif, à la borne ou avant. Le producteur doit relier ce reçu
au carnet reconstruit et à son contrôle natif.

Pour HISTORICAL, le couple identifiant du corpus et SHA-256 du manifeste
est comparé à la référence d’admission versionnée dans perception.py.
Une empreinte fournie par l’opérateur à la CLI constitue un contrôle
d’égalité supplémentaire. La référence documentaire ne certifie pas un rejeu.

### Rejeu Kraken C2-R

Les plages des événements pavent frames.bin dans l’ordre des reçus, y compris
les plages vides. Les tailles du sceau, si présentes, doivent correspondre
aux fichiers. Une trame book doit contenir un seul élément pour l’instrument
souscrit. Une enveloppe ambiguë, un opcode inattendu ou un carnet non
bilatéral après checksum invalide la continuité. Les anomalies portent le
numéro du reçu, y compris pendant une rupture déjà ouverte. La reprise
exige un snapshot bilatéral, non croisé, avec checksum valide, sur une
connexion observée. Une souscription ou un heartbeat seuls ne rétablissent
pas le carnet. Le rejeu garde la règle de vivacité des intervalles semi-ouverts.

### Unités du manifeste Kraken Spot (C2-R2)

La base et la cotation établissent les unités implicites de ce contrat Spot.
Les champs facultatifs quantity_unit, price_quote_unit et price_unit sont
contrôlés à la racine, dans instrument et dans ws.kraken. Ils doivent
respectivement correspondre à la base, à la cotation et à cotation/base.
Chaque déclaration explicite est contrôlée, même si un autre niveau donne la
bonne valeur. Un champ d'unité inconnu donne KRAKEN_UNIT_FIELD_UNKNOWN, une
valeur malformée KRAKEN_UNIT_MALFORMED, et une unité différente de l'attendu
KRAKEN_UNIT_MISMATCH, avec le chemin concerné. Le code d'identité préexistant
KRAKEN_SPOT_IDENTITY_MISMATCH demeure applicable.

Quand les unités ne sont pas déclarées, la projection conserve les
conventions de l'instrument Spot. L'absence ne constitue aucune attestation
de l'exchange ni de provenance historique.

### Contrôles de connexion Kraken Spot v2 (C2-R2)

Les enveloppes de contrôle sont validées avant d'attester la connexion.
Heartbeat est limité au champ channel. Pong accepte les métadonnées de
réponse documentées, sans champ data. Status et acquittements book sont
limités aux structures de base documentées et à la souscription du pilote.
Les extensions non prises en charge sont classées de manière conservatrice.
Les représentations abrégées du générateur BBO (horodatage x et symbole en
liste dans les acquittements) sont réservées au mode SYNTHETIC.
Un ping/pong WebSocket natif exige un opcode de contrôle et au plus 125 octets
sur une connexion ouverte. Une enveloppe ambiguë ou malformée conserve son
reçu et rompt la continuité sans prolonger la vivacité. Un désabonnement book
confirmé invalide le carnet courant. Un contrôle valide n'actualise jamais le
carnet. La réparation exige un snapshot admissible. Les preuves book de
connexion proviennent de trames appliquées avec checksum valide et carnet
admissible. Les bornes de silence demeurent à 2 000 et 2 001 ms.

Références Kraken Spot v2 :
[Ping](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/ping),
[Heartbeat](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/heartbeat),
[Status](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/status),
[Book](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/book).
