# CONTRADICTIONS.md — Divergences documentation ↔ runtime

> **Statut de ce document.** Contrairement aux cinq documents de cartographie,
> celui-ci est **rédigé** à partir des mesures, pas généré mécaniquement :
> apparier une affirmation documentaire à un fait runtime demande un jugement.
> En revanche, **chaque preuve runtime citée est mesurée** et rejouable via
> `tools/runtime_cartographer.py`.
>
> Règle appliquée : la documentation n'est jamais une preuve, seulement une
> hypothèse à vérifier. Le runtime tranche.

Mesure de référence : `artifacts/cartography.json`, commit `348e83d`, 2026-08-01.

---

## CONTRADICTION-01 — L'unité systemd lance un fichier qui n'existe pas

**Preuve documentaire**
`scripts/crypto_advisor.service:15`
```
ExecStart=/home/mathieuhasard111/crypto_ai_terminal/.venv/bin/python advisor_loop.py
```
Dernier commit du fichier : **2026-05-24**.

**Preuve runtime**
`find . -name "advisor_loop*.py"` → une seule occurrence : `core/advisor_loop.py`.
`ls advisor_loop.py` → *No such file or directory*.

**Explication**
`scripts/deploy_vps.sh:69-72` décrit deux cibles historiques : `core/advisor_loop.py`
(« moteur reel ») et `advisor_loop.py` racine (« bot passif »). Le second a
disparu du dépôt ; l'unité systemd n'a pas suivi. Le chemin utilisateur diffère
également des notes de déploiement (`mathieuhasard111` vs `mathieu`).

**Impact**
Le fichier de service versionné dans le dépôt **n'est pas** celui qui fait
tourner le VPS, ou alors le service échoue au démarrage. Dans les deux cas,
**le dépôt ne décrit pas comment le système est lancé**. C'est la rupture de
source de vérité la plus fondamentale : on ne sait pas, depuis le dépôt seul,
quel processus produit les données scientifiques.

**Statut de résolution** : NON MESURÉ côté VPS. Exige un `systemctl cat` sur la
machine. **À vérifier en priorité absolue.**

---

## CONTRADICTION-02 — Le dépôt contient des imports dépendants de `sys.path`

**Preuve documentaire**
`docs/adr/0002-src-ssot-domain-objects.md` et la structure en packages nommés
laissent supposer des imports pointés canoniques.

**Preuve runtime**
`core/advisor_loop.py:33`
```python
from advisor_runtime_adapters import AdvisorRuntime, load_advisor_runtime
```
Le module existe à `core/advisor_runtime_adapters.py`, donc sous le nom pointé
`core.advisor_runtime_adapters`. L'import par **nom nu** ne fonctionne que si
`core/` est dans `sys.path`.

**Explication**
Ce style d'import rend le graphe de dépendances non déterministe : la résolution
dépend du répertoire de lancement. C'est aussi ce qui a fait échouer la première
passe de mon propre instrument (102 modules atteignables mesurés, contre 170
après correction).

**Impact**
Trois conséquences mesurées :
1. **Le graphe d'import n'est pas décidable sans exécution.** Toute analyse
   statique du dépôt produit soit un sous-comptage, soit un sur-comptage.
2. Le point d'entrée n'est pas interchangeable : lancer depuis la racine ou
   depuis `core/` ne charge pas le même système.
3. Corrélé à CONTRADICTION-01 : l'ambiguïté sur le fichier lancé se double d'une
   ambiguïté sur le répertoire de lancement.

---

## CONTRADICTION-03 — La pile `governance/` ne gouverne rien

**Preuve documentaire**
`CLAUDE.md` érige ADR-0007 en règle constitutionnelle. `governance/` contient
une chaîne décisionnelle complète : `decision_router` → `confidence_gate` →
`risk_authorizer` → `execution_approval` → `trading_authority` → `authority_state`.

