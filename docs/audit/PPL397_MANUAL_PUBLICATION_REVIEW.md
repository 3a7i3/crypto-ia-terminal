# PR #397 — révision publication manuelle et causalité DENY

Décision opérateur : HOLD MERGE, patch source autorisé, aucun déploiement.
Candidat repris : `91103987f83ef307c9d0a4cf671463c157124005`.
Base GitHub vérifiée : `8c0dc27fbe456834423e8543c8ff30d657ec2d86`.
Le nouveau SHA et les checks exacts sont enregistrés dans la PR après push.
Cette révision ne reprend aucun changement de la PR #398.

## Audit effectué avant modifications et patch minimal

29 définitions de workflows suivies ont été relues, avec leurs événements,
permissions, jobs et actions. Le registre GitHub a été consulté séparément :
les anciennes entrées ops-a/ops-c/sec-web-deps absentes du tree main ne sont
pas des définitions actuellement suivies ; `dynamic/copilot-swe-agent/copilot`
est une intégration GitHub distincte, pas un workflow de déploiement suivi.
Aucun `workflow_run`, `workflow_call`, `repository_dispatch`,
`pull_request_target`, job reusable ou appel de dispatch indirect identifié.

Sphinx était la seule définition suivie publiant Pages via
`peaceiris/actions-gh-pages@v4`, avec notifications Discord/Slack optionnelles.
Le patch supprime son événement push, conserve uniquement `workflow_dispatch`,
et ajoute la condition événement manuel ET branche main au job et au deploy.
Permissions par défaut du fichier : `contents: read` ; l'écriture `contents:
write` reste limitée au job manuel, nécessaire à la branche gh-pages.
Pas de permission `pages: write` ou `id-token: write`, ni nouveau secret.
Les notifications `always()` sont enfermées dans ce même job manuel : aucun
secret/webhook Sphinx n'est accessible par un job automatique après ce patch.
Aucun dispatch, publication Pages ou notification n'a été exécuté ici.
Les gates CI requis restent automatiques et en lecture seule, sans modification.

## Matrice des définitions vérifiées

| Workflow | Événements source | Permissions du fichier |
|---|---|---|
| `app-unify-u2-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `app-unify-u2b-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `app-unify-u3a-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `app-unify-u3b-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `app-unify-u4-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `app-unify-u8-prep.yml` | pull_request, workflow_dispatch | {'contents': 'read'} |
| `ci.yml` | push, pull_request, workflow_dispatch | {'contents': 'read'} |
| `ci_dashboard_panels.yml` | push, workflow_dispatch | héritées — défaut dépôt non observable |
| `codecov.yml` | push, pull_request | {'contents': 'read'} |
| `coverage.yml` | push, pull_request | {'contents': 'read'} |
| `coveralls.yml` | push, pull_request | {'contents': 'read'} |
| `cross-stack-compat.yml` | pull_request, push | {'contents': 'read'} |
| `diagnostic_env.yml` | workflow_dispatch, push | héritées — défaut dépôt non observable |
| `fin02-financial-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `frontend-ci.yml` | pull_request, push | {'contents': 'read'} |
| `machine-lab-u6-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `onboarding_dashboard_ci.yml` | push, pull_request | héritées — défaut dépôt non observable |
| `orchestrator-healthcheck.yml` | push, pull_request, workflow_dispatch | {'contents': 'read'} |
| `phase_c_validation.yml` | push, pull_request, workflow_dispatch | héritées — défaut dépôt non observable |
| `rl-burnin-source-proof.yml` | push, pull_request, workflow_dispatch | {'contents': 'read'} |
| `screenshots.yml` | workflow_dispatch, push, pull_request | {'contents': 'read'} |
| `sphinx.yml` | workflow_dispatch | {'contents': 'read'} |
| `test-panels.yml` | push, pull_request | {'contents': 'read'} |
| `testnet-integration.yml` | workflow_dispatch | {'contents': 'read'} |
| `vps-audit.yml` | workflow_dispatch, push | {'contents': 'write'} |
| `web-dir-d3-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `web-rl-research-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `web01-market-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |
| `web02-ppl-visual-proof.yml` | pull_request, push, workflow_dispatch | {'contents': 'read'} |

Sphinx a une surcharge d'écriture au job manuel. `vps-audit.yml` dispose de
`contents: write` et d'un accès SSH d'audit, uniquement dispatch manuel ou push
main touchant `audit_requests/request.json` : ce fichier n'est pas changé par
la PR. Aucun appel de ce bridge effectué. Testnet est strictement manuel et
n'est pas exécuté. Les quatre workflows à permissions héritées ne sont pas
modifiés et leurs filtres automatiques ne correspondent pas au diff de #397.
Les variables historiques `BINANCE_TESTNET=true` dans certains jobs CI
sans secrets servent aux tests synthétiques : aucun workflow d'intégration
exchange n'est lancé par cette révision.

Effets CI maintenus et distincts d'un déploiement : upload d'artefacts et de
couverture (Codecov/Coveralls), checks Actions et analyse Semgrep. Ils peuvent
être automatiques après merge, mais aucune définition suivie atteignable par
ce diff ne déploie sur VPS, redémarre Advisor ou active Research.

## Correction isolée du classement DENY

Le garde PPL rejetait correctement le nouvel OPEN par
`PPLAdmissionClosedError`, mais `_exit_admission` classait ensuite ce rejet
générique comme `REJECTED_INSUFFICIENT_CAPITAL`. Un champ facultatif ajouté en
fin de `MexcOrder`, `rejection_code`, transmet uniquement cette cause typée.
Le journal d'admission produit maintenant `REJECTED_ADMISSION` avec
`anomaly=PPL_ADMISSION_DENIED`. Aucun nouveau verdict, enum, schéma ledger,
calcul financier, gate d'ouverture ou transition CLOSE n'est introduit.
Les tentatives restent reliées à leur outcome ; aucune ligne ancienne n'est
modifiée. Les autres rejets gardent leur comportement existant.

Limite préexistante conservée : prix indisponible, divergence OHLCV/ticker et
statuts inattendus peuvent encore être classés par le fallback générique
« capital insuffisant ». Cette mission corrige uniquement le DENY typé PPL ;
elle ne requalifie pas rétroactivement les historiques et ne généralise pas
le modèle de causes de rejet.

## Nouvelle revue technique du diff

Revue source effectuée par l'agent auteur, pas une approbation humaine indépendante.
Le code de concurrence/persistance (`burn_in_admission.py`,
`durable_event_store.py`) n'est pas modifié depuis le candidat précédent.
Le lock store couvre scan/idempotence/barrière/append et la frontière du reçu.
Une répétition canonique d'OPEN déjà persisté est admise avant la barrière ;
un nouvel OPEN burn-in est refusé avant écriture ; CLOSE et UNRESOLVED restent
hors de cette barrière. La course multi-processus et la reprise sont rejouées.
Le reçu reste write-once, lié à séquence/digest, fsync fichier et répertoire ;
un reçu absent, partiel, supprimé ou corrompu ne peut rouvrir les admissions.
Le nouveau champ de refus est informatif : sa valeur par défaut préserve les
constructeurs existants ; il ne participe à aucun calcul ou mutation PPL.

Tests locaux : 455 tests `tests/paper_trading` réussis, 3 tests de gouvernance
workflow réussis ; suite ciblée de 120 tests réussie, lint différentiel ruff
0 nouvelle violation. Les quatre nouveaux scénarios DENY couvrent reçu absent,
valide, corrompu et supprimé après nouvelle instance ; ils vérifient la causalité
attempt/outcome, le capital, l'absence d'OPEN, les octets historiques inchangés
et la conservation du CLOSE. L'insuffisance réelle et les autres admissions
sont couvertes par la régression existante. Preuves exclusivement synthétiques.

Reproduction :

```bash
python -m pytest -q tests/paper_trading tests/test_pr397_publication_governance.py
python scripts/ci/ruff_baseline_gate.py check
```

## Limites de preuve et récupération

Permissions par défaut Actions et webhooks du dépôt : lectures API refusées
HTTP 403. Configuration effective Pages : HTTP 404 ; absence ou accès masqué
ne peuvent être distingués par ce seul résultat. Aucun paramètre d'administration
n'a été changé. Une publication Pages native indépendante des workflows suivis
ou un déploiement déclenché par un webhook externe ne peuvent donc pas être
exclus. La preuve source ferme la voie Sphinx identifiée ; elle ne certifie pas
l'ensemble des intégrations administrées hors Git. Leur vérification/attestation
opérateur reste nécessaire avant un GO MERGE global. Aucune méthode de contournement
ou demande d'élargissement de droits n'est exécutée.

La barrière candidate demeure intrinsèque au code de l'epoch burn-in : un futur
déploiement/activation serait un changement d'admission explicite, non autorisé
par un merge source. Le reçu n'est pas un commutateur permettant OPEN.
Ne pas déployer l'ancien binaire non protégé en guise de rollback ; conserver
la barrière ou maintenir l'écrivain arrêté. Aucun rollback de reçu/PPL, aucune
édition historique, aucun changement de capital, d'epoch ou de PB_MAX_POSITIONS.
Si un rollback source de cette révision est demandé : conserver le workflow
Sphinx manuel ; ne pas restaurer son push automatique. La télémétrie peut
revenir au classement ancien sans rouvrir les admissions, mais cela réintroduit
la mauvaise attribution DENY. Le runbook #397 de drainage/reprise reste applicable.

MERGE HOLD ; RUNTIME ACTIVATION BLOCKED ; SCIENTIFIC FINALIZATION BLOCKED.
PAPER_STRESS_RESEARCH reste une préparation inactive. Aucun VPS, Advisor,
publication Pages, ordre exchange ou activation LIVE/TESTNET exécuté.
SOURCE_PROOF ≠ RUNTIME_PROOF. Verdict final et résultats CI du SHA exact : PR #397.
