# PAPER-STRESS-RESEARCH-01 — #401

SOURCE-ONLY / OFFLINE / NO PRODUCTION MUTATION. Verdict : INSUFFICIENT_EVIDENCE.

- [Rapport 1 — Architecture S0](01_architecture.md)
- [Rapport 2 — Protocole](02_protocole.md), [contrat JSON](protocol.json)
- [Rapport 3 — Résultats](03_resultats.md)
- [Rapport 4 — Gouvernance](04_gouvernance.md)
- [Rapport 5 — Readiness](05_readiness.md)
- [Validation](validation.md)

Exécution reproductible depuis une copie propre au SHA source indiqué dans
`source_manifest.json` (Python 3.12.14 local ; cible CI 3.11) :

```bash
python -B -m research_stress \
  --protocol docs/research/paper_stress_401/protocol.json \
  --research-code-sha <SHA_SOURCE_COMPLET_DU_MANIFEST>
```

La CLI imprime un envelope canonique avec SHA256. Aucun output/root par défaut.
Vérifier HEAD propre et empreintes de modules contre le manifest avant le run :
le SHA passé est une déclaration de l’appelant, pas une attestation autonome.
La sortie peut être conservée exclusivement dans un stockage Research indépendant,
create-only. `analytic_report.json` est la sortie NO_DATASET incluse pour revue.
Pour vérifier/recalculer :

```python
from pathlib import Path
from research_stress.campaign import build_report, verify_report
from research_stress.protocol import canonical, strict_json
root = Path("docs/research/paper_stress_401")
protocol = strict_json((root / "protocol.json").read_bytes())
envelope = strict_json((root / "analytic_report.json").read_bytes())
verify_report(envelope, protocol)
assert canonical(envelope) == canonical(build_report(
    protocol, research_code_sha=envelope["report"]["identity"]["research_code_sha"]))
```

Copie RL-DATA admissible : `--dataset-copy <copie_Research_immutable>` et
`--input-class DECLARED_IMMUTABLE_RESEARCH_COPY`. Validation de structure/hashes
n’est pas une certification de droit d’usage/provenance externe. Ne jamais passer
un chemin de ledger ou de checkout production. Les fixtures de test portent
SYNTHETIC_TEST_ONLY. Toute comparaison dynamique reste explicitement bloquée.

Validation du corpus Python en refusant les connexions et résolutions externes
(les API locales et mocks restent permis) :

```bash
PYTHONPATH="$PWD/tests/research_stress/offline_guard:$PWD" \
  python -B -m pytest -q -m 'not performance and not slow' tests/
```

Le garde est opt-in, sans modification du runtime ni des tests historiques.
Il couvre les événements réseau CPython audités, pas des appels natifs hostiles.
