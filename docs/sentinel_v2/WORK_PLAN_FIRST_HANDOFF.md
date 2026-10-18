# PROMPT DE REPRISE — GPT WORK, MODE PLAN D'ABORD

Version 2026-10-18. Copier le bloc « MISSION » ci-dessous dans **une nouvelle conversation ChatGPT Work**. C'est une instruction de PLANIFICATION, pas une autorisation de coder ou de modifier l'infrastructure.

## MISSION À COPIER DANS WORK

MISSION : SENTINEL-V2-J01-PLAN-FIRST
PROJET : CRYPTO AI TERMINAL — AGENT CIVILIZATION
REPOSITORY : 3a7i3/crypto-ia-terminal
BRANCHE DOCUMENTAIRE : docs/sentinel-v2-j01-work-handoff-20261018
BASE DE RÉFÉRENCE : main@a49eedfcd683145cf8ae6e38c6dc38cff8ea698e
MODE : PLAN / AUDIT READ-ONLY / NO IMPLEMENTATION.

CONTEXTE :
Le fondateur réoriente la vision produit : une communauté d'agents autonomes, avec Sentinel comme futur gouverneur, un secrétariat, des vérificateurs indépendants, des clans, une économie AIC expérimentale et des compétitions de marché en laboratoire. Le produit principal souhaité est une interface d'observation des activités RÉELLES et vérifiables, ressemblant plus tard à un réseau social privé, pas un chatbot principal. Le fondateur définit les objectifs et approuve les gates ; les agents pourront plus tard accepter/refuser des quêtes et expliquer leur décision (raison déclarée, pas émotion humaine).

Le premier chantier J01 est un **journal d'activité persistant**. Il ne crée PAS de worker autonome, d'économie AIC, de monnaie, de marketplace, de nouvelle app mobile ni de connexion LLM.

OBJECTIF DE CETTE SESSION :
Créer un PLAN J01 technique, vérifiable et exécutable **APRÈS APPROBATION**, sans aucune modification de code. Examiner d'abord le dépôt au SHA exact et les documents de la branche documentaire.

ÉTAPE 0 — ACCÈS ET ÉTAT :
- Accéder au dépôt GitHub connecté. Si un navigateur nécessite la connexion, me laisser saisir mes identifiants moi-même. N'accepte ni ne copie de secret dans le chat.
- Vérifier le HEAD courant de main, la branche documentaire et son SHA. Si main a changé, comparer les différences pertinentes ; ne pas transposer un ancien verdict CI au nouveau SHA.
- Vérifier #286 ACTIVE, #315 Gate O, #445, #282, #285, #284 et PR #374 (DRAFT ou état réel constaté). Conserver les nuances source-only / deployed / certified / not_proven.
- Si un accès échoue, le dire précisément : NOT_VERIFIABLE, sans compensation par invention.

