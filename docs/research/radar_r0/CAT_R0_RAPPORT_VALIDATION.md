# CAT R0 — Rapport de validation du Radar

Gates R0-3 et R0-4. Environnement isolé (conteneur cloud, utilisateur root),
2026-11-24, branche `claude/project-thread-dg0k91`. Données SYNTHETIC
uniquement, aucun accès réseau de marché.

## 1. Tests R0 (groupes A à F)

`python -m pytest -q tests/radar_selection` : **71 PASS, 0 FAIL, 0 SKIP, 0 XFAIL**,
sous Python 3.11.18 et 3.13.18.

| Groupe | Tests | Résultat |
|---|---|---|
| A — Univers | A01–A08 | 8 PASS |
| B — Qualité | B01–B08 | 8 PASS |
| C — Sélection | C01–C10 | 10 PASS |
| D — Contrôle manuel (CLI réelle) | D01–D07 | 7 PASS |
| E — Isolation | E01–E12 (E07 ×4 univers, E09 ×7 entrées), historique borné, seuils réutilisés, fixtures reproductibles | 24 PASS |
| F — Terminal | F01, F02 (×4 univers), F03–F08 | 14 PASS |

Aucun test supprimé ou affaibli. Un test (E01) a été précisé pendant la
validation : Python 3.11 charge `urllib.parse` via `pathlib` ; seule la liste
des modules de transport (`urllib.request`, `http.client`…) est interdite.

## 2. Régressions

| Suite | Python | PASS | FAIL | SKIP | XFAIL |
|---|---|---|---|---|---|
| `tests/radar_selection` + `scanner_universe` + `radar_composite` | 3.11 | 277 | 0 | 0 | 0 |
| idem | 3.13 | 275 | 0 | 2 | 0 |
| Suite complète `-m "not performance and not slow" tests/` (équivalent TEST REGRESSION GATE) | 3.11 | 12 880 | 3 | 22 | 2 |

Les 3 échecs de la suite complète :

1. `tests/colony_lab/test_supervisor.py::test_process_count_is_bounded` :
   quirk connu du conteneur (root, RLIMIT_NPROC non appliqué), sans lien
   avec R0.
2. `tests/governance_tower/test_gt_host_provider.py::test_snapshot_permission_denial_is_not_a_missing_source` :
   un refus de permission simulé par `chmod` n'empêche pas root de lire ;
   même cause, aucun fichier lié à R0.
3. `tests/radar_selection/test_e_isolation.py::test_E01_fully_offline_execution` :
   exécuté avant la précision décrite au §1 ; repasse vert ensuite (3.11 et 3.13).

Lint : ruff 0.15.8 OK ; `scripts/ci/ruff_baseline_gate.py check` : 0 nouvelle
violation. Garde de publication Sphinx : OK.

### Résultat CI définitif (PR #607, HEAD `d8edf17`)

28 checks : 26 succès, 2 ignorés (Walk-forward validation et publish-docs,
conditionnels), 0 échec, dont TEST REGRESSION GATE, LINT REGRESSION GATE,
COVERAGE REGRESSION BASELINE et CROSS-STACK COMPATIBILITY GATE. Les échecs 1
et 2 ne se reproduisent pas en CI (utilisateur non privilégié), ce qui confirme
leur origine d'environnement. L'échec 3 était antérieur au commit validé.

### Contre-revue (classement `radar-ranking/1.1.0`)

Les candidats `COMPLETE` sont classés avant les `INCOMPLETE` (décision
opérateur du 2026-11-24, test C11). Les quatre univers donnent les mêmes
candidats qu'en 1.0.0, chacun n'ayant qu'un marché `COMPLETE` au plus.

## 3. Performances locales (`bench 5`)

| Univers | Marchés | Durée max | Mémoire pic | Entrée | Sortie | Empreintes |
|---|---|---|---|---|---|---|
| calm | 23 | 189 ms | 700 468 o | 109 901 o | 69 628 o | 1 |
| volatile | 23 | 152 ms | 664 912 o | 100 472 o | 68 227 o | 1 |
| gaps | 25 | 106 ms | 589 469 o | 75 426 o | 68 124 o | 1 |
| incoherent | 22 | 83 ms | 577 344 o | 85 347 o | 60 917 o | 1 |

Budgets de test respectés (2 000 ms, 64 MiB, 2 Mo, 1 Mo). Mesures non
représentatives de la production ; budgets de production `NOT_MEASURED`.

## 4. Preuves d'isolation

- Hook d'audit installé avant toute commande : connexion socket, résolution
  DNS, `urllib` → `PermissionError RADAR_OFFLINE_GUARD` (E01) ;
  `subprocess`, `os.system`, `fork` refusés (E05) ; écriture hors
  `--state-dir` refusée, y compris `../` (E06).
- Imports limités par AST à la bibliothèque standard et à
  `scanner_universe.{catalogues,universe}` ; aucun module PPL, FIN, PAPER,
  Advisor, Risk, opérateur chargé après exécution (E03, E04).
- `git status` identique avant et après exécution depuis la racine (E11).
- `deep_observation_jobs = []`, autorité `false` partout, propositions
  `PROPOSED_NOT_AUTHORIZED` (E12) ; seuls `preferences.json` et
  `history.json` sont écrits, atomiquement.
- Deux exports successifs : mêmes octets, même SHA-256 (E10).

## 5. Limites

- Données SYNTHETIC ; seuils de régime et de score non calibrés.
- Aucune source réelle de surveillance légère multi-marché sur main.
- Gates C2-C et C2-D absentes du dépôt : UNKNOWN.
- Preuves locales dans un conteneur root ; la CI GitHub de la PR #607 fait foi
  pour Python 3.11 non privilégié.

## 6. Verdict

**GO R0** (source) : prototype fonctionnel, isolé, déterministe, sans autorité
de collecte. Ce GO n'autorise ni déploiement, ni collecte réseau, ni L2,
ni PAPER.
