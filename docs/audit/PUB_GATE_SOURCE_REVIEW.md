# PUB-GATE-SOURCE — audit, revue et rollback

Mission autorisée par l’opérateur le 2026-10-10 UTC, coordination #399, roadmap #285.
Périmètre source uniquement. READY_FOR_REVIEW n’est pas GO MERGE.

## Baseline directement relue avant mutation

- main : `8c0dc27fbe456834423e8543c8ff30d657ec2d86` ; arbre `4fa0244c1c4274e0faf0b6e23d0f8087abcac0ec`.
- #397 OPEN/DRAFT/non mergée : `e6fa26b839f5d71db5de390203129c107d5e46e1`.
- #398 OPEN/DRAFT/non mergée : `77fc84c6fb0a9b606c53b13d70c3a35a7c6f89a4`.
- Deux PR base main, mergeable=true au relevé ; aucune modification de ces PR.
- #399/#285/#286 relues. Freeze actif ; aucun VPS, Advisor, PAPER/PPL/FIN ou epoch modifié.
- Aucun AGENTS.md dans l’arbre récursif non tronqué de main.
- Ruleset actif 21989939 : quatre checks Actions 15368, résolution des threads, zéro approbation imposée, aucune obligation CODEOWNERS, strict=false, aucun bypass retourné. La protection classique demeure inconnue (403).
- Au relevé préparatoire : #397 29 checks SUCCESS + 2 Walk-forward SKIPPED ; #398 30 SUCCESS + 2 SKIPPED. Les quatre contextes requis réussissent à ces SHA. Ces preuves ne sont pas transférées à cette PR.

## Cause et différence par rapport à #397

