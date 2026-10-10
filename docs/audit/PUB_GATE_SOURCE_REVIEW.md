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

## Empreintes des workflows de la composition proposée

Aucun environment déclaré dans les 29 workflows lus. Les empreintes ci-dessous désignent les octets préparés ; sphinx.yml est le seul workflow changé.

| Fichier | Événements | SHA-256 |
|---|---|---|
| .github/workflows/app-unify-u2-visual-proof.yml | pull_request, push, workflow_dispatch | `f61d9a5e890dc5b5c51c95a6c8e98c47389711994ef930e103c9839bc060ba1f` |
| .github/workflows/app-unify-u2b-visual-proof.yml | pull_request, push, workflow_dispatch | `406590549610d84e18108b33b413aad3ffc05a5fb87734ebbf9ce2a02e9f85a8` |
| .github/workflows/app-unify-u3a-visual-proof.yml | pull_request, push, workflow_dispatch | `a811a49326583741dba48b2662829871e939c9fcc2c630137441760a7360baa2` |
| .github/workflows/app-unify-u3b-visual-proof.yml | pull_request, push, workflow_dispatch | `2774533f541369c3dc82493d1307ab0089cb97ed7c839b278c5b39c95e650ae5` |
| .github/workflows/app-unify-u4-visual-proof.yml | pull_request, push, workflow_dispatch | `e4b064ecfba554ce619b1e28f6450ce5d072c3ef8a81a9ece1b0d78befa70edf` |
| .github/workflows/app-unify-u8-prep.yml | pull_request, workflow_dispatch | `d88dfaada15e5dc215f8aeb5df74d578218a642338529e277e03b5154b146de5` |
| .github/workflows/ci.yml | push, pull_request, workflow_dispatch | `9f6d10040c0dbeea3925c778a79619457a5b6fee5fba45e965732f9ed6398b50` |
| .github/workflows/ci_dashboard_panels.yml | push, workflow_dispatch | `b46646dbe99d0188b38384d37419be76b0bad85cc91dc20e4ed3ced853416bde` |
| .github/workflows/codecov.yml | push, pull_request | `1c8850b0c8e945de9a33678e78f20acb1cf5da664d760c74dfbf6c9aba69efce` |
| .github/workflows/coverage.yml | push, pull_request | `92cac2f5527cdd425fc9fdbd3ada702543934017c2ba0d065bd846218b1d5033` |
| .github/workflows/coveralls.yml | push, pull_request | `d9bbc57a56e3e73caf39ee84198c6d2b1bf04b83a22226333be4503ac406dec9` |
| .github/workflows/cross-stack-compat.yml | pull_request, push | `bda89cbcfd4d295b446c12a3935e30a642ba045dd84585668ce99498ad27cfe7` |
| .github/workflows/diagnostic_env.yml | workflow_dispatch, push | `2f00f62e8c4edb96ba988de12b894993b1b2eeda77549cb8f63885141ab67bf8` |
| .github/workflows/fin02-financial-visual-proof.yml | pull_request, push, workflow_dispatch | `e02b4061bb7e026741e9366acbfeef03d797a1e05c704c2c55ec73c9d1c17713` |
| .github/workflows/frontend-ci.yml | pull_request, push | `42679013e20034bb55527d0ded9f5297efca9633a9ab89e40c065b770d4836be` |
| .github/workflows/machine-lab-u6-visual-proof.yml | pull_request, push, workflow_dispatch | `cecae01c83d4157ba4e4f8367ba41c5996f20e18e3d48add43fb881860abe3b3` |
| .github/workflows/onboarding_dashboard_ci.yml | push, pull_request | `5d8b6344537116e8ba3f66682b5bd63b5ef135de89ee5c7da0eecb334f0f7c6b` |
| .github/workflows/orchestrator-healthcheck.yml | push, pull_request, workflow_dispatch | `cacedf13a39294176a0c0bfe0e9a032c5d8a915bdb79eb456a1b09ea3e98784a` |
| .github/workflows/phase_c_validation.yml | push, pull_request, workflow_dispatch | `8112208d68ae481aafa423df341131b2146cfb80539fec49f0f97b8e0d49974b` |
| .github/workflows/rl-burnin-source-proof.yml | push, pull_request, workflow_dispatch | `5c65317e7bfce074612338cd55afb7bb98e7e47b112f4fb6d055dfb0fb1f8ca9` |
| .github/workflows/screenshots.yml | workflow_dispatch, push, pull_request | `c9cbb3469fb7e33a26f551583265e5ad547d554c8306daaed96668a496c493ee` |
| .github/workflows/sphinx.yml | pull_request, workflow_dispatch | `779877d5a8b59149ecebf067131e6d3b2051338cd7022fe65202da72f2c77d79` |
| .github/workflows/test-panels.yml | push, pull_request | `3a595ec8fe0da4690ffc2de1e898330e65aacdc724f0dfb5bb92c487cfdfcf88` |
| .github/workflows/testnet-integration.yml | workflow_dispatch | `b8d2208f2650db26049bd1da4a50020351e5a2b18462a27b0452160fa62c535a` |
| .github/workflows/vps-audit.yml | workflow_dispatch, push | `7b3a07da432277851b3202f4711a24b1d6d587a46030cc2f5ae2c976cf6d1f97` |
| .github/workflows/web-dir-d3-visual-proof.yml | pull_request, push, workflow_dispatch | `3f4c22838252b0c5b0658de52e5624cd6effb8bc0665c095a8fba9ca737a845a` |
| .github/workflows/web-rl-research-visual-proof.yml | pull_request, push, workflow_dispatch | `85f3457a59565910a23067c7be3ceab9ee9d5b008fad58d3ee5e06f32b2ab683` |
| .github/workflows/web01-market-visual-proof.yml | pull_request, push, workflow_dispatch | `c2391a093a9bc33bb41b579e5a5d500231dff3d96d18052bdd32d13f8cf18e77` |
| .github/workflows/web02-ppl-visual-proof.yml | pull_request, push, workflow_dispatch | `c5f41b73a47b5d9bda63589746c3ef28d619fa6d09896f3a8a1689c620a089b0` |
