# ADR-0006 — Decision Event Bus : découplage moteur/observateurs

**Date :** 2026-06-29
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

Sans Event Bus, le moteur de trading connaît directement chaque observateur :
    advisor_loop → Telegram
    advisor_loop → RejectionStore
    advisor_loop → RegretScheduler
    advisor_loop → (future) ACE
    advisor_loop → (future) Dashboard
    advisor_loop → (future) Governance

Chaque nouvelle phase (P4-P7) nécessite de modifier `advisor_loop.py` — le fichier le plus
critique du système. Ce couplage fort augmente le risque de régression à chaque extension.

Un `metrics_bus.py` existe déjà pour les métriques numériques (compteurs, gauges). Il n'est pas
conçu pour transporter des objets métier complets (DecisionObservation).

## Décision

Créer `observability/decision_event_bus.py` : un bus pub/sub léger qui transporte des
`DecisionObservation` immutables. `advisor_loop.py` appelle uniquement `bus.publish(obs)`.
Les listeners (Telegram, RejectionStore, RegretScheduler, ACE futur) s'abonnent au démarrage.

Dispatch asynchrone via `ThreadPoolExecutor(max_workers=4)` — les listeners ne bloquent jamais
le cycle de trading. Échecs silencieux (try/except par listener, log warning).

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Étendre `metrics_bus.py` | Conçu pour des float, pas pour des objets métier ; interface incompatible |
| Redis pub/sub | Dépendance externe, sérialisation/désérialisation, latence réseau |
| asyncio.Queue | Incompatible avec le threading model synchrone d'advisor_loop |
| Appels directs gardés | Chaque nouvelle phase = modification d'advisor_loop = risque régression |

## Conséquences

**Positives :**
- `advisor_loop.py` ne connaît plus aucun observateur après intégration complète
- Ajout d'une Phase 4-7 = nouveau listener, zéro modification du moteur de décision
- Les listeners peuvent être activés/désactivés indépendamment via feature flags
- Testable : bus mockable, listeners testables indépendamment

**Négatives / compromis :**
- Le dispatch asynchrone signifie que les erreurs de listener sont retardées (pas immédiates)
- `max_workers=4` est un paramètre à ajuster si les listeners deviennent nombreux
- Ordre de livraison non garanti entre listeners (chacun dans son thread)

**Règles induites :**
- Les listeners ne doivent pas modifier `DecisionObservation` (frozen dataclass)
- Les listeners ne peuvent pas faire remonter d'information au moteur de décision
- Chaque listener doit implémenter l'interface `Callable[[DecisionObservation], None]`
- Le bus se dégrade silencieusement si désactivé (feature flag FEATURE_EVENT_BUS=false)
- Le bus principal est un singleton (`_bus` module-level) — pas de DI complexe
