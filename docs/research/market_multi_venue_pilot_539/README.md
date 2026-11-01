# Dossier de préparation du pilote #539

Statut : **préparé en source ; aucune collecte réelle, installation ou activation**.
[Contrat, identité et gates](../../contracts/MARKET_MULTI_VENUE_PILOT_539.md).
[PILOT_PLAN.json](PILOT_PLAN.json) est généré depuis `PilotPlan().document()` ;
il propose 4 bindings, 120 cycles, 600 secondes et au plus 724 GET.
La revue des mappings demeure PENDING_OPERATOR_REVIEW.

## Où se trouve chaque partie

| Partie | Chemin |
| --- | --- |
| Plan fermé et requêtes natives | observability/market_venues/pilot/plan.py |
| Métadonnées, timestamps et sondes d’horloge | observability/market_venues/pilot/capture.py |
| Transport HTTPS désactivé par défaut | observability/market_venues/pilot/transport.py |
| Boucle finie, budget, aucun scheduler | observability/market_venues/pilot/runner.py |
| Intentions, réponses brutes, reçus, publication | observability/market_venues/pilot/store.py |
| Vérification locale des liens de preuve | observability/market_venues/pilot/verify.py |
| Réponses inventées et horloge de test | observability/market_venues/pilot/synthetic.py |
| Génération de fixture par toute la chaîne | tests/cross_stack/generate_pilot_fixture.py |
| Test d’expiration entre deux lectures API | frontend/src/test/venueFreshness.compat.test.tsx |

## Commandes uniquement hors réseau

Depuis un checkout isolé et un environnement Python de tests :

```bash
python -m observability.market_venues.pilot --check-plan
pytest -q tests/market_venues/pilot/
```

Pour une simulation, le parent doit déjà exister, être absolu, sans symlink,
mode 0700 et appartenir à l’utilisateur courant :

```bash
python -m observability.market_venues.pilot --simulate --cycles 2 \
  --out /chemin/prive/market-venue-pilot-runs
python -m observability.market_venues.pilot --verify-run \
  /chemin/prive/market-venue-pilot-runs/IDENTIFIANT_DU_RUN
```

Le premier résultat donne l’identifiant exclusif du run. Le mode simulation
utilise une horloge fixe et des prix inventés, `evidence_kind=SYNTHETIC`,
`source_sha=0000000000000000000000000000000000000000`.
Ce SHA réservé ne doit jamais être présenté comme celui d’un collecteur réel.
La CLI ne possède pas de mode réseau ; une option inconnue est refusée.
Le vérificateur n’accorde aucune permission et ne certifie pas l’origine réseau.

Les tests du pilote bloquent les sockets ; le transport HTTP est vérifié avec
des doubles. La fixture T_market_pilot est générée depuis deux cycles
synthétiques, leurs preuves persistées, le vrai lecteur et la vraie route GET.
La CI exécute les tests Python et React puis la preuve navigateur sans serveur
HTTP pour les écrans Marché, avec sandbox Chromium conservé.

## Reprise après revue

Aucun service actif n’importe ce pilote. Aucun chemin d’app n’est raccordé.
L’onglet existant **Marché → Comparaison des plateformes** reste indisponible
tant qu’un artifact réel n’a pas sa propre admission et publication.
La prochaine tâche doit obtenir une décision explicite pour le premier run,
son processus isolé et ses bornes ; l’activation n’est pas une conséquence du
merge. Les gates et les limites de temps/custody sont détaillées dans le contrat.
