# Détail LMI et liquidité CryptoRadar — APP-LMI-DETAIL-01

Mission [#370](https://github.com/3a7i3/crypto-ia-terminal/issues/370), parent
[#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323), roadmap
[#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285).

Suite du stockage #368/#369 intégré. Détail par symbole : flux agressif,
liquidité bid/ask, résistance et composantes de l’état, via projection passive
fermée 1.1.0 et GET existant. Anciens artifacts 1.0.0 lisibles. Dates propres
aux groupes, valeurs exactes/null/zéro, provenance contractSize et limite
explicite des zéros de liquidité avant la première observation du carnet.

[Contrat et extension](docs/contracts/APP_UNIFY_01_U3B_MICROSTRUCTURE_CONTRACT.md).
Base source `d9cbb14d0b8a7f3818968f9de6871f435d9c87b3` ; branche `feat/app-lmi-detail-01`.
Vérifier la disposition GitHub avant reprise ; source intégrée ≠ runtime déployé.

[Entrée développeur](docs/DEVELOPER_ENTRYPOINT.md) ;
[inventaire de parité](docs/plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md).
Tests et captures synthétiques locaux ; aucun accès VPS configuré ici.
Burn-in #282/#286 intact ; aucun moteur, service, transport ou retrait CryptoRadar.
