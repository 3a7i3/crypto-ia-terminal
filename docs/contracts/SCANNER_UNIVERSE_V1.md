# Scanner V1 — univers commun MEXC × Kraken (contrat `scanner-universe/1.0.0`)

Statut : source seulement, **déploiement non effectué**. Aucune donnée collectée
n'est versionnée : les relevés restent sur le disque du VPS (règle données).

## Règle

```text
Univers Scanner =
    MEXC Spot négociable
  ∩ MEXC Perpétuel négociable
  ∩ Kraken Spot négociable
  ∩ Kraken Perpétuel négociable
```

- Clé commune : `BASE/QUOTE` canonique. `USD`, `USDT`, `USDC` (et `USD1`) restent
  distincts. Seuls alias admis : `XBT → BTC`, `XDG → DOGE`, appliqués aux noms
  natifs Kraken (`catalogues.KRAKEN_ASSET_ALIASES`, testés).
- Une paire entre dans l'univers seulement avec **quatre preuves** admissibles.
  Chaque preuve garde : exchange, type de marché, symbole natif, base/cotation
  canoniques et natives, statut natif, type de contrat, devise de règlement
  (séparée de la cotation) et sa base de détermination, heure de collecte.

## Sources officielles et négociabilité

| Marché | Endpoint public | Identité | Négociable si | Perpétuel si |
|---|---|---|---|---|
| MEXC Spot | `GET api.mexc.com/api/v3/exchangeInfo` | `symbol`, `baseAsset`, `quoteAsset` | `status == "1"` et `isSpotTradingAllowed` | — |
| MEXC Perpétuel | `GET contract.mexc.com/api/v1/contract/detail` | `symbol` (`BASE_QUOTE`), `baseCoin`, `quoteCoin`, `settleCoin` | `state == 0` et `isHidden == false` | `futureType == 1` ; linéaire si `settleCoin == quoteCoin`, inverse si `settleCoin == baseCoin`, sinon ambigu |
| Kraken Spot | `GET api.kraken.com/0/public/AssetPairs` + `/0/public/Assets` | clé, `altname`, `wsname`, `base`/`quote` → `Assets.altname` | `status == "online"` | — |
| Kraken Perpétuel | `GET futures.kraken.com/derivatives/api/v3/instruments` | `symbol`, `type`, `base`, `quote`, `pair` | `tradeable` et ni `suspended`, ni `isExpired`, ni `postOnly` | `PF_` + `flexible_futures` (linéaire, multi-collatéral) ou `PI_` + `futures_inverse`, sans `lastTradingTime` |

## Motifs d'exclusion

`ABSENT` (le marché ne liste pas la clé), `NOT_TRADABLE`, `NOT_PERPETUAL`
(échéance), `AMBIGUOUS_MAPPING` (symbole incohérent avec ses champs, actif non
canonique, base/cotation absentes), `AMBIGUOUS_CONTRACT` (règlement ni base ni
cotation), `DUPLICATE_KEY` (deux instruments natifs pour la même clé sur un
marché), `DARK_POOL_PAIR`. Un instrument exclu n'est jamais « choisi » à la place
d'un autre.

## Complétude, fraîcheur et statuts

- Catalogue **COMPLETE** : enveloppe de succès attendue, au moins un instrument,
  aucun symbole natif dupliqué, chaque entrée bien typée. Une entrée illisible ⇒
  **INCOMPLETE** ; un échec HTTP/transport ⇒ **UNAVAILABLE**.
- Cadence du producteur : 900 s (même cadence que la campagne D1-RC1 qui relit
  `exchangeInfo`). Fraîcheur : `FRESHNESS_MAX_AGE_MS = 2 × 900 s + 300 s = 35 min`
  (une exécution manquée tolérée, + gigue du timer et budget de 5 requêtes × 20 s).
  Borne incluse ; une réception de plus de 5 s dans le futur est refusée.
