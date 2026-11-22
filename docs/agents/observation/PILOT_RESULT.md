# Pilote `data-provenance-auditor` — résultat du banc isolé

SHA analysé : `857404f8ebfbcf9df4a3f36052ab5357ea9b8d7b` · contrat
[AGENT_OBSERVATION_MISSION_V1](../../contracts/AGENT_OBSERVATION_MISSION_V1.md) ·
audit initial [2026-11-22](../../forensics/AGENT_OBSERVATION_PILOT_AUDIT_2026-11-22.md).

Statut : **banc isolé, aucun runner, non déployé.** Ce document propose une décision ;
il ne qualifie rien lui-même.

## 1. Matrice des neuf cas

Résultats attendus fixés dans `tests/agent_bench/fixtures/observation/*/expected.json`
avant exécution ; obtenus par `python3 -m agent_bench.observation.bench matrix`.
Matrice complète (constats, mesures) : [bench/matrix.md](bench/matrix.md),
[bench/matrix.json](bench/matrix.json).

| Cas | Fixture | Attendu | Obtenu | Preuve |
|---|---|---|---|---|
| A | chaîne complète et cohérente | COMPLETE, 7 maillons PROVEN, source dans le seuil | idem | `A_complete` |
| B | producteur absent | PARTIAL, PRODUCER NOT_FOUND, aval (lecteur→API→client→vue) PROVEN conservé | idem | `B_producer_absent` |
| C | lecteur sans lien prouvé | PARTIAL, STORAGE_TO_READER INCONCLUSIVE, `READER_WITHOUT_PROVEN_STORAGE_LINK` | idem | `C_reader_unlinked` |
| D | source périmée, mtime récent | `SOURCE_STALE` + `MTIME_RECENT_SOURCE_STALE`, mtime non utilisé | idem | `D_stale_recent_mtime` |
| E | jointures contradictoires | `JOIN_KEY_CONTRADICTION` (symbole/archive ; points/empreintes) | idem | `E_join_contradiction` |
| F | unité absente / incompatible | `UNIT_MISSING` + `UNIT_INCOMPATIBLE` (secondes ; nombre au lieu de chaîne) | idem | `F_unit_missing_incompatible` |
| G | entrée malformée | PARTIAL, `CAPTURE_MALFORMED`, 7 maillons prouvés conservés, fraîcheur INCONCLUSIVE (jamais « saine ») | idem | `G_malformed_capture` |
| H | chemin hors périmètre ou secret | H1 : `.env` demandé ⇒ BLOCKED avant toute lecture ; H2 : lecteur hors périmètre non lu + `.env` d'un dossier autorisé ignoré ⇒ PARTIAL | idem | `H1_env_path_in_scope`, `H2_reader_out_of_scope` |
| I | rejeu identique | doublon compté une fois : 4 observations distinctes, pas 5 | idem | `I_identical_replay` |

**10/10 cas conformes, 0 faux constat, 0 constat sans preuve**, deux exécutions par cas
avec `content_sha256` identique (horodatages séparés dans `run`).

Contrôles additionnels (`tests/agent_bench/test_observation_bench.py`, 53 tests) :
hook d'audit Python sur chaque ouverture de fichier et chaque socket (aucune ouverture
hors périmètre, aucune socket) ; arbre de travail identique octet pour octet après la
mission (aucune écriture) ; 13 refus d'entrée (profil, identité, empreinte, glob, `..`,
absolu, clé, `secrets/`, agent non qualifié…) ; budget épuisé ⇒ FAILED ; aucun mot
d'auto-certification dans les rapports ; contrôle du contrôle (le hook voit une
ouverture hors périmètre).

## 2. Rapport du pilote sur le dépôt réel

Entrée : [examples/pilot_mission.json](examples/pilot_mission.json) · sortie :
[examples/pilot_report.json](examples/pilot_report.json) (`content_sha256`
`734cd723…` ; le test de non-régression compare le contenu hors `mtime`).
Statut : **PARTIAL** (un maillon INFERRED).

### Maillons prouvés

| Maillon | Preuve |
|---|---|
| SOURCE → producteur | `bbo_pilot.py:181,182` (`events.jsonl`, `frames.bin` en ajout), `:244` (`manifest.json` via `os.replace`), `:994` (`window_{}_primary.json`), `:1045` (`summary.json`) ; relus par `bbo_history.py:77-80,91,149` |
| Producteur | `bbo_history.py:31` `SCHEMA_VERSION`, écriture `main` `:308` |
| Producteur → stockage | chemin fourni par `--out` (`bbo_history.py:298`) |
| Lecteur → API | `app.py:646` route, `:648` `_bbo_history_reader.read()`, `:32` import de `BboHistoryReader` |
| API → client | endpoint identique `app.py:646` / `bboHistoryClient.ts:6`, identifiant `:43` |
| Client → affichage | `BboCompositeHistory.tsx:7` importe `fetchBboHistory` ; rendue par `SpotRadarMap.tsx:2` |

### Maillon seulement inféré

**Stockage → lecteur (INFERRED).** Le lecteur valide le même schéma
(`bbo_history_reader.py:16` importe `validate_history`) mais lit
`OPERATOR_BBO_HISTORY_PATH` alors que le producteur écrit vers `--out`. Le fichier commun
n'est relié que par la configuration de déploiement : **mesure runtime nécessaire**.

### Fraîcheur effective

