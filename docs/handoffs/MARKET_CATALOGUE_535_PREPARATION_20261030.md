# MARKET-CATALOGUE-02 — préparation du 30 octobre 2026 (Mexico)

Mission #535, prolongement de #533 / PR #534.
Statut : **PRÉPARÉ OFFLINE / NON_FUSIONNÉ / NON_INSTALLÉ SUR LES UNITÉS / NON_DÉMARRÉ**.
Aucune admission scientifique, aucune nouvelle collecte.

## Résultat sur les données réelles

Deux fichiers journaliers explicitement autorisés ont été lus en mode read-only,
après vérification contre le manifeste reçu et avec leurs empreintes recontrôlées.
Ils contiennent 8 825 objets, sans ligne JSON invalide ni packet_id dupliqué.

La reconstruction v1.0 reproduit sémantiquement tous les champs du fichier
historique de 4 722 octets. La nouvelle v1.1 borne exactement les 24 heures
terminant à `2026-10-29T05:32:36Z` :
7 154 observations incluses, 1 671 antérieures exclues, aucune future/non datée.
124 symboles observés, 90 avec paquets au seuil, 20 affichés par page.

BTC/USDT et ETH/USDT sont présents et retrouvés dans l’aperçu réel isolé.
Leurs variantes USDC restent séparées ; une recherche « ETH » peut aussi
retourner ETHFI, conformément à son filtrage textuel.

Le candidat JSON de 53 861 octets a pour SHA256
`aed28d3835188b4722ac0abb697ad62d2ba75519f043f5553518953398117501`.
Il reste dans staging #535, jamais dans le répertoire actif.
Les dates de l’archive ne sont pas remplacées par celles de la préparation.

## Provenance : fait attesté et inférence séparés

L’audit des structures des 8 825 paquets n’a trouvé aucun champ exchange/venue
ou SHA producteur/epoch. Le champ `source_agents` n’est pas une venue.
Les signatures présentes n’ont pas été vérifiées.

Le code courant `MarketScanner` et `ExchangeFactory` prévoit MEXC par défaut.
Ce constat source ne prouve pas la configuration du producteur passé.
**Exchange réel, produit et SHA producteur : UNRESOLVED / NOT_AVAILABLE.**
L’app affiche cette limite dans ses provenances.

Le catalogue n’est pas un roster indépendant et ne certifie pas l’epoch.
Il ne contient pas de bid/ask permettant de reconstruire un spread.

## Lecteur compatible et validation

Le lecteur v1.1 préparé accepte le candidat réel en ASGI in-process :
HTTP200, STALE, dates/124/90/7154/1671 conservés, méthodes mutantes refusées.
Le lecteur installé dans `82cd63e...` refuse ce format, ce qui confirme
la nécessité d’une mise à jour API distincte avant une admission.

Les imports et requêtes du test sont sous un garde-fou :
aucun bind/connect/DNS/subprocess, .env, lecture des archives ou données actives,
ni écriture hors du reçu d’audit. Zéro violation observée.
Aucune requête du test n’atteint l’API active.

| Contrôle de cette tranche | Résultat |
| --- | --- |
| Python, tests concernés + totalité cross-stack | 208 PASS |
| Frontend complet avec fixtures générées | 509 PASS, aucun skip |
| Serveur/PWA | 17 PASS |
| TypeScript / build production | PASS |
| Ruff des fichiers Python concernés | PASS |
| Browser synthétique, 2 thèmes, 3 largeurs | 375 assertions / 50 captures PASS |
| Aperçu historique réel intercepté, 2 thèmes, 2 largeurs | 118 assertions / 16 captures PASS |
| API active atteinte / serveur lancé par ces aperçus | 0 / 0 |

Les captures montrent la projection réelle dans une preview de sources isolées.
Elles ne sont pas une preuve de publication privée, d’actualité du marché
ou d’efficacité économique. Les avertissements pytest/Vite/Starlette de la
pile isolée sont conservés dans les logs, sans suppression de dépendance.

## Préparation multi-plateformes

Le [contrat](../contracts/MARKET_MULTI_VENUE_01.md) et son registre décrivent
25 candidats, dont huit sources documentées pour un premier pilote.
Aucun classement mondial de volume n’est revendiqué, aucun adaptateur réseau
n’est déclaré implémenté ou activé.

Le module offline sépare spread interne, écart des milieux et écarts BBO bruts.
Il conserve les Decimal, les identités d’actifs/contrats et la qualité temporelle.
Il refuse les cotations sans timestamp, périmées, désynchronisées ou incompatibles.
Les valeurs absentes restent null/NOT_AVAILABLE ; aucun score CryptoRadar
ou classement n’est modifié et aucune autorité d’exécution n’est créée.

OpenSea est étudié séparément : son offre documentée comprend aussi les tokens
et devis de swaps, mais ceux-ci ne sont pas assimilés aux carnets des CEX.

## Paquet et prochaine action

Le [runbook](../runbooks/MARKET_CATALOGUE_535_PREPARATION.md) précise les chemins
actifs connus, le candidat, le lecteur, la bascule future API → web → fichier
et le rollback inverse, avec restauration v1.0 avant retour à l’ancienne API.
Les drop-ins et unités combinées restent dans le staging de préparation.

Manifeste concret :
`~/crypto-install/staging/market-catalogue-535-20261030/RUNTIME_PREPARATION_MANIFEST.json`.
Il lie l’arbre exact à sa copie de validation, au venv verrouillé, au build,
aux fichiers candidats et aux preuves. La CI du nouveau HEAD de #534 doit
être vérifiée séparément de celle de son ancien HEAD.

Les preuves de cette tranche sont dans les dossiers staging et audit-browser
`market-catalogue-535-20261030`. Les datasets réels complets et captures privées
ne sont pas ajoutés au dépôt public. Seuls code, documentation, counts et hashes
utiles à la revue sont publiés.

La capture active reste
`46c2f0d3704f3dbf6dcc4df541870a7cb72fadd2ca812736c87d3243d40eaa4e`,
API79546/web143612 à la dernière vérification. Aucun start/stop/restart/reload/
enable, secret, port public, collecte, Telegram, notification, paramètre
scientifique, PPL/FIN ou original récupéré n’a été changé.
L’exception #532 est consommée et n’est pas réutilisée.
