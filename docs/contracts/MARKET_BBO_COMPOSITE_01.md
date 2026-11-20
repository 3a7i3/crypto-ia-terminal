# MARKET-BBO-COMPOSITE-01 — meilleur bid/ask MEXC + Kraken, composite M5 sur carnets continus

Mission CAT-RADAR-KRAKEN-MEXC-01, pilote BBO (plan G2 du 2026-11-20, GO G3).
Statut : **SOURCE_ONLY / OFFLINE / NON_DEPLOYED**. Base : branche `claude/project-thread-xs10rr`
sur `710929be` (L1 + L3). Ce document n'autorise aucune collecte, aucun accès VPS, aucun lecteur API,
aucune vue, aucun service ni déploiement. La collecte publique attend un GO runtime séparé.
Le Radar reste une observation : aucun pont vers Advisor, stratégies, PAPER, PPL ou FIN.

## Pourquoi un produit distinct

`MarketVenueComparison` (contrat Venues, #536) qualifie la fraîcheur d'une cotation par
`observed_at` et `timestamp_kind`. Les carnets REST MEXC et Kraken n'ont pas d'heure de carnet,
ils y sont refusés à juste titre. Ici, la fraîcheur repose sur **la continuité prouvée du carnet
et une preuve de vie récente**, pas sur une heure source. `MarketBboComposite` 1.0.0 est donc un
produit frère. Il reprend sans en changer le sens : `InstrumentKey`, `mid = (bid+ask)/2`,
`spread_bps = (ask−bid)/mid × 10 000`, le refus des carnets croisés (`ask > bid` strict, le cas
verrouillé est aussi exclu), et le signe de `mid_basis_bps` avec MEXC pour référence.
Une projection vers `Quote` (`book_state=SYNCHRONIZED`) reste à décider : elle n'est pas branchée.

## Fichiers

| Emplacement | Rôle |
|---|---|
| `observability/radar_composite/bbo_wire.py` | Codec client RFC 6455 (poignée de main, masquage, fragmentation, contrôles, plafonds) et décodeur protobuf minimal MEXC ; encodeurs synthétiques |
| `observability/radar_composite/mexc_proto/` | Copie verbatim des `.proto` officiels utilisés, licence Apache-2.0, `PROVENANCE.md` (révision, sha256) |
| `observability/radar_composite/bbo_book.py` | Carnets MEXC (versions) et Kraken (CRC32), états à l'instant t, paire, composite, bougies |
| `observability/radar_composite/bbo_pilot.py` | Orchestration bornée, preuves brutes, rejeu, transports synthétiques ; transport réel verrouillé |
| `observability/radar_composite/bbo_schema.py` | Validation fermée de `MarketBboComposite` 1.0.0 |
| `tests/radar_composite/test_bbo_*.py` | Tests hors réseau (création de socket interdite) |

Bibliothèque standard uniquement, compatible Python 3.10.

## Sources officielles vérifiées (2026-11-20)

- MEXC Spot v3, *WebSocket Market Streams* et *Protocol Buffers integration* :
  `wss://wbs-api.mexc.com/ws`, canal `spot@public.aggre.depth.v3.api.pb@(100ms|10ms)@<SYMBOL>`,
  `{"method":"SUBSCRIPTION"}`, `{"method":"PING"}` → `{"id":0,"code":0,"msg":"PONG"}`,
  connexion de 24 h au plus, 30 abonnements au plus, coupure après 30 s sans abonnement et après
  1 min sans flux ; procédure « How to Properly Maintain a Local Copy of the Order Book ».
- Définitions protobuf : `github.com/mexcdevelop/websocket-proto` à la révision
  `0c9c4f35dd0fadc3a46a350e909a93379d81e811` (empreintes dans `mexc_proto/PROVENANCE.md`,
  revérifiées par les tests).
- Kraken Spot WS v2 : `book` (profondeur 10/25/100/500/1000, `snapshot`, `checksum`,
  `timestamp`), guide *Book checksum v2*, `ping` (`{"method":"ping","req_id":n}` →
  `{"method":"pong",…}`), `heartbeat` (`{"channel":"heartbeat"}`, « approximately once every
  second in the absence of any other channel updates », généré automatiquement après un
  abonnement).

## MEXC : jonction initiale et continuité

**Jonction (première initialisation et toute réinitialisation)**, selon la procédure officielle :
1. s'abonner et mettre en cache les diffs, en gardant le cache contigu
   (`fromVersion = toVersion précédent + 1`, sinon le cache repart du diff reçu) ;
2. demander `GET /api/v3/depth?symbol=<S>&limit=5000` dès le premier diff en cache ;
3. si `lastUpdateId < fromVersion` du premier diff en cache, redemander le snapshot
   (`SNAPSHOT_OLDER_THAN_FIRST_DIFF`). La règle est appliquée **à la lettre** : un snapshot égal à
   `fromVersion − 1`, pourtant contigu, est aussi redemandé ;
4. écarter les diffs dont `toVersion ≤ lastUpdateId` ; s'il n'en reste aucun, attendre le
   prochain diff ;
5. si le premier diff restant a `fromVersion > lastUpdateId + 1`, réinitialiser
   (`FIRST_DIFF_AFTER_SNAPSHOT_GAP`) ;
6. appliquer le snapshot puis les diffs restants : `JOINED`.

**Continuité après jonction** : chaque diff exige `fromVersion = toVersion précédent + 1`.
Sinon `VERSION_GAP` : le carnet est retiré immédiatement et une nouvelle jonction démarre.
Une quantité `0` supprime le niveau. Les niveaux au-delà des 5 000 du snapshot peuvent différer
(note officielle) ; seul le sommet est publié.

**Champs utilisés** (`PushDataV3ApiWrapper`) : `channel` (1), `symbol` (3), `symbolId` (4),
`createTime` (5, commentaire officiel « 消息生成时间 », heure de génération du message),
`sendTime` (6, « 消息推送时间 », heure de push), corps `publicAggreDepths` (313) :
`asks` (1), `bids` (2), `eventType` (3), `fromVersion` (4), `toVersion` (5),
`lastOrderCreateTime` (6) ; niveaux `price` (1), `quantity` (2) en texte décimal.

## Kraken : checksum

- Calcul : 10 meilleurs asks du plus bas au plus haut, puis 10 meilleurs bids du plus haut au plus
  bas ; pour chaque niveau, prix puis quantité, sans `.` et sans zéros de tête ; chaîne asks +
  chaîne bids ; CRC32 non signé. Le vecteur officiel (BTC/USD, 3310070434) est reproduit par test.
- Le calcul porte sur **les caractères** reçus. Les nombres JSON sont donc lus comme littéraux
  exacts (`Num`), jamais via `float`. Les mêmes valeurs sans zéros de fin donnent un autre CRC (test).
- Après chaque message : application dans l'ordre (plusieurs mises à jour d'un même niveau
  possibles), suppression à quantité `0`, troncature à la profondeur souscrite, puis vérification.
