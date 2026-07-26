# GOVERNANCE.md — Règles du projet crypto_ai_terminal

**Statut :** document de référence normatif du chantier « SSoT portefeuille / cohérence d'affichage ».
**Portée :** ce fichier ne crée aucune règle nouvelle. Il rassemble, pour ce chantier, les règles
déjà en vigueur (`CLAUDE.md`, ADR 0001→0018, `docs/protocole_audit_epistemique.md`) et les rend
opérationnelles sous forme de tests de classement.
**Autorité :** en cas de divergence entre ce document et `CLAUDE.md` ou un ADR accepté,
**`CLAUDE.md` et les ADR font foi**. Ce fichier doit alors être corrigé, jamais l'inverse.
**Public :** tout agent (humain ou LLM) qui ouvre un ticket dans `.claude/`.

---

## 1. Règles invariantes du projet

### 1.1 ADR-0007 — Passivité absolue des observers (règle constitutionnelle)

> Le moteur de décision est le seul composant autorisé à prendre une décision de trading.
> Tous les autres composants (observabilité, télémétrie, regret, calibration, gouvernance,
> laboratoire, replay, IA) sont strictement passifs. Ils peuvent observer, enregistrer,
> simuler, expliquer et recommander, mais ils ne peuvent jamais influencer une décision
> en temps réel. Toute évolution des paramètres doit être validée explicitement par
> l'opérateur et appliquée via un processus de configuration versionné.

Conséquences directes, non négociables :

- `FEATURE_AUTO_CALIBRATION=false` est le **défaut permanent**. Aucune exception sans ADR signé
  par l'opérateur.
- Base de sizing **épinglée à `WALLET_PAPER_CAPITAL`** jusqu'aux gates de calibration. Tout sizing
  dépendant de l'equity est une décision de calibration explicite, jamais un effet de redémarrage.
- Un composant d'affichage qui **lit** un store est passif. Le même composant qui **fournit** une
  valeur relue par une couche de décision cesse d'être passif : il devient une entrée de décision
  et bascule sous la règle de gating (§6).

### 1.2 Scientific Debt Rule — Gel architectural

> Aucune nouvelle fonctionnalité ne peut être développée tant qu'elle crée davantage
> de variables expérimentales qu'elle n'en élimine. Toute nouvelle fonctionnalité doit
> être justifiée par une hypothèse scientifique existante ou par un besoin de validation,
> jamais par une intuition ou une opportunité technique.

Conséquence directe : **zéro nouvelle couche, zéro nouvel indicateur, zéro nouvelle stratégie.**
Seuls les outils de mesure, d'audit et de certification sont autorisés. Toute demande de
fonctionnalité doit pointer vers une hypothèse H1→H6 existante qui la justifie.

**Test de recevabilité d'un ticket** (les trois doivent être vrais) :

1. Le ticket **élimine** au moins une variable expérimentale, ou en élimine plus qu'il n'en crée.
2. Le ticket ne change **aucune** entrée lue par le moteur de décision (§6).
3. Le ticket est rattachable à une hypothèse existante ou à un besoin de mesure/audit déclaré.

### 1.3 Règle du statisticien — Validation empirique obligatoire

> Aucun paramètre du moteur de trading ne peut être modifié sur la base d'une intuition,
> d'une observation isolée ou d'un faible échantillon. Toute proposition de calibration
> doit être accompagnée d'une justification statistique (taille d'échantillon, intervalles
> de confiance, puissance statistique, impact attendu sur les métriques de risque et de
> performance) et être validée par un opérateur humain avant toute application.

**Seuils minimums absolus avant toute calibration :**

| Catégorie | Minimum |
|---|---|
| Trades totaux | 500 |
| Winners | 150 |
| Losers | 150 |
| MISSED_WIN (regret) | 100 |
| GOOD_REFUSAL (regret) | 100 |
| Par régime de marché | 50 |
| Par couche bloqueuse | 30 |
| Calibration Readiness Index (CRI) | ≥ 90/100 |

