# APP-UNIFY-01-U0 — Contrat de données et matrice de parité

Issue : #324  
Parent : #323  
Roadmap : #285  
Burn-in : #282  
Freeze : #286  
Baseline source auditée : `fa3a6167bc3fb2efcba6284f95de26f0872d7fa0`  
Date : 2026-10-01

## 1. Verdict de l'audit

L'Operator App dispose déjà d'une base fonctionnelle importante. Le problème
principal n'est pas l'absence d'interface, mais l'absence de certaines
**projections gouvernées** permettant de remplacer les inspections VPS
manuelles.

Architecture à préserver :

```text
PRODUCTEUR GOUVERNÉ
        ↓
ARTIFACT / SNAPSHOT ATOMIQUE
        ↓
OPERATOR API GET-ONLY
        ↓
VALIDATION FRONTEND
        ↓
OPERATOR APP
```

Interdit :

```text
React → JSONL / database / systemd / exchange / calcul scientifique
```

Verdict U0 :

`APP_UNIFY_U0_DATA_PARITY_CONTRACT_READY`

Ce verdict est documentaire/source-only. Il n'autorise aucun déploiement,
restart, activation FIN-02, modification de l'Advisor, ni retrait de
CryptoRadar.

---

## 2. Surfaces existantes

### 2.1 Operator API

Routes GET-only déjà présentes :

- `/api/operator/v1/snapshot`
- `/api/operator/v1/portfolio`
- `/api/operator/v1/decision-pipeline`
- `/api/operator/v1/system-health`
- `/api/operator/v1/ppl-comparison`
- `/api/operator/v1/financial-reconciliation`
- `/api/operator/v1/market`
- `/api/operator/v1/research-lab`

### 2.2 Frontend

Routes produit déjà présentes :

- `/paper-live`
- `/direction`
- `/research`

Vues principales déjà disponibles :

- Overview ;
- Market ;
- Portfolio ;
- Decisions ;
- Lifecycle/PPL comparison ;
- Finance ;
- System ;
- Direction ;
- Research Lab.

### 2.3 Direction

`DirectionOverview.tsx` consomme déjà quatre familles indépendantes :

1. snapshot Advisor ;
2. FIN-02 ;
3. Market/CryptoRadar ;
4. Research Lab.

La page est correctement définie comme :

`FÉDÉRÉ · NON ATOMIQUE`.

Aucun état global synthétique ne doit être inventé.

---

## 3. Vocabulaire U0

| Statut | Sens |
|---|---|
| `DISPLAYED` | producteur + API + UI présents |
| `AVAILABLE_NOT_DISPLAYED` | la donnée existe dans un payload gouverné mais l'UI ne l'affiche pas |
| `SOURCE_AVAILABLE_RUNTIME_UNPROVEN` | chaîne source existe, disponibilité runtime courante non certifiée |
| `MISSING_PRODUCER` | aucune projection gouvernée appropriée n'existe |
| `NON_DEPLOYE` | capacité volontairement non déployée |
| `DO_NOT_MIGRATE` | donnée historique/ambiguë à ne pas recopier dans la nouvelle app |
| `DEFERRED` | utile mais hors première tranche |

---

## 4. Matrice de vérité — état machine

