# ADR-0008 — Rule DS-001 : Runtime path resolution

- **Statut** : Accepté
- **Date** : 2026-07-03
- **Contexte** : Sprints S1/S3/S4 (Scientific Data Guard, décontamination des données)

## Contexte

Entre juin et juillet 2026, **sept occurrences** du même anti-pattern ont causé
la contamination des données scientifiques de production par la suite de tests :

| # | Emplacement | Variante de l'anti-pattern | Impact |
|---|---|---|---|
| 1 | `tests/test_p6_validation.py` → `regret_analysis.jsonl` | pas d'isolation | 91,8 % contaminé |
| 2 | `WarmupReport.archive_to_black_box()` | littéral en défaut de signature | `black_box.jsonl` 98 % contaminé |
| 3 | `WarmupReport.save()` / `_REPORT_DIR` | constante de module figée à l'import | 46 567 fichiers (206 Mo) |
| 4 | `paper_trading/recorder._DEFAULT_PATH` | défaut évalué à l'import (fixture no-op) | `paper_trades.jsonl` 95 % contaminé |
| 5 | `warmup_state_machine._STATE_PERSIST_PATH` | constante figée à l'import | état FAILED **signé HMAC** persisté |
| 6 | `bypass_detector._TOKEN_PATH` | constante figée à l'import | leak latent (`live_ready.token`) |
| 7 | `observability/json_logger.LOG_ROOT` | `Path(__file__)` absolu, handler ouvert à l'import | logs runtime pollués |

Un état de test **signé HMAC** (occurrence 5) passe `verify_state()` et peut
influencer le comportement réel au démarrage — la gravité dépasse la simple
pollution de métriques.

## Décision — Rule DS-001

Tout chemin configurable (`databases/`, `cache/`, rapports, journaux,
SQLite, tokens…) DOIT être résolu **à l'exécution** — dans `__init__` ou
dans la méthode d'ouverture/écriture — et JAMAIS dans :

1. **une valeur par défaut de signature** :
   `def save(self, path: str = "databases/x.jsonl")` — le littéral est figé
   à la définition de la fonction ; aucun mécanisme d'injection ne l'atteint ;
2. **une constante de module dépendant de l'environnement** :
   `_PATH = Path(os.getenv("X_PATH", "databases/x.jsonl"))` —
   `monkeypatch.setenv()` est **inopérant** après l'import ; seul
   `monkeypatch.setattr` sur l'attribut de module fonctionne ;
3. **une variable évaluée à l'import** (y compris `Path(__file__)...`
   pour des chemins d'écriture, et les handlers de logging ouverts à l'import).

### Forme correcte

```python
def _resolve_path() -> Path:
    """Résolu à CHAQUE appel — injectable par env, testable, jamais figé."""
    return Path(os.getenv("X_PATH", "databases/x.jsonl"))

class Writer:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else _resolve_path()
```

## Défense en profondeur côté tests

La règle ci-dessus est la solution **côté code**. Côté tests, trois couches
complémentaires (toutes dans le `conftest.py` racine) :

1. **Env vars au niveau module du conftest** — posées AVANT tout import de
   module de test, elles atteignent même les constantes figées à l'import
   (`OBS_LOG_ROOT`, `REJECTION_STORE_DIR`, `COLD_START_REPORT_DIR`,
   `BLACK_BOX_PATH`). Chemins **absolus** obligatoires : un thread
   d'arrière-plan peut flusher APRÈS restauration du CWD par le teardown,
   et un chemin relatif résoudrait alors dans le vrai repo.
2. **Fixtures autouse** patchant les attributs de module et les défauts de
   signature non injectables (`_isolate_paper_recorder`,
   `_isolate_cold_start_persistence`).
3. **`monkeypatch.chdir(tmp_path)`** pour les tests exerçant `main()`
   (smoke tests) : toutes les écritures relatives partent en tmp, sans
   modifier le code gelé (`advisor_loop.py`, phase de validation
   scientifique). Valide UNIQUEMENT si aucun chemin n'est ancré via
   `__file__`/`abspath` — à vérifier empiriquement (voir ci-dessous).

## Méthode de vérification empirique

Toute correction d'isolation DOIT être validée par observation directe du
système de fichiers, pas seulement par le passage des tests :

```bash
touch /tmp/marker && pytest <suites> -q && sleep 2  # threads retardataires
find . -newer /tmp/marker -type f \
  -not -path "./.git/*" -not -path "*/__pycache__/*" \
  -not -path "./.pytest_cache/*"
# Résultat attendu : VIDE.
```

Contre-épreuve : retirer le correctif, relancer, constater la réapparition
du leak (établit la causalité).

## Conséquences

- Tout nouveau module écrivant sur disque est revu à l'aune de DS-001
  (revue de code + `scripts/default_path_audit.py`, Sprint S2, automatisera
  la détection des trois variantes).
- Le garde-fou SHA256 (`databases/`, `cache/`) reste le filet de sécurité
  final : DS-001 prévient, le garde-fou détecte.
