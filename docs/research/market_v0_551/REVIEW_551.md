# Revue indépendante et prototype hors réseau — #551

2 novembre 2026. Base `1a1e61ca375b1f54a9a9b424d9ff5cc0ef95c3f7` (revérifiée : `main` = HEAD du checkout).
**DESIGN_ONLY / OFFLINE / NON_ADMIS / NON_DÉPLOYÉ.** Aucune requête réseau, aucune
connexion à un flux, aucun contact fournisseur, aucune lecture VM, aucun secret.
Seconde lecture faite par un autre agent que celui des revues #543/#546/#548 ;
**ce n'est pas une validation humaine** et elle n'a pas relu les bytes privés de #550 :
tout ce qui dépend d'eux reste `NON_VÉRIFIÉ`. #286 reste ACTIVE.

## 1. Ce qui a été relu

Contrats #543/#546/#548, dossiers `market_time_{review_543,attestation_546,qualification_548}`,
`interval_reference.py`, `verify_synthetic_examples.py`, `observability/market_venues/public_us.py`
(`decode_book`), tests existants. Les 43 tests de `test_temporal_interval_reference.py` passent.
J'ai revérifié à la main l'algèbre de `event_window`, `age_window`, `separation_window` et
l'arrondi `chrony_point_bound_ns` (1928 + 800163 + ⌈130041/2⌉ = 867112) : **conformes**.

## 2. Constats

| # | Gravité | Constat | Preuve | Conséquence |
|---|---|---|---|---|
| 1 | P1 | La conclusion #548 « aucune borne finie qualifiée pour les 12 observations REST » est **correcte** : sans borne sur l'offset fournisseur K ni sur le délai événement→champ, deux mondes compatibles donnent des âges différents. Le raisonnement ne dépend pas d'une estimation d'erreur. | `SYNTHETIC_COUNTEREXAMPLES.json`, `verify_synthetic_examples.py` ; algèbre `E=t−K`. | La voie REST reste historique ; aucune capture REST supplémentaire n'apporte l'information manquante (même trois cycles de plus). |
| 2 | P1 | Le modèle #546 ne relie pas l'observateur à l'échelle commune : `age_window(now, event)` exige une `Window` pour `now`, mais rien dans le code ne l'obtient à partir d'une lecture locale + borne chrony, et aucune expiration de borne n'est modélisée (le contrat #548 §3 l'exige). Le texte promet davantage que ce que le code garantit. | `interval_reference.py` : `chrony_point_bound_ns` renvoie un entier nu, sans validité ni domaine. | Comblé dans le prototype (`ObserverAttestation`, validité en horloge locale, refus si la lecture sort du domaine). À reporter dans le modèle si adopté. |
| 3 | P1 | « Fraîcheur » mélange deux quantités : l'**âge du dernier changement d'un niveau** (croît même quand le BBO reste exact) et l'**âge de l'état reflété par le flux**. Dater le BBO par un `event_time` de niveau est faux dans les deux sens (#548 §6 le dit, aucun code ne l'impose). | Test `test_level_time_is_never_used_as_book_age`. | Le prototype ne publie que `level_event_time` brut avec son état, et calcule la fraîcheur à partir du silence du flux et de l'`timestamp` d'enveloppe (heure d'envoi). |
| 4 | P1 | Il existe une mesure **défendable sans horloge fournisseur** : le silence du flux sur l'horloge monotone de l'observateur. Elle peut *refuser* (STALE) mais ne peut jamais *certifier* (elle ignore le retard de transport avant réception). | `freshness()` ; tests silence. | Utile à la V0 comme premier filtre ; budget de silence obligatoire et explicite, sans défaut (décision de gouvernance). |
| 5 | P2 | `decode_book` convertit les dates Coinbase par `datetime.fromisoformat` : neuf décimales tronquées à six (vérifié, Python 3.13). Déjà signalé en #543 ; sans effet sur les 12 lignes (6 décimales) mais à ne pas reprendre pour du L2. | `public_us.py:378` | Le prototype parse en nanosecondes entières (`parse_rfc3339_ns`). |
| 6 | P2 | L'étiquette `age_status="WITHIN_BUDGET"` est posée sur un temps non qualifié (`temporal_semantics` UNRESOLVED à côté). Lisible pour un humain, trompeuse pour un consommateur. Aucune modification proposée ici (hors scope, non déployé). | `public_us.py:441` | À traiter si ce chemin devait être publié : un nom du type `APPARENT_WITHIN_BUDGET`. |
| 7 | P2 | Hypothèses de format L2 non attestées par un extrait daté et haché : libellés `snapshot`/`update`, côtés `bid`/`offer`, `new_quantity` absolue (0 = retrait), snapshot complet, compteur de séquence partagé par tous les canaux, `event_time` de snapshot parfois égal à l'époque Unix. | `DOCUMENTARY_DELTA.json` n'atteste que `event_time`, `timestamp`, `sequence_num` « par connexion ». | Listées `A-*` dans le code et **répétées dans chaque sortie** (`unattested_assumptions`). Les erreurs possibles tombent du côté refus (fail-closed). |
| 8 | P1 (blocage) | Bitstamp WS : documentation illisible (challenge). Pas de contournement, pas d'autre hôte, pas de navigateur. | `DOCUMENTARY_DELTA.json`, `BITSTAMP_WS_DOCUMENT_ACCESS`. | Aucun décodeur Bitstamp n'est écrit : la V0 à deux plateformes en flux L2 est **bloquée côté Bitstamp**. Le deuxième côté du couple reste `SOURCE_NOT_SUPPLIED`. |

## 3. Verdicts distincts

| Périmètre | Verdict | Condition / ce qui manque |
|---|---|---|
| **Code source hors réseau** | **GO (livré dans ce dossier)** | Hypothèses `A-*` explicites ; fixtures inventées ; aucune importation par un producteur, reader, API ou frontend. |
| **Collecte (nouvelle capture L2)** | **NO_GO à ce jour** | Autorisation distincte de l'opérateur ; question fournisseur sur le périmètre du compteur de séquence et le sens de `timestamp`/`event_time` (rédigées, non envoyées) ou plan de capture dont chaque message répond à une hypothèse nommée (voir §5) ; éligibilité d'accès/région de la VM non prouvée ; budget silence/âge décidé ; preuve d'horloge observateur valide sur la durée ; SHA/roster/arrêt/custody. Bitstamp sans documentation lisible : pas de V0 à deux venues. |
| **Publication dans l'app** | **NO_GO** | Artifact compatible non défini (le lecteur actuel n'admet pas le format standalone) ; mapping Python/TypeScript/API GET ; fixtures visuelles ; décision de publication distincte. Une capture ou une fusion de source ne la donne pas. |

