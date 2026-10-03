# Centre d’événements — APP-EVENTS-01

Mission : [#361](https://github.com/3a7i3/crypto-ia-terminal/issues/361), parent
[#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323), priorisation
[#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285).

Sources, contrat fermé et implémentation passive dans l’app :
[APP_EVENTS_01_CONTRACT](docs/contracts/APP_EVENTS_01_CONTRACT.md).
Base source `7d7b29669f9940f5e7e47b5b1c7d88371f067fbb` ; branche `feat/app-events-01`.
Vérifier la disposition GitHub avant reprise ; fusion source ≠ publication runtime.

Trois sources explicites : alertes P12, audit supervision et lifecycles déjà
projetés par U2. Capture atomique séparée, API GET-only, vue indépendante.
Aucun journal PPL lu par l’API/frontend, aucun moteur ou autoheal activé.

La consolidation [#359](https://github.com/3a7i3/crypto-ia-terminal/issues/359)
a été intégrée par #360. L’[inventaire application](docs/plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md#revue-application-et-consolidation--2026-10-03)
conserve les résultats de cette tranche précédente.

[Entrée développeur](docs/DEVELOPER_ENTRYPOINT.md). Tests locaux synthétiques ;
aucune observation Machine nouvelle. Burn-in [#282](https://github.com/3a7i3/crypto-ia-terminal/issues/282)
et garde-fou [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) inchangés.
