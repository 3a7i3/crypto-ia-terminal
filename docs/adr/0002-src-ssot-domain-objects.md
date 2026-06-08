# ADR-0002 — src/domain/ comme SSoT des objets métier

**Date :** 2026-06-08
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

`TradeEvent`, `Signal`, `Order`, `Position` existaient en plusieurs versions incompatibles
à travers le projet (dict, dataclass, namedtuple, classes ad-hoc). Chaque module définissait
sa propre représentation, rendant les pipelines de données fragiles et les tests difficiles.

La Phase B (2026-06) a introduit un pipeline dict-free mais les objets métier restaient
dispersés.

## Décision

`src/domain/` est la **Source Unique de Vérité** pour tous les objets métier fondamentaux.
Aucun autre module ne redéfinit `TradeEvent`, `Signal`, `Order`, ou `Position`.
Tous les modules importent depuis `src.domain.*`.

À terme (Phase 0C), ces types migrent vers `core/contracts/types.py` selon ADR-0001.

## Alternatives rejetées

| Alternative | Raison du rejet |
|------------|----------------|
| TypedDict partout | Pas de validation, pas d'immutabilité, pas de méthodes |
| Pydantic | Overhead de validation non justifié sur le hot path de backtest (10k+ appels/s) |
| Garder les dicts | Opaque, pas de type checking, source des bugs les plus silencieux |

## Conséquences

**Positives :**
- `TradeEvent` est immutable (frozen dataclass) — les invariants sont enforced à la création
- UTC enforced pour tous les timestamps — pas de bug de timezone
- `MarketRegime` est un enum — plus de strings magiques

**Négatives / compromis :**
- Migration des appels existants (dicts → objets) coûteuse en Phase B, faite
- Les modules legacy qui retournent des dicts doivent être adaptés progressivement

**Règles induites :**
- Interdiction de définir une classe `TradeEvent`, `Signal`, `Order`, `Position` ailleurs que `src/domain/`
- Détecté automatiquement par `tests/test_architecture.py` (à compléter)
