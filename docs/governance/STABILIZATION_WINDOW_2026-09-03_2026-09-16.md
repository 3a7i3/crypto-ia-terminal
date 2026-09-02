# STABILIZATION WINDOW — 3 au 16 septembre 2026

## Décision

La certification du burn-in EXP-001 est suspendue à compter du
`2026-09-02T20:18:12Z`. Le runtime VPS reste actif en paper/revision afin de
tester le comportement réel de l'infrastructure. Son historique est conservé
pour analyse forensic, mais il n'est pas certifiable et ne doit pas être
mélangé à la prochaine époque expérimentale.

La fenêtre opérationnelle `STABILIZATION_LAB` court du 3 septembre 2026
au 16 septembre 2026 inclus. Elle peut être close plus tôt par verdict humain,
mais ne peut jamais déclencher automatiquement un nouveau burn-in.

## Motif

Le burn-in a été lancé avant certification suffisante du runtime, des
entrypoints, des datasets, de la vérité des positions, du protocole d'ordre
et de la chaîne d'observabilité. Des pulls et redémarrages successifs ont
empêché de traiter le volume affiché comme une population expérimentale
homogène. L'opérateur rapporte près de 500 opérations affichées mais seulement
38 clôtures réellement enregistrées; ces valeurs restent à réconcilier par un
audit runtime et ne constituent pas une preuve certifiée.

## État de sécurité obligatoire

- `PAPER_TRADING_ENABLED=true`.
- `LIVE_TRADING_CONFIRMED=false`.
- Aucune clé API avec permission de retrait.
- Aucun trading réel.
- Kill switch, limites de taille, journal d'audit et contrôles d'autorité conservés.
- ADR-0007 inchangé: observers, Telegram, LMI, regret et recherche restent passifs.
- `FEATURE_AUTO_CALIBRATION=false`.
- Aucune modification opportuniste de `GATE_MIN_SCORE_OVERRIDE`,
  `PB_MIN_POSITION_USD` ou d'un seuil de stratégie.

Ces lignes sont des exigences à vérifier sur le VPS, pas une attestation de
l'état actuellement déployé.

## Sémantique des données

- Les données antérieures à la suspension restent intactes et forensic.
- Les données produites pendant la révision portent
  `revision_mode=true` et `certified=false`, ou sont séparées par une racine
  et un manifest propres.
- Le compteur du prochain burn-in repartira à `N=0` dans une nouvelle
  expérience, sur un commit et une configuration figés.
- Aucun rapport de la fenêtre de révision ne peut annoncer
  `READY_FOR_BURNIN` sans le gate final signé.

## Travaux autorisés

- Audits read-only, provenance runtime et inventaire des entrypoints.
- Instrumentation passive et qualité des données.
- Corrections de défauts démontrés avec test, rollback et preuve runtime.
- Replay/shadow bornés et pré-enregistrés, une variable à la fois.
- Tests de restart, continuité, idempotence et réconciliation.

## Travaux interdits

- Nouveau signal, indicateur, modèle IA, stratégie ou boucle adaptative.
- Calibration alpha ou changement de seuil à partir des résultats observés.
- Activation live, micro-live ou permissions API de trading/retrait.
- Suppression ou réécriture des journaux historiques.
- Modification rétroactive de `experiments/EXP-001.yaml`.
- Déploiement d'une branche non mergée, d'un SHA non identifié ou restart sans vérification post-déploiement.
- Interaction décisionnelle de Telegram, LMI ou d'un observer avec le moteur.

## Protocole de déploiement pendant la révision

Le VPS reste disponible comme banc d'essai de l'infrastructure réelle. Les
tests runtime sont nécessaires notamment pour systemd, la concurrence des
processus, la rotation des fichiers, les permissions, le réseau et Telegram.

Un changement peut atteindre le VPS uniquement selon cette chaîne:

1. une question causale et une PR dédiée;
2. tests ciblés et CI interprétée;
3. revue puis merge sur `main`;
4. déploiement explicite du SHA mergé, jamais de la branche de travail;
5. `git fetch` puis mise à jour en fast-forward uniquement;
6. vérification du SHA et des flags non secrets;
7. restart du seul service concerné;
8. smoke test, journal borné et preuve de santé;
9. période d'observation de 24 à 48 heures;
10. verdict PASS, FAIL ou ROLLBACK avant la mission suivante.

Le téléphone peut déclencher ce protocole par une interface GitHub
`workflow_dispatch` contrôlée. Cela n'autorise pas un déploiement automatique
sur chaque push. Chaque run doit être lié au commit mergé qui l'a déclenché,
produire un rapport d'audit et conserver un rollback explicite.

Les données produites après chaque déploiement restent
`revision_mode=true`, `certified=false`. Les pulls, pushes, déploiements et
restarts sont autorisés comme instruments de validation; ils rendent
précisément cette fenêtre impropre à un burn-in statistique homogène.

## Méthode de correction

Avant chaque écriture:

1. formuler la question scientifique;
2. énumérer les hypothèses concurrentes;
3. définir la preuve minimale;
4. identifier fichiers, impact runtime et rollback;
5. définir tests et critère PASS/FAIL;
6. confirmer le périmètre paper/replay/shadow.

Une cause non démontrée reçoit `INCONCLUSIF` et ne justifie aucun changement.
Une mission = une branche = une PR = un problème causal.

## Ordre des 14 jours

1. Gouvernance et baseline disque.
2. Provenance runtime et entrypoints.
3. Lifecycle, halt et restart.
4. Intégrité, fraîcheur, writers, doublons et rotation des datasets.
5. Réconciliation DecisionPacket et attrition.
6. Telegram passif: ACK, NO_CHANGE, FAILURE, retry et latence.
7. Checkpoint et réduction du backlog aux bloqueurs.
8. Vérité positions/portefeuille.
9. Idempotence et sécurité du cycle d'ordre.
10. Réalisme paper/shadow: frais, slippage, précision, rejets, partial fills.
11. Baselines et pré-enregistrement.
12. Chaos et continuité.
13. Répétition figée de 24 heures, zéro modification.
14. Audit final et verdict.

## Gate READY_FOR_BURNIN

Le verdict `READY` exige simultanément:

- contrat de gouvernance clôturé et nouveau manifest signé;
- CI et tests ciblés acceptables;
- commit, configuration, services et runtime attribuables;
- un seul moteur et aucun PID orphelin;
- datasets frais, cohérents, dédupliqués et correctement rotés;
- pipeline réconcilié sans événements perdus;
- aucune position fantôme après restart;
- tailles invalides rejetées;
- cycle d'ordre idempotent;
- frais, slippage, précision et rejets visibles;
- Telegram observable et passif;
- capacité disque suffisante;
- 24 heures figées sans incident critique.

Verdicts autorisés:

- `READY`: ouvrir une nouvelle expérience et repartir à `N=0`;
- `CONDITIONAL`: prolonger la répétition sans burn-in certifié;
- `NOT_READY`: revenir à une correction ciblée en Stabilization Lab.

## Sortie et autorité

Seul l'opérateur humain peut signer le verdict. La date du 16 septembre
représente une échéance d'audit, jamais une autorisation de reprise.
