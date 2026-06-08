# ADR-0001 — Architecture V2 : 4 couches + 9 Bounded Contexts

**Date :** 2026-06-08
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

Le projet avait atteint 89 dossiers racine avec 7 doublons fonctionnels identifiés :
3 moteurs de risque concurrents, 2 event bus, 3 runtimes, 5 machines d'états, 4 dashboards.
L'architecture implicite rendait chaque modification risquée — les dépendances entre modules
n'étaient pas documentées, et les responsabilités des modules se chevauchaient.

Déclencheur immédiat : la phase ALPHA_DISCOVERY_100 (gel architecture pendant le burn-in)
a fourni le temps de cartographier l'existant sans modifier le comportement.

## Décision

Adopter une architecture explicite en **4 couches** (Platform → Core → Domains → Applications)
avec **9 Bounded Contexts** métier, communiquant par événements via `core/event_bus/` uniquement.

Migration progressive (pas de Big Bang) : chaque module source est d'abord encapsulé dans un shim
DEPRECATED, puis supprimé après 14 jours sans imports résiduels.

## Alternatives rejetées

| Alternative | Raison du rejet |
|------------|----------------|
| Big Bang (tout réécrire en une fois) | Risque opérationnel inacceptable — le VPS tourne en production avec de l'argent réel en cours de burn-in |
| Microservices (séparation par processus) | Overhead réseau et complexité d'orchestration non justifiés à ce stade ; DDD intra-process suffit |
| Garder l'architecture implicite | Les doublons s'auto-alimentent — chaque nouvelle feature crée un nouveau doublon |
| Architecture hexagonale pure | Trop contraignante pour les modules quantitatifs où les ports/adapters introduisent de la latence de calcul |

## Conséquences

**Positives :**
- Règle des dépendances encodée dans des tests automatiques (`tests/test_architecture.py`)
- Onboarding d'un nouveau module : répondre aux 4 questions souveraines (BC / responsabilité / contrat / doublon)
- KPIs de dette architecture mesurables : dossiers racine 89→<40, runtimes 3→1, etc.
- ADR comme trace de décision — dans 6 mois on sait pourquoi, pas seulement quoi

**Négatives / compromis :**
- La migration Phase 0C prend du temps (estimé 5-8 sessions)
- Les shims temporaires introduisent une complexité transitoire (délai max 14j)
- Les modules `risk/` et `governance/` sont bloqués jusqu'à ALPHA_DISCOVERY_100 levé

**Règles induites :**
- Tout nouveau module répond aux 4 questions (`docs/MIGRATION_MATRIX.md §5`)
- Toute PR de migration respecte le budget (`docs/MIGRATION_MATRIX.md §3`)
- Aucun import direct inter-Bounded-Contexts (passer par `core/event_bus/`)
- Les violations de frontières DDD brisent le build (`tests/test_architecture.py`)
