# Diagnostic Chief Scientist — Crypto AI Terminal

**Date** : 2026-08-01
**Périmètre** : intégralité du dépôt, branche `feat/t3-store-event-ledger` (359 commits, 1 116 fichiers Python hors dépendances, ~234 000 lignes)
**Posture** : revue externe, aucune complaisance. Chaque affirmation est ancrée sur un fichier:ligne ou un artefact vérifiable. Les inférences sont étiquetées comme telles.

---

## 0. Verdict en une page

Le projet n'a pas un problème d'architecture insuffisante. Il a le problème inverse : **une architecture de contrôle hypertrophiée greffée sur une source d'alpha unique et non validée**.

Trois constats structurent tout le reste :

1. **La décision d'exécution est une conjonction de 12 booléens** (`core/advisor_loop.py:1983`). Chaque couche ajoutée en un an a multiplié la probabilité de refus, pas amélioré la qualité de sélection. Le système a été optimisé pour ne pas se tromper, jamais pour apprendre vite.
2. **L'intégralité de la couche « V2 intelligence » est du code mort** : 12 paramètres `v2_*` déclarés dans la signature d'`analyze_symbol` (`core/advisor_loop.py:1082-1096`), **aucun n'est passé au site d'appel** (`core/advisor_loop.py:5511-5568`). Microstructure, régime HMM, arbitrateur, timing, slippage, feature store, apprentissage : jamais exécutés en production.
3. **Le projet est en deadlock épistémique.** Le gate de calibration exige N≥500 trades propres ; le débit de trades est étranglé par la conjonction de 12 vétos ; et la règle constitutionnelle interdit de toucher aux seuils avant d'avoir atteint N≥500. **On ne peut pas produire les données qui autoriseraient à corriger ce qui empêche de produire les données.**

Ce n'est pas un échec d'ingénierie — l'ingénierie est de bonne facture (L1 = 100/100, tests nombreux, gouvernance formalisée, ADR disciplinés). C'est un **échec de conception expérimentale**, et il est réversible.

---

## 1. Reconstruction de l'historique

Sans accès aux intentions, je reconstitue trois régimes de développement à partir des commits, des ADR et de la sédimentation documentaire.

### Régime I — Accrétion (mars → fin mai 2026)

**Observation.** 66 fichiers markdown à la racine du dépôt (`README.md`, `README_CONSOLIDATED.md`, `README_FRANCAIS.txt`, `QUICKSTART.md`, `QUICK_START.md`, `DOCUMENTATION.md`, `DOCUMENTATION_FRANCAISE_COMPLETE.md`…), ~45 scripts `launch_*.bat`, des répertoires `_ARCHIVE_2026/`, `archives/`, `backups/`, `S2`, `S3`, plusieurs `.zip` de code source versionnés.

**Inférence.** Le développement a procédé par ajout continu de capacités, chacune documentée et lancée indépendamment, sans jamais retirer la précédente. Le dépôt porte encore la totalité de sa propre histoire à la racine. La mémoire projet confirme le pattern : `Renforcements #1-#8`, `Phases 4-7`, `Position Intelligence Layer`, `Meta-Strategy Engine`, `Decision Intelligence Layer`, `Cockpit Layer`, `Command Center`, `Optimization Stack` — huit vagues successives de couches, toutes conservées.

C'est la période où se constituent les 12 couches de décision. Chacune est individuellement défendable. Aucune n'a été évaluée contre l'alternative « ne pas l'ajouter ».

### Régime II — Prise de conscience et gel (juin 2026)

Le tournant est net et il est à porter au crédit du projet. Apparaissent :

- **ADR-0007** — passivité absolue des observateurs, hissée au rang constitutionnel dans `CLAUDE.md` ;
- la **Scientific Debt Rule** — interdiction d'ajouter une fonctionnalité qui crée plus de variables expérimentales qu'elle n'en élimine ;
- la **règle du statisticien** — seuils N≥500 / 150 W / 150 L / CRI≥90 avant toute calibration ;
- le **PMI-7 / SDOS** avec sa double lecture *Capability* (26 %) vs *Evidence* (**0 %**).

**Ce « Evidence Score = 0 » assumé publiquement est l'acte intellectuel le plus honnête du projet.** Il constate qu'après un an, aucune hypothèse n'est conclue.

**Mais le gel a été appliqué de façon asymétrique** : il a interdit d'ajouter, sans jamais autoriser à retrancher. Aucune couche n'a été supprimée, aucun véto n'a été désarmé. Le gel a figé la dette de conception au lieu de la liquider.

### Régime III — Instrumentation scientifique (juillet → août 2026)

Construction de l'appareil de mesure : `tools/cri_calculator.py`, `tools/score_calibration_audit.py`, `tools/experiment_quality_audit.py`, `tools/instrumentation_validator.py` (1 102 lignes), `tools/live_observer_validator.py` (1 396 lignes), `scripts/regret_audit.py`, `scripts/data_quality.py`, les bornes `CLEAN_DATA_SINCE` v1→v4, `research/execution_lab/`, l'observatoire des comptes réels.

