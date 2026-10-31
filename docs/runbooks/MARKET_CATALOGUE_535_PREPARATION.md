# MARKET-CATALOGUE-02 — préparation et admission future

Mission #535. Préparation uniquement. Cette procédure n’accorde aucun restart,
raccordement, secret, collecteur ou merge automatique.
Le paquet concret et ses hashes sont consignés dans
`~/crypto-install/staging/market-catalogue-535-20261030/RUNTIME_PREPARATION_MANIFEST.json`.

## 1. Candidat historique

Ancre : `2026-10-29T05:32:36Z` (28 octobre, 23 h 32 min 36 s à Mexico).
Fenêtre exacte : du 28 octobre 05:32:36Z au 29 octobre 05:32:36Z.
Entrées autorisées et re-hachées contre le manifeste reçu :

| Fichier | Octets | SHA256 |
| --- | ---: | --- |
| `decision_packets_2026-10-28.jsonl` | 32488057 | `2555e5acfe54d17459c86cc9426e5b08c854e5e977df9d1948e57b7097785d60` |
| `decision_packets_2026-10-29.jsonl` | 7203623 | `c3270a623000b463c57ba0af4107bd2359439c5a06c40044dbfd2243820d61cc` |

Manifeste reçu : `17f69cd5d2b44f64495e207ed806b98ec8880bffb6a9e1d09391ab891d299f39`.

Les 8 825 objets sont décodés sans ligne invalide ni packet_id dupliqué.
La projection v1.1 retient 7 154 observations, exclut 1 671 observations
antérieures et ne trouve aucune date future ou non résolue.
124 symboles observés, 90 avec au moins un paquet au seuil, 20 en aperçu.
BTC/USDT et ETH/USDT sont présents ; BTC/USDC et ETH/USDC restent distincts.

Candidat : 53 861 octets, SHA256
`aed28d3835188b4722ac0abb697ad62d2ba75519f043f5553518953398117501`.
La reconstruction v1.0 sur les 8 825 paquets reproduit sémantiquement tous les
champs de la capture d’origine. Cela ne prouve pas le SHA du producteur historique.
La différence de 94 → 90 symboles au seuil résulte du bornage temporel v1.1 ;
l’ancienne capture et ses résultats ne sont pas réécrits.

## 2. Reproduction de la préparation isolée

Depuis le checkout source exact de la PR, avec Python 3.11 et les dépendances
de validation isolées, utiliser `python -m tools.prepare_market_catalogue` :

- `--source-root ~/crypto-migration/verified-20261029T053303Z` ;
- `--manifest ~/crypto-migration/received-20261029T053303Z/manifest.json` ;
- `--manifest-sha256` avec l’empreinte ci-dessus ;
- les deux `--input databases/decision_packets_YYYY-MM-DD.jsonl` explicitement ;
- `--as-of 2026-10-29T05:32:36Z --window-hours 24` ;
- `--reference-snapshot databases/cryptoradar_market_snapshot.json` ;
- `--output-dir` vers un NOUVEAU dossier privé dans le staging #535.

Ne pas employer une date de génération actuelle pour rajeunir cette archive.
L’outil n’appelle pas le chargeur runtime lorsqu’il reçoit les paquets explicites.
Il refuse un hash incorrect, une ligne malformée, une entrée hors périmètre,
un symlink et une destination existante/dans presentation ou dans les originaux.
Il ne copie que la projection des cinq champs d’entrée nécessaires au calcul.
Les champs de risque, exécution et secrets ne traversent pas la projection.

## 3. Provenance et lecteur

Les 8 825 paquets n’embarquent pas d’identifiant de venue reconnu. Aucun champ
de provenance producteur/epoch/exchange n’a été observé dans leurs structures
de métadonnées ; `source_agents` décrit des agents, pas une plateforme.
Le code courant de MarketScanner prend MEXC par défaut, mais cela n’atteste
ni la configuration passée ni la provenance de chaque observation.

La venue, le type de marché et le SHA producteur restent UNRESOLVED/NOT_AVAILABLE.
Les signatures présentes n’ont pas été vérifiées. Le candidat ne certifie pas
un roster indépendant, l’epoch, une activité de producteur ou des prix actuels.