| Besoin opérateur | Producteur | Endpoint / champ | App actuelle | Statut U0 | Action |
|---|---|---|---|---|---|
| Mode PAPER/TESTNET/REAL | canonical operator snapshot | `snapshot.portfolio.mode` | Direction + Portfolio | DISPLAYED | conserver |
| Runtime snapshot courant/last-known | reader Operator | `snapshot.runtime_state` | Overview + Direction | DISPLAYED | conserver |
| Relation instance | reader Operator | `snapshot.instance_relation` | Overview + Direction | DISPLAYED | conserver |
| SHA runtime | operator snapshot | `snapshot.source_sha` + evidence status | Direction provenance | DISPLAYED | remonter plus lisiblement en U1 |
| Worktree runtime | operator snapshot | `snapshot.worktree_state` | Direction provenance | DISPLAYED | conserver |
| Fraîcheur snapshot | reader Operator | age + freshness | Overview + Direction | DISPLAYED | conserver |
| Santé modules | system_health | `module_statuses` | System | DISPLAYED | hiérarchiser |
| `boot_alive` Advisor | system_health | ObservedValue | System + Direction | DISPLAYED mais généralement UNKNOWN par contrat | ne jamais transformer en preuve systemd |
| Service Advisor réellement actif | aucun producteur opérateur gouverné | — | absent | MISSING_PRODUCER | futur snapshot host/runtime read-only |
| MainPID / NRestarts / ExecMainStart | aucun producteur App | — | absent | MISSING_PRODUCER | futur snapshot host/runtime read-only |
| Epoch active | FIN-02 / PPL comparison / Research | `paper_epoch_id` | Direction via FIN | SOURCE_AVAILABLE_RUNTIME_UNPROVEN | U2 doit disposer d'une source burn-in indépendante de FIN |
| Config hash actif | FIN-02 | `config_hash` | Direction provenance | SOURCE_AVAILABLE_RUNTIME_UNPROVEN | U2 : projection experiment/burn-in |
| Dernière activité machine | sources séparées | timestamps snapshot/Market | partiel | AVAILABLE_NOT_DISPLAYED / MISSING_PRODUCER pour dernier PPL | U1 + U2 |

### Conclusion A

L'app connaît déjà l'identité de son snapshot et une partie du runtime, mais
elle ne possède **aucune preuve gouvernée de liveness systemd de l'Advisor**.
`/healthz` prouve seulement que l'Operator API répond.

Pour atteindre l'objectif "ne plus ouvrir le VPS", une future projection
host/runtime read-only est nécessaire. Elle ne doit jamais être construite à
partir d'une inférence frontend.

---

## 5. Matrice de vérité — burn-in actif

| Besoin | Source actuelle | App | Statut U0 | Décision |
|---|---|---|---|---|
| `paper_epoch_id` | FIN-02 / PPL comparison / Research | partiel | SOURCE_AVAILABLE_RUNTIME_UNPROVEN | U2 |
| T0 / EPOCH_CREATED | PPL autoritaire | absent | MISSING_PRODUCER | U2 |
| event_count | PPL autoritaire | absent | MISSING_PRODUCER | U2 |
| last_sequence | FIN-02 transporte `last_source_sequence` | Finance seulement | AVAILABLE_NOT_DISPLAYED | U1 peut l'afficher si FIN disponible ; U2 doit l'exposer canoniquement |
| POSITION_OPENED | PPL autoritaire | absent comme compteur actif | MISSING_PRODUCER | U2 |
| POSITION_CLOSED | PPL autoritaire | FIN expose seulement `settled_position_count` | absent comme CLOSED exact | MISSING_PRODUCER | U2 ; ne jamais assimiler Settled à CLOSED |
| POSITION_UNRESOLVED | FIN-02 + PPL | Direction/Finance | partiel | SOURCE_AVAILABLE_RUNTIME_UNPROVEN | U2 |
| open positions courantes | canonical snapshot | Portfolio | DISPLAYED | réutiliser |
| détail positions | canonical snapshot | Portfolio | DISPLAYED | améliorer mobile |
| `opened_at` | canonical snapshot | payload présent, non affiché | AVAILABLE_NOT_DISPLAYED | U1/U2 |
| `timeout_at` / recovery deadline | PPL OPEN event | absent | MISSING_PRODUCER | U2 |
| âge/deadline state | aucune projection | absent | MISSING_PRODUCER | produire côté U2, pas dans React |
| dernier événement PPL | PPL autoritaire | absent comme fait actif canonique | MISSING_PRODUCER | U2 |
| source SHA burn-in | operator snapshot / FIN | partiel | DISPLAYED / SOURCE_AVAILABLE_RUNTIME_UNPROVEN | U1/U2 |
| config hash burn-in | FIN / config freeze | partiel | SOURCE_AVAILABLE_RUNTIME_UNPROVEN | U2 |
| PB hard limit | `portfolio_status` construit par operator snapshot | payload, non affiché | AVAILABLE_NOT_DISPLAYED | U1 |
| admission_state OPEN/SATURATED/OVER_LIMIT | `portfolio_status` | non affiché | AVAILABLE_NOT_DISPLAYED | U1 |
| positions par régime/personality | `portfolio_status` | non affiché | AVAILABLE_NOT_DISPLAYED | U1 secondaire |
| `PAPER_PORTFOLIO_BRAIN_LEVEL` | runtime config | absent | MISSING_PRODUCER | U2 depuis config gelée, pas env frontend |
| `MEXC_SIM_MAX_POSITION_USD` | runtime config | absent | MISSING_PRODUCER | U2 depuis config gelée |
| max age 8h | runtime config/PPL OPEN | absent | MISSING_PRODUCER | U2 |
| progression O1…O9 | preuves gouvernance #282 | absent | MISSING_PRODUCER | ne pas scraper/calculer dans React ; prévoir artifact de checkpoint gouverné |
| dernier checkpoint certifié | preuves #282 | absent | MISSING_PRODUCER | artifact de checkpoint gouverné |
| critères restants avant finalisation | #282/#286 | absent | MISSING_PRODUCER | présentation gouvernée, jamais heuristique |
| dataset final désigné | Research | non final aujourd'hui | NOT_AVAILABLE | rester explicite |

