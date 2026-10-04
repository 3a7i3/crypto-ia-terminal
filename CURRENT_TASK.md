# Reprise canonique — DOC-CANON-02

Mission active : [#380](https://github.com/3a7i3/crypto-ia-terminal/issues/380).
Roadmap : [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285).
Burn-in : [#282](https://github.com/3a7i3/crypto-ia-terminal/issues/282).
Garde-fou : [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286).
Cockpit : [#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323).

Baseline source de cette reprise :

`main@a057d4e972cd60ee32710d59f327b4185f3af287`

## État canonique

- Machine Maturity L0 : `CERTIFIED`.
- Machine Maturity L1 : `CERTIFIED`, chaîne canonique v2.
- certificat L1 canonique :
  `49d112260450cd3d34802e50aebbd3abd1922718f8cc9b789e81b8dc074e91cf`;
- `FORMAL_CERTIFIED_FRONTIER = L1`;
- `EVIDENCE_DEMONSTRATED_FRONTIER = L3`;
- `DEVELOPMENT_FRONTIER = L4`;
- prochain niveau formel : L2.
- #282 reste `ACTIVE_BURN_IN_OBSERVATION`.
- #286 reste `ACTIVE_BURN_IN_IMMUTABILITY_GUARD`.
- #315 Gate O reste `OPEN / NON_RESOLVED`.
- APP-UNIFY U7 global n'est pas encore certifié.
- APP-UNIFY U8 runtime n'est pas autorisé par ce document.
- #374 Agent Registry reste `PARKED_SOURCE_ONLY / DRAFT / NON_DEPLOYED`.

## Ordre de reprise

1. synchroniser la documentation canonique (#380) ;
2. effectuer un checkpoint #282 strictement READ-ONLY si un accès runtime autorisé existe ;
3. fermer la certification source globale APP-UNIFY U7 ;
4. certifier Machine Maturity L2 puis L3, séquentiellement ;
5. finaliser scientifiquement le burn-in lorsque ses conditions de sortie sont réellement satisfaites ;
6. seulement ensuite traiter U8 / L4 sous gates runtime dédiées ;
7. reprendre Agent Economy après ces frontières.

Ce fichier est un pointeur de reprise, pas une autorité runtime.

**SOURCE STATE ≠ DEPLOYED RUNTIME STATE.**

Aucune observation VPS fraîche n'est créée par DOC-CANON-02. La dernière vérité
runtime reste celle des preuves datées de #282/#286 jusqu'à un nouveau checkpoint
READ-ONLY autorisé. Aucun merge source n'autorise restart, deploy, mutation
PAPER/PPL/FIN, epoch/config, stratégie/risk/sizing, Watchdog, TESTNET/LIVE ou
écriture exchange.

Lire ensuite [docs/DEVELOPER_ENTRYPOINT.md](docs/DEVELOPER_ENTRYPOINT.md),
[CLAUDE.md](CLAUDE.md) et la mission GitHub applicable.
