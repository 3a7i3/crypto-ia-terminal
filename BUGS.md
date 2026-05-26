# BUGS

## Regles

- Un bug = un item clair
- Indiquer le statut et l'impact
- Mettre a jour la ligne plutot que dupliquer l'information

## Statuts

- open
- in_progress
- blocked
- fixed

## Bugs suivis

| ID | Statut | Zone | Description | Impact | Notes |
|---|---|---|---|---|---|
| BUG-001 | fixed | documentation | Le `README.md` racine pointait vers plusieurs fichiers sans prefixe `docs\`, alors que les fichiers existent sous `docs\...` | eleve | Corrige le 2026-05-26 : liens visibles vers onboarding, quick start, config, index, roadmap, validation et rapports d'audit |
| BUG-002 | fixed | documentation | Les badges du `README.md` utilisaient encore les placeholders `<OWNER>` et `<REPO>` | faible | Corrige le 2026-05-26 avec `0xl1v/crypto-ai-terminal` |
| BUG-003 | open | architecture | Mismatch entre les noms de regime retournes par certains modules et le format `MarketRegime` utilise ailleurs | eleve | Documente dans `ARCHITECTURE_NOTES.md`, cela impose des mappings fragiles |
| BUG-004 | fixed | architecture | `blacklisted_regimes` n'utilisait pas un format unique entre l'API historique et le flux `DecisionPacket` | eleve | Corrige le 2026-05-26 : `GlobalRiskGate` normalise les regimes legacy et packet avant comparaison |
| BUG-005 | open | architecture | Deux enums de conviction coexistent avec des valeurs incompatibles | moyen | Duplication entre le moteur local de conviction et le coeur `DecisionPacket` |
| BUG-006 | open | tests | Quelques fichiers `test_*.py` racine restent a fiabiliser ou reclasser | moyen | Cas cites dans `ROOT_TEST_AUDIT.md` : `test_analyze_strategy_niches.py`, `test_fallbacks_intelligents.py`, `test_fullsuite.py`, `test_onboarding_feedback_playwright.py`, `test_plot_god_mode.py`, `test_security_permissions.py` |
| BUG-007 | open | environnement | La `.venv` locale pointe vers `C:\Users\WINDOWS\AppData\Local\Programs\Python\Python311\python.exe`, absent du poste courant | eleve | Bloque `pytest` local; commande test retournee : `No Python at ...Python311\python.exe` |

## Tri rapide

- Priorite haute : BUG-003, BUG-007
- Priorite moyenne : BUG-005, BUG-006
- Corriges dans cette passe : BUG-001, BUG-002, BUG-004