Tant que ces seuils ne sont pas atteints : **ACE interdit, zéro modification de seuil.**

### 1.4 `FEATURE_AUTO_CALIBRATION=false`

Valeur permanente. Elle n'est pas un réglage d'environnement mais une conséquence de l'ADR-0007 :
une calibration automatique serait un observer qui décide. Toute activation, même temporaire, même
sur le VPS, même « pour tester », exige un ADR signé par l'opérateur.

---

## 2. Les 4 invariants du chantier

Ces quatre invariants s'appliquent à **tout** ticket produit dans `.claude/`. Un ticket qui en viole
un seul est irrecevable, quelle que soit sa valeur technique.

### INV-1 — Passivité (ADR-0007)

Aucun ticket ne peut faire remonter une valeur d'observabilité vers une couche décisionnelle.
L'affichage consomme, il ne produit jamais d'entrée de décision.

- **Vérification :** le diff ne modifie aucun appelant situé en amont d'une décision
  (`check_new_trade`, sizing, risk gate, `PortfolioBrain` en entrée de décision).
- **Falsificateur :** si un symbole modifié est lu par le pipeline de décision, INV-1 est violé.

### INV-2 — Aucun reset de N sans ADR signé

Le compteur N de l'époque courante ne peut être remis à zéro que par un ADR d'époque signé par
l'opérateur. Un reset accidentel (changement d'univers, changement d'entrée de décision, changement
de borne) détruit le burn-in en cours.

- **Vérification :** le ticket déclare explicitement `RESET D'ÉPOQUE : NON` et le justifie, ou il est
  marqué `GATED`.
- **Falsificateur :** si le comportement de décision diffère avant/après le patch sur une même
  entrée de marché, il y a reset implicite → INV-2 violé.

### INV-3 — `paper_trades.jsonl` intact

`paper_trading/mexc_simulator.py` et `paper_trading/recorder.py` sont les **seuls écrivains** de
`databases/paper_trades.jsonl`. Aucun ticket n'ajoute un écrivain, ne réécrit, ne filtre, ne
réordonne ni ne migre ce fichier.

- **Vérification :** le diff ne contient aucune écriture vers `paper_trades.jsonl` hors de ces deux
  modules.
- **Falsificateur :** un nouveau chemin d'écriture, même en append, même en test, viole INV-3.

### INV-4 — Sizing épinglé à `WALLET_PAPER_CAPITAL`

La base de sizing reste `WALLET_PAPER_CAPITAL`. Aucun ticket ne substitue `paper_equity`,
`free_cash`, `capital` recalculé ou toute autre grandeur dérivée comme base de dimensionnement.

- **Vérification :** aucune des grandeurs corrigées par le chantier d'affichage n'alimente le sizing.
- **Falsificateur :** si la taille d'un ordre change après le patch, INV-4 est violé.

---

## 3. Registre des ADR

Répertoire canonique : `docs/adr/`. Deux fichiers dérogent au répertoire :
`docs/ADR-0018-regret-source-canonical-v2.md` et `docs/ADR-001-market-scanner-architecture.md`.

**Anomalie de numérotation constatée (observation, non corrigée par ce chantier) :** deux fichiers
portent le numéro 0008 (`0008-ds001-runtime-path-resolution.md` et
`0008-scientific-intelligence-layer.md`). Ne pas réutiliser ce numéro ; ne pas le renuméroter sans
décision opérateur.

