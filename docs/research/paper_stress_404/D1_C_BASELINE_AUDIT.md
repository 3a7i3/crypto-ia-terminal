# D1_C_BASELINE_AUDIT

Relevé GitHub du 2026-10-11 UTC, mission #404, roadmap #285, protections
#282/#286, campagne future #401. Corps des cinq issues et vingt commentaires
#404 relus ; dernière preuve D1-B : issuecomment-6105687514.

| Référence | SHA exact | État observé |
|---|---|---|
| main / clone propre | 2015a88f10c31e3379b569f864696d62c282b0f0 | concordance API et Git |
| #405 | 2499891ab56bdd4dfb35e18ec7d471dddc2cb228 | ouverte, Draft, non fusionnée ; un document, +97 |
| #406 | b99c2ed4f38ebeff481b5f470ed2d08e8e852257 | ouverte, Draft, non fusionnée ; cinq fichiers, +1354 |
| source runtime de référence | 116634be0d3c015cce1cfa58be7da7255414fbfd | historique gouverné ; aucun déploiement déduit |

Clone neuf dans `/workspace/crypto-ia-terminal`, aucun changement préexistant,
aucun AGENTS.md trouvé. CLAUDE.md et docs/DEVELOPER_ENTRYPOINT.md lus : leurs
états documentaires anciens sont distingués des preuves GitHub courantes.

Branche indépendante `research/paper-stress-404-d1-c` depuis #406 : dépendance
explicite, sans modifier sa branche. Pas de worktree nécessaire dans ce clone
neuf. Les cinq fichiers hérités sont conservés ; l'auditeur historique demeure
inchangé (identité source et preuve historique préservées). #405 est un contrat
documentaire parallèle, sans import logiciel requis.

Changements concurrents ouverts relevés par `gh api .../pulls` : #397
`e6fa26b839f5d71db5de390203129c107d5e46e1` (admission), #396
`14ff87aafa65b438493336b23eca73fd774738f6` (extras U8), #374
`c21e1a83f031993ade5551ee7249ee72e86117c6` (registre agents). Aucun intégré.
Risque : si #406 évolue ou est fusionnée, revoir composition/base et CI exactes ;
les changements d'admission #397 sont hors périmètre et ne sont pas activés.

Le diff source gelée → #406 est vide sur rejection_store, decision_observation,
decision_packet, advisor_loop et live_signal_engine. Cela justifie la lecture
comparée des contrats ; cela ne prouve ni l'identité actuelle du runtime, ni
l'appartenance des octets à l'epoch. La capture historique déclare justement
`source_epoch_binding=UNVERIFIED` et `population_completeness=NOT_PROVEN`.

D1-B historique : 10824 packets, 9672 REJECTED, 1152 EXECUTION_PENDING,
5486 liés et 4186 sans lien ; aucun défaut de jointure rapporté. Stdout complet
reçu, sortie finale de l'intersection non indépendamment confirmée. Aucun de
ces nombres n'est une nouvelle mesure D1-C ni une perte démontrée.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