**Preuve runtime**
Sur 11 modules de `governance/`, **1 est ACTIVE et 10 sont ORPHAN**.
Le runtime n'importe qu'une seule chose de ce package :
`core/advisor_loop.py:4777` → `from governance.auditor import GovernanceAuditor`.

Statuts mesurés :

| Module | Statut |
|---|---|
| `governance.auditor` | **ACTIVE** |
| `governance.authority_state` | ORPHAN |
| `governance.trading_authority` | ORPHAN |
| `governance.confidence_gate` | ORPHAN |
| `governance.decision_router` | ORPHAN |
| `governance.risk_authorizer` | ORPHAN |
| `governance.execution_approval` | ORPHAN |
| `governance.status_dashboard` | ORPHAN |
| `governance.decision_trace` | ORPHAN |
| `governance.ai_constraints` | ORPHAN |

**Explication**
Il existe **deux piles d'autorité**. Celle qui porte le nom, les contrats et
l'apparence constitutionnelle est déconnectée. Celle qui gouverne réellement est
la conjonction de 12 booléens à `core/advisor_loop.py:1983`.

**Impact**
Critique. Un auditeur lisant `governance/` conclurait que le système possède un
routeur de décision, un gate de confiance et une autorité d'exécution formalisés.
Aucun des trois n'est atteint par le runtime. **La gouvernance du projet est
documentée dans du code mort.**

---

## CONTRADICTION-04 — Le « socle Research OS » est vide ou déconnecté

**Preuve documentaire**
L'arborescence du dépôt expose `research/`, `experiments/`, `walk_forward/`,
`meta_learning/`, `execution_simulator/`, `ai_autonomous_loop/`, `project_os/`,
`audit/` — présentés comme une base de plateforme de recherche.

**Preuve runtime**

| Répertoire | Modules .py | ACTIVE | Dernier commit |
|---|---:|---:|---|
| `research/` | **0** (un seul `.md`) | 0 | 2026-07-21 |
| `experiments/` | **0** (un seul `.yaml`) | 0 | 2026-06-30 |
| `walk_forward/` | 5 | **0** | 2026-05-14 |
| `meta_learning/` | 5 | **0** | 2026-05-25 |
| `ai_autonomous_loop/` | 1 | **0** | 2026-05-29 |
| `project_os/` | 9 | **0** | 2026-05-14 |
| `audit/` | 5 | **0** | 2026-06-12 |
| `execution_simulator/` | 9 | **7** | 2026-06-13 |

**Explication**
Sept répertoires sur huit sont totalement déconnectés du runtime, et six sont
gelés depuis mai 2026 — l'ère d'accrétion antérieure au gel scientifique de juin.
Seul `execution_simulator/` est réellement vivant.

**Impact**
Toute feuille de route fondée sur « unifier les composants de recherche
existants » repose sur une prémisse fausse. **Il n'y a rien à unifier** : il y a
des noms de dossiers. La bonne action est de classer puis proposer l'amputation,
pas d'harmoniser.

---

## CONTRADICTION-05 — Deux `ReplayEngine` existent, aucun n'est dans le runtime

**Preuve documentaire**
`ADR-0009`, `docs/blueprint_v2.md` et le PMI (niveau L5 « Digital Twin »)
présupposent une capacité de rejeu.

**Preuve runtime**
Deux classes `ReplayEngine` mesurées :
- `audit/replay_engine.py:131` — **TEST_ONLY**
- `market_data/replay_engine.py:70` — **TEST_ONLY**

Aucune n'est atteignable depuis `core.advisor_loop`.

**Explication**
La capacité de rejeu a été écrite deux fois et n'a jamais été branchée.

**Impact**
Confirme le point le plus structurant du diagnostic : **il n'existe aucun moteur
de rejeu déterministe opérationnel**. Sans lui, aucune hypothèse n'est testable
hors production, et le débit de recherche reste plafonné au débit du marché.

---

## CONTRADICTION-06 — L'identité des kill switches est incohérente

