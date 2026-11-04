# Archives de réconciliation — lot 2, 2026-11-04 UTC

**Textes historiques, aucune instruction ni autorisation active.** Les cinq
copies sont conservées octet pour octet depuis leurs PR. Leur statut décrit
leur date d'origine. L'extension `.md.txt` permet de les consulter comme texte,
sans publier leurs anciens prompts comme pages de reprise.

La [réconciliation du suivi](../../handoffs/LOT2_TRACKING_RECONCILIATION_20261104.md)
porte les décisions actuelles. Le [manifeste](manifest.json) enregistre PR,
HEAD, chemin d'origine, taille, blob Git SHA-1 et SHA-256. Chaque blob a été
comparé à celui retourné par GitHub au HEAD exact, sans réécriture.
La copie de #491 conserve notamment sa ligne vide finale d'origine ; le
signalement `git diff --check` sur cette seule archive est attendu. Le contrôle
des documents actifs est distinct et ne justifie aucune normalisation des copies.

| PR / HEAD d'origine | Copie conservée | Lecture actuelle |
|---|---|---|
| [#465](https://github.com/3a7i3/crypto-ia-terminal/pull/465) / `811c2feda8dfe4439c77ec23bd8e88d4248aedef` | [Vision Sentinel V2](pr465/docs/sentinel_v2/README.md.txt) | J03–J07 et hypothèses économiques conservés au backlog ; aucune autonomie ou AIC admise |
| #465 / même HEAD | [Spécification initiale J01](pr465/docs/sentinel_v2/J01_ACTIVITY_LEDGER_SPEC.md.txt) | Proposition historique ; le contrat intégré est dans `docs/sentinel_activity/` |
| #465 / même HEAD | [Ancien prompt PLAN FIRST](pr465/docs/sentinel_v2/WORK_PLAN_FIRST_HANDOFF.md.txt) | Mission historique suivie d'implémentations ; ne pas la relancer comme mission actuelle |
| [#487](https://github.com/3a7i3/crypto-ia-terminal/pull/487) / `e9f989a60b19680ff6ccdde5d6f18eea5dc988a3` | [Plan d'admission étape 7](pr487/docs/colony_registrar/STEP7_AUTHENTICATED_ADMISSION_PLAN.md.txt) | Obligations de composition/récupération conservées, réalisation complète non prouvée |
| [#491](https://github.com/3a7i3/crypto-ia-terminal/pull/491) / `edfc2da078ca71498f8fc75373f4ec7a70a1b0d1` | [Préparation P4](pr491/docs/colony_admission/P4_IMPLEMENTATION_PREPARATION.md.txt) | Inspection #492 intégrée ; formats/readers/observers livrés ensuite ; contrôleur global non qualifié |

Références intégrées à consulter avant reprise :

- [Contrat J01](../../sentinel_activity/J01_CONTRACT.md),
  [rapport historique J01](../../sentinel_activity/J01_QUALIFICATION_REPORT.md),
  [plan J02](../../sentinel_activity/J02_PLAN.md),
  [capacité J02 mesurée](../../sentinel_activity/J02_CAPACITY_REPORT.md).
- [Contrat d'admission](../../colony_admission/ADMISSION_CONTRACT.md),
  [formats/transitions](../../colony_admission/P4_FORMATS_AND_STATE_MACHINE_V0.md),
  [observer borné](../../colony_admission/P4_FILE_OBSERVER_BOUNDARY_V0.md),
  [corpus](../../colony_admission/acceptance/CORPUS_COVERAGE_PLAN_V0.md).

Les PR #465/#487/#491 restent **OPEN / DRAFT**, signalées comme historiques,
tant que la PR d'archivage du lot 2 n'est pas fusionnée. Après cette fusion,
leur clôture administrative pourra citer la copie intégrée et son manifeste.
Fusion de l'archive, clôture administrative et satisfaction des obligations
scientifiques restantes sont des événements distincts.

Aucun contrat, certificat, pin ou rapport de qualification existant modifié.
Les anciennes permissions et commandes ne sont pas réactivées. #286 ACTIVE.