- **Ce que le checksum vérifie** : après ce message, les 10 premiers niveaux locaux, dans leur
  représentation textuelle, sont identiques à ceux de l'échange au moment du calcul serveur.
- **Ce qu'il ne peut pas affirmer** sans numéro de séquence (v2 n'en documente pas) : qu'aucun
  message n'a été perdu puis compensé ; l'ordre de livraison ; l'état sous le 10e niveau ;
  l'heure à laquelle ce sommet était vrai. Une collision CRC32 reste possible.
- Divergence : la documentation ne prescrit rien (« Checksum verification is optional »). Choix
  conservateur : `CHECKSUM_MISMATCH`, carnet retiré, désabonnement puis réabonnement avec snapshot.
  Les mises à jour reçues entre-temps sont ignorées. Un snapshot n'est réadmis que si son propre
  checksum concorde.

## Vie, mise à jour et continuité : trois faits séparés

Pour chaque source, au plus tard à l'instant t :
- `liveness_ms` : dernière trame prouvant que la connexion vit (toute trame, PONG, heartbeat,
  ping/pong protocolaire) ;
- `quote_as_of_ms` : dernière modification appliquée au carnet (snapshot validé, diff, update).
  C'est l'heure de la cotation. **PONG et heartbeat ne la rafraîchissent jamais** ;
- `continuity` : `NOT_INITIALIZED`, `SYNCED` ou `CONTINUITY_LOST` avec un motif
  (`VERSION_GAP`, `CHECKSUM_MISMATCH`, `DISCONNECTED`, `DIFF_INVALID`, `MESSAGE_INVALID`, `GAVE_UP`).

Une preuve de vie ne valide ni un snapshot, ni un diff, ni un carnet en resynchronisation.
Après une rupture de version, un checksum divergent ou une déconnexion, la source sort du composite
**immédiatement** et n'y revient qu'après reconstruction validée (jonction MEXC `JOINED`, ou
snapshot Kraken à checksum concordant).

## États par source à l'instant t

Précédence : indisponible, continuité, initialisation, carnet, vie, changement.

| État | Condition |
|---|---|
| `SOURCE_UNAVAILABLE` | jamais connectée, déconnectée hors rupture, ou abandon après le plafond de reconnexions |
| `CONTINUITY_LOST` | depuis la rupture jusqu'à la reconstruction validée |
| `NOT_INITIALIZED` | connectée, jonction pas encore faite |
| `BOOK_INVALID` | côté vide, ou `ask ≤ bid` |
| `FRESHNESS_UNKNOWN` | `t − max(liveness_ms, quote_as_of_ms) > L` |
| `UNCHANGED_VERIFIED` | éligible ; sommet inchangé depuis plus de `L`, mais vie prouvée dans `[t−L, t]` |
| `VALID` | éligible ; sommet modifié dans `[t−L, t]` |

Hypothèse **A-ORDER** (à qualifier au runtime) : sur une connexion, le serveur émet dans l'ordre ;
un PONG reçu après des diffs prouve que ces diffs ont été livrés. `UNCHANGED_VERIFIED` en dépend
et est compté à part.

