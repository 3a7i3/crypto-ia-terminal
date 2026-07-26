# PHASE_04_GATED — Réconciliation du moteur de portefeuille et de risque

> **GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**
>
> Cette phase modifie **l'entrée de décision**. Elle change le comportement du moteur.
> Elle **détruit le burn-in en cours** (N revient à zéro, nouvelle borne d'époque).
>
> **Préconditions de déblocage, cumulatives :**
> 1. Checkpoint L2 franchi.
> 2. N ≥ 100 atteint **sur l'époque courante V4** (`CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`)
>    — on ne sacrifie pas une époque avant qu'elle ait produit sa mesure.
> 3. ADR d'époque (numéro libre à partir de ADR-0019) **rédigé et signé par l'opérateur**.
> 4. PHASE_02_GATED terminée (le store canonique doit exister avant d'être branché sur la décision).
>
> Tant que ces quatre conditions ne sont pas réunies : **aucun ticket de cette phase n'est démarrable**,
> à la seule exception de **PORT-001**, qui est passif et documenté comme tel ci-dessous.

---

## Objectif

Faire en sorte que `PortfolioBrain` calcule l'exposition, le capital libre, le risque de corrélation et
le levier agrégé sur les positions **réellement ouvertes**, et non sur un store vide.

Conséquence assumée : le gate de risque devient **plus restrictif**. Aujourd'hui il croit gérer 0 %
d'exposition alors que trois positions sont ouvertes ; il autorise donc des trades qu'il aurait dû
refuser. Corriger cela **change les décisions du moteur** — c'est précisément ce qui rend la phase GATED.

## Contexte

`core/advisor_loop.py:6785-6787` appelle `portfolio_brain.portfolio_health(pos_manager.get_open())`.
En mode paper, `pos_manager` (PositionManager) est vide : les positions sont ouvertes dans
`_virtual_portfolio` (MexcSimulator) via `place_market_order` (`advisor:2176`), tandis que
`pos_manager.add_position` (`advisor:3883`) n'est atteint que par le chemin
`_register_position_from_execution` (`advisor:3859-3883`).

`portfolio_brain.py:668-687` `_snapshot()` itère la liste reçue :
`total_exposure_usd += p.size_usd`, `n_positions += 1`, puis
`total_exposure_pct = total_exposure_usd / self._capital`. Liste vide ⇒ exposition 0.

`portfolio_brain.py:645-664` `portfolio_health()` en dérive `free_capital =
max(0, capital * MAX_TOTAL_EXPOSURE_PCT - total_exposure_usd)` avec `MAX_TOTAL_EXPOSURE_PCT = 0.40`
(`portfolio_brain.py:88`). Preuve numérique : `674.47 × 0.40 − 0 = 269.79 $`, exactement la valeur
`Free Cash` affichée — confirmation que `total_exposure_usd` valait bien 0.

Ces mêmes valeurs alimentent `check_new_trade` (`portfolio_brain.py:121-190`) : contrôle d'exposition
totale (§1), de concentration par actif (§2), d'exposition par régime (§3), de corrélation (§4),
de levier (§5). **Les cinq contrôles s'exécutent aujourd'hui sur un portefeuille perçu comme vide.**

PHASE_01 a corrigé l'**affichage** ; elle a laissé ce trou intact, volontairement, comme l'indique la
docstring `core/advisor_loop.py:437-448` : « corriger son entrée changerait le comportement de décision
en pleine validation scientifique. Ce bug est documenté, gelé, à corriger à la calibration ».

**PHASE_04_GATED est la levée de ce gel.**

## Dépendances

| Dépendance | Nature | Justification |
|---|---|---|
| PHASE_02_GATED (SSOT-001 → SSOT-007) | **Dure** | Le store canonique et son résolveur doivent exister avant d'être branchés sur la décision. |
| PHASE_00 (GOV-001, GOV-002, GOV-003) | **Dure** | Format d'ADR, registre d'invariants opposable, journal des décisions. |
| PHASE_01 (OBS-001 → OBS-004) | Recommandée | L'affichage doit déjà être honnête, sinon on ne peut pas comparer avant/après. |
| PHASE_03 | Aucune | Indépendante (couche de publication HTTP). |

## Prérequis

1. Les quatre préconditions de déblocage de l'encart GATED ci-dessus, sans exception.
2. Une baseline de tests relevée et archivée (`python -m pytest tests/ -q`).
3. Une mesure d'impact chiffrée produite par **PORT-001** et lue par l'opérateur **avant** la décision
   d'époque. Décider d'un reset de N sans savoir ce qu'il achète serait une décision non informée.
4. Un tag git de déploiement antérieur identifié, pour permettre un retour arrière VPS.
5. Une fenêtre d'arrêt du moteur acceptée par l'opérateur (le changement de comportement impose
   un redémarrage propre et une nouvelle borne d'époque).

## Risques

| ID | Risque | Gravité | Mitigation |
|---|---|---|---|
| R1 | **Destruction du burn-in** : N repart de 0, les données V4 deviennent une époque close. | Critique | Précondition N ≥ 100 sur V4 ; archivage documenté de l'époque V4 ; ADR signé. |
| R2 | Le gate devient si restrictif que le débit de trades s'effondre (famine de trading). | Majeure | PORT-001 chiffre l'effet **avant** bascule ; seuils inchangés (INV-4). |
| R3 | Double comptage : une position présente dans deux stores est comptée deux fois. | Majeure | Store canonique unique (PHASE_02) ; test d'idempotence dans PORT-002. |
| R4 | La corrélation et le levier, calculés sur un portefeuille vide depuis toujours, révèlent des seuils jamais éprouvés. | Majeure | PORT-003 isolé de PORT-002 ; mesure séparée. |
| R5 | Régression silencieuse : le verdict change sans qu'aucun test ne le détecte. | Majeure | Harnais de comparaison de verdicts (SSOT-005) obligatoire avant PORT-002. |
| R6 | Confusion entre l'arbitrage des deux `PortfolioBrain` et le câblage du store. | Modérée | Tickets séparés (PORT-004 distinct de PORT-002). |
| R7 | La bascule est faite sans nouvelle borne d'époque ⇒ dataset contaminé, mélange V4/V5. | Critique | PORT-006 pose la borne dans le même geste que la bascule ; contrôle CRI après. |

## Architecture

Cible de la phase :

```
AVANT (etat courant)
  pos_manager.get_open()  ──►  portfolio_health()  ──►  check_new_trade()
     (VIDE en paper)              exposure = 0            5 controles sur un vide

APRES (cible PHASE_04)
  store canonique (PHASE_02)  ──►  portfolio_health()  ──►  check_new_trade()
     (positions REELLES)             exposure REELLE         5 controles sur la realite
                                          │
                                          └──► harnais de comparaison (SSOT-005)
                                               journalise verdict_avant vs verdict_apres
```

Principe directeur : **on ne modifie ni les seuils, ni les formules**. On corrige uniquement
**ce que le moteur regarde**. `MAX_TOTAL_EXPOSURE_PCT`, `MAX_SINGLE_SYMBOL_PCT`,
`MAX_SAME_REGIME_PCT`, `MAX_CORRELATION_RISK`, `MAX_LEVERAGE_WEIGHTED`, `MAX_POSITIONS`
restent à leurs valeurs actuelles (INV-4 et règle du statisticien : toute modification de seuil
exige N ≥ 500 et CRI ≥ 90).

## Fichiers concernés

| Fichier | Rôle dans la phase |
|---|---|
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | `portfolio_health:645-664`, `_snapshot:668-687`, `check_new_trade:121-190`, constantes `:88-109` |
| `core/advisor_loop.py` | Site d'appel `:6785-6787` (le point de bascule), `:3859-3883` |
| `quant_hedge_ai/agents/portfolio/__init__.py` | Second `PortfolioBrain:71` — arbitrage PORT-004 |
| `paper_trading/ledger.py` | `PaperTrade` (mutation en place), `PaperLedger:121` — PORT-005 |
| `scripts/data_quality.py` | Borne d'époque `CLEAN_DATA_SINCE_*` — PORT-006 |
| `tools/cri_calculator.py` | `load_clean_trades()` — contrôle post-bascule PORT-006 |
| `tests/` | Tests de verdict, d'idempotence, de non-régression |

## Invariants

- **INV-1** (ADR-0007) — la passivité des observers reste absolue. Cette phase modifie le **moteur de
  décision lui-même**, ce qui est autorisé ; elle n'autorise **pas** un observer à influencer une décision.
- **INV-2 — SUSPENDU PAR ADR SIGNE.** C'est la seule phase (avec PHASE_02_GATED) où le reset de N est
  autorisé, et uniquement après signature. Sans ADR signé au dépôt, INV-2 reste actif et bloque la phase.
- **INV-3** — `paper_trades.jsonl` reste écrit exclusivement par `paper_trading/mexc_simulator.py` et
  `paper_trading/recorder.py`. Aucun ticket de cette phase n'y écrit.
- **INV-4** — **aucun seuil n'est modifié.** On corrige l'entrée, jamais la permissivité.
- **INV-P1** — aucune position ne peut être comptée deux fois (idempotence du store canonique).
- **INV-P2** — tout changement de verdict entre avant/après doit être **journalisé et chiffré**,
  jamais silencieux.
- **INV-P3** — la bascule et la pose de la nouvelle borne d'époque sont **atomiques** :
  jamais de fenêtre où le moteur décide autrement sans que la borne soit posée.

## Validation

| # | Contrôle | Méthode |
|---|---|---|
| V1 | ADR d'époque présent, signé, référencé | Fichier sous `docs/adr/`, numéro ≥ 0019 |
| V2 | N ≥ 100 sur V4 au moment de la décision | `tools/cri_calculator.py`, borne V4 |
| V3 | Mesure d'impact PORT-001 produite et lue | Rapport chiffré au dépôt |
| V4 | Exposition affichée = exposition-gate | Comparaison des deux valeurs sur un même cycle |
| V5 | Aucun seuil modifié | `git diff` sur `portfolio_brain.py:88-109` : vide |
| V6 | Nouvelle borne d'époque posée | `scripts/data_quality.py` : `CLEAN_DATA_SINCE_V5` |
| V7 | CRI recalculé sur la nouvelle époque, cohérent | `tools/cri_calculator.py`, N = 0 attendu |
| V8 | Suite de tests verte | `python -m pytest tests/ -q` |
| V9 | Déploiement vérifié | Tag `deploy-YYYYMMDD-HHMM`, SHA VPS = SHA local, service actif |

## Rollback

Deux niveaux, à ne pas confondre :

1. **Rollback technique** (par ticket) : `git revert <sha>` du ticket concerné. Restaure le code.
2. **Rollback d'époque** : **impossible**. Une fois la borne V5 posée et le moteur redémarré, les
   décisions prises sous le nouveau comportement appartiennent à la nouvelle époque. Revenir en arrière
   ne restaure pas N ; cela créerait une **troisième** époque hybride.

> **Conséquence de gouvernance** : la bascule PORT-002 est le point de non-retour scientifique de tout
> le chantier. Le rollback code existe ; le rollback de la mesure n'existe pas.
> C'est la raison d'être des quatre préconditions.

## Estimation

| Ticket | Estimation |
|---|---|
| PORT-001 | 1 – 2 j |
| PORT-002 | 1 – 2 j |
| PORT-003 | 1 j |
| PORT-004 | 1 – 2 j |
| PORT-005 | 2 – 3 j |
| PORT-006 | 0,5 j + fenêtre opérateur |
| **Total** | **7 – 11 j** de travail, hors temps d'attente de la précondition N ≥ 100 |

## Tickets

### PORT-001

> **PASSIF — EXCEPTION DOCUMENTEE.** Ce ticket est le **seul** de la phase qui ne modifie pas l'entrée
> de décision. Il **mesure** hors ligne ce que la bascule changerait. Il ne reset **pas** N et peut
> être exécuté **avant** l'ADR d'époque — c'est même souhaitable, puisque son résultat informe la décision.

- **ID** : PORT-001
- **Titre** : Mesure d'impact hors ligne — combien de trades auraient été refusés avec l'exposition réelle
- **Objectif** : produire un rapport chiffré répondant à : *sur l'historique V4, combien de trades
  autorisés auraient été refusés si `portfolio_health` avait vu les positions réelles ?*
- **Pourquoi** : décider d'un reset de N sans savoir ce qu'il achète est une décision non informée.
  Ce chiffre est l'argument central de l'ADR d'époque. S'il est proche de zéro, la bascule ne vaut
  peut-être pas un reset ; s'il est élevé, il prouve que le gate est aveugle depuis le début de l'époque.
- **Diagnostic résumé** : `portfolio_brain.py:668-687` calcule l'exposition sur la liste reçue ;
  `advisor_loop.py:6786` lui passe `pos_manager.get_open()`, vide en paper. Les cinq contrôles de
  `check_new_trade:121-190` s'exécutent donc sur un portefeuille perçu vide. La preuve numérique
  (`674.47 × 0.40 = 269.79`) confirme `total_exposure_usd = 0` en production.
- **Contexte** : ticket de **mesure passive**, en rejeu hors ligne. Aucun composant de production n'est
  modifié ; le moteur en cours d'exécution n'est ni arrêté ni influencé (ADR-0007 respecté).
- **Hypothèses** :
  - H1 — l'historique V4 permet de reconstituer, pour chaque décision, les positions ouvertes à cet
    instant. **A CONFIRMER AU DEMARRAGE DU TICKET** (source probable : `paper_trades.jsonl` +
    horodatages d'ouverture/fermeture).
  - H2 — `check_new_trade` est appelable en pur calcul, sans effet de bord.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H3 — le capital historique est reconstituable par instant. **A CONFIRMER AU DEMARRAGE DU TICKET.**
- **Invariants** : INV-1, **INV-2 (respecté : aucun reset)**, INV-3 (lecture seule de
  `paper_trades.jsonl`), INV-4, INV-P2.
- **Fichiers** : 1 script d'analyse hors ligne sous `analysis/` ou `research/` (emplacement
  **A CONFIRMER AU DEMARRAGE DU TICKET**) + 1 rapport `.md`. **≤ 2 fichiers.**
  Aucun fichier de production modifié.
- **Pseudo-code** (description, non exécutable) :

```
CHARGER les trades de l'epoque V4 (borne CLEAN_DATA_SINCE_ACTIVE, lecture seule)
RECONSTITUER, par ordre chronologique, l'etat du portefeuille a chaque decision

POUR CHAQUE decision d'ouverture enregistree :
    positions_reelles <- positions ouvertes A CET INSTANT (reconstruites)
    verdict_reel      <- check_new_trade(..., open_positions = positions_reelles)
    verdict_historique<- AUTORISE            # ce que le moteur a fait, gate aveugle

    SI verdict_reel = REFUSE
        COMPTER comme "aurait ete refuse"
        ENREGISTRER le motif (exposition / concentration / regime / correlation / levier)

PRODUIRE :
    n_total, n_aurait_ete_refuse, pourcentage
    REPARTITION des motifs de refus
    PnL CUMULE des trades qui auraient ete refuses      # gagne ou perdu ?
    EXPOSITION MAXIMALE reellement atteinte vs plafond 0.40

NE RIEN MODIFIER. NE RIEN DEPLOYER. AUCUNE ECRITURE hors du rapport.
```

- **Plan d'action** :
  1. Confirmer H1/H2/H3 par lecture des sources.
  2. Écrire le script de rejeu hors ligne (lecture seule).
  3. Reconstituer l'état du portefeuille par instant.
  4. Rejouer les verdicts avec les positions réelles.
  5. Produire le rapport chiffré (5 métriques du pseudo-code).
  6. Commit unique (script + rapport).
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6. L'étape 1 est bloquante : sans reconstitution fiable de
  l'état, le chiffre produit serait faux et servirait à une décision d'époque irréversible.
- **Tests** : test de non-régression trivial (aucun fichier de production touché) +
  contrôle de cohérence : le rejeu doit reproduire à l'identique les verdicts **historiques** lorsqu'on
  lui passe un portefeuille vide (validation du harnais lui-même).
- **Validation** :
  - Le rapport donne un pourcentage chiffré et la répartition des motifs.
  - Le harnais reproduit les verdicts historiques avec `open_positions = []` (auto-validation).
  - `git diff --name-only` ne liste aucun fichier de production.
- **Rollback** : `git revert <sha PORT-001>`. Sans effet fonctionnel.
- **Risques** : R2 (le chiffre oriente la décision : s'il est mal calculé, il induit une décision
  irréversible), R5.
- **Temps estimé** : 1 – 2 j.
- **Dépendances** : aucune dure. **Exécutable immédiatement**, avant l'ADR d'époque.
- **Critères Done** :
  - Rapport présent au dépôt, contenant les 5 métriques listées.
  - Auto-validation du harnais démontrée (verdicts historiques reproduits).
  - Aucun fichier de production modifié.
  - `python -m pytest tests/ -q` identique à la baseline.
- **Critères Refus** :
  - Le script écrit quoi que ce soit dans `paper_trades.jsonl` ⇒ refus (INV-3).
  - Le script est branché sur le moteur en cours d'exécution ⇒ refus (ADR-0007).
  - Le rapport donne une conclusion sans chiffre ⇒ refus.
  - L'auto-validation du harnais est absente ⇒ refus (le chiffre serait invérifiable).

---

### PORT-002

> **GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**
> Précondition : les 4 conditions de l'encart de phase **+ PORT-001 lu par l'opérateur**.

- **ID** : PORT-002
- **Titre** : Brancher `portfolio_health` sur le store canonique (point de non-retour)
- **Objectif** : remplacer, en `core/advisor_loop.py:6786`, l'argument `pos_manager.get_open()` par le
  store canonique résolu (SSOT-004/SSOT-007), afin que l'exposition et le capital libre soient calculés
  sur les positions réellement ouvertes.
- **Pourquoi** : c'est le geste qui corrige la cause racine. Sans lui, les cinq contrôles de risque
  restent aveugles et l'ensemble du chantier n'aura corrigé que des affichages.
- **Diagnostic résumé** : `advisor_loop.py:6785-6787` →
  `portfolio_brain.portfolio_health(pos_manager.get_open())` ; `pos_manager` vide en paper ;
  `portfolio_brain.py:668-687` itère une liste vide ⇒ `total_exposure_pct = 0` ;
  `portfolio_health:645-664` en dérive `free_capital = capital × 0.40 − 0`.
  Preuve : `674.47 × 0.40 = 269.79` = valeur affichée.
- **Contexte** : **ce ticket change le comportement de décision.** À partir de son déploiement, le moteur
  refuse des trades qu'il acceptait. C'est le point de non-retour scientifique de tout le chantier.
- **Hypothèses** :
  - H1 — le store canonique (PHASE_02) expose une liste d'objets porteurs de `size_usd`, `symbol`,
    `regime`, `pnl_usd`, `closed`, compatible avec `_snapshot` (`portfolio_brain.py:670-681`).
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H2 — le harnais de comparaison SSOT-005 est actif et journalise les deux verdicts.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
  - H3 — aucune position n'est présente dans deux stores simultanément (INV-P1).
- **Invariants** : INV-1, **INV-2 suspendu par ADR signé**, INV-3, **INV-4 (aucun seuil modifié)**,
  INV-P1, INV-P2, INV-P3.
- **Fichiers** : `core/advisor_loop.py` (site d'appel `:6786`) ;
  `quant_hedge_ai/agents/risk/portfolio_brain.py` si une signature doit évoluer ; 1 fichier de test.
  **≤ 3 fichiers, ≤ 80 lignes.**
- **Pseudo-code** (description, non exécutable) :

```
AVANT   pb_health <- portfolio_health( pos_manager.get_open() )     # VIDE en paper

APRES   positions <- store_canonique.positions_ouvertes()           # REELLES
        ASSERTER idempotence : aucun symbole en double               # INV-P1
        pb_health <- portfolio_health( positions )

        SI harnais_actif :
            verdict_ancien <- check_new_trade(..., pos_manager.get_open())
            verdict_nouveau<- check_new_trade(..., positions)
            JOURNALISER (verdict_ancien, verdict_nouveau, ecart)     # INV-P2

AUCUN SEUIL N'EST TOUCHE : MAX_TOTAL_EXPOSURE_PCT, MAX_SINGLE_SYMBOL_PCT,
MAX_SAME_REGIME_PCT, MAX_CORRELATION_RISK, MAX_LEVERAGE_WEIGHTED, MAX_POSITIONS
restent a leurs valeurs actuelles (portfolio_brain.py:88-109)
```

- **Plan d'action** :
  1. Vérifier que l'ADR d'époque est signé et référencé. **Sinon : STOP.**
  2. Vérifier N ≥ 100 sur V4. **Sinon : STOP.**
  3. Relever la baseline de tests et archiver un tag de déploiement de repli.
  4. Confirmer H1/H2/H3.
  5. Substituer l'argument au site d'appel `:6786`.
  6. Ajouter l'assertion d'idempotence (INV-P1).
  7. Vérifier par `git diff` qu'aucune constante de `portfolio_brain.py:88-109` n'a bougé.
  8. Tests, puis commit unique. **Ne pas déployer dans le même geste** (PORT-006 s'en charge).
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Les étapes 1 et 2 sont des portes : leur échec
  arrête le ticket, sans exception ni dérogation locale.
- **Tests** : `python -m pytest tests/ -q` ; test d'idempotence du store ;
  test de verdict comparant avant/après sur un jeu de positions fixé.
- **Validation** :
  - `exposure` calculée > 0 dès qu'une position est ouverte.
  - `exposition affichée == exposition-gate` sur un même cycle (V4 de la phase).
  - Aucun seuil modifié (`git diff` sur `:88-109` vide).
  - Écart de verdicts journalisé et chiffré.
- **Rollback** : `git revert <sha PORT-002>` restaure le code. **Le rollback d'époque n'existe pas**
  (cf section Rollback de la phase).
- **Risques** : R1, R2, R3, R5, R7.
- **Temps estimé** : 1 – 2 j.
- **Dépendances** : **PHASE_02_GATED (SSOT-004, SSOT-005, SSOT-007) — dures.** PORT-001 — dure
  (le chiffre d'impact conditionne l'ADR).
- **Critères Done** :
  - Un cycle avec 3 positions ouvertes affiche une exposition non nulle et cohérente avec Σ `size_usd`.
  - Le journal d'écart de verdicts existe et est non vide.
  - `git diff` sur `portfolio_brain.py:88-109` : vide.
  - Suite de tests verte.
- **Critères Refus** :
  - ADR d'époque absent ou non signé ⇒ refus immédiat, aucune exception.
  - N < 100 sur V4 ⇒ refus.
  - Un seuil a été modifié « pour compenser » la nouvelle restrictivité ⇒ refus (INV-4).
  - Le harnais de comparaison n'est pas actif ⇒ refus (le changement serait silencieux, INV-P2).
  - Une position est comptée deux fois ⇒ refus (INV-P1).

---

### PORT-003

> **GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**

- **ID** : PORT-003
- **Titre** : Corrélation et levier agrégé calculés sur les positions réelles
- **Objectif** : faire porter `_correlation_risk` / `_portfolio_correlation_risk` et `_weighted_leverage`
  (`portfolio_brain.py:685-686`, `:689-700`) sur le store canonique, et mesurer les valeurs obtenues.
- **Pourquoi** : ces deux contrôles n'ont **jamais** été éprouvés sur un portefeuille non vide. Leurs
  seuils (`MAX_CORRELATION_RISK = 0.75`, `MAX_LEVERAGE_WEIGHTED = 2.0`) sont des valeurs par défaut
  jamais confrontées au réel. Les activer sans les mesurer d'abord risque de bloquer tout le trading.
- **Diagnostic résumé** : `_snapshot` (`:685-686`) appelle `_portfolio_correlation_risk(positions)` et
  `_weighted_leverage(positions)` sur la liste reçue — vide aujourd'hui, donc corrélation et levier
  valent 0 en permanence (`Corr risk: 0.0%` dans le panneau).
- **Contexte** : ticket **séparé de PORT-002** délibérément. Si les deux étaient fusionnés et que le
  débit s'effondrait, on ne saurait pas si la cause est l'exposition ou la corrélation.
- **Hypothèses** :
  - H1 — la matrice `_DEFAULT_CORRELATIONS` couvre les paires de l'univers V4 (135 paires).
    **A CONFIRMER AU DEMARRAGE DU TICKET** — si non, la valeur par défaut `0.5`
    (`portfolio_brain.py:697`) s'applique massivement, ce qui est un fait à documenter.
  - H2 — le levier est 1 en paper spot. **A CONFIRMER AU DEMARRAGE DU TICKET.**
- **Invariants** : INV-1, INV-2 suspendu, INV-3, **INV-4**, INV-P2.
- **Fichiers** : `quant_hedge_ai/agents/risk/portfolio_brain.py` + 1 fichier de test.
  **≤ 2 fichiers, ≤ 60 lignes.**
- **Pseudo-code** (description, non exécutable) :

```
MESURER D'ABORD, ACTIVER ENSUITE

ETAPE 1 (mesure passive)
    POUR chaque cycle observe :
        corr <- correlation_risk(positions_reelles)
        lev  <- levier_pondere(positions_reelles)
        JOURNALISER corr, lev, et la part de paires tombant sur le defaut 0.5

ETAPE 2 (constat)
    SI corr depasse frequemment MAX_CORRELATION_RISK (0.75)
        ALORS SIGNALER a l'operateur : le seuil n'a jamais ete eprouve
              NE PAS MODIFIER LE SEUIL (INV-4) — c'est une decision de calibration

ETAPE 3 (activation)
    Brancher les deux calculs sur le store canonique
```

- **Plan d'action** : 1. Confirmer H1/H2. 2. Instrumenter la mesure passive. 3. Observer sur plusieurs
  cycles. 4. Documenter le constat. 5. Brancher. 6. Tests. 7. Commit.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. L'étape 3 précède l'étape 5 : on mesure avant d'activer.
- **Tests** : `python -m pytest tests/ -q` + test sur un portefeuille fixé à corrélation connue.
- **Validation** : corrélation et levier non nuls quand des positions existent ; part des paires
  retombant sur le défaut `0.5` documentée ; aucun seuil modifié.
- **Rollback** : `git revert <sha PORT-003>`.
- **Risques** : R2, R4.
- **Temps estimé** : 1 j.
- **Dépendances** : **PORT-002 (dure).**
- **Critères Done** : mesure documentée ; branchement effectif ; `git diff` sur `:88-109` vide ; tests verts.
- **Critères Refus** : un seuil modifié ⇒ refus (INV-4) ; activation sans mesure préalable ⇒ refus ;
  couverture de la matrice de corrélation non documentée ⇒ refus.

---

### PORT-004

> **GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**
> (Gated par prudence : le ticket touche une classe présente dans le chemin de décision.)

- **ID** : PORT-004
- **Titre** : Arbitrage des deux `PortfolioBrain`
- **Objectif** : déterminer lequel de `quant_hedge_ai/agents/risk/portfolio_brain.py:75` et
  `quant_hedge_ai/agents/portfolio/__init__.py:71` est canonique, et neutraliser l'autre
  (suppression ou façade explicite).
- **Pourquoi** : deux classes du même nom dans le chemin de décision rendent le système illisible.
  Un contributeur futur ne peut pas savoir laquelle est active sans exécuter le code.
- **Diagnostic résumé** : audit de duplication — 2 classes `PortfolioBrain` (chemins ci-dessus),
  3 classes `PortfolioSnapshot`, 2 classes `SystemSnapshot`. `advisor_loop` utilise
  `portfolio_brain.portfolio_health` ; **laquelle des deux est importée est A CONFIRMER AU DEMARRAGE
  DU TICKET.**
- **Contexte** : ticket de clarification structurelle. Il ne change pas le calcul si la classe morte
  est réellement morte — mais cela doit être **prouvé**, pas supposé.
- **Hypothèses** :
  - H1 — une seule des deux est effectivement importée dans le chemin de décision.
    **A CONFIRMER AU DEMARRAGE DU TICKET** (grep des imports + trace d'exécution).
  - H2 — la classe non canonique n'a pas d'autre consommateur.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
- **Invariants** : INV-1, INV-2 suspendu, INV-3, INV-4, INV-P2.
- **Fichiers** : les deux fichiers de classe + au plus 2 fichiers d'import. **≤ 4 fichiers.**
- **Pseudo-code** (description, non exécutable) :

```
1. TRACER tous les imports des deux classes (grep + inspection du chemin runtime)
2. ETABLIR laquelle est atteinte par advisor_loop -> portfolio_health
3. SI l'autre n'a AUCUN consommateur
       LA SUPPRIMER
   SINON
       LA REMPLACER par une facade qui delegue a la canonique
       ET documenter pourquoi elle survit
4. VERIFIER qu'aucun verdict ne change (le calcul doit etre identique)
```

- **Plan d'action** : 1. Tracer. 2. Établir. 3. Décider. 4. Neutraliser. 5. Prouver l'absence de
  changement de verdict. 6. Tests. 7. Commit.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. L'étape 5 est obligatoire : si le verdict change,
  c'est que la mauvaise classe était active, ce qui est un incident à remonter à l'opérateur.
- **Tests** : `python -m pytest tests/ -q` + test de verdict identique avant/après.
- **Validation** : une seule `PortfolioBrain` atteignable depuis le chemin de décision ; verdicts
  inchangés ; aucun import cassé.
- **Rollback** : `git revert <sha PORT-004>`.
- **Risques** : R6 ; risque de suppression d'une classe utilisée par un chemin non tracé.
- **Temps estimé** : 1 – 2 j.
- **Dépendances** : PORT-002 recommandée (pour ne pas mêler deux causes de changement de verdict).
- **Critères Done** : une seule classe canonique ; verdicts prouvés identiques ; tests verts.
- **Critères Refus** : un verdict change sans explication ⇒ **STOP et remontée opérateur** ;
  suppression sans traçage des imports ⇒ refus.

---

### PORT-005

> **GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**

- **ID** : PORT-005
- **Titre** : `PaperTrade` — remplacer la mutation en place par deux événements distincts
- **Objectif** : cesser de muter la ligne d'un trade à la clôture (`paper_trading/ledger.py`,
  `is_open` passe à `False`, champs `exit_*` remplis) et émettre deux faits distincts :
  `TradeOpened` puis `TradeClosed`.
- **Pourquoi** : la mutation en place **détruit le fait « le trade s'est ouvert »**. Un trade ouvert puis
  fermé ne laisse qu'une seule ligne, dans son état final. C'est l'obstacle structurel n°1 à toute
  reconstruction d'état par rejeu — et donc à l'architecture C.
- **Diagnostic résumé** : `paper_trading/ledger.py` — `PaperTrade` porte `is_open`, `exit_price`,
  `exit_ts`, `exit_reason` remplis à la clôture par `close_trade` (`:144-166`), qui fait
  `self._closed.append(trade)` et `self._capital += trade.pnl_net_usd`. L'état antérieur est perdu.
- **Contexte** : amorce de l'architecture C. Ticket **le plus lourd** de la phase : il touche le format
  du grand livre, donc potentiellement `paper_trades.jsonl`.
- **Hypothèses** :
  - H1 — le schéma de `paper_trades.jsonl` peut évoluer sans casser `tools/cri_calculator.py` ni
    `scripts/data_quality.py`. **A CONFIRMER AU DEMARRAGE DU TICKET** — si non, prévoir un
    upcasting de lecture, jamais une réécriture de l'historique.
  - H2 — aucun consommateur ne dépend de la mutation en place.
    **A CONFIRMER AU DEMARRAGE DU TICKET.**
- **Invariants** : INV-1, INV-2 suspendu, **INV-3 (l'historique existant n'est jamais réécrit —
  on ajoute, on ne modifie pas)**, INV-4, INV-P2.
- **Fichiers** : `paper_trading/ledger.py`, `paper_trading/mexc_simulator.py` (émission),
  + 2 fichiers de test. **≤ 4 fichiers.**
- **Pseudo-code** (description, non exécutable) :

```
AVANT
    trade.is_open <- False        # le fait "ouvert" est DETRUIT
    trade.exit_*  <- ...

APRES
    A l'ouverture : EMETTRE TradeOpened(trade_id, symbol, side, size, prix, ts)   # immuable
    A la cloture  : EMETTRE TradeClosed(trade_id, prix_sortie, frais, motif, ts)  # immuable

    L'ETAT COURANT devient une PROJECTION :
        positions_ouvertes = { TradeOpened sans TradeClosed correspondant }

REGLE ABSOLUE : l'historique existant n'est JAMAIS reecrit.
                On ajoute un nouveau format ; on lit l'ancien via un upcasting.
```

- **Plan d'action** : 1. Confirmer H1/H2. 2. Définir les deux événements. 3. Émettre en parallèle de
  l'existant (double écriture temporaire). 4. Construire la projection « positions ouvertes ».
  5. Comparer projection vs `_open` (doivent coïncider). 6. Basculer les lecteurs. 7. Tests. 8. Commit.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. L'étape 5 est la porte : tant que la projection ne
  reproduit pas exactement l'état courant, on ne bascule pas.
- **Tests** : `python -m pytest tests/ -q` ; test de projection ; test d'upcasting sur l'historique V4 ;
  test de non-réécriture de `paper_trades.jsonl`.
- **Validation** : projection == `_open` sur tout l'historique ; ancien format toujours lisible ;
  CRI inchangé sur l'historique existant.
- **Rollback** : `git revert <sha PORT-005>`. La double écriture rend le retour arrière sûr tant que
  la bascule des lecteurs (étape 6) n'est pas faite.
- **Risques** : R3, R5, R7 ; risque de corruption du dataset scientifique (mitigé par INV-3 et le
  contrôle CRI).
- **Temps estimé** : 2 – 3 j.
- **Dépendances** : PORT-002 (dure) ; PHASE_02_GATED (store canonique).
- **Critères Done** : deux événements émis ; projection prouvée équivalente ; historique intact ;
  CRI identique avant/après sur les données existantes ; tests verts.
- **Critères Refus** : une ligne de `paper_trades.jsonl` est modifiée ou supprimée ⇒ **refus immédiat**
  (INV-3) ; la projection diverge de `_open` ⇒ refus ; le CRI change sur des données inchangées ⇒ refus.

---

### PORT-006

> **GATED / RESET D'EPOQUE / N → 0 / ADR OBLIGATOIRE**
> **C'est le ticket qui exécute effectivement le reset d'époque.**

- **ID** : PORT-006
- **Titre** : Pose de la borne d'époque V5, déploiement et vérification
- **Objectif** : poser `CLEAN_DATA_SINCE_V5` dans `scripts/data_quality.py`, déployer, redémarrer,
  et vérifier que le système décide désormais sur des positions réelles et compte sur la nouvelle époque.
- **Pourquoi** : sans nouvelle borne, les décisions prises sous l'ancien comportement (gate aveugle) et
  sous le nouveau seraient mélangées dans le même dataset. Le N ainsi obtenu ne mesurerait rien.
- **Diagnostic résumé** : `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` est la borne courante
  (`scripts/data_quality.py`, alias `CLEAN_DATA_SINCE_ACTIVE`, lue par
  `tools/cri_calculator.py::load_clean_trades`). Précédents : V1 (ADR-0011), V2/V3 (ADR-0012),
  V4 (ADR-0017). Chaque changement de comportement de décision a historiquement imposé une nouvelle borne.
- **Contexte** : ticket **opérationnel**, exécuté dans une fenêtre acceptée par l'opérateur.
  Il combine pose de borne, déploiement et vérification — délibérément atomiques (INV-P3).
- **Hypothèses** :
  - H1 — PORT-002 (et le cas échéant PORT-003/004/005) sont mergés et testés.
  - H2 — l'opérateur a validé la fenêtre d'arrêt du moteur.
  - H3 — un tag de déploiement de repli existe.
- **Invariants** : INV-1, **INV-2 suspendu par ADR signé**, INV-3, INV-4,
  **INV-P3 (bascule et borne atomiques)**.
- **Fichiers** : `scripts/data_quality.py` (borne V5), `CLAUDE.md` (borne canonique),
  l'ADR d'époque, + mémoire de session. **≤ 4 fichiers.**
- **Pseudo-code** (description, non exécutable) :

```
1. VERIFIER : ADR signe, N>=100 sur V4, PORT-001 lu, PORT-002 merge      # sinon STOP
2. ARCHIVER l'epoque V4 : N final, bornes, dernier trade, commit de reference
3. POSER  CLEAN_DATA_SINCE_V5 = <timestamp du restart>
   METTRE A JOUR l'alias CLEAN_DATA_SINCE_ACTIVE -> V5
4. DEPLOYER : bash scripts/deploy_vps.sh --confirm --yes --restart
5. VERIFIER AU BOOT :
       exposition-gate > 0 des qu'une position est ouverte
       exposition affichee == exposition-gate
       borne V5 active
       CRI recalcule : N(V5) = 0 attendu
       SHA VPS == SHA local ; service actif
6. TAGGER deploy-YYYYMMDD-HHMM
7. METTRE A JOUR CLAUDE.md et la memoire de session
```

- **Plan d'action** : identique au pseudo-code, étape par étape, sans anticipation.
- **Ordre exact** : 1 → 2 → 3 → 4 → 5 → 6 → 7. L'étape 2 précède l'étape 3 : une époque qu'on ferme
  doit d'abord être archivée, sinon sa mesure est perdue.
- **Tests** : suite complète avant déploiement ; vérifications runtime de l'étape 5 après.
- **Validation** : les 9 contrôles V1 → V9 de la section « Validation » de la phase.
- **Rollback** : redéploiement du tag de repli + restauration de la borne V4. **Mais les décisions
  prises entre-temps appartiennent déjà à V5** : le rollback de code n'annule pas le fait scientifique.
- **Risques** : **R1 et R7 (critiques)**, R2.
- **Temps estimé** : 0,5 j + fenêtre opérateur.
- **Dépendances** : **PORT-001, PORT-002 (dures)** ; PORT-003/004/005 si retenus dans la même bascule.
- **Critères Done** : les 9 contrôles V1 → V9 passent ; tag de déploiement créé et poussé ;
  `CLAUDE.md` mis à jour ; époque V4 archivée avec son N final.
- **Critères Refus** :
  - ADR d'époque absent ou non signé ⇒ **refus immédiat, sans dérogation possible**.
  - Déploiement effectué sans `--confirm` ⇒ refus.
  - Borne posée sans archivage préalable de V4 ⇒ refus (mesure perdue).
  - Vérification post-déploiement non faite ou partielle ⇒ refus
    (précédent documenté : incident `ssh` sans `-n` du 2026-07-09, 3 tags d'audit mensongers).

---

## Ordre

```
PORT-001 (PASSIF, executable des maintenant)
    │
    └──► [ PORTE : ADR d'epoque signe + N>=100 sur V4 + PHASE_02_GATED terminee ]
             │
             ├──► PORT-002 ──┬──► PORT-003
             │               ├──► PORT-004
             │               └──► PORT-005
             │
             └──────────────────► PORT-006 (bascule + borne V5 + deploiement)
```

## Priorité

| Ticket | Priorité | Justification |
|---|---|---|
| PORT-001 | **P0** | Passif, exécutable immédiatement ; produit le chiffre qui **fonde** la décision d'époque. |
| PORT-002 | **P1** | Corrige la cause racine côté décision. Point de non-retour. |
| PORT-006 | **P1** | Sans borne V5, la bascule contamine le dataset. Indissociable de PORT-002. |
| PORT-003 | **P2** | Nécessaire, mais séparable ; seuils jamais éprouvés. |
| PORT-004 | **P2** | Clarification structurelle ; pas de changement de calcul attendu. |
| PORT-005 | **P3** | Amorce de l'architecture C ; le plus lourd, le moins urgent. |

## Statut

**BLOQUE** — à l'exception de **PORT-001**, marqué **PRET** (passif, sans reset de N).

Blocage levé uniquement lorsque les **quatre préconditions** de l'encart de tête sont réunies
simultanément. Aucune dérogation locale n'est admise : contrairement à ADR-0017 où l'opérateur a dérogé
explicitement à T1/T2, une dérogation ici détruirait la mesure sans compensation, puisque le rollback
d'époque n'existe pas.

**Décision en attente de l'opérateur** : autoriser ou non le reset d'époque V4 → V5.
Cette décision doit être prise **après** lecture du rapport PORT-001, jamais avant.
