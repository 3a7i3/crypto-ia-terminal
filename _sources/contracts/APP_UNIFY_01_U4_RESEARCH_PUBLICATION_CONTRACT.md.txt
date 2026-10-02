# APP-UNIFY U4 — Research publication → Operator App

2026-10-02 · #336 / parent #323 · #286 ACTIVE · SOURCE ONLY.
Base : U3b #335, merge `b48ac1aa1c4255a4f9fdb3d248fa556ff6ccb37f`.

## Chaîne et frontière

```text
sélection Research explicite (admission + référence + SHA-256)
  + publication RL-REPLAY immutable (manifest/metrics/terminal_state)
  + résultat RL-DIAG optionnel, explicitement lié
    → builder offline déterministe
    → publication atomique research_lab_snapshot.json
    → reader strict → GET /api/operator/v1/research-lab
    → ResearchLabView / carte Research Direction
```

Le builder ne charge aucun moteur Replay/Diag/PPL/runtime/exchange. Il ne lit
aucun dataset, JSONL lifecycle/DecisionPacket, ledger ou répertoire de candidats.
Il ne calcule pas de PnL, frais, ratios, drawdown, attribution ou causalité.
Les seules dérivations sont l'adaptation de vocabulaire, la vérification de
liaisons/populations/empreintes, le tri stable et la projection de champs.

Il ne choisit jamais un `latest` selon mtime, génération ou tri de répertoire.
Le choix du dernier résultat **certifié** appartient au processus Research ;
U4 reçoit cette sélection. Aucun producteur automatique O7 ni mécanisme de
signature/authentification d'une certification n'existe dans cette tranche.
`CERTIFIED` + `certification_ref` sont une admission fournie par ce processus,
pas une certification émise ou authentifiée par le builder. Les hashes vérifient
les bytes sélectionnés et leur intégrité, pas l'identité de l'attestateur.
Ne pas générer une admission depuis un simple `status=COMPLETE`.

Aucune preuve Research réelle courante ou runtime n'est certifiée par les
fixtures synthétiques. Leur référence est explicitement `synthetic-test-only`.

## Entrées explicites

`app-unify-u4.research-selection.v1` est un objet fermé :

```json
{
  "schema_version": "app-unify-u4.research-selection.v1",
  "certification_ref": "référence gouvernée de la certification Research existante",
  "admission": "CERTIFIED",
  "research_run_id": "<64 caractères hexadécimaux>",
  "manifest_sha256": "<SHA-256 exact des bytes manifest.json>",
  "diagnostic_run_id": null,
  "diagnostic_sha256": null
}
```

Le diagnostic est soit absent (deux null + aucun chemin), soit présent (deux
hashes valides + chemin explicite). Référence obligatoire, non vide, ≤512
caractères. Aucun chemin de source dans le payload app ; références logiques
stables et empreintes exactes dans `provenance.source_artifacts`.

Profil initial : RL-REPLAY `rl-replay-01.result.v1`, COMPLETE, FACTUAL_BASELINE,
OFFLINE_FACTUAL_PPL_REPLAY, identité `rl-replay-01.run-identity.v1`, méthode
PPL_PROJECT_FACTUAL_V1. Pas de counterfactual/candidate configuration.

Les identités run sont vérifiées par hash canonique. Les champs du manifeste
et de son identité doivent coïncider. Les bytes metrics/terminal_state doivent
correspondre aux SHA/tailles du manifeste et à ses aggregates embarqués. Le
lifecycle JSONL n'est jamais ouvert : U4 vérifie les composants qu'il consomme,
et s'appuie sur la certification amont pour les autres preuves scientifiques.

Diagnostic : `rl-diag-01.run-identity.v1`, FACTUAL_PERFORMANCE_ATTRIBUTION,
FACTUAL_PPL_PLUS_EXACT_PACKET_CONTEXT_V1. Run upstream, dataset, boundary,
epoch, SHA replay, hash config, population fermée et réconciliations PASS doivent
coïncider. L'app reçoit le hash du résultat entier mais uniquement ses aggregates.

## Parité scientifique

