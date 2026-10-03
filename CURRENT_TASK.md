# Stockage Machine — APP-STORAGE-01

Mission [#368](https://github.com/3a7i3/crypto-ia-terminal/issues/368), parent
[#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323), roadmap
[#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285).

Suite du Centre d’événements #361/#364 intégré. Combler le reliquat de stockage
CryptoRadar dans Système, sans ouvrir les DecisionPacket JSONL.
[Contrat APP-STORAGE-01](docs/contracts/APP_STORAGE_01_CONTRACT.md).
Base source `8aad0ac42705f50e626aa802340a23c8b5c94aa9` ; branche `feat/app-storage-01`.
Vérifier la disposition GitHub avant reprise ; source intégrée ≠ runtime déployé.

Capture bornée des métadonnées de fichiers, volume logique exact en octets,
projection atomique séparée, API GET-only et carte indépendante sur Système.
Unknown, absent, vide, erreur ou mutation concurrente restent distincts.
Lecture HTTP commune Events/Stockage, sérialisée et bornée à 10 s.

[Entrée développeur](docs/DEVELOPER_ENTRYPOINT.md) ;
[inventaire de parité](docs/plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md).
Tests et captures locaux synthétiques ; aucun accès VPS configuré dans la session.
Burn-in #282 et garde-fou #286 intact ; aucun retrait de transport/CryptoRadar.
