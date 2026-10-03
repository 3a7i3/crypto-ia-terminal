# Inventaire Machine / Laboratoire / surfaces historiques

2026-10-02 · #338 · base U4 fusionnée `de8281f3fa2a7994e2836b4139cc8457d389030a`.
SOURCE ONLY, #286 ACTIVE. Aucun accès VPS ni certification de disponibilité réelle.

## Couverture et portée

Index AST de **913 fichiers Python suivis**, **8 342 déclarations** classe/fonction/
fonction async, zéro erreur de parsing, hors tests et `_ARCHIVE_2026` :
[APP_UNIFY_SOURCE_FUNCTION_INDEX.csv](APP_UNIFY_SOURCE_FUNCTION_INDEX.csv).
Le CSV contient uniquement chemin, ligne, nom qualifié et type ; aucun secret ou
contenu de configuration. Il est une photographie structurelle de cette base,
pas une revue sémantique exhaustive de 8 342 fonctions, ni un inventaire runtime.
Les modules sans déclaration (constantes/imports) ne figurent pas dans le CSV.
Le nouveau domaine `ResearchStrategyBoardSnapshot` de #338 apparaît après cette
base : adaptation passive des candidats/évaluations admis et des verdicts/rangs
prépubliés. Son contrat indépendant est décrit dans
[APP_UNIFY_RESEARCH_STRATEGY_BOARD_CONTRACT.md](../contracts/APP_UNIFY_RESEARCH_STRATEGY_BOARD_CONTRACT.md).
Il ne prouve pas l'activité runtime du registre ni l'admission de résultats réels.
Les lignes « source uniquement » ci-dessous nécessitent leur propre preuve de
producteur/consommateurs et d'alimentation avant présentation de résultats.

## Matrice des capacités