### Conclusion B

Le manque principal est un **BurnInStatusSnapshot** ou contrat équivalent,
produit hors frontend.

Il doit être passif et fail-closed et porter au minimum :

- epoch/config/source identity ;
- T0 ;
- event_count/last_sequence ;
- OPEN/CLOSED/UNRESOLVED ;
- dernier événement ;
- open lifecycles ;
- opened_at/timeout_at/recovery deadline ;
- admission configuration certifiée utile à l'opérateur ;
- provenance/freshness ;
- finalization state factuel.

Les verdicts O1…O9 sont des certifications de gouvernance, pas des métriques
runtime. Ils nécessitent un artifact de checkpoint explicitement publié ou
doivent rester hors de la vérité live.

---

## 6. Matrice de vérité — Finance

| Besoin | Producteur source | Endpoint | App | Statut |
|---|---|---|---|---|
| capital initial | FIN-02 | financial reconciliation | Finance/Direction partiel | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| cash disponible | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| réservé | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| déployé | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| unresolved | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| PnL réalisé | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| frais | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| equity certifiée | FIN-02 | idem | Finance | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| reconciliation | FIN-02 | idem | Finance/Direction | SOURCE_AVAILABLE_RUNTIME_UNPROVEN |
| last_source_sequence | FIN-02 | idem | Finance | DISPLAYED dans Finance / non remonté niveau 1 |

### Point de gouvernance

`FIN02_RUNTIME_ENABLED` est OFF par défaut et le burn-in a été activé avec
FIN-02 runtime OFF. #286 interdit une activation implicite.

U0 ne demande donc aucune activation.

Pour une App autonome à terme, deux voies seulement sont acceptables :

1. gate séparée pour activer le writer passif existant ;
2. producteur sidecar READ-ONLY séparé lisant la frontière PPL certifiée sans
   redémarrer/modifier l'Advisor.

Le choix appartient à une future mission de runtime proof.

---

## 7. Parité CryptoRadar standalone → Operator App

Le dashboard historique `scripts/dashboard_api.py` possède :

- Scanner ;
- Signaux ;
- Live Market / LMI ;
- status DecisionPacket ;
- détail symbole ;
- authentification/dashboard standalone.

### 7.1 Scanner

| Fonction standalone | Operator App actuelle | Classe U0 | Décision |
|---|---|---|---|
| classement symbole | `MarketView.top_opportunities` | DÉJÀ COUVERT PARTIELLEMENT | conserver |
| avg confidence | oui | DÉJÀ COUVERT | conserver |
| max confidence | oui | DÉJÀ COUVERT | conserver |
| dominant side | oui | DÉJÀ COUVERT | conserver |
| dominance % | oui | DÉJÀ COUVERT | conserver |
| nombre signaux | oui | DÉJÀ COUVERT | conserver |
| régime | oui | DÉJÀ COUVERT | conserver |
| filtre LONG/SHORT | non | AVAILABLE UI GAP | U3 |
| recherche symbole | non | AVAILABLE UI GAP | U3 |
| liste jusqu'à 50 / univers large | snapshot actuel top 20 | PRODUCER GAP | U3 : étendre projection safe |
| Entry/SL/TP | volontairement interdits par WEB-01 Market | DO_NOT_MIGRATE | ne pas remettre dans Market |

Le contrat WEB-01 interdit explicitement les champs d'exécution :
`entry/sl/tp/r_multiple/trade_allowed/is_actionable/order/position`.

