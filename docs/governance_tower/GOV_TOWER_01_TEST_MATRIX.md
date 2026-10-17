# GOV-TOWER-01 — Matrice de tests

Toutes les données sont SYNTHETIC (fixtures, transports factices, répertoires temporaires).
Aucun test ne lit le VPS réel, n'appelle GitHub ni un modèle.

| Fichier | Tests | Mission | Couvre |
|---|---:|---|---|
| `test_gt01_github.py` | 72 | M1 | chemins sensibles/ambigus/binaires refusés sans requête ; plages de lignes ; lecture par SHA et HEAD par défaut ; empreinte Git ; plafond de taille ; expurgation ; clé privée refusée ; réponses forgées (chemin, type, base64, liste) ; matrice HTTP 401/403/403 quota/404/429/500/redirection/timeout/JSON invalide ; budget par question et quota distant persistant ; `budget_status` sans requête ; jeton envoyé seulement à l'API et absent des sorties ; issue, PR, CI par SHA, branche ; fixtures |
| `test_gt01_host.py` | 29 | M2 | identité d'hôte attendue (HOST_MISMATCH, validation) ; rejeu/rétrogradation (NON_MONOTONIC) ; Content-Type ; ETag sûr/forgé ; en-têtes mal formés ; défaillance partielle de `storage` sans perte des champs prouvés ; DENIED jamais converti en 0 ; horloge future ; cache serveur périmé ; fixtures `no_deployment_id` et `partial` |
| `test_gt01_diagnostics.py` | 25 | M3 | routage « même version » → COMPARE ; un code par scénario (runtime épinglé en retard sur main, dérive, périmé, VPS indisponible, sans identité de build) ; GitHub refusé / quota ≠ panne ; ACTIVE ≠ HEALTHY ; preuves partielles ; compare indisponible → NOT_COMPARABLE ; ALIGNED_WITH_MAIN sans santé ; SERVICE_NOT_RUNNING ; CI échec/en cours/aucune ; contrat `Diagnostic` ; aucun code de violation ni de santé ; preuves citées présentes dans le run |
| `test_gt01_llm_adapter.py` | 42 | M4 | désactivé par défaut ; transport non simulé refusé ; aucun import réseau/SDK ; faits VPS retenus par défaut ; budget d'entrée ; secret dans la question ; chaque code de rejet de sortie ; preuves VPS non citables ; fusion INFERRED seulement, sans proposition ; repli déterministe sur panne ; audit sans texte |
| `test_gt01_sentinel.py` | 23 | M3/M6 | intentions détaillées et paramètres ; refus (.env, secrets, fermer/commenter/approuver, relancer la CI) ; un outil par lecture ; PR → CI de son SHA ; cartographie sans lecture ; outil absent → NOT_IMPLEMENTED ; injection dans fichier et issue citée, jamais suivie ; empreinte forgée refusée ; quota GitHub |
| Tests GOV-TOWER-00 étendus | — | M0–M5 | `test_gt_github_provider.py` (méthodes publiques admises), `test_gt_scenarios.py` (nouveaux scénarios), `test_gt_ui_static.py` (aller-retour de `sample_run.json` avec diagnostics et extraits) |
| `scripts/governance_tower/gt01_ui_e2e.mjs` | 29 contrôles | M5/M6 | Chromium réel : 5 raccourcis, bannière DÉMO, diagnostic en 4 étapes, preuves repliées, extrait numéroté, refus de relance CI, cartographie, aucun bouton d'action, aucune requête hors loopback, aucune boîte de dialogue ni erreur JS ; mobile 390 px sans défilement horizontal ; injection `<script>`/`<img onerror>` affichée comme texte ; bandeaux STALE et NO_DEPLOYED_BUILD_ID |

Commandes :

```bash
python -m pytest -q tests/governance_tower
python -m pytest -q -m "not performance and not slow" tests/
python scripts/ci/ruff_baseline_gate.py check
node --check governance_tower/ui/app.js
NODE_PATH=$(npm root -g) node scripts/governance_tower/gt01_ui_e2e.mjs
```

Le parcours E2E n'est pas exécuté par la CI (pas de navigateur dans `ci.yml`) ; ses résultats
sont ceux du rapport de livraison, au SHA indiqué.
