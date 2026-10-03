# Reprise application et consolidation — 2026-10-03

Mission : [APP-CLEANUP-01 · #359](https://github.com/3a7i3/crypto-ia-terminal/issues/359).

Demande opérateur : revoir les issues, tester l'app et ses sorties, classer les
chantiers inachevés et réduire le bruit documentaire. Burn-in intact.

Base source : `385b8c9cdd4f0f67fd58898ba18f6a37b5e308a4`.
Branche locale : `audit/app-coherence-cleanup`. Cette reprise ne certifie ni U7
globalement, ni le runtime. Voir l'[inventaire et les résultats](docs/plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md#revue-application-et-consolidation--2026-10-03).

DOC-CANON #340/#341 est déjà intégré. U8 #342/#343 est préparé en source,
sans autorisation de déploiement. #257 est remédiée après #344/#346 ; #315
Gate O reste ouvert. Les premiers commentaires ne décrivent pas forcément
l'état final : vérifier les dispositions des issues.

Entrée de travail : [docs/DEVELOPER_ENTRYPOINT.md](docs/DEVELOPER_ENTRYPOINT.md).
Tests locaux sur données synthétiques ; aucun accès machine disponible ici.

Priorisation : [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285).
Cockpit : [#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323).
Garde-fou : [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) actif.
Burn-in : [#282](https://github.com/3a7i3/crypto-ia-terminal/issues/282), checkpoints
READ-ONLY distincts ; aucune nouvelle observation VPS dans cette reprise.