| App | Source | Règle |
|---|---|---|
| population N | Replay metrics + identité + terminal + Diag si présent | closed performance, cohérence obligatoire |
| win_rate, profit_factor, expectancy | Replay metrics | copie exacte, aucune recomputation |
| Sharpe / MTM drawdown | Replay metrics | NOT_AVAILABLE + raison source |
| close-to-close drawdown | Replay metrics | ratio historique distinct du MTM |
| net realized PnL | Diag closed summary | aucun fallback sur capital/terminal PAPER |
| closed population fees | Diag summary | exclut explicitement non-closed entry fees |
| attribution symbol/side/regime/conviction | Diag categorical aggregates | copie PnL/N ; populations bornées et couverture cohérente |
| diagnostic absent | sélection explicite | null/NOT_AVAILABLE, frais/attribution non fabriqués |
| candidat | aucun catalog admis dans ce profil | zéro **lignes publiées**, catalogue NOT_AVAILABLE dans limitations |
| limitations | Replay/Diag + frontières du profil | raisons source conservées, pas d'inférence causale |

`POSITIVE_INFINITY` et `UNDEFINED_ZERO_DENOMINATOR` deviennent une métrique
NOT_AVAILABLE/null avec le statut source dans la raison, jamais zéro ou nombre
fini synthétique. Zéro réellement publié reste zéro. DESCRIPTIVE_ONLY n'est pas
une preuve d'adéquation statistique ; LOW_SAMPLE_DESCRIPTIVE_ONLY du diagnostic
reste LOW_SAMPLE au niveau population, avec la qualification descriptive visible.

N=0 produit EMPTY avec sections métriques/attribution vides, pas de métrique
performance artificielle. Les publications historiques ne deviennent ni LIVE ni
STALE selon une horloge runtime : timestamp de publication et IDs sont affichés.

Le schéma app demeure WEB-RL 1.0.0. Research expose désormais les hashes de tous
les artifacts dans la provenance repliable. Direction distingue les candidats
publiés du registre global. Les métriques restent séparées du capital PAPER.

## Publication et erreurs

CLI source/offline, uniquement après admission Research effective :

```sh
python -m observability.research_publication_builder \
  --selection /research/admission/selection.json \
  --run /research/runs/EXACT_RUN_ID \
  --diagnostic /research/diagnostics/EXACT_DIAG_ID/result.json \
  --output /presentation/research_lab_snapshot.json \
  --generated-at-utc 2026-10-02T00:00:00Z \
  --builder-source-sha EXACT_40_HEX_SOURCE_SHA
```

Omettre `--diagnostic` uniquement si les deux champs sélectionnés sont null.
La date de présentation et le SHA builder sont fournis, jamais inférés depuis
le Research SHA ou le commit runtime. Même evidence/date/SHA → même snapshot.
La publication atomique existante valide, fsync puis replace. Une admission
invalide laisse la présentation précédente intacte ; son timestamp historique
reste celui de cette publication (aucun succès/republication silencieux).

Source protégée : output hors run, dossier diagnostic et dossier admission ;
symlinks refusés. Aucune modification de publication immutable. Aucun scheduler,
service/timer, configuration API/VPS ou wiring runtime ajouté.

Lecture stricte : fichier régulier, borné 4 MiB pour evidence, doublons JSON et
NaN/Infinity refusés, non bloquante pour FIFO. Présentation canonique ≤512 KiB ;
JSON pretty ≤1 MiB garanti avant écriture ; API bornée à 1 MiB. Schéma malformed
(structure enum non hashable, nombre hors plage, etc.) retourne false sans 500.
Codes 503 historiques conservés, messages bornés sans chemin source sensible.
GET ne lit que la présentation, même après suppression des sources de fixture.

## Validation et limites

- Tests Python U4 : determinisme, preuves bytes, copie exacte, source inchangée,
  admission/context/population/config/identités, valeurs non finies, vrais zéros,
  empty/diagnostic absent, limites fichiers/FIFO/symlink, CLI, atomicité et imports.
- N cross-stack : dataset **synthétique** → vrais Replay/Diag et publisher
  immutable → builder U4 → artifact → vrai reader/API → validator/React inchangés.
  Les moteurs ne sont invoqués que par le générateur de tests isolé.
- Desktop1440/mobile390 : publié/historique/empty/missing/invalid/network,
  hashes/provenance, pas d'overflow, GET-only et carte Direction indépendante.
- Régressions WEB-RL, frontend, transport/PWA, build et lint différentiel.

Pas de candidate catalog/attribution MTF/numeric_context/concentration dans ce
profil ; pas de résultats counterfactual. Pas de nouvelle route/app schema.
Publication runtime, production de sélection gouvernée/O7 et preuve de données
réelles restent séparées. Aucun VPS/runtime/Advisor/PPL/FIN/epoch/config/risk/
sizing/Watchdog/exchange modifié ; #286 ACTIVE.