**Preuve documentaire**
`core/advisor_loop.py:3255` instancie `runtime.TelegramKillSwitch(...)`.

**Preuve runtime**
`core/advisor_runtime_adapters.py:109`
```python
from supervision.killswitch_hardened import KillSwitchHardened as TelegramKillSwitch
```

Six classes de kill switch mesurées :

| Classe | Fichier | Statut |
|---|---|---|
| `TelegramKillSwitch` | `supervision/kill_switch.py:42` | **ORPHAN** |
| `TelegramKillSwitch` | `supervision/telegram_kill_switch.py:52` | **ORPHAN** |
| `KillSwitchHardened` | `supervision/killswitch_hardened.py:87` | **ACTIVE** |
| `KillSwitch` | `src/risk/kill_switch.py:1` | TEST_ONLY |
| `AlphaKillSwitch` | `system/alpha_kill_switch.py:49` | TEST_ONLY |
| `KillSwitchState` | `supervision/telegram_kill_switch.py:39` | ORPHAN |

**Explication**
Deux classes portent le nom `TelegramKillSwitch` et **aucune des deux n'est
utilisée**. Celle réellement active s'appelle `KillSwitchHardened` et porte le
nom `TelegramKillSwitch` par aliasing dans la façade.

**Impact**
Lire le code du kill switch en cherchant `class TelegramKillSwitch` conduit
dans deux impasses avant d'atteindre l'implémentation réelle. En cas d'incident
sur l'arrêt d'urgence, cette indirection coûte du temps de diagnostic — sur le
mécanisme dont la latence de compréhension importe le plus.

---

## CONTRADICTION-07 — 69 noms de classe sont définis à plusieurs endroits

**Preuve runtime**
`docs/cartography/RUNTIME_GRAPH.md §6` — **69 noms de classe dupliqués** hors
tests. Cas les plus graves, où **plusieurs définitions sont simultanément
ACTIVE** :

| Classe | Définitions ACTIVE simultanées |
|---|---|
| `CapitalThrottle` | `capital_deployment/capital_throttle.py:59` **et** `quant_hedge_ai/agents/risk/capital_throttle.py:18` |
| `TradeRecord` | `capital_deployment/phase_kpi_tracker.py:67` **et** `quant_hedge_ai/agents/intelligence/performance_supervisor.py:40` |
| `Position` | `quant_hedge_ai/agents/execution/position_manager.py:60` **et** `.../portfolio_intelligence.py:38` |
| `PortfolioSnapshot` | `observability/system_snapshot.py:56` **et** `.../portfolio_brain.py:64` |
| `Alert` | `observability/alerting.py:51` **et** `supervision/alert_manager.py:15` |
| `SystemState` | `quant_hedge_ai/runtime/runtime_state_machine.py:35` **et** `system/state_manager.py:15` |
| `ValidationResult` | `exchange_constraints/models.py:100` **et** `paper_trading/dataset_validator.py:100` |
| `MarketSnapshot` | `execution_simulator/models.py:53` **et** `observability/system_snapshot.py:92` |

**Explication**
`GlobalRiskGate` est également défini deux fois — `quant_hedge_ai/agents/risk/`
(**ACTIVE**) et `risk/` (**ORPHAN**) — de même que deux `SystemState` actifs
dans deux machines d'état différentes.

**Impact**
C'est la forme mesurable de « plusieurs versions de vérité ». Deux
`CapitalThrottle` actifs signifient que deux notions distinctes d'étranglement du
capital coexistent dans le processus vivant. **NON MESURÉ** : si elles sont
cohérentes entre elles. Cette question exige une trace runtime.

---

## CONTRADICTION-08 — Deux machines d'état portant `SAFE_MODE` sont actives

**Preuve documentaire**
`SAFE_MODE_UNIFICATION_AUDIT.md` (2026-06-08) annonce un travail d'unification.

**Preuve runtime**
Trois machines d'état mesurées, **deux ACTIVE** :

