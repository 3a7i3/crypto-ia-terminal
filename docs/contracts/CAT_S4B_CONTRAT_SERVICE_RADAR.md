# CAT S4-b — Service GET du Radar : `radar-projection-service/1.0.0`

Statut : **SOURCE PROOF, SYNTHETIC, hors VPS.** GO opérateur du 2026-11-25 (20:47Z) pour S4-b
uniquement. Ce document complète le contrat S4-a
([CAT_S4A_CONTRAT_PROJECTION_RADAR.md](CAT_S4A_CONTRAT_PROJECTION_RADAR.md)) ; il ne le modifie pas.

Décisions opérateur appliquées :
- S4-a validé, fusionné (#612, `main@a2ec703`) ;
- **E1 : option 2 acceptée**, jointure par provenance des catalogues bruts, **sans assimilation
  à une identité des univers** ;
- règles permanentes CAT-DATA-01 (unicité des données) et CAT-PREPROD-01 (préproduction HTTP
  isolée), proposées comme amendement à CAT-GOV-SDLC-01 #578.

## 1. Chaîne

```text
export figé (octets, fichier configuré)
   └─ lecteur borné (bounded_file) ──▶ project_bytes(raw)  [vérificateur S4-a, seul producteur]
                                            │ refus typé ─▶ 503 RADAR_PROJECTION_REFUSED + refusal_code
                                            ▼
             corps = {"projection": <octets de project_bytes, inchangés>, "service": <enveloppe>}
                                            ▲
             Scanner : ScannerUniverseReader existant (même publication que /scanner-universe)
```

Route : **`GET /api/operator/v1/radar-projection`**. C'est la seule route ajoutée. Elle est en
lecture seule ; POST donne 405.

Configuration :

| Variable | Rôle | Défaut |
|---|---|---|
| `OPERATOR_RADAR_EXPORT_PATH` | chemin de l'export Radar (sortie de la commande `export`) | absent ⇒ `RADAR_PROJECTION_NOT_CONFIGURED` |
| `OPERATOR_RADAR_PROJECTION_MAX_AGE_S` | âge maximal de la publication (E2), entier > 0, au plus 7 jours | 900 s, **provisoire, non calibré** |
| `OPERATOR_SCANNER_UNIVERSE_PATH` | publication Scanner existante, réutilisée pour E1 | inchangé |

## 2. Corps servi

Le corps est exactement :

```text
{"projection":<project_bytes(raw) sans le "\n" final>,"service":<canonical(service)>}
```

- Les octets de la projection sont **recopiés tels quels** : le service ne construit, ne complète
  et ne réécrit jamais une projection (frontière S4A-RV-03).
- Les clés sont triées (`projection` < `service`), donc le corps entier est lui-même la forme
  canonique de `{"projection", "service"}`. Un client peut vérifier `projection_sha256`.
- `Cache-Control: no-store` ; `Content-Type: application/json`.

### Enveloppe `service`

| Champ | Contenu |
|---|---|
| `schema` | `radar-projection-service/1.0.0` |
| `projection_schema`, `projection_sha256` | recopiés de la projection |
| `status` | `PRESENTATION_ONLY_NOT_AN_ADMISSION_NOT_A_RUNTIME_AUTHORIZATION` |
| `scope` | `evidence_kind` (toujours `SYNTHETIC` : S4-a refuse le reste), `runtime_proof: false`, `statement: SYNTHETIC_SOURCE_PROOF_ONLY_NOT_RUNTIME_PROOF` |
| `publication` | E2, section 3 |
| `catalogue_provenance` | E1, section 4 |

## 3. E2 — fraîcheur de la publication

La fraîcheur porte sur **la publication servie** (le fichier), jamais sur une observation. La
fraîcheur d'observation par instrument reste dans la projection (`instruments[].observation`).

| Champ | Sens |
|---|---|
| `published_ms`, `published_basis` | heure de modification du fichier lu (`FILE_MODIFICATION_TIME`) |
| `served_ms` | horloge du serveur au moment du service |
| `age_ms` | `served_ms − published_ms` |
| `max_age_ms`, `max_age_basis` | `CONFIGURED`, `PROVISIONAL_DEFAULT` ou `PROVISIONAL_DEFAULT_INVALID_CONFIGURATION` |
| `state` | `FRESH` si `−5 000 ≤ age ≤ max_age` ; `STALE` si `age > max_age` ; `PUBLISHED_IN_FUTURE` si `age < −5 000` |
| `current` | `true` seulement si `FRESH` |

Une publication `STALE` reste servie, marquée `current: false`, et sa projection est identique
à l'octet près. Une interface (S4-c) ne doit jamais la présenter comme courante. Le temps n'est
lu que dans l'enveloppe : la projection reste une fonction pure des octets (SA8).

## 4. E1 — relation de provenance des catalogues (option 2)

Pour chacun des quatre marchés (`MEXC_SPOT`, `MEXC_PERPETUAL`, `KRAKEN_SPOT`,
`KRAKEN_PERPETUAL`), on compare les dictionnaires d'empreintes brutes :
`projection.scanner_universe.catalogue_sources[market].raw_sha256` et
`sources[market].raw_sha256` de la publication Scanner servie.

| `markets[].relation` | Condition | `reason` |
|---|---|---|
| `SAME_CATALOGUE_BYTES` | les deux existent, non vides, identiques | `null` |
| `DIFFERENT_CATALOGUE_BYTES` | les deux existent et diffèrent | `null` |
| `NOT_COMPARABLE` | sinon | `SCANNER_PUBLICATION_UNAVAILABLE`, `RADAR_SOURCE_ABSENT`, `SCANNER_SOURCE_ABSENT`, `CATALOGUE_DIGESTS_EMPTY` ou `CATALOGUE_UNAVAILABLE` |

`relation` globale : `CATALOGUE_PROVENANCE_UNKNOWN` dès qu'un marché n'est pas comparable ;
sinon `CATALOGUE_PROVENANCE_MATCH` si les quatre sont identiques, sinon
`CATALOGUE_PROVENANCE_MISMATCH`. Jamais un succès par défaut.

Champs fixes : `statement: CATALOGUE_BYTES_PROVENANCE_ONLY_NOT_UNIVERSE_IDENTITY` ;
`radar_scanner_universe_sha256` recopie `projection.scanner_universe.sha256`, qui **reste `null`**
(`NOT_AVAILABLE`). `scanner_publication` donne la publication comparée (version, statut, instant,
et `scanner_universe_sha256_of_compared_publication`, l'empreinte **du Scanner**, nommée ainsi
pour ne jamais passer pour celle du Radar). Si la publication Scanner est illisible :
`scanner_publication: null` et `scanner_error_code` (code du lecteur Scanner).

`CATALOGUE_PROVENANCE_MATCH` veut dire seulement : « le Radar a évalué à partir des mêmes octets
de catalogue que ceux de la publication Scanner servie ». Ce n'est pas « même univers ». Les
fixtures R0, reconstruites par canonicalisation, ne concordent jamais avec des octets réels ;
seul un lot R1-B, qui garde les octets d'origine, peut concorder. La fraîcheur des sources Scanner
est indiquée par `scanner_source_current`, sans changer la comparaison des octets.

La jointure des instruments (identité exacte `market_id`, `native_symbol`, `contract_type`,
`quote`, `settlement_asset`) n'est pas faite côté serveur : elle appartient à S4-c, sur ces deux
réponses, et un instrument sans entrée reste « Non évalué ».

## 5. Erreurs typées

Toujours `503`, `Cache-Control: no-store`, jamais un Radar vide :

| `error_code` | Cas |
|---|---|
| `RADAR_PROJECTION_NOT_CONFIGURED` | chemin absent |
| `RADAR_PROJECTION_MISSING` | fichier absent |
| `RADAR_PROJECTION_INVALID_PATH` | lien symbolique sur le chemin, ou pas un fichier régulier |
| `RADAR_PROJECTION_UNREADABLE` | erreur de lecture |
| `RADAR_PROJECTION_TOO_LARGE` | plus de 1 000 001 octets (borne S4-a) |
| `RADAR_PROJECTION_CHANGED_DURING_READ` | fichier modifié pendant la lecture |
| `RADAR_PROJECTION_REFUSED` + `refusal_code` | refus du vérificateur S4-a (code seul, sans détail d'entrée) |

## 6. Gates SB1 à SB10 (tests `tests/radar_projection/test_s4b_service.py`)

| Gate | Preuve |
|---|---|
| SB1 Projection servie à l'octet près | 15 cas (4 fixtures + 1 lot × 3 missions) ; corps canonique ; `projection_sha256` |
| SB2 Lecture bornée et typée | non configuré, absent, dossier, lien, parent lien, trop grand, modifié pendant la lecture |
| SB3 Refus du vérificateur conservés | archive pré-R-REF, entrée vide, UTF-8 invalide, flottant, contrefaçon rescellée, LIVE |
| SB4 E2 | bornes FRESH / STALE / PUBLISHED_IN_FUTURE ; configuration ; projection inchangée |
| SB5 E1 | MATCH (lot R1-B ↔ rejeu du Scanner sur les mêmes octets), MISMATCH, UNKNOWN (Scanner absent, non configuré, digests vides, catalogue indisponible, côté absent) ; R0 jamais MATCH ; `sha256` de la projection reste `null` |
| SB6 Portée SYNTHETIC explicite, autorité nulle | enveloppe `scope` ; autorité de la projection |
| SB7 Déterminisme | mêmes octets et même instant ⇒ même corps |
| SB8 Isolation du lecteur | imports fermés ; aucun moteur, aucun réseau, aucune écriture |
| SB9 Route HTTP | 200 et corps, 405 sur POST, 503 typés, route Scanner inchangée (FastAPI) |
| SB10 Aucun nouveau producteur | une seule route ; l'API n'importe pas le moteur Radar |

## 7. Ce que S4-b ne fait pas

Aucun collecteur, timer ou écriture ; aucun recalcul de score, de décision ou de rang ; aucun
frontend (S4-c) ; aucun déploiement ; aucune donnée réelle.

## 8. Prérequis de l'alimentation réelle (non contournés)

1. **Un producteur d'export gouverné** sur la machine autorisée : la commande `export` du moteur
   sur un lot R1-B construit à partir des relevés réels du Scanner (`/var/lib/cat-scanner-universe/runs/*`),
   avec écriture atomique d'un seul fichier. Ce n'est pas un nouveau collecteur : il réutilise les
   octets déjà collectés. GO distinct requis.
2. **Évidence non SYNTHETIC** : S4-a refuse `HISTORICAL` et `LIVE`. Une projection de données réelles
   exige une révision versionnée du contrat et les gates C2-C et C2-D.
3. **Observations BBO/L2 réelles** pour les missions qui en ont besoin (`needs_bbo`), aujourd'hui
   synthétiques dans le lot R1-B.
4. **Cadence et âge maximal calibrés** (E2) : le défaut de 900 s est provisoire.
5. **Budgets de production mesurés** (aujourd'hui `NOT_MEASURED`).
6. **Authenticité** du producteur (signature ou canal de confiance) : décision distincte.
7. **Déploiement** : préproduction CAT-PREPROD-01 sur la base exacte de production, puis GO runtime G7.
