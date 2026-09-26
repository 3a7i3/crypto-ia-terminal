# AUDIT INDÉPENDANT D'ENRICHISSEMENT — 2026-09-24

> **Nature de ce document** : audit **passif** au sens d'ADR-0007. Il observe,
> mesure, reproduit et recommande. Il ne rend **aucun verdict de gouvernance**,
> ne certifie rien, n'autorise rien et n'a modifié **aucun code source
> existant**. Les seuls fichiers ajoutés sont ce rapport, ses preuves
> (`docs/audit/evidence/`) et un outil de mesure statique en lecture seule
> (`tools/research_boundary_auditor.py`, autorisé par la règle « outils de
> mesure et d'audit uniquement » de `CLAUDE.md`).

| Champ | Valeur |
|---|---|
| Base auditée | `main@98082ef01e8bef93f86fe5e4d1d2af48dddec53e` (merge PR #254, FIN-02) |
| Branche de livraison | `claude/upbeat-brown-f9fv3a` |
| Environnement | conteneur Linux éphémère, Python 3.11.15, `requirements-ci.txt` installé à neuf |
| Périmètre | source + issues GitHub + gates CI reproductibles hors-ligne |
| Hors périmètre | VPS, runtime déployé, PPL/PAPER/FIN réels, TESTNET/LIVE, navigateur |
| Données de production | **absentes localement** (`databases/` ne contient ni `paper_trades.jsonl` ni store PPL) — aucune métrique WR/PF/N réelle n'est calculée ici |

---

## 1. Ce qui a réellement été exécuté (preuves)

| # | Action | Résultat |
|---|---|---|
| P1 | Lecture des 13 issues ouvertes + `#148` (roadmap maîtresse, 182 commentaires) + issues fermées pertinentes (#174, #197) | carte d'état §2 |
| P2 | `scripts/ci/ruff_baseline_gate.py check` | **PASS** — 947 findings vs baseline 957, **0 nouvelle violation**, 10 corrigées |
| P3 | `pytest -q -m "not performance and not slow" tests/` (commande canonique de `ci.yml`) | **2 failed, 6319 passed, 19 skipped, 13 deselected, 2 xfailed** en 332 s |
| P4 | Ré-exécution isolée du fichier rouge | mêmes 2 échecs → **non lié à l'ordre des tests** (§3, A-01) |
| P5 | Audit statique AST des surfaces PAPER / FIN / replay (51 fichiers) | `docs/audit/evidence/2026-09-24_research_boundary_static_findings.json` |
| P6 | Reproduction empirique du défaut de classification UNKNOWN | §3, A-03 — script et sortie reproduits ci-dessous |
| P7 | `npm audit` + `npm audit --omit=dev` sur `frontend/` (issue #257) | `docs/audit/evidence/2026-09-24_frontend_npm_audit_triage.json` |
| P8 | Recherche de cycles d'import par sous-paquet | §3, A-07 |

Métriques de masse (informatif) : 1 354 fichiers Python versionnés,
≈ 302 000 lignes hors archives, 374 fichiers de tests, 364 fichiers `.md`.

---

## 2. Carte d'état de la roadmap au 2026-09-24

### 2.1 Chaîne certifiée (acquis)

```
PHASE A  OPS-C / OPS-A / OPS-D / SEC-API-01                        ✅
PHASE B  PPL-02B → 02C → 02D(SHADOW) → 02E(AUTORITÉ) + WEB-01/01B/02 ✅
PHASE C  FIN-00 → FIN-01 → PPL-RECOVERY-01 → FIN-02                ✅ (PR #254 mergée)
PHASE D  F00-PREFLIGHT ✅ → EPOCH-01 ACTIVE ✅ → F00_CERTIFIED      🟡 gate séparé
PHASE D2 RL-ARCH-00 🟡 → RL-DATA-01 ✅ SOURCE_CERTIFIED (#238 clos, PR #243 draft)
```

Époque canonique active : `F00-EPOCH-01-20260920T084335Z`, T0
`2026-09-20T20:39:57.056499Z`, capital scientifique initial `1000.0 USDT`,
PPL = 27 événements (1 EPOCH_CREATED + 13 OPEN + 13 CLOSE + 0 UNRESOLVED),
SHA-256 `50220fdf…f729b2`, réconciliation FIN-02 `WITHIN_TOLERANCE`,
capital reporté `1001.8635705815693`.

### 2.2 Mission active et chaîne restante

| Ordre | Issue | Mission | État observé |
|---|---|---|---|
| 1 | **#239** | RL-REPLAY-01 — replay offline déterministe + contrefactuel | 🟡 **EN COURS ce jour** : A1 audit surfaces PASS, A2 contrat SPECIFIED, A3 branche `rl-replay-01-offline-replay-engine` / PR **#259** draft (empilée sur #243) |
| 2 | #248 | RL-DIAG-01 — attribution de performance / incohérences | ⏳ |
| 3 | #240 | RL-CANDIDATE-01 — registre de candidats + frontière de promotion | ⏳ |
| 4 | #241 | WEB-RL-01 — séparation PAPER SCIENCE / RESEARCH LAB | ⏳ |
| 5 | #242 | RL-BURNIN-01 — capture/replay du burn-in sans rétroaction | ⏳ **pré-requis burn-in** |
| — | #237 | RL-ARCH-00 — architecture parente | 🟡 active |

Dette parallèle ouverte, non bloquante : #207 (cycles `src`), #208 (trace_id
cross-thread, différée pendant F00), #209 (orchestration évolutionnaire
obsolète), #202 (permissions des secrets au déploiement), #257 (npm audit),
#150 (FIN-ARCH parent).

Verrous explicites confirmés inchangés : burn-in ⛔, nouvelle époque PAPER ⛔,
Watchdog ⛔, TESTNET ⛔, LIVE ⛔, FIN-03 ⛔, merge de #243 vers `main` ⛔.

### 2.3 Corroboration indépendante de l'audit A1 de #239

L'audit statique P5 a été mené **sans** lire le classement A1 au préalable et
le confirme point par point :

| Surface | Classement #239 | Mesure indépendante |
|---|---|---|
| `paper_trading/ledger_events.py` | REUSABLE | **0 signal** |
| `paper_trading/paper_portfolio_ledger.py` | REUSABLE | 1 signal bénin (`.get("restored_count", 0)`, ligne 650 — compteur, pas une valeur financière) ; `realized_pnl` explicitement laissé UNKNOWN ligne 638 |
| `financial_institute/*` (10 fichiers) | ADAPTER_REQUIRED | **9/10 sans aucun signal** — noyau pur confirmé ; seul `recovery.py:28` importe `DurableEventStore` (attendu pour son rôle de rejeu : à isoler derrière un adaptateur côté Research) |
| `src/backtest/engine.py` | ADAPTER_REQUIRED | `time.time()` ligne 91 confirmé (horloge murale dans les métadonnées d'ordre) |
| `market_data/replay_engine.py` | ADAPTER_REQUIRED | `time.monotonic()` l. 203/234 + `json.dump` sans `allow_nan=False` l. 299 |
| `dip/modules/decision_replay.py` / `counterfactual.py` | FORBIDDEN | `DIPStore` importé, `now_us()` ×5, `uuid4()` ×2, `except: pass` l. 409 |
| `quant_hedge_ai/…/trade_replay.py` | FORBIDDEN | `except: pass` l. 320 confirmé |

**Conclusion** : le choix du noyau factuel (`project()` + `LedgerEvent`) est le
bon, et la couche FIN est mécaniquement la plus propre du dépôt. C'est un point
fort à conserver comme référence de style pour RL-REPLAY.

---

## 3. Anomalies constatées

Sévérité : **MAJEUR** = fausse une mesure scientifique ou la reproductibilité
d'un gate ; **MOYEN** = dette qui bloquera une mission proche ; **MINEUR** =
hygiène. Aucune n'a été corrigée : chacune propose un rattachement.

### A-01 — MAJEUR — Deux tests du gate TEST REGRESSION dépendent du réseau MEXC live

`tests/test_mexc_ws_recv_timeout.py::test_reconcile_does_not_restart_alive_task`
et `::test_reconcile_repeated_no_duplicate` échouent sur une machine neuve
sans accès sortant à MEXC :

```
tests/test_mexc_ws_recv_timeout.py:483: assert obs._tasks["BTCUSDT"] is task_btc
E   KeyError: 'BTCUSDT'
[Observatory] symbols unavailable: BTCUSDT=market_catalog_unavailable:URLError
ERROR market_data.mexc: URLError on https://contract.mexc.com/api/v1/contract/detail
```

Chaîne : `trade_analysis/observatory.py` valide les symboles contre le catalogue
Futures public, non stubé par ces deux tests (les 11 autres du fichier passent).
En isolation : mêmes 2 échecs → ce n'est **pas** un effet d'ordre.

**Confirmation croisée (2026-09-24 09:03 UTC)** : sur le commit
`f92200cade545b2353358c1f239e278d13a56bca` (ce même audit, contenu strictement
documentaire), le job GitHub Actions `TEST REGRESSION GATE` est **vert**, alors
que le même corpus sur le même arbre donne 2 échecs dans un conteneur sans
accès à MEXC. Le résultat du gate dépend donc bien de la joignabilité de
`contract.mexc.com`, et non du code testé.

**Impact** : le corpus canonique (`pytest -m "not performance and not slow"`)
mesure partiellement la disponibilité de `contract.mexc.com`. Un « TEST
REGRESSION: 6386 passed » n'est donc pas rejouable hors ligne, ce qui affaiblit
exactement la propriété que TI-00 (#201) et DS-001 ont établie ailleurs.

**Remédiation proposée** : fixture de catalogue injectée (même patron que les
autres tests du fichier) ; ou marqueur `integration` + désélection dans le gate
de correctness. Rattachement naturel : extension de #201 (isolation des tests)
ou nouvelle issue `TI-01 — hermeticity of the reconcile tests`.

### A-02 — MAJEUR — `dataset_validator` compte un PnL UNKNOWN comme une perte

`paper_trading/dataset_validator.py` (chemin de certification du corpus et de
`burnin_eligible`) :

```python
pnl = getattr(cl, "pnl_usd", 0.0) or 0.0    # ligne 521
...
if pnl > 0:   report.win_count += 1          # ligne 533
else:         report.loss_count += 1         # ligne 535
```

Or `TradeEvent.pnl_usd` est `Optional[float] = None` et `recorder.py:495-499`
documente explicitement la doctrine inverse (REM-C R1.1) :

> « pnl_usd=None (genuinely unknown, …) **must NOT be coerced into a LOSS** »
> — et le recorder la respecte : `is_win = None if cl.pnl_usd is None else …`

Reproduction exécutée (corpus synthétique : 1 gain +2.0, 1 perte −1.0,
1 CLOSE à `pnl_usd=null`) :

```
paired_trades : 3
win_count     : 1
loss_count    : 2        <-- l'UNKNOWN est devenu un loser
win_rate      : 0.333    <-- au lieu de 0.500
violations    : []       <-- silencieux
warnings      : []
```

**Impact** : contamine `win_rate`, `loss_count` et donc les seuils du
« statisticien » de `CLAUDE.md` (≥150 winners / ≥150 losers) et le drapeau
`burnin_eligible` — au moment précis où le projet s'apprête à instrumenter un
burn-in. Effet secondaire : un `pnl_usd = 0.0` réel (break-even évidencé) est
également classé perte.

Le module protège déjà d'autres cas (`expired_on_restore`,
`pnl_fee_evidence_incomplete` exclus) : le trou est spécifiquement `None`.

**Remédiation proposée** : un troisième compteur `unknown_pnl_count` exclu des
statistiques certifiées, aligné sur `is_win = None`, et une violation (ou au
moins un warning) quand la population en contient. Rattachement : #242
(pré-requis burn-in) ou extension REM-C R1.

### A-03 — MAJEUR (gouvernance) — l'univers tradé réel est 124 paires, la doctrine dit 135

- #174 (clos le 2026-09-16, `OPS_C_RUNTIME_RECERTIFIED`) prouve
  `UNIVERSE_PINNED_SYMBOLS = 124`, certifié `124/124/0 rejected`, après
  `135 → 125` (10 symboles non dérivables retirés) puis `125 → 124`
  (`RAVE/USDT`, `market_inactive`).
- `CLAUDE.md`, `ROADMAP.md` et `docs/adr/0017-epoque-v4-palier-univers-trade.md`
  décrivent toujours **135 paires épinglées**. Aucun fichier du dépôt ne
  mentionne 124 (`grep` : 0 occurrence).
- Or `CLAUDE.md` pose : « l'univers est une variable expérimentale, changer
  d'univers = changer d'époque ».
- Le §1 de #148 affiche encore « ⚠️ RUNTIME DRIFT À REMÉDIER » alors que #174
  est clos recertifié.

**Impact** : l'époque F00 active tourne sur un univers qui n'est documenté
nulle part comme tel ; toute comparaison inter-époques (V4 135 vs F00 124)
repose sur une hypothèse non écrite. C'est la seule anomalie qui touche
directement la validité d'une future conclusion d'hypothèse.

**Remédiation proposée** : addendum à ADR-0017 (ou ADR-0022) enregistrant
`135 → 125 → 124` avec les 11 symboles et leur preuve, mise à jour du §1 de
#148, et alignement de `CLAUDE.md`/`ROADMAP.md`. Aucun changement de code.

### A-04 — MOYEN — Trois vocabulaires de régime incompatibles (BUG-003 toujours ouvert)

| Source | Valeurs |
|---|---|
| `core/decision_packet.py::MarketRegime` | `TREND_BULL`, `TREND_BEAR`, `RANGE`, `VOLATILE`, `UNKNOWN` |
| `src/domain/trade_event.py::MarketRegime` | `unknown`, `trending`, `sideways`, `volatile` |
| `quant_hedge_ai/…/market_regime_classifier.py::_REGIME_CONFIGS` | 11 clés : `bull_trend`, `bear_trend`, `sideways`, `high_volatility_regime`, `flash_crash`, `unknown` **+** alias `TREND_BULL`, `TREND_BEAR`, `RANGE`, `VOLATILE`, `UNKNOWN` |

Les membres ne sont pas seulement en casse différente : ils ne se recouvrent
pas (`trending` ↔ `TREND_BULL`/`TREND_BEAR` est une projection à perte).

**Impact sur la roadmap** : #239 promet le « regime/context slicing » et #248
l'attribution par régime. Sans vocabulaire canonique, un slicing par régime
produit des populations non comparables — un faux résultat silencieux plutôt
qu'une erreur. À traiter **avant** #248, pas après.

### A-05 — MOYEN — Le pont de conviction n'est jamais appelé (BUG-005 toujours ouvert)

`core/contracts.py` définit `EngineConvictionScale` (MAJUSCULES) et le pont
`to_core_conviction()` / `from_core_conviction()` vers `ConvictionLevel`, avec
le commentaire « Utilisé uniquement dans conviction_engine.py ».
Or `quant_hedge_ai/agents/intelligence/conviction_engine.py` :

- n'importe **pas** `core.contracts` ;
- redéfinit sa propre classe **`ConvictionLevel`** (même nom que la canonique)
  avec des valeurs **minuscules** (`"minimal"`, `"low"`, … `"exceptional"`).

`grep` sur `to_core_conviction|from_core_conviction|EngineConvictionScale` :
aucun appelant hors de `core/contracts.py` et de son `__all__`. La
normalisation déclarée existe mais n'est jamais exécutée, et le nom canonique
est masqué à l'import.

**Impact** : toute comparaison ou agrégation par niveau de conviction
(diagnostics #248, candidats #240) doit aujourd'hui deviner la casse.

### A-06 — MOYEN — `json.dump` sans `allow_nan=False` dans la chaîne de preuve

Occurrences mesurées sur les surfaces PAPER/dataset/replay :
`paper_trading/admission_ledger.py:38`, `paper_trading/engine.py:269`,
`paper_trading/recorder.py:620`, `paper_trading/dataset_validator.py:636`,
`market_data/replay_engine.py:299`, `core/decision_packet.py:283`.

Python sérialise par défaut `NaN` / `Infinity`, qui ne sont **pas** du JSON
valide. Le contrat A2 de #239 exige justement « UTF-8 JSON, clés triées,
séparateurs `(",", ":")`, **no NaN/Infinity** » pour que `research_run_id` et
les digests SHA-256 soient reproductibles et relisibles par un tiers.

**Remédiation proposée** : `allow_nan=False` sur les écritures de preuve (et
`PF = +∞` représenté explicitement, comme le prévoit déjà A2). À poser comme
invariant de la nouvelle couche Research plutôt qu'en réécrivant l'existant
certifié.

### A-07 — MINEUR — Cycle d'import latent `core.decision_packet ↔ core.lifecycle`

`core/lifecycle.py:32` importe `core.decision_packet` au niveau module, et
`core/decision_packet.py:502-503` réimporte `core.lifecycle` **dans une
fonction** — le cycle est donc masqué à l'exécution mais bien présent.

`tests/test_architecture.py::test_src_no_circular_between_subdirectories`
(xfail, #207) ne couvre que `src/` : ce cycle-là n'est ni testé ni suivi.
Mesure fournie par `tools/research_boundary_auditor.py --cycles` :
`src` → 2 cycles connus (#207), `core` → 1 cycle **non suivi**,
`paper_trading` / `financial_institute` / `market_data` / `dip` /
`quant_hedge_ai` → 0.

**Remédiation proposée** : ajouter `core` au périmètre de #207 (documentation
seule ; la levée du xfail reste liée au refactor prévu).

### A-08 — MOYEN (gouvernance) — PR #204 orpheline, ouverte et non-draft

PR #204 « F00-DATA-01 — authoritative PPL epoch scientific dataset bridge » :
ouverte, **non-draft**, 14 commits, +690/−49 sur 6 fichiers, base périmée
`main@e8e3720` (antérieure à l'époque F00). Elle déclare `Closes #197` — or
#197 est **fermé/completed** par **PR #205, mergée**. #148 ne la mentionne
nulle part.

**Impact** : une PR mergeable en un clic, qui touche la sémantique de
population scientifique (`load_clean_trades`, baseline de capital, fallback
`WALLET_PAPER_CAPITAL`) et double partiellement RL-DATA-01. C'est le seul point
du dépôt où un geste accidentel pourrait muter la vérité expérimentale.

**Remédiation proposée** : fermer #204 avec un commentaire de provenance
(« superseded by #205 merged for #197 »), ou la repasser en draft si un reliquat
est encore utile. Aucune modification de code.

### A-09 — MOYEN (gouvernance) — `CLAUDE.md` et les documents racine ne décrivent plus le système

| Document | Ce qu'il affirme | État réel (#148, ce jour) |
|---|---|---|
| `CLAUDE.md` § AVIS TEMPORAIRE | fenêtre de stabilisation `2026-09-02 → 2026-09-16`, « le 16 septembre n'autorise aucune reprise automatique » | fenêtre **expirée depuis 8 jours**, aucun acte de clôture ; PPL est devenu autorité, FIN-02 certifié, Research Lab démarré |
| `CLAUDE.md` § borne canonique | `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30Z` = borne du N | l'autorité de population est désormais l'**époque F00** (T0 2026-09-20, N = 13 lifecycles), pas un timestamp de nettoyage |
| `CLAUDE.md` § sizing | base de sizing épinglée à `WALLET_PAPER_CAPITAL` | sous PPL_AUTHORITY le capital scientifique = capital initial d'époque + PnL réalisé (`1001.86`) — les deux règles doivent être explicitement réconciliées |
| `CURRENT_TASK.md` | « Focus actuel : P10 Evolutionary Architecture », branche `feat/stack-unification`, 1 627 tests | contredit le gel scientifique ; branche inexistante ; corpus ≈ 6 340 tests |
| `ROADMAP.md` | daté 2026-07-17 : scanner top-K, migration Hetzner, paliers 500/1000 paires | superseded par les phases A→F de #148 |
| `BUGS.md` | BUG-003/005/006/007 « open » | BUG-003 et BUG-005 confirmés ici (A-04/A-05) ; BUG-007 (venv Windows) n'a plus de sens dans l'environnement actuel |

**Impact** : `CLAUDE.md` est chargé automatiquement au début de chaque session
et présenté comme invariant. Tant qu'il décrit un état périmé, chaque nouvelle
session démarre avec une vérité fausse — risque de gouvernance supérieur à
n'importe laquelle des anomalies de code ci-dessus.

**Remédiation proposée** (documentaire, zéro code) : clôturer formellement la
fenêtre de stabilisation ; remplacer le bloc borne-de-données par un pointeur
vers l'époque canonique F00 ; réduire `CURRENT_TASK.md` à un pointeur vers
#148/#239 ; marquer `ROADMAP.md` comme archive datée.

### A-10 — INFO (favorable) + action simple — #257 : 0 vulnérabilité en production

Preuve exécutée dans `frontend/` :

```
npm audit              → 11 vulnérabilités (1 critical, 4 high, 4 moderate, 2 low)
npm audit --omit=dev   → found 0 vulnerabilities
```

Les 11 findings sont **exclusivement** dans la chaîne de build/dev :
`vitest` (critical, direct), `vite`, `postcss`, `nanoid`, `browserslist`
(high), `esbuild`, `@vitest/mocker`, `vite-node`, `baseline-browser-mapping`
(moderate), `@babel/core`, `postcss-selector-parser` (low). Les dépendances
d'exécution sont `react` + `react-dom` seules, sans avis.

**Conséquence pour #257** : le bundle PWA servi (certifié WEB-01B/FIN-02)
n'est pas exposé ; la dette porte sur le poste de build (notamment
« esbuild dev-server lit toute réponse » et les path-traversal `.map`).
Priorité **basse**, mais correctif simple et sans impact runtime : montée de
majeure `vitest`/`vite` derrière la CI frontend existante. Détail par paquet :
`docs/audit/evidence/2026-09-24_frontend_npm_audit_triage.json`.

### A-11 — MINEUR — Hygiène et concentration de risque

- `core/advisor_loop.py` : **8 925 lignes**, 92 `def`/`class`, **86 lectures
  d'environnement distinctes**. C'est le point de passage obligé de toute
  mission runtime : chaque certification future y revient. Aucun découpage
  n'est demandé pendant le gel, mais le risque mérite d'être nommé.
- `docs/_build/html/` : **118 fichiers générés versionnés** (dont des polices
  `.ttf`/`.woff`) — sortie Sphinx dans le VCS.
- **364 fichiers `.md`** dont 51 à la racine, plusieurs concurrents sur le même
  sujet (`README.md` / `README_CONSOLIDATED.md` / `README_FRANCAIS.txt`,
  `QUICKSTART.md` / `QUICK_START.md`, `ARBORESCENCE.md` /
  `ARBORESCENCE_COMPLETE.md`). C'est le terreau direct de A-09.
- `.github/workflows/test-panels.yml` : l'étape `python test_panels_with_report.py`
  cible un fichier **absent** du dépôt ; elle est neutralisée par une garde
  `hashFiles` (et verrouillée par `tests/test_ci_scope_contract.py`), donc
  inoffensive mais définitivement morte.
- `quant_hedge_ai/agents/intelligence/system_intel_reporter.py:46` : le
  commentaire dit `CLEAN_DATA_SINCE_V3` alors que le code importe la borne
  `_ACTIVE` (= V4). La règle « source unique » de `CLAUDE.md` est en revanche
  **respectée partout** : aucune copie locale de la constante n'existe.

---

## 4. Ce qui est sain — à ne pas « améliorer »

1. **Gate de lint** : baseline explicite, 0 nouvelle violation, 10 dettes
   spontanément résorbées. Mécanisme sain, à ne pas durcir maintenant.
2. **Couche FIN** : 9 fichiers sur 10 sans aucun signal (pas d'horloge, pas
   d'UUID, pas de couplage runtime, pas d'`except` silencieux) ; le dixième,
   `recovery.py`, ne dépend du store durable que pour sa fonction de rejeu.
   C'est le meilleur exemple de style du dépôt — à citer comme référence pour
   RL-REPLAY.
3. **Doctrine « UNKNOWN != 0 »** : réellement implémentée là où elle compte
   (`paper_portfolio_ledger` laisse `realized_pnl` intact sur
   `POSITION_UNRESOLVED`, `recorder` conserve `is_win = None`). A-02 est une
   fuite ponctuelle, pas un échec de doctrine.
4. **Discipline de provenance** : chaque mission porte un SHA exact, un verdict
   et une frontière SOURCE/RUNTIME. C'est rare et c'est l'actif principal du
   projet.
5. **Isolation des données scientifiques (TI-00, #201)** : après l'exécution
   complète du corpus (6 340 tests), `git status` est **vide** — aucun artefact
   de production n'a été touché par les tests. La baseline « zero leaking
   paths » tient empiriquement sur cette machine.
6. **Séparation clé publique / clé privée** (SEC-API-01) et passivité des
   observers (ADR-0007) : aucun import réseau/privé détecté dans les surfaces
   de recherche auditées.

---

## 5. Travaux restants — séquence proposée

L'ordre canonique `#239 → #248 → #240 → #241 → #242 → (décision burn-in)`
reste le bon. Les anomalies ci-dessus s'y **insèrent** sans le modifier :

**Pendant #239 (en cours, aucun blocage)**
- Poser dans le contrat RL-REPLAY : `allow_nan=False` + clés triées
  (répond à A-06 par construction, sans toucher au code certifié).
- Réutiliser le noyau confirmé propre (`LedgerEvent` + `project()`), et
  documenter `financial_institute/` comme référence de pureté.

**Avant d'ouvrir #248 (diagnostics par régime)**
- A-04 : figer un vocabulaire de régime canonique et une table de projection
  explicite (documentaire d'abord ; le code reste gelé). Sans cela, le slicing
  par régime de #248 n'est pas définissable.
- A-05 : décider si le pont de conviction est réactivé ou supprimé.

**Avant #242 / toute autorisation de burn-in**
- A-02 : `unknown_pnl` exclu des statistiques certifiées — c'est un pré-requis
  de la comptabilité WR/PF du burn-in, pas une amélioration.
- A-01 : rendre le corpus canonique hermétique, sinon la certification du
  burn-in dépendra de la disponibilité d'un service externe.
- A-03 : ADR d'univers (124) — sinon la population du burn-in n'a pas
  d'identité d'univers écrite.

**Quick wins hors chaîne (aucun risque runtime)**
- Fermer PR #204 (A-08).
- Resynchroniser `CLAUDE.md` / `CURRENT_TASK.md` / `ROADMAP.md` / `BUGS.md` (A-09).
- #257 requalifiée « dev-only, priorité basse » avec la preuve fournie (A-10).
- Étendre #207 au cycle `core` (A-07) ; nettoyer `docs/_build` et l'étape morte
  de `test-panels.yml` (A-11).

**Vue d'ensemble honnête** : côté *capability*, la machine est mûre
(PMI-7 26 %, chaîne PPL+FIN certifiée, cockpit prouvé au navigateur). Côté
*evidence*, la population certifiée est de **13 lifecycles** sur une époque
ouverte depuis 4 jours, face à des seuils de calibration à 500 trades / 150
gagnants / 150 perdants. Autrement dit : il ne manque presque plus
d'infrastructure, il manque du **temps d'observation propre** — ce qui rend
A-01, A-02 et A-03 prioritaires, puisqu'ils déterminent si ce temps produira
des chiffres exploitables ou des chiffres à refaire.

---

## 6. Outil livré

`tools/research_boundary_auditor.py` — audit statique AST, lecture seule,
zéro import du projet, aucune écriture dans le dépôt :

```bash
python tools/research_boundary_auditor.py paper_trading financial_institute
python tools/research_boundary_auditor.py --json --cycles --per-file src/backtest
```

Il détecte : `runtime_coupling` (store durable, authority runtime,
advisor_loop, simulateur, exécution, DIPStore, réseau, Telegram, subprocess),
`nondeterminism` (horloge murale, uuid, pid, hostname, random),
`evidence_erasure` (`... or 0`, `.get(..., 0)`), `silent_except`,
`nonfinite_json`, et les cycles d'import entre sous-paquets (complément à
`tests/test_architecture.py`, qui ne couvre que `src/`).

Il ne rend **aucun verdict** : il fournit des faits localisés
(`fichier:ligne`) qu'un humain classe REUSABLE / ADAPTER_REQUIRED / FORBIDDEN.
Utilisable tel quel comme preuve récurrente pour #239/#242.

---

## 7. Limites de cet audit

- Aucune preuve **runtime** : pas d'accès VPS, pas de systemd, pas de PPL/FIN
  réels, pas de navigateur. Tout ce qui est écrit ici est SOURCE + issues.
- Les métriques scientifiques (WR, PF, N, CRI) **n'ont pas été recalculées** :
  les données de production ne sont pas dans le dépôt.
- Les deux échecs de tests sont attribués à une dépendance réseau **prouvée par
  le message d'erreur** ; je n'exclus pas qu'un environnement avec MEXC
  joignable les rende verts (c'est précisément le défaut signalé).
- Le classement de sévérité est une proposition d'audit, pas un verdict de
  gouvernance : seul l'opérateur arbitre.