| Capacité | Source / autorité | App / destination | État source et suite |
|---|---|---|---|
| État Advisor / décision courante | `core/advisor_loop.py`, snapshot canonique | Machine · Vue générale / Direction | projection existante ; runtime non recertifié |
| Service Advisor | `observability/runtime_service_snapshot.py` | Machine · Système / Direction | U2b, observation bornée à la capture |
| Coordination / cycle de vie | `runtime/` | Machine · Système | source indexée ; ne pas confondre présence et activation |
| Portefeuille / positions | `paper_trading/`, snapshot ObservedValue | Machine · Portefeuille | existant, isolé de comptes réels |
| PPL événements et lifecycle | `paper_trading/ledger_events.py`, readers | Machine · Lifecycle / Événements | existant ; sources exactes et pas de reconstruction financière UI |
| Comparaison legacy/PPL | `observability/ppl_comparison.py` | Machine · Lifecycle | existant ; comparabilité et valeurs originales conservées |
| Finance / equity / frais | `financial_institute/`, FIN-02 | Machine · Finance | existant ; préciser l'affichage decimal sans changer la valeur |
| Réconciliation | `observability/financial_reconciliation.py` | Machine · Finance / Direction | existant ; statut source, pas d'auto-correction |
| Burn-in / epoch / populations | `observability/burn_in_status_snapshot.py` | Machine · Burn-in / Direction | U2 ; aucune mutation d'epoch |
| Checkpoints / dataset final | `research_data/burn_in_finalization.py` | Machine · preuves ; Lab · dataset | disponibilité dépend de preuves admises ; jamais inférée |
| Décisions / blocages | `core/decision_packet.py`, snapshot | Machine · Décisions | existant ; niveaux/permissions réservés à ce domaine |
| Signal / conviction | `quant_hedge_ai/agents/execution/` | Machine · Décisions | source indexée ; valeurs uniquement via projection exacte |
| Risque / contraintes | `risk/`, `exchange_constraints/`, governance gates | Machine · blocages ; Lab · critères | sources indexées ; aucun câblage/config/sizing modifié |
| Execution / simulation | `execution_simulator/`, `paper_trading/` | Machine · état ; Lab · expérience identifiée | pas de mélange simulation, PAPER et résultats réels |
| Marché / collecte / régimes | `market_data/`, `quant_hedge_ai/agents/market/` | Machine · CryptoRadar | agrégats sûrs existants ; contextes supplémentaires à qualifier |
| Scanner / classement symboles | `observability/market_radar_snapshot.py` | Machine · CryptoRadar | U3a : top50, recherche, filtres, détail ; couverture partielle explicite |
| Microstructure LMI | `trade_analysis/integrations/dashboard_adapter.py`, snapshot U3b | Machine · CryptoRadar | projection passive déjà intégrée |
| Events LMI historiques | `/api/lmi/events`, adapter | Machine · CryptoRadar | ancienne route filtre les **états actuels** notables ; aucun journal temporel certifié trouvé |
| Détail LMI complet | `/api/lmi/symbol/{symbol}` | Machine · détail Microstructure | core metrics intégrées ; `state_components`/raw/liq détaillée restent à contractualiser |
| Horizon / observer / radar secondaires | `scripts/systemd/crypto-market-*.service`, producers | Machine · Marché / Système | unités source existantes ; dépendances/consommateurs runtime non recertifiés |
| Volumes filesystem DecisionPacket | ancien `/api/status` | Machine · Système / Stockage | projection storage manquante ; ne pas placer dans Market |
| Replay factuel | `research_replay/` | Lab · Évaluations | publication immutable + U4 ; moteur jamais lancé par l'app |
| Diagnostic / attribution | `research_diag/` | Lab · Évaluations / détails | aggregates publiés via U4, contraintes scientifiques conservées |
| Catalogue candidate | `research_candidate/registry.py` | Lab · Stratégies/candidats | contrats/publisher existants ; raccordement présentation à construire |
| Identités / résultats candidate | `research_candidate/candidate.py` | Lab · fiche / critères | validateur pur ; consommation explicite d'artifacts évalués |
| Strategy Lab génération/backtest | `quant_hedge_ai/strategy_lab/` | Lab · expériences | source uniquement ; exemples de scoring non financiers exclus des classements admis |
| Factory / évolution | `quant_hedge_ai/strategy_factory/`, `ai_evolution/` | Lab · développement / lineage | données/évaluations à admettre ; aucun lancement d'optimisation |
| Stratégies primitives | `src/agent/`, `signal/strategies/` | Lab · catalogue après identité | code présent ≠ stratégie active ou performance certifiée |
| Ranker / mémoire / meta stratégie | `quant_hedge_ai/ai_evolution/`, `agents/intelligence/` | Lab · ranking qualifié ; Machine · contexte | ADR-0014 historique ; alimentation actuelle non recertifiée, pas de raccordement runtime |
| Walk-forward / validation | `walk_forward/`, `certification/`, `reality_checks/` | Lab · validation | protocole/population/provenance nécessaires, pas de vert depuis présence d'un fichier |
| Analyse trades / postmortem | `trade_analysis/`, `analysis/` | Lab · diagnostics ; Machine · historique | canoniser provenance avant migration complémentaire |
| DIP / contre-factuel | `dip/` | Lab · protocole identifié | absence de trajectoire marché ne doit pas devenir simulation fictive |
| Santé / monitoring / profiler | `health/`, `monitoring/`, `monitor/` | Machine · Système | existant partiel ; sélectionner des métriques sourcées |
| Supervision / watchdog | `supervision/`, `watchdog_vps.py` | Machine · Santé | source uniquement pour état non projeté ; aucun restart/action |
| Trading authority / gouvernance | `governance/`, `observability/operator_decision*` | Machine · Direction / décisions | #315 Gate O OPEN ; aucune queue opérationnelle inventée |
| Capital deployment | `capital_deployment/` | Lab · propositions ; Machine · état admis | commandes non exposées ; scope runtime séparé |
| Mémoire / meta-learning / knowledge | `meta_learning/`, `quant_hedge_ai/`, `pieuvre/` | Lab · preuve/contextes | source indexée ; qualification et preuve d'alimentation nécessaires |
| Tracker / rapports | `tracker_system/`, `reports/`, `metrics/` | App · historique / preuve après mapping | multiples sorties legacy ; pas d'autorité déduite du nom |
| Visualisations / anciens panels | `visualization/`, `infra/visualization/`, `dashboard/` | Lab ou Machine selon autorité | transport à remplacer après parité ; aucune suppression ici |
| Terminal / interfaces anciennes | `terminal_core/`, `sdos_terminal/`, `src/` | App · fonctions utiles après qualification | code/transport legacy, non preuve d'exécution VPS |
| LM Studio / recherche IA | `lm_studio/`, `agents/research/` | Lab · expériences admises | aucune requête IA / accès provider nécessaire à cette migration |

