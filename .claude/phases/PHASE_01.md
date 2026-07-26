# PHASE_01 — Panneau honnête (architecture A)

**Préfixe d'ID de tickets : `OBS-###`** (aucun autre préfixe n'est autorisé dans ce document).

**Statut de gating : NON GATED — exécutable sous le gel fonctionnel.**
Architecture retenue : **A** (l'affichage dérive du même store que le compte de positions,
`_virtual_portfolio`, sans jamais toucher `pos_manager`). Aucun reset d'époque, aucun reset de N.

---

## Objectif

Rendre le panneau Telegram **interne­ment cohérent** : dans un même panneau, le nombre de positions et
l'exposition/le cash doivent provenir du **même store**.

Objectif mesurable, en trois assertions binaires :

1. Quand `_virtual_portfolio` porte K positions ouvertes (K > 0), le panneau affiche
   `portfolio_exposure_pct > 0` et non `0.0%`.
2. `free_cash` affiché n'est plus le produit d'une exposition nulle
   (fin du symptôme `674.47 * 0.40 - 0 = 269.79`).
3. Le verdict de `check_new_trade` est **strictement identique** avant/après la phase, sur les mêmes entrées
   (invariant **INV-2**, figé par un test de garde écrit en premier).

Non-objectif explicite : **corriger la décision**. La décision reste alimentée par `pos_manager`, donc
reste aveugle aux positions paper. Ce résidu est assumé, documenté (OBS-004) et traité en PHASE_02_GATED.

---

## Contexte

Diagnostic validé (ne pas ré-enquêter) :

- `core/advisor_loop.py:6785-6787` appelle `portfolio_brain.portfolio_health(pos_manager.get_open())`.
  En mode paper, `pos_manager` est **vide** : les positions sont ouvertes dans `_virtual_portfolio`
  (`MexcSimulator`) via `place_market_order` (`core/advisor_loop.py:2176`).
- `quant_hedge_ai/agents/risk/portfolio_brain.py:668-687` `_snapshot()` somme `p.size_usd` sur la liste
  reçue ; liste vide ⇒ `total_exposure_usd = 0` ⇒ `total_exposure_pct = 0`.
- `quant_hedge_ai/agents/risk/portfolio_brain.py:645-664` `portfolio_health()` renvoie
  `total_exposure_pct`, `n_positions`, `capital`,
  `free_capital = max(0, capital * MAX_TOTAL_EXPOSURE_PCT - total_exposure_usd)`,
  avec `MAX_TOTAL_EXPOSURE_PCT = 0.40` (`portfolio_brain.py:88`).
- `core/advisor_loop.py:6788` `_display_position_summary(_virtual_portfolio, pb_health)` renvoie `n_open`
  depuis `_virtual_portfolio.get_open_positions_summary()` (`advisor_loop.py:450-453`), avec fallback
  `pb_health` si le store est `None` (`advisor_loop.py:456-459`).
- **Premier point d'incohérence : `core/advisor_loop.py:6786`** (mauvais store passé à `portfolio_health`).
- Preuve numérique : `free_cash = 269.79 = 674.47 * 0.40 - 0` ⇒ `total_exposure_usd = 0` confirmé.
- Preuve secondaire : le bloc `POSITIONS:` est absent des rapports (condition `open_count > 0`,
  `advisor_loop.py:6971`) ⇒ `pos_manager` vide.
- Bug **documenté et gelé volontairement** : docstring `core/advisor_loop.py:437-448` — « `pos_manager` reste
  la source des contraintes de décision … jamais modifié ici, corriger son entrée changerait le comportement
  de décision en pleine validation scientifique ». Régression historique tracée `advisor_loop.py:462-471`
  (2026-07-12 21:00 UTC : `POSITIONS 0` affiché alors que le ledger MexcSim portait BTC/BNB/ETH).

Audit SSoT de référence : **0 PASS / 1 WARNING / 8 FAIL**. La phase 01 ne prétend pas résoudre les 8 FAIL ;
elle traite **exclusivement la ligne d'affichage** (exposure, paper_cash, free_cash, positions) du panneau
CYCLE et du panneau HEARTBEAT.

Cadre de gouvernance applicable : ADR-0007 (passivité absolue des observers), Scientific Debt Rule
(gel architectural, seuls les outils de mesure/audit sont autorisés), règle du statisticien
(aucune calibration avant les seuils), borne d'époque `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`.
L'architecture A est compatible avec les trois : elle ne modifie **aucune entrée de décision**, donc
**ne crée pas de nouvelle époque**.

---

## Dépendances

| Dépendance | Nature | Statut |
|---|---|---|
| PHASE_00 (`GOV-*`) — charte de gating, registre des invariants, protocole de commit | Amont, documentaire | Contenu exact **A CONFIRMER AU DEMARRAGE DU TICKET** (`.claude/phases/PHASE_00.md` non lu par cet agent) |
| `docs/protocole_audit_epistemique.md` (v3) | Amont, méthodologique — chaque ticket sépare Observation / Inférence / Hypothèse / Décision | Présent dans `main` |
| `CLAUDE.md` (règles invariantes) | Amont, normatif | Présent |
| PHASE_02_GATED (`SSOT-*`) | **Aval** — consomme les tests OBS-001 comme filet | Bloqué (voir PHASE_02_GATED) |
| PHASE_03 (`REST-*`) | Aval, indépendant — la couche REST a ses propres valeurs codées en dur | Non bloquant |

Aucune dépendance envers un déploiement VPS : la phase est validable en local par tests.

---

## Prérequis

1. Dépôt sur `main` propre (`git status` vide) avant le premier ticket.
2. Suite de tests exécutable en local : `python -m pytest tests/ -q` (temps de référence et taux de succès
   de départ à noter avant OBS-001 — **A CONFIRMER AU DEMARRAGE DU TICKET**).
3. Lecture préalable, sans modification, de :
   - `core/advisor_loop.py:434-471` (docstring de gel + régression historique),
   - `core/advisor_loop.py:6785-6906` (builder CYCLE),
   - `core/advisor_loop.py:7444-7482` (builder HEARTBEAT),
   - `observability/system_snapshot.py:56` (champs de `PortfolioSnapshot`),
   - `quant_hedge_ai/agents/risk/portfolio_brain.py:645-687`.
4. Confirmation de la **surface d'API réellement exposée** par `_virtual_portfolio` (`MexcSimulator`,
   `paper_trading/mexc_simulator.py:230`) : `get_open_positions_summary()` est connu
   (`advisor_loop.py:450-453`) ; l'existence d'un accès au **notional par position** et au **PnL ouvert**
   est **A CONFIRMER AU DEMARRAGE DU TICKET** (OBS-002, étape 1).
5. Aucune modification de `.env`, `runtime_config.json`, ni de la configuration VPS pendant la phase.

---

## Risques