| ADR | Titre | Date | Statut | Gouverne ce chantier |
|---|---|---|---|---|
| 0000 | Template | — | Modèle | — |
| 0001 | Architecture V2 : 4 couches + 9 Bounded Contexts | 2026-06-08 | Accepté | |
| 0002 | `src/domain/` comme SSoT des objets métier | 2026-06-08 | Accepté | contexte SSoT |
| 0003 | DecisionExplainer : observabilité du pipeline décisionnel via Telegram | 2026-06-29 | Accepté | |
| 0004 | Rejection Observatory : JSONL atomique plutôt que SQLite ou CSV | 2026-06-29 | Accepté | |
| 0005 | Regret Intelligence : évaluation multi-horizon asynchrone | 2026-06-29 | Accepté | |
| 0006 | Decision Event Bus : découplage moteur/observateurs | 2026-06-29 | Accepté | |
| **0007** | **Principe de passivité : séparation stricte moteur/observabilité** | 2026-06-29 | **Accepté — règle constitutionnelle** | **OUI — INV-1** |
| 0008 (a) | Rule DS-001 : Runtime path resolution | 2026-07-03 | Accepté | |
| 0008 (b) | Scientific Intelligence Layer et SDOS | 2026-07-01 | Accepté | |
| 0009 | SDOS Terminal comme interface d'observation, abrogation de la règle Telegram-only | 2026-07-02 | Accepté | contexte affichage |
| 0010 | Réconciliation VPS et leçons d'observabilité | 2026-07-05 | Accepté | |
| **0011** | **Borne canonique du dataset propre et pré-enregistrement du CRI** | 2026-07-05 | Accepté | **OUI — époque V1** |
| **0012** | **Époque SEC-01 : fin de la contamination `consecutive_losses`** (+ addendum) | 2026-07-09 | Accepté | **OUI — époques V2/V3** |
| 0013 | Deux points morts dans la machine d'état runtime (SAFE_MODE / RECOVERY) | 2026-07-11 | Accepté | |
| 0014 | Brancher `StrategyRanker`/`MetaStrategyEngine` sur les clôtures MexcSim | 2026-07-13 | **Proposé** (en attente opérateur) | référence : ce serait GATED |
| **0015** | **Univers de trading épinglé pendant le burn-in** | 2026-07-14 | Accepté | **OUI — univers = variable** |
| **0016** | **Univers d'observation MEXC complet (spot + perp), strictement passif** | 2026-07-15 | Accepté | **OUI — modèle « observer passif »** |
| **0017** | **Époque dataset V4 et paliers d'élargissement de l'univers tradé** | 2026-07-16 | Accepté sur le principe | **OUI — procédure de reset** |
| **0018** | **Source canonique de regret = `regret-v2` (pour V4+)** | 2026-07-21 | Accepté | **OUI — MISSED_WIN / GOOD_REFUSAL** |
| ADR-001 (hors série) | Architecture cible du Market Scanner Quant | 2026-06-16 | DRAFT, prospectif | — |

**Numéros libres à partir de ADR-0019.** Tout ticket marqué `GATED` doit indiquer qu'il consommera
un numéro ≥ 0019, sans le réserver à l'avance (le numéro est attribué à la rédaction effective).

**ADR gouvernant ce chantier :** 0007, 0011, 0012, 0015, 0016, 0017, 0018.

---

## 4. Les resets d'époque

### 4.1 Définition

Une **époque** est une fenêtre temporelle pendant laquelle le comportement de décision et l'univers
tradé sont constants. Les trades d'époques différentes ne sont pas comparables et **ne s'additionnent
pas** dans N. Changer une variable expérimentale structurelle = changer d'époque = **N repart à 0**.

### 4.2 Historique

