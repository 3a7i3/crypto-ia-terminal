# PHASE_03 — Couche REST honnête (fin des métriques codées en dur)

**Préfixe d'ID de tickets : `REST-###`** (aucun autre préfixe n'est autorisé dans ce document).

**Statut de gating : NON GATED — exécutable sous le gel fonctionnel.**
Tous les tickets de cette phase sont en **lecture seule côté décision** : ils ne touchent ni
`PositionManager`, ni `check_new_trade`, ni le sizing, ni le risk, ni `PortfolioBrain` en entrée de
décision. **Aucun reset d'époque, aucun reset de N.**

---

## Objectif

Faire en sorte que la couche REST (`visualization/api/portfolio_api.py`) **cesse de publier des nombres
fabriqués**.

Objectif mesurable, en quatre assertions binaires :

1. Aucune des huit valeurs `n_trades`, `n_wins`, `n_losses`, `win_rate_pct`, `profit_factor`,
   `expectancy_pct`, `max_drawdown_pct`, `sharpe` n'est plus un littéral codé en dur
   (`visualization/api/portfolio_api.py:22-29`).
2. `total_pnl_usd` (`portfolio_api.py:30`) n'est plus une recopie de `open_pnl_usd`.
3. Toute valeur qui n'est **pas** disponible depuis la source retenue est renvoyée comme **absente**
   (`null` / champ omis), **jamais** comme `0`.
4. Le verdict de `check_new_trade` est strictement identique avant/après la phase (invariant **INV-R3**),
   ce qui prouve l'absence de nouvelle époque.

Non-objectifs explicites :

- **Ne pas** unifier les 4 stores de positions ni les 3 classes `PortfolioSnapshot`
  (`observability/system_snapshot.py:56`, `quant_hedge_ai/agents/risk/portfolio_brain.py:64`,
  `visualization/api/models.py:69`) — c'est PHASE_04_GATED.
- **Ne pas** créer une nouvelle lignée de calcul de `win_rate` / `max_drawdown`. L'audit SSoT compte déjà
  ~5 recalculs de `win_rate` et ~5 de `drawdown` ; la phase doit en **consommer un existant**, pas en
  ajouter un sixième.
- **Ne pas** corriger la décision. La couche REST n'a jamais été une entrée de décision et ne le devient
  pas.

---

## Contexte

Diagnostic validé (ne pas ré-enquêter) :

- `visualization/api/portfolio_api.py:22-29` : `n_trades=0`, `n_wins=0`, `n_losses=0`, `win_rate_pct=0.0`,
  `profit_factor=0.0`, `expectancy_pct=0.0`, `max_drawdown_pct=0.0`, `sharpe=0.0` sont **codés en dur**.
  L'API publie donc un état de performance qui n'a jamais été mesuré.
- `visualization/api/portfolio_api.py:30` : `total_pnl_usd = open_pnl_usd` — le PnL **ouvert** est recopié
  dans le PnL **total**. Le PnL réalisé est absent de la réponse.
- `visualization/api/portfolio_api.py:33` : `capital_usd = portfolio.paper_equity`.
- `visualization/api/portfolio_api.py:34` : `trade_history = []` — historique systématiquement vide.
- Audit SSoT de référence : **0 PASS / 1 WARNING / 8 FAIL**, dont `win_rate` (~5 recalculs),
  `drawdown` (~5), `PnL` (4 ouvert / 2 fermé), `capital` (5), `equity` (5). La couche REST est l'un des
  producteurs fautifs.
- Lignées de calcul concurrentes déjà recensées, à ne pas multiplier :
  `paper_trading/ledger.py:191` `summary()` (`n_trades`, `capital`, `win_rate`, `max_drawdown_pct`,
  `total_fees_usd`) ; `analysis/base.py:88` `win_rate()` et `:125` `max_drawdown()` (lignée scientifique
  des tests H1-H6) ; `certification/operator_signoff.py:46` (`paper_max_dd`, `paper_win_rate`) ;
  `system/integrity_snapshot.py:100-135` (`pb_free` / `pb_exposure` / `pb_n` via `pos_manager`).
- Écrivains de `paper_trades.jsonl` : `paper_trading/mexc_simulator.py` et `paper_trading/recorder.py`
  **exclusivement**. La couche REST est lectrice, jamais écrivaine.
- Rappel de la cause racine générale (PHASE_01) : `core/advisor_loop.py:6785-6787` passe
  `pos_manager.get_open()` (vide en paper) à `portfolio_brain.portfolio_health()`
  (`quant_hedge_ai/agents/risk/portfolio_brain.py:645-664`, `:668-687`, `MAX_TOTAL_EXPOSURE_PCT = 0.40`
  ligne 88). **PHASE_03 ne touche pas ce chemin.**

Cadre de gouvernance applicable : ADR-0007 (passivité absolue des observers — une API de lecture est un
observer, elle ne décide de rien), Scientific Debt Rule (seuls les outils de mesure et d'audit sont
autorisés : remplacer un zéro fabriqué par une mesure réelle **est** un outil de mesure), règle du
statisticien (aucun seuil modifié, aucune calibration), borne d'époque
`CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` (`scripts/data_quality.py`, alias `CLEAN_DATA_SINCE_ACTIVE`).

Point épistémique (protocole v3, `docs/protocole_audit_epistemique.md`) : un `0.0` publié par l'API est
lu par tout consommateur aval comme une **observation** (« le win rate mesuré vaut 0 »), alors qu'il n'est
qu'un **littéral d'implémentation**. C'est une fabrication d'évidence. C'est la raison d'être de la phase,
et c'est pourquoi l'assertion 3 de l'Objectif (absent ≠ zéro) est non négociable.

---

## Dépendances

| Dépendance | Nature | Statut |
|---|---|---|
| PHASE_00 (`GOV-*`) — charte de gating, registre des invariants, format de commit | Amont, documentaire | Contenu exact **A CONFIRMER AU DEMARRAGE DU TICKET** (`.claude/phases/PHASE_00.md` non lu par cet agent) |
| PHASE_01 (`OBS-*`) | **Indépendante** — PHASE_01 corrige les panneaux Telegram, PHASE_03 corrige l'API REST. Aucun fichier commun sauf lecture de `observability/system_snapshot.py` | Non bloquante dans les deux sens |
| PHASE_02_GATED (`SSOT-*`) | Aval — l'unification du store canonique rendra REST-003/004 plus simples, jamais l'inverse | Bloqué (voir PHASE_02_GATED) |
| PHASE_04_GATED (`PORT-*`) | Aval — déduplication des 3 `PortfolioSnapshot` dont `visualization/api/models.py:69` | Bloqué |
| `docs/protocole_audit_epistemique.md` (v3) | Amont, méthodologique | Présent dans `main` |
| `CLAUDE.md` (règles invariantes) | Amont, normatif | Présent |