Cette interdiction doit rester.

### 7.2 Onglet historique "Signaux"

Le standalone reconstruit :

- Entry ;
- Stop Loss ;
- Take Profit ;
- R:R ;
- risk_pct ;
- reward_pct ;
- confidence ;
- régime.

Cette vue est issue des DecisionPackets historiques et ressemble à une surface
d'exécution.

Verdict U0 :

`DO_NOT_MIGRATE_AS_MARKET_VIEW`.

Si l'opérateur a besoin de comprendre les décisions réelles de la machine,
utiliser/faire évoluer `PAPER LIVE / Decisions`, qui conserve déjà
`is_actionable`, `trade_allowed`, blocker, side, regime, lifecycle et
confidence avec leurs autorités exactes.

### 7.3 Détail symbole

Standalone :

- n_signals ;
- avg/max confidence ;
- longs/shorts ;
- dominant regime ;
- dernier signal avec Entry/SL/TP/R.

Classification :

- agrégats observationnels : utiles, mais projection actuelle incomplète ;
- niveaux Entry/SL/TP/R : DO_NOT_MIGRATE dans Market.

U3 pourra ajouter un drill-down observationnel safe sans niveaux d'exécution.

### 7.4 Status DecisionPackets

Standalone :

- packets_today ;
- last_packet ;
- dp_files ;
- dp_total_gb.

Parité :

- `last_packet` est largement remplacé par `market.source_updated_at_utc` ;
- volume de packets sur fenêtre : `packets_observed` ;
- `dp_files` / `dp_total_gb` relèvent de System/Storage, pas de Market.

Ne pas recopier les métriques filesystem dans Market.

### 7.5 Live Market / LMI

Le standalone expose une capacité utile non présente dans l'Operator App :

- état microstructure ;
- state confidence ;
- buy/sell pressure ;
- flow USD ;
- resistance ;
- fragility ;
- price ;
- freshness/stale ;
- couverture ;
- événements LMI.

Source :

`trade_analysis/integrations/dashboard_adapter.py` lisant
`lmi_live_state.json`.

Verdict :

`USEFUL_MISSING_PRODUCT_PROJECTION`.

Cette capacité doit migrer, mais pas par lecture directe du fichier depuis
React ou l'Operator API.

Cible U3 :

```text
LMI source
   ↓
MarketMicrostructureSnapshot atomique
   ↓
reader API strict GET-only
   ↓
PAPER LIVE / Marché · Microstructure
```

Le statut runtime courant de cette source doit être recertifié séparément avant
tout verdict LIVE.

### 7.6 Dashboard standalone lui-même

Éléments à ne pas migrer :

- serveur FastAPI standalone ;
- login/cookie propres au dashboard ;
- lecture directe DecisionPacket JSONL par le serveur dashboard ;
- HTML/CSS/JS monolithique ;
- routes d'exécution-shaped signal levels.

Le retrait futur concerne la **surface de transport**, pas les producteurs
métier utiles.

---

## 8. Matrice de vérité — Research

| Besoin | Schéma/UI | Production live | Statut U0 |
|---|---|---|---|
| dataset_id | présent | artifact attendu | UI_READY |
| source_boundary_id | présent | artifact attendu | UI_READY |
| paper_epoch_id | présent | artifact attendu | UI_READY |
| N / evidence strength | présent | artifact attendu | UI_READY |
| research_run_id | présent | artifact attendu | UI_READY |
| diagnostic_run_id | présent | artifact attendu | UI_READY |
| performance metrics | présent | artifact attendu | UI_READY |
| attribution | présent | artifact attendu | UI_READY |
| limitations | présent | artifact attendu | UI_READY |
| candidates | présent | artifact attendu | UI_READY |
| publication automatique depuis O7 | absente | absente | MISSING_PRODUCER |

Constat source :

`observability/research_lab_snapshot.py` fournit validation + publication
atomique d'un document déjà construit.

Aucun builder de production n'a été trouvé. Les appels au publisher sont
limités aux tests/fixtures.

Cible U4 :

```text
publication Research certifiée
        ↓
builder de présentation déterministe
        ↓
research_lab_snapshot.json
        ↓
/api/operator/v1/research-lab
        ↓
ResearchLabView / Direction
```