| Époque | Borne (`CLEAN_DATA_SINCE`) | ADR | Cause du reset |
|---|---|---|---|
| V1 | `2026-06-25` | ADR-0011 | Qualité de données : tokens toxiques, bypass `meta_allowed` |
| V2 | `2026-07-09T01:16:00Z` | ADR-0012 | Correction `consecutive_losses` (échecs d'exécution technique comptés comme pertes, 5 mécanismes de décision contaminés) — **fenêtre invalidée a posteriori** : le déploiement du 2026-07-08 était silencieusement partiel (`ssh` sans `-n` dans `deploy_vps.sh`), SEC-01 n'a jamais été chargé |
| V3 | `2026-07-09T07:45:00Z` | addendum ADR-0012 | Borne postérieure au restart de rattrapage qui charge réellement SEC-01. Époque « 28 paires », N=49, **archivée** et comparable en interne |
| **V4 (courante)** | **`2026-07-17T01:30:00Z`** | **ADR-0017** | **Univers tradé élargi à 135 paires épinglées (palier 1). L'univers est une variable expérimentale.** |

Ces bornes sont **emboîtées** : chaque version exclut strictement un sur-ensemble de la précédente.
Adopter la plus récente satisfait simultanément toutes les exigences antérieures. Les bornes
antérieures restent documentées pour l'audit qualité de données, jamais pour le calcul de N.

**Source unique de la borne :** `scripts/data_quality.py` (constante `CLEAN_DATA_SINCE_V4`, alias
`CLEAN_DATA_SINCE_ACTIVE`), consommée par `tools/cri_calculator.py::load_clean_trades()`.
La borne **n'est jamais recopiée localement** dans un autre module.

### 4.3 Ce qui déclenche un reset d'époque

Déclenchement automatique (la liste n'est pas exhaustive ; en cas de doute, appliquer le test §6) :

1. Changement de l'univers tradé (ajout, retrait, rotation, passage à un palier supérieur).
2. Changement d'une entrée lue par le moteur de décision (store de positions, exposure, capital,
   equity, cash consommés par une couche décisionnelle).
3. Changement d'un seuil de décision, y compris par régime.
4. Changement du sizing ou de sa base.
5. Changement du comportement d'une couche bloqueuse (`check_new_trade`, risk gate,
   `PortfolioBrain` en entrée de décision, gates SEC).
6. Correction d'un bug qui modifie les décisions produites, même si la correction est « juste ».
7. Déplacement de `CLEAN_DATA_SINCE` lui-même.

### 4.4 Ce que coûte un reset

- **N repart à 0.** Le burn-in en cours est détruit. Au rythme observé, la reconstitution se compte
  en semaines, pas en jours.
- Tous les seuils du §1.3 repartent de zéro : 500 trades, 150 winners, 150 losers, 100 MISSED_WIN,
  100 GOOD_REFUSAL, 50 par régime, 30 par couche bloqueuse.
- Le CRI de l'époque précédente devient non transférable.
- Les checkpoints (§5) reculent d'autant. Le passage au capital réel est repoussé mécaniquement.
- Contrainte externe à intégrer : la fin d'essai GCP (~2026-08-05) borne la durée pendant laquelle
  le burn-in peut tourner sans décision d'infrastructure. Un reset consomme cette marge.

### 4.5 Procédure obligatoire de reset

Aucun reset n'est valide s'il manque une seule de ces étapes :

1. **ADR d'époque rédigé** (numéro ≥ 0019), énonçant : la variable expérimentale changée, la
   nouvelle borne au format ISO UTC, ce qui devient incomparable, et le coût accepté.
2. **Signature explicite de l'opérateur** dans le champ Statut de l'ADR (décision datée, citée).
3. **Mise à jour de `scripts/data_quality.py`** : nouvelle constante `CLEAN_DATA_SINCE_Vn` +
   bascule de l'alias `CLEAN_DATA_SINCE_ACTIVE`. Les anciennes constantes sont conservées, jamais
   supprimées.
4. **Mise à jour de `CLAUDE.md`** (bloc « Borne canonique du dataset propre ») avec le lien vers
   l'ADR et l'historique de remplacement.
5. **Mise à jour de la mémoire projet** (`MEMORY.md` + fiche époque) pour que les sessions suivantes
   ne raisonnent pas sur l'ancienne borne.
6. **Archivage de l'époque sortante** : N final, univers, période, statut (« archivée, comparable en
   interne »).
7. Redémarrage effectif du moteur avec le nouveau comportement, **postérieur** à la borne déclarée.
   La borne doit être postérieure au restart réellement vérifié, pas au commit — leçon ADR-0012.

---

## 5. Les checkpoints

Progression ordonnée. Chaque checkpoint est une **précondition** du suivant ; aucun ne s'anticipe.