## CryptoRadar : transfert des fonctions et pas du transport

| Route historique | Fonction | App / décision |
|---|---|---|
| `/api/scan` | Scanner | U3a, intégré ; données live à recertifier séparément |
| `/api/symbol/{symbol}` | détail agrégats symbole | détail safe U3a ; LONG/SHORT exacts non publiés |
| `/api/signals` | niveaux Entry/SL/TP/R historiques | domaine Decisions/Portfolio, pas une permission de trade dans Market |
| `/api/status` | derniers packets + taille/fichiers | population/fraîcheur Market existantes ; stockage requiert une projection System |
| `/api/lmi/status` | couverture/état | U3b intégré |
| `/api/lmi/table` | métriques microstructure | U3b intégré |
| `/api/lmi/symbol/{symbol}` | détail complet | metrics intégrées, champs raw non repris aveuglément |
| `/api/lmi/events` | état notable actuel filtré | U3b observations notables à la capture ; pas d'historique inventé |
| `/`, login/cookie standalone | interface/transport | remplacés par l'app après parité, preuves consommateurs et rollback |

## Sorties et consommateurs à consolider

| Sortie | Point de source | Consommateurs connus en source | Cible / condition |
|---|---|---|---|
| Operator API/app | `observability/operator_api/app.py`, `frontend/` | app React | surface opérateur unique cible |
| CryptoRadar standalone | `scripts/dashboard_api.py`, `crypto-dashboard.service` | navigateur ; dépendants API non recertifiés | retrait seulement après parité/consommateurs/rollback/gate |
| Telegram | `core/advisor_loop.py` helpers `_telegram*`, `_send_intel`, `scripts/telegram_alerts.py` | humains / canaux configurés | exporter les faits vers projections ; pas de redirection d'envoi dans ce chantier |
| Email | `_send_email` | destinataires configurés | alerte app après contrat ; aucune adresse/clé lue dans l'inventaire |
| Dashboards Streamlit/anciens scripts | launchers + `dashboard/`, `visualization/`, `src/` | consultation opérateur, usages non prouvés | qualifier/migrer avant fermeture |
| Rapports/KPI tracker | `tracker_system/`, `scripts/`, `reports/` | panels/fichiers/audits | données utiles admises dans app, preuves internes conservées |
| JSONL PPL/DecisionPacket | producteurs métier | Replay/Diag/projections/audits | conserver preuves, jamais lecture frontend directe |
| Artifacts Research et snapshots | Research/projections | API, tests, certification | conserver sources exactes et formats internes |
| Logs/sauvegardes | runtime/observability | forensic/reprise | conserver ; ne pas confondre avec une UI concurrente |

## Résultat / limites

Deux espaces visuels ne fusionnent pas les autorités ni les comptes. Aucun
classement financier depuis un score de démonstration. Les producteurs continuent
à porter les calculs ; le frontend présente les faits et les limites.

Le catalogue Research, la politique de verdicts des critères, les cohortes de
classement et leurs preuves doivent être **publiés explicitement** ; aucun
`latest` implicite, classement depuis le nom d'un module ou pipeline autonome
lancé au clic. Le tableau peut être livré en source avec état indisponible
honnête tant que les artifacts réels ne sont pas publiés.

Restent des chantiers de preuve/producer distincts : stockage, liq/raw LMI
contractualisés, consommateurs des anciens transports, sources KPI historiques
et Gate O. Cette matrice interdit de les présenter comme déjà déployés/résolus.

## Revue application et consolidation — 2026-10-03

