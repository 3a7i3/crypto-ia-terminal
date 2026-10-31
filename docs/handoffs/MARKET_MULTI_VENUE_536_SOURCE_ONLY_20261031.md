# Passation #536 — comparaison des plateformes, source seule

Date : 31 octobre 2026, America/Mexico_City. Mission [#536](https://github.com/3a7i3/crypto-ia-terminal/issues/536).
Base exacte : `e517438221deefb4f43705ef7bd0215f722af8e5`, tree `28bbc32974d2d36fdcfe1e6ea2e990c04713dbf3`.
Branche : `feat/market-venues-offline-20261031`.
Statut : **PR à examiner ; SOURCE_ONLY / OFFLINE / NON_DEPLOYED**.

## Résultat préparé

- Un second onglet **Marché → Comparaison des plateformes** ; le scanner reste initial et son contrat conserve sa propre source.
- Sélection d’instrument et de référence, tableau bid/ask/spread/écart, détails de source. Provenances, dates absentes, limites et états périmés visibles ; clavier/focus et thèmes clair/sombre vérifiés.
- Huit décodeurs purs de snapshots déjà fournis : MEXC, Bybit, OKX, Kraken, Bitfinex, KuCoin, Coinbase Exchange, Hyperliquid. Aucun adaptateur réseau ou collecteur ajouté.
- Publication fermée depuis un roster explicite, Decimal, instruments séparés et expiration par date de carnet. Les bindings et empreintes fournis ne certifient pas l’origine des réponses.
- GET `/api/operator/v1/venue-comparison`, non configuré par défaut. Aucun nouveau fichier dans la présentation active.
- Registre documentaire de 25 candidats : huit décodeurs source préparés, tous les adaptateurs réseau NOT_IMPLEMENTED et toutes les collectes désactivées.

Le [contrat détaillé](../contracts/MARKET_MULTI_VENUE_02.md) expose les champs, formats officiels et limites. Le [mode d’emploi](../research/market_multi_venue_02/README.md) indique où classer les fichiers et reproduire l’exemple offline.

## Contrôles locaux

Exécutés sur `crypto-restore-01`, compte `lecanada26` UID 1001, dans un nouveau worktree isolé ; aucun fichier servi n’est modifié.

| Contrôle | Résultat |
| --- | --- |
| Python : cross-stack, nouveaux décodeurs/publication, catalogue/préparation, comparateur existant | 254 tests réussis (sélection dédupliquée) |
| Vitest complet, fixtures cross-stack générées | 530 tests réussis, aucun skip |
| Vitest de la nouvelle vue après correction des libellés accessibles | 21 tests réussis |
| Tests de cache/PWA/runtime frontend | 17 tests réussis |
| Build TypeScript/Vite de production | réussi |
| Ruff, fichiers Python ajoutés | réussi ; baseline inchangée, aucune nouvelle violation |
| Nouvelle vue en navigateur sandboxé | 308 assertions, 30 captures, 5 états × 2 thèmes × 3 largeurs |
| Scanner catalogue existant en navigateur sandboxé | 375 assertions, 50 captures, réussi |

La preuve navigateur utilise le build et des fixtures **entièrement synthétiques** : aucune API active ni exchange atteint, aucun serveur HTTP démarré. Elle n’atteste pas de prix de marché ou de qualité réseau. Les artefacts CI sont conservés 14 jours ; les contrôles GitHub au HEAD exact de la PR restent à vérifier séparément.
Les avertissements préexistants pytest asyncio, Starlette/httpx et chargement de configuration Vite sont conservés, sans suppression. Des essais initiaux ont révélé puis corrigé un identifiant de fixture invalide, le refus d’un chemin répertoire et le libellé des sélecteurs. Une commande de sélection de tests a aussi refusé un fichier de cache Python ; la sélection a été limitée aux fichiers `.py`, sans retirer de test. La revue finale a aussi reproduit puis corrigé un arrondi de taille Bitfinex au-delà de 28 chiffres, avec un test gardant les décimales natives. Les logs d’essai restent dans le dossier d’audit isolé.

## Production observée, inchangée par cette tranche

Contrôle ponctuel du 31 octobre 2026 à **14:21:58 America/Mexico_City** (20:21:58 UTC), vérificateur #535 revérifié par son SHA avant lecture : CATALOGUE_READ_ONLY_PASS.
API PID `192881`, web PID `192947` ; capture active SHA-256 `aed28d3835188b4722ac0abb697ad62d2ba75519f043f5553518953398117501`, 10 assets servis ; hardening et mounts vérifiés par le contrôle existant.
Les champs new_api/new_web du vérificateur sont relatifs à la publication #535 déjà terminée, pas à une action de cette tranche.
Le nouvel onglet est **préparé et testé en isolation**, pas installé, démarré ou vérifié sur le service actif.

## Reprise

1. Examiner le diff exact et les contrôles au HEAD de la PR ; ne pas déduire une permission de fusion de l’ancienne publication #535.
2. Pour une future collecte : admettre séparément les bindings, sources, cadences/coûts, horloges et transport ; préparer une preuve de custody et une recette isolée. Les cotations anciennes CryptoRadar ne fournissent pas de bid/ask ou de provenance native attestée.
3. Préparer ensuite un paquet et rollback précis, puis obtenir une décision de publication applicable. La mise en production du code et l’activation de collecte sont deux décisions distinctes.

Le garde-fou #286 reste actif. Aucun restart, reload, enable, reboot, trading, secret, Telegram, moteur, modification de stratégie/seuil/calibration, mutation PPL/FIN/epoch ou raccordement d’archives n’a lieu ici. Aucun accès à l’ancienne VM crypto-advisor-2.