### 5.1 Checkpoint L2 — Validation scientifique

- État de référence : L2 = 35/100 (`CLAUDE.md`, blueprint v2).
- Gate d'entrée S1→S5 : **N ≥ 100** sur l'époque courante.
- Tant que L2 n'est pas franchi : L3 (gouvernance), L3.5 (SDOS), L4 (lab), L5 (twin) restent fermés,
  et le passage Phase A du capital réel reste fermé.
- Discipline opérateur en vigueur : **« zéro nouvelle construction avant N ≈ 100 »**.

### 5.2 Checkpoint N ≥ 100 (époque courante)

- Débloque : le checkpoint L2, l'examen des tickets `GATED` (examen, pas exécution), le backlog
  accepté post-checkpoint (`measurement_contract_validator.py`, bloc « Certification » des dossiers).
- Ne débloque **pas** : la calibration, la modification de seuils, le capital réel.

### 5.3 Checkpoint calibration — N ≥ 500 et CRI ≥ 90

- Tous les seuils du §1.3 doivent être atteints **simultanément**, sur la **même** époque.
- Le CRI doit être calculé par `tools/cri_calculator.py` sur la borne active, avec source de regret
  canonique `regret-v2` (ADR-0018), fraîcheur et validité contrôlées.
- Seul ce checkpoint autorise l'ACE et la modification d'un seuil, et uniquement avec la
  justification statistique complète du §1.3, validée par l'opérateur.

### 5.4 Verrous Go/No-Go EXP-001

En plus des métriques financières, deux verrous bloquants :

1. **Zéro Inconclusive critique** : si H1, H2 ou H3 est `Inconclusive` avec
   `n_at_eval >= min_n_required` → passage réel **interdit**.
2. **Zéro contradiction** : les conflits H1↔H3 et H2↔H3 doivent être résolus
   (`experiments/EXP-001.yaml § known_conflict_pairs`).

### 5.5 Passage au capital réel

- Ordre imposé : checkpoint L2 franchi → verrous Go/No-Go EXP-001 levés → **décision opérateur** →
  Phase A ($50 réel, gate L6 Phase A) → Phase B → Phase C.
- Aucun agent ne propose, ne prépare ni n'exécute un passage au capital réel. C'est une décision
  opérateur exclusive (§8).

---

## 6. Règle de gating

### 6.1 Test opérationnel (à appliquer à tout changement, sans exception)

> **« Ce changement modifie-t-il ce que LIT le moteur de décision ? »**

- **NON** → le changement est **exécutable** sous le gel, s'il respecte aussi §1.2 et les 4 invariants.
- **OUI** → le changement est **`GATED`**.
- **INCERTAIN** → traiter comme **OUI**. Le doute est gaté par défaut (règle du maillon faible :
  la classification d'un ticket vaut celle de son maillon le plus faible).

Test dérivé, utile quand la lecture du code ne tranche pas :

> « À entrée de marché identique, la décision produite après le patch peut-elle différer de la
> décision produite avant ? » — Si oui : `GATED`.

### 6.2 Marquage obligatoire

Tout ticket classé `OUI` porte, en tête, la bannière exacte :

```
GATED / RESET D'ÉPOQUE / N -> 0 / ADR OBLIGATOIRE
```

Et déclare sa **précondition de déblocage** :

> checkpoint L2 franchi **ET** N ≥ 100 atteint sur l'époque courante **ET** ADR d'époque signé par
> l'opérateur.

Ces tickets ne doivent **jamais** être présentés comme exécutables immédiatement, ni figurer dans
une file d'exécution active, ni être « préparés en attendant » par un patch partiel.

### 6.3 Symboles sensibles — liste explicite

Toucher l'un de ces symboles **en entrée de décision** déclenche `GATED` :

| Symbole / zone | Nature |
|---|---|
| `PositionManager` (contenu, alimentation, lecture par la décision) | store lu par les contraintes de décision |
| `check_new_trade` | couche bloqueuse |
| Sizing (base, formule, `WALLET_PAPER_CAPITAL`, Kelly/EV/vol) | dimensionnement des ordres |
| Risk (risk gate, limites, exposition max, `MAX_TOTAL_EXPOSURE_PCT`) | couche bloqueuse |
| `PortfolioBrain` **en entrée de décision** (`portfolio_health` consommé par une décision) | 8 checks portefeuille |
| Seuils par régime (score packet, seuil 66/72, RECOVERY/NORMAL) | paramètres de décision |
| `CLEAN_DATA_SINCE` / `scripts/data_quality.py` | définition de l'époque |
| Univers tradé (`UNIVERSE_PINNED_SYMBOLS`, paliers ADR-0017) | variable expérimentale |
| `FEATURE_AUTO_CALIBRATION`, ACE | passivité ADR-0007 |
| Écriture de `paper_trades.jsonl` | INV-3 |

**Nuance décisive pour ce chantier** : `PortfolioBrain` **en sortie d'affichage** (valeur lue par un
panneau Telegram ou un snapshot) n'est pas gaté ; `PortfolioBrain` **en entrée de décision** l'est.
Le même module peut donc être touché ou non selon le sens de la dépendance. Un ticket doit déclarer
explicitement lequel des deux sens il modifie.

