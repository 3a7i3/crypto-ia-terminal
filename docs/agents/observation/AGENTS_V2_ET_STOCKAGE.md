# Agents d'observation restants — banc v2, exécuteur commun, dossier par agent

Statut : **SOURCE SEULEMENT**. Rien n'est installé : aucun utilisateur, aucun dossier, aucune
unité, aucun timer sur le VPS. Le Repository Cartographer installé (le 22/11) garde exactement
son comportement : l'exécuteur l'appelle par défaut et son dossier ne change pas. Registre
Système : `wiring_status` reste `NOT_WIRED` et `runner_id` reste `null` pour les trois profils.

Fiche de départ : fiches techniques du 22/11 (document projet). Contrat :
[AGENT_OBSERVATION_MISSION_V1 §10](../../contracts/AGENT_OBSERVATION_MISSION_V1.md).

## 1. Les quatre agents

| Agent | Question | Contrat | Runner proposé | Dossier de stockage (VPS) | Rythme proposé |
|---|---|---|---|---|---|
| `repository-cartographer` | `REPOSITORY_MAP` | v1 | `obs-repo-cartographer-ro-01` (installé) | `/srv/cat-obs/reports` (existant) | suivi de main |
| `data-provenance-auditor` | `DATASET_PROVENANCE_CHAIN` | v1 | `obs-data-provenance-ro-01` | `/srv/cat-obs/agents/data-provenance-auditor` | suivi de main |
| `observability-cartographer` | `METRIC_SURFACE_MAP` | **v2** | `obs-observability-ro-01` | `/srv/cat-obs/agents/observability-cartographer` | suivi de main |
| `repo-architect` | `CHANGE_IMPACT` | **v2** | `obs-repo-architect-ro-01` | `/srv/cat-obs/agents/repo-architect` | à la demande |

Source de vérité : [`agent_bench/observation/agents.py`](../../../agent_bench/observation/agents.py)
(`python3 -m agent_bench.observation.agents list`).

## 2. Dossier de stockage d'un agent

Règle données (Mathieu, 22/11) : les rapports restent sur le disque du VPS, jamais dans GitHub ;
valeur momentanée, `keep_last 20`, pas d'archive. Domaine `observation-reports`, autorité
`OBSERVATION`, `git_policy = NEVER`.

```text
<dossier>/
  MANIFEST.json            identité, disposition, rétention     agents manifest --agent X --write
  summary.json             résumé borné des preuves             agents summary  --agent X --write
  locks/<runner_id>.lock   verrou noyau de l'exécuteur
  runs/<mission_id>/<AAAAMMJJThhmmssZ>_<invocation_id>.json      une enveloppe par passage
  mission/                 mission dérivée et pointeur <agent_id>.mission (suivi de main)
```

Pour l'inventaire « Stockage CAT » (fait côté GPT) : chaque dossier a le même modèle que
`/var/lib/cat-storage-inventory/storage_inventory.json`, un petit JSON lisible :

