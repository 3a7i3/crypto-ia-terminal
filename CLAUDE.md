# CLAUDE.md — Règles invariantes du projet crypto_ai_terminal

Ces règles s'appliquent à toutes les sessions, sans exception.

> **Structure de ce document** (revue forensique 2026-09-26) :
> §1 règles constitutionnelles (permanentes) · §2 frontières d'autorité
> courantes PAPER/PPL/Research · §3 seuils statistiques · §4 déploiement ·
> §5 instructions temporaires périmées, conservées pour l'audit uniquement.
>
> **Autorité de priorisation** :
> [#148 — MASTER ROADMAP](https://github.com/3a7i3/crypto-ia-terminal/issues/148).
> En cas de divergence entre ce fichier et #148 sur l'*état courant*, #148 gagne.
> Les règles constitutionnelles du §1 ne sont pas, elles, révisables par #148.

---

# §1 — RÈGLES CONSTITUTIONNELLES (permanentes)

## Passivité absolue des observers (ADR-0007)

> Le moteur de décision est le seul composant autorisé à prendre une décision de trading.
> Tous les autres composants (observabilité, télémétrie, regret, calibration, gouvernance,
> laboratoire, replay, IA) sont strictement passifs. Ils peuvent observer, enregistrer,
> simuler, expliquer et recommander, mais ils ne peuvent jamais influencer une décision
> en temps réel. Toute évolution des paramètres doit être validée explicitement par
> l'opérateur et appliquée via un processus de configuration versionné.

**Conséquence directe :** `FEATURE_AUTO_CALIBRATION=false` est le défaut permanent.
Aucune exception sans ADR signé par l'opérateur.

## Scientific Debt Rule — Gel architectural

> Aucune nouvelle fonctionnalité ne peut être développée tant qu'elle crée davantage
> de variables expérimentales qu'elle n'en élimine. Toute nouvelle fonctionnalité doit
> être justifiée par une hypothèse scientifique existante ou par un besoin de validation,
> jamais par une intuition ou une opportunité technique.

**Conséquence directe :** zéro nouvelles couches décisionnelles, zéro nouveaux
indicateurs, zéro nouvelles stratégies. Seuls les outils de mesure, d'audit, de
certification et l'infrastructure Research sont autorisés.

## Règle du statisticien — Validation empirique obligatoire

> Aucun paramètre du moteur de trading ne peut être modifié sur la base d'une intuition,
> d'une observation isolée ou d'un faible échantillon. Toute proposition de calibration
> doit être accompagnée d'une justification statistique (taille d'échantillon, intervalles
> de confiance, puissance statistique, impact attendu sur les métriques de risque et de
> performance) et être validée par un opérateur humain avant toute application.

## Doctrine Research Lab (ADR / #237 RL-ARCH-00)

> **PAPER produit les faits. Research Lab produit des hypothèses.
> Une promotion explicite crée une future expérience.**

Flux autorisé :

```
PAPER → dataset immuable → Research Lab → replay/counterfactual
      → candidate artifact → promotion explicite → future époque SHADOW/PAPER
```

Flux interdit :

```
Research Lab → mutation de l'époque PAPER/F00/burn-in active
```

## `UNRESOLVED IS DATA` (PPL-02C)

Un outcome non résolu n'est jamais converti en PnL synthétique, ni en zéro.
Une position dont l'outcome exact n'est pas connu produit `POSITION_UNRESOLVED`
et est **exclue** de la population de performance, jamais comptée comme
`pnl = 0`.

---

# §2 — FRONTIÈRES D'AUTORITÉ COURANTES (PAPER / PPL / Research)

## Autorité lifecycle PAPER

`PAPER_LIFECYCLE_AUTHORITY = PPL_AUTHORITY` — transition runtime effectuée et
certifiée (PPL-02E).

| Propriété | Valeur |
|---|---|
| Époque F00 canonique | `F00-EPOCH-01-20260920T084335Z` |
| Capital scientifique initial | `1000.0 USDT` |
| T0 scientifique | `2026-09-20T20:39:57.056499Z` |
| Population PPL finale | 27 événements = 1 EPOCH_CREATED + 13 OPEN + 13 CLOSE + **0 UNRESOLVED** |
| SHA-256 PPL final | `50220fdfd4a75d219795db518d77ab6c6574883eb74a6a8db9e26a6d8cf729b2` |
| Verdict | `F00_FINAL_SCIENTIFIC_EXPERIMENT_CERTIFIED` |

