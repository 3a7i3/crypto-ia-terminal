# Revue hors réseau du temps, du cache et de l’admission — #543

1er novembre 2026, America/Mexico_City. Revue des preuves de
[#542](https://github.com/3a7i3/crypto-ia-terminal/issues/542), sans nouvelle collecte.
Source capturante : `1e82b9750202e62f687b2e0404e62ea84a1a1b52`, PR540 non fusionnée.
Main et release de l’app : `1da7376829f82eacfb52794ec267be97523fb244`.

**Verdict : preuves locales cohérentes, comparaison et publication NON ADMISES.**
La revue autorise uniquement ses analyses et sa documentation. Elle ne fusionne,
n’installe, ne démarre et ne publie rien. #286 ACTIVE autrement ; #538 et
l’unique tentative #542 restent consommées. Aucun nouveau seuil appliqué.

## 1. Population et conservation

Capture réelle du 31 octobre 2026, 23:23:53–23:24:05 Mexico :
15 GET/HTTP200, 3 métadonnées, 12 carnets, 3 cycles.
Coinbase Advanced et Bitstamp, BTC/USD et ETH/USD Spot, quatre bindings explicites.
Ces noms n’attestent pas la provenance du catalogue CryptoRadar historique.

Ancre privée RESULT.json SHA256 :
`20a5b97800ac44f5e37d3e8a422598a7321b3ddd41e2f5609aa874b2d7faa00a`.
Les **65 fichiers indexés** sont relus et hashés avant/après l’analyse.
Les quatre qualifications de métadonnées et les **12 lignes décodées** sont
reproduites exactement depuis les bytes conservés, aux dates de cycle conservées.
Aucun prix ou quantité n’est recopié dans ce rapport ou dans DECISION.json.

Le résultat LOCAL_COHERENCE_PASS prouve la cohérence de cette chaîne locale.
Les fichiers 0400 restent modifiables par leur propriétaire ; ce mode et un hash
local ne constituent ni WORM, ni signature de l’exchange, ni certification.
Aucune nouvelle durabilité après panne, origine signée ou disponibilité future
n’est déduite de ces preuves. Les bodies restent dans leur dossier privé.

## 2. Signification des champs temporels

| Champ conservé | Ce qui est établi | Ce qui ne l’est pas |
| --- | --- | --- |
| Coinbase pricebook.time | Texte RFC3339, produit natif vérifié, date UTC sérialisable | Temps de mise à jour du BBO, de génération/cache ou du moteur ; portée bid/ask et borne de délai |
| Bitstamp microtimestamp | Entier microsecondes, cohérent avec timestamp en secondes | Événement précis daté, relation au moteur et borne de délai de publication/cache |
| requested/received UTC et monotone | Fenêtres locales avant intention fsync et après réponse complète | Date de création du carnet ou latence aller simple |
| HTTP Date | Champ sélectionné conservé, précision apparente à la seconde | Horloge du moteur, horloge d’origine ou émission forcément comprise dans la requête |
| Âge natif publié | Fin du cycle moins timestamp natif, calcul reproduit | Borne physique de fraîcheur tant que sémantique et horloges ne sont pas qualifiées |

Les 12 âges apparents étaient compris entre **192.984 et 1774.399 ms**, sous
la borne de 5 s du plan #542. Ils décrivent cet instant historique uniquement.
Dix timestamps natifs précèdent le début de leur requête, deux sont dans sa
fenêtre ; aucun n’est après réception. Cela n’est pas une preuve de cache ou
d’erreur en soi : un snapshot peut dater un événement antérieur à la lecture.

Les dates Coinbase observées ont six décimales ; Bitstamp est en microsecondes.
Le décodeur accepte aussi jusqu’à neuf décimales Coinbase mais ses dates dérivées
Python ont une résolution microseconde. Aucun cas à neuf décimales n’est présent
ici ; une admission future doit expliciter résolution/quantification sans
confondre la conservation du texte natif avec la précision du calcul dérivé.

Aucune attestation amont versionnée de la sémantique de ces champs ne figure
dans les 65 pièces indexées. Les liens documentaires du contrat #542 indiquent
des sources examinées auparavant ; ils ne remplacent pas un contenu daté,
conservé et relié à la version du produit. Aucun site documentaire n’a été
réinterrogé dans cette revue hors réseau. Le verdict reste UNRESOLVED.

## 3. Cache : observations dans les reçus

| Réponses | Cache-Control conservé | Age |
| --- | --- | --- |
| Coinbase : 2 métadonnées + 6 carnets | public, max-age=14400 — 8/8 | Non fourni — 8/8 |
| Bitstamp : 3 carnets | max-age=1, public | Non fourni — 3/3 |
| Bitstamp : 1 métadonnée + 3 carnets | Non fourni | Non fourni — 4/4 |

Les huit réponses Coinbase annoncent une durée de cache de quatre heures.
**Cela ne dit pas que les réponses reçues avaient quatre heures.**
Un Age absent reste inconnu, jamais zéro. L’absence de Cache-Control Bitstamp
ne prouve pas l’absence de cache. Un max-age court n’atteste pas l’événement
que date le corps, et une réponse HTTP200 ne prouve pas une revalidation d’origine.

Les timestamps et hashes de corps changent entre les cycles ; trois cycles
ne démontrent pas une politique permanente de cache ou un délai maximal.
La métadonnée Coinbase « online » est cohérente dans les bytes reçus ; sa durée
de cache empêche d’en déduire un état d’ouverture actuel certifié.
La contradiction éventuelle avec une description documentaire antérieure de
cache court reste à instruire séparément, sans nouvelle lecture ici.

Le client #542 n’a pas envoyé de Cache-Control no-cache. Cette revue n’ajoute
ni ce header ni un paramètre d’URL ; un futur essai devra être décidé séparément.
Un tel header ne suffirait pas, à lui seul, à qualifier l’âge du BBO.
Ne pas additionner ou retrancher aveuglément Age, Date, RTT et âge natif :
leurs origines temporelles et un éventuel double comptage restent à définir.
Le Cache-Control no-store de l’Operator API concerne un autre étage du flux ;
il ne corrige pas le cache amont.

## 4. Horloges de l’observateur et des plateformes

NTP=yes, NTPSynchronized=yes et Chrony Normal sont conservés dans l’admission
préalable à 05:23:53.523606 UTC. Référence Chrony : 05:12:44 UTC, soit environ
669.524 s avant ; intervalle d’update indiqué 1039.5 s.
System time : 1.928 µs slow ; root delay : 0.130041 ms ;
root dispersion : 0.800163 ms. Ces valeurs sont des diagnostics ponctuels,
pas une borne physique certifiée ni une preuve continue pendant tout le run.
Aucune nouvelle commande NTP/Chrony ou sonde temporelle n’est lancée ici.

L’écart cumulé maximal UTC/monotone aux points conservés vaut **0.000883 ms**.
Il est bien sous le critère de saut de 50 ms du plan et ne montre pas de saut
à ces points. Un offset UTC constant, un saut entre deux points ou une erreur
commune aux systèmes ne sont pas exclus par ce calcul.

Durées locales des tentatives : **68.500613 à 589.200599 ms**.
L’intention fsync précède le fetch mais suit l’échantillon de départ :
ces durées incluent son coût, DNS/TLS, transport et lecture du corps.
Elles ne sont pas une mesure séparée de la seule latence réseau.
Aucune hypothèse de symétrie ne permet d’utiliser RTT/2 comme correction d’horloge.

Le run #542 contient **zéro sonde d’horloge exchange**.
HTTP Date n’est pas un remplacement : source d’horloge, cache et sémantique
ne sont pas attestés. Chrony local ne qualifie pas l’horloge des plateformes.
exchange_clock_qualification reste NOT_PROVEN.

## 5. Comparabilité entre plateformes

Les différences ci-dessous sont numériques entre champs natifs non qualifiés,
pas des écarts physiques de synchronisation établis.

| Cycle | BTC/USD : différence native absolue (ms) | ETH/USD : différence native absolue (ms) |
| --- | --- | --- |
| 1 | 506.630 | 420.225 |
| 2 | 838.369 | 557.866 |
| 3 | 122.221 | 291.857 |

Les fenêtres locales encadrant les lectures ne se chevauchent pas ; séparation locale
entre réception Coinbase et envoi Bitstamp : 5.993241 à 7.502155 ms.
Cela décrit l’ordre séquentiel des lectures, sans prouver les périodes de validité
des états de carnet. Même deux timestamps numériques proches ne qualifient pas
des événements de sens différent ou des horloges d’offset inconnu.

Le plan US #542 ne définit pas de politique de paire max_skew_ms :
il interdit toutes les métriques économiques. Le plafond de 500 ms du profil
Bybit/OKX #539 ne lui est pas transféré silencieusement. Aucun plafond n’est
élargi pour faire passer ces données. Aucun spread, écart de prix, profit,
classement ou score n’a été calculé par cette revue.

## 6. Contrat et lecteur actif

Le lecteur, son schéma et la table ENDPOINTS ont été comparés aux fichiers de
la release active 1da737 : mêmes bytes pour ces trois fichiers.
Sans toucher l’app, une instance locale du même lecteur lit les fichiers privés.
run-result.json et les trois cycle-*.json donnent tous
**VENUE_COMPARISON_INVALID_SCHEMA**, résultat attendu.

La sortie PublicUSCapture ne contient pas le contrat fermé MarketVenueComparison,
ses groupes/paires/provenances/politiques/expiry. Les IDs coinbase_advanced et
bitstamp ne figurent pas dans ENDPOINTS. coinbase_exchange désigne un autre
produit ; aucun alias ou simple renommage de clé/produit/fichier n’est admis.
Même une compatibilité syntaxique future ne constituerait pas une admission
scientifique ou une permission de publication.

Le prototype du lecteur accepte certains timestamps déjà qualifiés sur déclaration
de leur fournisseur. Il ne valide pas une attestation externe de cache ou
d’horloge : l’admission du producteur doit rester séparée du JSON schema.
Les résultats #542 demeurent des observations privées, non un artifact actif.

## 7. Décision et suite préparée

Voir [DECISION.json](DECISION.json) et la
[proposition d’admission](../../contracts/MARKET_PUBLIC_US_ADMISSION_543.md).
Les barrières non franchies sont : sémantique native, cache, borne continue
d’horloge, comparabilité temporelle, freshness actuelle, format et permission.

Prochaine portée possible : attestation documentaire versionnée des champs et
du cache, modèle d’incertitude temporelle et tests synthétiques d’un éventuel
adaptateur explicite. Cette proposition n’autorise ni documentation réseau
supplémentaire, ni sonde, ni nouvelle capture, ni publication.
Un nouveau plan devra dire ce qu’il cherche à établir, comment il peut échouer,
quelles bornes il respecte et quelle décision l’autorise.

## 8. Reproduction hors réseau

Depuis la racine d’une source contenant les modules identiques à 1e82b975 :

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B \
  docs/research/market_time_review_543/review_saved_capture.py \
  /chemin/prive/market-public-us-542-20261031
```

Le script écrit seulement ses diagnostics JSON sur stdout, jamais un prix ou
une réponse brute. Il ferme les constructeurs de sockets et résolveurs usuels
avant les imports applicatifs ; aucune CLI de capture, transport activé ou
commande de service n’est invoquée. Le champ network_calls_by_review=0 décrit
ce parcours fermé, pas un certificat global d’egress de la VM.
Il vérifie hashes/qualification/rejeu exact/rejet de schéma et relit les hashes
à la fin. Le dossier doit être la copie privée déjà autorisée ; ne pas créer
d’autre capture pour faire fonctionner le rapport.

Validation : relecture réelle hors réseau, checks de refus socket/DNS et
ancre altérée, Ruff/gate et liens documentaires. Aucun test n’est retiré,
aucune baseline n’est changée. Le premier essai a échoué avant lecture des
preuves par une substitution de classe socket incompatible avec l’import SSL ;
la garde a été corrigée en sous-classe refusant la construction, puis le rejeu
complet a réussi. Les deux logs privés sont préservés.