## 4. Preuves indispensables pour la V0, et décisions à prendre

Indispensable (sinon refus explicite) : identité exacte du flux (hôte, canal, produit, USD ≠ USDT/USDC),
texte natif conservé, séquence contiguë par connexion, reprise sur snapshot après toute rupture,
heure de réception avec bornes avant/après, et — pour tout chiffre d'âge — un offset fournisseur borné,
un lien envoi→état, une borne observateur valide, le tout couvrant la fenêtre calculée.

À faire décider par l'opérateur (aucune valeur par défaut posée) :
D1 budget de silence ; D2 budget d'âge ; D3 si « LIVE_UNQUALIFIED » (prix natifs + silence, sans âge certifié)
peut être montré à l'écran avec ses états ; D4 politique de reprise (snapshot par produit vs reconnexion
complète) ; D5 si une V0 à une seule venue est acceptable en attendant Bitstamp ;
D6 sur les questions fournisseur : les envoyer (décision séparée) ou ne pas les envoyer. **Accepter un risque ou une hypothèse n'en fait pas une preuve** : cela n'autorise ni qualification, ni publication, et A-SEQ-CONN / A-SEND-AS-OF restent non attestées.

## 5. Ce qu'une capture finie peut et ne peut pas établir

Une capture finie peut **observer des formats et réfuter** des hypothèses (layout, libellés, présence
d'un placeholder d'époque, comportement du compteur sur la durée observée). Elle ne peut pas, seule,
**attester** la complétude d'un snapshot, le domaine général d'un compteur de séquence, la sémantique
absolue d'une quantité, l'offset d'horloge fournisseur ni le lien envoi→état : une absence d'écart sur
un échantillon n'est pas une preuve universelle. Sans clarification documentaire ou sonde d'heure
justifiée, la fenêtre d'âge reste nulle et la meilleure sortie est `LIVE_UNQUALIFIED`.
Une capture qui ne vise aucune hypothèse nommée et réfutable ne vaut pas la requête.

## 6. Le prototype (`l2_reconstruction_prototype.py`)