## Paire, composite et bougies

- `mid_gap_bps = (mid_kraken − mid_mexc) / mid_mexc × 10 000`, positif quand Kraken est au-dessus.
- Catégories : `COMPOSITE`, `SINGLE_SOURCE` (une seule source éligible : son observation est
  publiée avec sa provenance), `SOURCE_EXCLUDED` (aucune), `EXCESSIVE_GAP`, `NOT_EVALUATED`
  (après un arrêt technique).
- Composite : moyenne simple des deux mids, seulement si les deux sources sont éligibles et
  `|mid_gap_bps| ≤ G`. **Borne fermée** : un écart de exactement ±50 bps est admis, 50,01 ne l'est
  pas (tests). Calcul exact en `Decimal` (précision 50) ; publication de `mid_gap_bps` et
  `spread_bps` à 6 décimales.
- Valeurs publiées seulement pour une source éligible. Une source exclue publie son état, sa
  continuité, ses heures et son horodatage source, sans prix.
- Bougie : 30 points d'une fenêtre M5 alignée UTC, pas de 10 s. OHLC seulement à 30/30
  (`COMPLETE`). Sinon `INCOMPLETE`, avec le nombre de points et sans OHLC. Même règle pour les
  séries mono-source MEXC et Kraken.

## Paramètres pré-enregistrés

| Paramètre | Primaire | Sensibilité |
|---|---|---|
| `L`, vie maximale (hypothèse du pilote) | 2 000 ms | 1, 2, 5, 10 s |
| `G`, écart de mid maximal, borne fermée | 50 bps | 10, 25, 50, 100 bps |
| Ping applicatif | 1 s sur chaque connexion | — |
| Décalage d'horloge REST | ≤ 1 s MEXC, ≤ 2 s Kraken au preflight (arrêt sinon), mesuré et publié en fin de run | — |

Lecture séparée des résultats :
1. **Disponibilité du flux** par source : instants éligibles / évalués ≥ 95 % et 0 rupture non
   résolue → `FLUX_VIABLE` ;
2. **Taux de points composites** : ≥ 80 % viable, de 50 % inclus à < 80 % partiel, < 50 %
   insuffisant (mêmes classes que L3) ;
3. **Nombre de bougies composites complètes**.

## Preuves et rejeu

- `events.jsonl` : une ligne par événement (trame, envoi, ouverture, fermeture, REST, arrêt) avec
  `seq`, plateforme, heures murale et monotone de réception, `t_ms`, position et taille dans
  `frames.bin`, sha256 du contenu. `frames.bin` : octets bruts concaténés.
- `t_ms = ancre murale + (monotone − ancre monotone)`, une seule ancre par run : la grille ne
  dépend pas des sauts d'horloge murale.
- Scellement final dans `manifest.json` : nombre d'événements, sha256 de `events.jsonl` et de
  `frames.bin`. Le rejeu refuse une preuve non scellée, une trame altérée, une ligne retirée ou
  déplacée, ou une heure incohérente avec l'ancre.
- Le rejeu reconstruit les carnets à partir des seules trames, dans l'ordre de réception. L'état à
  l'instant t n'utilise que les trames reçues au plus tard à t. Deux rejeux produisent des octets
  identiques.

## Arrêts et budgets (transport réel)

HTTP 403/418/429/451 ; refus de poignée de main WebSocket ; erreur fournisseur (`code ≠ 0` MEXC,
`error` Kraken) ; abonnement refusé ; plus de 3 resynchronisations par source ; plus de
3 reconnexions par plateforme ; budgets REST par endpoint ; 200 000 trames, 512 Kio par message,
300 Mo ; durée ; preflight d'identité et d'horloge repris de L3 ; marge MEXC non établie.
Le transport réel n'accepte que deux URL WebSocket et six URL REST, et ne démarre qu'avec `run`,
`--confirm-public-collection BBO-PILOT` et la vérification du collecteur Radar.

## À qualifier au runtime

1. Forme binaire réelle des trames MEXC et présence de `symbol` dans le wrapper.
2. Horloge et unité de `createTime`, `sendTime` (MEXC) et `timestamp` (Kraken) : conservés,
   jamais utilisés pour la fraîcheur.
3. Représentation des nombres Kraken sur le fil (zéros de fin conservés ou non) : si elle diffère
   du guide, chaque checksum divergera et le pilote s'arrêtera au plafond de resynchronisations.
4. Hypothèse A-ORDER.
5. Symbole WS v2 Kraken (`BTC/USDT` attendu ; l'altname REST est `XBTUSDT`).
6. Poids REST de `depth?limit=5000` et accès WebSocket depuis le VPS.
7. Débit réel des carnets et comportement à faible activité (ATOM longtemps `UNCHANGED_VERIFIED`).

## Hors périmètre

Perpétuels, comparaison USD/USDT (conversion qualifiée requise), raccordement à l'interface,
collecte, VPS, push, PR et déploiement.