| ID | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | **Un panneau honnête masque que la décision reste aveugle.** L'opérateur lit « exposition 43 % » et suppose que le moteur en tient compte ; il ne le fait pas. | Élevée | Élevé — fausse confiance opérationnelle | OBS-004 : libellés distincts `exposition d'affichage` vs `exposition-gate`, plus commentaire de code normatif au point de calcul |
| R2 | Dérive de périmètre : la correction « glisse » vers `portfolio_health()` en entrée de décision | Moyenne | Critique — reset de N, burn-in détruit | Critère de refus binaire dans chaque ticket : tout diff touchant `pos_manager`, `check_new_trade`, le sizing ou le risk ⇒ ticket rejeté |
| R3 | Régression du mode non-paper (`_virtual_portfolio is None`) | Moyenne | Moyen | Fallback `pb_health` obligatoire + test dédié dans OBS-001 |
| R4 | Divergence CYCLE / HEARTBEAT (un panneau corrigé, l'autre non) | Élevée si OBS-003 est omis | Moyen — incohérence inter-panneaux à la place de l'incohérence intra-panneau | OBS-003 obligatoire, test de parité |
| R5 | L'API de `_virtual_portfolio` n'expose pas le notional par position ⇒ recalcul approximatif | Inconnue | Moyen | Étape 1 d'OBS-002 : constat écrit ; si l'information manque, le ticket s'arrête et remonte la question au lieu d'inventer une estimation |
| R6 | Un test existant fige l'ancien comportement (`exposure == 0`) et casse | Moyenne | Faible | Inventaire des tests impactés dans OBS-001 : `tests/test_system_snapshot.py:31-36`, `tests/test_state_integrity.py:51-56` et `:277-285`, `tests/capital_deployment/test_capital_lines.py:22-48`, `tests/visualization/test_snapshot_only_loaders.py` |
| R7 | Confusion `paper_cash` / `free_cash` persistante (WARNING de l'audit SSoT) | Élevée | Moyen | OBS-002 : les deux valeurs sont dérivées du même store et leur définition est écrite en commentaire ; aucune des deux n'est supprimée |

---

## Architecture

Architecture **A**, une seule règle :

> Tout chiffre affiché dans un panneau donné dérive du store qui compte les positions de ce même panneau.

En mode paper, ce store est `_virtual_portfolio`. Le chemin cible :

```
_virtual_portfolio (MexcSimulator)
        |
        +--> positions ouvertes ------> n_open (deja le cas, advisor_loop.py:450-453)
        +--> notional deploye --------> portfolio_exposure_pct   (NOUVEAU chemin)
        +--> notional deploye --------> paper_cash / free_cash   (NOUVEAU chemin)

pos_manager (PositionManager)
        |
        +--> portfolio_health() ------> ENTREE DE DECISION : INCHANGEE
        +--> fallback d'affichage SI _virtual_portfolio is None