Aucune dépendance envers un déploiement VPS : la phase est intégralement validable en local par tests.

**Précision d'ordonnancement** : REST-001 (choix de source) est bloquant pour REST-003 et REST-004.
Si PHASE_01 est exécutée en parallèle, aucune coordination n'est requise — les plages de code sont
disjointes (`core/advisor_loop.py` d'un côté, `visualization/api/` de l'autre).

---

## Prérequis

1. Dépôt sur `main` propre (`git status` vide) avant le premier ticket.
2. Baseline de tests notée avant REST-001 : `python -m pytest tests/ -q` (nombre de tests, échecs
   préexistants, durée) — **A CONFIRMER AU DEMARRAGE DU TICKET**.
3. Lecture préalable, sans modification, de :
   - `visualization/api/portfolio_api.py` (intégralité — le diagnostic ne cite que les lignes 22-34 ;
     la longueur totale du fichier et la nature exacte de l'objet `portfolio` reçu sont
     **A CONFIRMER AU DEMARRAGE DU TICKET**),
   - `visualization/api/models.py:69` (`PortfolioSnapshot` de la couche REST — schéma exposé),
   - `paper_trading/ledger.py:121` (`PaperLedger._open`) et `:191` (`summary()`),
   - `observability/system_snapshot.py:56`, `:132`, `:143` (`to_dict`),
   - `tests/visualization/test_snapshot_only_loaders.py`.
4. Inventaire des **consommateurs** de l'endpoint : frontend React, tests, scripts, dashboards
   `sdos_terminal/` / `visualization/`. **A CONFIRMER AU DEMARRAGE DU TICKET** — un consommateur qui
   suppose « champ toujours présent, type toujours numérique » change la forme acceptable du correctif
   (voir R7 et INV-R6).
5. Vérification que l'API est bien lancée en **lecture seule** sur les fichiers de données (aucun mode
   d'ouverture en écriture, aucun verrou pris) — **A CONFIRMER AU DEMARRAGE DU TICKET**.
6. Aucune modification de `.env`, `runtime_config.json`, ni de la configuration VPS pendant la phase.

---

## Risques

| ID | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | **Un zéro fabriqué est lu comme une mesure.** Un consommateur (opérateur, dashboard, futur dossier Go/No-Go) prend `win_rate_pct = 0.0` pour un résultat scientifique. | Certaine aujourd'hui | Élevé — fabrication d'évidence | Objet même de la phase (REST-003) + invariant INV-R6 : indisponible ⇒ `null`, jamais `0` |
| **R2** | **Ajout d'une 5ᵉ/6ᵉ lignée de recalcul.** L'implémenteur code un `win_rate` local dans l'API « parce que c'est plus simple ». | Élevée | Élevé — aggrave les 8 FAIL SSoT | REST-001 fige la source **avant** tout code ; critère de refus binaire dans REST-003 (aucune arithmétique de métrique dans `portfolio_api.py`) |
| **R3** | Dérive de périmètre vers `core/advisor_loop.py`, `paper_trading/`, `quant_hedge_ai/agents/risk/` | Moyenne | Critique — reset de N, burn-in détruit | Critère de refus : tout diff hors `visualization/` et `tests/` ⇒ ticket rejeté |
| **R4** | **Mélange d'époques.** La source lue (par ex. `paper_trades.jsonl` complet) contient des trades antérieurs à `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` ⇒ métriques justes en forme, fausses en fond | Élevée | Élevé — chiffres publiés non comparables au CRI | REST-001 tranche explicitement la question du filtrage d'époque et l'inscrit dans la réponse (champ de provenance) |
| R5 | Concurrence de lecture : l'API lit un fichier pendant que `mexc_simulator.py` / `recorder.py` écrit ⇒ ligne tronquée, exception, ou snapshot incohérent | Moyenne | Moyen | REST-001 privilégie une source déjà matérialisée/atomique ; REST-003 impose une lecture tolérante aux lignes incomplètes, sans jamais réparer ni réécrire le fichier (INV-R1) |
| R6 | Des tests figent les zéros actuels (`tests/visualization/test_snapshot_only_loaders.py`) et « prouvent » le bug | Élevée | Moyen | REST-002 (rouge d'abord) + REST-005 (adaptation explicite, une justification par assertion modifiée) |
| R7 | Un consommateur aval (frontend React, dashboard) casse sur `null` là où il attendait un nombre | Moyenne | Moyen | Prérequis 4 (inventaire) ; si un consommateur ne tolère pas `null`, la valeur reste absente du schéma plutôt que remise à `0` — arbitrage tranché et écrit en REST-001 |
| R8 | `trade_history = []` (`portfolio_api.py:34`) laissé en l'état donne une réponse « cohérente en apparence, vide en fait » | Certaine | Faible en PHASE_03 | Hors périmètre assumé : annoté en REST-004, traité en PHASE_04_GATED |

---

## Architecture

Règle unique de la phase :

> La couche REST **n'est pas un producteur de métriques**. Elle est un **transporteur**. Chaque nombre
> publié est soit repris tel quel d'un producteur existant et nommé, soit absent.

Chemin cible :

```
SOURCE RETENUE (figee par REST-001, un seul producteur)
        |
        +--> metriques agregees (n_trades, n_wins, n_losses, win_rate,
        |    profit_factor, expectancy, max_drawdown, sharpe)
        |            |
        |            v
        |    visualization/api/portfolio_api.py  (TRANSPORT SEUL : lit, mappe, publie)
        |            |
        |            v
        |    visualization/api/models.py:69  (schema expose, INCHANGE si possible)
        |
        +--> champ de PROVENANCE publie a cote des metriques
             (nom de la source + borne d'epoque appliquee + fraicheur)

INTERDIT DANS portfolio_api.py :
        toute somme, division, comparaison ou tri servant a fabriquer une metrique
        toute ecriture de fichier
        tout appel a pos_manager / check_new_trade / portfolio_brain
```

Trois propriétés structurelles :

1. **Zéro nouveau calcul.** Conformité Scientific Debt Rule : on ne crée pas de variable expérimentale
   supplémentaire, on en supprime une (le zéro fabriqué).
2. **Sens unique et passivité.** L'API lit ; elle n'écrit ni fichier, ni état, ni décision (ADR-0007).
3. **Absence explicite.** `null` déclaré est une information vraie ; `0.0` fabriqué est une information
   fausse. Le schéma doit pouvoir porter l'absence.

Ce qui **n'est pas** fait en PHASE_03 : déduplication des classes (`PortfolioSnapshot` ×3,
`PortfolioBrain` ×2, `SystemSnapshot` ×2), unification des 4 stores de positions, reconstruction de
`trade_history`.