| Classe | Fichier | Statut |
|---|---|---|
| `RuntimeStateMachine` | `quant_hedge_ai/runtime/runtime_state_machine.py:53` | **ACTIVE** |
| `SystemStateMachine` | `system/state_machine.py:69` | **ACTIVE** |
| `WarmupStateMachine` | `cold_start/warmup_state_machine.py:113` | TEST_ONLY |

`SAFE_MODE` est mentionné dans **18 fichiers de production**, dont **8
atteignables par le runtime**.

**Explication**
L'unification annoncée en juin n'a pas convergé : deux machines d'état portant
chacune une notion de mode dégradé coexistent dans le runtime.

**Impact**
**NON MESURÉ** : laquelle prévaut en cas de désaccord. C'est une question de
sécurité, pas de style — elle doit être tranchée avant toute reprise du trading
réel.

---

## CONTRADICTION-09 — ADR-0018 est cité comme norme mais n'existe pas

**Preuve documentaire**
`tools/score_calibration_audit.py:675` :
> « Candidats observés (regret_horizons v2, source canonique ADR-0018). »

**Preuve runtime**
`ls docs/adr/` → la séquence passe de `0017-epoque-v4-palier-univers-trade.md`
à `0019-observateur-comptes-reels.md`. **Aucun fichier ADR-0018.**

**Impact**
Un outil d'audit s'appuie sur une norme introuvable. Non-conformité bloquante
dans un cadre de gouvernance scientifique : le verdict produit par cet outil
n'est pas opposable tant que sa norme de référence n'est pas restaurée.

---

## CONTRADICTION-10 — La documentation racine décrit un système révolu

**Preuve documentaire — dates du dernier commit**

| Fichier | Dernier commit |
|---|---|
| `COMPLETE_SYSTEM_ARCHITECTURE.md` | 2026-05-05 |
| `README.md` | 2026-05-26 |
| `CURRENT_TASK.md` | 2026-05-26 |
| `ARCHITECTURE_NOTES.md` | 2026-05-26 |
| `ARBORESCENCE.md` | 2026-05-29 |
| `SAFE_MODE_UNIFICATION_AUDIT.md` | 2026-06-08 |

**Preuve runtime**
66 fichiers `.md` à la racine du dépôt. Le gel scientifique (ADR-0007,
Scientific Debt Rule) date de fin juin ; l'époque V4 du 17 juillet. Tous les
documents ci-dessus sont **antérieurs** et décrivent des états abandonnés
(roadmap P10 avec `RLPolicyEngine`, système « sur données synthétiques »).

**Explication**
Le dépôt conserve la totalité de son historique documentaire à la racine, sans
marquage de péremption. Un lecteur externe ne peut pas distinguer une norme
active d'un vestige.

**Impact**
Mesuré empiriquement : une analyse indépendante du dépôt conduite sur ces
documents a conclu que le projet possédait un socle Research OS opérationnel et
planifiait un moteur RL — deux affirmations réfutées par CONTRADICTION-04.
**La documentation racine ne trompe pas seulement les humains, elle a déjà
trompé un auditeur.**

---

## Récapitulatif

| # | Contradiction | Gravité | Vérifiable par |
|---|---|---|---|
| 01 | systemd lance un fichier inexistant | **Critique** | `systemctl cat` sur VPS — **à faire** |
| 02 | imports dépendants de `sys.path` | Élevée | mesuré |
| 03 | `governance/` déconnecté à 10/11 | **Critique** | mesuré |
| 04 | socle Research OS vide | Élevée | mesuré |
| 05 | 2 `ReplayEngine`, 0 dans le runtime | Élevée | mesuré |
| 06 | identité des kill switches | Élevée | mesuré |
| 07 | 69 classes dupliquées | Élevée | mesuré |
| 08 | 2 machines d'état actives | **Critique** | mesuré (arbitrage NON MESURÉ) |
| 09 | ADR-0018 absent | Moyenne | mesuré |
| 10 | doc racine périmée | Élevée | mesuré |
