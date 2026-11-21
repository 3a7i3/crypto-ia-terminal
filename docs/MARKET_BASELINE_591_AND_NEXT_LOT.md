# Marché — Référence VPS et prochain lot

## Microstructure — état constaté le 20 novembre 2026 (Mexico)

- VPS `crypto-restore-01`. Frontend déployé depuis `6cf82fb7c398d6a6ddbdb079a2fbdd6223807bbc` (PR [#591](https://github.com/3a7i3/crypto-ia-terminal/pull/591), ouverte en brouillon au moment du contrôle).
- Release `/opt/cat-app/releases/CAT-FOOTPRINT-591-6cf82fb7`, montée en lecture seule sur le dist de Finance V6 RC1 par le drop-in `zzzzzzzzzzzzzzzz-footprint-v3-l1.conf`.
- Services web et API actifs. HTTPS Tailscale sert `index-BY-koc7N.js`. HTTP local 200 sur Microstructure, Finance, le bundle, le service worker et le rejeu. Le 200 Finance vérifie la livraison de la page.
- SHA-256 JS `f02af34431a1920b3651b2389d46749ba8f5872cd3cec2c974c7f8e8dee50ff6`.
- SHA-256 service worker `947a992594876d5c722b3af8d8da89d3300d015fc2b3da767b5a51d65a53fa2f`.
- SHA-256 rejeu MEXC `a41c608814c02a10e5a9369b11806196b770ad578db0d5037368413c4cce391f`. Rejeu historique avec couverture partielle.
- Retour arrière par `sudo bash /home/lecanada26/install-footprint-591.sh rollback`. Configuration précédente vérifiée dans `/opt/cat-app/releases/footprint-591-previous.conf`, vers `CAT-FOOTPRINT-V3-L1-ab941c2`.

## Plateformes & levier et Flux & rythmes — contrat de présentation V1.0

| Propriétaire | Données et visualisations |
| --- | --- |
| Plateformes & levier | Bid/Ask et spread comparatif, écart entre plateformes, marque, indice, OI et variation 1 h/4 h/24 h, funding et intervalle, prime marque/indice, basis dérivé/spot, devise/unité/taille des contrats et comparabilité. Graphique Prix + OI et historiques funding/basis. |
| Flux & rythmes | Volume exécuté par période, nombre et cadence des transactions, profondeur/déséquilibres/changements du carnet, concentration des activités aux quarts d'heure et baseline/placebo. Transmission inter-marchés, retard, stabilité et coûts pour un module futur. |
| Microstructure | Footprint Bid × Ask au prix, imbalances des transactions, delta par bougie, CVD, Delta Profile et Volume Profile. |

Les sources peuvent être partagées. Chaque mesure a un propriétaire de présentation. Les autres vues peuvent afficher un repère discret ou un lien lorsque le contrat le permet. Couverture, fraîcheur, provenance et motifs d'indisponibilité accompagnent les valeurs. Les métriques de contrat (marque, indice, prime, basis) et les visualisations spécialisées restent dans leur vue propriétaire.

- **Plateformes & levier** suit la deuxième maquette. Filtres, quatre cartes OI / variation OI / funding / prime ou basis et un seul graphique Prix + OI dans la vue principale. Comparaison spot, historiques funding/basis et qualité dans les détails. Préciser la référence exacte du champ prime ou basis. Les comparaisons USD/USDT, totaux d'OI et financements agrégés requièrent des unités, couvertures et intervalles comparables. Aucun score de stress ni signal.
- **Flux & rythmes** présente un graphique principal d'activité et trois sections spécialisées : Carnet et liquidité, Périodicité, Transmission inter-marchés. Afficher une mesure de retard seulement lorsqu'une source validée l'établit. Les chiffres des maquettes sont illustratifs.

## Point de départ et ordre de réalisation

Les vues `MarketVenuesView` et `MarketFlowView` existent. Sur le VPS, l'API `market-flow` répond 503 et `derivatives-stress` répond 404. La PR brouillon [#590](https://github.com/3a7i3/crypto-ia-terminal/pull/590) prépare le stress dérivés, son lecteur non configuré par défaut et la périodicité. Elle fournit du code à réutiliser après comparaison avec la base déployée.

1. Inventorier les champs, unités, fraîcheur et couverture par source, ainsi que les historiques effectivement disponibles. Relever les écarts de branches #590 et #591.
2. Réaliser Plateformes & levier à partir de Comparaison, puis vérifier les états disponible, partiel, périmé, indisponible et contrats non comparables. Afficher les séries seulement si leurs historiques et leur alignement temporel sont attestés.
3. Réaliser Flux & rythmes à partir de Flux. Qualifier la source avant d'afficher des graphiques alimentés. Relier la périodicité à une baseline et à un placebo explicites.
4. Vérifier Microstructure, Finance, les deux vues à 384 px et l'absence de duplications de graphiques. Les jeux d'essai restent identifiés comme tels.
