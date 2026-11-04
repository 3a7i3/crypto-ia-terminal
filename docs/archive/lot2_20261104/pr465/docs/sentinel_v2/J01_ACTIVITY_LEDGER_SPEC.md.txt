# J01 — Sentinel Persistent Activity Ledger (spécification de travail)

Version 0.1 · 2026-10-18 · PROPOSAL / NOT_IMPLEMENTED / NOT_DEPLOYED.
Alias oral « G01 » : dans ce dossier la mission est **J01**, distincte de **GT01-G** (intégration GitHub App existante).
Ce texte reprend les objectifs du document de cadrage SENTINEL_V2_JOURNAL_ACTIVITE_V0.md ; il est destiné à la planification, pas à l'exécution implicite.

## 1. Produit et limites

Créer la première mémoire persistante **d'activité** destinée à une future communauté d'agents. La valeur est de reconstituer les événements pendant l'absence de l'opérateur : QUI, QUOI, POURQUOI déclaré, QUAND, QUÊTE, AUTORISATION, COÛT, PREUVES, VERDICT.

Distinguer :
- Evénement d'activité de produit (nouveau J01).
- Audit de sécurité existant (governance_tower/sentinel/audit.py).
- Agent Registry A0/A1 prévu par #284 et PR #374.
- Ledger PPL/FIN du trading (intouchable).
Ces systèmes peuvent citer des identifiants de preuve les uns des autres, sans écriture croisée ni assimilation de leur autorité.

Scope J01 : contrat versionné, UTC, identité et provenance, persistance durable locale en labo, append-only logique, séquence monotone, corrélation/causalité, idempotence, preuve d'intégrité, requêtes paginées et replay, tests négatifs.
Hors scope : LLM live, scheduler, worker 24/7, agent « parent » actif, réseaux sociaux, AIC / rewards réelles, wallets, marketplace réel, mutations GitHub, VPS de prod, déploiement, PAPER/TESTNET/LIVE. Données synthétiques affichées SIMULATED.

## 2. Schéma canonique d'événement : sentinel-event/0.1

| Champ | Règle |
|---|---|
| schema_version | version explicite « sentinel-event/0.1 » |
| event_id | unique au journal, stable en cas de réémission |
| sequence | entier strictement monotone attribué par le journal, jamais par l'agent |
| occurred_at_utc | instant déclaré UTC ou null (unknown ≠ maintenant) |
| recorded_at_utc | instant effectif d'acceptation du journal, UTC obligatoire |
| actor_id, actor_kind, actor_version | identité / opérateur / système, version déclarée ou documentée |
| event_type | membre d'un enum fermé, jamais chaîne libre inconnue |
| quest_id | identifiant stable ou null hors quête |
| correlation_id | identifiant de flux ou null |
| causation_event_id | événement parent existant dans la même chaîne ou null |
| source_kind | SYSTEM_OBSERVED / AGENT_REPORTED / OPERATOR_DECISION / SIMULATED |
| summary | texte factuel court, expurgé et borné |
| reason_declared | motif déclaré, borné, potentiellement null ; PAS motivation interne prouvée |
| payload | schéma validé par type, types stricts, taille maximale |
| evidence_refs | pointeurs validés vers preuves, éventuellement [] pour proposition |
| authorization_ref | référence de permission exacte si applicable, sinon null |
| integrity | previous_hash + event_hash produits/validés par l'enregistreur |

**Provenance non interchangeable :** AGENT_REPORTED n'est pas SYSTEM_OBSERVED ; SIMULATED n'est ni un résultat réel ni une approbation réelle. Les déclarations d'un agent n'ont pas d'autorité pour changer la politique. L'identité annoncée par l'agent n'est pas une authentification du producteur ; un producteur doit être reconnu par le service d'ingestion en dehors de son payload. Si un champ est inconnu, le conserver explicitement UNKNOWN / null selon le contrat, sans le transformer en 0 ou succès.

L'intégrité nécessite une sérialisation canonique précisément spécifiée, un hash précédent et un hash d'événement. Un hash-chaînage dans une seule base **ne résiste pas** à une réécriture complète par un attaquant ayant accès à cette base. Prévoir, dans un stade ultérieur distinct, un ancrage de tête externe et une politique de sauvegarde/rotation. Ne pas prétendre que SHA-256 signe l'identité des agents.

## 3. Types initialement admis

Cycle de quête :
QUEST_PROPOSED ; QUEST_APPROVED ; QUEST_REJECTED ; QUEST_PUBLISHED ;
QUEST_ACCEPTED ; QUEST_DECLINED ; WORK_STARTED ; ARTIFACT_SUBMITTED ;
REVIEW_PASSED ; REVIEW_FAILED ; QUEST_COMPLETED ; QUEST_FAILED.

Supervision :
OBSERVATION_RECORDED ; ANOMALY_DETECTED ; RUN_INTERRUPTED ;
BUDGET_EXHAUSTED ; POLICY_DENIED ; AUDIT_UNAVAILABLE.

