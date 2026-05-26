# Inventaire de surete des modules

Derniere mise a jour : 2026-05-26

Ce document resume l'etat reel du depot avant la suite P7. Il ne remplace pas
`ARBORESCENCE.md` : il explique a quoi servent les blocs, ce qu'ils apportent,
et ou ils peuvent devenir vulnerables si on ne les surveille pas.

## Etat realise

| Zone | Etat | Notes |
|---|---|---|
| P1-P5 operational | Fait | Signal, scanner, paper trading, portfolio/risk brain, dashboards et logs sont presents. |
| P6 adaptive core | Fait / cable | Regime classifier, seuil adaptatif, regret loop, smoother et activity tracker sont presents dans `advisor_loop.py`. |
| P7 risk regulation | En cours avance | `RiskGovernor`, `CapitalThrottle`, `DynamicExposureManager` et `ComponentCircuitBreaker` existent avec tests dedies. |
| Gouvernance DecisionPacket | En cours | Le flux packet trace les rejets, mais les formats de regimes restent une zone sensible. |
| Documentation racine | A nettoyer en continu | Plusieurs rapports existent, mais README/roadmap doivent rester synchronises. |

## Problemes traites le 2026-05-26

| Probleme | Correction |
|---|---|
| Blacklist de regime fragile entre `flash_crash` et `VOLATILE` | Normalisation dans `GlobalRiskGate` pour les APIs legacy et `DecisionPacket`. |
| Volatilite absente interpretee comme volatilite calme | `RiskGovernor` ne sort plus de `RISK_OFF` et ne passe plus `AGGRESSIVE` seulement parce que l'ATR manque. |
| Circuit breaker `UNSTABLE` continuait a appeler le composant pendant le backoff | `ComponentCircuitBreaker` retourne maintenant le fallback jusqu'a expiration du backoff. |
| Pas de verdict central contre les pannes silencieuses | Ajout de `system.safety_auditor.SystemSafetyAuditor` et integration dans `advisor_loop.py`. |
| Liens README visibles casses / placeholders GitHub | Liens corriges vers `docs/...` et badges remplaces par `0xl1v/crypto-ai-terminal`. |

## Inventaire par module