---

## Fichiers concernés

| Fichier | Lignes de référence | Type d'intervention en PHASE_03 |
|---|---|---|
| `visualization/api/portfolio_api.py` | 22-29 (8 littéraux) | Modification (REST-003) |
| `visualization/api/portfolio_api.py` | 30 (`total_pnl_usd = open_pnl_usd`) | Modification (REST-004) |
| `visualization/api/portfolio_api.py` | 33 (`capital_usd = portfolio.paper_equity`), 34 (`trade_history = []`) | Annotation uniquement (REST-004) |
| `visualization/api/models.py` | 69 (`PortfolioSnapshot` REST) | Modification **minimale et seulement si nécessaire** (REST-003 : rendre les champs optionnels) |
| `tests/visualization/test_snapshot_only_loaders.py` | — | Adaptation (REST-005), inventaire dès REST-002 |
| `tests/` (nouveau fichier de régression REST) | — | Création (REST-002) |
| `docs/adr/` (ADR de choix de source) | — | Création (REST-001) — chemin et numéro exacts **A CONFIRMER AU DEMARRAGE DU TICKET** ; numéros libres à partir d'**ADR-0019** |
| `paper_trading/ledger.py` | 121, 191 | **Lecture seule — NON MODIFIÉ** |
| `observability/system_snapshot.py` | 56, 132, 143 | **Lecture seule — NON MODIFIÉ** |
| `core/advisor_loop.py` | toutes | **Lecture seule — NON MODIFIÉ** |
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | toutes | **Lecture seule — NON MODIFIÉ** |
| `analysis/base.py` | 88, 125 | **Lecture seule — NON MODIFIÉ** (lignée scientifique H1-H6) |

Fichiers **interdits d'écriture sur toute la phase** : `core/*`, `paper_trading/*`,
`quant_hedge_ai/agents/risk/*`, `analysis/*`, `certification/*`, `system/integrity_snapshot.py`,
`scripts/data_quality.py`, `tools/cri_calculator.py`, `databases/*`, `.env`, `runtime_config.json`.

---

## Invariants

| ID | Énoncé | Vérification |
|---|---|---|
| **INV-R1** | Aucune écriture de fichier par la couche REST. Les seuls écrivains de `paper_trades.jsonl` restent `paper_trading/mexc_simulator.py` et `paper_trading/recorder.py`. | Test dédié REST-002 (aucun fichier créé/modifié pendant un appel d'endpoint) + revue de diff |
| **INV-R2** | Aucune métrique n'est **calculée** dans `visualization/` : pas de somme, division, tri ou comparaison servant à produire `win_rate`, `profit_factor`, `expectancy`, `drawdown`, `sharpe`. Seuls le mapping et le formatage sont permis. | Revue de diff ; critère de refus binaire dans REST-003 |
| **INV-R3** | Le verdict de `check_new_trade` est identique avant/après, sur des entrées identiques ⇒ **aucun reset d'époque, N inchangé**. | Test de garde (réutiliser celui d'OBS-001 s'il existe, sinon en créer un équivalent — REST-002) |
| **INV-R4** | Aucun fichier hors `visualization/`, `tests/` et `docs/` n'apparaît dans le diff de la phase. | `git diff --name-only main...HEAD` |
| **INV-R5** | Borne d'époque intacte : `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`. `scripts/data_quality.py` et `tools/cri_calculator.py` ne sont pas modifiés ; si un filtrage d'époque est appliqué, il **importe** l'alias `CLEAN_DATA_SINCE_ACTIVE`, il ne le recopie pas. | `git diff --stat` ne contient ni `scripts/data_quality.py` ni `tools/cri_calculator.py` ; recherche de la chaîne `2026-07-17` dans le diff = 0 littéral |
| **INV-R6** | Une valeur indisponible est publiée comme absente (`null` ou champ omis), **jamais** comme `0`, `0.0`, `-1` ou toute autre valeur sentinelle numériquement interprétable. | Test REST-002 : source vide ⇒ champs `null`, aucun `0` |
| **INV-R7** | Le schéma `visualization/api/models.py:69` n'est **pas renommé** et aucun champ existant n'est supprimé. Seul l'assouplissement de type (numérique ⇒ numérique optionnel) est autorisé, et uniquement si REST-001 l'a tranché. | Revue de diff ; test de compatibilité de schéma REST-002 |
| **INV-R8** | Aucune nouvelle couche décisionnelle, aucun nouvel indicateur, aucune nouvelle stratégie, aucun seuil modifié (Scientific Debt Rule, règle du statisticien). | Revue de diff : aucun littéral de seuil ajouté hors formatage |
| **INV-R9** | Passivité ADR-0007 : le code REST n'appelle aucune fonction à effet de bord (ordre, mutation de position, écriture d'état, déclenchement de cycle). | Revue de diff : lectures + mapping uniquement |

---

## Validation

Validation de phase (après REST-005, avant clôture) :

1. `python -m pytest tests/ -q` — aucun échec nouveau par rapport à la baseline notée en Prérequis.
2. `python -m pytest tests/visualization/ -q` — 100 % vert, tests adaptés inclus.
3. `git diff --name-only main...HEAD` — uniquement des chemins sous `visualization/`, `tests/`, `docs/`.
4. Inspection de la réponse de l'endpoint sur un jeu de données local contenant au moins un trade fermé :
   - `n_trades` > 0 et égal à la valeur retournée par la source retenue (REST-001) ;
   - `total_pnl_usd` ≠ `open_pnl_usd` dès qu'un trade fermé existe avec un PnL réalisé non nul ;
   - chaque métrique non disponible est `null`, aucune n'est `0.0` par défaut ;
   - le champ de provenance indique la source et la borne d'époque appliquée.
