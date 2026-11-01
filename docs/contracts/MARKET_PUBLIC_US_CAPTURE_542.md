# MARKET-MULTI-VENUE-06 — capture publique isolée depuis la VM US

Mission [#542](https://github.com/3a7i3/crypto-ia-terminal/issues/542).
31 octobre 2026, America/Mexico_City.
Suite du refus d’admission [#541](https://github.com/3a7i3/crypto-ia-terminal/issues/541).
La variante source est ajoutée au pilote de PR540 ; elle ne modifie aucun
fichier frontend, Operator API, service ou artifact actif.
L’autorisation de première collecte ponctuelle est conservée sous ses gates ;
elle n’autorise pas la publication dans l’app ni un collecteur permanent.

## Nouveau roster, aucune substitution implicite

| Source native | Produit | Base / devise | Symbole natif |
| --- | --- | --- | --- |
| Coinbase Advanced public | Spot | BTC / USD | BTC-USD |
| Bitstamp Public API | Spot | BTC / USD | btcusd |
| Coinbase Advanced public | Spot | ETH / USD | ETH-USD |
| Bitstamp Public API | Spot | ETH / USD | ethusd |

USD reste distinct de USDT et USDC. Coinbase Advanced API v3 ne devient pas
Coinbase Exchange API v1 par renommage. Les définitions et hashes de mapping
figurent dans [le plan](../research/market_public_us_542/PLAN.json).
Le plan Bybit/OKX antérieur demeure intact et non admis depuis cette VM.
Aucun fallback, proxy, domaine régional substitué ou déplacement d’hébergement.

## Lectures candidates et admission native

Uniquement GET HTTPS vérifié sur api.coinbase.com et www.bitstamp.net :

- Coinbase : /api/v3/brokerage/market/products/BTC-USD et ETH-USD ;
  /api/v3/brokerage/market/product_book?product_id=…&limit=1.
- Bitstamp : /api/v2/markets/?entity=US_INC ;
  /api/v2/order_book/btcusd/ et ethusd/, avec group=1.

Sept URLs exactes sont fermées dans USSpec. Aucun compte, JWT, clé, cookie ou
environnement proxy. Le filtre Bitstamp US_INC sélectionne le catalogue natif
de cette entité ; il n’attribue aucune résidence ou permission de trading à l’opérateur.
Les deux sources documentent ces lectures publiques. L’accès effectif est
vérifié par les seuls GET du run admis, sans challenge d’une restriction connue.
Tout refus HTTP, redirection, code natif d’erreur, encodage inattendu ou réponse
trop grande arrête le run. Pas de retry ni de plateforme de repli.

Trois lectures de métadonnées précèdent tout carnet. Les quatre bindings
doivent confirmer actif/devise/type Spot et état ouvert. Coinbase exige ses
IDs natifs, status online, les quatre indicateurs de fermeture à false et des
incréments positifs. Bitstamp exige un seul match par symbole, type SPOT,
trading Enabled, base/counter USD et précisions valides. Les échos manquants
dans le carnet Bitstamp sont déclarés comme contexte de requête + métadonnées
préalables, sans inventer une identité renvoyée.

## Première fenêtre réduite

| Borne | Valeur maximale |
| --- | --- |
| Cycles | 3 |
| Intervalle | 5 s entre débuts de cycles ; aucun rattrapage |
| Durée interne | 30 s, métadonnées comprises |
| Lectures | 3 métadonnées + 4 carnets par cycle, au plus 15 GET |
| Timeout par lecture | 3 s, réduit au temps interne restant |
| Corps par réponse | 512 000 octets ; aucun décodage d’un préfixe tronqué |
| Contenu du run | 16 Mio, reçu final réservé |
| Processus extérieur | deadline 35 s, TERM puis KILL après 1 s |
| Limites du child | CPU 10 s, AS 256 Mio, fichier 512 Kio, 64 FD, core 0, NPROC 0 |
| Surveillance extérieure | 80 fichiers, contenu 16 Mio, allocation 32 Mio, deux dossiers |

La réponse Bitstamp peut contenir le carnet complet : aucun paramètre de
profondeur non documenté n’est ajouté. La limite est explicite et provoque un
arrêt si dépassée. Le watchdog de stockage est échantillonné, sans prétendre
être un quota de blocs disque ou une certification face à un noyau bloqué.

## Temps, données observées et inconnus

Les réponses brutes, intentions fsync avant chaque appel, reçus UTC/monotone,
statuts, headers autorisés et hashes restent dans un nouveau run privé.
Les fichiers immuables sont créés en 0400 ; le parent/run doit être 0700,
propriétaire UID1001, sans symlink. Aucun latest.json ni chemin lu par l’app.

Coinbase fournit pricebook.time ; Bitstamp timestamp et microtimestamp,
dont la cohérence secondes/microsecondes est vérifiée. Le texte natif est
conservé en plus de sa conversion UTC. Le temps de réception ne le remplace
jamais. Les prix et quantités restent des chaînes décimales exactes.
Bids/asks invalides, croisés, verrouillés, niveaux non triés ou ambigus sont refusés.

L’âge selon la date native est mesuré au terme du cycle, avec états
WITHIN_BUDGET (≤5 s), STALE, FUTURE ou UNRESOLVED. Le RTT maximal est 1 s ;
un saut UTC/monotone >50 ms arrête la capture et invalide son cycle.
La synchronisation Chrony de l’observateur est un contrôle préalable ponctuel.

La sémantique temporelle reste UNRESOLVED_BOOK_TIMESTAMP_SEMANTICS et la
qualification des horloges des plateformes NOT_PROVEN. Un timestamp présent
et récent ne certifie ni la fraîcheur physique d’un carnet ni des événements
simultanés. OBSERVED signifie décodé, pas admis pour le trading.
Aucun spread, écart économique, profit, score ou verdict scientifique n’est
publié : economic_metrics=null. Un run COMPLETED atteste le parcours prévu,
sans promouvoir ses données en mesures qualifiées.

## Confinement utilisateur, sans action administrateur

Le worker réduit ses propres droits via NoNewPrivileges et Landlock ABI≥4 ;
UID1001 reste inchangé. Aucun sudo, mount, namespace root, capacité ajoutée,
modification du noyau, règle réseau globale ou service.
La règle limite les écritures/créations/retraits/renommages/troncatures au
nouveau parent isolé ; elle refuse le bind TCP et les connect TCP hors 443.
Pas de fallback si le noyau ou l’identité ne sont pas compatibles.

Ce n’est pas une isolation de toutes les opérations possibles : les lectures,
UDP/DNS et certaines métadonnées comme chmod ne sont pas couvertes par cette
règle ABI4. Le worker est du code fixé et revu, sans input exécutable, dans un
environnement minimal sans secrets/proxy, et n’effectue pas ces mutations.
Les stdout/stderr sont capturés par le parent avec une limite de 8 Kio.
Ce dispositif n’est pas une certification contre un autre processus hostile du même UID.

Un caller privé doit épingler source, plan, décision et hashes, revérifier
hostname/id/NTP, refuser un parent non vide et créer un reçu exclusif avant de
démarrer son unique child. Aucun retry automatique. Le superviseur ne s’accorde
aucune autorité par sa seule présence. Aucun mode réseau réel dans la CLI :
elle propose uniquement --plan, --simulate et --verify-run.

## Vérifications et livraison

Tests synthétiques : sockets bloquées, mauvaises devises/type/état, dates
périmées/futures, carnets invalides, refus natifs et HTTP, captures partielles,
budget, intention sans reçu, hashes altérés, fausse complétude et ordre attendu.
Une preuve noyau en child vérifie le refus d’écrire hors parent, du bind TCP et
d’un connect au port9 local. Elle est obligatoire sur la VM cible ; le test
peut être skipped dans une CI d’identité/noyau différents, explicitement.
Le watchdog est testé avec attente et sortie trop volumineuse, sans exchange.

verify_capture contrôle hors réseau plan/roster/ordre, intentions, reçus,
corps et liens des cycles, compteurs et états incomplets. Un hash local ne
certifie ni l’origine d’un serveur ni la validité scientifique des valeurs.
L’app et ses sources actives restent identiques, même après un run réussi.
Une admission/évolution distincte sera nécessaire avant tout affichage de ces
nouvelles sources dans Marché → Comparaison des plateformes.

## Documentation officielle examinée

- [Coinbase public endpoints, cache et absence de JWT](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-api)
- [Coinbase public product](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product)
- [Coinbase public product book](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-book)
- [Bitstamp Public API, markets US_INC, order book et limites](https://www.bitstamp.net/api/)
- [Landlock, contrôle utilisateur ajouté aux restrictions existantes](https://docs.kernel.org/userspace-api/landlock.html)

La capture vise l’étude privée et ne redistribue pas les réponses réelles sur
GitHub. Aucune licence commerciale, souscription ou autorisation de trading
n’est créée par ce protocole.
