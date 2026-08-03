# SCIENTIFIC_DEBT.md — Registre de dette, classé et priorisé

> **Statut.** Rédigé à partir des mesures de `artifacts/cartography.json` et de
> `CONTRADICTIONS.md`. Chaque entrée cite sa preuve. Les estimations de temps
> sont des **estimations** et sont étiquetées comme telles — elles ne sont pas
> mesurées.
>
> **Aucune de ces dettes n'est remboursée dans cette phase.** J1-J2 mesure.

Mesure de référence : commit `348e83d`, 2026-08-01.

---

## Échelle

**Impact** — conséquence si la dette n'est pas remboursée.
**Risque** — probabilité × gravité d'un incident causé par cette dette.
**Priorité** — P0 (bloque toute suite) → P3 (à traiter quand le reste est fait).

---

## Catégorie : RUNTIME

### DEBT-RT-01 — Le fichier réellement exécuté sur le VPS n'est pas établi
- **Preuve** : CONTRADICTION-01. `crypto_advisor.service:15` lance `advisor_loop.py`, absent du dépôt.
- **Impact** : le dépôt ne décrit pas comment le système démarre. Toute cartographie, y compris celle-ci, repose sur une hypothèse de point d'entrée (`core.advisor_loop`) issue de `deploy_vps.sh`, non d'une observation du VPS.
- **Risque** : **Maximal.** Si le point d'entrée réel diffère, l'intégralité des classements ACTIVE/ORPHAN de ce lot est fausse.
- **Priorité** : **P0**
- **Temps estimé** : 15 min *(estimation)* — un `systemctl cat crypto-advisor` + `ps aux` sur le VPS.

### DEBT-RT-02 — Le graphe d'import n'est pas décidable statiquement
- **Preuve** : CONTRADICTION-02. `core/advisor_loop.py:33` importe par nom nu.
- **Impact** : la joignabilité runtime n'a pas de valeur unique — mesurée entre **102** (borne basse) et **170** (borne haute) sur 1115 modules.
- **Risque** : Élevé. Toute proposition de suppression fondée sur ces chiffres seuls peut retirer un module vivant.
- **Priorité** : **P0**
- **Temps estimé** : 2 h *(estimation)* — une trace `sys.settrace` d'un cycle complet donnerait la liste exacte des modules chargés et remplacerait les deux bornes par une mesure.

### DEBT-RT-03 — 3 cycles d'import
- **Preuve** : `RUNTIME_GRAPH.md §2` — `core.decision_packet ↔ core.lifecycle`, `lm_studio ↔ lm_studio.ai_router`, `tracker_system.main ↔ tracker_system.scheduler.auto_update`.
- **Impact** : ordre d'initialisation dépendant du point d'entrée ; le premier cycle touche le `DecisionPacket`, cœur du contrat de décision.
- **Risque** : Moyen.
- **Priorité** : P2
- **Temps estimé** : 3 h *(estimation)*

---

## Catégorie : GOVERNANCE

### DEBT-GV-01 — L'autorité d'exécution est distribuée sur 5 sites d'écriture
- **Preuve** : `AUTHORITY_CHAIN.md §1`. Calcul à `core/advisor_loop.py:1983`, révocations à `:5626`, `:5658`, `:5734`, `:5808`.
- **Impact** : aucune phrase ne peut décrire qui décide. L'attribution d'un refus est indécidable sans instrumentation.
- **Risque** : **Maximal.** C'est la dette dont toutes les autres dérivent.
- **Priorité** : **P0**
- **Temps estimé** : 1 j *(estimation)* pour la convergence en un site unique ; la mesure d'attribution préalable est plus rapide.

### DEBT-GV-02 — La pile `governance/` est morte à 10/11
- **Preuve** : CONTRADICTION-03.
- **Impact** : la gouvernance formalisée du projet ne s'exécute pas. Risque majeur de **fausse assurance** — croire protégé ce qui ne l'est pas.
- **Risque** : **Maximal.**
- **Priorité** : **P0** (décision : brancher ou déclarer mort — pas de troisième option)
- **Temps estimé** : 30 min pour la décision *(estimation)*, variable pour l'exécution.

### DEBT-GV-03 — Deux machines d'état actives, arbitrage inconnu
- **Preuve** : CONTRADICTION-08. `RuntimeStateMachine` et `SystemStateMachine`, toutes deux ACTIVE, toutes deux porteuses de `SAFE_MODE`.
- **Impact** : en cas de désaccord sur le mode dégradé, le comportement est **NON MESURÉ**.
- **Risque** : **Élevé** — touche l'arrêt d'urgence.
- **Priorité** : **P0**
- **Temps estimé** : 4 h *(estimation)*

### DEBT-GV-04 — 6 kill switches, 1 actif, identité trompeuse
- **Preuve** : CONTRADICTION-06.
- **Impact** : latence de diagnostic sur le mécanisme de sécurité le plus critique.
- **Risque** : Élevé.
- **Priorité** : P1
- **Temps estimé** : 2 h *(estimation)*

