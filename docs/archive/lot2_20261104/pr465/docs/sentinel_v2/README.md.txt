# SENTINEL V2 — Dossier de reprise canonique (proposition)

Date de cadrage : 2026-10-18. Statut : VISION ET SPÉCIFICATIONS, NON IMPLÉMENTÉES, NON DÉPLOYÉES.
Point de départ GitHub : main@a49eedfcd683145cf8ae6e38c6dc38cff8ea698e, issu de la fusion de PR #464.
Ce document accompagne la roadmap active #285 ; il ne la modifie pas, ne certifie rien et ne donne aucune autorité opérationnelle.

## Intention du fondateur

Faire évoluer Crypto AI Terminal d'une infrastructure principalement consacrée au trading/research vers un **laboratoire de civilisation d'agents**. Le trading crypto demeure un banc d'essai futur (simulation puis PAPER séparé) ; le trading réel n'est plus la priorité produit.

L'opérateur ne souhaite pas converser quotidiennement avec les agents ni leur distribuer leurs tâches une par une. Il veut **observer leur travail effectif**, les décisions, refus, preuves, progrès, échecs, communications, quêtes et résultats, y compris lorsqu'il est absent. Une interaction humaine se concentre sur le sens, les objectifs, la constitution et les validations de publication de quêtes ou d'élévation de permissions.

L'expérience utilisateur visée ressemble à un **réseau social privé de l'activité prouvée** : fil chronologique, profils, fils de discussion et groupes, place des quêtes (« marketplace » de missions), clans, tableaux de classement, généalogies futures. Pas de simulation d'activité masquée en activité réelle. La conversation directe avec Sentinel est facultative et secondaire.

## Principe d'architecture

Humain (constitution et approbations) → règles de gouvernance indépendantes → futur Sentinel Governor (orchestration) → secrétariat (missions/protocoles) + audit indépendant → agents/clans spécialisés → missions expérimentales → preuves → journal d'événements → projections sociales / suivi opérateur.

Le gouverneur ne peut pas supprimer ses restrictions. Les agents ne peuvent pas s'octroyer eux-mêmes de permissions, de budget ou de privilèges. Un vote, une réputation, une récompense AIC ou une réussite en simulation ne constitue jamais une autorisation de déploiement.

**Ne pas confondre les composants** : SENTINEL-01 existant est un observateur déterministe OBSERVE_ONLY ; SENTINEL V2 GOVERNOR est une ambition à spécifier et valider, pas un démon actif ni un agent déjà autonome.

## État existant vérifié dans le dépôt, distinct de la vision

- Code existant : governance_tower/sentinel/{agent,analysis,audit,policy,reasoner,tools,llm_adapter}.py, contracts.py, providers/, scenarios.py, server.py, ui/.
- Interface existante : governance_tower/ui/index.html, app.js et styles.css. C'est une interface locale distincte de l'Operator App, à conversation et raccourcis ; **pas** encore un fil social/observatoire multi-agents intégré.
- Operator App existante : frontend/src/App.tsx, routes Direction, Paper/Live, Research ; pas de route Sentinel dédiée dans ce routeur au SHA de départ. Une future interface doit rester une projection read-only jusqu'à une gate distincte.
- Les fournisseurs GitHub/host sont opt-in et soumis à des limites ; les scénarios SYNTHETIC ne sont pas de l'observation live. Le serveur de Governance Tower est limité au loopback et ne possède pas d'authentification réseau de production.
- PR #464 fusionnée, code source et workflow GitHub App d'intégration disponibles dans main. CI main au SHA de référence : 24 success, 0 failure lors du relevé précédent. **Cela ne prouve aucun déploiement ni la réussite d'une exécution authentifiée du backend Sentinel.**
- GT01-G LIVE PREFLIGHT = HOLD à la dernière vérification : environnement GitHub protégé non vérifiable actuellement (noms et présence du secret/variable, reviewer, restriction main, doublon). APP_IDENTITY = DECLARED ; TOKEN_REPOSITORY_SCOPE = NOT_YET_LIVE_VERIFIED ; APP_INSTALLATION_GLOBAL_SCOPE = NOT_VERIFIABLE.
- Adaptateur de modèle : testé uniquement hors ligne ; GT01_LLM_LIVE = DISABLED. Aucun modèle live ni activité autonome démontrée.
- Governance Tower runtime : NOT_DEPLOYED d'après le plan de déploiement source. Ne pas déduire un état d'exécution VPS de la présence du code GitHub.
- Agent Economy : #284 est une **architecture future** avec contrats A0/A1 certifiés sur main, mais aucun worker/registre runtime/AIC opérationnel. PR #374 Agent Registry pure core reste OPEN/DRAFT et **non fusionnée** au relevé. Étudier ces contrats avant de créer un schéma concurrent.
- Roadmap #285 : référence active antérieure ; toute nouvelle direction doit faire l'objet d'une réconciliation tracée et approuvée, sans écraser le contenu historique.