main déclenche Sphinx sur push main pour docs/**, *.md, quant_hedge_ai/** et le workflow. Le job possède contents:write, publie gh-pages et peut notifier Discord/Slack.
#397 supprime push et impose workflow_dispatch/main au job et au déploiement. Cela protège la publication mais ne prévoit pas de build Sphinx sur PR.
Cette tranche reprend le principe de gate, sans cherry-pick ni import PPL, et sépare :
1. validate-docs : PR documentaire ou dispatch, contents:read, checkout sans credential persistant, build HTML et contrôle de liens existants, artefact du run ;
2. publish-docs : needs validate-docs, uniquement workflow_dispatch + refs/heads/main, contents:write pour gh-pages. Téléchargement de l’artefact du même run ; aucun run-id ou repository externe.
Déploiement et notifications portent aussi la condition manuelle/main. Les notifications restent optionnelles ; leur always() est enfermé dans le job manuel. Aucune notification envoyée par cette mission.

## Fichiers modifiés et frontière

- .github/workflows/sphinx.yml
- tests/governance/test_sphinx_publication_gate.py
- docs/audit/PUB_GATE_SOURCE_REVIEW.md (ce rapport)

Les 28 autres workflows restent byte-identical à la baseline. Aucun changement des quatre workflows/gates requis, des fixtures financières, du frontend #398 ou du runtime #397. Aucun environment GitHub ajouté : les éventuels reviewers d’environnement ne sont pas inventés. L’identité et le droit de dispatch sont contrôlés par GitHub ; la condition YAML ne constitue pas une preuve cryptographique d’une décision humaine. Un appel API manuel par un acteur autorisé reste un workflow_dispatch : prévenir l’automatisation par ce canal exige la gouvernance et les droits administratifs.

## Matrice des événements et effets

| Événement/ref | Validation docs | Publication/notifications |
|---|---|---|
| PR touchant les chemins documentaires | build lecture seule ; pas de secrets | interdit |
| push main après merge, même docs modifiées | aucun Sphinx push | interdit |
| push branche | aucun Sphinx push | interdit |
| workflow_dispatch sur main | build et tests ; publication seulement après succès | autorisé techniquement, décision opérateur distincte obligatoire |
| workflow_dispatch autre branche/tag | build possible | interdit |
| schedule, workflow_run, workflow_call, repository_dispatch, pull_request_target | non déclarés | interdit |
| échec du build/test/artefact | pas de succès prerequisite | job publication ignoré |

Le linkcheck reste continue-on-error comme sur main : une URL morte est un avertissement et non une nouvelle gate bloquante. Le build HTML et le test de frontière restent bloquants. Les liens vérifiés peuvent contacter des sites externes depuis la CI ; ce n’est pas une publication. Les installs pip, actions tierces, uploads d’artefacts et CI existantes conservent leurs effets réseau.

## Inventaire des 29 workflows

Tous les fichiers .github/workflows/*.yml de main ont été lus. Aucun workflow_run/workflow_call/repository_dispatch ni appel suivi à Sphinx/dispatch/gh-pages identifié hors sphinx.yml dans cet inventaire.
- Workflows de preuves/app/market/research/finance et santé : CI, serveurs locaux de fixtures, artefacts ; pas de publication Sphinx identifiée.
- ci.yml : lint/tests/performance/coverage/smoke, read-only ; inchangé.
- codecov.yml/coveralls.yml/coverage.yml : couverture et uploads externes ; inchangés.
- ci_dashboard_panels.yml, onboarding_dashboard_ci.yml, diagnostic_env.yml, phase_c_validation.yml, test-panels.yml, screenshots.yml : contrôles/outils/artefacts existants ; inchangés.
- testnet-integration.yml : dispatch seulement, credentials testnet ; non déclenché.
- vps-audit.yml : dispatch ou push main audit_requests/request.json ; SSH et écriture de résultats ; cette PR ne modifie pas ce chemin et ne dispatch pas le bridge.
La matrice exhaustive des noms/événements/empreintes suit. Cet inventaire est une analyse statique des workflows suivis, pas un audit transitif de chaque dépendance/action tierce ni une certification d’absence de service hors Git.

## Validation et limites de preuve

Local : Python 3.12.14, PyYAML 6.0.3 ; sept tests unittest PASS, 32 combinaisons event/ref évaluées.
Tests : fermeture des événements, prerequisite de succès, séparation permissions/secrets, checkout sans credentials, liaison d’artefact au run courant, conditions de chaque effet externe, rejet de conditions affaiblies.
Il s’agit de contrats statiques sur YAML, pas d’une exécution du moteur Actions. Aucun dispatch réalisé.
Ruff 0.15.8 ciblé E,F,W avec exclusions E501/E402 de la baseline : aucune violation nouvelle.
Pas de build HTML local revendiqué ; le job validate-docs doit fournir cette preuve en CI. La suite monorepo et les checks requis doivent être lus au SHA final dans le corps de PR, sans réutiliser #397/#398.
La liste de fichiers et les 28 empreintes de workflows non modifiés doivent concorder avec la comparaison GitHub base..head.

## Risques résiduels et revue

1. Pages, hooks et permissions Actions : endpoints non autorisés par le canal Fetch actuel (INVALID_ARGUMENT), pas « absents ». Protection classique 403. Attestation opérateur/configuration admin encore nécessaire avant verdict global sur les effets externes d’un merge.
2. Les actions gardent leurs versions majeures @v4/@v5 ; pin SHA intégral et audit supply-chain seraient une mission séparée. Build documentaire exécute du code de PR dans un runner sans secrets et en lecture seule ; ne pas transférer d’artefact PR vers une publication manuelle d’un autre run.
3. Pas d’environnement protégé introduit sans propriétaire/reviewers définis. Dispatch main techniquement autorisé n’est pas GO PUBLISH automatique.
4. Une future #397 pourrait réintroduire une version Sphinx différente : conserver ses HEAD actuels, puis réconcilier explicitement cette dépendance après un éventuel merge de cette PR. Aucun rebase ni changement de #397/#398 effectué.
5. L’état de main peut évoluer ; réévaluer composition/base/checks au SHA exact avant merge. CI verte ne clôt pas le freeze ou les gates runtime.

## Rollback

Avant merge : conserver la PR en draft ou proposer sa fermeture ; aucun effet runtime à annuler.
Après un éventuel merge autorisé : NE PAS reverter sphinx.yml vers le déclencheur push historique, car le revert pourrait lui-même réactiver/publicher automatiquement.
Récupération sûre : patch source conservant une gate manuelle (ou désactivation de publication), avec revue et CI, puis décision de merge distincte.
Un éventuel retour d’un contenu gh-pages serait une décision de publication manuelle séparée, jamais un déploiement VPS. Les artefacts CI sont des preuves de build, pas des publications.
Aucun rollback PPL/FIN/Advisor concerné.

## Verdict

Tests locaux PASS. Verdict global des intégrations externes INCONCLUSIVE faute d’accès administratif.
PR source prête à la revue seulement après vérification des tests/build et checks nécessaires au SHA final ; état daté et liens CI consignés dans le corps de PR.
Aucun merge/auto-merge/dispatch/publication/VPS/restart/activation PAPER autorisé.

## Identités Git des workflows de la composition proposée

Aucun environment déclaré dans les 29 workflows lus. Les identités ci-dessous sont les blob SHA Git, pas des SHA-256 de copies locales. sphinx.yml est le seul workflow changé ; les 28 autres blobs sont ceux de la baseline.

| Fichier | Événements | Git blob SHA |
|---|---|---|
| .github/workflows/app-unify-u2-visual-proof.yml | pull_request, push, workflow_dispatch | `78db5752b07b18271cb59814801e077073d04b02` |
| .github/workflows/app-unify-u2b-visual-proof.yml | pull_request, push, workflow_dispatch | `ddc238296e2c8123127e3cb2cd53b0e5b180e2bd` |
| .github/workflows/app-unify-u3a-visual-proof.yml | pull_request, push, workflow_dispatch | `9eec286b694c1ee313a3641034992f1aede31e10` |
| .github/workflows/app-unify-u3b-visual-proof.yml | pull_request, push, workflow_dispatch | `99d1dd25291821fd44f5d3509c88a43054c2857c` |
| .github/workflows/app-unify-u4-visual-proof.yml | pull_request, push, workflow_dispatch | `85baff47a69535b66ecd9950ce22703023f12d29` |
| .github/workflows/app-unify-u8-prep.yml | pull_request, workflow_dispatch | `5f127177e7c8dd78359f62b5e581fe5734120dc5` |
| .github/workflows/ci.yml | push, pull_request, workflow_dispatch | `27848653411b372c3fe161745d565618aa5d0994` |
| .github/workflows/ci_dashboard_panels.yml | push, workflow_dispatch | `7c18582118a6d26ddfa3c90ac58ef22b77c16bb8` |
| .github/workflows/codecov.yml | push, pull_request | `f8fb2cb1312feb7fc8511156b5868c25155f1226` |
| .github/workflows/coverage.yml | push, pull_request | `1d4b611f9765040001fb4908ba771d2452d9517f` |
| .github/workflows/coveralls.yml | push, pull_request | `2796e6fef4bab09273b646dde8136c4f779e86f0` |
| .github/workflows/cross-stack-compat.yml | pull_request, push | `176ed15c492c8d5061dffaf9ae1a6e528d70e344` |
| .github/workflows/diagnostic_env.yml | workflow_dispatch, push | `24e3ee83b3cb1d74c35788d0e8d68eba279833dd` |
| .github/workflows/fin02-financial-visual-proof.yml | pull_request, push, workflow_dispatch | `0e80b0b978a996d6b0e7b6af0923bdfdc9b31b9f` |
| .github/workflows/frontend-ci.yml | pull_request, push | `3b9d12121986e3ceca5bc2e47abe72ab3b99b012` |
| .github/workflows/machine-lab-u6-visual-proof.yml | pull_request, push, workflow_dispatch | `374b00b80e8053ff79b8dc1c61cb65063b4b8b1f` |
| .github/workflows/onboarding_dashboard_ci.yml | push, pull_request | `e61ffb39863a7ad5acbac1052226b9bfcff95b79` |
| .github/workflows/orchestrator-healthcheck.yml | push, pull_request, workflow_dispatch | `d96dd3d557b477e387560a4fa4501a3f16b47d41` |
| .github/workflows/phase_c_validation.yml | push, pull_request, workflow_dispatch | `0c4f1f536bab44275cb464e1087596ed0b9a9dd6` |
| .github/workflows/rl-burnin-source-proof.yml | push, pull_request, workflow_dispatch | `f4b659fc04e9d34aa9063deae0b66dd572312b26` |
| .github/workflows/screenshots.yml | workflow_dispatch, push, pull_request | `2499c3e4f038d92ee7b8640d7182fa95594576ec` |
| .github/workflows/sphinx.yml | pull_request, workflow_dispatch | `9b31abdf0f6f7c3d215e1fcfc8394641ee802fcb` |
| .github/workflows/test-panels.yml | push, pull_request | `ff2e461be64cf7d37eb5d72a6c198c483874d5ae` |
| .github/workflows/testnet-integration.yml | workflow_dispatch | `711c52a545a15c07d586cf65f1028b7ad982a36d` |
| .github/workflows/vps-audit.yml | workflow_dispatch, push | `5419cb1ba7478fa2f17e47f73d5b95c04b9ddbe8` |
| .github/workflows/web-dir-d3-visual-proof.yml | pull_request, push, workflow_dispatch | `64e7132b123cfb8a34c2891426efbc5567eb4847` |
| .github/workflows/web-rl-research-visual-proof.yml | pull_request, push, workflow_dispatch | `19d8c00188bbe397be5dca0d11e1bba87ec8f313` |
| .github/workflows/web01-market-visual-proof.yml | pull_request, push, workflow_dispatch | `ca259962a76c522d6f6b80d75a3f68ad7b032526` |
| .github/workflows/web02-ppl-visual-proof.yml | pull_request, push, workflow_dispatch | `6389fe617a517fcb04b1c4f22d7ce3a419d92a68` |
