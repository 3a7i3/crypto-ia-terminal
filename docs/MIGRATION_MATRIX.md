# MIGRATION MATRIX — Phase 0C

> **Document vivant** — mis à jour après chaque PR de migration.
> Généré le 2026-06-08.
> **Règle :** Aucune migration sans entrée dans cette matrice. Aucune entrée sans réponse aux 4 questions souveraines (§5).

---

## 1. TABLEAU DE BORD

| Indicateur              | Baseline | Objectif | Actuel |
|-------------------------|--------:|--------:|------:|
| Dossiers racine         |      89 |     <40 |    89 |
| Doublons fonctionnels   |       7 |       0 |     7 |
| Imports circulaires     |       ? |       0 |     ? |
| Runtime unique          |       3 |       1 |     3 |
| Event Bus unique        |       2 |       1 |     2 |
| Risk Engine unique      |       3 |       1 |     3 |
| Dashboard unique        |       4 |       1 |     4 |
| Strategy Factory unique |       2 |       1 |     2 |

> **Règle de lecture :** Une migration qui n'améliore aucun de ces indicateurs est une migration inutile.

---

## 2. MATRICE DE MIGRATION

| Module              | Remplacer par                     | Risque  | Dépendants | Shim | État      | PR  |
|---------------------|----------------------------------|---------|----------:|------|-----------|-----|
| `dashboard/` (4x)  | `applications/dashboard/`         | Faible  |          0 | Non  | Planifié  | —   |
| `market_radar/`    | `domains/market/radar/`           | Faible  |          3 | Oui  | Planifié  | —   |
| `observability/`   | `platform/observability/`         | Faible  |          8 | Oui  | Planifié  | —   |
| `monitoring/`      | `platform/observability/`         | Faible  |          5 | Oui  | Planifié  | —   |
| `health/`          | `platform/observability/`         | Faible  |          3 | Non  | Planifié  | —   |
| `databases/`       | `platform/storage/`               | Faible  |         12 | Oui  | Planifié  | —   |
| `deploy/` + `k8s/` | `platform/deployment/`            | Faible  |          0 | Non  | Planifié  | —   |
| `event_bus/`       | `core/event_bus/`                 | Moyen   |         15 | Oui  | Planifié  | —   |
| `src/events/`      | `core/event_bus/`                 | Moyen   |          8 | Oui  | Planifié  | —   |
| `runtime/` (3x)    | `core/kernel/`                    | Élevé   |         22 | Oui  | Planifié  | —   |
| `system/`          | `core/startup/` + `core/integrity/` | Élevé |         18 | Oui  | Planifié  | —   |
| `cold_start/`      | `core/startup/`                   | Moyen   |          7 | Oui  | Planifié  | —   |
| `terminal_core/`   | Suppression (doublon `core/`)     | Faible  |          1 | Non  | Planifié  | —   |
| `strategy_factory/` (2x) | `domains/strategy/factory/` | Élevé  |         18 | Oui  | Planifié  | —   |
| `risk/` (3x)       | `domains/risk/engine/`            | Critique|         30 | Oui  | Bloqué*   | —   |
| `governance/`      | `domains/governance/`             | Élevé   |         24 | Oui  | Bloqué*   | —   |
| `supervision/`     | `domains/supervision/`            | Élevé   |         16 | Oui  | Planifié  | —   |
| `audit/`           | `domains/governance/audit/`       | Moyen   |          8 | Oui  | Planifié  | —   |
| `paper_trading/`   | `domains/simulation/paper/`       | Moyen   |         10 | Oui  | Planifié  | —   |
| `src/backtest/`    | `domains/simulation/backtest/`    | Faible  |          6 | Oui  | Planifié  | —   |
| `lm_studio/`       | `domains/intelligence/llm/`       | Faible  |          2 | Non  | Planifié  | —   |
| `ai_autonomous_loop/` | Suppression (zombie)           | Faible  |          0 | Non  | Planifié  | —   |
| `pieuvre/`         | `domains/supervision/pieuvre/`    | Moyen   |          5 | Non  | Planifié  | —   |
| `capital_deployment/` | `domains/portfolio/deployment/` | Élevé |         14 | Oui  | Planifié  | —   |
| `meta_learning/`   | `domains/intelligence/meta_learning/` | Moyen |       9 | Oui  | Planifié  | —   |

> \* **Bloqué ALPHA_DISCOVERY_100** : ces modules ne migrent pas avant 100 trades fermés.

**Colonnes :**
- **Risque** : Faible (tests couverts, peu de dépendants) / Moyen / Élevé / Critique
- **Dépendants** : nombre d'imports actifs vers ce module
- **Shim** : shim temporaire requis pendant la transition
- **État** : Planifié / En cours / Terminé / Bloqué

---

## 3. BUDGET PAR PR DE MIGRATION

Chaque PR de migration doit respecter ces limites strictes :

```
📦 1 à 3 modules maximum par PR
🧪 100% tests verts avant et après merge
📉 Réduction nette : au moins 1 module ou 5 imports supprimés
🚫 Zéro nouveau doublon introduit
🔄 Shim présent si des imports existants utilisent l'ancien chemin
⏱️ Shim supprimé dans les 14 jours si aucun import restant
```

**Anti-patterns interdits :**
- Déplacer un fichier sans mettre à jour ses imports actifs
- Créer un nouveau module sans passer par la règle des 4 questions (§5)
- Merger une PR de migration si un test gouvernance régresse

---

## 4. ORDRE DE MIGRATION (du plus indépendant vers le plus central)