`FRESHNESS_CANONICAL` : heure source = fin de fenêtre la plus récente
(`2026-11-19T22:55:00Z` dans la fixture), heure d'écriture = `generated_at_utc`
(`2026-11-20T08:00:00Z`), mtime consigné mais **non utilisé**. Aucun seuil déclaré
(publication historique, `HISTORICAL_NOT_LIVE`) ⇒ verdict `AGE_REPORTED_NO_THRESHOLD`.

### Doublons et rejeu établis par le code

- `RISK_NON_ATOMIC_OVERWRITE` (PROVEN) : `bbo_history.py:308` écrase la publication par
  `write_bytes`, sans renommage atomique ; le lecteur limite le risque en refusant un
  fichier modifié pendant la lecture (`bbo_history_reader.py:60`, SUPPORTED).
- `RISK_WALLCLOCK_IN_PUBLICATION` (PROVEN) : `bbo_history.py:161` lit l'horloge ; deux
  constructions de la même preuve diffèrent par `generated_at_utc`.
- `UPSTREAM_APPEND_ONLY_LOG` (PROVEN) : journaux amont ouverts en ajout (`bbo_pilot.py:181,182`).
- `GUARD_DUPLICATE_REJECTED` (SUPPORTED) : `PAIR_DUPLICATE` (`bbo_history.py:213`).
- Capture : 5 enregistrements, 5 observations distinctes, 0 rejeu, 0 conflit de clé ;
  jointures `pair ⊂ archive_name` et `windows ≡ window_sha256` cohérentes ; unités conformes.

### Mesures runtime distinctes nécessaires

1. Sur l'hôte : valeur de `OPERATOR_BBO_HISTORY_PATH` vs chemin passé à `--out`, puis
   sha256 du fichier servi vs publication.
2. Manifest scellé de la collecte (heures, symboles, reconnexions) : la connexion
   effective à `wss://wbs-api.mexc.com/ws` et `wss://ws.kraken.com/v2` n'est que déclarée
   dans le code (`bbo_pilot.py:74,75`).
3. Doublons de lignes et ruptures de séquence dans `events.jsonl` de la capture scellée.

## 3. Mesures de ressources

| Exécution | Durée | Mémoire Python max (tracemalloc) | Sources lues | Constats justifiés | Faux | Non conclusifs |
|---|---|---|---|---|---|---|
| Pilote dépôt réel | 0,30–0,37 s | 8,5 Mo | 9 (174 196 o, profil inclus) | 8/8 | 0 connu | 1 maillon INFERRED |
| Cas A–I (par cas) | 0,3–22 ms | 0,43 Mo (H1 : 1,6 Ko) | 0–9 | 44/44 au total | 0 | B 5, C 1, H2 1 |
| Processus `bench matrix` | — | RSS max ≈ 21 Mo | — | — | — | — |

Valeurs d'une machine de développement (conteneur), indicatives et non comparables
entre hôtes. **Aucun gain de productivité n'est annoncé** : il n'existe ni tâche
témoin, ni mesure du temps humain équivalent.

Faux constat observé pendant la mise au point : la première version attribuait la route
au décorateur `app.get` (lecteur « `fastapi.py` »). Repéré à la relecture humaine du
rapport pilote, corrigé (seul le corps du handler compte). Réintroduire l'erreur fait
échouer 9 des 10 cas : la régression est couverte.

## 4. Limites

Analyse statique à un saut d'indirection ; chemins dynamiques ⇒ INCONCLUSIVE ; motifs
TypeScript (pas de parseur) ; capture = fixture synthétique, pas la publication VPS ;
fixtures écrites par le même auteur que l'auditeur (indépendance faible, A0 §8) : une
revue humaine des attendus reste nécessaire.

## 5. Décision proposée

**Pilote recevable comme banc et contrat**, sous trois réserves à trancher :
(1) revue humaine des neuf attendus, (2) validation de la frontière
cartographe/architecte, (3) accord pour que le maillon INFERRED du pilote fasse l'objet
d'une mesure runtime READ-ONLY séparée. Il n'est **pas** recevable comme agent
opérationnel : aucun voyant ne change.

Ordre conseillé : `repository-cartographer` → `observability-cartographer` →
`repo-architect` (voir [fiches](MISSION_SHEETS.md)).

## 6. Conditions avant tout branchement VPS (non remplies, rien n'est déployé)

1. Décision humaine explicite (#284 / #286) autorisant un runner Observation et sa phase
   (A6 sandbox non ouverte).
2. Identité de runner stable (`runner_id`) et `AgentSpec` validée par PR humaine ; le
   registre #597 passé par sa propre gate.
3. Exécution sous un utilisateur système sans secret, sans réseau sortant, en lecture
   seule sur un checkout **séparé** du runtime gelé (`116634be…`), jamais dans
   `/opt/cat-app` ni sur les données PAPER/PPL/FIN.
4. Missions et captures uniquement par fichiers à empreinte ; aucune lecture directe
   des JSONL de production sans mission READ-ONLY dédiée.
5. Rapports écrits par un écrivain gouverné, append-only, hors répertoires Advisor/PPL/FIN
   (A1 AW-01), avec `content_sha256` et `report_sha256`.
6. Preuve d'activité conforme à #597 (invocation datée + résultat corrélé + heartbeat)
   exposée par une API GET distincte ; sans elle les voyants restent gris.
7. Banc vert au HEAD exact déployé, CI complète (aujourd'hui l'empilement #591→#597
   n'exécute pas la CI complète), revue indépendante.
8. Rollback documenté : arrêt du runner sans effet sur la collecte, l'Advisor ou les
   services opérateur.
