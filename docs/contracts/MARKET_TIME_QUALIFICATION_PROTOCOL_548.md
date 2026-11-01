# Protocole de qualification temporelle — #548

**DESIGN_ONLY / NON_ADMIS / NON_DÉPLOYÉ.** Suite du [modèle #546](MARKET_TIME_UNCERTAINTY_546.md).
[Dossier](../research/market_time_qualification_548/README.md) ·
[Matrice](../research/market_time_qualification_548/QUALIFICATION_MATRIX.json).

## Objet et résultat présent

Le but est de borner l'âge d'un état de carnet et sa séparation d'un autre état
pour un usage déclaré. Une chaîne parsable, un HTTP200 ou un temps proche du
temps local ne suffisent pas. Le dossier conservé n'apporte pas de borne finie
qualifiée pour les douze observations REST ; les fenêtres restent nulles.
Ce constat ne signifie pas qu'une erreur importante a réellement eu lieu.

Les définitions documentaires d'un autre transport restent attachées à ce
transport. Le candidat L2 n'est pas une correction du roster REST ni une
attestation rétroactive de ses timestamps. Les observations restent historiques.

## 1. Identifier exactement la quantité à mesurer

Choisir avant les données : âge d'un événement, âge d'une publication,
état du carnet à une frontière complète, ou simple heure de réception.
Ces quantités ont des significations différentes. L'heure du dernier changement
d'un niveau peut être ancienne alors que le niveau est toujours valide ;
l'heure d'un message récent ne certifie pas à elle seule un carnet complet.

Chaque preuve doit porter son rôle, fournisseur, produit, marché, base/devise,
hôte, route ou canal, champ exact, version/instantané, source, localisateur,
empreinte, auteur de l'attestation, hypothèses et limites. Une preuve sans
domaine d'applicabilité n'est pas transférée à un voisin de nom similaire.
USD, USDT et USDC gardent leurs identités distinctes.

## 2. Séparer les dimensions et leurs preuves

| Dimension | Condition de fermeture proposée | Ce qui ne la ferme pas |
| --- | --- | --- |
| Représentation | Texte natif conservé, unité/format et arrondi/incertitude établis | Nombre de décimales ou succès d'un parseur |
| Événement | Définition du champ reliée au bid/ask ou à la frontière recherchée | Définition d'un trade, d'un autre canal ou de Date HTTP |
| Horloge source | Échelle, sens d'offset, erreur, validité et relation à l'événement établis | Mention NTP, nom UTC ou proximité numérique |
| Observateur | Borne valide sur toutes les lectures utilisées, sauts et expiration traités | Un diagnostic ponctuel ou des différences wall/monotone faibles |
| Cache et état | Relation établie entre horodatage, corps et éventuel délai non déjà couvert | max-age, Age absent ou no-cache seuls |
| Frontière de carnet | État complet, ordre, trous et reconnexions traités pour le flux choisi | Dernier message reçu ou maximum des dates de niveaux |
| Paire | Même domaine de comparaison, bornes conservatrices dans une politique explicite | Intersection des fenêtres ou seule différence des dates brutes |
| Présentation | Artifact exact compatible et publication séparément autorisée | Verdict documentaire ou fusion de source |

Ces conditions sont une proposition de preuve, pas un nouvel enum ou seuil actif.
Le format standalone demeure non admis par le lecteur actuel.

## 3. Horloges : domaine, propagation et expiration

L'offset garde le sens source moins temps commun. Une source disant UTC ne
prouve pas une relation physique avec une autre réalisation du temps.
Le diagnostic sauvegardé pointe vers la référence Google ; la notice ajoutée
décrit sa politique de lissage. Aucune activation de lissage, erreur réelle
ou correction de date n'est déduite pour la capture.

La borne conditionnelle 867112 ns reste ponctuelle et relative aux hypothèses
déjà précisées en #546. Une borne de variation et sa validité doivent exister
avant toute propagation ; la fréquence estimée et le Skew ne les remplacent pas.
Des points pré/post ne prouvent pas seuls l'absence d'une excursion intermédiaire.

Une preuve doit avoir un identifiant de domaine commun, une fenêtre de validité,
ses conditions d'expiration/révocation et une couverture des événements concernés.
Après calcul conservateur, toute fenêtre d'événement doit être incluse dans le
domaine de validité de son mapping. Un état ancien servi depuis un cache peut
précéder la validité du run : ne pas extrapoler une preuve récente vers ce passé.
Ne pas régler NTP, déplacer la VM ou redémarrer un service dans cette préparation.

## 4. Cache : deux relations possibles, à démontrer

Si le champ date effectivement l'état recherché, l'âge calculé depuis cet
événement inclut déjà le séjour ultérieur en cache. Ne pas ajouter ce séjour
une seconde fois au délai causal. Les preuves de représentation/horloge/cohérence
du corps doivent néanmoins être valides pour cet événement.

Si le champ date une production ou un envoi de message, il faut une relation
bornée vers l'état du carnet. Sans cette borne, un message récent peut porter
un état ancien. Une validation HTTP d'une ressource ne certifie pas cette relation.
Age absent reste un manque de preuve événementielle ; le calcul HTTP et ses
défauts normatifs restent distincts. Une durée de fraîcheur HTTP ne mesure
ni le séjour réel, ni le retard moteur.

La divergence notice/en-têtes Coinbase est conservée, pas arbitrairement résolue.
Une expérimentation de revalidation devrait conserver tous les headers, les
contextes et les corps, expliquer les cas 200/304 et les couches observables ;
elle ne pourrait pas, à elle seule, attester l'horloge ou l'événement du carnet.

## 5. Pourquoi les mesures actuelles ne suffisent pas

Avec N et t observés, q=0 et délai nul sous hypothèse :
E=t-K et âge=N-t+K pour un offset inconnu K.
Le dossier n'apporte pas de borne supérieure justifiée sur K. Choisir deux K
donne deux histoires compatibles avec les mêmes valeurs encodées et des âges
différents. Il ne s'agit pas d'estimer l'erreur réelle d'une plateforme.

Même ambiguïté si l'offset est posé nul mais que le délai entre événement
recherché et champ daté reste inconnu. Les différences successives d'horloges
annulent également un offset constant ; leur stabilité n'est pas une mesure de
cet offset absolu. Les [exemples synthétiques](../research/market_time_qualification_548/SYNTHETIC_COUNTEREXAMPLES.json)
illustrent ces trois cas, sans définir de budget ou de permission de trading.

## 6. Valeur et limites des futures actions possibles

| Action à décider séparément | Peut apporter | Ne suffit pas à prouver |
| --- | --- | --- |
| Clarification technique fournisseur | Sens exact du champ, horloges liées, politique applicable | Borne numérique si la réponse reste qualitative |
| Relecture documentaire versionnée | Définition pour un flux précis et ses limites | Comportement de la capture historique |
| Sonde d'heure publique | Fenêtre d'offset conditionnelle si l'événement daté est dans une fenêtre justifiée | Relation à l'horloge moteur ou absence de cache par son seul nom |
| Essai de headers de cache | Comportement des réponses sur cet essai et ce chemin | Fraîcheur événementielle de tous les états |
| Diagnostics locaux bornés | État observé et sa cohérence dans leur domaine | Absence de sauts entre mesures sans modèle |
| Capture d'un candidat L2 | Présence/ordre de messages et comportement observé | Reconstruction complète ou alignement d'horloges automatique |

Pour un éventuel flux incrémental : séparer snapshot et mises à jour, vérifier
les trous, les changements de connexion et les frontières de séquence ; définir
ce qui rend un état de carnet à nouveau utilisable après une rupture.
Une séquence attachée à une connexion ne devient pas une séquence moteur globale.
Ne pas dater automatiquement tout le BBO par le dernier update d'un autre niveau.
Une heure d'envoi et une heure d'événement restent deux horloges à relier.

Aucune de ces actions n'est lancée ici. Un nouveau plan devrait fixer SHA,
hôtes/URLs, roster, hypothèses testables, budgets et arrêt, confinement, custody,
reçus et décision exclusive avant exécution. Ne rejouer aucun ancien claim.
Une sonde sans hypothèse identifiable ne résoudrait pas ces ambiguïtés.

## 7. Livraison présente et prochain jalon utile

Livrer la matrice, les pièces documentaires additionnelles, les exemples et
les questions fournisseur sans les envoyer. La lecture Bitstamp WS a rencontré
un document non lisible avec challenge ; ce n'est pas une preuve d'absence de
définition et le challenge n'est pas suivi.

Le jalon suivant est une revue des clarifications de sémantique et de relation
d'horloges, puis la définition d'une expérience bornée seulement si elle apporte
une information identifiable. Aucun nouveau caller n'est préparé sur une
sémantique encore indéterminée. Les budgets de comparaison seront décidés
explicitement avant une admission, sans ajustement sur les trois cycles.
#286 reste ACTIVE autrement ; installation et publication restent distinctes.
