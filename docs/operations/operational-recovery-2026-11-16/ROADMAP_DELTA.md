# Écarts explicites et mise à jour du suivi

## Références lues

- [#568](https://github.com/3a7i3/crypto-ia-terminal/issues/568) porte toujours la ligne `ACTIVE_CANONICAL` du 11 novembre et l'ancienne priorisation III-R1.1-A.
- Les décisions opérateur plus récentes [Vision V3](https://github.com/3a7i3/crypto-ia-terminal/issues/285#issuecomment-6872693051), [V3.1](https://github.com/3a7i3/crypto-ia-terminal/issues/285#issuecomment-6872726684) et [A9/V3.2](https://github.com/3a7i3/crypto-ia-terminal/issues/285#issuecomment-6873046840) font du scanner #574 l'unique chantier produit actif. #285 a donc aussi reçu de nouvelles décisions après sa bannière historique d'archivage.
- Dernier point de livraison lu avant synchronisation : [#574, 04:39 UTC](https://github.com/3a7i3/crypto-ia-terminal/issues/574#issuecomment-6907492555), encore « mobile pending / collecte permanente non autorisée ».
- GO OPERATIONAL RECOVERY reçu ensuite en conversation : priorité au cockpit quotidien, accès VPS et collecte publique continue autorisés, corpus historiques protégés ; M1-B.9→B.13 suspendus. Puis GO d'intégration dans l'app habituelle et demande de synchronisation GitHub.

La hiérarchie éditoriale #568/#285 présente des formulations historiques concurrentes. Ce bilan rattache les nouvelles décisions aux deux fils, sans effacer l'un d'eux, inventer une nouvelle certification ou renuméroter toute la roadmap. #576 est le suivi de cette livraison, pas une deuxième roadmap autonome.

## Plan initial → livré → reste ouvert

| Axe / étape | Réalisation vérifiée | État à retenir |
|---|---|---|
| A0 / contre-revue S2 | Correctifs D1 disponibles ; travaux M1 distincts, revue contradictoire et limites conservées | Pas clôture scientifique globale S2 par cette mission |
| A1 / mobile privé | Démonstration Samsung puis app habituelle sur 443 | Accès utilisateur démontré, recette Liste/accès négatif incomplète |
| A2 / DMI-ADX | Aucun calcul ajouté | NON FAIT ; mandat séparé avant code |
| A3 / ATR-RVOL-EMA-RSI-VWAP | Aucun calcul ajouté | NON FAIT |
| A4 / événements-phase-MTF | Navigation de séries MTF seulement | Pas confluence, phase, score ni événement calculé |
| A5 / sélection globale | 30 Spot USDT, sélection déterministe bornée du collecteur existant | Univers global, sélection dynamique/benchmark non faits |
| A6 / Flux | Onglets et API historiques conservés | Pas de Flux MEXC qualifié, CVD ou OI nouveau |
| A7 / contrat Advisor | Aucun raccordement | NON FAIT, aucune capacité d'action |
| A8 / release scanner | Installation et exploitation read-only sous GO OR ; restart, budget et recette visibles | Consultation acquise ; intégration source/main, CI exacte et qualification longue durée ouvertes |
| A9 / certification scientifique | Aucune expérience de signal nouvelle | NON FAIT ; aucune probabilité de profit ni avantage certifiés |
| III-R2 / app existante | Origine/identité PWA conservées, défaut radar, API commune, assets/worker mis à jour | Pas certification formelle U8 globale |
| III-R3.6 / ressources | Limites systemd et rétention neuve ; mesures ponctuelles réelles | Longue durée et optimisation du coût de maintenance ouvertes |

## Ajouts au-delà du lot initial d'accès mobile

| Ajout | Motif / autorisation | Livraison / statut |
|---|---|---|
| Exploitation publique read-only permanente par campagnes | GO OR-04/06 explicite, remplace la seule permission de pilote temporaire dans ce périmètre | Services persistants et renouvellements observés ; jamais une permission de trading |
| Corpus opérationnel indépendant | Préserver les expériences scientifiques et le premier pilote | Corpus OR-LIVE neuf, distinct des archives/pilotes |
| Maintenance / budgets / rétention | Empêcher croissance illimitée et permettre usage quotidien | Maintenance source conservée, 3 tests, éviction réelle observée ; mesures longue durée manquantes |
| Preuve SIGKILL sur collecteur réel | Vérifier autonomie vis-à-vis des sessions et reprise | Reprise réelle observée ; ne certifie pas le moteur transactionnel M1 |
| Intégration même origine 443 et même icône | Correction de livraison demandée par l'opérateur : ne pas imposer une deuxième application | Réalisée ; reprend les permissions privées de 443, distinctes de 8443 |
| Proxy scanner + legacy | Raccorder reader neuf à l'app sans supprimer les autres domaines | GET-only ; anciennes routes conservées ; aucun accès frontend direct exchange |
| Chandeliers et volumes SVG | Rendre les OHLCV existants lisibles au quotidien | BTC/ASTER/ENA montrés sur Samsung ; aucune dépendance ni indicateur nouveau |
| Mise à jour PWA/cache/default route | L'ancienne icône ouvrait encore l'accueil historique | Même manifest id/scope ; version cache changée ; défaut radar |
| Réparation des permissions et rollback réel | Défaut de copie dans le script de déploiement | Échec observé, ancien frontend restauré, correction ciblée puis succès |
| Activation du frontend au boot | Ancienne unité active mais disabled | enabled confirmé ; reboot réel non testé |

## Travail conservé, pas recommencé

D1–D3, frontend S1/S2, reader/collector MEXC et dépendances installées réutilisés. Les archives M1 et leurs échecs restent disponibles. M1 RC1 conserve PARTIAL ; pas de faux achèvement B.9→B.13. Aucune réécriture des modules Advisor, PPL/FIN ou de l'ancien CryptoRadar métier ; l'onglet historique demeure accessible.

## Prochaine priorité proposée

1. Lisibilité réelle sur Samsung : identifier viewport/zoom/CSS, puis une correction ciblée ; pas d'indicateur avant stabilisation de cet usage.
2. Réconciliation source/main de la release déployée et checks au vrai HEAD, en traitant les sources originales D1 et leurs contrats ; pas appliquer aveuglément le delta de référence.
3. Continuité/rétention : réduire pause + maintenance + bootstrap ; qualifier fraîcheur des bougies ouvertes et ressources sur durée longue.
4. Reprendre ensuite A2/S3 et les gates A9 selon mandat explicite. Cartographie, Finance/Positions/Décisions, Lab et agents ne sont pas réputés livrés ou réactivés.

Ce suivi ne démarre aucun nouveau chantier technique et ne fusionne aucune PR.
