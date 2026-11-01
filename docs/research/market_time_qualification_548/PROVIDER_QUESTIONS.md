# Clarifications techniques à obtenir — #548

**Brouillons uniquement : aucun message, ticket ou appel envoyé.**
Écarter toute clé, donnée de compte ou corps de marché privé de ces questions.
Les réponses doivent être attribuées, datées, liées au flux et conservées avec
leurs limites ; une réponse qualitative n'est pas une borne chiffrée.

## Coinbase Advanced REST public

Périmètre : GET /api/v3/brokerage/market/product_book, pricebook.time,
BTC-USD/ETH-USD Spot, distinct de Coinbase Exchange et du canal L2.

1. Quel événement exact est daté : état atomique du carnet, dernière
   modification, génération d'une vue, sérialisation ou envoi du message ?
   Le bid et l'ask sont-ils liés à la même frontière de carnet ?
2. Quelle horloge produit ce champ, et quelle relation documentée a-t-elle
   avec l'heure publique /api/v3/brokerage/time et les horloges L2 ?
   Existe-t-il une borne d'erreur/offset et son domaine de validité ?
3. Quels sont résolution, arrondi et traitement des secondes intercalaires ?
   Une précision sérialisée implique-t-elle une précision garantie ?
4. Quelle politique de cache s'applique à cette route et à quelles couches ?
   Comment relier la notice de cache public et les en-têtes sauvegardés ?
   Une revalidation peut-elle conserver le même carnet ou modifier son timestamp
   sans reconstruire le corps ? Quelle relation maximale corps/événement est garantie ?
5. Pouvez-vous fournir une référence versionnée ou une clarification publiable,
   sans présumer que ces garanties existaient lors de la capture antérieure ?

## Bitstamp REST public

Périmètre : GET /api/v2/order_book/{market_symbol}/, timestamp/microtimestamp,
btcusd/ethusd Spot, distinct des dates de trades, d'authentification ou d'ordres.

1. Quel événement et quel périmètre bid/ask sont datés par ces champs ?
   Sont-ils liés à un état du matching engine, à sa publication ou au message ?
2. Quelles horloges, quelle échelle, quel arrondi et quelles bornes de
   relation/erreur/validité s'appliquent ? Existe-t-il un point de comparaison
   public documenté avec cette même horloge, sans supposer son nom suffisant ?
3. Quelle politique de cache, de revalidation et de conservation du timestamp
   s'applique au carnet ? Que garantissent les réponses sans Age/Cache-Control ?
4. Existe-t-il une documentation publique lisible et versionnée des événements
   du flux WS et de leur frontière de snapshot/séquence, sans exécuter de widget ?
   Cette demande ne présume ni l'équivalence REST/WS ni une autorisation de connexion.

## Candidat Coinbase L2, si un scope séparé est retenu

Clarifier le point de snapshot et la relation temporelle entre un événement
de niveau, l'état complet du BBO, le message émis et une éventuelle sonde.
Demander comment fermer une rupture de séquence/connexion et quelle garantie
d'horloge couvre chaque champ. Ne pas traiter la dernière mise à jour reçue
comme preuve que tous les niveaux et toutes les sources sont à jour.

## Observateur et échelle commune

À documenter dans une future préparation : référence réelle, politique de
seconde intercalaire, réalisation de l'échelle, preuve d'offset, modèle de
variation et validité sur les événements et lectures utilisés.
Aucune migration, nouvelle source NTP, lecture de compte ou changement système
n'est nécessaire pour envoyer ultérieurement des questions documentaires.
Aucun envoi n'est autorisé par la présence de ce fichier.