Une seule autorité lifecycle par processus. `DUAL_AUTHORITY` est interdit.
`paper_trades.jsonl` est une **projection de compatibilité/recherche**, jamais
une autorité lifecycle, capital ou restart.

## Sémantique de capital et de sizing — ⚠️ point de vigilance

Sous le chemin d'autorité PPL certifié par F00, **`WALLET_PAPER_CAPITAL` n'est
pas l'autorité de capital scientifique**. L'énoncé historique
« base de sizing épinglée à `WALLET_PAPER_CAPITAL` » est **périmé** pour ce
chemin et ne doit pas être réutilisé.

Preuve F00 / A5 (`EXPLAINED_DUAL_PATH_SIMULATOR_AUTO_SIZE`) :

- `PAPER_LIFECYCLE_AUTHORITY = PPL_AUTHORITY` ;
- `MexcSimulator` a lié son état de capital à la **projection PPL** ;
- le contexte de sizing `DecisionPacket` / `CapitalEngine` (30.0 → 37.5 USDT)
  **n'a pas été transmis** comme principal PAPER ;
- `advisor_loop` a appelé PAPER avec `qty_usd = 0.0` ;
- `MexcSimulator` a donc appliqué
  `principal = min(PPL available_cash * 0.15, MEXC_SIM_MAX_POSITION_USD)` ;
- valeur F00 gelée : `MEXC_SIM_MAX_POSITION_USD = 10` ;
- les 13 principals OPEN autoritaires F00 valaient donc exactement 10 USDT.

**Interdictions de lecture :** ne pas écrire que `WALLET_PAPER_CAPITAL` est
l'autorité de capital scientifique du chemin PPL ; ne pas affirmer que les
30–37.5 USDT du DecisionPacket auraient dû être exécutés, ni qu'ils auraient
amélioré la performance. Cette seconde question est une **hypothèse de candidat
futur**, pas un fait certifié, et exige une nouvelle frontière d'évaluation.

La base de sizing reste épinglée jusqu'aux gates de calibration ; tout sizing
dépendant de l'equity est une décision de calibration explicite, jamais un effet
de redémarrage.

## Bornes de population scientifique

Deux contrats de population coexistent — ne jamais les confondre :

| Mode | Contrat de population | Usage |
|---|---|---|
| `PPL_AUTHORITY` | exactement `PPL_AUTHORITY_EPOCH_ID` ; Legacy, autres époques et outcomes `UNRESOLVED`/PnL absent exclus | **canonique** pour F00 |
| `LEGACY_AUTHORITY` / `PPL_SHADOW` | fenêtre historique `CLEAN_DATA_SINCE_ACTIVE` + heuristiques qualité | **historique / non autoritaire** |

Source unique : `scripts/data_quality.py` (alias `CLEAN_DATA_SINCE_ACTIVE`) et
`tools/cri_calculator.py::load_clean_trades()`. Jamais recopiée localement.

**`CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`** (ADR-0017) reste la borne du
**chemin Legacy uniquement**. Sous `PPL_AUTHORITY`, l'identité de population est
l'`paper_epoch_id`, pas un timestamp : la borne V4 n'y est pas appliquée.
Elle remplace v1 (`2026-06-25`, ADR-0011), v2 (`2026-07-09T01:16:00Z`,
ADR-0012) et v3 (`2026-07-09T07:45:00Z`, addendum ADR-0012) sans les
contredire — chaque version exclut strictement un sur-ensemble de la précédente.

## Univers expérimental

L'univers tradé est une **variable expérimentale** : changer d'univers = changer
d'époque.

État certifié le plus récent (#148 § OPS-C / MARKET-UNIVERSE-01, restart
PPL-02D du 2026-09-16) : **135 symboles configurés, 125 valides, 10 rejetés** —
dérive runtime/config signalée `⚠️ RUNTIME DRIFT À REMÉDIER`, aucun bypass
autorisé, remédiation et recertification requises avant reprise du runtime
SHADOW.

Distinguer explicitement, sans jamais les additionner :
univers **configuré** (`UNIVERSE_PINNED_SYMBOLS`) · univers **certifié/valide**
(`core/universe_certification.py`) · univers **observé**
(`databases/observation/`, ADR-0016) · symboles **réellement représentés** dans
une population F00. Le contrat de certification énonce déjà :
`configured universe != validated universe != scan results`.

`experiments/EXP-001.yaml` porte encore `trading_universe_size: null` — champ
non renseigné, à ne pas interpréter comme une cardinalité certifiée.

## Non-autorisations courantes