Décodage strict (clés dupliquées, NaN, nombres JSON fractionnaires refusés : prix/quantités en texte
décimal exact), dates RFC 3339 en nanosecondes entières, carnet par connexion avec états
`NO_SNAPSHOT / LIVE / INVALID / CONNECTION_CLOSED`, application atomique d'un message, invalidation
sur trou, doublon, ordre inversé, message mal formé, retrait inconnu, carnet croisé, dépassement de
niveaux ; reprise uniquement par nouveau snapshot du produit ; aucun état hérité d'une autre connexion ;
BBO avec texte natif et provenance par niveau, sans mid ni spread ; deux questions séparées : silence de la connexion (monotone, tout canal)
et frontière du carnet par produit (heure d'envoi du dernier message `l2_data` portant un événement de ce produit),
qualifiée seulement par une attestation observateur (validité) et fournisseur nommant le même flux
(fournisseur, hôte, canal), le produit et le champ, avec fenêtre de validité et provenance ; relation de paire `NOT_PROVEN` sans deux fenêtres qualifiées.

Tests : `tests/market_venues/test_l2_prototype_551.py` (157 cas après corrections : snapshot/update, trous, reconnexion,
portée de séquence, dates absentes/futures, neuf décimales sans float, expiration des preuves,
non-transfert d'attestation, double comptage, état ancien reçu à l'instant, interdiction d'imports
réseau/horloge). Des mutations du code (doublon, trou, expiration, couverture, signe de l'offset, placeholder,
domaine, flux, refus atomique, validation de type) font chacune échouer au moins un test.

## 7. Limites

Copie du carnet à chaque message (O(niveaux)) : acceptable en prototype, pas pour un débit réel.
Aucune reconnexion automatique, aucun transport. Le prototype ne prouve rien sur un fournisseur réel.
Les fixtures ne sont pas des données de marché. Rien n'a été comparé à des octets privés de #550.
Aucune baseline, dépendance, workflow, producteur ou contrat actif n'est modifié.

## 8. Corrections après la revue technique du HEAD `754c78c0`

Quatre défauts reproduits par la relecture de l'opérateur, corrigés et couverts par des régressions
(les contre-exemples du relecteur sont repris dans `test_l2_prototype_551.py`, section R1–R4) :

| ID | Correction |
|---|---|
| R1 | Le dernier message global ne date plus le carnet. Silence de connexion (tout canal) et frontière du carnet sont séparés ; la frontière est l'heure d'envoi du dernier `l2_data` portant un événement du produit. Un heartbeat ou un autre produit ne la fait pas avancer et n'emprunte pas la preuve `l2_data.timestamp`. Un produit calme garde une frontière ancienne (échec sûr). La continuité de séquence reste indépendante. |
| R2 | Un refus atomique invalide **toute la connexion** (aussi les produits après l'opération fautive) ; un heartbeat ou un delta suivant ne ressuscite rien, les deltas sur base invalide étant écartés. |
| R3 | `ClockAttestation` porte un `FlowIdentity` (fournisseur, hôte, canal, version de layout déclarée) qui doit égaler celui déclaré par la connexion ; fournisseur, hôte, canal, produit et champ ont chacun un contre-exemple. La connexion refuse un flux que le décodeur n'implémente pas. L'identité du flux est déclarée par l'appelant : le prototype n'authentifie aucun transport. |
| R4 | Types validés avant tout lookup (`product_id`, `side`, `type`, `channel`, nombres, dates, listes) : listes, objets, booléens, null, entiers, fractions sont refusés avec invalidation, sans exception. Aucun catch général ajouté. |

Recommandations D1–D6 de l'opérateur-relecteur, **sans décision runtime** : D1 5 s de silence de connexion seulement
si un heartbeat documentaire de 1 s est retenu (valeur de travail à justifier, ni défaut ni seuil de stratégie) ;
D2 âge `null / UNRESOLVED` tant que les preuves manquent, aucun budget admis ; D3 `LIVE_UNQUALIFIED` acceptable pour
une maquette identifiée, sans publication dans l'app active ; D4 invalidation de toute la connexion puis nouvelle
session et snapshots complets (le prototype autorise encore la reprise par snapshot sur la même connexion : mode plus
permissif, qui repose sur A-SNAP-FULL et A-SEQ-CONN, à resserrer dans le futur plan) ; D5 V0 mono-plateforme
explicitement annoncée, aucune comparaison inter-plateformes ; D6 questions préparées, non envoyées.