```

Trois propriétés structurelles :

1. **Aucun nouveau store, aucune nouvelle couche.** On rebranche une lecture existante, on n'ajoute pas de
   composant (conformité Scientific Debt Rule).
2. **Sens unique.** `_virtual_portfolio` alimente l'affichage ; l'affichage n'écrit nulle part
   (conformité ADR-0007 : observer strictement passif).
3. **Fallback conservateur.** `_virtual_portfolio is None` ⇒ comportement actuel bit-à-bit
   (`pb_health`), donc le mode non-paper est un no-op.

Ce qui **n'est pas** fait en PHASE_01 (renvoyé à PHASE_02_GATED / PHASE_04_GATED) :
unification des 4 stores de positions, des 3 classes `PortfolioSnapshot`
(`observability/system_snapshot.py:56`, `quant_hedge_ai/agents/risk/portfolio_brain.py:64`,
`visualization/api/models.py:69`), des 2 classes `PortfolioBrain`, des 2 classes `SystemSnapshot`.

---

## Fichiers concernés

| Fichier | Lignes de référence | Type d'intervention en PHASE_01 |
|---|---|---|
| `core/advisor_loop.py` | 6788-6906 (builder CYCLE) | Modification (OBS-002) |
| `core/advisor_loop.py` | 7444-7482 (builder HEARTBEAT) | Modification (OBS-003) |
| `core/advisor_loop.py` | 434-471 (docstring de gel, régression) | Commentaires uniquement (OBS-004) |
| `core/advisor_loop.py` | 6785-6787 (`portfolio_health(pos_manager.get_open())`) | **Lecture seule — NON MODIFIÉ** (entrée de décision) |
| `observability/system_snapshot.py` | 56 (`PortfolioSnapshot`), 132, 143 | Lecture seule ; aucun champ ajouté ni renommé en PHASE_01 |
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | 88, 645-664, 668-687 | **Lecture seule — NON MODIFIÉ** |
| `paper_trading/mexc_simulator.py` | 230 | **Lecture seule — NON MODIFIÉ** |
| `paper_trading/ledger.py` | 121, 191 | **Lecture seule — NON MODIFIÉ** |
| `system/integrity_snapshot.py` | 100-135 | Modification optionnelle (OBS-005) |
| `tests/` (nouveau fichier de régression) | — | Création (OBS-001) |
| `tests/test_system_snapshot.py` | 31-36 | Ajustement possible (OBS-001, inventaire) |
| `tests/test_state_integrity.py` | 51-56, 277-285 | Ajustement possible (OBS-001, inventaire) |
| `tests/capital_deployment/test_capital_lines.py` | 22-48 | Ajustement possible (OBS-001, inventaire) |
| `tests/visualization/test_snapshot_only_loaders.py` | — | Ajustement possible (OBS-001, inventaire) |

Fichiers **interdits d'écriture sur toute la phase** : `core/decision*`, tout appelant de
`check_new_trade`, `quant_hedge_ai/agents/risk/*`, `paper_trading/*`, `databases/*.jsonl`,
`databases/positions_snapshot.json`, `.env`, `runtime_config.json`.

---

## Invariants

| ID | Énoncé | Vérification |
|---|---|---|
| **INV-1** | Aucune écriture nouvelle ou modifiée dans `paper_trades.jsonl` ni dans `databases/positions_snapshot.json`. Les seuls écrivains restent `paper_trading/mexc_simulator.py` et `paper_trading/recorder.py`. | `git diff --stat` ne contient aucun fichier de `paper_trading/` ; recherche de `paper_trades.jsonl` dans le diff = 0 occurrence |
| **INV-2** | Le verdict de `check_new_trade` est identique avant/après, sur des entrées identiques. | Test de garde OBS-001 (vert avant, vert après chaque ticket) |
| **INV-3** | `pos_manager` n'est ni muté, ni remplacé, ni contourné dans son rôle d'entrée de décision. `core/advisor_loop.py:6786` reste littéralement inchangé. | `git diff core/advisor_loop.py` : la ligne d'appel `portfolio_health(pos_manager.get_open())` n'apparaît pas dans le diff |
| **INV-4** | Aucune nouvelle couche décisionnelle, aucun nouvel indicateur, aucune nouvelle stratégie, aucun seuil modifié. | Revue de diff ; aucun littéral numérique de seuil ajouté hors formatage d'affichage |
| **INV-5** | Mode non-paper (`_virtual_portfolio is None`) : comportement strictement identique à l'existant (fallback `pb_health`). | Test dédié OBS-001 |
| **INV-6** | Aucun reset d'époque. `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` reste la borne active ; `scripts/data_quality.py` et `tools/cri_calculator.py` ne sont pas touchés. | `git diff --stat` ne contient ni `scripts/data_quality.py` ni `tools/cri_calculator.py` |
| **INV-7** | Passivité (ADR-0007) : le code d'affichage ne rappelle aucune fonction à effet de bord (ordre, écriture d'état, mutation de position). | Revue de diff : le diff ne contient que des lectures + formatage |

---

## Validation

Validation de phase (à exécuter après OBS-004, avant clôture) :

1. `python -m pytest tests/ -q` — aucun échec nouveau par rapport à la baseline notée en Prérequis.
2. `python -m pytest <fichier de régression OBS-001> -q` — 100 % vert, dont le test initialement rouge.
3. `git diff --stat main...HEAD` — aucun fichier hors de la liste « Fichiers concernés »,
   aucun fichier de `paper_trading/`, `quant_hedge_ai/agents/risk/`, `scripts/`, `tools/`.
4. Contrôle visuel d'un panneau CYCLE et d'un panneau HEARTBEAT produits par le même cycle :
   `positions` et `exposition d'affichage` sont cohérents entre eux **et entre les deux panneaux**.
   (Sur données locales ou fixture ; **aucun déploiement VPS n'est requis pour valider la phase**.)
5. Contrôle épistémique (protocole v3) : le document de clôture de phase distingue explicitement
   ce qui est **observé** (le panneau affiche X) de ce qui est **inféré** (le moteur voit X) —
   et rappelle que la seconde proposition reste **fausse** après PHASE_01.

Deux falsificateurs de la phase (à écrire dans la clôture) :

- **F1** : si, avec K > 0 positions dans `_virtual_portfolio`, un panneau affiche encore
  `portfolio_exposure_pct == 0`, la phase a échoué.
- **F2** : si le verdict de `check_new_trade` diffère sur un seul cas du test de garde,
  la phase a échoué et doit être intégralement révoquée (INV-2 violé ⇒ risque de nouvelle époque).

---

## Rollback

- Granularité : **1 ticket = 1 commit** ⇒ `git revert <sha>` d'un seul ticket est toujours possible.
- Ordre de revert recommandé si la phase entière doit être annulée : OBS-005, OBS-004, OBS-003, OBS-002,
  puis OBS-001 en dernier (les tests sont le filet ; on les retire en dernier).
- Rollback sans risque de données : aucun ticket n'écrit de données de trading, donc **aucun rollback ne
  peut corrompre le dataset** ni décaler la borne d'époque (INV-1, INV-6).
- Aucun rollback VPS n'est nécessaire tant que la phase n'est pas déployée. Si elle l'a été, le geste de
  retour est un nouveau déploiement délibéré du commit précédent :
  `bash scripts/deploy_vps.sh --confirm` (jamais automatique), redémarrage en double opt-in.

---

## Estimation

| Ticket | Estimation | Fichiers | Lignes modifiées (ordre de grandeur) |
|---|---|---|---|
| OBS-001 | 3 h – 5 h | 1 créé + 0 à 4 ajustés | ≤ 250 |
| OBS-002 | 3 h – 4 h | 1 | ≤ 80 |
| OBS-003 | 1 h – 2 h | 1 | ≤ 60 |
| OBS-004 | 1 h | 1 | ≤ 60 (commentaires + libellés) |
| OBS-005 (optionnel) | 1 h – 2 h | 1 | ≤ 50 |
| **Total phase** | **1 à 2 jours** | — | **≤ 500 cumulées** |

Chaque ticket respecte la contrainte d'atomicité : ≤ 300 lignes modifiées **et** ≤ 4 fichiers.

---

## Tickets

### OBS-001

- **ID** : OBS-001
- **Titre** : Tests de régression d'abord — rouge « exposition d'affichage nulle » + garde verte INV-2
- **Objectif** : produire, avant toute correction, (a) un test **rouge** qui reproduit
  « K positions dans `_virtual_portfolio` ⇒ `portfolio_exposure_pct == 0` dans le panneau » et
  (b) un test **vert** de garde figeant le verdict de `check_new_trade` (INV-2), plus (c) un test **vert**
  de non-régression du mode non-paper (INV-5).
- **Pourquoi** : sans test rouge préalable, rien ne prouve que la correction corrige quelque chose ;
  sans test de garde, rien ne prouve qu'elle n'a pas déplacé la décision — donc rien ne prouve que
  l'époque courante survit. Le test de garde est la seule preuve exécutable que N n'est pas remis à zéro.
- **Diagnostic résumé** :
  1. `core/advisor_loop.py:6785-6787` : `portfolio_health(pos_manager.get_open())`.
  2. En mode paper, `pos_manager` est vide ; les positions vivent dans `_virtual_portfolio`
     (`MexcSimulator`), remplies par `place_market_order` (`advisor_loop.py:2176`).
  3. `portfolio_brain.py:668-687` somme `p.size_usd` sur une liste vide ⇒ `total_exposure_usd = 0`.
  4. `portfolio_brain.py:645-664` ⇒ `free_capital = max(0, capital*0.40 - 0)`
     (`MAX_TOTAL_EXPOSURE_PCT = 0.40`, `portfolio_brain.py:88`) ⇒ `269.79` pour un capital `674.47`.
  5. `advisor_loop.py:6788` prend `n_open` dans `_virtual_portfolio` (`advisor_loop.py:450-453`).
  6. Même panneau, deux sources ⇒ `Positions: 3` et `Portfolio Exposure: 0.0%`.
  7. Le bloc `POSITIONS:` (`advisor_loop.py:6971`, condition `open_count > 0`) est absent : deuxième preuve
     que `pos_manager` est vide.
- **Contexte** : PHASE_01 applique l'architecture A. Ce ticket ne corrige rien ; il installe le filet.
  Les tests existants susceptibles de figer l'ancien comportement sont listés dans « Fichiers ».
- **Hypothèses** :
  - H1 — un `MexcSimulator` (ou un double de test) peut être instancié et peuplé de K positions ouvertes
    dans un test unitaire, sans réseau. **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H2 — le builder de panneau CYCLE (`advisor_loop.py:6788-6906`) est atteignable en test sans démarrer la
    boucle complète (fonction ou fragment isolable). Si ce n'est pas le cas, le test rouge cible directement
    le couple `(_virtual_portfolio, pb_health)` passé aux fonctions d'affichage
    (`_display_position_summary:434-459`, `_positions_for_display:462+`).
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H3 — `check_new_trade` est appelable en test avec des entrées fixées. **A CONFIRMER AU DEMARRAGE DU
    TICKET** (localisation exacte du point d'appel : non fournie par le diagnostic).
- **Invariants** : INV-1, INV-2 (c'est le ticket qui la matérialise), INV-3, INV-4, INV-5, INV-6, INV-7.
- **Fichiers** :
  - `tests/test_display_exposure_consistency.py` (créé)
  - jusqu'à 3 fichiers de tests existants ajustés **uniquement s'ils figent l'ancien comportement** :
    `tests/test_system_snapshot.py:31-36`, `tests/test_state_integrity.py:51-56` et `:277-285`,
    `tests/capital_deployment/test_capital_lines.py:22-48`,
    `tests/visualization/test_snapshot_only_loaders.py`.
    Si plus de 3 doivent bouger, **couper le ticket en OBS-001a / OBS-001b** (atomicité).
  - Aucun fichier de production modifié.
- **Pseudo-code** (description, non exécutable) :

```
TEST 1  — ROUGE ATTENDU  « exposition d'affichage incoherente »
    ETANT DONNE un store virtuel peuple de 3 positions ouvertes
                (notional connu, par exemple 100 + 100 + 50 unites de compte)
    ET        un pos_manager VIDE
    ET        un pb_health obtenu depuis ce pos_manager vide
    QUAND     on construit le bloc d'affichage du panneau CYCLE
    ALORS     n_open VAUT 3
    ET        exposition_affichee DOIT ETRE STRICTEMENT SUPERIEURE A 0     <-- ECHOUE AUJOURD'HUI
    ET        free_cash_affiche NE DOIT PAS VALOIR capital * 0.40          <-- ECHOUE AUJOURD'HUI
    MARQUER   ce test comme « attendu rouge jusqu'a OBS-002 »

TEST 2  — VERT DE GARDE  « INV-2 : la decision ne bouge pas »
    ETANT DONNE un jeu FIGE de cas d'entree de check_new_trade
                (liste enregistree une fois pour toutes, sans aleatoire, sans horloge)
    QUAND     on evalue check_new_trade sur chaque cas
    ALORS     le verdict ET le motif de refus SONT IDENTIQUES a la reference figee
    NOTE      ce test doit etre VERT AVANT et APRES chaque ticket de la phase

TEST 3  — VERT  « INV-5 : mode non-paper inchange »
    ETANT DONNE store_virtuel = ABSENT
    QUAND     on construit le bloc d'affichage
    ALORS     les valeurs proviennent de pb_health, a l'identique de l'existant

TEST 4  — VERT  « INV-1 : aucun effet de bord »
    ETANT DONNE un repertoire de donnees observe
    QUAND     on construit le bloc d'affichage
    ALORS     aucun fichier de donnees n'est cree, modifie ni ouvert en ecriture
```

- **Plan d'action** :
  1. Exécuter la suite complète et **noter la baseline** (nombre de tests, échecs préexistants, durée).
  2. Lire `advisor_loop.py:434-471` et `:6785-6906` pour identifier le point d'accroche testable.
  3. Confirmer H1/H2/H3 ; consigner par écrit ce qui est confirmé et ce qui ne l'est pas.
  4. Écrire TEST 2 (garde INV-2) **en premier** et vérifier qu'il est vert sur `main` inchangé.
  5. Écrire TEST 1 et vérifier qu'il est **rouge** pour la raison attendue (exposition nulle), pas pour une
     erreur d'import ou de fixture.
  6. Écrire TEST 3 et TEST 4, vérifier verts.
  7. Inventorier les tests existants qui figent l'ancien comportement ; ne toucher que ceux qui cassent
     réellement, avec un commentaire de justification par assertion modifiée.
  8. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Ne pas écrire TEST 1 avant que TEST 2 soit vert.
- **Tests** : c'est le livrable du ticket. Commandes :
  - `python -m pytest tests/test_display_exposure_consistency.py -q`
  - `python -m pytest tests/ -q`
- **Validation** :
  - TEST 1 rouge, avec message d'échec citant l'exposition attendue > 0 et l'exposition obtenue 0.
  - TEST 2, TEST 3, TEST 4 verts.
  - `git diff --stat` : uniquement des fichiers sous `tests/`.
- **Rollback** : `git revert <sha OBS-001>` — aucun impact production (le ticket ne touche aucun module
  de production).
- **Risques** : R6 (tests existants figeant l'ancien comportement) ; risque de fixture non déterministe
  (horloge, réseau) rendant TEST 2 instable ⇒ interdiction d'appel réseau et d'horloge courante dans les
  fixtures.
- **Temps estimé** : 3 h – 5 h.
- **Dépendances** : PHASE_00 (`GOV-*`) pour le format de commit — **A CONFIRMER AU DEMARRAGE DU TICKET**.
  Aucune dépendance code.
- **Critères Done** :
  - `python -m pytest tests/test_display_exposure_consistency.py -q` : 3 passés, 1 échoué (TEST 1),
    et l'échec mentionne explicitement l'exposition nulle.
  - `python -m pytest tests/ -q` : aucun échec nouveau hors TEST 1 par rapport à la baseline de l'étape 1.
  - `git diff --name-only` ne liste que des chemins commençant par `tests/`.
- **Critères Refus** :
  - Un seul fichier de production apparaît dans le diff ⇒ refus.
  - TEST 1 est rouge pour une autre raison que l'exposition nulle (import, fixture, attribut manquant)
    ⇒ refus.
  - TEST 2 est instable (deux exécutions consécutives donnent des verdicts différents) ⇒ refus.
  - Plus de 4 fichiers modifiés au total ⇒ refus, découper en OBS-001a / OBS-001b.

---

### OBS-002

- **ID** : OBS-002
- **Titre** : Builder de panneau CYCLE — exposition, `paper_cash` et `free_cash` dérivés de `_virtual_portfolio`
- **Objectif** : dans `core/advisor_loop.py:6788-6906`, calculer `portfolio_exposure_pct`, `paper_cash` et
  `free_cash` à partir de `_virtual_portfolio` (le store qui fournit déjà `n_open`), avec **fallback
  `pb_health` si `_virtual_portfolio is None`**.
- **Pourquoi** : c'est le point unique où le panneau CYCLE mélange deux sources. Corriger ici rend le panneau
  interne­ment cohérent sans toucher la décision (`advisor_loop.py:6786` reste intact).
- **Diagnostic résumé** :
  1. `advisor_loop.py:6786` : `pb_health = portfolio_brain.portfolio_health(pos_manager.get_open())` —
     source vide en paper, **et entrée de décision : ne pas y toucher**.
  2. `advisor_loop.py:6788` : `_display_position_summary(_virtual_portfolio, pb_health)` — source correcte
     pour le comptage (`advisor_loop.py:450-453`).
  3. `advisor_loop.py:6791-6799` : calcul de `_deployed_notional` / `_paper_equity` / `_paper_cash` —
     **c'est ici que se décide la ligne d'argent affichée**.
  4. `advisor_loop.py:6888-6906` : construction du `PortfolioSnapshot`
     (`observability/system_snapshot.py:56` : `paper_equity`, `paper_cash`, `free_cash`,
     `portfolio_exposure_pct`, `open_pnl_usd`, `open_positions`, `correlation_risk_pct`, `session_pnl_usd`).
  5. `portfolio_brain.py:645-664` + `:88` : `free_capital = max(0, capital*0.40 - exposure_usd)` — formule
     à **répliquer pour l'affichage**, sans modifier `portfolio_brain.py`.
  6. Preuve : `269.79 = 674.47*0.40 - 0`.
- **Contexte** : architecture A. Aucun store nouveau ; on remplace la provenance de trois nombres affichés.
  Le WARNING SSoT (`free_cash` producteur unique mais co-affiché avec un `paper_cash` contradictoire)
  est traité ici en rendant les deux valeurs dérivées du **même** notional.
- **Hypothèses** :
  - H1 — `_virtual_portfolio` expose le notional par position ouverte (ou de quoi le reconstituer sans
    approximation). **A CONFIRMER AU DEMARRAGE DU TICKET** (étape 1 du plan). Si l'information n'existe pas,
    **arrêter le ticket** et remonter la question ; ne pas estimer.
  - H2 — `PortfolioSnapshot` accepte les valeurs sans changement de schéma (aucun champ ajouté).
  - H3 — le capital de référence affiché reste `WALLET_PAPER_CAPITAL` (sizing épinglé, CLAUDE.md) ;
    aucune bascule vers une base equity. **A CONFIRMER AU DEMARRAGE DU TICKET** pour la valeur exacte utilisée
    au point 6791-6799.
- **Invariants** : INV-1, INV-2, INV-3 (`advisor_loop.py:6786` littéralement non modifié), INV-4, INV-5,
  INV-6, INV-7.
- **Fichiers** : `core/advisor_loop.py` (uniquement, plage 6788-6906). 1 fichier.
- **Pseudo-code** (description, non exécutable) :

```
DANS le builder du panneau CYCLE (advisor_loop, plage 6788-6906) :

    NE PAS TOUCHER la ligne 6786 (pb_health <- portfolio_health(pos_manager.get_open()))
    pb_health RESTE UTILISE : (a) en fallback d'affichage, (b) tel quel pour tout usage decisionnel existant

    SI store_virtuel EXISTE ALORS
        notional_deploye   <- SOMME DES notionals des positions ouvertes DU STORE VIRTUEL
        n_positions_aff    <- NOMBRE de positions ouvertes DU STORE VIRTUEL   (deja le cas)
        capital_reference  <- capital de reference d'affichage deja utilise lignes 6791-6799
        exposition_aff_pct <- notional_deploye / capital_reference       SI capital_reference > 0
                              SINON 0
        cash_papier_aff    <- capital_reference MOINS notional_deploye   (definition ECRITE en commentaire)
        cash_libre_aff     <- MAXIMUM(0, capital_reference * PLAFOND_EXPOSITION - notional_deploye)
                              OU PLAFOND_EXPOSITION est LU depuis portfolio_brain, JAMAIS recopie en dur
        SOURCE_AFFICHAGE   <- « store virtuel »
    SINON
        exposition_aff_pct <- pb_health.total_exposure_pct     (comportement actuel, inchange)
        cash_libre_aff     <- pb_health.free_capital           (comportement actuel, inchange)
        cash_papier_aff    <- valeur actuelle, inchangee
        SOURCE_AFFICHAGE   <- « pb_health (mode non-paper) »
    FIN SI

    CONSTRUIRE PortfolioSnapshot AVEC exposition_aff_pct, cash_papier_aff, cash_libre_aff
    (AUCUN champ ajoute, AUCUN champ renomme)

    INTERDIT : ecrire quoi que ce soit, appeler pos_manager, appeler check_new_trade,
               modifier portfolio_brain, modifier un seuil
```

- **Plan d'action** :
  1. Lire `paper_trading/mexc_simulator.py:230` et l'usage `advisor_loop.py:450-453` pour établir
     **précisément** quelles grandeurs le store expose ; écrire ce constat dans le message de commit.
  2. Si le notional n'est pas disponible sans approximation : **arrêter**, marquer le ticket BLOQUÉ,
     remonter la question. Ne pas inventer de proxy.
  3. Localiser exactement le calcul `advisor_loop.py:6791-6799` et le point de construction du snapshot
     `:6888-6906`.
  4. Introduire le calcul dérivé du store virtuel, avec la branche de fallback.
  5. Lire le plafond d'exposition depuis `portfolio_brain` (référence, pas duplication de la constante).
  6. Exécuter le test rouge d'OBS-001 : il doit passer au vert.
  7. Exécuter le test de garde INV-2 : il doit rester vert.
  8. Exécuter la suite complète ; corriger les seuls tests d'affichage qui figeaient l'ancienne valeur —
     s'ils sont plus de 3, les traiter dans un ticket séparé plutôt que d'élargir celui-ci.
  9. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. L'étape 7 ne peut pas être sautée ni reportée.
- **Tests** :
  - `python -m pytest tests/test_display_exposure_consistency.py -q` (TEST 1 doit devenir vert)
  - `python -m pytest tests/ -q`
- **Validation** :
  - Panneau CYCLE avec K > 0 positions ⇒ exposition affichée > 0 et `free_cash` ≠ `capital * plafond`.
  - `git diff core/advisor_loop.py` ne contient **pas** la ligne d'appel
    `portfolio_health(pos_manager.get_open())`.
  - Diff ≤ 80 lignes, 1 fichier.
- **Rollback** : `git revert <sha OBS-002>` ⇒ retour au panneau incohérent, aucun impact sur les données
  ni sur la décision (le ticket n'a jamais touché la décision).
- **Risques** : R1 (le panneau devient crédible alors que la décision reste aveugle — traité par OBS-004),
  R2 (dérive vers `portfolio_health`), R5 (API du store insuffisante), R7 (`paper_cash` vs `free_cash`).
- **Temps estimé** : 3 h – 4 h.
- **Dépendances** : OBS-001 (obligatoire — le test rouge doit exister avant).
- **Critères Done** :
  - `python -m pytest tests/test_display_exposure_consistency.py -q` : tous verts, 0 échec.
  - `python -m pytest tests/ -q` : aucun échec nouveau vs baseline OBS-001.
  - `git diff --name-only` retourne exactement `core/advisor_loop.py`.
  - `git diff core/advisor_loop.py | grep -c "pos_manager"` retourne `0`.
- **Critères Refus** :
  - Le diff contient `pos_manager`, `check_new_trade`, `portfolio_brain.py` ou un fichier de
    `paper_trading/` ⇒ refus immédiat (risque de nouvelle époque).
  - Le plafond d'exposition (0.40) est recopié en dur au lieu d'être lu depuis `portfolio_brain` ⇒ refus.
  - Un champ est ajouté ou renommé dans `PortfolioSnapshot` ⇒ refus (hors périmètre, casse PHASE_03).
  - Le fallback non-paper est absent ⇒ refus (INV-5).

---

### OBS-003

- **ID** : OBS-003
- **Titre** : Builder de panneau HEARTBEAT — parité stricte avec OBS-002
- **Objectif** : appliquer à `core/advisor_loop.py:7444-7482` exactement le même calcul d'exposition /
  `paper_cash` / `free_cash` que celui posé en OBS-002, avec le même fallback.
- **Pourquoi** : deux builders indépendants produisent deux panneaux. Corriger un seul remplacerait une
  incohérence intra-panneau par une incohérence inter-panneaux, plus difficile à diagnostiquer.
- **Diagnostic résumé** :
  1. Le builder HEARTBEAT (`advisor_loop.py:7444-7482`) construit un `PortfolioSnapshot` de la même famille
     que le builder CYCLE (`observability/system_snapshot.py:56`).
  2. La cause racine est la même : les positions vivent dans `_virtual_portfolio` (`MexcSimulator`,
     `paper_trading/mexc_simulator.py:230`), l'exposition vient d'un `pb_health` calculé sur un
     `pos_manager` vide (`advisor_loop.py:6785-6787`, `portfolio_brain.py:668-687`).
  3. `free_capital` obéit à la même formule `max(0, capital*0.40 - exposure_usd)`
     (`portfolio_brain.py:645-664`, `:88`).
  4. Le détail exact des sources utilisées par le builder HEARTBEAT (réutilise-t-il `pb_health`
     du cycle, ou recalcule-t-il ?) est **A CONFIRMER AU DEMARRAGE DU TICKET** — le diagnostic ne le
     tranche pas.
- **Contexte** : ticket mécanique, postérieur à OBS-002 dont il réutilise la logique. S'il apparaît que le
  calcul peut être factorisé sans toucher à une entrée de décision, la factorisation est autorisée à
  condition de rester dans `core/advisor_loop.py` et sous 60 lignes de diff.
- **Hypothèses** :
  - H1 — le builder HEARTBEAT a accès à `_virtual_portfolio` dans sa portée. **A CONFIRMER AU DEMARRAGE
    DU TICKET.** S'il n'y a pas accès, le ticket est reformulé (passage explicite du store en paramètre
    d'affichage) sans jamais élargir le périmètre à la décision.
- **Invariants** : INV-1, INV-2, INV-3, INV-4, INV-5, INV-6, INV-7.
- **Fichiers** : `core/advisor_loop.py` (plage 7444-7482, plus éventuellement le point de factorisation
  issu d'OBS-002). 1 fichier.
- **Pseudo-code** (description, non exécutable) :

```
DANS le builder du panneau HEARTBEAT (advisor_loop, plage 7444-7482) :

    REUTILISER LA MEME REGLE QU'EN OBS-002 :
        SI store_virtuel EXISTE
            ALORS exposition / cash_papier / cash_libre <- DERIVES DU STORE VIRTUEL
            SINON <- pb_health (comportement actuel)

    EXIGENCE DE PARITE :
        POUR UN MEME ETAT DU STORE, panneau CYCLE ET panneau HEARTBEAT
        DOIVENT AFFICHER LES MEMES TROIS NOMBRES (aux arrondis d'affichage pres)

    INTERDIT : toute lecture de pos_manager ajoutee, toute ecriture, tout appel decisionnel
```

- **Plan d'action** :
  1. Lire `advisor_loop.py:7444-7482` et déterminer d'où viennent aujourd'hui exposition / cash.
  2. Confirmer H1 (accès au store virtuel dans la portée).
  3. Écrire d'abord un test de **parité** CYCLE/HEARTBEAT dans le fichier créé en OBS-001
     (même état ⇒ mêmes trois nombres) et vérifier qu'il est rouge.
  4. Appliquer la même règle qu'en OBS-002, avec fallback.
  5. Rendre le test de parité vert.
  6. Rejouer le test de garde INV-2 (doit rester vert) puis la suite complète.
  7. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. Le test de parité (étape 3) précède la correction.
- **Tests** :
  - `python -m pytest tests/test_display_exposure_consistency.py -q` (dont le test de parité)
  - `python -m pytest tests/ -q`
- **Validation** :
  - Test de parité vert.
  - `git diff --name-only` retourne exactement `core/advisor_loop.py`.
  - Diff ≤ 60 lignes.
- **Rollback** : `git revert <sha OBS-003>` ⇒ le panneau HEARTBEAT redevient incohérent, le panneau CYCLE
  reste corrigé (état intermédiaire acceptable, sans impact données ni décision).
- **Risques** : R4 (divergence CYCLE/HEARTBEAT si le ticket est omis ou partiel), R2 (dérive de périmètre).
- **Temps estimé** : 1 h – 2 h.
- **Dépendances** : OBS-002 (obligatoire).
- **Critères Done** :
  - `python -m pytest tests/test_display_exposure_consistency.py -q` : 0 échec, test de parité inclus.
  - `git diff core/advisor_loop.py | grep -c "pos_manager"` retourne `0`.
  - `python -m pytest tests/ -q` : aucun échec nouveau.
- **Critères Refus** :
  - Le test de parité n'existe pas ou n'a jamais été rouge ⇒ refus (rien ne prouve qu'il teste quelque chose).
  - Le fallback non-paper est absent dans le builder HEARTBEAT ⇒ refus.
  - Diff touchant un second fichier de production ⇒ refus.

---

### OBS-004

- **ID** : OBS-004
- **Titre** : Documentation dans le code — « exposition d'affichage » ≠ « exposition-gate » (risque R1)
- **Objectif** : inscrire dans le code, aux points de calcul et d'affichage, la distinction normative entre
  l'**exposition d'affichage** (dérivée de `_virtual_portfolio`, corrigée en OBS-002/003) et
  l'**exposition-gate** (dérivée de `pos_manager`, utilisée par la décision, toujours nulle en paper).
- **Pourquoi** : R1 est le risque principal de la phase. Un panneau devenu crédible peut induire l'opérateur
  en erreur : il verra « exposition 43 % » et supposera que le moteur en tient compte. C'est faux, et cela
  le restera jusqu'à PHASE_02_GATED. Le seul contre-poison compatible avec le gel est un avertissement écrit
  au point de lecture.
- **Diagnostic résumé** :
  1. `advisor_loop.py:6786` : la décision consomme `portfolio_health(pos_manager.get_open())` — vide en paper.
  2. `portfolio_brain.py:668-687` : exposition calculée sur cette liste vide.
  3. `advisor_loop.py:437-448` : docstring existante actant le gel volontaire du bug
     (« corriger son entrée changerait le comportement de décision en pleine validation scientifique »).
  4. `advisor_loop.py:462-471` : régression historique du 2026-07-12 21:00 UTC déjà consignée.
  5. Après OBS-002/003, deux notions d'exposition coexistent dans le même fichier ; sans nommage explicite,
     la prochaine session confondra les deux et « corrigera » la décision par inadvertance (= reset de N).
- **Contexte** : ticket purement documentaire **dans le code** (commentaires, docstrings, libellés de
  panneau). Aucun changement de logique. Aucun fichier `.md` produit par ce ticket.
- **Hypothèses** :
  - H1 — les libellés de panneau sont modifiables sans casser un parseur aval.
    **A CONFIRMER AU DEMARRAGE DU TICKET** (vérifier qu'aucun test ni consommateur ne matche la chaîne
    exacte affichée ; sinon, se limiter aux commentaires de code).
- **Invariants** : INV-1, INV-2, INV-3, INV-4, INV-7. INV-5 et INV-6 triviaux (aucune logique modifiée).
- **Fichiers** : `core/advisor_loop.py` (docstring `:434-459`, points de calcul modifiés par OBS-002/003).
  1 fichier.
- **Pseudo-code** (description, non exécutable) :

```
AJOUTER, au point de calcul de l'exposition d'affichage :

    COMMENTAIRE NORMATIF
    « exposition_affichage : derivee du store virtuel (positions paper reellement ouvertes).
      Sert UNIQUEMENT a l'affichage.
      NE PAS brancher sur une decision.
      exposition_gate : derivee de pos_manager via portfolio_health (advisor 6786).
      VAUT 0 en mode paper. C'est ELLE que la decision consomme.
      Les deux nombres PEUVENT DIVERGER ; cette divergence est un ETAT CONNU, gele
      volontairement (voir docstring 437-448), a corriger en PHASE_02_GATED sous ADR
      et avec reset d'epoque. »

METTRE A JOUR la docstring 434-459 POUR :
    - dire ce qui a ete corrige en PHASE_01 (l'affichage)
    - dire ce qui N'A PAS ete corrige (la decision)
    - nommer le ticket de suite (PHASE_02_GATED / SSOT-xxx) et sa precondition
      (checkpoint L2 + N >= 100 + ADR signe)

OPTIONNEL, SI AUCUN CONSOMMATEUR NE DEPEND DU LIBELLE EXACT :
    RENOMMER le libelle affiche « Portfolio Exposure » EN « Exposition (affichage) »
    POUR QUE LE PANNEAU LUI-MEME PORTE LA DISTINCTION
```

- **Plan d'action** :
  1. Vérifier si un test ou un consommateur dépend des libellés exacts affichés
     (`tests/visualization/test_snapshot_only_loaders.py` notamment).
  2. Ajouter le commentaire normatif au point de calcul d'OBS-002.
  3. Idem au point de calcul d'OBS-003.
  4. Mettre à jour la docstring `advisor_loop.py:434-459` (sans supprimer l'historique `:462-471`).
  5. Renommer le libellé **uniquement** si l'étape 1 le permet.
  6. Rejouer la suite complète.
  7. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. L'étape 5 est conditionnelle au résultat de l'étape 1.
- **Tests** : `python -m pytest tests/ -q` (aucune régression attendue ; le ticket ne change pas de logique).
- **Validation** :
  - La docstring `:434-459` mentionne explicitement les deux notions et la précondition de déblocage
    (checkpoint L2 + N ≥ 100 + ADR d'époque signé).
  - Le diff ne contient aucune modification d'expression conditionnelle ni d'opérateur arithmétique.
- **Rollback** : `git revert <sha OBS-004>` — sans effet fonctionnel.
- **Risques** : R1 partiellement mitigé seulement (un commentaire ne protège pas un opérateur qui ne lit
  que Telegram — d'où l'étape 5, à privilégier si elle est possible).
- **Temps estimé** : 1 h.
- **Dépendances** : OBS-002 et OBS-003 (les points de calcul doivent exister pour être commentés).
- **Critères Done** :
  - `git diff core/advisor_loop.py` contient au moins un bloc de commentaire employant littéralement les
    deux termes « exposition d'affichage » et « exposition-gate ».
  - `python -m pytest tests/ -q` : aucun échec nouveau.
  - Aucun fichier hors `core/advisor_loop.py` dans le diff.
- **Critères Refus** :
  - Le diff modifie une condition, un calcul ou un seuil ⇒ refus (le ticket est documentaire).
  - Le libellé affiché est renommé alors qu'un test/consommateur dépend de la chaîne exacte ⇒ refus.
  - La docstring supprime ou réécrit l'historique de régression `:462-471` ⇒ refus (perte de traçabilité).

---

### OBS-005 (OPTIONNEL)

- **ID** : OBS-005
- **Titre** : Cohérence d'affichage de `system/integrity_snapshot.py` (lecture seule)
- **Objectif** : aligner l'affichage produit par `system/integrity_snapshot.py:100-135`
  (`pb_free` / `pb_exposure` / `pb_n`, actuellement recalculés depuis `pos_manager` — 3ᵉ lignée) sur la même
  règle que les panneaux, **ou**, si l'alignement n'est pas sûr, se limiter à annoter la provenance.
- **Pourquoi** : après OBS-002/003, `integrity_snapshot` deviendrait la dernière surface affichant
  `exposure = 0` avec des positions ouvertes — donc une source de contradiction résiduelle pour l'opérateur
  et pour tout audit ultérieur.
- **Diagnostic résumé** :
  1. `system/integrity_snapshot.py:100-135` recalcule `pb_free` / `pb_exposure` / `pb_n` **via
     `pos_manager`** — troisième lignée de calcul, indépendante des builders CYCLE/HEARTBEAT.
  2. En mode paper, `pos_manager` est vide (`advisor_loop.py:6785-6787`), donc ces trois valeurs sont
     structurellement nulles.
  3. La formule sous-jacente est celle de `portfolio_brain.py:645-664` avec
     `MAX_TOTAL_EXPOSURE_PCT = 0.40` (`:88`).
  4. Le rôle exact d'`integrity_snapshot` (diagnostic opérateur, artefact d'audit, ou entrée d'un contrôle
     automatique) est **A CONFIRMER AU DEMARRAGE DU TICKET** : si une quelconque vérification automatique
     consomme ces valeurs, **le ticket est abandonné** et remonté en PHASE_02_GATED.
- **Contexte** : ticket **optionnel**, exécuté en dernier. Il est abandonnable sans conséquence sur le reste
  de la phase.
- **Hypothèses** :
  - H1 — `integrity_snapshot` est un producteur d'affichage/diagnostic, sans effet sur la décision.
    **A CONFIRMER AU DEMARRAGE DU TICKET.** Si l'hypothèse tombe, arrêter.
  - H2 — `_virtual_portfolio` est accessible depuis ce module. **A CONFIRMER AU DEMARRAGE DU TICKET.**
    Si l'accès demande de câbler une nouvelle dépendance, se rabattre sur l'option « annotation seule ».
- **Invariants** : INV-1, INV-2, INV-3, INV-4, INV-5, INV-6, INV-7.
- **Fichiers** : `system/integrity_snapshot.py` (plage 100-135) et, si un test existe, le test associé.
  Maximum 2 fichiers.
- **Pseudo-code** (description, non exécutable) :

```
ETAPE DE DECISION (obligatoire, avant toute modification) :

    SI une verification automatique CONSOMME pb_free / pb_exposure / pb_n
        ALORS ABANDONNER le ticket ET le remonter en PHASE_02_GATED
    SINON CONTINUER

OPTION 1 (preferee, si le store virtuel est accessible SANS nouvelle dependance) :
    pb_exposure_affiche <- MEME REGLE QU'EN OBS-002 (store virtuel, fallback pos_manager)
    pb_n_affiche        <- NOMBRE de positions du store virtuel
    pb_free_affiche     <- MAXIMUM(0, capital * PLAFOND - notional_deploye)

OPTION 2 (repli) :
    NE RIEN RECALCULER
    ANNOTER chaque valeur : « source = pos_manager (vide en mode paper) —
                              ne correspond PAS a l'exposition d'affichage des panneaux »
```

- **Plan d'action** :
  1. Chercher tous les consommateurs de `pb_free` / `pb_exposure` / `pb_n`.
  2. Trancher : Option 1 si aucun consommateur automatique et accès direct au store ; sinon Option 2 ;
     sinon abandon.
  3. Écrire un test correspondant à l'option retenue (Option 1 : cohérence avec les panneaux ;
     Option 2 : présence de l'annotation).
  4. Appliquer.
  5. Rejouer le test de garde INV-2 puis la suite complète.
  6. Commit unique.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6. L'étape 1 est bloquante : sans inventaire des consommateurs,
  ne pas passer à l'étape 2.
- **Tests** : `python -m pytest tests/ -q` plus le test ajouté à l'étape 3.
- **Validation** :
  - Option retenue écrite dans le message de commit, avec la liste des consommateurs trouvés.
  - Diff ≤ 50 lignes, ≤ 2 fichiers.
- **Rollback** : `git revert <sha OBS-005>` — sans impact sur OBS-002/003/004.
- **Risques** : R2 (si `integrity_snapshot` s'avère être une entrée de contrôle automatique, une
  modification deviendrait un changement de comportement ⇒ d'où l'étape 1 bloquante).
- **Temps estimé** : 1 h – 2 h.
- **Dépendances** : OBS-002, OBS-003, OBS-004.
- **Critères Done** :
  - `python -m pytest tests/ -q` : aucun échec nouveau.
  - `git diff --name-only` liste au plus 2 fichiers, dont `system/integrity_snapshot.py`.
  - Le message de commit contient la liste des consommateurs identifiés à l'étape 1.
- **Critères Refus** :
  - Modification appliquée sans que l'étape 1 ait été faite et consignée ⇒ refus.
  - Un consommateur automatique existe et le ticket a quand même modifié les valeurs ⇒ refus immédiat.
  - Le diff touche `core/advisor_loop.py` ⇒ refus (hors périmètre du ticket).

---

## Ordre

Ordre d'exécution **strict** (chaque ticket est un commit, chaque flèche est une dépendance dure) :

```
OBS-001  (tests d'abord : rouge + garde INV-2 + non-paper + effets de bord)
   |
   v
OBS-002  (builder CYCLE : exposition / paper_cash / free_cash <- store virtuel)
   |
   v
OBS-003  (builder HEARTBEAT : parite stricte)
   |
   v
OBS-004  (documentation dans le code : exposition d'affichage vs exposition-gate)
   |
   v
OBS-005  (OPTIONNEL : integrity_snapshot, abandonnable)
```

Règle d'arrêt : si OBS-002 est bloqué par l'absence de notional dans `_virtual_portfolio` (H1 non
confirmée), la phase s'arrête après OBS-001. Les tests écrits restent acquis et valides ; ils documentent
le défaut de façon exécutable.

---

## Priorité

| Ticket | Priorité | Justification |
|---|---|---|
| OBS-001 | **P0** | Sans le test de garde INV-2, aucune correction de la phase n'est démontrable comme non-décisionnelle. C'est la pièce qui protège l'époque courante. |
| OBS-002 | **P0** | Corrige le premier point d'incohérence sur le panneau le plus lu (CYCLE). |
| OBS-003 | **P1** | Sans lui, l'incohérence intra-panneau devient une incohérence inter-panneaux (R4). |
| OBS-004 | **P1** | Traite R1, le risque le plus élevé de la phase (fausse confiance opérationnelle). |
| OBS-005 | **P3** | Optionnel, abandonnable, sans effet sur les autres tickets. |

Toute la phase est de priorité inférieure à un incident de production ; aucun ticket n'est urgent au sens
opérationnel — le système fonctionne, il ment seulement sur un chiffre affiché.

---

## Statut

**PRET** — avec deux réserves nommées, aucune bloquante à ce stade :

1. **PRET** : l'architecture A est arbitrée, la cause racine est établie par inspection directe, aucun
   ticket ne touche une entrée de décision, donc **aucun reset d'époque, aucun reset de N**. La phase est
   compatible avec ADR-0007, la Scientific Debt Rule (outil de mesure/observabilité, pas de fonctionnalité
   nouvelle) et la règle du statisticien (aucun seuil modifié).
2. Réserve 1 — **A CONFIRMER AU DEMARRAGE D'OBS-002** : `_virtual_portfolio` expose-t-il le notional par
   position sans approximation ? Si non, la phase s'arrête après OBS-001 et la question remonte à
   l'opérateur. Aucun proxy ne doit être inventé.
3. Réserve 2 — **A CONFIRMER AU DEMARRAGE D'OBS-001** : `check_new_trade` est-il appelable en test avec des
   entrées figées ? Si non, INV-2 doit être figée autrement (par exemple par capture de journal
   décisionnel sur un cycle rejoué) avant qu'OBS-002 puisse démarrer.

Rappel de gating, à ne pas confondre avec le contenu de cette phase : toute évolution touchant
`PositionManager`, `check_new_trade`, le sizing, le risk ou `PortfolioBrain` **en entrée de décision** est
**GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**, préconditions checkpoint L2 franchi + N ≥ 100 sur
l'époque courante + ADR d'époque signé par l'opérateur. Rien de tel n'est présent dans PHASE_01.
