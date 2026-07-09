# CLAUDE.md — Règles invariantes du projet crypto_ai_terminal

Ces règles s'appliquent à toutes les sessions, sans exception.

---

## Règle constitutionnelle — Passivité absolue des observers (ADR-0007)

> Le moteur de décision est le seul composant autorisé à prendre une décision de trading.
> Tous les autres composants (observabilité, télémétrie, regret, calibration, gouvernance,
> laboratoire, replay, IA) sont strictement passifs. Ils peuvent observer, enregistrer,
> simuler, expliquer et recommander, mais ils ne peuvent jamais influencer une décision
> en temps réel. Toute évolution des paramètres doit être validée explicitement par
> l'opérateur et appliquée via un processus de configuration versionné.

**Conséquence directe :** `FEATURE_AUTO_CALIBRATION=false` est le défaut permanent.
Aucune exception sans ADR signé par l'opérateur.
Base de sizing épinglée à `WALLET_PAPER_CAPITAL` jusqu'aux gates de calibration ;
tout sizing dépendant de l'equity est une décision de calibration explicite,
jamais un effet de redémarrage.

---

## Scientific Debt Rule — Gel architectural

> Aucune nouvelle fonctionnalité ne peut être développée tant qu'elle crée davantage
> de variables expérimentales qu'elle n'en élimine. Toute nouvelle fonctionnalité doit
> être justifiée par une hypothèse scientifique existante ou par un besoin de validation,
> jamais par une intuition ou une opportunité technique.

**Conséquence directe :** Phase II = zéro nouvelles couches, zéro nouveaux indicateurs,
zéro nouvelles stratégies. Seuls les outils de mesure, d'audit et de certification
sont autorisés. Toute demande de nouvelle fonctionnalité doit pointer vers une hypothèse
H1-H6 existante qui la justifie.

---

## Règle du statisticien — Validation empirique obligatoire

> Aucun paramètre du moteur de trading ne peut être modifié sur la base d'une intuition,
> d'une observation isolée ou d'un faible échantillon. Toute proposition de calibration
> doit être accompagnée d'une justification statistique (taille d'échantillon, intervalles
> de confiance, puissance statistique, impact attendu sur les métriques de risque et de
> performance) et être validée par un opérateur humain avant toute application.

**Seuil minimum absolu avant toute calibration :**

| Catégorie              | Minimum |
|------------------------|---------|
| Trades totaux          | 500     |
| Winners                | 150     |
| Losers                 | 150     |
| MISSED_WIN (regret)    | 100     |
| GOOD_REFUSAL (regret)  | 100     |
| Par régime de marché   | 50      |
| Par couche bloqueuse   | 30      |
| Calibration Readiness Index (CRI) | ≥ 90/100 |

Tant que ces seuils ne sont pas atteints : **ACE interdit, zéro modification de seuil**.

**Borne canonique du dataset propre — `CLEAN_DATA_SINCE_V3 = 2026-07-09T07:45:00Z`.**
Toute donnée antérieure à ce timestamp (`paper_trades.jsonl`, `regret_analysis.jsonl`)
est invalide pour le calcul de N et de tout seuil ci-dessus — appliquée par
`scripts/data_quality.py` (source unique) et importée par
`tools/cri_calculator.py::load_clean_trades()`, jamais copiée localement.
Cette borne **remplace** v1 (`2026-06-25`, ADR-0011) et v2
(`2026-07-09T01:16:00Z`, ADR-0012) sans les contredire : chaque version
exclut strictement un sur-ensemble de la précédente — adopter la borne la
plus récente et la plus large satisfait toutes les exigences simultanément.
Historique : v2 marquait le restart censé activer le gate d'exécution réelle
SEC-01 (correction de `consecutive_losses` qui confondait échecs d'exécution
technique et vraies pertes, contaminant 5 mécanismes de décision — voir
ADR-0012) ; mais le déploiement du 2026-07-08 était **silencieusement
partiel** (bug `ssh` sans `-n` dans `deploy_vps.sh`, tags d'audit
`deploy-20260707-0806` → `deploy-20260708-1831` créés sur de faux succès) :
`execution_engine.py` n'a jamais atteint le VPS et SEC-01 était inactif dans
la fenêtre v2 (ordre réel encore tenté le 2026-07-09 06:28 UTC). v3 = borne
postérieure au restart de rattrapage qui charge réellement SEC-01 — voir
**addendum ADR-0012**. v1 reste documentée pour l'audit qualité de données
(`scripts/data_quality.py`, tokens toxiques/bypass `meta_allowed` — un
problème différent).

---

