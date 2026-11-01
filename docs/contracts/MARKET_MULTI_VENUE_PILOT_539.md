# MARKET-MULTI-VENUE-04 — pilote passif préparé sous #539

Mission : [#539](https://github.com/3a7i3/crypto-ia-terminal/issues/539).
Base : main `1da7376829f82eacfb52794ec267be97523fb244`.
Préparation du 31 octobre 2026, America/Mexico_City.
**SOURCE_ONLY / SYNTHETIC_TESTED / NON_DEPLOYED / ACTIVATION_NOT_AUTHORISED**.

La demande autorise la préparation et les tests synthétiques. La fusion,
l’installation, une première lecture réseau et l’admission d’un artifact dans
l’app restent des décisions distinctes. #286 demeure ACTIVE.
Le registre de 25 candidats ne devient ni un classement mondial, ni 25 collecteurs.

## Périmètre et identité proposés

| Plateforme | Produit | Actif / devise | Instrument natif |
| --- | --- | --- | --- |
| Bybit | Spot | BTC / USDT | BTCUSDT |
| OKX | Spot | BTC / USDT | BTC-USDT |
| Bybit | Spot | ETH / USDT | ETHUSDT |
| OKX | Spot | ETH / USDT | ETH-USDT |

Le roster indépendant figure dans [PILOT_PLAN.json](../research/market_multi_venue_pilot_539/PILOT_PLAN.json).
Les quatre définitions et leurs SHA-256 sont déterministes.
Leur présence ne vaut pas admission opérateur du mapping.
BTC/USD, USDC, tokens enveloppés, contrats perpétuels et NFT restent distincts.

Avant les carnets, quatre réponses de métadonnées doivent confirmer le symbole,
l’actif, USDT, Spot, un état ouvert et des précisions positives. Tout écart arrête
ce run sans reconstituer le roster depuis les réponses reçues.
Bybit vérifie aussi catégorie et écho du symbole dans le carnet ; OKX conserve
l’identité du contexte de requête, sans inventer un écho absent de sa réponse.

## Transport préparé

`observability/market_venues/pilot/` ne réalise aucune opération à l’import.
`PublicHTTPS()` refuse le réseau par défaut. Le seul transport préparé utilise
TLS vérifié, HTTPS 443 et GET sur deux hôtes fixés :
`api.bybit.com` et `www.okx.com`.
Les dix requêtes possibles, paramètres et symboles sont fermés dans le plan.

| Plateforme | Métadonnées | Horloge | Carnet, un niveau |
| --- | --- | --- | --- |
| Bybit | /v5/market/instruments-info | /v5/market/time | /v5/market/orderbook |
| OKX | /api/v5/public/instruments | /api/v5/public/time | /api/v5/market/books |

Aucune redirection suivie, clé, cookie, authentification, SDK, abonnement,
endpoint d’ordre ou proxy d’environnement. Une référence de décision GitHub est
obligatoire pour construire un transport explicitement activé ; cette chaîne
est une déclaration du caller, **pas une autorisation vérifiée ou auto-accordée**.
La CLI livrée ne propose aucun mode réseau réel.

## Budget proposé, encore non activé

| Limite | Valeur maximale proposée |
| --- | --- |
| Durée monotone du run | 600 secondes |
| Cycles | 120, sans rattrapage des cycles en retard |
| Intervalle entre débuts de cycles | 5 secondes ; peut être allongé |
| Requêtes | 4 métadonnées + 6 par cycle, soit au plus 724 |
| Par cycle | 2 sondes d’horloge, puis 4 carnets, séquentiellement |
| Deadline par requête | 3 secondes, réduite au temps restant du run |
| Corps conservé par réponse | 65 536 octets |
| Contenu écrit par run | 16 Mio, dont 4 Kio réservés au reçu final |

Le run s’arrête plutôt que de masquer une limite. Aucun retry immédiat,
host alternatif ou contournement géographique. HTTP 401/403/429 et redirection
arrêtent le run ; corps trop grand et encodage compressé refusé également.
Une panne ordinaire garde sa ligne indisponible dans le cycle. Le cycle suivant,
s’il reste admis, constitue une nouvelle tentative avec son propre reçu.

Le timer Python et les timeouts socket ne prouvent pas une borne physique
face à un appel système bloqué. Une future activation exige un processus
séparé avec limite extérieure de temps, ressources et stockage ; aucun
ordonnanceur, service, timer ou caller réseau réel n’est installé ici.
Le budget de contenu n’est pas un quota des blocs disque/inodes ni un budget
de bande passante global de la machine.

## Temps et qualification

Chaque tentative conserve UTC en nanosecondes et temps monotone avant/après,
une identité d’horloge observatrice par run, ainsi que le timestamp natif.
Le temps de réception ne remplace jamais le temps du carnet.
Bybit utilise `ts`, pas `cts` ; OKX utilise le `ts` du carnet.
Ces dates de publication ne sont pas des preuves de simultanéité des moteurs.

Les plafonds du pilote sont : âge du carnet 5 s, écart entre carnets 500 ms,
RTT 1 s, divergence UTC/monotone 50 ms, intervalle d’offset serveur entièrement
contenu dans ±250 ms. Les deux sondes expirent après 5 s.
L’intervalle d’offset suppose un timestamp serveur situé pendant la requête.
Il ne certifie ni NTP, ni l’horloge du moteur de carnet. Aucune date n’est corrigée
à partir de cet offset. Un saut d’horloge arrête le run.

Prix périmés, date future, carnet invalide, mauvaise identité ou horloge non
qualifiée restent explicitement indisponibles pour les métriques.
Les bid/ask natifs et leur provenance peuvent rester consultables lorsqu’ils
existent ; aucun résultat de paire n’est calculé depuis une source non qualifiée.
Ni spread interne ni écart brut ne représente un profit net ou un prix exécutable.
Les frais, slippage, profondeur complète, financement et FX restent hors mesure.
Ces paramètres de qualité n’affectent aucune stratégie ou calibration.

## Conservation avant publication

Le caller doit fournir un parent isolé, existant, propriétaire courant, mode
0700, nommé `market-venue-pilot-runs`, sans symlink dans la chaîne des chemins.
Les chemins actifs `presentation`, `releases` et `crypto-migration` sont refusés.
Chaque run crée un sous-dossier exclusif 0700 ; aucune reprise ni écrasement
d’un ancien run. Aucun backup ou fichier d’origine n’est modifié.

L’intention est écrite/fsync avant la requête. La réponse capturée, son SHA-256,
le statut HTTP, les en-têtes autorisés et le reçu lié à l’intention sont ensuite
écrits/fsync avant la publication. Les corps incomplets ne sont pas décodés.
Les fichiers de preuve sont créés exclusivement en 0400.
La qualification de métadonnées, les diagnostics temporels par cycle et le
reçu final sont conservés. Le reçu final distingue COMPLETED, STOPPED et INCOMPLETE.

Les snapshots de publication sont immuables ; seul `latest.json`, dans ce run
exclusif, avance atomiquement après validation du contrat existant.
Une substitution de pointeur détectée est refusée. Ce mécanisme suppose un seul
writer coopératif ; il ne protège pas contre un autre processus hostile du même UID.
Une panne disque ou un kill peut laisser un run sans reçu terminal : aucune
complétude n’est alors affirmée. Un budget épuisé peut laisser une intention
sans capture ; le vérificateur expose ces ordinaux manquants.

`--verify-run` vérifie hors réseau les liens intention/reçu/corps/publication,
les empreintes, les compteurs et la cohérence du dernier snapshot.
Il ne constitue ni signature d’origine, ni nouvelle qualification scientifique,
ni preuve de durabilité après panne électrique.

## Présentation et prochaine admission

Le contrat MarketVenueComparison et le lecteur GET-only existants sont réutilisés.
La publication distingue SYNTHETIC et OBSERVATION. L’API ne lance jamais le pilote.
React conserve les prix/métriques exacts publiés et fait seulement avancer
l’âge et l’expiration entre les lectures API, actuellement espacées de 20 s.
Une réponse tardive, un retour d’onglet ou une panne ne rajeunit pas un ancien prix.

Après admission distincte, l’artifact pourra alimenter **Marché → Comparaison des
plateformes**, avec choix BTC/USDT ou ETH/USDT, référence et détail source.
Pour cette préparation, le lecteur actif reste non configuré et renvoie 503
VENUE_COMPARISON_NOT_CONFIGURED. Aucune cotation synthétique n’y est raccordée.

Avant une éventuelle activation : revoir le HEAD exact et ses checks, admettre
les quatre mappings, vérifier l’horloge/NTP de l’observateur, accès/région/conditions
et limites partagées par IP, puis arrêter les bornes et le processus isolé.
L’éligibilité native et la disponibilité réelle ne sont pas attestées par les tests.
Ne pas desserrer le réseau des unités API/web pour y intégrer un collecteur.
Une lecture pilote réelle n’autorise pas sa publication dans l’app : custody,
roster, temps, erreurs et limites du run doivent être revus avant ce raccordement.
Son plan distinct devra conserver l’ancien chemin/config/hash et prévoir le
retour à l’état non configuré, sans modifier les originaux ni l’epoch.

## Sources officielles consultées

Schémas documentaires consultés le 31 octobre 2026, America/Mexico_City ;
aucun endpoint de données de marché appelé pour cette préparation.

- Bybit : [instruments](https://bybit-exchange.github.io/docs/v5/market/instrument),
  [heure](https://bybit-exchange.github.io/docs/v5/market/time),
  [carnet](https://bybit-exchange.github.io/docs/v5/market/orderbook).
- OKX : [instruments publics](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments),
  [heure](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-system-time),
  [carnet](https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-order-book).
