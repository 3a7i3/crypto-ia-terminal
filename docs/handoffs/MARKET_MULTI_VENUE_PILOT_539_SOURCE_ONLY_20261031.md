# Passation #539 — préparation source du pilote de cotations

31 octobre 2026, America/Mexico_City.
Mission [#539](https://github.com/3a7i3/crypto-ia-terminal/issues/539).
Base main : `1da7376829f82eacfb52794ec267be97523fb244`.
Branche : `feat/market-venues-pilot-20261031`.
Le HEAD exact et la CI de livraison sont consignés dans la PR associée à #539.

## Résultat et autorité

**Préparé et testé sur réponses synthétiques. Non fusionné par cette mission,
non installé en production, aucune collecte réelle démarrée.**

L’opérateur demande un pilote en lecture seule, bid/ask datés, plateforme et
instrument identifiés, avec contrôles de fraîcheur. Son activation doit faire
l’objet d’une décision distincte. #286 reste ACTIVE ; l’exception #538 est consommée.

Le [contrat](../contracts/MARKET_MULTI_VENUE_PILOT_539.md) et le
[dossier de préparation](../research/market_multi_venue_pilot_539/README.md)
définissent quatre bindings : BTC/USDT et ETH/USDT Spot sur Bybit/OKX.
Le transport HTTPS est désactivé par défaut et la CLI permet uniquement plan,
simulation et vérification hors réseau. Aucune unité ni configuration active
n’importe le pilote. Les mappings restent proposés, non admis par leur hash.

Le plan propose 120 cycles sur 600 secondes, cadence 5 secondes, au plus
724 GET et 16 Mio de contenu écrit. Les réponses natives, intentions et reçus
sont persistés avant toute publication dans le seul dossier exclusif du run.
Les refus d’accès, limites, mauvaises identités, dates périmées et défauts
d’horloge gardent leurs diagnostics ; ils n’engendrent ni zéro ni prix de repli.

Deux corrections de présentation accompagnent le pilote : suppression des
métriques de paire lorsqu’une source décodée reste non qualifiée ; expiration
de l’affichage entre les GET API, sans recalcul de prix. Le retour d’une horloge
navigateur après un saut ne rajeunit pas une publication déjà expirée.

## Vérifications sur le tree de livraison

| Contrôle | Résultat |
| --- | --- |
| Python : cross-stack, market_venues, comparateur | 278 PASS ; 0 échec, 0 skip |
| Dont tests spécifiques du pilote | 64 PASS, réseau bloqué par les tests |
| Vitest complet avec fixtures Python générées | 543 PASS / 41 fichiers ; 0 skip |
| Runtime frontend / contrat PWA | 17 PASS |
| TypeScript et build Vite | PASS |
| Ruff des nouveaux modules et tests | PASS |
| Gate Ruff du dépôt | 0 nouvelle violation ; baseline inchangée |
| Navigateur Chromium sandbox activé | 446 assertions / 42 vues PASS |
| Simulation CLI et vérification de ses liens | 2 cycles, 16 intentions/reçus, 2 snapshots, 0 capture en attente |

La preuve navigateur couvre 1440/768/393 px, clair/sombre, pilote synthétique,
comparaison synthétique initiale, expiration avant le deuxième GET API,
publication périmée, temps non résolu, 503 et contrat invalide.
Elle intercepte les GET et assets du build ; aucun serveur HTTP ni endpoint
exchange ou API actif n’est utilisé. Les fixtures restent SYNTHETIC, sans
certification d’origine, de performance ou scientifique.
La simulation du budget complet vérifie aussi 120 cycles / 724 tentatives
sans attente réelle ni réseau.

Deux avertissements Python locaux restent visibles : option asyncio_mode
sans son plugin dans le venv réutilisé, et dépréciation Starlette/httpx.
Vite signale son changement futur de chargement de configuration.
La revue finale ajoute aussi le rétablissement du handler de timeout si
l’installation du timer échoue, avec un test d’injection dédié.
Un premier passage a révélé quatre erreurs dans le double de réponse HTTP
(statut manquant) ; le double a été corrigé sans retirer de test.
Une commande initiale PWA visait un fichier absent ; le script suivi du dépôt
`npm run test:runtime` a ensuite passé ses 17 tests.

## VM réellement observée, sans modification des services

Connexion par Remote Desktop Commander, appareil
`bc07f523-ad34-4c2e-9af1-0105f66d5783` :
`hostname=crypto-restore-01`, `lecanada26`, UID 1001.
ACCESS_HANDOFF.md a été lu avant les opérations.

Dernier guard existant relancé uniquement en mode lecture seule :
**31 octobre 2026, 21:30:28 America/Mexico_City**.
`VENUES_INSTALL_READ_ONLY_PASS`, API PID **257740**, web PID **257806**.
Dix assets installés cohérents avec le plan #538 ; payload Marché inchangé :
`aed28d3835188b4722ac0abb697ad62d2ba75519f043f5553518953398117501`.
La comparaison reste 503 `VENUE_COMPARISON_NOT_CONFIGURED` par API, web et HTTPS
privé. Aucun start/stop/restart/reload/enable/reboot, secret ou donnée récupérée
raccordée. Aucune intervention sur Advisor, Telegram, PPL/FIN ou l’ancienne VM.

Worktree isolé :
`/home/lecanada26/crypto-install/worktrees/market-venues-pilot-539-20261031`.
Logs et simulations privés :
`/home/lecanada26/crypto-install/audit-browser/market-venues-pilot-539-20261031`.
Les captures CI sont générées dans `frontend/artifacts/market-venues/` et
conservées par le workflow cross-stack pendant 14 jours.

## Prochaine décision

Relire le diff au HEAD exact, la CI, les reviews et les gates avant toute fusion.
Pour un premier run réel : mappings admis, conditions/région/rate limits revus,
horloge observatrice qualifiée, processus séparé borné et emplacement isolé,
puis autorisation explicite. Le timeout Python seul ne borne pas tous les
blocages système. L’accès réel aux plateformes reste NON VÉRIFIÉ.

L’admission et la publication d’un artifact réel dans
**Marché → Comparaison des plateformes** auront ensuite leur propre procédure,
avec état antérieur/config/hash et rollback borné. Ni la source, ni les fixtures,
ni une future fusion ne donnent cette permission.