| Module | A quoi il sert | Avantage systeme | Vulnerabilite principale | Controle recommande |
|---|---|---|---|---|
| `advisor_loop.py` | Boucle live/advisor multi-symboles. | Point d'orchestration concret entre perception, risque, execution et notifications. | Fichier tres dense, beaucoup de `try/except` non bloquants peuvent masquer une couche indisponible. | `SystemSafetyAuditor` est cable; surveiller son verdict et router les exceptions critiques. |
| `quant_hedge_ai/main_v91.py` | Pipeline V9.1 autonome de recherche/trading. | Chemin principal historique, utile pour tests de bout en bout. | Peut diverger de `advisor_loop.py` si les protections evoluent dans un seul flux. | Garder des tests communs risk/packet et documenter le flux actif. |
| `core/decision_packet.py` | Contrat canonique d'une decision. | Trace chaque transition et rend les rejets auditables. | Toute couche qui contourne `transition_to()` casse la causalite. | Tests de transitions et revue stricte des mutations directes. |
| `quant_hedge_ai/agents/execution/` | Signaux live, execution, paper trading, replay et postmortem. | Transforme les signaux en actions et apprend des trades. | Risque le plus couteux : ordre envoye mal size, duplique ou en regime interdit. | Gate, deduplicateur, logger, replay et tests de non-execution. |
| `quant_hedge_ai/agents/risk/` | Gate global, sizing, drawdown, session, portfolio brain. | Premiere barriere avant capital. | Contrats implicites sur regimes, score et sizing advisory/final. | Normalisation des regimes, tests `DecisionPacket`, `SafetyAuditor`. |
| `risk_governor.py` | Machine d'etats P7 : normal, defensive, risk_off, recovery, aggressive. | Change le comportement global selon drawdown, pertes et volatilite. | Une donnee absente peut etre mal lue comme signal de securite. | Ne jamais traiter une metrique manquante comme "OK"; tests par etat. |
| `capital_throttle.py` | Reduit la taille selon drawdown capital. | Coupe le risque progressivement sans arret brutal inutile. | Depend d'un peak capital fiable; mauvais capital = mauvais facteur. | Synchroniser le capital live et auditer `snapshot()`. |
| `exposure_manager.py` | Borne l'exposition totale selon l'etat de risque. | Evite l'accumulation de positions en mode degrade. | `exposure_used` peut deriver si les positions ne sont pas resynchronisees. | Appeler `sync_from_positions()` a chaque cycle. |
| `quant_hedge_ai/agents/intelligence/` | Conviction, regime, regret, no-trade, alertes, self-awareness. | Apporte le contexte et les veto intelligents. | Peut devenir gouvernance cachee si un module bloque sans passer par le gate. | Les avis doivent rester metadata/advisory, les rejets dans `GlobalRiskGate`. |
| `quant_hedge_ai/agents/market/` | OHLCV, scanners, orderflow, retry, microstructure. | Perception marche et qualite de donnees. | Donnees manquantes ou stale peuvent creer de faux signaux. | Validateurs OHLCV, retry policy, heartbeat scanner. |
| `quant_hedge_ai/features/` | Feature store, registry, materializer, validator. | Stabilise les donnees ML et backtest. | Drift schema/feature silencieux. | Validation schema et versionning des features. |
| `quant_hedge_ai/strategy_factory/` | Generation, backtest et ranking de strategies. | Produit des candidats et de la diversite. | Sur-optimisation et strategies toxiques en regime rare. | Probation, walk-forward, blacklist par regime. |
| `quant_hedge_ai/strategy_lab/` | Laboratoire batch, DB, cache, evolution. | Teste beaucoup d'hypotheses rapidement. | Tests et caches peuvent se melanger aux resultats live. | Sorties isolees et min trades par regime. |
| `tracker_system/` | Suivi trade, sorties, backtest, analytics, meta memory. | Donne la boucle apprentissage post-trade. | Schemas trade/regime multiples. | Maintenir `TRADE_EVENT_SCHEMA.md` et tests schema. |
| `meta_learning/` | Memoire, similarite, learner, decision engine. | Reutilise les contextes gagnants. | Memoire biaisee si les trades sont trop peu nombreux. | Seuil min echantillons et audit par regime. |
| `execution_simulator/` | Simulation slippage, latency, fills. | Teste l'execution avant capital reel. | Modele faux si le marche change. | Comparer fills simules vs fills reels. |
| `exchange_constraints/` | Precision, tailles min, rate limiter, rules Binance. | Evite des ordres invalides. | Regles exchange changent avec le temps. | Verification periodique et testnet. |
| `supervision/` | Bot doctor, kill switch, watchdog, notifications, circuit breaker. | Couche operateur et auto-healing. | Notification ou fallback peut echouer sans bloquer le flux. | Circuit breakers + ErrorBus + alertes multi-canal. |
| `system/` | Kernel, registry, state machine, runtime controller, safety auditor. | Verite runtime centralisee. | Si les modules ne s'enregistrent pas, le health score est incomplet. | Rendre l'enregistrement obligatoire pour modules critiques. |
| `observability/` | Heartbeats, JSON logs, metrics, topology. | Rend les pannes visibles. | Si les exceptions sont swallow sans `ErrorBus`, les metriques mentent. | Interdire `except: pass` sur flux critique. |
| `errors/` | ErrorBus et incident manager. | Centralise exceptions, severite et panic threshold. | Pas utile si les modules ne l'utilisent pas. | Router les exceptions critiques dans `error_bus.emit()`. |
| `event_bus/` | Bus evenements et ponts. | Decouple alerts, audit et dashboards. | Perte d'evenement si emission silencieuse. | Logs d'emission et tests d'integration. |
| `audit/` | Trace decisions, replay, audit trades. | Explique le "pourquoi" d'une decision. | Incomplet si le flux contourne `DecisionPacket`. | Rejouer les rejets et executions regulierement. |
| `dashboard/` et `quant_hedge_ai/dashboard/` | Dashboards Streamlit/Panel/API. | Visibilite operateur. | Peut afficher un etat stale comme s'il etait live. | Horodatage, heartbeat UI, badge data freshness. |
| `databases/`, `logs/`, `cache/`, `checkpoints/` | Persistance runtime et resultats. | Reprise et audit. | Fichiers modifies par execution, risque de bruit git et corruption partielle. | Ignorer le runtime non source, backups atomiques. |
| `scripts/` | Runners, validateurs, migrations, demos. | Accelere operations et QA. | Scripts `test_*.py` ou validateurs manuels peuvent perturber pytest. | Conserver les tests dans `tests/`, scripts manuels hors pattern. |
| `tests/` | Couverture unit/integration/e2e. | Filet de securite avant P7+. | Environnement Python local casse bloque la validation. | Restaurer Python 3.11/.venv puis relancer tests P6/P7/risk. |
| `mvp/` | Prototype simplifie de pipeline trading. | Reference pedagogique et fallback conceptuel. | Peut diverger du systeme principal. | Ne pas le traiter comme source de verite live. |
| `pieuvre/` | Architecture experimentale tentaculaire. | Exploration supervision/evolution. | Risque de doublon avec `system/` et `supervision/`. | Garder experimental tant que non cable au flux principal. |
| `lm_studio/` | Client et routage IA locale. | Option IA locale. | Service externe local indisponible. | Fallback propre et statut explicite. |
| `deploy/`, `k8s/`, `install/` | Deploiement et setup. | Reproductibilite operationnelle. | Scripts peuvent etre obsoletes par rapport au code. | Smoke test apres installation. |
| `docs/`, `tickets/`, `project_os/` | Pilotage, dette, documentation, tickets. | Reprise rapide du contexte. | Documentation abondante mais parfois contradictoire. | Mettre a jour `CURRENT_TASK.md`, `BUGS.md`, `ROADMAP.md` a chaque passe. |
| `quant_hedge_ai/_legacy/` et archives | Modules conserves pour reference. | Recuperation possible d'idees anciennes. | Import accidentel de code archive. | Exclure de la prod et des tests standards. |