Cette période produit les **premiers résultats réels du projet** : H3 rejetée (Cohen's d = −0,097), l'horizon d'information du score cartographié (ρ = 0,16 à 12-24 h, rien à ≤1 h), le plancher de friction INV-FRICTION-001 identifié à 0,194 %.

**Ce sont les seules connaissances dures produites en un an. Elles ont été produites par les outils de mesure, pas par les couches de décision.** C'est le signal le plus fort du diagnostic : le retour sur investissement de la mesure a été, en six semaines, supérieur à celui de douze mois de construction décisionnelle.

---

## 2. Erreurs de **conception**

> Une erreur de conception est un choix qui, correctement implémenté, produit quand même le mauvais résultat. Aucune n'est corrigeable par un patch.

### C-1 — La conjonction comme architecture de décision *(erreur racine)*

```python
# core/advisor_loop.py:1983
trade_allowed = (
    _authority_ok and meta_allowed and gate_result.allowed
    and _awareness_ok and _conviction_ok and _notrade_ok
    and _pb_ok and _cae_ok and _mm_ok and _eo_ok
    and _radar_ok and _arb_ok
)
```

Douze termes, tous en ET, tous avec droit de véto absolu, aucun pondéré.

**Trois conséquences, toutes fatales :**

*(a) Effondrement multiplicatif du débit.* Si chaque couche laisse passer 90 % des candidats de façon indépendante, il en survit 0,9¹² ≈ **28 %**. À 85 %, il en survit 14 %. Chaque couche ajoutée en un an a coûté du débit expérimental. La « famine de trading » documentée les 13-14/07 n'était pas un incident : c'est le régime nominal de cette architecture.

*(b) Non-identifiabilité causale.* Quand un ET de 12 termes vaut `False`, on observe *qu'au moins un* terme a bloqué. On ne peut pas savoir ce que les onze autres auraient dit sur les candidats qu'ils n'ont jamais vus survivre jusqu'à eux. **L'attribution du refus n'est pas estimable à partir des données observationnelles** — il faudrait des interventions randomisées (désarmer une couche au hasard) que l'architecture ne permet pas. Toute la machinerie de regret et de rejection store mesure donc un effet composite qu'elle ne peut pas décomposer.

*(c) Le refus est gratuit, l'acceptation est coûteuse.* Une couche qui bloque à tort produit un `MISSED_WIN` — un contrefactuel non observé, jamais imputé à personne. Une couche qui laisse passer à tort produit une perte visible et attribuable. L'incitation structurelle de chaque contributeur de couche est donc de bloquer. Sur douze couches et douze mois, cette asymétrie converge vers un système qui ne trade pas. **C'est exactement ce qui s'est produit.**

### C-2 — Asymétrie alpha / contrôle

Une source de signal : `engine.evaluate(symbol, mtf_candles, features, memory_sharpe)` (`core/advisor_loop.py:1459`), alimentée par des indicateurs techniques classiques (RSI, MACD, EMA, ATR, Bollinger, MTF).

Contre : douze couches de véto, une gouvernance à quatre niveaux, un PMI à sept niveaux, un SDOS à huit, dix-huit modules d'observabilité, vingt-deux outils d'audit.

**Aucune quantité de gouvernance ne crée d'alpha.** Le rapport d'investissement entre recherche de signal et contrôle du signal est, à la louche, de 1:50. Dans une équipe quant fonctionnelle il est de l'ordre de 5:1 — le contrôle du risque y est important mais mince, parce qu'il opère sur un edge dont l'existence a été démontrée en amont. Ici le contrôle opère sur un edge dont l'existence n'a jamais été établie.

### C-3 — La passivité constitutionnelle sans chemin de sortie

ADR-0007 est une bonne règle mal complétée. Interdire aux observateurs d'influencer la décision *en temps réel* est correct — c'est la protection standard contre l'overfitting en boucle fermée. Mais l'ADR ne définit **aucun mécanisme par lequel une observation devient un paramètre**, même lent, même versionné, même validé par un humain.

Résultat mesurable : `FEATURE_AUTO_CALIBRATION=false` par défaut (`config/feature_flags.py:47`), `FEATURE_ADAPTIVE_CALIBRATION=false` (`:50`), et l'unique consommateur de la calibration (`quant_hedge_ai/agents/intelligence/regret_engine.py:339-341`) retourne systématiquement un delta nul.

**Le système observe intensément et n'agit jamais sur ce qu'il observe.** Ce n'est pas de la prudence, c'est une boucle ouverte.

### C-4 — Le deadlock du gel *(conséquence composée de C-1 et C-3)*

```
Modifier un seuil          ⟸ exige N≥500 + CRI≥90
N≥500                      ⟸ exige un débit de trades suffisant
Débit de trades suffisant  ⟸ exige d'assouplir la conjonction de 12 vétos
Assouplir la conjonction   ⟸ EST une modification de seuil
```

Le cycle est fermé. À un débit observé de ~2,4 trades propres/jour (mesuré le 05/07) et N = 139 en époque V4, atteindre N = 500 demande environ **150 jours sans aucune remise à zéro d'époque** — alors que quatre remises à zéro se sont produites en six semaines (§ C-5).

**Ce deadlock est la raison principale pour laquelle un an de développement a produit un Evidence Score de 0.** Il doit être brisé par une décision explicite, pas contourné.

### C-5 — Le dataset n'a jamais été conçu comme stationnaire

Quatre bornes `CLEAN_DATA_SINCE` en six semaines : v1 (25/06), v2 (09/07 01:16), v3 (09/07 07:45), v4 (17/07 01:30). Motifs : tokens toxiques, bug `consecutive_losses`, déploiement silencieusement partiel, puis élargissement de l'univers de 28 à 135 paires.

Le raisonnement de l'ADR-0017 est juste (« changer d'univers = changer d'époque »). **Mais il traite comme une fatalité ce qui aurait dû être une décision de conception du jour 1.** En recherche quantitative, l'univers, la fenêtre et la définition du trade sont figés *avant* la collecte et versionnés comme un artefact immuable. Ici l'univers a été traité comme un paramètre opérationnel, et chaque ajustement opérationnel a détruit le capital statistique accumulé.

### C-6 — Un seul environnement pour trois fonctions incompatibles

Le VPS est simultanément la production, la source de vérité des données scientifiques, et le laboratoire. Corollaires observés dans l'historique du projet : l'incident de déploiement du 09/07 (trois tags d'audit mensongers, 55 fichiers sur 80 jamais déployés, SEC-01 inactif pendant toute la fenêtre v2) a **contaminé le dataset scientifique** et forcé deux changements d'époque.

Il n'existe pas de replay déterministe canonique : `tools/exit_replay.py` et `research/execution_lab/` sont des instruments partiels, pas un moteur de rejeu bit-à-bit du pipeline complet. **Sans replay, aucune hypothèse n'est falsifiable hors production**, donc toute question doit attendre du temps réel — ce qui plafonne le débit de recherche au débit du marché.

### C-7 — God object

`core/advisor_loop.py` : 7 815 lignes. `main()` en occupe ~4 000 avec plus de cinquante closures imbriquées (`_on_position_close`, `_get_regret_engine`, `_sc_run_cycle`, `_start_healer`…). Le pipeline de décision, l'orchestration, la télémétrie, les trois bots Telegram, la santé système, le kill switch et le tracker vivent dans une seule fonction.

Conséquences : le pipeline n'est pas instanciable en test sans démarrer le monde ; il n'est pas forkable pour une expérience contrefactuelle ; il n'est pas rejouable. **La testabilité unitaire élevée du projet (nombreux tests) porte sur la périphérie, pas sur le cœur décisionnel.**

---

## 3. Erreurs d'**implémentation**

> Corrigeables. Certaines en une heure. Leur intérêt est diagnostique : elles révèlent que le cœur de décision n'est pas relu.

### I-1 — La couche V2 entière est inatteignable *(critique)*

`analyze_symbol` déclare douze paramètres d'enrichissement (`core/advisor_loop.py:1082-1096`) :

`v2_data_unifier`, `v2_microstructure`, `v2_hmm_regime`, `v2_regime_predictor`, `v2_arbitrator`, `v2_feature_store`, `v2_learning`, `v2_degradation_monitor`, `v2_onchain`, `v2_flow_tracker`, `v2_slippage_predictor`, `v2_execution_optimizer`, `v2_timing_engine`.

L'unique site d'appel (`core/advisor_loop.py:5511-5568`) n'en passe **aucun**. Tous valent `None` à chaque cycle depuis toujours. Environ 400 lignes du corps d'`analyze_symbol` — arbitrage multi-agents pondéré, régime HMM, pression directionnelle de microstructure, prévision de transition — ne s'exécutent jamais.

Ce n'est pas un flag désactivé : c'est du code jamais atteint et jamais détecté comme tel en un an.

### I-2 — Le commentaire contredit le code

```python
# core/advisor_loop.py:1962
# V2 arbitration : si disponible, son verdict remplace la logique dispersée
```

Le code qui suit calcule `_arb_ok` puis **l'ajoute** au ET final (`:1996`). L'arbitrateur, s'il avait été branché, n'aurait rien remplacé : il aurait constitué un **douzième véto** par-dessus les onze existants — aggravant exactement le problème qu'il prétendait résoudre.

L'écart entre l'intention documentée et le comportement réel n'a jamais été détecté parce que le chemin n'est jamais exécuté (I-1). **Deux défauts qui se masquent mutuellement.**

### I-3 — `timing_signal` calculé puis jeté

`core/advisor_loop.py:1866-1881` : le moteur de timing est évalué, son verdict `execute_now` est écrit dans un `log.debug`, et la variable n'est **jamais relue** (vérifié : quatre occurrences au total, toutes dans le bloc de calcul). Travail pur perte.

### I-4 — `FORCE_TEST_EXECUTION` désarme la constitution depuis l'environnement

`core/advisor_loop.py:1943-1980` : si `FORCE_TEST_EXECUTION=true`, huit couches sont forcées à `True` (`_awareness_ok`, `_conviction_ok`, `_notrade_ok`, `_pb_ok`, `_cae_ok`, `_mm_ok`, `_eo_ok`, `_radar_ok`, plus `meta_allowed`), et la taille d'ordre est restaurée à `EXEC_MAX_ORDER_USD`.

Le code est correctement commenté (`_authority_ok` n'est pas bypassé) et l'intention est légitime. Mais **une variable d'environnement dans un processus de production suffit à annuler onze couches de gouvernance**, sans trace dans la chaîne d'audit ni marquage des trades produits. Un trade émis sous ce flag est indistinguable d'un trade nominal dans `paper_trades.jsonl`. C'est un vecteur de contamination du dataset scientifique de même nature que celui qui a coûté l'époque v2.

### I-5 — Rupture de traçabilité normative : ADR-0018 absent

`docs/adr/` contient 0017 puis 0019. **ADR-0018 n'existe pas dans le dépôt**, alors qu'il est cité comme source normative canonique du regret dans `tools/score_calibration_audit.py:675` (« regret_horizons v2, source canonique ADR-0018 ») et référencé en mémoire projet.

Un outil d'audit s'appuie sur une norme introuvable. Dans un cadre de gouvernance scientifique, c'est une non-conformité bloquante.

### I-6 — Dual-track jamais convergé

`core/advisor_loop.py:1471-1473` :
> « Dual track : le packet traverse les 4 couches… **Les variables legacy pilotent encore les décisions.** Ce bloc produit l'audit trail complet + prépare la migration future. »

Le `DecisionPacket` (ADR-0002, `core/decision_packet.py`, 861 lignes) a été conçu comme le remplaçant souverain des booléens dispersés. Il n'a jamais remplacé quoi que ce soit : il tourne en parallèle et sert d'observateur. `core/advisor_loop.py:5743-5808` va jusqu'à comparer les deux verdicts et à logger les désaccords (`_decision_packet_disagrees`) — puis force `trade_allowed = False` en cas de conflit, ajoutant un treizième véto plutôt qu'achevant la migration.

**Une migration à moitié faite coûte davantage que les deux états qu'elle relie.**

---

## 4. Pourquoi les performances n'ont pas suivi malgré la richesse architecturale

Trois faits déjà établis par les outils du projet, que la richesse architecturale n'adresse pas :

**(1) Le signal est mesuré au mauvais horizon.** AUDIT-EMP-002/003 : le score ne classe rien à ≤1 h ; il classe faiblement à 12-24 h (ρ = 0,16, AUC = 0,60) ; la détention réalisée est de 5,92 h. **Le système décide à un horizon où il n'a pas d'information, et détient à un horizon intermédiaire où l'information est déjà dégradée.** Aucune couche de véto ne peut corriger un désalignement d'horizon.

**(2) L'edge brut est sous le plancher de friction.** INV-FRICTION-001 : plancher de 0,194 % jamais franchi. Un edge inférieur au coût de transaction reste négatif quel que soit le filtrage appliqué en aval. Filtrer davantage réduit le nombre de trades perdants **et** le nombre de trades gagnants, sans déplacer le plancher.

**(3) L'échantillon n'a jamais atteint la puissance requise.** N = 139 (époque V4), PF = 0,617, WR = 34,9 %, t = −1,571 — **non significatif**. Pour détecter un edge de 2 % avec une puissance de 0,8, il faut un ordre de grandeur de plus. Le projet n'a donc jamais été en position de savoir si sa stratégie fonctionne.

**Synthèse.** La performance n'a pas déçu *malgré* l'architecture — elle a déçu *et* l'architecture a rendu ce fait indétectable pendant douze mois. L'abondance de mécanisme a produit une impression de sophistication qui a différé la question fondatrice : *existe-t-il un edge, à quel horizon, et dépasse-t-il la friction ?* Cette question a reçu ses premiers éléments de réponse en juillet 2026 — et la réponse provisoire est **non, pas à l'horizon exploité**.

C'est une bonne nouvelle mal habillée : le problème est localisé dans la couche la plus mince du système, donc la moins coûteuse à remplacer.

---

## 5. Inventaire des modules passifs

> Passif = ne modifie jamais `trade_allowed`, `order_size_usd`, ni un paramètre persistant. Écrire un JSONL n'est pas agir.

### 5.1 — Passifs par conception assumée (ADR-0007)

| Module | Emplacement | Statut |
|---|---|---|
| DecisionExplainer | `observability/decision_explainer.py` | passif |
| RejectionStore | `observability/rejection_store.py` | passif (ADR-0004) |
| RegretScheduler | `observability/regret_scheduler.py` | passif (ADR-0005) |
| DecisionEventBus | `observability/decision_event_bus.py` | passif (ADR-0006) |
| DecisionObservation | `observability/decision_observation.py` | passif |
| Telemetry / MetricsBus / MetricsCollector | `observability/` (×3) | passif |
| HealthScore / Heartbeat / LiveTopology | `observability/` (×3) | passif |
| SystemSnapshot (+ renderers, event_bus) | `observability/` (×3) | passif |
| RealAccounts | `observability/real_accounts.py` | passif (ADR-0019) |
| Alerting / JsonLogger | `observability/` (×2) | passif |
| BlackBox | `capital_deployment/` | passif |
| Les 22 outils de `tools/` | `tools/` | passifs par nature (lecture seule) |
| ExecutionLab | `research/execution_lab/` | passif par nature |
| SDOS Terminal, `visualization/` | — | passifs par nature |

**Ces modules ne sont pas le problème.** Ils sont passifs à dessein et ils ont produit les seules connaissances du projet.

### 5.2 — Passifs **non assumés** — conçus pour agir, n'agissant pas

Ce sont eux, le problème.

| Module | Preuve d'inertie |
|---|---|
| **Toute la couche V2** (12 modules : microstructure, HMM, regime predictor, arbitrator, feature store, learning, degradation monitor, onchain, flow tracker, slippage, execution optimizer, timing) | Jamais passés au site d'appel — `advisor_loop.py:5511-5568` |
| **DecisionArbitrator** | Non branché ; et s'il l'était, ajouterait un véto au lieu de remplacer (`:1962` vs `:1996`) |
| **TimingEngine** | Verdict calculé puis jeté (`:1866-1881`) |
| **RegretEngine** (voie calibration) | `FEATURE_AUTO_CALIBRATION=false` → delta toujours nul (`regret_engine.py:339-341`) |
| **AdaptiveCalibration** | `FEATURE_ADAPTIVE_CALIBRATION=false` (`feature_flags.py:50`) |
| **DecisionPacket** | Dual-track jamais convergé ; « legacy pilote encore » (`:1471-1473`) |
| **MistakeMemory** | Génère des règles de blocage (`mistake_memory.py:471,620-653`) — mais localement seuls des `.bak_20260608` / `.bak_20260617` subsistent, aucun `mistake_memory.jsonl` vivant. *(À revérifier sur le VPS : le local n'est pas autoritatif.)* Si la base est vide, `_mm_ok` passe toujours et la couche est inerte. |
| **MetaLearner** | `learn()` écrit, `suggest()` est lu (`:4445`) — mais la suggestion n'entre pas dans `trade_allowed` |
| **ThreatRadar** | Actif, mais échantillonné (`cycle % threat_radar_every`) et coupé sous `shed_optional_work` : sa contribution au dataset est non stationnaire |

### 5.3 — Le décompte qui compte

Sur douze paramètres de véto dans `trade_allowed`, **un seul comporte un mécanisme d'apprentissage** (MistakeMemory) et il est probablement inerte faute de base. Les onze autres sont des règles fixes écrites à la main, jamais recalibrées, jamais évaluées individuellement.

**Le système n'apprend, aujourd'hui, absolument rien.**

---

## 6. Points où la connaissance collectée n'est jamais réinjectée

Six ruptures identifiées, du plus grave au moins grave.

**R-1 — Regret → seuils.** `regret_analysis.jsonl` et `regret/regret_horizons_*.jsonl` accumulent MISSED_WIN et GOOD_REFUSAL. Consommateurs : `cri_calculator`, `regret_audit`, `score_calibration_audit`, `throughput_probe` — **tous en lecture seule**. Le seul chemin d'écriture (`regret_engine.py:341`) est verrouillé par un flag à `false`. *Rupture totale.*

**R-2 — Rejets → conception des couches.** Le `RejectionStore` sait quelle couche bloque le plus. Cette information ne remonte à aucune décision de suppression, d'assouplissement ou de réordonnancement de couche. On mesure le goulot sans jamais l'élargir.

**R-3 — Post-mortem de trade → sizing et sélection.** `TradePostMortem` et `DecisionQualityEngine` produisent un scoring de qualité de décision qui n'alimente ni le sizing (`capital_engine`) ni la sélection (`ranker`).

**R-4 — Horizon d'information → horizon de détention.** Le résultat le plus actionnable du projet (le score classe à 12-24 h, la détention est à 5,92 h) **n'a modifié aucun paramètre de sortie**. C'est une connaissance dure, mesurée, publiée en interne, et sans effet.

**R-5 — H3 rejetée → moteur.** Première conclusion scientifique du projet (31/07, Cohen's d = −0,097). Aucun changement de code n'en découle. Une hypothèse rejetée devrait retirer du mécanisme ; ici elle n'a rien retiré.

**R-6 — Observatoire des comptes réels → réconciliation.** ADR-0019 collecte les soldes réels multi-exchange. Ces observations ne réconcilient pas l'equity de sizing, épinglée à `WALLET_PAPER_CAPITAL` par décision constitutionnelle. Décision défendable — mais il n'existe pas de procédure de révision, donc l'épinglage est de fait permanent.

---

## 7. Cartographie des boucles d'apprentissage manquantes

Un système autonome a besoin de cinq boucles, à cinq constantes de temps. **Le projet en possède zéro fermée.**

| # | Boucle | Constante de temps | État actuel |
|---|---|---|---|
| **B1** | Exécution → coût réel → modèle de slippage → sizing | minutes | `v2_slippage_predictor` existe, jamais branché. **Ouverte.** |
| **B2** | Sortie → post-mortem → paramètres TP/SL/horizon | heures | `sl_factor_override`/`tp_factor_override` existent (`:5559-5568`) mais pilotés par `_sc_state`, pas par un apprentissage sur résultats. **Ouverte.** |
| **B3** | Regret → efficacité par couche → assouplir/retirer la couche | jours | Mesurée, jamais rebouclée. **Ouverte (R-1, R-2).** |
| **B4** | Hypothèse → expérience → verdict → changement de code | semaines | H3 rejetée sans conséquence. **Ouverte (R-5).** |
| **B5** | Méta : le système propose lui-même une hypothèse et un protocole | mois | Inexistante. `experiments/` contient **un seul** fichier, `EXP-001.yaml`. |

Le déficit le plus coûteux est **B4** : c'est la boucle qui transforme la mesure en amélioration. Sans elle, l'appareil scientifique (excellent) produit des rapports que personne n'a le droit d'appliquer.

**Observation structurelle.** Toutes les boucles sont *ouvertes au même endroit* : au point de retour vers le code. Ce n'est pas cinq problèmes, c'est **un seul mécanisme manquant** — un chemin gouverné, versionné et auditable de la preuve vers le paramètre. C'est l'objet central de l'architecture V2 proposée au § 9.

---

## 8. Ce qui empêche l'autonomie réelle

**A-1 — Aucun chemin légal de la preuve vers le paramètre.** ADR-0007 interdit ; rien n'autorise, même sous conditions. Un système ne peut pas devenir autonome si aucune de ses conclusions n'a de porte de sortie. *C'est le blocage n°1.*

**A-2 — Aucun replay déterministe.** Sans rejeu bit-à-bit, une proposition d'amélioration n'est pas testable avant déploiement. L'autonomie exige que le système puisse **se prouver à lui-même** qu'un changement est bon. Aujourd'hui, seul le temps réel arbitre — à ~2,4 trades/jour.

**A-3 — Le débit expérimental est inférieur au débit décisionnel requis.** Un système auto-améliorant doit boucler plus vite que le marché ne dérive. Ici c'est l'inverse d'un ordre de grandeur.

**A-4 — Le monolithe empêche l'isolation des variables.** Impossible de faire tourner deux variantes du pipeline en parallèle sur les mêmes données : la fonction `main()` n'est pas ré-entrante.

**A-5 — L'univers est une variable non contrôlée.** Tant que l'univers bouge (28 → 135 paires), toute comparaison inter-période est confondue. L'autonomie exige un socle stationnaire.

**A-6 — Aucune représentation formelle de la connaissance acquise.** Les conclusions vivent dans du markdown et de la mémoire de session. Un système ne peut pas raisonner sur des faits qu'il ne peut pas interroger. Il manque un registre d'hypothèses lisible par machine — `experiments/` en contient un seul.

---

## 9. Architecture V2 proposée

### Principe directeur

> **Le système ne change jamais son propre comportement. Il produit des *propositions de changement* accompagnées de preuves reproductibles. Un humain signe. Un pipeline versionné applique.**

Cela préserve intégralement ADR-0007 — la passivité en temps réel reste absolue — tout en ouvrant le chemin de sortie qui manque aujourd'hui.

### 9.1 — Le noyau : réduire avant d'ajouter

**Aucune fonctionnalité nouvelle n'est proposée ici.** Conformément à la Scientific Debt Rule, chaque élément ci-dessous **élimine** des variables expérimentales.

1. **Extraire le pipeline de décision hors du monolithe** vers une fonction pure :
   `decide(market_state, config, policy) -> Decision` — sans I/O, sans horloge, sans réseau. Condition nécessaire du replay, de l'expérimentation et du test.
2. **Remplacer la conjonction par une politique explicite.** Le ET de 12 termes devient un objet `Policy` versionné et sérialisé, où chaque couche déclare son type : `VETO_DUR` (sécurité, capital, autorité — non négociable), `SCORE` (contribution pondérée), ou `OBSERVATEUR` (aucun effet). **Attente de cible : 3 vétos durs maximum.** Les neuf autres deviennent des contributions scorées ou des observateurs — ce qui rend enfin leur effet marginal *mesurable individuellement*.
3. **Supprimer le code mort.** Les 12 paramètres `v2_*`, `timing_signal`, la branche `arbitration_result`. S'ils doivent revivre, ils reviendront par le processus expérimental, avec une hypothèse attachée.
4. **Achever le dual-track.** `DecisionPacket` devient l'unique porteur de la décision ; les booléens legacy disparaissent. Une seule vérité.
5. **Retirer `FORCE_TEST_EXECUTION` du chemin de production.** Il n'appartient qu'au harnais de test, qui marque ses trades d'un drapeau indélébile.

### 9.2 — Les agents spécialisés

Cinq agents, frontières strictes, **un seul avec autorité d'écriture sur le marché**.

| Agent | Rôle | Autorité |
|---|---|---|
| **Decider** | applique `Policy` à `MarketState` → `Decision` | **Seul** à décider. Pur, déterministe, rejouable |
| **Historian** | ingère, certifie, borne les données ; propriétaire unique des époques | Écrit le dataset. Ne décide jamais |
| **Analyst** | mesure : regret, calibration, efficacité par couche, horizons | Lecture seule |
| **Proposer** | formule des hypothèses et des protocoles à partir des mesures de l'Analyst | **Écrit uniquement dans `experiments/`.** Ne touche à aucun paramètre |
| **Referee** | exécute les protocoles en replay, rend un verdict signé + preuve | Écrit uniquement des verdicts. Ne peut pas appliquer |

**Invariant d'architecture — la séparation proposer/valider/appliquer.** Le Proposer ne peut pas valider sa propre proposition. Le Referee ne peut pas appliquer son propre verdict. L'application exige une signature humaine. Un agent ne peut jamais fermer seul la boucle sur lui-même — c'est la protection contre l'auto-optimisation dégénérée.

### 9.3 — Le moteur de replay *(pierre angulaire)*

Rejeu déterministe bit-à-bit à partir d'un `MarketState` archivé. Contrat : *même entrée + même Policy + même seed → même Decision, octet pour octet.* Vérifié par un test de non-régression sur un corpus figé.

**Ce que le replay débloque :** évaluer une proposition en minutes au lieu de mois ; mesurer l'effet marginal de chaque couche par ablation (désarmer une couche, rejouer, comparer) — **ce qui résout la non-identifiabilité causale de C-1** ; et rendre `experiments/` exécutable.

### 9.4 — Les expériences comme artefacts de première classe

`experiments/EXP-NNN.yaml` devient un objet exécutable et non un document : hypothèse, prédiction pré-enregistrée, corpus (hash), Policy A vs Policy B, métrique, N minimum, puissance visée, critère d'arrêt. Le Referee l'exécute et produit `verdicts/EXP-NNN.verdict.json` signé.

Le pré-enregistrement est ce qui empêche le p-hacking — indispensable dès lors qu'un agent génère les hypothèses.

### 9.5 — Le chemin gouverné du changement

```
Analyst mesure  →  Proposer formule EXP-NNN (pré-enregistrée)
                →  Referee rejoue et signe un verdict
                →  PR automatique : diff de Policy + verdict + preuve de replay
                →  ⟨ SIGNATURE HUMAINE — seul point d'écriture sur le vivant ⟩
                →  Application versionnée + nouvelle époque déclarée par l'Historian
```

Le CI refuse toute PR touchant une `Policy` sans verdict attaché, sans preuve de replay, ou sans N suffisant. **La gouvernance devient exécutable au lieu d'être déclarative.**

---

## 10. Feuille de route — 90 jours

Six sprints de 15 jours. Chaque sprint a un **critère de sortie binaire**. Un sprint non sorti n'autorise pas le suivant.

### Sprint 1 (J1-J15) — Réduction et vérité
**Objectif : que le code dise ce qu'il fait.**
- Supprimer les 12 paramètres `v2_*`, `timing_signal`, la branche arbitrateur mort *(I-1, I-2, I-3)*
- Retirer `FORCE_TEST_EXECUTION` du chemin de production *(I-4)*
- Rédiger ou révoquer ADR-0018 *(I-5)*
- Vérifier sur le VPS l'état réel de `mistake_memory.jsonl` — si vide, le déclarer inerte
- Instrumenter un compteur d'ablation : par cycle, pour chaque candidat actionnable, journaliser le verdict des **12** couches indépendamment, pas seulement du premier bloqueur

**Sortie :** aucun code inatteignable dans `analyze_symbol` ; le premier jeu de données d'attribution par couche existe.

### Sprint 2 (J16-J30) — Extraction du noyau
**Objectif : rendre la décision pure.**
- Extraire `decide(market_state, config, policy) -> Decision` hors de `main()`
- Sérialiser `MarketState` ; archiver un corpus de 30 jours
- Le monolithe appelle la fonction pure — comportement strictement inchangé, vérifié par égalité stricte sur le corpus

**Sortie :** la décision est testable sans démarrer le monde. **Aucun changement de comportement.**

### Sprint 3 (J31-J45) — Replay déterministe
**Objectif : la pierre angulaire.**
- Moteur de rejeu bit-à-bit + test de non-régression sur corpus figé
- Harnais d'ablation : rejouer avec chaque couche désarmée à tour de rôle

**Sortie :** *pour chacune des 12 couches, l'effet marginal sur PF, WR, N et regret est chiffré.* C'est le livrable le plus important des 90 jours — il rend enfin décidable la question « quelles couches méritent d'exister ».

### Sprint 4 (J46-J60) — Briser le deadlock *(décision d'opérateur)*
**Objectif : restaurer le débit expérimental.**

Le sprint 3 fournit la justification statistique qu'exige la règle du statisticien. Sur cette base, formaliser un **ADR-0020** : les couches dont l'ablation n'améliore aucune métrique et dont l'effet marginal sur le débit est significatif sont reclassées `SCORE` ou `OBSERVATEUR`. Trois vétos durs conservés au maximum.

⚠️ **Ce sprint exige une signature explicite de l'opérateur.** Il modifie des seuils avant N≥500 — c'est une dérogation consciente à la règle du statisticien, justifiée par le fait que la règle elle-même est ce qui empêche d'atteindre N≥500 *(C-4)*. La dérogation doit être bornée, datée et inscrite dans l'ADR.

**Sortie :** débit expérimental cible ≥ 15 trades propres/jour (×6). Nouvelle époque V5 déclarée, univers gelé pour 90 jours minimum *(C-5)*.

### Sprint 5 (J61-J75) — Aligner le signal sur son horizon
**Objectif : traiter la cause réelle de la sous-performance.**
- Rejouer les données existantes en alignant l'horizon de détention sur l'horizon d'information mesuré (12-24 h vs 5,92 h actuels) — *réinjection de R-4*
- Mesurer si l'edge aligné franchit le plancher de friction de 0,194 % — *test direct de INV-FRICTION-001*
- Formaliser en `EXP-002` pré-enregistrée, verdict par replay

**Sortie :** réponse chiffrée à la question fondatrice — *existe-t-il un edge au bon horizon, net de friction ?* Un « non » est un résultat pleinement valide et libère l'année suivante.

### Sprint 6 (J76-J90) — Fermer la boucle sous gouvernance
**Objectif : l'autonomie proposée, jamais l'autonomie appliquée.**
- Agents Proposer et Referee opérationnels
- `experiments/` exécutable ; format de verdict signé
- CI bloquant : aucune PR de `Policy` sans verdict + preuve de replay + N suffisant
- Démonstration bout-en-bout : le système produit **seul** une proposition d'amélioration, sa preuve, et une PR — qui attend une signature humaine

**Sortie :** une PR générée par le système, jamais fusionnée automatiquement.

### Ce que la roadmap ne fait pas
Aucune nouvelle couche décisionnelle, aucun nouvel indicateur, aucune nouvelle stratégie. Le solde net en variables expérimentales est **négatif** — conforme à la Scientific Debt Rule. La seule dérogation demandée est celle du sprint 4, explicite et signée.

---

## 11. Les trois décisions qui appartiennent à l'opérateur

1. **Accepter de démonter avant de construire.** Le sprint 4 supprime du mécanisme qui a coûté des mois. C'est la décision la plus difficile et la plus rentable.
2. **Accepter la dérogation bornée à la règle du statisticien.** Sans elle, le deadlock C-4 tient indéfiniment. La justification statistique viendra du sprint 3 — la règle est respectée dans son esprit (preuve avant changement), assouplie dans sa lettre (N requis).
3. **Accepter qu'un « pas d'edge » soit un succès.** Si le sprint 5 conclut que le signal ne franchit pas la friction à aucun horizon, c'est la conclusion la plus précieuse en douze mois. La plateforme de recherche, elle, reste valide et réutilisable pour la source d'alpha suivante.

---

## 12. Ce qui mérite d'être défendu

La revue est sévère sur la conception. Elle ne l'est pas sur l'exécution, et il serait malhonnête de terminer sans le dire.

La discipline ADR, le Evidence Score assumé à 0, les bornes d'époque documentées et opposables, la détection publique de ses propres incidents (déploiement du 09/07, `regime_audit.py` inerte, gate D câblée sur NO-GO), l'appareil de mesure construit en six semaines : **c'est un niveau d'honnêteté épistémique que beaucoup d'équipes professionnelles n'atteignent pas.**

Le projet a construit un excellent instrument de mesure autour d'un objet d'étude qu'il n'a pas encore validé. C'est l'ordre inverse de la bonne pratique — mais c'est un ordre récupérable, parce que l'instrument, lui, est bon. Les 90 jours ci-dessus consistent à retourner l'instrument vers la seule question qui compte.
