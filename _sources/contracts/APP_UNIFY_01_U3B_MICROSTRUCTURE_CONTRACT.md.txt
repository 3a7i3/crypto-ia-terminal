# APP-UNIFY U3b — MarketMicrostructureSnapshot

Issue #334 ; parent #323 ; #286 ACTIVE.
Baseline U3a fusionnée : `106b0ac16101847cb2aab742797d6fca2da29e58`.

## Architecture passive

`lmi_live_state.json` existant → producteur one-shot externe
`observability/market_microstructure_snapshot.py` → artifact atomique
`market_microstructure_snapshot.json` → reader strict → GET
`/api/operator/v1/market-microstructure` → validation TS → Marché / Microstructure.

Aucune importation du moteur LMI, de son adaptateur historique, de l'Advisor,
exchange, PPL, risk ou sizing dans cette chaîne de production/transport. Le
producteur ne fait que lire un fichier déjà produit, sélectionner les mesures,
convertir les unités de présentation et publier une capture indépendante.
Aucun service/timer ou boucle n'est ajouté. Source/output sont injectables
par CLI, sans modification de configuration :

```sh
python -m observability.market_microstructure_snapshot --source <sidecar-local> --out <artifact-local>
```

Cette commande décrit la capacité source ; elle ne demande pas de l'exécuter
sur le VPS. Le reader ne lit jamais le sidecar LMI et ne lance pas le producteur.

## Contrat fermé 1.0.0

Identité : product `MarketMicrostructureSnapshot`, domain `market_microstructure`,
authority `OBSERVATIONAL_TELEMETRY`, mode `READ_ONLY`. Aucun champ d'exécution.

Enveloppe : generated_at_utc, source_updated_at_utc, SHA256 des octets source,
exchange mexc/binance, provenance globale contractSize api/fallback/mixed/unknown,
dégradation déclarée boolean/null, compteur source PressureFields int/null,
couverture requested/streamable/observed/unavailable, lignes watchlist.
Le SHA256 identifie les octets lus ; ce n'est pas une attestation runtime.

Chaque ligne contient symbol, stream_requested, disponibilité OBSERVED ou
UNAVAILABLE, raison fermée SOURCE_UNAVAILABLE/NO_OBSERVATION ou null, timestamp
de PressureField, état LMI, confidence 0–1, prix, variation bps, pressions achat/
vente %, flux achat/vente/total USD, fenêtre flux ms, résistance USD/bps,
fragilité 0–1 et notable boolean/null.

Les mesures sont copiées depuis les champs PressureField existants. Seules les
transformations de présentation sont : ratio × 100 et complément pour les
pressions ; somme des deux flux pour le total. Aucun score, classifier ou
modèle n'est recalculé. Pas d'arrondi supplémentaire ni de clamp résistance
0–100 : le modèle source définit USD/bps avec plancher déplacement 0,01 bps.
Le total est null si l'un des deux flux manque. Prix/confiance zéro observés
restent zéro ; absent/null reste null. Le frontend ne calcule aucune mesure.

Notable reprend la règle d'affichage historique : état non quiet et confiance
≥ 0,6. Absence d'état/confiance → null. C'est une observation à la capture, pas
un événement nouveau ni un historique WS. PressureFields cumulés viennent
uniquement de stats.events ; un compteur absent n'est pas zéro.

Watchlist et stream_watchlist modernes sont exigées explicitement, uniques,
≤100 symboles chacune, streamable subset de requested. Aucun fallback depuis
les anciennes ghost states. Seules les lignes de la watchlist sont publiées,
y compris les symboles indisponibles ; aucune troncature silencieuse. La
couverture est comptée à partir de ces disponibilités explicites, sans utiliser
les compteurs de fraîcheur figés du source. Les raisons brutes peuvent porter
des détails d'exception ; elles sont ramenées au vocabulaire fermé.

Un état observé sans timestamp reste OBSERVED avec temps null. Il ne devient
pas FRESH depuis un age_ms, une mtime ou le temps de publication. Les mesures
optionnelles absentes restent NOT_AVAILABLE. Les types/valeurs malformés,
future timestamps ou populations incohérentes empêchent la publication.

La provenance contractSize est globale à la capture source : elle ne certifie
pas chaque symbole. Champ source manquant ou `n/a` → unknown ; liste de
dégradation absente → null, liste explicitement vide → false. Les flux USD
restent affichés avec cette limite ; fallback/mixed dégradés sont visibles.

