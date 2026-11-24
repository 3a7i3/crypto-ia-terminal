# CAT R0 — Audit de réutilisation avant le Radar

Gate R0-1. Audit en lecture seule, réalisé le 2026-11-24 sur
`main@9e438c22d1d66ed7a86220442edd89598f8bef8b` (branche de travail
`claude/project-thread-dg0k91`). Aucun réseau de marché, aucun runtime,
aucune donnée réelle consultés.

## 1. Cadre vérifié

| Référence | État lu le 2026-11-24 | Conséquence pour R0 |
|---|---|---|
| [#568](https://github.com/3a7i3/crypto-ia-terminal/issues/568) MASTER ROADMAP III | `ACTIVE_CANONICAL` depuis 2026-11-11 ; III-R3 « Market Observatory » ; règle III-R3 : aucune donnée marché ne touche l'epoch active | R0 est un chantier source de III-R3, sans collecte ni publication runtime |
| [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) garde-fou | `ACTIVE_BURN_IN_IMMUTABILITY_GUARD` actif | Aucun fichier de stratégie, signal, risk, PPL, FIN, config ou runtime touché |
| `CLAUDE.md`, `docs/DEVELOPER_ENTRYPOINT.md` | UNKNOWN ≠ 0 ; l'intelligence n'est pas l'autorité ; source ≠ runtime | Le Radar publie des propositions `PROPOSED_NOT_AUTHORIZED`, jamais une permission |
| PR [#604](https://github.com/3a7i3/crypto-ia-terminal/pull/604) | DRAFT, ouverte, HEAD `987f4b11`, base `main@9e438c22` | Non modifiée, non importée (contrat CH1-01 pas encore sur main) |
| PR [#605](https://github.com/3a7i3/crypto-ia-terminal/pull/605) | DRAFT, ouverte, empilée sur #604, HEAD `f482ac39` | Non modifiée, non importée |

Les gates **C2-C** et **C2-D** citées dans le mandat ne sont définies ni sur
main ni dans #604/#605 (seule « C2-R » existe dans le contrat CH1-01 de #604).
Leur contenu est donc **UNKNOWN** pour cet audit ; le Radar se contente de les
nommer comme préalables de toute admission historique de la référence BTC.

## 2. Composants examinés

### 2.1 `observability/scanner_universe/` — réutilisé directement

| Fichier | Capacité réelle | Réutilisation R0 |
|---|---|---|
| `catalogues.py` | Parseurs purs des quatre catalogues publics officiels (MEXC Spot `exchangeInfo`, MEXC Perpétuel `contract/detail`, Kraken Spot `AssetPairs`+`Assets`, Kraken Perpétuel `instruments`) ; une preuve `Evidence` par instrument natif ; complétude `COMPLETE / INCOMPLETE / UNAVAILABLE` ; motifs d'exclusion (`NOT_TRADABLE`, `NOT_PERPETUAL`, `AMBIGUOUS_MAPPING`, `AMBIGUOUS_CONTRACT`, `DUPLICATE_KEY`, `DARK_POOL_PAIR`) ; alias Kraken `XBT→BTC`, `XDG→DOGE` seulement | **Importé tel quel** (`parse_all`) : la découverte R0-A passe par ces parseurs, alimentés par les octets des catalogues de fixture |
| `universe.py` | Intersection stricte des quatre marchés (`VERIFIED / VERIFIED_EMPTY / UNVERIFIABLE`), fraîcheur 35 min (`source_status`), classes d'actifs (`asset_class`) | **Importé** : `source_status` (validité des métadonnées) et `asset_class` (politique d'univers). `compute_universe` **n'est pas** réutilisé : l'intersection supprime tout marché absent d'un des quatre catalogues, alors que le Radar doit évaluer chaque marché individuellement |
| `collect.py` | Seul point réseau (5 GET publics), producteur VPS | **Non importé** (interdiction réseau) |
| `schema.py` + `operator_api/scanner_universe_reader.py` | Validation fermée et lecteur GET | Non concernés (pas de publication API en R0) |

### 2.2 `observability/radar_composite/`

| Fichier | Capacité réelle | Réutilisation R0 |
|---|---|---|
| `instruments.py` | Identité Spot `InstrumentKey`, `Binding` natif MEXC/Kraken, alias Kraken justifiés par catalogue | Règles d'identité reprises (USD ≠ USDT, alias explicites). Non importé : il ne couvre que le Spot, et R0 doit couvrir le Perpétuel |
| `bbo_pilot.py`, `bbo_book.py`, `bbo_wire.py` | Pilote BBO borné BTC puis ATOM, MEXC protobuf diff + REST snapshot, Kraken WS v2 `book` profondeur 10 avec CRC32, preuves brutes scellées, rejeu hors ligne | **Non réimplémenté, non importé** (module chargeant `socket`/`ssl`). Ses classes de couverture (0,95 / 0,80 / 0,50) sont reprises et un test vérifie l'égalité des valeurs. Le chemin Kraken WS v2 + CRC32 est cité comme **compatibilité technique** L2 de la référence, jamais comme intégrité prouvée |
| `bbo_history.py` | Publication historique compacte `bbo-composite-history/1.0.0` | Modèle de compacité ; non importé |
| `coverage.py` | Couverture par instrument MEXC/Kraken Spot depuis une sélection du Moniteur | Catégories complémentaires ; non importé (Spot seul, sélection amont) |
| `pilot.py`, `composite.py`, `m5.py` | Pilote dernier trade L3 et composite M5 | Constantes `VIABLE_RATIO`/`PARTIAL_RATIO` reprises et testées |

### 2.3 Autres producteurs et contrats d'observation

| Composant | Ce qu'il fait | Position R0 |
|---|---|---|
| `observability/venue_quote_comparison.py` | Comparaison hors ligne de cotations normalisées, `InstrumentKey` multi-type | Vocabulaire `UNRESOLVED` et distinction des types de marché repris |
| `observability/market_venues/` | Captures publiques US (#539–#548), admission, publication | Non concerné (autres venues) |
| `observability/market_flow/` (Flux) | Contrat Flux V1 : trades, L2, heatmap, intervalles ; `perception.py` (CH1-01) sur #604 seulement | Hors R0 : Flux est un étage aval (« Intelligence de marché »). Vocabulaire qualité à 7 états de CH1-01 compatible mais non importé (pas sur main) |
| `observability/flux_collection_pilot/` | Collecte Flux Coinbase pilotée | Hors R0 (collecte) |
| LMI (`market_microstructure_*`, lecteur API) | Microstructure MEXC futures ; défauts connus (profondeur, « cancellation_rate », UNKNOWN→0) | **Aucune entrée LMI** dans le Radar (décision CH1 du 2026-11-23) |
| `observability/market_radar_snapshot.py` | Snapshot CryptoRadar : classement par confiance de signaux `radar_bot` | **Non réutilisé** : classement de signaux de trading ; le Radar R0 n'est pas un détecteur de signaux |
| Footprint | Fixture statique | Hors R0 |

### 2.4 Frontend (chemins réels)

| Chemin | Rôle | Position R0 |
|---|---|---|
| `frontend/src/views/MarketView.tsx` | Onglets montés « Scanner » et « Microstructure » | Non modifié |
| `frontend/src/views/SymbolScanner.tsx` | « Moniteur de marché » : lignes MEXC Spot (`spot-radar/1.0.0`), volume 24 h, bid/ask `RECEIPT_ONLY`, fraîcheur LIVE/STALE | Non modifié. Donne la forme d'une future source de surveillance légère (MEXC Spot seulement) |
| `frontend/src/lib/spotRadarClient.ts` | Client GET `/api/operator/v1/spot-radar/` | Le producteur `spot-radar` **n'est pas sur main** (seul le client et une fixture `spotRadar-scanner.json` existent) |
| `frontend/src/views/ScannerUniverse.tsx`, `lib/scannerUniverseClient.ts` | Univers commun MEXC × Kraken | Non modifié |
| `frontend/src/views/MarketScanner.tsx` | Ancien scanner, servi par la preuve `legacyProof` | Non modifié |

Aucune PWA ni vue opérationnelle n'est modifiée.

## 3. Sources réellement disponibles

| Source | Disponible en source (main) | Disponible en R0 isolé |
|---|---|---|
| Catalogues publics MEXC Spot/Perp, Kraken Spot/Perp | Parseurs + producteur réseau | **Oui, par octets de fixture** au format officiel |
| Ticker/BBO MEXC Spot (`spot-radar`) | Client frontend seulement | Non : remplacé par des observations SYNTHETIC |
| BBO MEXC + Kraken Spot (BTC, ATOM) | Pilote réseau sous GO séparé, corpus `BBO-BTC-20261120T070632Z` hors dépôt | Non lu (corpus hors dépôt, admission en cours dans #604) |
| L2 complet vérifié | Kraken WS v2 profondeur 10 + CRC32 (pilote) ; Flux Coinbase | Non : statut L2 déclaré par fixture (`VERIFIED` exige une référence de preuve) |
| Trades | Pilote L3 (dernier trade), Flux | Non : compteur SYNTHETIC `TRADE_COUNT_WINDOW` |
| Données Perpétuel (prix mark, BBO) | Aucune collecte Kraken/MEXC Perp sur main | **Aucune** : uniquement fixtures |

## 4. Instruments et plateformes réellement pris en charge

- **Identité** : quatre marchés (MEXC Spot, MEXC Perpétuel, Kraken Spot,
  Kraken Perpétuel), avec contrats linéaires et inverses, par les parseurs
  Scanner V1. Le Radar ajoute un identifiant lisible par marché :
  `venue:type:BASE/QUOTE` (`kraken:spot:BTC/USDT`, `mexc:perp:BTC/USDT`,
  `kraken:perp-inv:BTC/USD`…).
- **Observation réelle** : seuls BTC/USDT et ATOM/USDT Spot ont un chemin BBO
  (pilote, GO runtime séparé). Aucun Perpétuel n'a de chemin d'observation.
- La mention « MEXC et Kraken, Spot et Perpétuel » du scanner décrit donc une
  **capacité d'identification**, pas une disponibilité d'observation.

## 5. Contrats à conserver

1. `scanner-universe/1.1.0` et ses parseurs : inchangés, importés.
2. Identité Spot `radar_composite.instruments` : règles reprises (USD ≠ USDT,
   alias explicites), aucune modification.
3. Classes de couverture des pilotes (0,95 / 0,80 / 0,50) et tolérance
   d'horloge de 5 s : reprises à l'identique, testées.
4. CH1-01 (#604) : vocabulaire qualité et règle « LIVE n'atteint VERIFIED
   qu'avec une preuve de reconstruction » respectés dans l'esprit
   (`TECHNICALLY_COMPATIBLE` ≠ `VERIFIED`) ; aucune dépendance de code.
5. Frontière d'autorité : PPL/FIN/PAPER/Advisor/Risk jamais importés.

## 6. Lacunes techniques

| Lacune | Effet | Traitement R0 |
|---|---|---|
| Pas de surveillance légère multi-marché (Perpétuel, Kraken) sur main | Aucune mesure réelle d'activité/spread hors BTC/ATOM Spot | Observations SYNTHETIC au contrat explicite ; branchement réel = mission future |
| `spot-radar` backend absent de main | Le Moniteur ne peut pas alimenter le Radar en source | Documenté ; pas de producteur créé |
| Aucune preuve d'intégrité L2 hors pilote | Critère L2 surtout `TO_QUALIFY` | Statut L2 à trois niveaux : `PROVEN / TO_QUALIFY / UNKNOWN` |
| Budgets de collecte non mesurés | Coûts inventés impossibles à justifier | Coûts `ESTIMATED` vs `MEASURED` + provenance ; budgets de production `NOT_MEASURED` |
| Gates C2-C / C2-D non définies dans le dépôt | Admission historique BTC impossible à évaluer | Référence `NOT_YET_HISTORICALLY_ADMITTED` |

## 7. Modifications minimales retenues

- **Nouveau paquet** `observability/radar_selection/` (aucun fichier existant
  modifié) : univers (sur `scanner_universe`), surveillance légère, sélection,
  préférences manuelles, terminal.
- **Fixtures** SYNTHETIC générées par `tests/radar_selection/build_fixtures.py`.
- **Tests** `tests/radar_selection/` (groupes A à F).
- **Docs** : ce rapport, le contrat `docs/contracts/CAT_R0_CONTRAT_RADAR.md`,
  le rapport de validation et le guide terminal.

## 8. Risques de duplication

| Domaine | Risque | Mesure |
|---|---|---|
| Scanner / Univers | Recréer un parseur de catalogue | Parseurs importés ; un test casse si leurs constantes divergent |
| BBO pilote | Réimplémenter carnet/CRC32 | Aucun carnet reconstruit ; le Radar lit un statut L2 et sa référence |
| Flux | Recalculer trades/CVD/heatmap | Aucun indicateur Flux ; seul un compteur d'activité borné |
| LMI | Réutiliser des mesures douteuses | Aucune entrée LMI |
| Footprint | Recalculer un profil | Aucun |
| Market Intelligence (CH1) | Créer un second vocabulaire qualité | États par critère limités (`AVAILABLE / PARTIAL / UNKNOWN / INVALID`) ; décision d'admissibilité séparée ; alignement avec CH1-01 à faire quand #604 sera fusionnée |
| CryptoRadar | Confondre sélection scientifique et signal | Aucun signal, aucune confiance, aucune direction |

Verdict R0-1 : **GO** pour un nouveau module de sélection adossé à
`scanner_universe`, sans moteur concurrent ni collecte.