Aucun calcul scientifique ne doit être déplacé dans le builder.

---

## 9. Gouvernance, sécurité et dette

| Besoin | App actuelle | Statut |
|---|---|---|
| Freeze #286 | aucun producteur | NON_DEPLOYE |
| Gate O #315 | bloc placeholder seulement | NON_DEPLOYE |
| décisions opérateur réelles | aucun producteur opérationnel | NON_DEPLOYE |
| Agents/Bounties/AIC | placeholders honnêtes | NON_DEPLOYE |
| dette #202/#207/#208/#209/#257 | aucune projection consolidée | NON_DEPLOYE |
| incidents consolidés | aucune projection | NON_DEPLOYE |
| coûts réels consolidés | aucune projection | NON_DEPLOYE |

La première version de #323 doit continuer à afficher ces absences
explicitement plutôt que créer une fausse complétude.

Une future `GovernanceSnapshot` pourra être étudiée après U1–U4.

---

## 10. Données déjà disponibles mais sous-utilisées

Priorité U1, sans nouveau moteur métier :

### Operator snapshot

- `source_sha` ;
- `worktree_state` ;
- `runtime_sha_evidence_status` ;
- `open_positions` ;
- `open_positions[].opened_at` ;
- `portfolio_status.current_positions` ;
- `portfolio_status.hard_position_limit` ;
- `portfolio_status.admission_state` ;
- positions par régime/personality ;
- decision blockers et autorités.

### FIN-02

Lorsque son artifact est disponible :

- `last_source_sequence` ;
- source/config identities ;
- counts ;
- capital/frais/PnL ;
- reconciliation.

### Market

- `source_updated_at_utc` ;
- universe ;
- actionable/watchlist ;
- top opportunity rows ;
- freshness.

### Research

L'UI est déjà suffisamment riche ; le manque est essentiellement le builder
de présentation de production.

---

## 11. Modifications produit proposées

### U1 — Vue Propriétaire lisible

Fichiers principaux :

- `frontend/src/views/DirectionOverview.tsx`
- `frontend/src/types.ts`
- `frontend/src/operator.css`
- tests Direction.

Objectif :

- remonter mode, source/runtime evidence, position count/limit,
  admission_state et dernière fraîcheur ;
- rendre le portefeuille et ses limites compréhensibles en quelques secondes ;
- conserver les détails SHA/provenance repliables ;
- ne créer aucun nouveau calcul scientifique.

U1 peut utiliser uniquement des champs déjà présents.

### U2 — BurnInStatusSnapshot

Nouveau producteur/projection passif à spécifier séparément.

Composants candidats :

- builder `observability/burn_in_status_snapshot.py` ;
- reader `observability/operator_api/burn_in_status_reader.py` ;
- route GET-only `/api/operator/v1/burn-in` ;
- types/validator/client frontend ;
- carte burn-in Direction + vue PAPER lifecycle enrichie.

Le builder possède la lecture de la frontière PPL/config. L'API ne lit jamais
le JSONL autoritaire directement.

Aucune mutation PPL.

### U2b — RuntimeServiceSnapshot

Pour supprimer le besoin de `systemctl` manuel :

- producteur host read-only ;
- Advisor unit state ;
- MainPID ;
- NRestarts ;
- ExecMainStartTimestamp ;
- source/deployment evidence ;
- freshness.

Cette capacité est une preuve host/runtime séparée et ne doit pas être inférée
du snapshot Advisor.

Déploiement ultérieur sous gate #286 distincte.

### U3 — Market / CryptoRadar unifié

1. scanner safe : compléter filtres/recherche et couverture ;
2. microstructure LMI : nouveau snapshot gouverné ;
3. ne pas migrer l'onglet Signaux historique dans Market ;
4. conserver provenance/freshness par source ;
5. matrice de parité obligatoire avant retirement.

### U4 — Research publication → App

Créer le builder déterministe de présentation depuis les artifacts Research
certifiés.

### U5 — Gouvernance/Decision Queue

Reste dépendant de #315 Gate O pour la queue opérationnelle.

Les informations read-only peuvent être ajoutées plus tôt si un producteur
gouverné existe.

---

## 12. Ordre des PR recommandé