### Phase 1 — Modules périphériques 🟢 (risque nul)
*Aucun code métier. Aucun shim requis.*

1. Dashboards multiples → `applications/dashboard/`
2. Launchers / scripts → `scripts/launchers/`
3. Rapports racine → `docs/reports/`
4. Archives → `archives/`
5. `ai_autonomous_loop/` → Suppression (zombie, `__init__.py` vide)

**Critère de clôture :** `ls -d */ | wc -l` < 70 dossiers racine.

---

### Phase 2 — Modules de support 🟢 (risque faible)
*Peu de dépendants. Shim recommandé.*

6. `observability/` + `monitoring/` + `health/` + `metrics/` → `platform/observability/`
7. `databases/` → `platform/storage/`
8. `deploy/` + `k8s/` + `install/` → `platform/deployment/`
9. `lm_studio/` → `domains/intelligence/llm/`
10. `terminal_core/` → Suppression (doublon `core/`)

**Critère de clôture :** `grep -r "from observability" . | wc -l` = 0.

---

### Phase 3 — Services techniques 🟡 (risque moyen — shims obligatoires)
*Les shims sont critiques ici. Tester 48h avant de supprimer.*

11. `event_bus/` + `src/events/` → `core/event_bus/`
12. `runtime/` (3x) → `core/kernel/`
13. `cold_start/` → `core/startup/`
14. `system/` → `core/startup/` + `core/integrity/`
15. `exchange_constraints/` → `domains/market/constraints/`

**Critère de clôture :** `grep -rn "from event_bus import" . | wc -l` = 0.

---

### Phase 4 — Domaines métier 🟠 (risque élevé — peer review obligatoire)
*Les frontières DDD se fixent ici. Pas de raccourci.*

16. `market_radar/` + `quant_hedge_ai/market_radar/` → `domains/market/radar/`
17. `paper_trading/` + `src/paper/` → `domains/simulation/paper/`
18. `src/backtest/` → `domains/simulation/backtest/`
19. `strategy_factory/` (2x) → `domains/strategy/factory/`
20. `capital_deployment/` → `domains/portfolio/deployment/`
21. `meta_learning/` → `domains/intelligence/meta_learning/`
22. `pieuvre/` → `domains/supervision/pieuvre/`
23. `supervision/` → `domains/supervision/`
24. `audit/` → `domains/governance/audit/`

**Critère de clôture :** Matrice §6 de TO-BE respectée (aucune dépendance inter-contexte directe).

---

### Phase 5 — Cœur décisionnel 🔴 (critique — migration après validation complète Phase 4)
*Ces modules ne bougent qu'une fois le reste stabilisé.*

25. `governance/` → `domains/governance/approval/` + `authority/` + `trace/`
26. `risk/` (3x) → `domains/risk/engine/` (un seul moteur)
27. `core/` — refactorisation interne vers `core/contracts/` + `core/kernel/`

**Prérequis strict :** ALPHA_DISCOVERY_100 levé + 30 jours de stabilité en production.

---

## 5. LA RÈGLE DES 4 QUESTIONS (souveraine)

À partir de la Phase 0C, **aucun nouveau module n'est créé** sans répondre à ces 4 questions. Si une réponse est floue, la création est reportée.

```
1. À quel Bounded Context appartient-il ?
   → Réponse obligatoire parmi les 9 BC du TO-BE.
   → "Utilitaire" ou "transverse" n'est pas une réponse.

2. Quelle responsabilité unique apporte-t-il ?
   → Une seule phrase. Si deux phrases sont nécessaires, c'est deux modules.

3. Quel contrat public expose-t-il ?
   → Liste des types/fonctions dans core/contracts/ ou sa propre API.

4. Existe-t-il déjà un module qui couvre cette responsabilité ?
   → Vérifier dans ARCHITECTURE_V2_AS_IS.md §1 avant de créer.
   → Si oui : enrichir l'existant. Si non : créer avec la fiche §13 du TO-BE.
```

---

## 6. MODÈLE DE SHIM

```python
# ancien_chemin/__init__.py
"""
⚠️ DEPRECATED — Ce module a migré vers <nouveau_chemin>.

Ce shim sera supprimé quand :
  1. Aucun import n'utilise plus l'ancien chemin.
  2. Les tests passent avec le nouveau chemin.
  3. Le shim a existé pendant ≥ 14 jours.

Migration date  : YYYY-MM-DD
Target          : <nouveau_chemin>
Dépendants (N)  : <nombre>
"""
import warnings as _warnings

_warnings.warn(
    "<ancien_chemin> est déprécié. Utilisez <nouveau_chemin>.",
    DeprecationWarning,
    stacklevel=2,
)

from <nouveau_chemin> import *  # noqa: F401, F403
```

---

## 7. CHECKLIST PAR PR DE MIGRATION

```
Avant la PR :
  [ ] Entrée dans cette matrice créée (module, risque, dépendants)
  [ ] 4 questions souveraines répondues
  [ ] grep des imports actifs vers l'ancien module effectué
  [ ] Shim créé si N dépendants > 0
  [ ] Tests verts sur branche de migration

Après merge :
  [ ] Indicateurs §1 mis à jour
  [ ] État matrice §2 → "Terminé"
  [ ] Ticket de suppression du shim créé (délai : 14 jours)
  [ ] ARCHITECTURE_V2_AS_IS.md mis à jour (suppression module)
```

---

> **Ce document est le plan de vol de la Phase 0C.**
> Il est mis à jour après chaque PR. Il ne remplace pas ARCHITECTURE_V2_TO_BE.md (la constitution) — il en est l'outil d'exécution.