Demande opérateur : reprise des issues, tests de l'app et de ses sorties, ménage
source sans toucher au burn-in. Branche locale `audit/app-coherence-cleanup`,
base examinée `385b8c9cdd4f0f67fd58898ba18f6a37b5e308a4`.
Ce complément conserve la photographie U4 ci-dessus et utilise cet inventaire
existant comme liste de travail, sans créer de nouveau rapport concurrent.

### Reprise et cohérence roadmap

Corpus récupéré : 109 issues distinctes du dépôt et 858 commentaires, par
recherches ascendante/descendante (limite 100 par appel) et complément récent.
Il ne certifie pas l'exhaustivité de l'historique GitHub ni toutes les discussions
de PR. Les dispositions finales priment sur les anciens blocs/commentaires.

| Mission | Dernière disposition consultée | Conséquence |
|---|---|---|
| #285 / #323 | app unique prioritaire, burn-in protégé | visibilité et consolidation source |
| #338 / #339 | Machine/Lab intégré en source | aucune preuve de déploiement induite |
| #340 / #341 | façade documentaire intégrée | ancien pointeur CURRENT_TASK à remplacer |
| #342 / #343 | préparation U8 intégrée, NOT_AUTHORIZED | publication/appareil sous gates G0–G8 séparées |
| #257 / #344 / #346 | sécurité remédiée | ancien total de vulnérabilités dépassé ; audit frais local à zéro |
| #315 | Gate S accepté, Gate O ouvert | queue/actions opérationnelles encore bloquées |
| #287 / #309 | forensic et observation runtime historique terminées | réobserver les consommateurs avant retrait |
| #349 / #350–#355 / #207 | triage intégré, reliquats distincts | rapport PASS ne signifie pas défauts corrigés |
| #209 / #284 | orchestration legacy différée / économie contractuelle | ne pas ajouter de couplage au cockpit courant |

Exemples de bruit administratif : les premiers commentaires de #342 décrivent
encore une PR Draft non fusionnée et une sécurité bloquante, alors que son corps
consigne la préparation intégrée après remédiation. #257 a connu plusieurs
dispositions successives. Ne pas utiliser un commentaire ancien comme état actuel.

### Faiblesses et ordre utile

| Priorité | Constat vérifié | Action suivante |
|---|---|---|
| 1 | source intégrée ≠ sorties réellement servies ; accès machine absent ici | vérifier endpoints, build et provenance en lecture seule |
| 2 | Events était statique à la base de cette revue | APP-EVENTS-01 #361 : contrat et chaîne passive implémentés en source ; publication runtime distincte, notifications conservées |
| 2 | détail LMI raw/liq et projection stockage manquants dans la matrice | terminer les projections utiles avant retrait CryptoRadar |
| 2 | grille Research source disponible, résultats réels non admis par cette tranche | sélectionner explicitement évaluations et assessments certifiés |
| 3 | index documentaire prétendait être source unique/live avec chiffres de mai | entrée canonique et limites historiques clarifiées, générateur corrigé |
| 3 | CURRENT_TASK pointait #340 déjà intégrée | reprise actuelle et reliquats explicités |
| différée | Scores, queue Direction, économie et orchestration legacy | garder indisponible/différé jusqu'aux contrats et gates applicables |

### Classification pour le ménage

Une classification source n'établit pas l'absence de consommateurs runtime.
L'observation de dormance dans #309 est historique, pas une preuve de retrait actuel.

| Surface / fichiers | Classification de cette revue | Disposition |
|---|---|---|
| `frontend/`, Operator API, projections gouvernées | KEEP | chaîne canonique testée |
| index, générateur documentaire, CURRENT_TASK | KEEP | affirmations périmées supprimées et reprise clarifiée |
| fonctions de `scripts/dashboard_api.py` | INTEGRATE | compléter la parité utile ; transport conservé |
| transports CryptoRadar/Telegram/email | UNKNOWN pour retrait actuel | consommateurs, parité et rollback à réobserver |
| `sdos_terminal/`, `infra/api/api_server.py`, `governance/status_dashboard.py` | UNKNOWN pour retrait actuel | présence/dormance historique connue, usages contemporains non vérifiés |
| launchers Windows/panels, `core/orchestration/orchestrate_*` | UNKNOWN pour déplacement/retrait | #209 recense des entrées manquantes ; certains panels ont encore des importeurs/tests |
| README_CONSOLIDATED, anciens Quick Starts, rapports racine | ARCHIVE au sens documentaire, emplacements conservés | références source/docs encore présentes ; déplacement aveugle exclu |
| `src/telegram/exchange_sync.py` | RETIRE candidat source hérité de #287 | hors app ; aucun retrait dans cette tranche |
| PPL/DecisionPacket JSONL, datasets, logs, sauvegardes | KEEP | preuves scientifiques/reprise |