### DEBT-GV-05 — `FORCE_TEST_EXECUTION` désarme 8 couches depuis l'environnement
- **Preuve** : `core/advisor_loop.py:1943-1980`.
- **Impact** : une variable d'environnement annule la gouvernance, sans marquer les trades produits — donc sans distinction possible dans `paper_trades.jsonl`.
- **Risque** : Élevé — même vecteur de contamination du dataset que l'incident ayant coûté l'époque v2.
- **Priorité** : P1
- **Temps estimé** : 1 h *(estimation)*

---

## Catégorie : ARCHITECTURE

### DEBT-AR-01 — God object de 7 815 lignes
- **Preuve** : `core/advisor_loop.py`, mesuré. `main()` occupe ~4 000 lignes.
- **Impact** : la décision n'est ni testable isolément, ni rejouable, ni forkable pour expérience. Bloque DEBT-RS-01 et DEBT-RP-01.
- **Risque** : Élevé.
- **Priorité** : P1
- **Temps estimé** : 3-5 j *(estimation)* pour extraire une fonction `decide()` pure à comportement inchangé.

### DEBT-AR-02 — 69 noms de classe dupliqués, dont 8 paires simultanément ACTIVE
- **Preuve** : CONTRADICTION-07.
- **Impact** : deux `CapitalThrottle` actifs = deux notions d'étranglement du capital dans le même processus. Cohérence **NON MESURÉE**.
- **Risque** : Élevé.
- **Priorité** : P1
- **Temps estimé** : 2 j *(estimation)*

### DEBT-AR-03 — 248 modules ORPHAN, 153 totalement isolés
- **Preuve** : `artifacts/cartography.json`, `DEAD_MODULES.md`.
- **Impact** : 22 % du dépôt (hors tests) n'est atteint par rien. Coût de lecture, de recherche et d'onboarding ; surface d'erreur d'interprétation.
- **Risque** : Moyen (coût cognitif, pas opérationnel).
- **Priorité** : P2 — **et seulement après DEBT-RT-01/02**, car le classement dépend du point d'entrée.
- **Temps estimé** : 1 j *(estimation)* pour la proposition d'amputation.

### DEBT-AR-04 — Couche V2 déclarée mais jamais passée
- **Preuve** : 12 paramètres `v2_*` à `core/advisor_loop.py:1082-1096` ; aucun au site d'appel `:5511-5568`.
- **Impact** : ~400 lignes inatteignables dans la fonction de décision ; un commentaire (`:1962`) décrit un comportement contredit par le code (`:1996`).
- **Risque** : Moyen.
- **Priorité** : P2
- **Temps estimé** : 3 h *(estimation)*

---

## Catégorie : REPLAY

### DEBT-RP-01 — Aucun moteur de rejeu déterministe dans le runtime
- **Preuve** : CONTRADICTION-05. Deux `ReplayEngine`, tous deux TEST_ONLY.
- **Impact** : **aucune hypothèse n'est falsifiable hors production.** Le débit de recherche est plafonné au débit du marché (~2,4 trades propres/jour au dernier relevé).
- **Risque** : **Maximal** pour la trajectoire scientifique du projet.
- **Priorité** : **P0** (après DEBT-AR-01, dont il dépend techniquement)
- **Temps estimé** : 1 semaine *(estimation)*

---

## Catégorie : RESEARCH

### DEBT-RS-01 — Aucun moteur d'ablation
- **Preuve** : aucun module correspondant dans le graphe runtime. `governance/ai_constraints.py` (ORPHAN) est le plus proche et ne fait pas d'ablation.
- **Impact** : l'effet marginal de chacune des 12 couches sur le débit et la performance est **indécidable**. Sans lui, DEBT-GV-01 ne peut pas être remboursée sur preuve — seulement sur opinion.
- **Risque** : **Maximal.**
- **Priorité** : **P0** (dépend de DEBT-RP-01)
- **Temps estimé** : 3 j *(estimation)* une fois le replay disponible.

### DEBT-RS-02 — Un seul fichier d'expérience, aucun protocole exécutable
- **Preuve** : `experiments/` contient `EXP-001.yaml` et zéro module Python.
- **Impact** : les expériences ne sont pas exécutables, donc pas reproductibles, donc les résultats ne sont pas des preuves.
- **Risque** : Élevé.
- **Priorité** : P1
- **Temps estimé** : 2 j *(estimation)*

### DEBT-RS-03 — Sept répertoires de recherche déconnectés et gelés
- **Preuve** : CONTRADICTION-04.
- **Impact** : entretient l'illusion d'un socle de recherche existant, et a déjà induit en erreur une analyse externe.
- **Risque** : Moyen.
- **Priorité** : P2
- **Temps estimé** : inclus dans DEBT-AR-03.