## Phase actuelle : Validation Scientifique (gel fonctionnel étendu)

Le développement fonctionnel est **gelé**. Sont désormais **interdits** :

- Nouvelles couches IA ou décisionnelles
- Nouveaux indicateurs techniques
- Nouvelles stratégies ou personnalités
- Nouvelles règles de décision ou de filtrage
- Toute modification des seuils existants

**Autorisés exclusivement :**
outils de mesure, outils d'audit, tableaux de bord scientifiques,
visualisation des hypothèses/datasets/expériences, qualité statistique, reproductibilité.

---

## Project Maturity Index (PMI) et SDOS

Indicateur composite en 7 niveaux, complété par la couche L3.5 du
Scientific Decision Operating System (SDOS). Référence normative :
`docs/blueprint_v2.md`.

```
PMI = (L1 + L2 + L3 + L4 + L5 + L6 + L7) / 700
SDOS Capability = (L1 + L2 + L3 + L3.5 + L4 + L5 + L6 + L7) / 800
```

| Niveau | Nom | Score | Gate |
|--------|-----|-------|------|
| L1 | Engineering | 100/100 | FRANCHIE ✅ |
| L2 | Scientific Validation | 35/100 | gate S1→S5 (N>=100) |
| L3 | Scientific Governance | 10/100 | gate L2 |
| L3.5 | Scientific Intelligence Layer | 0/100 | gate L3 + Observer Certification |
| L4 | Research Lab | 0/100 | gate L3.5 + N>=500 |
| L5 | Digital Twin | 0/100 | gate L4 |
| L6 | Live Operations | 36/100 | gate L2 → Phase A |
| L7 | Scientific Intelligence Core | 0/100 | gate L6 Phase C |
| **PMI-7** | | **181/700 = 26%** | |
| **SDOS** | | **181/800 = 22.6%** | |

Baseline PMI-7 : 2026-06-30. Baseline SDOS : 2026-07-01.
Les scores progressent avec les gates franchies, jamais avec le nombre de
lignes de code ajoutées.

### Double lecture PMI

| Score | Signification | Baseline |
|---|---|---|
| **Capability Score** | Ce que le système peut faire | PMI-7 181/700 = 26% ; SDOS 181/800 = 22.6% |
| **Evidence Score** | Ce qui est démontré par les données | 0/700 = 0% ; SDOS 0/800 = 0% |

**Evidence Score = 0** signifie : aucune donnée certifiée, aucune hypothèse conclue.
L'architecture est mature. Les preuves restent à construire.

---

## Verrous Go/No-Go EXP-001 (en plus des métriques financières)

1. **Zéro Inconclusive critique** : si H1, H2 ou H3 est `Inconclusive` avec
   `n_at_eval >= min_n_required` → passage réel interdit.
2. **Zéro contradiction** : conflits H1↔H3 et H2↔H3 doivent être résolus
   (voir `experiments/EXP-001.yaml § known_conflict_pairs`).

---

## Déploiement VPS — geste délibéré (2026-07-04)

Le hook `.git/hooks/post-commit` qui déployait automatiquement chaque commit
vers le VPS a été **aboli** (renommé `post-commit.disabled`, réversible mais
non réactivé). Un commit sur `main` ne déploie plus jamais rien tout seul —
conforme au gel scientifique, un déploiement doit rester un acte conscient.

**Nouveau geste** :

```
bash scripts/deploy_vps.sh --confirm            # avec confirmation interactive
bash scripts/deploy_vps.sh --confirm --yes       # usage scripté, sans prompt
bash scripts/deploy_vps.sh --confirm --dry-run   # simulation, aucun transfert réel
bash scripts/deploy_vps.sh --confirm --restart   # + redémarrage du service (double opt-in)
```

Sans `--confirm` : affiche l'usage, exit 1. Aucune exécution implicite.

Le script conserve le filtre d'exclusion (`databases/|cache/|logs/|tests/|docs/`)
qui empêche d'écraser l'état runtime du VPS (dont `runtime_config.json`,
paramètres de risque live) via un commit accidentel.

Après un déploiement réussi (jamais avant, jamais en `--dry-run`), un tag
git annoté `deploy-YYYYMMDD-HHMM` est créé et poussé — SHA du commit + liste
des fichiers transférés dans le message. **Ce tag est le journal d'audit des
déploiements**, `git tag -l "deploy-*"` en donne l'historique complet.

Le redémarrage du service (`pkill` + relance `advisor_loop.py`) reste un
double opt-in : `VPS_RESTART_CMD` défini dans `.env` ET `--restart` passé
explicitement. Jamais implicite, même avec un fichier critique déployé.