Ménage réalisé : clarification des entrées de travail et de l'autorité des
documents, sans suppression de fichier métier ou historique ni interruption de
service. Les références restent consultables. La taille d'un dossier ou l'absence
d'import statique ne suffit pas à prouver qu'il est inutilisé.

### Suite APP-EVENTS-01 — #361

Depuis la base source `7d7b29669f9940f5e7e47b5b1c7d88371f067fbb`, le
[contrat Events](../contracts/APP_EVENTS_01_CONTRACT.md) cadre trois sources
explicitement sélectionnées : P12, audit supervision et projection lifecycle U2.
Capture passive atomique → artifact → GET `/api/operator/v1/events` → vue
indépendante `/paper-live/events`. UNKNOWN, source absente, source invalide,
capture vide et données périmées restent distincts. Les corrections supervision
restent comptées comme exclusions ; aucune activité moteur déduite des journaux.

Validation locale synthétique : 389 tests frontend, 526 tests Python de la chaîne
et surfaces voisines, puis 22 tests Events finaux ; build, 7 contrôles PWA et
Ruff sans nouvelle violation. 16 captures Chromium 1440/390 couvrent sources,
filtres, erreurs, provenance et overflow. Cette preuve ne certifie aucun
endpoint ou producteur déployé. Pas de nouvelle workflow concurrente : le gate
cross-stack existant porte aussi la preuve visuelle Events.

### Vérification locale

Python 3.12.14 / Node 24.19.0, distincts de la CI Python 3.11 / Node 20.
Données synthétiques produites via les vrais producteurs/publishers/readers/API ;
aucun dataset Machine réel ouvert.

| Vérification | Résultat observé |
|---|---|
| Build TypeScript/Vite | PASS |
| Transport/PWA | 7 PASS |
| Vitest avec onze générateurs cross-stack | 376 PASS, zéro skip |
| `tests/cross_stack/` + `tests/observability/` | 298 PASS |
| API, FIN/PPL, burn-in/runtime-service/microstructure/U4 ciblés | 337 PASS |
| U6 Chromium 1440/820/390, deux espaces, critères, exact FIN, erreurs et GET-only | PASS |
| npm audit avant ajout de l'outil visuel | zéro vulnérabilité |
| Ruff baseline 0.15.8 | 947 findings existants, zéro nouvelle violation |
| Générateur documentaire | entrée canonique et rapports locaux distincts PASS |

Le premier Vitest sans fixtures avait 351 PASS / 25 skips : remplacé par le
passage complet. Avertissements existants : config Vite ESM chargée comme
CommonJS, dépréciation Starlette/httpx. Aucun baseline/gate/test affaibli.
Ces vérifications ciblées ne certifient pas le corpus CI complet, U7 ou le runtime.
Les captures et logs de cette session se trouvent hors des sources dans
`/workspace/scratch/app-visual/` et `/workspace/scratch/app-*.log` ; les issues
récupérées dans `/workspace/scratch/issues-review.json`. Ces chemins de session
ne sont pas des artifacts scientifiques durables ni des publications admises.

Aucune machine Desktop Commander connectée, aucune identité SSH/VPN configurée
dans cet environnement. L'accès read-only a été demandé à l'opérateur. Les sorties
déployées et le fonctionnement courant du burn-in restent **non réobservés**.
#286 reste actif ; aucun changement runtime/Advisor/PPL/FIN/config/epoch/services.