5. Inspection de la réponse sur un jeu de données **vide** : toutes les métriques agrégées sont `null`
   (et non `0`), `n_trades` vaut `0` **uniquement** si la source retourne réellement un compte de zéro
   trade — distinction à écrire dans le test.
6. Contrôle épistémique (protocole v3) : la clôture de phase sépare explicitement
   **Observation** (« l'API publiait 8 littéraux »), **Inférence** (« tout consommateur les lisait comme
   des mesures »), **Décision** (« source retenue = X, absence = `null` »), et nomme la dette résiduelle
   (`trade_history` vide, `capital_usd` = une des 5 définitions de capital).

Deux falsificateurs de la phase (à écrire dans la clôture) :

- **F1** : si, avec au moins un trade fermé dans la source, l'API publie encore `win_rate_pct = 0.0`
  ou `n_trades = 0`, la phase a échoué.
- **F2** : si `git diff main...HEAD` contient un fichier hors `visualization/`, `tests/`, `docs/`,
  ou si le test de garde INV-R3 diffère d'un seul cas, la phase a échoué et doit être intégralement
  révoquée (risque de nouvelle époque).

---

## Rollback

- Granularité : **1 ticket = 1 commit** ⇒ `git revert <sha>` d'un seul ticket est toujours possible.
- Ordre de revert si la phase entière doit être annulée : REST-005, REST-004, REST-003, REST-001,
  puis REST-002 en dernier (les tests sont le filet ; on les retire en dernier).
- Aucun rollback ne peut corrompre de données : aucun ticket n'écrit dans `databases/`,
  `paper_trades.jsonl` ni `regret_horizons` (INV-R1). La borne d'époque est inchangée (INV-R5).
- Revert partiel acceptable : annuler REST-004 seul laisse les 8 métriques correctes et
  `total_pnl_usd` de nouveau faux — état dégradé mais cohérent, sans effet sur la décision.
- Aucun rollback VPS nécessaire tant que la phase n'est pas déployée. Si elle l'a été, le retour est un
  déploiement délibéré du commit précédent : `bash scripts/deploy_vps.sh --confirm` (jamais automatique),
  redémarrage en double opt-in.

---

## Estimation

| Ticket | Estimation | Fichiers | Lignes modifiées (ordre de grandeur) |
|---|---|---|---|
| REST-001 | 2 h – 4 h | 1 créé (`docs/adr/`) | ≤ 200 (document) |
| REST-002 | 3 h – 5 h | 1 créé + 0 à 2 inventoriés | ≤ 250 |
| REST-003 | 3 h – 5 h | 2 (`portfolio_api.py`, `models.py`) | ≤ 120 |
| REST-004 | 1 h – 2 h | 1 (`portfolio_api.py`) | ≤ 60 |
| REST-005 | 1 h – 3 h | 1 à 2 (`tests/visualization/`) | ≤ 150 |
| **Total phase** | **1 à 2 jours** | — | **≤ 780 cumulées** |

Chaque ticket respecte l'atomicité : ≤ 300 lignes modifiées **et** ≤ 4 fichiers.

---

## Tickets

### REST-001

- **ID** : REST-001
- **Titre** : Figer la source unique de lecture de l'API REST (ADR) — `PaperLedger.summary()` ou snapshot persisté
- **Objectif** : produire un ADR (numéro libre à partir d'**ADR-0019**, chemin
  **A CONFIRMER AU DEMARRAGE DU TICKET**) qui tranche, **avant toute ligne de code**, quelle source unique
  alimente `visualization/api/portfolio_api.py`, et qui démontre que ce choix **n'ajoute aucun recalcul**.
- **Pourquoi** : l'audit SSoT compte déjà 8 FAIL, dont ~5 recalculs de `win_rate` et ~5 de `drawdown`.
  Brancher l'API sans décision écrite conduit mécaniquement à en créer un de plus (R2), c'est-à-dire à
  aggraver le défaut qu'on prétend corriger. Le livrable de ce ticket est une **contrainte opposable** aux
  tickets suivants, pas une préférence.
- **Diagnostic résumé** :
  1. `visualization/api/portfolio_api.py:22-29` : 8 métriques codées en dur à `0` / `0.0`.
  2. `visualization/api/portfolio_api.py:30` : `total_pnl_usd = open_pnl_usd` (PnL ouvert recopié).
  3. `visualization/api/portfolio_api.py:33` : `capital_usd = portfolio.paper_equity` — l'une des
     5 définitions rivales de capital recensées par l'audit.
  4. Candidat A : `paper_trading/ledger.py:191` `summary()` expose déjà `n_trades`, `capital`,
     `win_rate`, `max_drawdown_pct`, `total_fees_usd` — producteur existant, donc **zéro recalcul ajouté**.
     Ne couvre pas nécessairement `profit_factor`, `expectancy_pct`, `sharpe`, `n_wins`, `n_losses` :
     **A CONFIRMER AU DEMARRAGE DU TICKET**.
  5. Candidat B : snapshot persisté (`observability/system_snapshot.py:56`, `:132`, `to_dict:143`) —
     déjà matérialisé, donc lecture atomique et insensible à la concurrence d'écriture (R5), mais son
     contenu en métriques **fermées** est **A CONFIRMER AU DEMARRAGE DU TICKET**.
  6. Contrainte transverse : `paper_trades.jsonl` est écrit par `paper_trading/mexc_simulator.py` et
     `paper_trading/recorder.py` uniquement ; toute lecture directe expose à une ligne tronquée.
  7. Contrainte d'époque : `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` (`scripts/data_quality.py`,
     alias `CLEAN_DATA_SINCE_ACTIVE`) — une métrique publiée sans borne mélange les époques V3 et V4.
- **Contexte** : ticket **documentaire pur**. Aucun fichier `.py` modifié, aucun test exécuté au-delà de la
  baseline. Il conditionne REST-003 et REST-004.
- **Hypothèses** :
  - H1 — `PaperLedger.summary()` (`paper_trading/ledger.py:191`) est appelable depuis le process qui sert
    l'API, sans démarrer la boucle de trading. **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H2 — un snapshot persisté existe, est rafraîchi à une fréquence connue, et son emplacement est stable.
    **A CONFIRMER AU DEMARRAGE DU TICKET** (la fraîcheur est un critère de choix : une source rafraîchie
    toutes les N minutes doit publier son horodatage).
  - H3 — au moins un des deux candidats couvre `n_wins` / `n_losses` / `profit_factor` / `expectancy_pct` /
    `sharpe`. **A CONFIRMER AU DEMARRAGE DU TICKET.** Si aucun ne les couvre, la décision de l'ADR est
    « ces champs sont publiés `null` » — **jamais** « on les calcule dans l'API » (INV-R2).
  - H4 — les consommateurs aval tolèrent `null`. **A CONFIRMER AU DEMARRAGE DU TICKET** (Prérequis 4).
