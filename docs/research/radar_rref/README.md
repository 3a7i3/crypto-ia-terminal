# R-REF — Archive des sorties Radar antérieures (D-R1)

R-REF retire la référence obligatoire `kraken:spot:BTC/USDT` du Radar
(`radar-rules/1.2.0`, `radar-ranking/1.3.0`, `radar-evaluation/1.2.0`). Contrat :
[CAT_R0_CONTRAT_RADAR.md, section 10](../../contracts/CAT_R0_CONTRAT_RADAR.md).

Ce dossier conserve, **telles qu'elles ont été produites**, les sorties des
moteurs antérieurs sur les entrées SYNTHETIC du dépôt. Elles ne sont jamais
régénérées par le moteur courant, et aucun moteur historique n'est maintenu
actif.

| Dossier | Moteur | Commit | Versions | Sorties |
|---|---|---|---|---|
| `archive/r0_ca0354f/` | R0 | `ca0354f99b2ec2c8fa5ec8ba61c21280f91ed823` | `radar-evaluation/1.0.0`, `radar-rules/1.0.0`, `radar-ranking/1.1.0` | 4 fixtures × 3 missions |
| `archive/r1b_77bd30e/` | R1-B | `77bd30e2888a11207c2c0dbce19eaa62fd4421ac` | `radar-evaluation/1.1.0`, `radar-rules/1.1.0`, `radar-ranking/1.2.0` | (4 fixtures + 1 lot) × 3 missions |

`archive/MANIFEST.json` (`radar-archive-manifest/1.0.0`) donne pour chaque
sortie : chemin, taille, SHA-256, commit et étape du moteur, versions, mission,
nature SYNTHETIC, `evaluation_sha256`, source (chemin, SHA-256 de la fixture ou
du lot au commit moteur, identifiant et empreinte du jeu de données) et la
commande de production.

**Vérifier n'est pas rejouer.** Les tests `tests/radar_selection/test_h_rref.py`
(RR4) vérifient l'empreinte épinglée du manifeste, l'empreinte de chaque
fichier, ses versions, son sceau `evaluation_sha256` et l'identité des entrées
citées avec les entrées actuelles. Ils ne recalculent aucune sortie historique.
Pour rejouer une sortie, extraire un checkout séparé du commit moteur et y lancer
`producing_command` ; le 2026-11-25, les 27 sorties ont été ainsi reproduites à
l'octet avant leur archivage.

Production : `python -m observability.radar_selection ... export` dans un
checkout de chaque commit moteur (aucun réseau, aucune donnée réelle, aucun
runtime).