## Protection des systèmes existants

#286 = ACTIVE_BURN_IN_IMMUTABILITY_GUARD (OPEN) ; #282 non finalisée. Pas de mutation du checkout/epoch/config/Advisor/PPL/FIN/risk/signal/sizing, pas de restart ni systemd, pas de TESTNET/LIVE ni exchange write.
#315 Gate O = OPEN / NON_RESOLVED (OperatorDecision opérationnel NON_DEPLOYED). #445 reste une frontière d'opérations privilégiées distincte.
Le changement de **priorité stratégique** ne clôt pas l'expérience burn-in et ne lève pas ses protections. Une clôture ou migration exigerait ses propres preuves et autorisations.
Seuls docs, contrats, investigations forensiques read-only, code source isolé, tests hors ligne et PR DRAFT sans merge/déploiement sont dans ce cadrage.

## Progression proposée (non autorisante)

| Étape | Produit | Preuve nécessaire |
|---|---|---|
| J01 | Journal d'activité durable, append-only logique, provenance et intégrité | Rejeu après redémarrage, idempotence, refus des invalides, corruption détectée, tests |
| J02 | Projection read-only du journal dans un fil chronologique | Zéro événement inventé, badges SIMULATED/REPORTED/OBSERVED, pagination |
| J03 | Mémoire des missions et planification à budget borné | État durable, arrêt/reprise, absence d'action non autorisée |
| J04 | Premier worker isolé avec capacité d'accepter/refuser une quête | Sandbox, budgets, preuves d'échec et succès, aucune autorité de prod |
| J05 | Secrétariat, conseils de clans, tableau de quêtes et échanges prouvables | Identités, corrélations, acceptation/refus auditables, anti-spam |
| J06 | AIC interne de test : comptabilité des contributions vérifiées | Registre séparé, anti-collusion, aucune valeur externe revendiquée |
| J07 | Clans, spécialisations, scores, lignées et descendants | Benchmarks hors échantillon, reproductibilité, limites de création et coûts |

Ne pas appeler J01 « agent autonome ». Ne pas coder J02–J07 pendant J01.
Le premier produit concret est la **trace vérifiable**, non l'interface Facebook ni un jeton financier.

## Économie : hypothèse de recherche

L'activité sociale et l'échange de messages ne doivent pas être rémunérés en soi : ce serait exploitable par spam et collusion. Étudier un **Proof of Verified Contribution** (PoVC, nom de travail) : problème borné → allocation de mission → artefact → tests/revue indépendants → preuve et coût → récompense interne éventuelle. Les récompenses sont des points/crédits de laboratoire et ne constituent ni une preuve d'utilité économique externe ni une blockchain décentralisée. Ne pas confondre hash-chaînage du journal, preuve de travail cryptographique (PoW) et création de valeur. AIC, banque, clans et compétition demeurent FUTURE / NOT_DEPLOYED.

## Sources canoniques à consulter avant toute planification

- docs/DEVELOPER_ENTRYPOINT.md et CLAUDE.md, CURRENT_TASK.md, README.md.
- #285 roadmap ; #284 économie ; #286 garde ; #315 Gate O ; #445 passerelle ; #282 burn-in ; PR #374 Agent Registry ; PR #464 GitHub App.
- docs/governance_tower/GOV_TOWER_01_ARCHITECTURE.md ; CONTRACTS.md ; THREAT_MODEL.md ; FUTURE_DEPLOYMENT_PLAN.md ; GT01_LLM_CONTRACT.md ; GT01_G_INTEGRATION.md.
- governance_tower/sentinel/audit.py pour distinguer le journal de sécurité existant et le nouveau journal d'activité ; governance_tower/contracts.py pour les contraintes de vérité/provenance.
- docs/sentinel_v2/J01_ACTIVITY_LEDGER_SPEC.md (périmètre fonctionnel J01) ; docs/sentinel_v2/WORK_PLAN_FIRST_HANDOFF.md (mission Work).

## Décision actuelle

Documenter et **planifier d'abord**, avec revue du dépôt et arbitrages explicites. Cette PR documentaire ne contient aucun module, migration, exécution ni nouvelle capacité d'agent.