### 6.4 Cas connu et gelé volontairement

`pos_manager` reste la source des contraintes de décision et n'est **jamais** modifié par le chantier
d'affichage. Corriger son alimentation changerait le comportement de décision en pleine validation
scientifique. Ce bug est **documenté, gelé, à corriger à la calibration**
(docstring `core/advisor_loop.py:437-448`). Toute proposition de « corriger enfin l'entrée de
pos_manager » est `GATED`, sans discussion.

---

## 7. Interdictions sous le gel actuel

Numérotées, opposables, sans exception implicite.

1. **INT-01** — Interdit d'ajouter une couche décisionnelle ou une règle de filtrage.
2. **INT-02** — Interdit d'ajouter un indicateur technique.
3. **INT-03** — Interdit d'ajouter une stratégie ou une personnalité.
4. **INT-04** — Interdit de modifier un seuil existant, y compris « temporairement » ou « pour tester ».
5. **INT-05** — Interdit de modifier le sizing ou sa base (INV-4).
6. **INT-06** — Interdit de modifier `PositionManager`, `check_new_trade`, le risk gate, ou
   `PortfolioBrain` en entrée de décision (§6.3) — sauf ticket `GATED` débloqué.
7. **INT-07** — Interdit de faire remonter une valeur d'observabilité vers une décision (INV-1).
8. **INT-08** — Interdit d'activer `FEATURE_AUTO_CALIBRATION` ou l'ACE.
9. **INT-09** — Interdit d'ajouter un écrivain de `paper_trades.jsonl`, ou de réécrire / filtrer /
   migrer ce fichier (INV-3).
10. **INT-10** — Interdit de déplacer `CLEAN_DATA_SINCE` ou de recopier la borne hors de
    `scripts/data_quality.py`.
11. **INT-11** — Interdit de changer l'univers tradé (ajout, retrait, palier) hors ADR d'époque signé.
12. **INT-12** — Interdit de provoquer un reset de N, même indirect, même « propre », sans la
    procédure §4.5 complète.
13. **INT-13** — Interdit de déployer automatiquement. Le déploiement est un geste délibéré :
    `bash scripts/deploy_vps.sh --confirm [--yes] [--dry-run] [--restart]`. Le hook `post-commit` est
    aboli et ne doit pas être réactivé.
14. **INT-14** — Interdit de redémarrer le service sans double opt-in explicite (`VPS_RESTART_CMD`
    défini **et** `--restart` passé).
15. **INT-15** — Interdit de conclure un déploiement sur la base d'un code retour : la vérification
    se fait sur l'état réel du VPS (leçon ADR-0012, incident `ssh` sans `-n`).