- `VERIFIED` : quatre catalogues complets et frais, ≥ 1 paire.
- `VERIFIED_EMPTY` : quatre catalogues complets et frais, 0 paire (univers vide valide).
- `UNVERIFIABLE` : au moins une source non courante ; `pairs` toujours vide ;
  `blocking_sources` nomme chaque marché et son motif ; la dernière liste vérifiée
  peut figurer dans `reference` avec `current: false`.
- Le lecteur API ré-applique la fraîcheur à chaque requête (`universe.requalify`)
  et le client la ré-applique avec le temps écoulé depuis la réception.

## Architecture

- `observability/scanner_universe/catalogues.py` — parseurs purs des 4 catalogues.
- `observability/scanner_universe/universe.py` — intersection pure, fraîcheur.
- `observability/scanner_universe/schema.py` — validation de la publication.
- `observability/scanner_universe/collect.py` — producteur (seuls appels réseau),
  conservation des réponses brutes + `manifest.json`, `--replay`.
- `observability/operator_api/scanner_universe_reader.py` + route GET
  `/api/operator/v1/scanner-universe` (`OPERATOR_SCANNER_UNIVERSE_PATH`).
- Frontend : `lib/scannerUniverseClient.ts`, `views/ScannerUniverse.tsx` ; les
  sous-vues Scanner classé, Bulles Intraday, Radar Spot et Composite historique ne
  montrent que les lignes admises par l'univers courant.

## Reproduction

```bash
python -m observability.scanner_universe.collect --out-dir DIR      # 5 GET publics
python -m observability.scanner_universe.collect --replay DIR/runs/<run_id> | cmp - DIR/runs/<run_id>/scanner-universe.json
python -m pytest tests/scanner_universe
(cd frontend && npx vitest run src/test/ScannerUniverse.test.tsx)
```

## Déploiement (non effectué) et retour arrière

Scripts : `deploy/scanner_universe/prep.sh` (sans root, construit l'API et le web
par-dessus les versions en service, vérifie que les fichiers remplacés sont
identiques à ceux en service, reconstruit le web en service à l'identique comme
témoin, lance les tests et un passage à blanc du producteur) et
`deploy/scanner_universe/cat-scanner-universe-root.sh` (phases `install`, `invoke`,
`api`, `web`, `status`, `rollback`, une à la fois, chacune sur GO de l'opérateur).

1. Producteur : compte système `cat-scanner-universe`, checkout immuable
   `/opt/cat-scanner-universe/checkout/<sha>`, service oneshot + timer `*:7/15`
   (900 s), `--out-dir /var/lib/cat-scanner-universe --keep-runs 24` (≈ 5 Mo de
   réponses brutes par relevé, 6 h conservées). Publication en mode 0644, lue par
   l'API sous un autre compte. Réseau : HTTPS public ; boucle locale (sauf le
   résolveur 127.0.0.53), réseaux privés et métadonnées refusés. Les hôtes des
   exchanges sont derrière des CDN : la restriction aux trois hôtes est portée par
   le code (`catalogues.ENDPOINTS`), pas par une liste d'adresses IP.
2. API : release = version en service + fichiers `scanner_universe` + 18 lignes
   ajoutées à `app.py` ; drop-in avec `OPERATOR_SCANNER_UNIVERSE_PATH=/var/lib/cat-scanner-universe/scanner-universe.json`,
   redémarrage de `crypto-operator-api` ; contrôle de la session PAPER (inchangée)
   et des routes existantes, retour arrière automatique en cas d'échec.
3. Web : dist = source en service + fichiers du Scanner ; drop-in de
   `crypto-operator-web` ; page et bundle servis comparés au build.
4. Retour arrière : `rollback` retire les deux drop-ins, arrête et retire le timer
   et le service, redémarre API et web sur le bloc précédent. Les relevés, le
   checkout et le compte restent sur disque.
