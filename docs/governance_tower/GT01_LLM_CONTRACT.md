# GT01-I — Contrat de l'adaptateur de modèle (TESTÉ HORS LIGNE SEULEMENT)

Statuts : `GT01_LLM_ADAPTER_TESTED_OFFLINE` ; `GT01_LLM_LIVE = DISABLED`.
Code : `governance_tower/sentinel/llm_adapter.py`. Tests : `tests/governance_tower/test_gt01_llm_adapter.py`.

## 1. Ce que l'adaptateur fait

```
preuves admises → faits structurés → expurgation / rétention VPS → requête bornée
  → réponse JSON stricte → validation → fusion INFERRED étiquetée (ou rejet fail-closed)
```

- Désactivé sauf `enabled=True` explicite ; seul `OfflineMockTransport` (en mémoire) est admis.
- Aucun SDK, aucune clé, aucun réseau dans le module (vérifié par test AST et par blocage de socket).
- La réponse déterministe reste la base factuelle. Le modèle ajoute au plus 8 interprétations
  `INFERRED`, préfixées « [Interprétation modèle hors ligne, non vérifiée] », citant des preuves
  admises ; jamais un constat `OBSERVED`, jamais une proposition de mission.

## 2. Données qui iraient au modèle (si GT01-I était ouverte)

| Catégorie | Par défaut | Remarque |
|---|---|---|
| Observations GitHub (dépôt, CI, PR/issues, fichiers, compare) | transmises, expurgées, ≤ 600 car. par fait, ≤ 80 faits | titres et corps marqués `UNTRUSTED_QUOTE` |
| Diagnostics, écarts, référence #286 déclarée | transmis | preuves VPS retirées des citations |
| Observations VPS (service, déploiement, stockage) | **retenues** | `allow_host_facts=True` seulement avec accord explicite |
| Secrets, PPL, FIN, journaux | jamais | non lus par Sentinel |
| Question de l'opérateur | transmise, ≤ 600 car. | refus `SECRET_IN_REQUEST` si un secret y figure |

Le run d'audit ne garde que l'empreinte SHA-256 de la requête, le nombre de faits, l'estimation
de jetons et le code de résultat ; jamais le texte du modèle.

## 3. Rejets (fail-closed)

`INVALID_JSON`, `DUPLICATE_KEY`, `NON_FINITE_NUMBER`, `SCHEMA_VIOLATION`, `OUTPUT_BUDGET_EXCEEDED`,
`UNCITED_INTERPRETATION`, `UNKNOWN_EVIDENCE`, `MARKUP_IN_OUTPUT`, `TOOL_REQUEST`, `ACTION_CLAIM`,
`AUTHORITY_CLAIM`, `UNSUPPORTED_HEALTH_CLAIM`, `SECRET_IN_OUTPUT`, `CONTROL_CHARACTER`,
`INSTRUCTION_IN_OUTPUT`, `INPUT_BUDGET_EXCEEDED`, `SECRET_IN_REQUEST`, `TRANSPORT_TIMEOUT`,
`TRANSPORT_ERROR`, `TRANSPORT_EMPTY`. Chaque rejet rend la réponse déterministe seule et une
incertitude qui nomme le code.

## 4. Coût

**Non mesuré.** Estimation prudente : 1 jeton ≈ 3 caractères. Sur le scénario nominal, la
question « Le VPS exécute-t-il la même version que GitHub ? » produit une requête estimée à
environ 1 800 jetons d'entrée (9 faits, 4 observations VPS retenues) ; plafonds par défaut :
6 000 jetons d'entrée, 1 200 de sortie. Aucun prix n'est avancé : il dépend du modèle choisi
à la gate GT01-I.

## 5. Ce que la gate GT01-I devra décider

Modèle et fournisseur, emplacement des données, rétention, budget mensuel, envoi ou non des
faits VPS, tests adversariaux sur le vrai modèle, journalisation, et procédure de retrait.