⛔ burn-in · ⛔ nouvelle époque PAPER · ⛔ activation Watchdog
⛔ TESTNET · ⛔ LIVE · ⛔ écritures exchange
⛔ calibration alpha · ⛔ nouveau signal/indicateur/stratégie
⛔ tuning stratégie/risk/sizing · ⛔ FIN-03

`PAPER_TRADING_ENABLED=true` et `LIVE_TRADING_CONFIRMED=false` restent
obligatoires.

---

# §3 — SEUILS STATISTIQUES

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

## Verrous Go/No-Go EXP-001

1. **Zéro Inconclusive critique** : si H1, H2 ou H3 est `Inconclusive` avec
   `n_at_eval >= min_n_required` → passage réel interdit.
2. **Zéro contradiction** : conflits H1↔H3 et H2↔H3 doivent être résolus
   (voir `experiments/EXP-001.yaml § known_conflict_pairs`).

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

> Ces scores sont des baselines de juin/juillet 2026 et n'ont pas été
> recalculés depuis la chaîne FIN/F00. À traiter comme un repère historique
> tant qu'un recalcul daté n'est pas produit.

---

# §4 — DÉPLOIEMENT VPS — geste délibéré (2026-07-04)

Le hook `.git/hooks/post-commit` qui déployait automatiquement chaque commit
vers le VPS a été **aboli** (renommé `post-commit.disabled`, réversible mais
non réactivé). Un commit sur `main` ne déploie plus jamais rien tout seul.

**Un merge GitHub ne redéploie ni ne redémarre le VPS par lui-même.**

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

---

# §5 — INSTRUCTIONS TEMPORAIRES PÉRIMÉES (audit uniquement)

> ⚠️ **Ne pas appliquer.** Conservé pour la traçabilité des sessions passées.

## AVIS TEMPORAIRE — STABILIZATION LAB (2026-09-02 → 2026-09-16) — **PÉRIMÉ**

Cette fenêtre déclarait la certification du burn-in EXP-001 suspendue depuis le
`2026-09-02T20:18:12Z`, marquait `certified=false` toute donnée produite pendant
la révision, et autorisait des déploiements/redémarrages contrôlés après PR
mergée jusqu'au 2026-09-16.

Statut au 2026-09-26 : **SUPERSEDED**. La fenêtre est close par sa propre date
de fin, et l'état courant est décrit par le §2 ci-dessus et par #148 :
PPL-02E runtime certifié, époque F00 `F00-EPOCH-01-20260920T084335Z` active puis
`F00_FINAL_SCIENTIFIC_EXPERIMENT_CERTIFIED`, chaîne FIN-00→FIN-02 complète,
infrastructure Research #238/#239/#248 certifiée.

Le verdict humain `READY_FOR_BURNIN` évoqué par cette fenêtre n'a **jamais été
émis**, et le burn-in reste ⛔ NOT AUTHORIZED (§2).

Contrats historiques associés :
`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md` et
`experiments/EXP-001-pause-2026-09-02.yaml` — actes append-only, conservés.

## Formulation « Phase II / gel fonctionnel étendu » — **SUPERSEDED**

La formulation « Phase actuelle : Validation Scientifique (gel fonctionnel
étendu) » et sa liste « Phase II = zéro nouvelles couches » restent
**matériellement vraies** quant aux interdits, mais leur cadre de phase est
remplacé par la progression de #148
(PHASE A → PHASE B → PHASE C FIN → PHASE D F-00 → PHASE D2 Research Lab).
Les interdits eux-mêmes sont repris au §1 (Scientific Debt Rule) et au §2
(non-autorisations courantes), qui font foi.

## Historique de contamination SEC-01 (bornes v1→v3) — **HISTORIQUE**

v2 marquait le restart censé activer le gate d'exécution réelle SEC-01
(correction de `consecutive_losses` qui confondait échecs d'exécution technique
et vraies pertes, contaminant 5 mécanismes de décision — voir ADR-0012) ; mais
le déploiement du 2026-07-08 était **silencieusement partiel** (bug `ssh` sans
`-n` dans `deploy_vps.sh`, tags d'audit `deploy-20260707-0806` →
`deploy-20260708-1831` créés sur de faux succès) : `execution_engine.py` n'a
jamais atteint le VPS et SEC-01 était inactif dans la fenêtre v2 (ordre réel
encore tenté le 2026-07-09 06:28 UTC). v3 = borne postérieure au restart de
rattrapage qui charge réellement SEC-01 — voir **addendum ADR-0012**. v1 reste
documentée pour l'audit qualité de données (`scripts/data_quality.py`, tokens
toxiques/bypass `meta_allowed` — un problème différent).
