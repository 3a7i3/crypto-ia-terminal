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
