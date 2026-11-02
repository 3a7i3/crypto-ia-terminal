# Dossier de décision — publication CryptoRadar Flux dans l'app (#553)

**PRÉPARÉ, NON AUTORISÉ, NON EXÉCUTÉ.** Une fusion de source n'est pas une publication ; une installation
inactive n'est pas un démarrage.

## 1. Prérequis (tous distincts)
1. Artifact exact : `MarketFlowArtifact` 1.0.0, produit par un producteur gouverné (aujourd'hui seulement des fixtures `SYNTHETIC`).
2. Usage admissible déclaré (D3 : `LIVE_UNQUALIFIED` acceptable pour maquette identifiée, pas dans l'app active sans décision).
3. Contrat compatible Python/TypeScript : **le validateur TypeScript et la vue ne sont pas encore livrés** (voir HANDOFF).
4. Reader/API GET : `GET /api/operator/v1/market-flow`, source `OPERATOR_MARKET_FLOW_PATH` (non défini par défaut → 503 `MARKET_FLOW_NOT_CONFIGURED`).
5. Vérification privée avant bascule : hash de l'artifact, âge, couverture, états `UNKNOWN/STALE/NOT_AVAILABLE` visibles.
6. Release frontend épinglée (SHA, tree, hashes des fichiers) et exception #286 distincte.

## 2. Bascule (à décrire dans le futur plan, non exécutée ici)
Définir `OPERATOR_MARKET_FLOW_PATH` vers l'artifact vérifié, recharger le service d'API concerné, servir la nouvelle release frontend.
Chaque étape est une action de service : **hors de ce mandat**.

## 3. Rollback concret
Retirer la variable `OPERATOR_MARKET_FLOW_PATH` (retour à « non configuré », 503 typé), restaurer le lien de release
précédent, conserver l'artifact et les journaux pour l'audit. Le SHA et le chemin précédents doivent être consignés
avant la bascule ; aucun rollback n'est exécuté ici.

## 4. Ce que la publication ne dit pas
Pas de score, pas de recommandation, pas de comparaison entre plateformes, aucune cause de disparition d'un niveau,
aucune fraîcheur certifiée sans preuves d'horloge. Une fixture n'est jamais présentée comme LIVE.