Le lecteur préparé sous #534 accepte la v1.1 en ASGI isolé ; le lecteur installé
dans la release `82cd63e...` la refuse. Le test du candidat réel vérifie HTTP200,
STALE, les comptes exacts, les dates et le refus des méthodes mutantes.
Le garde-fou du test interdit réseau/bind, lecture des archives après leur
projection, .env, données actives et écritures hors de son reçu explicite.

## 4. Préparation technique du paquet

La copie de validation du code exact, son environnement API verrouillé,
le build web, les deux drop-ins candidats et les unités combinées sont préparés
sous staging #535, avec leurs hashes dans le manifeste de préparation.
Aucun fichier /etc ni service actif n’est modifié par cette préparation.
La vérification systemd des fichiers candidats n’est pas un daemon-reload.

Le contrôle d’import/ASGI utilise les 13 dépendances runtime du lock API.
La configuration conserve les chemins d’artifacts et les restrictions existantes,
avec seulement les chemins de code/venv/build candidats adaptés.
Les deux futurs drop-ins portent un nom `zz-market-catalogue-535.conf` :
ils sont triés après les anciens 90/95/99. Ne pas utiliser « 100 » en supposant
un ordre numérique ; systemd applique l’ordre lexical.

Le lecteur ne nécessite aucun collecteur pour servir une archive. L’API demeure
GET-only, l’accès réseau de ses unités demeure bouclé sur localhost.
Les autres publications restent indisponibles et ne sont pas raccordées.

## 5. Séquence future, uniquement après décision du paquet exact

1. Reprendre hostname/id, HEAD/arbre, CI/reviews et manifeste/hashes exacts.
   Vérifier unités/drop-ins actuels, ancien payload, custody, mêmes processus
   et protections. Refuser tout état inattendu ; ne pas rejouer #532.
2. Consigner une nouvelle décision bornée : ce paquet, API ET web, un remplacement
   MARKET, une tentative et au plus un rollback de cette tentative. L’ancienne
   autorisation de redémarrer le web seul ne couvre pas cette opération.
3. Installer exclusivement les deux nouveaux drop-ins revus, sans écraser un
   fichier existant ; daemon-reload seulement dans cette décision administrateur.
4. Redémarrer l’API compatible d’abord, en conservant la capture v1.0.
   Vérifier transport, ancienne lecture, UID/caps/mounts/BPF/ports/argv/source.
5. Basculer le web sur son build revu et vérifier la compatibilité v1.0.
6. Préparer une copie privée hashée de la v1.1, puis remplacer atomiquement
   l’unique chemin MARKET après les contrôles frais. Conserver toutes les copies
   de custody et la capture d’origine. Ne pas déplacer le seul candidat.
7. Vérifier API/proxy/HTTPS privé et véritable navigateur : dates/STALE, 124/90,
   recherche BTC et ETH, populations et valeurs, pagination, carte, thèmes,
   erreurs et provenance non attestée. Vérifier les unités/protections finales.
8. Consigner processus, code, hashes et résultat réels. Boot toujours désactivé.
   Aucune réussite de cette présentation ne certifie U8/L4 ou l’epoch.

## 6. Rollback de cette seule tentative

Si la bascule échoue, contrôler owner/type/hash et liens de custody de la
destination avant toute restauration. Refuser une destination inattendue.

Restaurer atomiquement le payload v1.0 connu **avant** de revenir à l’ancienne
API, car celle-ci refuse la v1.1. Revenir ensuite au web précédent, puis à l’API
précédente en retirant uniquement les deux nouveaux drop-ins exacts créés dans
cette tentative, puis les reload/restarts bornés nécessaires. Préserver les
anciens drop-ins, code, preuves, marker #532, sauvegardes et bases.

Un rollback après restart ne peut pas retrouver les anciens PID. Il doit
vérifier les anciennes versions/paths/payload et les nouvelles identités de
processus dans un reçu distinct ; ne pas retoucher le baseline #532 pour le
faire passer. Aucun retry automatique, enable, reboot ou arrêt d’autre service.

## 7. Étape multi-venue séparée

Voir [MARKET-MULTI-VENUE-01](../contracts/MARKET_MULTI_VENUE_01.md).
Le registre de 25 candidats et le calcul offline ne collectent aucune cotation.
Spreads, écarts et précision temporelle restent indisponibles pour cette archive.
