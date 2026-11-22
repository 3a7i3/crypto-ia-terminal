# Inventaire Agents pour le domaine Système — étape 2

Statut : **inventaire source + constat VPS ponctuel**, sans activation d'agent ni modification d'interface. Source examinée : branche `ui/market-scanner-microstructure-wallet` @ `542c12e1` (base de la PR #595). Observation VPS `crypto-restore-01` : **2026-11-21T19:45:17Z**. Ce document ne prétend pas reconstituer les exécutions passées de GitHub Copilot ni certifier tous les processus futurs.

## Règles de preuve

- **Profil GitHub** = instruction `.agent.md` présente en source. Ce n'est ni une instance exécutée ni une capacité autorisée dans CAT.
- **Module Python** = classe/fonction présente en source. Il faut une liaison identifiée à un processus et une trace datée pour dire « actif ».
- **Actif observé** = identité + processus/runner + invocation datée + résultat ou heartbeat corrélé. Une unité systemd, un nom de fichier, un import ou un état `REGISTERED` ne suffisent pas.
- Validation du profil = statut de revue de [l'inventaire A0](AGENT_ECON_A0_GITHUB_AGENTS_INVENTORY.md), **distinct** de l'activité. Le [contrat A1](../contracts/AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md) est contract-only/non déployé et stipule `REGISTERED ≠ running ≠ authorized`.
- Les familles ci-dessous sont des **catégories d'affichage proposées**, pas des classes A1 ni des droits. « Exécution PAPER » n'accorde aucune exécution.

## Profils GitHub : identité, famille, mission, validation et activité

Les dix premiers profils viennent de `.github/agents/`. Les deux derniers sont dans `.github/` ; ils ne doivent pas disparaître du recensement.

| Profil et source | Famille proposée | Mission déclarée | Validation source | Preuve d'activité |
|---|---|---|---|---|
| [data-provenance-auditor](../../.github/agents/data-provenance-auditor.agent.md) | Observation | Auditer provenance, schémas, fraîcheur et traçabilité des datasets. | `MIGRATION_CANDIDATE` ; une spec bornée reste à créer. | **Aucune invocation/trace datée fournie** ; runtime non attesté. |
| [observability-cartographer](../../.github/agents/observability-cartographer.agent.md) | Observation | Cartographier métriques, snapshots et sources de vérité. | `MIGRATION_CANDIDATE` ; spec et périmètre à définir. | Aucune invocation/trace datée fournie. |
| [repository-cartographer](../../.github/agents/repository-cartographer.agent.md) | Observation | Cartographier dépôt, dépendances et frontières. | `MIGRATION_CANDIDATE` ; chevauche Repo Architect. | Aucune invocation/trace datée fournie. |
| [repo-architect](../../.github/repo-architect.agent.md) | Observation | Examiner l'architecture réelle avant modification. | `REVIEW_REQUIRED` ; profil hors dossier et front matter non fermé. | Aucune invocation/trace datée fournie. |
| [mission-preparation-researcher](../../.github/agents/mission-preparation-researcher.agent.md) | Recherche | Préparer un dossier de preuves avant mission. | `REVIEW_REQUIRED` ; l'outil `web` dépasse le catalogue A0. | Aucune invocation/trace datée fournie. |
| [research-scientist](../../.github/research-scientist.agent.md) | Recherche | Concevoir des expériences falsifiables et reproductibles. | `REVIEW_REQUIRED` ; profil hors dossier, frontière Research/Live à qualifier. | Aucune invocation/trace datée fournie. |
| [statistician-agent](../../.github/agents/statistician-agent.agent.md) | Évaluation | Examiner biais et validité statistique. | `REVIEW_REQUIRED` ; fonction de revue réservée, outils non bornés. | Aucune invocation/trace datée fournie. |
| [decision-path-forensic](../../.github/agents/decision-path-forensic.agent.md) | Risque et gouvernance | Tracer les chemins signal → gate → autorisation → exécution. | `MIGRATION_CANDIDATE` ; diagnostic seulement, sans autorité. | Aucune invocation/trace datée fournie. |
| [security-Guardian-agent](../../.github/agents/security-Guardian-agent.agent.md) | Risque et gouvernance | Examiner sécurité et frontière Research/PAPER/Live. | `REVIEW_REQUIRED` ; outils non bornés, pas de veto automatique. | Aucune invocation/trace datée fournie. |
| [system-diagnostic](../../.github/agents/system-diagnostic.agent.md) | Maintenance | Diagnostiquer Linux, VPS, services et réseau. | `REVIEW_REQUIRED` ; scinder audit dépôt et lecture runtime. | Aucune invocation/trace datée fournie. |
| [hedge-fund-architect](../../.github/agents/hedge-fund-architect.agent.md) | Héritage à arbitrer | Ancien profil d'architecture trading, édition, exécution et délégation. | `BLOCKED_LEGACY_RECONCILIATION` ; ne pas présenter comme agent opérationnel. | Aucune invocation/trace datée fournie. |
| [sniper-engine](../../.github/agents/sniper-engine.agent.md) | Héritage à arbitrer | Décrit l'exécution rapide d'ordres. | `BLOCKED_LEGACY_RECONCILIATION` ; aucun périmètre PAPER attesté. | Aucune invocation/trace datée fournie. |

**Famille Exécution PAPER : zéro profil GitHub qualifié.** Le nom `sniper-engine` ne prouve ni simulation PAPER ni permission de trading. Aucun des 12 profils n'a été qualifié « actif observé » par cet audit. Cela signifie **activité non prouvée dans les sources examinées**, et non « n'a jamais été appelé » sur une plateforme extérieure.

## Code Python : capacités candidates, pas des cartes d'agents

| Capacité source | Branchement vérifié dans le dépôt | Conclusion pour Système |
|---|---|---|
| `quant_hedge_ai/agents/strategy/strategy_generator.py` et `agents/research/strategy_researcher.py` | Instanciés notamment dans `quant_hedge_ai/main_v91.py` et `main_system.py`. | Capacités de génération/sélection présentes ; aucune preuve que ces points d'entrée tournent sur le VPS. |
| `quant_hedge_ai/agents/quant/backtest_lab.py` | Appelé par les pipelines de recherche et par `main_v91.py`/`main_system.py`. | Moteur de test en source, pas une identité d'agent autonome attestée. |
| `quant_hedge_ai/agents/execution/paper_trading_engine.py` | Instancié dans les points d'entrée historiques et testé. | Moteur PAPER en source ; ne pas le confondre avec un agent autonome actif. |
| `quant_hedge_ai/agents/risk/global_risk_gate.py` | Contrôle de risque importé par les points d'entrée ; contrat distinct d'une identité d'agent. | À présenter comme garde de la machine, pas comme une carte d'agent. |
| `core/advisor_loop.py` et `scripts/systemd/crypto-advisor.service` | Point d'entrée/unité déclarés dans Git. | L'unité `crypto-advisor.service` était **inactive** sur le VPS lors du constat ; aucune instance Advisor observée. |

Cette sélection n'est pas un inventaire de toutes les classes Python. L'étape ultérieure de branchement doit relever pour chaque candidat le runner réel, la configuration, l'identité stable, les entrées/sorties et une preuve d'exécution datée avant de créer sa carte « actif ».

## Constat runtime ponctuel

À `2026-11-21T19:45:17Z` sur `crypto-restore-01` : `crypto-operator-web.service` et `crypto-operator-api.service` étaient actifs, `crypto-advisor.service` inactif. Aucun processus `advisor_loop.py`, `main_v91.py` ou `main_system.py` n'apparaissait dans la recherche `ps` ciblée. Le web servait le service worker SHA-256 `4d2fc9ac38ab6c2795afabfd04bcf3cd1c0e6430c3e8ac52c5c532941279e067` du lot Wallet. **Ce constat de services ne prouve pas l'activité des profils GitHub.** Les journaux d'invocation GitHub Copilot n'ont pas été audités.

## Destination proposée dans Système (étape 3, non implémentée)

- Garder la page `/paper-live/system` et ses panneaux existants `RuntimeServiceView`, `StorageView` et « Diagnostic applicatif Advisor ».
- Ajouter une section **Agents** composée de cartes par famille. Première vue : nom, mission courte, provenance GitHub/code, statut de validation, statut d'activité et horodatage de la dernière preuve *si disponible*. Une fiche dépliable porte les détails et les limites.
- États d'activité fermés : `ACTIF_OBSERVÉ`, `INACTIF_OBSERVÉ` (runner identifié), `NON_ATTESTÉ` (valeur par défaut). Pas de `ACTIF` déduit d'un profil, d'un test ou d'une API web disponible.
- Montrer « Exécution PAPER · aucun profil qualifié » et placer les deux profils hérités bloqués dans un détail distinct, sans bouton de lancement.
- Ne pas brancher l'interface sur le contrat A1 comme s'il était déployé. Les cartes pourront d'abord utiliser un inventaire source versionné ; une télémétrie runtime future devra être indépendante, datée et bornée.

## Critères d'acceptation de l'étape 3

1. Sur S24+, familles et cartes lisibles sans défilement horizontal ; aucun tableau dense.
2. Les 12 profils ont chacun une source consultable ; aucun n'est affiché « actif » sans preuve d'invocation.
3. Les moteurs Python, le gate et les unités ne deviennent pas des agents par leur seul nom.
4. Les panneaux Système existants et Finance/Wallet restent inchangés ; aucune activation, exécution, fusion ou déploiement ne découle de l'affichage.