## Couche de surete ajoutee

`system.safety_auditor.SystemSafetyAuditor` lit :

- `system.module_registry` pour les statuts et heartbeats runtime.
- `observability.heartbeat_system` si fourni.
- `supervision.circuit_breaker_robust` si son registre est fourni.

Il retourne un `SafetyVerdict` :

- `normal` : aucun probleme.
- `degraded` : probleme non critique, pas de blocage obligatoire.
- `risk_off` : module critique manquant/degrade, ou circuit breaker critique degrade/desactive.

Usage recommande dans P7 :

```python
from system.safety_auditor import SystemSafetyAuditor

auditor = SystemSafetyAuditor(
    required_modules={"global_risk_gate", "execution_engine", "risk_governor"},
    critical_modules={"global_risk_gate", "execution_engine", "risk_governor"},
)
verdict = auditor.inspect()
if verdict.block_new_trades:
    # Ne pas ouvrir de nouvelles positions.
    ...
```

## Priorites avant suite P7

1. Restaurer l'environnement Python local : la `.venv` pointe vers un Python 3.11 absent.
2. Relancer `tests/test_p7_validation.py`, `tests/test_global_risk_gate.py`, `tests/test_safety_auditor.py`.
3. Verifier en dry-run que `SystemSafetyAuditor` bloque bien les nouvelles positions si `risk_governor` devient indisponible.
4. Remplacer progressivement les `except Exception: pass` sur flux critique par `error_bus.emit()`.
5. Continuer la consolidation des formats de regime vers un contrat unique.