Toute transition invalidant le passé est refusée, par exemple publication d'une quête rejetée sans nouvelle approbation traçable, attribution de réussite sur simple acceptation, validation par soumission seule. Toute revue de réussite importante doit disposer d'une preuve et d'un vérificateur distinct de l'auteur lorsque pertinent.

**La validation d'une quête pour publication** n'accorde PAS un droit de shell, de modification GitHub, de déploiement, de mutation du runtime ni d'action financière.

## 4. Architecture suggérée — à confirmer lors du PLAN

Service d'enregistrement local isolé + SQLite dédiée en laboratoire (transaction ACID, séquence atomique, unicité event_id, index sur temps/quête/acteur/corrélation) + lecteur/validateurs purs. Pas d'endpoint réseau public et pas d'import du registre dans Advisor ni risk/signal/sizing.

Chaîne :
candidat synthétique → validation du schéma et de la provenance → contrôles de portée, d'idempotence et d'expurgation → transaction SQLite append-only → hash → lecture/rejeu ordonnés → vues futures.

Exigences transverses :
- Contraintes de taille, délais, nombre d'événements et budget disque.
- Écriture transactionnelle ; crash partiel sans event « demi-committé ».
- Réémission identique du même event_id = no-op/idempotent ; collision avec contenu différent = erreur explicite.
- Séquence sans retour en arrière ; causalité lisible ; index de pagination stable.
- Pas de secrets/PAT/clé/.env/journal brut ni chaîne de raisonnement interne dans les événements.
- Entrée malveillante traitée comme **donnée** ; validation, expurgation et rendu neutre.
- Rétention, archivage, restauration et sauvegarde documentés ; aucun effacement silencieux.
- Journaux d'erreur/permissions SQLite restreints au laboratoire, aucun chemin prod.
- Production d'une vue future en lecture seule ; son existence ne donne aucun pouvoir d'exécution.

## 5. Démonstration synthétique de bout en bout

Scénario nominal explicitement étiqueté SIMULATED :
1. Sentinel-DEMO propose une quête de diagnostic d'un simulateur fictif.
2. Décision d'opérateur **simulée** autorisant uniquement la publication.
3. Publication de la quête fictive.
4. Agent-DEMO-A accepte pour une raison déclarée ; agent-DEMO-B refuse faute de budget.
5. Agent-DEMO-A soumet un artefact fictif ; un reviewer simulé distinct rend son verdict.
6. La quête est clôturée dans la simulation, sans AIC réel.
7. Arrêt du processus, réouverture de la même base, replay identique des événements et hashes.
8. Réémission d'un event_id identique → aucune nouvelle ligne.
9. Corruption intentionnelle d'une ligne, du hash ou de l'ordre → échec explicite d'intégrité.
10. Coupure en cours de transaction, stockage plein ou injoignable, budget dépassé → échec apparent, jamais succès inventé.
11. Event mal typé, enum inconnu, causation orpheline, transition interdite, texte hostile, oversized payload, timestamps anormaux → refus sûr.
12. Test d'isolation prouvant aucune mutation de main, runtime PAPER, PPL/FIN, VPS ou environnement GitHub.

## 6. Définition de done (gate J01)

- Contrat documenté et versionné ; compatibilité/intégration A0/A1 examinée.
- Tests d'intégrité, rejouabilité, idempotence et mauvaises transitions au moins.
- Test de redémarrage réel du processus de test/labo ; preuve du SHA et commandes.
- Test de crash simulé et de corruption ; erreurs distinctes (NO_DATA ≠ UNAVAILABLE ≠ CORRUPTED).
- Exemples/fixtures clairement SIMULATED, sans faux PnL ni activité d'agent imaginaire présentée comme réelle.
- Aucun appel réseau, IA externe, exchange, SSH ou GitHub Action authentifiée.
- Code source cantonné au laboratoire, sur branche isolée ; CI au HEAD exact ; revue indépendante avant fusion.
- Rapport final vérifiable décrivant LIMITATIONS/NOT_PROVEN. Le succès J01 n'est PAS SENTINEL_AUTONOMOUS_VERIFIED.

## 7. Gates futures distinctes (aucune activation)

J02 fil d'activité READ ONLY ; J03 planificateur/mémoire ; J04 worker isolé et décision de participer ; J05 plusieurs agents/quête-board/échanges ; J06 crédits AIC de test attribués à des contributions vérifiées ; J07 clans, lignées, compétition et descendants. Toute nouvelle permission exige une gate dédiée et la conservation de la souveraineté de l'opérateur.

## 8. Sources à préserver

Issue #286 ACTIVE (freeze) ; #285 roadmap ; #284 Agent Economy ; #315 Gate O ; #445 passerelle ; #282.
docs/governance_tower/CONTRACTS.md, THREAT_MODEL.md, GOV_TOWER_01_ARCHITECTURE.md, FUTURE_DEPLOYMENT_PLAN.md.
governance_tower/sentinel/audit.py, governance_tower/contracts.py ; PR #374 DRAFT à comparer avant toute réutilisation Agent Registry.

**Ce document est une spécification, pas un rapport de tests ni une implémentation réalisée.**