16. **INT-16** — Interdit d'écrire un ticket non atomique : maximum **300 lignes modifiées OU 4
    fichiers**, la contrainte la plus stricte des deux s'applique. Un ticket = un commit = revertable
    individuellement.
17. **INT-17** — Interdit de présenter un ticket `GATED` comme exécutable, ou de le placer dans une
    file active.
18. **INT-18** — Interdit d'inventer un fait sur le code. Information manquante ⇒ écrire
    **« À CONFIRMER AU DÉMARRAGE DU TICKET »**.
19. **INT-19** — Interdit de traiter `databases/*.jsonl` **local** comme l'état du VPS : fichier
    gitignoré, souvent vide ou périmé, jamais une vérification d'état runtime.
20. **INT-20** — Interdit de fournir une justification de calibration sans les éléments statistiques
    du §1.3 (taille d'échantillon, IC, puissance, impact attendu).

---

## 8. Autorité de décision

### 8.1 Opérateur (Mathieu) — décisions exclusives, non délégables

| Domaine | Portée |
|---|---|
| Époque | Déclencher un reset, signer l'ADR d'époque, fixer `CLEAN_DATA_SINCE` |
| Capital réel | Passage paper → réel, montants, phases A/B/C |
| Déploiement | Autoriser `deploy_vps.sh --confirm`, autoriser `--restart` |
| Seuils & calibration | Toute modification de paramètre du moteur, activation de l'ACE |
| Univers | Univers tradé, paliers d'élargissement |
| Feature flags de décision | `FEATURE_AUTO_CALIBRATION` et tout flag modifiant une décision |
| Statut des ADR | Passage `Proposé` → `Accepté` (ex. ADR-0014 toujours en attente) |
| Infrastructure | Décision GCP / hébergement / continuité du burn-in |
| Priorisation | Ordre des phases et des tickets |

### 8.2 Agent (Claude Code) — autorisé

- Analyser, mesurer, auditer, documenter.
- Rédiger des tickets, des specs, des ADR **au statut « Proposé »**.
- Implémenter un ticket **non gaté** explicitement demandé, dans les limites d'atomicité (INT-16).
- Exécuter les tests, rapporter les résultats bruts.
- Signaler une violation de règle et **s'arrêter**.

### 8.3 Agent — interdit

- Décider seul d'un reset, d'un déploiement, d'un redémarrage, d'un changement de seuil.
- Signer un ADR, ou passer un ADR de « Proposé » à « Accepté ».
- Manipuler des valeurs de clés API ou de secrets.
- Reformuler une interdiction en recommandation.

### 8.4 Règle d'arrêt

À la **première anomalie** rencontrée pendant une opération à risque : arrêt immédiat, rapport à
l'opérateur, revérification avant toute conclusion. Ne jamais poursuivre « pour voir ».

### 8.5 Discipline de rédaction

Tout audit, critique ou dossier produit dans ce chantier applique le
**protocole d'audit épistémique v3** (`docs/protocole_audit_epistemique.md`) : une phrase = une
catégorie (Observation / Inférence / Hypothèse / Décision), règle du maillon faible, portée explicite,
double falsificateur, dette épistémique rattachée à une décision, principe de symétrie.

---

## 9. Référence rapide — classement d'un changement

| Question | Réponse | Classement |
|---|---|---|
| Modifie ce que lit le moteur de décision ? | Oui / Incertain | `GATED` |
| Touche un symbole du §6.3 en entrée de décision ? | Oui | `GATED` |
| Change l'univers, un seuil, le sizing, la borne d'époque ? | Oui | `GATED` |
| Ajoute une couche / un indicateur / une stratégie ? | Oui | **Refusé** (INT-01→03) |
| Ajoute un écrivain de `paper_trades.jsonl` ? | Oui | **Refusé** (INT-09) |
| Affichage / mesure / audit seulement, > 300 lignes ou > 4 fichiers ? | Oui | **À scinder** (INT-16) |
| Affichage / mesure / audit seulement, atomique, 4 invariants respectés ? | Oui | **Exécutable** |