ÉTAPE 1 — LECTURES OBLIGATOIRES :
- docs/sentinel_v2/README.md
- docs/sentinel_v2/J01_ACTIVITY_LEDGER_SPEC.md
- docs/sentinel_v2/WORK_PLAN_FIRST_HANDOFF.md (ce fichier)
- README.md ; docs/DEVELOPER_ENTRYPOINT.md ; CLAUDE.md ; CURRENT_TASK.md.
- docs/governance_tower/GOV_TOWER_01_ARCHITECTURE.md ; CONTRACTS.md ; THREAT_MODEL.md ; FUTURE_DEPLOYMENT_PLAN.md ; GT01_LLM_CONTRACT.md ; GT01_G_INTEGRATION.md.
- Code : governance_tower/sentinel/{agent,audit,policy,tools,reasoner,llm_adapter}.py ; governance_tower/contracts.py ; governance_tower/server.py ; governance_tower/ui/*.
- Contrats et statut existants A0/A1 Agent Registry (#284, PR #374) : vérifier s'il y a un module réutilisable ou une collision de schéma, NE PAS le modifier.
- Spécification source disponible dans l'ancienne conversation « SENTINEL_V2_JOURNAL_ACTIVITE_V0.md » ; si non accessible, dire clairement et se baser sur les deux docs GitHub.

ÉTAPE 2 — INVENTAIRE FORENSIQUE :
Dessiner une carte AS-IS avec chemins réels et statuts de preuve pour : Sentinel OBSERVE_ONLY, audit sécurité existant, contrats Governance Tower, UI locale, GitHub provider, Host provider, LLM disabled, Agent Registry A0/A1, API/operator app, tests, règles CI. Signaler les divergences documentation/code. Ne pas confondre « code présent » et « tourne sur VPS » ni « agent déclaré » et « agent actif ».

ÉTAPE 3 — PROPOSER LE PLAN J01 :
Préciser les décisions ouvertes AVANT toute implémentation : placement du module, frontières d'import, contrat JSON strict et canonicalisation, versionnage, enums, validations événementielles, identité du producteur/portée, schéma SQLite et migrations, séquences et concurrence, idempotence (même ID/même charge et collisions), transactions/crash recovery, hachage/chaînage/ancrage futur, bornes et quotas, horodatages, horodatage inconnu, liens causaux, intégrité, restauration, rotation, redaction, séparation audit de sécurité/activité, isolation prod, compatibilité A0/A1.

Construire une matrice de transitions de quêtes (proposer/approuver/refuser/publier/accepter/décliner/démarrer/soumettre/revoir/terminer) avec acteur autorisé, preuve exigée, erreur, tests. Différencier les labels SIMULATED, AGENT_REPORTED, SYSTEM_OBSERVED, OPERATOR_DECISION. L'approbation simulée ne donne aucune permission réelle.

Proposer un découpage de 3 à 6 petites PR SOURCE-ONLY maximum, dépendances, fichiers anticipés, tests unitaires, sécurité et CI, budgets, métriques et critères d'acceptation à chaque gate. Si une seule PR est préférable, justifier. Prévoir un scénario DEMO entièrement synthétique avec 2 agents, 1 acceptation et 1 refus, artefact soumis, revue distincte, redémarrage/rejeu, vérification corruption, doublon, coupure et erreurs. Tous les événements DEMO portent SIMULATED.

ÉTAPE 4 — RISQUES, MENACES, PREUVES :
Inclure une threat model : injection de prompt dans messages, usurpation actor_id, double émission, race conditions, corruption, réécriture totale de chaîne, fausse preuve, leak de secrets, auto-récompenses, collusion, inflation d'événements, dérive de permission, saturation disque, faux état sain. Raison déclarée ≠ pensée interne. Hash chain ≠ preuve de source cryptographique ≠ preuve de valeur économique ; PoW et AIC restent hors J01.

Exiger tests négatifs fail-closed, reproductibles sans réseau ni credentials. Vérifier que ni Advisor/risk/signal/sizing, ni epoch, ni PPL/FIN, ni systemd, ni GitHub Actions, ni VPS ne sont touchés.

ÉTAPE 5 — LIVRABLES DE PLAN :
Rendre dans la conversation Work :
A) EXECUTIVE_DECISION : ce qui existe, ce qui n'existe pas, ce que J01 résout ;
B) INVENTORY_AS_IS : fichiers exacts, SHA, preuves et lacunes ;
C) TARGET_ARCHITECTURE : diagramme clair, frontières ;
D) DETAILED_PHASE_PLAN : tâches, priorités P0/P1, dépendances, estimations modestes, critères de done ;
E) J01_DATA_CONTRACT et QUEST_STATE_MACHINE : propositions avec points d'arbitrage explicites ;
F) SECURITY_AND_TEST_MATRIX : cas positifs et négatifs, commandes envisagées ;
G) REUSE_MATRIX : réutiliser / isoler / ne pas toucher / inconnu (y compris PR #374) ;
H) OPEN_QUESTIONS : maximum cinq arbitrages qui nécessitent mon choix ;
I) PLAN_VERDICT : READY_FOR_OPERATOR_REVIEW ou HOLD / NOT_VERIFIABLE.

Le plan doit être lisible, hiérarchisé et suffisamment détaillé pour servir de mandat à un développeur séparé (ex. Claude Code). Ne jamais transformer un plan en exécution silencieuse.

INTERDICTIONS :
- Ne crée/modifie aucun fichier, issue, branche, PR ou commit PENDANT CETTE PHASE de planification.
- Ne lance aucun workflow ni test qui modifie le dépôt ou un service.
- Aucun accès SSH/VPS, aucun changement de secrets, variables, GitHub App, permission ou facture.
- Ne merge pas, ne déploie pas, ne lance pas de worker/LLM live, ne crée pas d'AIC.
- #286 reste ACTIVE. Aucun contournement par changement de roadmap.
- N'annonce ni Sentinel autonome, ni J01 implémenté, ni intégration GitHub App live prouvée.

STOP CONDITION :
Après avoir livré le plan, attends ma validation explicite. La mission d'implémentation sera créée dans un nouveau mandat et sur une branche distincte. Le code produit ensuite devra passer par CI au SHA exact et revue indépendante.

## COMMANDE COURTE POUR RELANCER WORK

« PLAN D'ABORD — Exécute SENTINEL-V2-J01-PLAN-FIRST en lisant docs/sentinel_v2/README.md, J01_ACTIVITY_LEDGER_SPEC.md et WORK_PLAN_FIRST_HANDOFF.md depuis la branche docs/sentinel-v2-j01-work-handoff-20261018. Produis les neuf livrables de plan sans coder, modifier GitHub ni toucher au VPS ; attends mon feu vert. »