- `MANIFEST.json` (`cat.observation.agent-storage.v1`) : agent, question, runner, dossier, rétention.
- `summary.json` (`cat.observation.agent-storage-summary.v1`) : `readable`, `reason`, `missions`,
  `envelopes`, `bytes`, `latest{mission_id, file, state, result_status, started_utc, ended_utc,
  content_sha256}`. Une panne de lecture donne `readable=false` et un motif, **jamais des zéros**.
  Au-delà de 200 entrées, refus explicite `REPORTS_DIR_OVERFLOW` (même borne que l'exécuteur).

Un dossier par agent évite le piège relevé dans les fiches : avec un `runs/` partagé, la borne de
200 entrées serait atteinte plus vite et ferait passer les agents au rouge.

## 3. data-provenance-auditor

Inchangé dans son analyse (pilote, fixtures A–I). Nouveau : il passe par l'exécuteur commun
(`--agent-id data-provenance-auditor`), qui vérifie le checkout, publie l'enveloppe et accepte son
format de rapport (`sources_consulted`, profil de mission). Borne de fichiers : **60** (la chaîne
traverse producteur, lecteur, route, client, vue et capture ; le pilote en lit 8 sur un budget de 50).
Capture en V1 : `COMMITTED_FIXTURE` seulement ; une capture de production reste une mission séparée.

## 4. observability-cartographer (`METRIC_SURFACE_MAP`)

Question : pour **une** vue (`surface_path`, `.ts`/`.tsx` dans le périmètre), quelles métriques sont
affichées, quel code serveur les produit, et le frontend recalcule-t-il une valeur d'autorité ?

Champs : `surface_id`, `surface_path`, `text`, `upstream_reports` (rapports DPA **cités** par
`content_sha256`, jamais relus). Budget ≤ 30 fichiers, pas de capture.

| Règle | Constat |
|---|---|
| Champ snake_case lu par la vue, produit par une seule clé littérale de dict Python du périmètre | `CANONICAL_EXISTING` (`SUPPORTED`) |
| Produit dans plusieurs fichiers | `DERIVED` |
| Calculé dans ≥ 2 fichiers avec ≥ 2 formules | `DUPLICATED` + `DUPLICATED_CALCULATION` (`PROVEN`) |
| Aucun producteur dans le périmètre | `SOURCE_UNRESOLVED` + inconnue `METRIC_SOURCE_NOT_IN_SCOPE` |
| Le frontend calcule sur PnL/equity/balance/capital/rank/score/verdict | `FRONTEND_RECALCULATES_AUTHORITY` |
| `?? 0` / `\|\| 0` | `NULL_ZERO_AMBIGUITY` (UNKNOWN ≠ 0) |
| Nom sans unité | `UNIT_NOT_DECLARED` (`INFERRED`, faible) |
| Route lue par le client non servie dans le périmètre | inconnue `ROUTE_NOT_IN_SCOPE` |

Hors périmètre : chaîne d'un dataset (DPA), cycle de vie des messages Telegram, toute observation
runtime. Exemple réel : [`observability_surface_mission.json`](examples/observability_surface_mission.json)
(vue Stockage) → `COMPLETE`, 9 métriques, route `/api/operator/v1/storage` reliée à `app.py`.

## 5. repo-architect (`CHANGE_IMPACT`)

Frontière retenue : **prospectif, sans extraction propre**. Il lit le diff base → SHA analysé et les
fichiers modifiés, et **cite** la carte du cartographe de la base (`upstream_map`). Profil réécrit
(`.github/repo-architect.agent.md`, en-tête fermé, `tools: ["read","search"]`) ; blob mis à jour
dans le registre, statut `REVIEW_REQUIRED` conservé jusqu'à la revue humaine.

Champs : `change_id`, `text`, `base_sha`, `changed_paths` (= `read_paths`), `diff_sha256`,
`upstream_map` (`{agent_id: repository-cartographer, content_sha256, analysed_sha = base_sha,
mapped_paths}` ou `null`). L'exécuteur recalcule le diff avec la même commande git que
`change_mission` et refuse avant verrou si l'empreinte diffère (`DIFF_FINGERPRINT_MISMATCH`).

Frontières signalées (liste versionnée dans `repo_architect.py`) : `FROZEN_OBJECT_TOUCHED`,
`PPL_AUTHORITY_TOUCHED`, `FIN_AUTHORITY_TOUCHED`, `RUNTIME_PATH_TOUCHED`, `RESEARCH_TO_ACTIVE_PATH`,
`FRONTEND_RECALCULATES_AUTHORITY`, plus `MISSING_TESTS`. Sans carte ou hors zone cartographiée :
`PARTIAL` (`REPOSITORY_MAP_NOT_PROVIDED`, `DIFF_OUTSIDE_MAPPED_ZONE`), **jamais « sans risque »**.
Aucun rapport ne vaut autorisation de fusion.

Préparer une mission : `python3 -m agent_bench.observation.change_mission --repo <checkout> --base <sha>
--head <sha> --change-id <slug> --text "…" [--upstream-map carte.json]`. Exemple réel :
[`repo_architect_change_mission.json`](examples/repo_architect_change_mission.json) (commit c823cec1,
suivi de main du cartographe) → `PARTIAL`, aucune frontière, carte non fournie.

## 6. Exécuteur commun

```text
python3 -m agent_bench.observation.executor --agent-id <agent> --mission <mission.json> \
  --checkout <checkout au code_sha> --reports <dossier de l'agent> --runner-id <runner> \
  --code-sha <sha> --analysed-sha <sha> [--analysed-tree <arbre>]
```

Mêmes garanties que pour le cartographe (contrat d'invocation v1) : vérification du checkout et des
modules exécutés, verrou `flock`, publication `os.link` sans écrasement, `ABANDONED` après arrêt
brutal. `--agent-id` vaut `repository-cartographer` par défaut. Le suivi de main écrit un pointeur
par agent (`<agent_id>.mission`) et refuse `CHANGE_IMPACT`.

## 7. Matrices (attendu écrit avant exécution)

### observability-cartographer

| Cas | Titre | Attendu | Obtenu | Résultat |
|---|---|---|---|---|
| OBS_1_canonique | Métrique produite à un seul endroit | `{"findings": [], "metrics": [["win_rate_pct", "CANONICAL_EXISTING"]], "unknowns": []}` | `{"findings": [], "metrics": [["win_rate_pct", "CANONICAL_EXISTING"]], "unknowns": []}` | PASS |
| OBS_2_deux_formules | Même métrique calculée deux fois, deux formules | `{"findings": ["DUPLICATED_CALCULATION"], "metrics": [["fill_ratio", "DUPLICATED"]], "unknowns": []}` | `{"findings": ["DUPLICATED_CALCULATION"], "metrics": [["fill_ratio", "DUPLICATED"]], "unknowns": []}` | PASS |
| OBS_3_pnl_recalcule | La vue recalcule un PnL | `{"findings": ["FRONTEND_RECALCULATES_AUTHORITY"], "metrics": [["entry_usd", "CANONICAL_EXISTING"], ["exit_usd", "CANONICAL_EXISTING"]], "unknowns": []}` | `{"findings": ["FRONTEND_RECALCULATES_AUTHORITY"], "metrics": [["entry_usd", "CANONICAL_EXISTING"], ["exit_usd", "CANONICAL_EXISTING"]], "unknowns": []}` | PASS |
| OBS_4_null_zero | Valeur absente affichée 0 | `{"findings": ["NULL_ZERO_AMBIGUITY"], "metrics": [["open_count", "CANONICAL_EXISTING"]], "unknowns": []}` | `{"findings": ["NULL_ZERO_AMBIGUITY"], "metrics": [["open_count", "CANONICAL_EXISTING"]], "unknowns": []}` | PASS |
| OBS_5_source_absente | Métrique sans producteur dans le périmètre | `{"findings": [], "metrics": [["spread_bps", "SOURCE_UNRESOLVED"]], "unknowns": ["METRIC_SOURCE_NOT_IN_SCOPE"]}` | `{"findings": [], "metrics": [["spread_bps", "SOURCE_UNRESOLVED"]], "unknowns": ["METRIC_SOURCE_NOT_IN_SCOPE"]}` | PASS |
| OBS_6_sans_unite | Métrique sans unité portée par le nom | `{"findings": ["UNIT_NOT_DECLARED"], "metrics": [["signal_strength", "CANONICAL_EXISTING"]], "unknowns": []}` | `{"findings": ["UNIT_NOT_DECLARED"], "metrics": [["signal_strength", "CANONICAL_EXISTING"]], "unknowns": []}` | PASS |
| OBS_7_route_hors_perimetre | Route lue par le client mais non servie dans le périmètre | `{"findings": [], "metrics": [["age_ms", "CANONICAL_EXISTING"]], "unknowns": ["ROUTE_NOT_IN_SCOPE"]}` | `{"findings": [], "metrics": [["age_ms", "CANONICAL_EXISTING"]], "unknowns": ["ROUTE_NOT_IN_SCOPE"]}` | PASS |
| OBS_8_budget | Budget de 30 fichiers dépassé | `{"error": "FILE_BUDGET_EXCEEDED"}` | `{"error": "FILE_BUDGET_EXCEEDED"}` | PASS |

### repo-architect

| Cas | Titre | Attendu | Obtenu | Résultat |
|---|---|---|---|---|
| ARCH_1_inoffensif | Diff inoffensif avec test, zone cartographiée | `{"boundaries": [], "findings": [], "status": "COMPLETE", "unknowns": []}` | `{"boundaries": [], "findings": [], "status": "COMPLETE", "unknowns": []}` | PASS |
| ARCH_2_seuil_gele | Diff qui modifie un seuil gelé | `{"boundaries": ["FROZEN_OBJECT_TOUCHED"], "findings": ["FROZEN_OBJECT_TOUCHED", "MISSING_TESTS"], "status": "COMPLETE", "unknowns": []}` | `{"boundaries": ["FROZEN_OBJECT_TOUCHED"], "findings": ["FROZEN_OBJECT_TOUCHED", "MISSING_TESTS"], "status": "COMPLETE", "unknowns": []}` | PASS |
| ARCH_3_pnl_frontend | Diff qui ajoute un recalcul de PnL au frontend | `{"boundaries": ["FRONTEND_RECALCULATES_AUTHORITY"], "findings": ["FRONTEND_RECALCULATES_AUTHORITY", "MISSING_TESTS"], "status": "COMPLETE", "unknowns": []}` | `{"boundaries": ["FRONTEND_RECALCULATES_AUTHORITY"], "findings": ["FRONTEND_RECALCULATES_AUTHORITY", "MISSING_TESTS"], "status": "COMPLETE", "unknowns": []}` | PASS |
| ARCH_4_hors_zone | Diff hors zone cartographiée : INCONCLUSIVE, jamais « sans risque » | `{"boundaries": [], "findings": [], "status": "PARTIAL", "unknowns": ["DIFF_OUTSIDE_MAPPED_ZONE"]}` | `{"boundaries": [], "findings": [], "status": "PARTIAL", "unknowns": ["DIFF_OUTSIDE_MAPPED_ZONE"]}` | PASS |
| ARCH_5_sans_carte | Pas de carte du cartographe fournie | `{"boundaries": [], "findings": [], "status": "PARTIAL", "unknowns": ["REPOSITORY_MAP_NOT_PROVIDED"]}` | `{"boundaries": [], "findings": [], "status": "PARTIAL", "unknowns": ["REPOSITORY_MAP_NOT_PROVIDED"]}` | PASS |
| ARCH_6_ppl_et_research | Autorité PPL touchée et import Research | `{"boundaries": ["PPL_AUTHORITY_TOUCHED", "RESEARCH_TO_ACTIVE_PATH"], "findings": ["PPL_AUTHORITY_TOUCHED", "RESEARCH_TO_ACTIVE_PATH"], "status": "COMPLETE", "unknowns": []}` | `{"boundaries": ["PPL_AUTHORITY_TOUCHED", "RESEARCH_TO_ACTIVE_PATH"], "findings": ["PPL_AUTHORITY_TOUCHED", "RESEARCH_TO_ACTIVE_PATH"], "status": "COMPLETE", "unknowns": []}` | PASS |
| ARCH_7_runtime | Unité systemd modifiée | `{"boundaries": ["RUNTIME_PATH_TOUCHED"], "findings": ["RUNTIME_PATH_TOUCHED"], "status": "COMPLETE", "unknowns": []}` | `{"boundaries": ["RUNTIME_PATH_TOUCHED"], "findings": ["RUNTIME_PATH_TOUCHED"], "status": "COMPLETE", "unknowns": []}` | PASS |

Tests : `tests/agent_bench/test_observation_agents_v2.py` (exécuteur sur de vrais dépôts git pour
les trois agents, refus d'empreinte de diff, résumé de stockage sur dossier absent, vide, lien
symbolique et > 200 entrées, pointeurs du suivi de main).

## 8. Ce qui reste à décider (gates séparées)

1. Installer un runner par agent (utilisateur `cat-obs-ro`, dossier, unité) : même procédure que le
   cartographe, une décision par agent. Ordre proposé : DPA, puis observability-cartographer.
2. Catalogue initial : datasets du DPA, vues de l'observability-cartographer.
3. Rétention : appliquer `cat-obs-prune.sh` (keep_last 20) à chaque `runs/<mission_id>/` et purger
   les dossiers de mission dépassés.
4. Revue humaine du profil réécrit de repo-architect.
5. Affichage : GPT répertorie les dossiers (MANIFEST.json, summary.json) dans « Stockage CAT ».