```text
U0  contrat/parité                      ← cette mission
 ↓
U1  Direction : exploiter les champs déjà disponibles
 ↓
U2  BurnInStatusSnapshot source-only
 ↓
U2b RuntimeServiceSnapshot source-only
 ↓
U3a Market scanner safe / parité
 ↓
U3b LMI microstructure projection
 ↓
U4  Research presentation builder
 ↓
Certification source #323
 ↓
Déploiement Operator App / observers par gates séparées
 ↓
Runtime/browser proof
 ↓
Retirement CryptoRadar standalone dans une mission indépendante
```

U1 peut être développé sans toucher au runtime de trading.

U2/U2b/U3b/U4 doivent séparer SOURCE PROOF et RUNTIME PROOF.

---

## 13. Critères de retrait futur de CryptoRadar standalone

`crypto-dashboard.service` ne peut être retiré que si les conditions
suivantes sont toutes prouvées :

1. Scanner observationnel utile présent dans Operator App.
2. Filtres/recherche nécessaires disponibles.
3. LMI/microstructure utile migré ou explicitement classé non nécessaire.
4. Aucun niveau Entry/SL/TP historique n'est perdu silencieusement :
   il est soit volontairement retiré comme ambigu, soit remplacé par une vue
   PAPER Decision gouvernée.
5. Aucun consommateur humain/service légitime ne dépend encore du port/service.
6. Operator Market sources FRESH/STALE sont visibles et fail-closed.
7. Mobile/desktop parité fonctionnelle vérifiée.
8. Auth/canal Operator App certifié.
9. Rollback documenté.
10. Mission runtime séparée autorisée sous #286 ou après levée gouvernée du
    freeze.
11. L'Advisor n'est jamais redémarré comme effet du retirement.
12. Suppression source éventuelle séparée de l'arrêt runtime.

---

## 14. Tests requis pour la suite

### Backend / snapshots

- closed schema ;
- atomic write ;
- deterministic projection ;
- missing/malformed/stale fail-closed ;
- source identity/provenance ;
- no secrets ;
- aucune importation d'autorité execution/risk ;
- aucune mutation PPL ;
- aucune lecture brute depuis l'API lorsque le producteur doit posséder cette
  lecture.

### Frontend

- validateurs stricts ;
- invalid HTTP 200 → contract error ;
- UNKNOWN/UNRESOLVED/NOT_AVAILABLE/NON_DEPLOYE jamais transformés en zéro ;
- aucune recomputation PnL/equity/population ;
- aucune donnée Research injectée dans PAPER ;
- erreurs de cartes indépendantes ;
- desktop/mobile ;
- accessibilité ;
- routes GET-only.

### CryptoRadar parity

- même classement observationnel pour la même population source ;
- aucun champ Entry/SL/TP/R dans la projection Market ;
- filtres/search purement présentation ;
- LMI stale/fresh explicitement testé ;
- arrêt d'un producteur → STALE/UNAVAILABLE visible, jamais données courantes
  fabriquées.

### Gouvernance

- diff source-only pour chaque phase avant runtime gate ;
- exact SHA ;
- CI ;
- cross-stack ;
- visual proof ;
- rollback ;
- #286 explicitement respecté.

---

## 15. Ce que U0 ne recommande pas

Ne pas :

- fusionner l'ancien dashboard dans React en copiant son HTML/JS ;
- connecter React directement aux DecisionPacket JSONL ;
- faire lire PPL JSONL par une route API ad hoc ;
- afficher Entry/SL/TP issus du radar comme opportunités Market ;
- calculer le burn-in progress dans le frontend ;
- inférer Advisor alive depuis `/healthz` ;
- activer FIN-02 implicitement ;
- utiliser Research N/PF/WR comme métrique PAPER active ;
- retirer `crypto-dashboard.service` avant parité et gate séparée.

---

## 16. Conclusion

L'Operator App est déjà la bonne fondation.

Le travail restant se répartit ainsi :

- **présentation sous-utilisée** : U1 ;
- **projections réellement manquantes** : U2/U2b/U3b/U4 ;
- **surface historique à retirer plus tard** : CryptoRadar standalone ;
- **trading runtime** : inchangé.

La cible produit reste :

```text
ouvrir l'Operator App
→ comprendre l'état de la machine
→ comprendre le burn-in
→ voir portefeuille/finance/marché/Research
→ ouvrir le VPS seulement pour maintenance/forensic exceptionnel
```
