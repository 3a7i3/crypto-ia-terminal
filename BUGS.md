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
| BUG-001 | open | documentation | Le `README.md` racine pointe vers plusieurs fichiers sans prefixe `docs\`, alors que les fichiers existent sous `docs\...` | eleve | Exemples confirmes : `ONBOARDING_QUICK_START.md`, `QUICK_START_V91.md`, `CONFIG_REFERENCE_V91.md`, `DOCUMENTATION_INDEX.md`, `ROADMAP_V9_V10_V11.md` |
| BUG-002 | open | documentation | Les badges du `README.md` utilisent encore les placeholders `<OWNER>` et `<REPO>` | faible | Le rendu public est faux tant que les valeurs ne sont pas remplacees |
| BUG-003 | open | architecture | Mismatch entre les noms de regime retournes par certains modules et le format `MarketRegime` utilise ailleurs | eleve | Documente dans `ARCHITECTURE_NOTES.md`, cela impose des mappings fragiles |
| BUG-004 | open | architecture | `blacklisted_regimes` n'utilise pas un format unique entre l'API historique et le flux `DecisionPacket` | eleve | Un regime cense etre bloque peut passer silencieusement si le format configure n'est pas le bon |
| BUG-005 | open | architecture | Deux enums de conviction coexistent avec des valeurs incompatibles | moyen | Duplication entre le moteur local de conviction et le coeur `DecisionPacket` |
| BUG-006 | open | tests | Quelques fichiers `test_*.py` racine restent a fiabiliser ou reclasser | moyen | Cas cites dans `ROOT_TEST_AUDIT.md` : `test_analyze_strategy_niches.py`, `test_fallbacks_intelligents.py`, `test_fullsuite.py`, `test_onboarding_feedback_playwright.py`, `test_plot_god_mode.py`, `test_security_permissions.py` |

## Tri rapide

- Priorite haute : BUG-001, BUG-003, BUG-004
- Priorite moyenne : BUG-005, BUG-006
- Priorite basse mais visible : BUG-002
