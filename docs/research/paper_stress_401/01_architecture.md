# Rapport 1 — Audit S0 de l’architecture

Mission [#401](https://github.com/3a7i3/crypto-ia-terminal/issues/401), audit du
2026-10-10 UTC. Base GitHub et clone propre :
`b751333e53c8c341d8a4a64af82499bc03140210`. Aucun AGENTS.md trouvé dans le checkout.
CURRENT_TASK/entrée développeur portent des états historiques plus anciens ;
les corps et commentaires GitHub #401/#286/#282/#285 prévalent.

## État vérifié avant modifications

`main` distant et HEAD local concordent. Trois PR ouvertes lors du relevé :
#374 (Agent Registry), #396 (extras U8), #397 (fence d’admission).
La branche `research/paper-stress-401-offline` était absente du remote et a été
créée depuis main. Branches Research historiques disponibles :
`rl-data-01-paper-research-provenance`, `rl-replay-01-offline-replay-engine`,
`rl-burnin-01-no-feedback-contract`, `rl-integrate-01-research-stack-main`.
Pas de cherry-pick de #397 : son installation activerait DENY.

Le commentaire [#282 du 10 octobre](https://github.com/3a7i3/crypto-ia-terminal/issues/282#issuecomment-6094708362)
atteste une observation limitée Advisor active/running, mais pas le SHA runtime,
les compteurs PPL actuels, la quiescence ou FIN finale. Les projections STALE
(séquence 171 non vérifiée, FIN d’une epoch antérieure) ne sont pas autoritaires.
Burn-in/Research GET 503 ne signifie pas zéro dataset ou zéro lifecycle.
Aucun checkpoint VPS n’a été exécuté dans cette mission.

## Inventaire source et réutilisation

| Surface | Fonctions/capacités | Disposition dans #401 |
|---|---|---|
| `research_data/paper_exporter.py` | `export_paper_dataset`, hashes, copies exactes, exclusions de chemins | KEEP ; contrat d’entrée, aucun export du runtime effectué |
| `research_replay/factual.py` | `validate_dataset`, `replay_factual_dataset` | REUSE ; validation/identités et métriques PPL exactes |
| `paper_trading/paper_portfolio_ledger.py` | `project`, transitions OPEN/CLOSE/UNRESOLVED | REUSE transitif par replay ; pas de store |
| `research_diag/factual.py` | `diagnose_factual_dataset`, attribution aux DecisionPackets | KEEP ; nécessaire aux futures analyses par régime, pas exécuté sans evidence |
| `research_data/burn_in_research.py` | `BurnInResearchWorkspace`, racines protégées, copies seulement | KEEP ; pas de publication/candidat vers l’epoch courante |
| `research_data/burn_in_finalization.py` | `designate_final_burn_in_dataset`, preuves de quiescence | KEEP ; aucune finalisation demandée ou exécutée |
| `research_replay/publication.py` | publication exclusive, hashes de composants | KEEP ; runner #401 retourne un envelope en mémoire/stdout |
| `research_candidate/` | identités, registre, future-only promotion | KEEP ; aucun candidat promu, aucune autorité accordée |
| `financial_institute/ppl_adapter.py`, `ledger.py`, `reconciliation.py` | `adapt_ppl_stream`, `project_financial_ledger`, FinancialContext explicite | KEEP ; réconciliation future seulement avec contexte certifié, pas de FIN runtime |
| `paper_trading/admission_policy.py` | `evaluate_hard_portfolio_ceiling` pur Level A | KEEP ; plafond mécanique ne certifie ni concentration ni corrélation |
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | limites exposition/corrélation/régime | KEEP ; défauts environnement et corrélations approximatives, pas de preuve empirique |
| `paper_trading/mexc_simulator.py` | frais/slippage, TP/SL/timeout, capital, notifications/PPL | KEEP gelé ; imports/runtime mutation inadaptés à ce runner |
| `src/backtest/engine.py` | BT-00 entrée next-bar, pas de lookahead simple | ADAPTER_REQUIRED ; candles absentes, horloge/RunContext, pas moteur canonique PPL |
| `market_data/replay_engine.py` | replay de trajectoire marché | ADAPTER_REQUIRED ; dataset marché certifié absent |
| DIP/legacy replay, BacktestLab | heuristiques/approximations ou stores non liés | EXCLUDED du moteur canonique suivant RL-REPLAY-01 |

## Datasets réellement disponibles

Aucun `dataset manifest + composants` certifié n’est présent dans le clone.
La recherche des fichiers suivis n’a trouvé ni manifest dataset ni trajectoire
immuable admissible. Les tests construisent des fixtures éphémères synthétiques.
Pas de récupération depuis un home VPS, de ledger privé ou de secret.

Références historiques de #282, bytes NON DISPONIBLES dans cette mission :

| Capture | dataset_id | Couverture documentée, pas revalidée ici |
|---|---|---|
| O4 | `fdfadabe468a0eaa4b2854e25fa7ccf746ee918b2c9bf7024c7f9fa5a9a5f110` | préfixe 63 événements, 32 OPEN, 30 CLOSE ; sources rejets/admissions non incluses |
| O6-B | `410955659523d575b14445eebe7aad5525f73152c24e76f14294a015e383c768` | 32 packets/identités liés aux OPEN ; même boundary O4 |
| F00 historique | `4ea633a6a4e2ee0bc01a6fe855526d7c42451883ec0b6f3914cf21ea8e91cc8b` | référence du contrat RL-REPLAY, pas baseline courante |

Boundary O4 : `d60d1b73e48d2ff567e62469b96df0799c9711ffc90bd3f24697f17b5d6ac78e`.
Des IDs documentés ne prouvent ni disponibilité locale, ni dataset final.

## Lacunes et risques architecturaux

Absence de population complète de décisions/rejets/admissions et de trajectoires
multi-actifs synchronisées, spread/profondeur, marks, financement éventuel et
régimes causalement datés. Augmenter le cap ne permet donc pas de connaître les
trades supplémentaires. Modifier le timeout nécessite les prix intermédiaires,
la priorité TP/SL/timeout et les règles de récupération. Les mêmes trades resizés
ne recréent pas les admissions dépendantes du cash. Plus de notionnel ne crée pas
plus d’observations indépendantes.

Les corrélations par défaut PortfolioBrain ne sont pas estimées sur cette
population. Les coûts constants MEXC_SIM ne certifient aucune liquidité réelle.
FIN requiert un contexte sémantique explicite ; aucune réconciliation actuelle
n’est dérivée d’une projection ancienne. Le no-feedback applicatif n’est pas un
sandbox OS contre un opérateur ou un appelant malveillant.

## Plan minimal retenu

Ajouter `research_stress/` (contrat, enveloppes analytiques, intégration replay,
CLI stdout), protocole JSON versionné, cinq rapports et tests isolés.
Aucun second moteur de stratégie. Les facteurs non reconstruisibles restent
INSUFFICIENT_EVIDENCE. Le moteur contrefactuel de trajectoires est différé jusqu’à
admission des données et protocole d’exécution distinct ; il ne serait pas
scientifiquement validable sur les données disponibles.