---

## Catégorie : CALIBRATION

### DEBT-CA-01 — Aucun chemin de la preuve vers le paramètre
- **Preuve** : `config/feature_flags.py:47,50` — `FEATURE_AUTO_CALIBRATION=False`, `FEATURE_ADAPTIVE_CALIBRATION=False`. Unique consommateur : `quant_hedge_ai/agents/intelligence/regret_engine.py:339-341`, delta toujours nul.
- **Impact** : les cinq boucles d'apprentissage sont ouvertes au même endroit — le retour vers le code.
- **Risque** : Élevé pour la trajectoire, nul pour la sécurité.
- **Priorité** : P1 — **la décision d'ouvrir ce chemin appartient à l'opérateur, pas à l'ingénierie.**
- **Temps estimé** : NON ESTIMABLE — dépend d'une décision de gouvernance, pas d'un travail technique.

---

## Catégorie : EXECUTION

### DEBT-EX-01 — Cohérence des deux `CapitalThrottle` actifs non mesurée
- **Preuve** : CONTRADICTION-07.
- **Impact** : deux mécanismes d'étranglement du capital peuvent se composer de manière non intentionnelle.
- **Risque** : Élevé — touche le sizing.
- **Priorité** : P1
- **Temps estimé** : 3 h *(estimation)*

---

## Catégorie : SIMULATION

### DEBT-SI-01 — Fidélité du simulateur non mesurée
- **Preuve** : `paper_trading/mexc_simulator.py` (966 lignes) est **ACTIVE**. Aucune mesure d'écart entre fills simulés et fills réels n'a été trouvée dans le graphe runtime.
- **Impact** : les métriques de burn-in reposent sur un simulateur dont la fidélité est **NON MESURÉE**.
- **Risque** : Élevé — un edge mesuré sur un simulateur optimiste n'existe pas.
- **Priorité** : P1
- **Temps estimé** : 2 j *(estimation)*

---

## Catégorie : DOCUMENTATION

### DEBT-DO-01 — 66 fichiers markdown à la racine, sans marquage de péremption
- **Preuve** : CONTRADICTION-10.
- **Impact** : **mesuré empiriquement** — une analyse externe s'est appuyée sur ces documents et a conclu à l'existence d'un socle de recherche opérationnel, réfuté par CONTRADICTION-04.
- **Risque** : Élevé.
- **Priorité** : P1
- **Temps estimé** : 4 h *(estimation)* — déplacer vers `docs/_historique/` avec en-tête de péremption. Aucune suppression.

### DEBT-DO-02 — ADR-0018 cité comme norme, absent
- **Preuve** : CONTRADICTION-09.
- **Impact** : le verdict de `tools/score_calibration_audit.py` n'est pas opposable.
- **Risque** : Moyen.
- **Priorité** : P1
- **Temps estimé** : 1 h *(estimation)*

---

## Synthèse par priorité

| Priorité | Dettes | Thème commun |
|---|---|---|
| **P0** | RT-01, RT-02, GV-01, GV-02, GV-03, RP-01, RS-01 | **Établir qui décide et pouvoir le rejouer.** Rien d'autre n'est décidable avant. |
| **P1** | GV-04, GV-05, AR-01, AR-02, RS-02, CA-01, EX-01, SI-01, DO-01, DO-02 | Cohérence et sécurité |
| **P2** | RT-03, AR-03, AR-04, RS-03 | Réduction de surface |
| **P3** | — | — |

**Observation.** Les sept dettes P0 se réduisent à deux questions :

1. **Qui décide ?** (RT-01, RT-02, GV-01, GV-02, GV-03)
2. **Peut-on rejouer pour le prouver ?** (RP-01, RS-01)

Aucune ne demande d'écrire une fonctionnalité. Les cinq premières demandent de
**mesurer et de trancher** ; les deux dernières de **construire un instrument**.

---

## Ce qui reste NON MESURÉ à l'issue de J1-J2

| Question | Pourquoi non mesurée | Ce qu'il faudrait |
|---|---|---|
| Quel fichier tourne réellement sur le VPS | pas d'accès mesuré à la machine | `systemctl cat` + `ps aux` |
| Quels modules sont **exécutés** (vs atteignables) | analyse statique uniquement | trace `sys.settrace` / coverage d'un cycle |
| Fréquence de déclenchement de chaque révocation | aucun compteur en production | instrumentation passive de compteurs |
| Effet marginal de chaque couche | pas de moteur d'ablation | DEBT-RS-01 |
| Cohérence des 8 paires de classes ACTIVE dupliquées | exige l'exécution | trace + comparaison d'instances |
| Arbitrage entre les 2 machines d'état | exige l'exécution | trace sur transition SAFE_MODE |
| Fidélité du simulateur MEXC | aucune mesure d'écart trouvée | comparaison fills simulés/réels |
