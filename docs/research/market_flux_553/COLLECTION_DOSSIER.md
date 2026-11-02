# Dossier de décision — collecte bornée CryptoRadar Flux (#553)

**PRÉPARÉ, NON AUTORISÉ, NON EXÉCUTÉ.** Ce dossier alimente une décision opérateur distincte. Ni la fusion
des PR Flux ni une installation inactive ne l'accordent. #286 ACTIVE.

## 1. Question à laquelle la collecte répond (sinon pas de collecte)
Une capture finie peut **observer des formats et réfuter** des hypothèses ; elle n'atteste ni la complétude
d'un snapshot, ni le domaine d'un compteur, ni la sémantique absolue d'une quantité, ni l'offset d'horloge.

| Hypothèse (`A-*`) | Réfutable par une capture ? | Observation qui la réfuterait |
|---|---|---|
| A-LAYOUT | oui | libellé/champ/type différent du layout décodé |
| A-SEQ-CONN | partiellement | trou/doublon/retour en arrière entre canaux sur la durée observée |
| A-QTY-ABS | partiellement | retrait d'un niveau absent, quantité incohérente avec le snapshot |
| A-SNAP-FULL | non (absence d'écart ≠ preuve) | — |
| A-PLACEHOLDER | oui (présence) | `event_time` du snapshot à l'époque Unix ou absent |
| A-SEND-AS-OF, offset fournisseur | non | exige documentation ou sonde d'heure justifiée |
| convention maker/taker (trades) | non | exige documentation ; la capture montre seulement des valeurs brutes |

Une requête, un message ou une connexion qui ne vise aucune ligne « oui/partiellement » n'est pas justifiée.

## 2. Paramètres à fixer avant toute exécution (aucune valeur n'est décidée ici)
SHA exact du paquet et plan signé ; roster (fournisseur, hôte, canal, produits : BTC-USD, ETH-USD Spot,
Coinbase Advanced candidat uniquement) ; admissibilité région/usage de la machine d'exécution (non prouvée) ;
plafonds : connexions, tentatives de reprise, durée, messages, octets, mémoire ; arrêt (limite atteinte,
premier refus d'accès, trou de séquence) ; budget de silence (D1, hypothèse pilote 5 s si un heartbeat de 1 s est retenu) ;
reçus par tentative jusqu'au fsync ; hashes/custody ; contrôle d'horloge de l'observateur pré/post et sa validité ;
stockage privé, aucune redistribution des octets.

## 3. Ce qui reste inconnu après la collecte
Offset et incertitude de l'horloge fournisseur, lien envoi→état, convention de côté des trades, complétude du
snapshot, comparabilité entre plateformes. Le résultat attendu reste `LIVE_UNQUALIFIED` tant que ces preuves manquent.

## 4. Hors périmètre
Bitstamp (documentation WebSocket illisible, aucun contournement), 20–50 plateformes, score, collecteur permanent,
secret/compte/abonnement, message au fournisseur (questions préparées : `docs/research/market_time_qualification_548/PROVIDER_QUESTIONS.md`, non envoyées).