- **Invariants** : INV-R2 (raison d'être du ticket), INV-R4, INV-R5, INV-R6, INV-R7, INV-R8.
  INV-R1, INV-R3, INV-R9 triviaux (aucun code touché).
- **Fichiers** : 1 fichier créé sous `docs/adr/` (nom exact **A CONFIRMER AU DEMARRAGE DU TICKET**).
  Aucun fichier de production, aucun test.
- **Pseudo-code** (description, non exécutable) :

```
DOCUMENT DE DECISION — STRUCTURE IMPOSEE

  1. CONSTAT (Observation, verifiable)
       LISTER les 8 litteraux de portfolio_api 22-29 ET la recopie ligne 30
       LISTER les producteurs de metriques DEJA EXISTANTS et leur fichier:ligne

  2. CANDIDATS
       POUR CHAQUE candidat (ledger.summary / snapshot persiste) :
           QUELS champs sont FOURNIS TELS QUELS
           QUELS champs sont ABSENTS
           FRAICHEUR (temps reel ? periodique ? horodatee ?)
           ATOMICITE DE LECTURE (risque de ligne tronquee ?)
           BORNE D'EPOQUE appliquee OU NON

  3. CRITERE DE DECISION (dans cet ordre de priorite)
       C1  ZERO RECALCUL AJOUTE          <-- eliminatoire
       C2  BORNE D'EPOQUE APPLICABLE     <-- eliminatoire
       C3  LECTURE ATOMIQUE / SANS VERROU
       C4  COUVERTURE DE CHAMPS
       C5  COUT D'IMPLEMENTATION

  4. DECISION
       SOURCE RETENUE = <un seul nom, un seul fichier:ligne>
       CHAMPS PUBLIES DEPUIS CETTE SOURCE = <liste>
       CHAMPS PUBLIES NULL = <liste>            (JAMAIS zero)
       CHAMP DE PROVENANCE PUBLIE = nom_source + borne_epoque + horodatage_source

  5. DEMONSTRATION « AUCUN RECALCUL SUPPLEMENTAIRE »
       POUR CHAQUE champ publie :
           MONTRER le producteur existant (fichier:ligne) qui le calcule DEJA
           SI aucun producteur existant NE LE CALCULE
               ALORS le champ EST NULL — on n'en cree pas un nouveau

  6. CE QUE L'ADR N'AUTORISE PAS
       toute arithmetique de metrique dans visualization/
       toute ecriture de fichier depuis l'API
       toute lecture de pos_manager, check_new_trade, portfolio_brain
       tout litteral de borne d'epoque recopie (importer CLEAN_DATA_SINCE_ACTIVE)

  7. DEUX FALSIFICATEURS DE LA DECISION
       F1 : si la source retenue s'avere ne pas appliquer la borne V4, la decision est revisee
       F2 : si un champ publie ne correspond pas, chiffre pour chiffre, a la valeur du
            producteur nomme, la decision est violee
```

- **Plan d'action** :
  1. Lire `visualization/api/portfolio_api.py` en entier et relever ce que contient réellement l'objet
     `portfolio` passé à l'endpoint (`:30`, `:33`).
  2. Lire `paper_trading/ledger.py:191` `summary()` et lister exactement les champs retournés.
  3. Lire `observability/system_snapshot.py:56`, `:132`, `:143` et lister exactement les champs
     du snapshot persisté, ainsi que le producteur et la fréquence d'écriture.
  4. Vérifier, pour chaque candidat, si la borne `CLEAN_DATA_SINCE_ACTIVE` est appliquée
     (import depuis `scripts/data_quality.py`) ou non.
  5. Inventorier les consommateurs de l'endpoint (Prérequis 4) et leur tolérance à `null`.
  6. Remplir la grille de décision C1→C5 et trancher.
  7. Rédiger l'ADR avec les 7 sections du pseudo-code ci-dessus, y compris la démonstration
     « aucun recalcul supplémentaire » champ par champ.
  8. Commit unique (documentaire).
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. L'étape 6 ne peut pas précéder l'étape 4 :
  le critère C2 (borne d'époque) est éliminatoire et se décide sur constat, pas sur intuition.
- **Tests** : aucun test de code. Contrôle documentaire uniquement (`python -m pytest tests/ -q` doit
  rester à la baseline, ce qui est trivial puisque aucun `.py` n'est touché).
- **Validation** :
  - L'ADR nomme **une seule** source, avec `fichier:ligne`.
  - Pour chaque champ publié, l'ADR cite le producteur existant ; aucun champ n'est « à calculer ».
  - La liste des champs `null` est explicite et non vide **ou** justifiée si elle est vide.
  - `git diff --name-only` ne liste qu'un chemin sous `docs/`.
- **Rollback** : `git revert <sha REST-001>` — sans effet fonctionnel (document seul). REST-003 et
  REST-004 deviennent alors non démarrables (dépendance dure).
- **Risques** : R2 (raison d'être), R4 (mélange d'époques), R5 (concurrence de lecture), R7 (tolérance
  `null` des consommateurs).
- **Temps estimé** : 2 h – 4 h.
- **Dépendances** : PHASE_00 (`GOV-*`) pour le format d'ADR et de commit —
  **A CONFIRMER AU DEMARRAGE DU TICKET**. Aucune dépendance code.
- **Démonstration de non-décision** : le ticket ne produit qu'un fichier `.md` sous `docs/`. Il ne touche
  ni `PositionManager`, ni `check_new_trade`, ni le sizing, ni le risk, ni `PortfolioBrain`.
  **Aucun reset d'époque, N inchangé.**
- **Critères Done** :
  - `git diff --name-only` retourne exactement un chemin commençant par `docs/`.
  - L'ADR contient littéralement une section « Source retenue » avec un unique `fichier:ligne`.
  - L'ADR contient une table champ → producteur existant couvrant les 8 champs de
    `portfolio_api.py:22-29` **plus** `total_pnl_usd` (ligne 30), chaque case valant soit un
    `fichier:ligne`, soit `NULL`.
  - `python -m pytest tests/ -q` : identique à la baseline.
- **Critères Refus** :
  - L'ADR retient deux sources ou laisse le choix ouvert ⇒ refus (le ticket existe pour trancher).
  - Une case de la table champ → producteur vaut « à calculer dans l'API » ⇒ refus (viole INV-R2).
  - Un champ indisponible est décidé à `0` au lieu de `null` ⇒ refus (viole INV-R6).
  - Un fichier `.py` apparaît dans le diff ⇒ refus.
  - La question de la borne d'époque n'est pas tranchée explicitement ⇒ refus.

---

### REST-002

- **ID** : REST-002
- **Titre** : Supprimer la recopie `total_pnl_usd = open_pnl_usd` (`portfolio_api.py:30`)
- **Objectif** : cesser de publier le PnL **ouvert** dans le champ `total_pnl_usd`, qui est lu comme un
  PnL **total**. Publier soit la vraie valeur si un producteur existant la fournit, soit `null`.
- **Pourquoi** : c'est le seul défaut de la phase qui produit une valeur **activement fausse** (et non
  simplement absente). Un consommateur qui lit `total_pnl_usd` obtient aujourd'hui un chiffre plausible
  mais faux, sans aucun signal d'erreur. Une valeur fausse est plus nuisible qu'une valeur absente.
- **Diagnostic résumé** : `visualization/api/portfolio_api.py:30` écrit
  `total_pnl_usd=float(portfolio.get("open_pnl_usd", 0.0) or 0.0)`. Le champ source
  `open_pnl_usd` provient de `PortfolioSnapshot` (`observability/system_snapshot.py:56`), alimenté par
  `_display_position_summary` (`core/advisor_loop.py:434-459`) : c'est un PnL **latent**, sur positions
  **ouvertes**. Le PnL **fermé** est produit ailleurs (`paper_trading/ledger.py:191`, clé `pnl_net_usd`).
  Les deux ne sont pas commensurables.
- **Contexte** : ticket **indépendant de REST-001**. Il ne nécessite aucun choix de source nouveau :
  soit le champ devient `null`, soit il est alimenté par la source déjà retenue si REST-001 est terminé.
  La branche `null` est toujours applicable et suffit à corriger le défaut.
- **Hypothèses** :
  - H1 — les consommateurs de l'endpoint tolèrent `total_pnl_usd = null`.
    **A CONFIRMER AU DEMARRAGE DU TICKET** (si un consommateur casse, le ticket s'arrête, cf STOP).
  - H2 — aucun test existant n'asserte `total_pnl_usd == open_pnl_usd`.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
- **Invariants** : INV-1 (aucune écriture vers la décision), INV-2 (aucun reset de N), INV-3
  (`paper_trades.jsonl` non touché), INV-4 (sizing non touché), INV-R2 (aucun recalcul créé dans l'API),
  INV-R6 (indisponible ⇒ `null`, jamais `0`).
- **Fichiers** : `visualization/api/portfolio_api.py` (1 fichier). Éventuellement 1 fichier de test
  si H2 est infirmée. **≤ 2 fichiers, ≤ 20 lignes.**
- **Pseudo-code** (description, non exécutable) :

```
AVANT   total_pnl_usd <- portfolio["open_pnl_usd"]        # FAUX : ouvert publie comme total

APRES
  SI REST-001 termine ET la source retenue expose un PnL ferme
      total_pnl_usd <- <source_retenue>.<champ_pnl_ferme>
      provenance    <- nom_source + fichier:ligne
  SINON
      total_pnl_usd <- NULL                                # jamais 0, jamais open_pnl_usd
      provenance    <- "non disponible"

  open_pnl_usd RESTE publie SEPAREMENT, inchange, sous son propre nom
  AUCUNE arithmetique n'est introduite dans visualization/
```

- **Plan d'action** :
  1. Relever les consommateurs de `total_pnl_usd` (grep sur le dépôt + front éventuel) et leur
     tolérance à `null` (H1).
  2. Vérifier qu'aucun test n'asserte l'égalité avec `open_pnl_usd` (H2).
  3. Remplacer la recopie par `null` (ou par la source retenue si REST-001 est terminé).
  4. Vérifier que `open_pnl_usd` reste publié, séparément et inchangé.
  5. Lancer les tests, comparer à la baseline.
  6. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6. L'étape 1 précède l'étape 3 : publier `null` sans avoir
  vérifié la tolérance des consommateurs déplace le défaut au lieu de le corriger.
- **Tests** : `python -m pytest tests/visualization/ -q` puis `python -m pytest tests/ -q`.
  Comparaison stricte à la baseline relevée avant le ticket.
- **Validation** :
  - `total_pnl_usd` ne vaut plus jamais `open_pnl_usd`.
  - `open_pnl_usd` reste publié et inchangé.
  - Aucune opération arithmétique nouvelle dans `visualization/`.
  - `git diff --name-only` ne liste que `visualization/api/portfolio_api.py` (+ éventuellement un test).
- **Rollback** : `git revert <sha REST-002>`. Retour à la recopie fausse, sans autre effet.
- **Risques** : R7 (consommateur intolérant à `null`) ; R2 (tentation de calculer le PnL fermé dans
  l'API — interdit par INV-R2).
- **Temps estimé** : 1 h – 2 h.
- **Dépendances** : aucune dure. REST-001 est **facultatif** : sans lui, la branche `null` s'applique.
- **Démonstration de non-décision** : le fichier touché est un adaptateur de lecture HTTP. Il ne lit ni
  `pos_manager`, ni `check_new_trade`, ni `PortfolioBrain` en entrée de décision, et n'écrit nulle part.
  **Aucun reset d'époque, N inchangé.**
- **Critères Done** :
  - `grep -n "open_pnl_usd" visualization/api/portfolio_api.py` ne montre plus d'affectation à `total_pnl_usd`.
  - `python -m pytest tests/ -q` identique à la baseline.
  - Le diff fait ≤ 20 lignes.
- **Critères Refus** :
  - `total_pnl_usd` passe à `0.0` au lieu de `null` ⇒ refus (INV-R6).
  - Un calcul de PnL est introduit dans `visualization/` ⇒ refus (INV-R2).
  - `open_pnl_usd` est supprimé ou modifié ⇒ refus (hors périmètre).
  - Un fichier hors `visualization/` (ou hors tests) apparaît au diff ⇒ refus.

---

### REST-003

- **ID** : REST-003
- **Titre** : Remplacer les 8 littéraux figés de `portfolio_api.py:22-29` par la source retenue
- **Objectif** : publier `n_trades`, `n_wins`, `n_losses`, `win_rate_pct`, `profit_factor`,
  `expectancy_pct`, `max_drawdown_pct`, `sharpe` depuis la source unique arbitrée par REST-001,
  ou `null` pour les champs qu'aucun producteur existant ne fournit.
- **Pourquoi** : ces 8 champs sont aujourd'hui des **constantes littérales à 0**. Le dashboard affiche
  donc `win_rate = 0 %` alors que `PaperLedger.summary()` (`paper_trading/ledger.py:191`) mesure 28 %
  sur la même session. Deux surfaces du même système publient deux vérités incompatibles.
- **Diagnostic résumé** : `visualization/api/portfolio_api.py:22-29` construit `PortfolioSnapshot`
  (`visualization/api/models.py:69`) avec `n_trades=0, n_wins=0, n_losses=0, win_rate_pct=0.0,
  profit_factor=0.0, expectancy_pct=0.0, max_drawdown_pct=0.0, sharpe=0.0` — valeurs écrites en dur,
  jamais calculées. Producteurs réels existants : `paper_trading/ledger.py:191` (`n_trades`, `win_rate`,
  `max_drawdown_pct`) ; `analysis/base.py:88` et `:125` (lignée scientifique, **à ne pas appeler depuis
  l'API**) ; `certification/operator_signoff.py:46` (4ᵉ lignée). L'audit SSoT classe `win_rate` et
  `drawdown` en **FAIL** avec ~5 producteurs chacun : ce ticket ne doit pas en créer un sixième.
- **Contexte** : ticket **conditionné par REST-001** (la source doit être tranchée avant d'être câblée).
  C'est le ticket le plus exposé au risque de recalcul : la tentation d'un `sum()` local est directe.
- **Hypothèses** :
  - H1 — la source retenue par REST-001 est appelable depuis le process qui sert l'API.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H2 — la source applique `CLEAN_DATA_SINCE_ACTIVE`, ou son absence d'application est documentée
    dans l'ADR REST-001. **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H3 — les champs non couverts sont publiables à `null` sans casser un consommateur (cf REST-002 H1).
- **Invariants** : INV-1 à INV-4 ; INV-R2 (**zéro recalcul ajouté** — invariant central du ticket) ;
  INV-R4 (borne d'époque) ; INV-R6 (`null`, jamais `0`) ; INV-R8 (provenance publiée).
- **Fichiers** : `visualization/api/portfolio_api.py` ; éventuellement `visualization/api/models.py`
  si un champ doit devenir optionnel. **≤ 2 fichiers, ≤ 60 lignes.**
- **Pseudo-code** (description, non exécutable) :

```
source <- SOURCE_RETENUE_PAR_REST_001            # un seul nom, fixe dans l'ADR

POUR CHAQUE champ DANS [n_trades, n_wins, n_losses, win_rate_pct,
                        profit_factor, expectancy_pct, max_drawdown_pct, sharpe] :
    SI source FOURNIT le champ TEL QUEL
        valeur <- source.champ                    # lecture seule, aucune transformation
    SINON
        valeur <- NULL                            # on ne le calcule PAS ici
                                                  # (creerait un 6e producteur -> INV-R2)

PUBLIER AUSSI provenance = { source, fichier:ligne, borne_epoque, horodatage }

INTERDIT DANS CE FICHIER : sum(), len() sur des trades, division, moyenne,
                           ecart-type, boucle sur un historique de trades
```

- **Plan d'action** :
  1. Relire l'ADR produit par REST-001 et en extraire : source retenue, champs fournis, champs `null`.
  2. Relever la baseline des tests.
  3. Remplacer les 8 littéraux par des lectures de la source, ou par `null`.
  4. Ajouter le champ de provenance (INV-R8).
  5. Vérifier par lecture qu'aucune opération arithmétique n'a été introduite dans le fichier.
  6. Vérifier la cohérence croisée : la valeur publiée pour `win_rate_pct` est **identique, chiffre pour
     chiffre**, à celle du producteur nommé.
  7. Tests, puis commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. L'étape 1 est bloquante : sans ADR, le ticket
  n'est pas démarrable (dépendance dure).
- **Tests** : `python -m pytest tests/visualization/ -q` ; `python -m pytest tests/ -q`.
  Plus un contrôle manuel de cohérence croisée (étape 6).
- **Validation** :
  - Aucun des 8 champs n'est un littéral figé.
  - Chaque champ publié est traçable à un `fichier:ligne` de producteur existant.
  - Les champs non couverts valent `null`, jamais `0`.
  - Aucune arithmétique dans `visualization/`.
- **Rollback** : `git revert <sha REST-003>`. Retour aux littéraux à 0. Sans effet sur la décision.
- **Risques** : R2 (recalcul introduit — risque principal) ; R4 (mélange d'époques si la borne n'est pas
  appliquée) ; R5 (lecture non atomique) ; R7 (`null` mal toléré).
- **Temps estimé** : 3 h – 5 h.
- **Dépendances** : **REST-001 (dure)**. REST-002 recommandé avant, pour ne pas mêler deux corrections
  dans un même diff.
- **Démonstration de non-décision** : lecture seule, dans la couche HTTP. Ne touche ni `PositionManager`,
  ni `check_new_trade`, ni le sizing, ni le risk, ni `PortfolioBrain` en entrée de décision.
  **Aucun reset d'époque, N inchangé.**
- **Critères Done** :
  - `grep -nE "=\s*0\.0|=\s*0\b" visualization/api/portfolio_api.py` ne retourne plus aucun des 8 champs.
  - Le fichier ne contient ni `sum(`, ni `/`, ni `mean`, ni boucle sur des trades.
  - `python -m pytest tests/ -q` identique à la baseline (hors tests adaptés par REST-004).
  - La valeur de `win_rate_pct` publiée est identique à celle du producteur nommé.
- **Critères Refus** :
  - Une métrique est calculée dans `visualization/` ⇒ refus immédiat (INV-R2).
  - Deux sources différentes alimentent deux champs sans que l'ADR l'ait prévu ⇒ refus.
  - Un champ indisponible est publié à `0` ⇒ refus (INV-R6).
  - La provenance n'est pas publiée ⇒ refus (INV-R8).

---

### REST-004

- **ID** : REST-004
- **Titre** : Adapter `tests/visualization/test_snapshot_only_loaders.py` aux nouvelles valeurs publiées
- **Objectif** : mettre les tests du loader REST en accord avec le contrat établi par REST-001/002/003,
  et **ajouter un test de garde** interdisant le retour des littéraux figés.
- **Pourquoi** : sans test de garde, rien n'empêche un futur contributeur de réintroduire
  `win_rate_pct=0.0` « pour faire passer un test ». Le défaut corrigé doit devenir impossible à recréer
  silencieusement.
- **Diagnostic résumé** : `tests/visualization/test_snapshot_only_loaders.py` valide aujourd'hui le
  comportement du loader tel qu'il est, donc potentiellement les littéraux figés de
  `visualization/api/portfolio_api.py:22-29`. Après REST-002/003, ces assertions deviennent fausses.
- **Contexte** : dernier ticket de la phase. Il ferme la boucle : sans lui, la phase laisse des tests
  en désaccord avec le code.
- **Hypothèses** :
  - H1 — le fichier de test existe et couvre effectivement `load_portfolio_snapshot`.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H2 — aucun autre fichier de test n'asserte les valeurs des 8 champs.
    **A CONFIRMER AU DEMARRAGE DU TICKET** (si oui, l'ajouter au périmètre, dans la limite de 4 fichiers).
- **Invariants** : INV-1 à INV-4 ; INV-R2 ; INV-R6. Un test ne doit **jamais** asserter qu'un champ
  indisponible vaut `0`.
- **Fichiers** : `tests/visualization/test_snapshot_only_loaders.py` (+ au plus 1 autre fichier de test).
  **≤ 2 fichiers.** Aucun fichier de production.
- **Pseudo-code** (description, non exécutable) :

```
ADAPTER les assertions existantes au nouveau contrat de publication

AJOUTER test_garde_pas_de_litteraux_figes :
    CHARGER le snapshot REST
    POUR CHAQUE champ DANS les 8 champs :
        ASSERTER  champ EST NULL  OU  champ PROVIENT de la source nommee
        ASSERTER  NON (champ == 0.0 ET source == "aucune")   # le defaut d'origine

AJOUTER test_total_pnl_n_est_pas_open_pnl :
    ASSERTER  total_pnl_usd != open_pnl_usd  OU  total_pnl_usd EST NULL

AJOUTER test_provenance_publiee :
    ASSERTER  le champ de provenance existe et nomme une source
```

- **Plan d'action** :
  1. Relever la baseline des tests.
  2. Lire le fichier de test et identifier les assertions devenues fausses.
  3. Adapter ces assertions au contrat REST-001.
  4. Ajouter les trois tests de garde du pseudo-code.
  5. Vérifier que les nouveaux tests **échouent** sur le code d'avant REST-002/003 (valeur de garde
     réelle) — contrôle par `git stash` ou sur une copie, sans commit.
  6. Lancer la suite complète, comparer à la baseline.
  7. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. L'étape 5 est essentielle : un test de garde qui passe
  aussi sur le code bugué ne garde rien.
- **Tests** : `python -m pytest tests/visualization/ -q` puis `python -m pytest tests/ -q`.
- **Validation** :
  - Les trois tests de garde existent et passent.
  - Ils échouent sur le code antérieur à REST-002/003 (vérifié à l'étape 5).
  - Aucun fichier de production modifié.
- **Rollback** : `git revert <sha REST-004>`. Les tests reviennent à l'état antérieur ; le code de
  production reste corrigé (REST-002/003 restent en place).
- **Risques** : R7 ; risque de test tautologique (mitigé par l'étape 5).
- **Temps estimé** : 2 h – 3 h.
- **Dépendances** : **REST-002 et REST-003 (dures)**.
- **Démonstration de non-décision** : ne modifie que des fichiers de test. Ne touche ni `PositionManager`,
  ni `check_new_trade`, ni le sizing, ni le risk, ni `PortfolioBrain`.
  **Aucun reset d'époque, N inchangé.**
- **Critères Done** :
  - `git diff --name-only` ne liste que des chemins sous `tests/`.
  - `python -m pytest tests/ -q` : 0 échec.
  - Les trois tests de garde sont nommés explicitement et documentés d'une ligne chacun.
- **Critères Refus** :
  - Un fichier de production apparaît au diff ⇒ refus.
  - Un test de garde passe aussi sur le code bugué ⇒ refus (tautologique).
  - Une assertion attend `0` pour un champ indisponible ⇒ refus (INV-R6).
  - Un test étranger au périmètre est modifié pour le faire passer ⇒ refus.

---

## Ordre

Séquence d'exécution imposée pour la phase :

```
REST-001  (ADR, documentaire)  ──┐
                                 ├──►  REST-003  ──►  REST-004
REST-002  (fix ligne 30)  ───────┘
```

- **REST-001** et **REST-002** sont démarrables en parallèle (REST-002 n'a pas de dépendance dure).
- **REST-003** exige REST-001 terminé (source tranchée) et REST-002 recommandé (diffs séparés).
- **REST-004** exige REST-002 et REST-003 terminés.

## Priorité

| Ticket | Priorité | Justification |
|---|---|---|
| REST-002 | **P1** | Seul défaut publiant une valeur activement **fausse** (et non absente). |
| REST-001 | **P1** | Bloquant pour REST-003 ; documentaire, donc sans risque. |
| REST-003 | **P2** | Corrige 8 champs faux, mais aucun n'induit en erreur autant que REST-002. |
| REST-004 | **P2** | Ferme la boucle ; sans lui, tests et code divergent. |

## Statut

**PRET** — aucun ticket de cette phase ne touche l'entrée de décision.

Tous les tickets sont en **lecture seule côté décision** : ils modifient la couche de publication HTTP
(`visualization/api/`) et les tests associés. Aucun ne lit ni n'écrit `PositionManager`,
`check_new_trade`, le sizing, le risk ou `PortfolioBrain` en entrée de décision.

**Aucun reset d'époque. N inchangé. Phase exécutable sous le gel scientifique en vigueur.**

Réserve explicite : la phase corrige la **publication**, pas la **production** des métriques.
Les FAIL SSoT structurels sur `win_rate`, `drawdown`, `capital` et `PnL` (≈5 producteurs concurrents
chacun) subsistent après PHASE_03 — leur résolution relève de PHASE_02_GATED et PHASE_04_GATED.