## Temps et erreurs

Tous les timestamps publiés sont UTC à précision milliseconde. Le timestamp
source timezone-aware est normalisé en UTC ; l'observation vient exclusivement
de timestamp_ms. Observation ≤ source ≤ génération ≤ lecture. Temps naïf,
future ou incohérent refusé. Fraîcheur au seuil 15s (égalité FRESH), selon
la convention LMI existante, mesurée à chaque GET à partir des timestamps.

Le reader ajoute read_at_utc, source_age_s et freshness_classification global
FRESH/STALE, et observation_age_s + FRESH/STALE/UNKNOWN/NOT_AVAILABLE par ligne.
Il ne réécrit aucune mesure. Une republication ne rajeunit pas la source. Une
source récente n'efface pas un symbole STALE ; une source STALE ne rend jamais
une ligne FRESH. FRESH concerne la capture/PressureField, pas la santé du
service ni une certification exchange live. L'heure de lecture est visible
et les valeurs demeurent des faits à cette lecture, pas une vue atomique avec
le Scanner ou l'Advisor.

Le hook fait des GET sérialisés toutes les 5s après résolution, timeout réseau
5s, abort sur unmount, aucun chevauchement. Erreur remplace le succès précédent.
Python/TS valident les champs fermés, types, bornes, horodatages et cohérence
des comptes/totaux/pressions/notable/fraîcheur, sans autorité scientifique.

Lecture JSON : fichiers réguliers non-symlink, O_NONBLOCK, max source 512 KiB /
artifact 256 KiB ; duplicate keys, NaN et constantes interdites. Écriture
atomique via unique temp + replace ; collision source/output refusée ; échec
préserve l'ancien artifact et nettoie le temp.

GET échoue 503 avec code fermé MICROSTRUCTURE_MISSING, INVALID_ARTIFACT,
INVALID_SCHEMA ou FUTURE_TIMESTAMP (préfixe MICROSTRUCTURE_). Pas de chemin,
stderr ou données source brutes dans l'erreur. Aucun compteur synthétique.

## Matrice de parité LMI

| Dashboard historique | U3b | Limite explicite |
|---|---|---|
| lmi_status coverage/running | populations source et fraîcheurs distinctes | aucune inférence process running depuis fichier non vide |
| lmi_table état/confiance/prix | copiés, null si absents | pas de quiet/prix zéro inventés |
| buy/sell pressure et flux | projection des mesures source | précision conservée, provenance USD globale affichée |
| résistance / fragilité | mesures source et unités | pas de clamp/score inventé |
| lmi_symbol détail | cartes observationnelles avec fenêtre flux | liquidité détaillée/state_components/raw hors tranche |
| lmi_events | filtre notable à la capture | inclut historique étiqueté ; pas de journal d'événements |
| stale basé sur age_ms figé | temps source et PressureField à chaque GET | pas de LIVE revendiqué |
| ghost states legacy | exclus par watchlist explicite | ancien sidecar incomplet rejeté, pas population fabriquée |

Scanner, LMI et Advisor ont des erreurs indépendantes. Direction garde ses
six sources existantes ; U3b ne fabrique aucune synthèse globale supplémentaire.
Le retrait CryptoRadar reste interdit : consommateurs, parité restante,
disponibilité runtime et rollback transport/service à certifier séparément.

## Preuves et frontières

Tests producer/reader/API, corruption, absent/null/zéro, temps/source arrêtée,
publication répétée, atomicité, collision, fichiers bornés, GET-only, frontend
strict, polling/timeout/abort, sources indépendantes. Fixture M cross-stack
utilise des états LMI synthétiques et les vrais publisher/artifact/reader/API.
Captures desktop/mobile : fresh/stale/missing/invalid/network, degraded units,
unknown timestamps, populations/empty, absence d'overflow et mutations.

SOURCE ONLY : aucun déploiement/VPS, restart Advisor, modification LMI engine,
service/timer, PPL/FIN/epoch/config/risk/sizing/Watchdog/exchange. #286 ACTIVE.
Rollback source : revert de la PR U3b, suppression de la consommation de cette
projection ; aucun retrait de producteur ou service autorisé par ce rollback.
