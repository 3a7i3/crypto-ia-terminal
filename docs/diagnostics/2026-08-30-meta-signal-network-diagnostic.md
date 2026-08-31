# Diagnostic Technique — 30/08/2026 — Meta / Signal / Network

**Date d'investigation :** 30–31 août 2026  
**Rédigé par :** Investigation Claude Code (mode analyse/read-only) + vérifications VPS par copier-coller  
**Statut global :** Archivé — certains dossiers clos, un point ouvert sous surveillance

---

## 1. Contexte

Ce document consigne les résultats d'une session d'investigation technique approfondie
portant sur l'architecture de décision du projet `crypto-ai-terminal`, notamment :

- la chaîne Signal Generator → Meta → Gate → décision finale ;
- le comportement de `gate.check()` vs `gate.check_packet()` ;
- la cohérence du détecteur de régime entre `LiveSignalEngine` et `advisor_loop.py` ;
- le rôle et l'état du module HMM V2 ;
- l'analyse des rejets de production du 30/08/2026.

Aucune modification de code ni de configuration n'a été effectuée dans le cadre de cette investigation.

---

## 2. Méthodologie

- Lecture statique du code source dans le repository (read-only).
- Vérifications des données de production (`databases/rejections/`, `databases/gate_rejections.csv`)
  exécutées directement sur le VPS par copier-coller de commandes de diagnostic.
- Les conclusions marquées **[VPS]** proviennent de l'investigation VPS et ne peuvent pas
  être vérifiées par lecture seule du repository.
- Aucun résultat n'a été inféré ou inventé ; chaque conclusion est ancrée dans des preuves
  explicites citées dans ce document.

---

## 3. Environnement VPS

| Paramètre | Valeur |
|---|---|
| Projet | `crypto-ai-terminal` |
| Utilisateur système (historique) | `mathieu` |
| Utilisateur actuel | `ia_strategy_support` |
| Hostname | `crypto-advisor-2` |
| Répertoire | `/home/mathieu/crypto_ai_terminal` |

**Services systemd du projet :**
`crypto-advisor`, `crypto-quant-observer`, `paper-arena`, `crypto-lmi-observatory`,
`crypto-radar-bot`, `crypto-dashboard`, `crypto-watchdog`, `crypto-market-observer`,
`radar`, `horizons`

**Note de migration :** Le VPS a migré vers une nouvelle VM. Le compte `ia_strategy_support`
est le compte VPS actuel. Un autre compte disposait des droits `git pull` nécessaires
au travail avec Claude.

**Règle de travail établie :** diagnostic causal avant toute modification de code ;
aucune action destructive sans confirmation explicite.

---

## 4. Travaux réalisés

1. Analyse causale de `advisor_loop.py` — flux `gate.check()` / `gate.check_packet()`.
2. Vérification de `GATE_MIN_SCORE_OVERRIDE` en production sur `crypto-advisor`.
3. Analyse de `databases/gate_rejections.csv` — recherche de preuve de double-écriture.
4. Analyse de `databases/rejections/rejections_2026-08-30.jsonl` — impact décisionnel.
5. Inspection de `meta_strategy_engine.py` — `validate_signal()`, `select()`, `_REGIME_MAP`.
6. Analyse des 1 548 blocages `first_blocker=meta` du 30/08.
7. Cas MAGMA/USDT : corrélation régime / personnalité / direction.
8. Identification du Signal Generator (`LiveSignalEngine`) et de sa logique de vote.
9. Vérification de l'implémentation active de `AdvancedRegimeDetector`.
10. Vérification du chemin HMM V2 dans `advisor_loop.py`.
11. Dossier crypto-narrator / `@Telemetrie_IA_bot`.
12. Identification des timestamps ANSEM (correction de contexte temporel).

---

## 5. Résultats confirmés (synthèse)

| Domaine | Résultat |
|---|---|
| Détecteur de régime | Instance unique active, partagée entre Signal Generator et advisor_loop |
| HMM V2 | Chemin structurel présent, inactif en production |
| Meta `_REGIME_MAP` | Table complète confirmée (6 personnalités) |
| Meta rejets directionnels | Cohérents avec `allowed_signals` — comportement intentionnel |
| `check()` / `check_packet()` | Divergence structurelle confirmée, 0 impact autonome le 30/08 |
| `GATE_MIN_SCORE_OVERRIDE` | Inactif en production [VPS] |
| crypto-narrator | Correspond à `@Telemetrie_IA_bot`, module supprimé/décommissionné |

---

## 6. Gate / check() / check_packet()

### 6.1 Anomalie structurelle

**Fichier concerné :** `advisor_loop.py`

**Observation :**  
`results["gate"]` est alimenté uniquement par le retour de `gate.check()`.  
`gate.check_packet()` est appelé séparément mais son retour n'est capturé dans aucune
variable contribuant à `results["gate"]`.

**Conséquence :**  
Le compteur `gate` dans `block_stats_lifetime.json` reflète `check()` et non `check_packet()`.  
Il s'agit d'une **anomalie structurelle dans la télémétrie / l'agrégation des verdicts**.

**Statut :** ANOMALIE STRUCTURELLE CONFIRMÉE — aucun correctif apporté lors de cette investigation.

### 6.2 Preuve réelle — gate_rejections.csv [VPS]

Une preuve de divergence check/check_packet a été trouvée dans `databases/gate_rejections.csv`.

**Exemple concret (MAGMA/USDT, timestamp ~1788048106.793) :**

| Champ | Écriture 1 (check) | Écriture 2 (check_packet) |
|---|---|---|
| Régime | `bull_trend` | `TREND_BULL` |
| Score | 72 (brut) | 68.0 (ajusté) |
| Verdict | `True` (passé) | `False` (rejeté) |

Cela démontre que `check()` et `check_packet()` peuvent produire **deux verdicts différents**
à partir du même cycle d'analyse.

**Format du CSV :** `ts,symbol,regime,score,effective_min,allowed,failed`

**Note :** Le CSV `gate_rejections.csv` est cumulatif (multi-jours). Ne pas le comparer
directement aux JSONL journaliers sans filtrer sur la date.

### 6.3 Deuxième exemple de double-écriture [VPS]

**Exemple concret (T/USDT) :**

| Écriture | Régime | Score | effective_min | Résultat |
|---|---|---|---|---|
| 1 | `bear_trend` | 70 | 72 | rejeté |
| 2 | `TREND_BEAR` | 66.0 | 72 | rejeté |

Même timestamp exact, même symbole, deux régimes et deux scores différents.

### 6.4 GATE_MIN_SCORE_OVERRIDE

`GATE_MIN_SCORE_OVERRIDE` a été vérifié comme **INACTIF** en production sur `crypto-advisor` [VPS].  
Cet override n'est pas la cause de l'anomalie check/check_packet.

---

## 7. Meta Strategy

### 7.1 Table _REGIME_MAP confirmée

**Fichier :** `meta_strategy_engine.py`  
**Fonction :** `validate_signal()` possède exactement **4 conditions de rejet**.  
**Fonction :** `select()` mappe le régime vers une personnalité via `_REGIME_MAP` avec
ajustements dynamiques.

| Personnalité | Régime | allowed_signals | minimum |
|---|---|---|---|
| `momentum_following` | `bull_trend` | `[BUY]` | 62 |
| `defensive_short` | `bear_trend` | `[SELL]` | 68 |
| `mean_reversion` | `sideways` | `[BUY, SELL]` | 60 |
| `scalping_mode` | `high_volatility_regime` | `[BUY, SELL]` | 65 |
| `capital_protection` | `flash_crash` | `[]` | 999 |
| `neutral` | `unknown` | `[BUY, SELL]` | 75 |

Correspondance régime → personnalité : **1:1 confirmée**.

### 7.2 Résultats du 30/08/2026 — 1 548 blocages Meta [VPS]

**Répartition par personnalité :**

| Personnalité | Blocages |
|---|---|
| `defensive_short` | 788 |
| `momentum_following` | 601 |
| `scalping_mode` | 126 |
| `capital_protection` | 33 |

**Causes :**
- ~68 % des rejets Meta sont **directionnels** :
  - SELL avec `momentum_following` en `bull_trend`
  - BUY avec `defensive_short` en `bear_trend`
- Les rejets restants sont principalement liés aux seuils de score des personnalités.

**Important :** Les rejets directionnels sont cohérents avec les `allowed_signals` configurés.
Ils ne constituent **pas des bugs** en l'absence de preuve supplémentaire contraire.

### 7.3 Cas MAGMA/USDT [VPS]

Données du 30/08/2026 pour MAGMA/USDT :
- 154 entrées en régime `bull_trend`
- 15 entrées en régime `high_volatility_regime`

**Régime bull_trend :**  
Les SELL sont rejetés par Meta car `momentum_following` n'autorise que `[BUY]`.  
Scores observés : ~72–73.  
**Conclusion :** le rejet n'est pas causé par un score faible mais par la règle directionnelle.

**Régime high_volatility_regime :**  
- Entrées 609–624 : principalement blocage Meta, scores 62–63.
- Entrée 625 : blocage Gate, score 67.

Aucune preuve du scénario illustratif "75 → 76 VOLATILE" dans les données réelles du 30/08.

---

## 8. Signal Generator

**Implémentation :** `LiveSignalEngine`

**Logique de direction :** vote multi-indicateurs — EMA cross, Bollinger, momentum, RSI.

**Points confirmés :**
- La direction BUY/SELL est produite par vote, sans filtrage selon le régime.
- Le régime est calculé séparément et contribue au score/ranking mais ne contraint pas
  directement `buy_votes` / `sell_votes`.
- `engine.evaluate()` est appelé **sans** l'argument `personality`.
- Un commentaire explicite du code documente que le Signal Engine génère des opportunités
  larges et laisse les couches de risque/Meta effectuer le filtrage.

**Architecture observée :**

```
Signal Generator
  → génération large (BUY/SELL sans filtre régime)
  → Meta / Risk filtering
  → décision finale
```

Cette séparation des responsabilités est considérée comme **INTENTIONNELLE**
sur la base du code inspecté.

---

## 9. Regime Detector

**Implémentation active :** `AdvancedRegimeDetector`  
**Fichier :** `quant_hedge_ai/agents/intelligence/regime_detector.py`

**Utilisé par :**
- `LiveSignalEngine`
- `advisor_loop.py`

**Occurrence archivée :** `_ARCHIVE_2026/_legacy/` — code historique/mort, ne pas confondre
avec l'implémentation active.

**Anomalie historique documentée :**  
Le code contient le commentaire :

```python
# was trend < 0.3 (inverted — bug)
```

Ce commentaire indique qu'une ancienne inversion de condition pour `bear_trend` a existé
puis a été corrigée. **Ce bug n'est plus actif.** Cette trace est conservée uniquement
à titre historique.

**Conclusion :** La question d'une divergence due à deux classifieurs différents est fermée.
Le même `AdvancedRegimeDetector` est utilisé partout.

---

## 10. HMM V2

**Chemin structurel :** `advisor_loop.py` via `v2_hmm_regime`

**État en production :** **INACTIF**

**Preuves :**
- Paramètre avec valeur par défaut `None`
- Aucune réassignation dans `advisor_loop.py`
- Aucun argument `v2_hmm_regime=...` lors de l'appel de production de `analyze_symbol()`
- Aucune instanciation active de `HMMRegimeEngine`
- L'implémentation trouvée est dans `_ARCHIVE_2026/`

**Conséquence :**  
`regime_probs` reste `None`.  
Le bloc suivant est structurellement prévu mais **inatteignable** dans le déploiement actuel :

```python
if regime_probs.confidence >= 0.50:
    regime = regime_probs.dominant
```

**Verdict : `NO_MISMATCH_CONFIRMED`**  
Aucune divergence Signal Generator / Meta causée par HMM n'a été démontrée.  
Si HMM V2 est activé ultérieurement, cette conclusion devra être réévaluée.

---

## 11. Données de production

### 11.1 Analyse du 30/08/2026 — rejections_2026-08-30.jsonl [VPS]

**Fichier :** `databases/rejections/rejections_2026-08-30.jsonl`  
**Volume :** ~12 919 lignes

**Répartition first_blocker :**

| Blocker | Occurrences |
|---|---|
| `gate` | 11 371 |
| `meta` | 1 548 |
| `decision_packet` | 0 |

**Test spécifique check_packet :**
- `decision_packet` comme **seul** blocker : **0**
- `decision_packet` comme **premier** blocker : **0**

**Mécanisme G8-D sync :**  
Lorsque `decision_packet(REJECTED)` apparaît dans `all_blockers`, il apparaît toujours
**après** un blocage déjà existant par `gate` ou `meta`. Ce comportement est cohérent
avec le mécanisme G8-D sync identifié.

### 11.2 Correction de contexte temporel — timestamps ANSEM [VPS]

Les timestamps `1788139109.773` et `1788139109.808` correspondent au **31/08/2026**
et non au 30/08.  
Le fichier `databases/rejections/rejections_2026-08-31.jsonl` existe bien sur le VPS.

**Impact :** les données ANSEM associées à ces timestamps ne font pas partie du dataset
du 30/08. À prendre en compte pour toute analyse comparative journalière.

---

## 12. Anomalies confirmées

### A1 — Divergence check() / check_packet() dans la télémétrie

| Champ | Valeur |
|---|---|
| **Statut** | ANOMALIE STRUCTURELLE CONFIRMÉE |
| **Fichier** | `advisor_loop.py` |
| **Nature** | `results["gate"]` reflète `check()` uniquement ; `check_packet()` est appelé mais son retour n'est pas agrégé |
| **Preuve** | Double-écriture observée dans `databases/gate_rejections.csv` avec verdicts divergents sur même cycle |
| **Correction** | Aucune apportée lors de cette investigation |
| **À faire** | Traitement ultérieur à planifier |

---

## 13. Anomalies sans impact démontré

### I1 — check_packet() sans impact décisionnel autonome le 30/08

| Champ | Valeur |
|---|---|
| **Anomalie parente** | A1 |
| **Test effectué** | Analyse complète de `rejections_2026-08-30.jsonl` |
| **Résultat** | 0 cas où `decision_packet` est `first_blocker` ou `unique_blocker` |
| **Conclusion** | L'anomalie structurelle est réelle mais n'a produit **aucun impact décisionnel autonome** le 30/08/2026 |

---

## 14. Comportements intentionnels

### B1 — Séparation Signal Generator / filtrage Meta-Risk

Le Signal Generator (`LiveSignalEngine`) génère des opportunités larges sans filtrage
directionnel par régime. Le filtrage est délégué aux couches Meta et Risk.  
Cette architecture est explicitement documentée dans le code source.  
**Statut :** COMPORTEMENT INTENTIONNEL CONFIRMÉ

### B2 — Rejets directionnels Meta

Les rejets de signaux SELL en `bull_trend` ou BUY en `bear_trend` sont le résultat
attendu des `allowed_signals` définis dans `_REGIME_MAP`.  
Ils ne constituent pas des bugs.  
**Statut :** COMPORTEMENT INTENTIONNEL CONFIRMÉ

---

## 15. Dossiers clos

| # | Dossier | Statut | Motif |
|---|---|---|---|
| 1 | Meta / Signal / HMM | **CLOS** | Architecture comprise, rejets Meta expliqués, même détecteur confirmé, HMM inactif, aucun mismatch réel démontré |
| 2 | GATE_MIN_SCORE_OVERRIDE | **CLOS** | Inactif en production [VPS] |
| 3 | Signal Generator → Meta direction filtering | **CLOS / INTENTIONNEL** | Séparation des responsabilités explicitement documentée dans le code |
| 4 | HMM regime mismatch | **CLOS — NO_MISMATCH_CONFIRMED** | HMM V2 non déployé/activé |
| 5 | Regime detector duplication | **CLOS** | Même classe `AdvancedRegimeDetector` active pour Signal Generator et advisor_loop |
| 6 | crypto-narrator / @Telemetrie_IA_bot | **CLOS / HISTORIQUE** | Correspondance confirmée, module supprimé, service décommissionné — ne pas réactiver |

---

## 16. Dossiers encore ouverts

| # | Dossier | Statut | Action suggérée |
|---|---|---|---|
| 1 | check() / check_packet() divergence | **ANOMALIE STRUCTURELLE — À TRAITER** | Décider si `check_packet()` doit contribuer à `results["gate"]` ; impact sur télémétrie et `block_stats_lifetime.json` |

**Note importante :** L'anomalie A1 est structurellement confirmée mais n'a pas démontré
d'impact décisionnel autonome sur les données du 30/08/2026. Elle reste néanmoins un
point technique ouvert nécessitant une décision architecturale explicite.

---

## 17. Commandes / outils utiles pour reprise future

### decision_trace.py

```bash
# Prérequis
export PYTHONPATH=/home/mathieu/crypto_ai_terminal

# Usage — le symbole s'écrit SANS "/USDT"
python tools/decision_trace.py --symbol ANSEM

# Incorrect
python tools/decision_trace.py --symbol ANSEM/USDT
```

### Analyse des rejections journalières

```bash
# Compter les first_blocker par type
grep -o '"first_blocker":"[^"]*"' databases/rejections/rejections_2026-08-30.jsonl \
  | sort | uniq -c | sort -rn

# Identifier les cas decision_packet seul ou premier
python -c "
import json
with open('databases/rejections/rejections_2026-08-30.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('first_blocker') == 'decision_packet':
            print(r)
"
```

### Analyse gate_rejections.csv

```bash
# Chercher un symbole (CSV cumulatif — ne pas comparer directement au JSONL journalier)
grep "ANSEM" databases/gate_rejections.csv | wc -l

# Double-écriture — chercher même timestamp
awk -F',' '{print $1}' databases/gate_rejections.csv | sort | uniq -d | head -20
```

### Conversion timestamp Unix

```bash
python -c "import datetime; print(datetime.datetime.utcfromtimestamp(1788048106.793))"
# Rappel : 1788139109 → 31/08/2026, pas 30/08/2026
```

---

## 18. Historique / traçabilité

| Date | Événement |
|---|---|
| ~2025 | Correction bug `bear_trend` dans `AdvancedRegimeDetector` (condition `trend < 0.3` inversée — commentaire `# was trend < 0.3 (inverted — bug)` dans le code) |
| 2026-07-17 | `CLEAN_DATA_SINCE_V4` — époque palier 1, univers élargi à 135 paires |
| 2026-08-30 | Session d'investigation technique (cette session) |
| 2026-08-31 | Rédaction et versionnement de cette documentation |

---

## Légende des statuts

| Étiquette | Signification |
|---|---|
| ANOMALIE DE CODE CONFIRMÉE | Bug ou incohérence structurelle vérifiée dans le code |
| IMPACT PRODUCTION CONFIRMÉ | Impact mesurable démontré sur données réelles |
| IMPACT PRODUCTION NON DÉMONTRÉ | Anomalie réelle mais sans impact démontré sur les données disponibles |
| COMPORTEMENT INTENTIONNEL | Comportement observé, explicitement voulu par l'architecture |
| POINT À SURVEILLER | Sujet à surveiller lors des prochaines analyses |
| DOSSIER CLOS | Investigation terminée, conclusion définitive |

---

*Document archivé dans `docs/diagnostics/`. Ne pas modifier le code applicatif sur la base de ce seul document sans analyse supplémentaire.*

---

## Addendum — 31/08/2026 — Clôture opérationnelle check() / check_packet()

**Date de l'investigation complémentaire :** 31 août 2026  
**Méthode :** Lecture seule du code source + jointure sur fichiers de production VPS (`databases/decision_packets_*.jsonl` × `databases/rejections/rejections_*.jsonl` via `packet_id`) — aucune modification de code, aucun service redémarré.  
**Statut du dossier avant cet addendum :** ANOMALIE STRUCTURELLE CONFIRMÉE — À TRAITER  
**Statut après cet addendum :** voir tableau de verdict en fin de section.

---

### A.1 CODE PROUVÉ

#### A.1.1 Deux logiques de score différentes, comparées au même seuil

**`GlobalRiskGate.check()`**  
Fichier : `quant_hedge_ai/agents/risk/global_risk_gate.py`, méthode `check()`, condition ③ (`signal_score`)  
Compare : `signal_result.score` — le **score brut** du signal — au seuil `_effective_min_score(regime)`.

**`GlobalRiskGate.check_packet()`**  
Fichier : `quant_hedge_ai/agents/risk/global_risk_gate.py`, méthode `check_packet()`, condition ③ (`signal_score`)  
Compare : `packet.adjusted_confidence` (fallback `packet.confidence`) — un **score ajusté après reasoning** — au même seuil `_effective_min_score(regime)`.

**Point clé :** `_effective_min_score()` est identique pour les deux appels (même régime → même seuil).  
La divergence de verdicts provient uniquement de la **valeur comparée** (score brut vs score ajusté), pas du seuil.

#### A.1.2 Le retour de check_packet() est ignoré dans le pipeline principal

Dans `core/advisor_loop.py`, autour des lignes 1550–1560 :

- `gate.check_packet(...)` est appelé en mode **fire-and-forget** — son retour (`GateResult`) n'est capturé dans aucune variable.
- `results["gate"]` (ligne ~2298) provient **exclusivement** de `gate.check()`.
- Le compteur `block_stats_lifetime.json["gate"]` ne reflète donc **jamais** le verdict de `check_packet()`.

`check_packet()` écrit bien son verdict dans le packet lui-même (`DecisionPacket`) — l'information existe et est correctement propagée dans le packet, mais elle est **absente du chemin de décision legacy** (`results["gate"]`, `block_stats_lifetime`, flow blockers logués en `[FLOW] ... VERDICT`).

#### A.1.3 Synchronisation existante — mais unidirectionnelle (bloc G8-D)

Un bloc explicite **G8-D** existe dans `advisor_loop.py` (juste après le calcul de `trade_allowed`) :

```
Si le pipeline legacy refuse → le packet est forcé à refuser aussi.
```

Ce bloc synchronise dans **un seul sens**.  
Il n'existe **aucun mécanisme symétrique** pour le sens inverse :  
si `check_packet()` aurait refusé mais que le pipeline legacy (via `gate.check()` + les autres gardes) autorise, **rien ne bloque le trade** sur la base du verdict `check_packet()`.

C'est précisément ce sens inverse qui a été mesuré en production (voir section A.2).

---

### A.2 PRODUCTION PROUVÉE

Investigation sur `databases/rejections/rejections_*.jsonl` et `databases/decision_packets_*.jsonl`.  
Jointure exacte par `packet_id` — clé commune confirmée à **100% de correspondance** sur les échantillons testés.

#### A.2.1 Table de contingence — 30/08/2026 (n = 12 919 rejets, jointure 100%)

|  | `risk_failed=True` (check_packet aurait bloqué) | `risk_failed=False` |
|---|---|---|
| `gate_failed=True` (check() a bloqué) | 8 473 | 3 223 |
| `gate_failed=False` (check() a laissé passer) | **688** | 535 |

**La case critique :** `gate_failed=False, risk_failed=True` = **688 cas** où le verdict legacy (souverain sur l'exécution) a laissé passer un signal que `check_packet()` aurait explicitement rejeté.

#### A.2.2 Analyse des 688 cas divergents — 30/08/2026

- **100%** des 688 cas ont `first_blocker = "meta"` dans le RejectionStore.  
  Dans chaque cas, le trade était **déjà bloqué en amont par `MetaStrategyEngine.validate_signal()`**, indépendamment de la divergence `check()`/`check_packet()`.
- **100%** des conditions `risk_failed` sont de type `signal_score` (aucune autre condition : pas de `regime_blacklisted`, pas de `signal_confirmed`, pas de `drawdown_ok`).

**Exemples bruts :** `RIF/USDT` bear_trend score 63 < 66, `ANTFUN/USDT` bull_trend score 68 < 70, `MAGMA/USDT` bull_trend score 68 < 70.

#### A.2.3 Confirmation sur 8 jours consécutifs (24/08 → 31/08/2026)

| Date | Cas divergents (gate passe / check_packet aurait bloqué) | first_blocker |
|---|---|---|
| 2026-08-24 | 848 | 100% meta |
| 2026-08-25 | 841 | 100% meta |
| 2026-08-26 | 310 | 100% meta |
| 2026-08-27 | 675 | 100% meta |
| 2026-08-28 | 502 | 100% meta |
| 2026-08-29 | 692 | 100% meta |
| 2026-08-30 | 688 | 100% meta |
| 2026-08-31 | 63 | 100% meta |

**Résultat cumulé (~4 600 cas, 8/8 jours à 100%) :** aucune exception.  
Meta bloque systématiquement en amont, avant que la divergence `check()`/`check_packet()` ait une quelconque conséquence sur l'exécution réelle du trade.

#### A.2.4 Autres constats production (contexte, déjà établis avant cet addendum)

- `GATE_MIN_SCORE_OVERRIDE` : confirmé **inactif** en production sur `crypto-advisor`. [VPS]
- `HMM V2` (`v2_hmm_regime`) : confirmé **totalement inactif** — aucune variable d'environnement, aucun service systemd, aucune instanciation de `HMMRegimeEngine()` hors archive/tests, paramètre jamais réassigné avant l'appel à `analyze_symbol()`. Dossier **CLOSED**. [VPS + code]

---

### A.3 HYPOTHÈSE (non prouvée — à garder distincte des faits)

Le fait que Meta bloque systématiquement en premier sur cette fenêtre de 8 jours est une **observation empirique, pas une garantie structurelle**.

Les seuils Gate et Meta sont deux sources indépendantes non synchronisées (confirmé dans le diagnostic du 30/08).  
Rien dans le code ne garantit que Meta restera **toujours** plus strict que Gate sur `signal_score`.

**Risque latent identifié :**  
Si Meta est un jour rendu plus permissif (changement de seuil, changement de personnalité pour un régime donné), les ~600–800 cas/jour actuellement filtrés par Meta pourraient cesser de l'être.  
Ces cas deviendraient alors des **trades potentiellement exécutés sans que `check_packet()` ait eu voix au chapitre** — puisque son verdict n'est de toute façon jamais consulté par le pipeline de décision.

---

### A.4 Verdicts mis à jour

| Dossier | Statut | Base |
|---|---|---|
| check()/check_packet() — impact opérationnel actuel (30/08 et 8 jours) | **CLOS** | Production prouvée — 100% des cas divergents masqués par Meta, 8/8 jours |
| check()/check_packet() — dette architecturale (retour ignoré + 2 scores comparés) | **OUVERT → NEEDS_ARCHITECTURAL_DECISION** | Code prouvé |
| Risque dormant si Meta est assoupli sans garde-fou côté Gate | **POSSIBLE_ANOMALY (risque latent, non actif)** | Hypothèse fondée sur code + logs |
| HMM V2 (v2_hmm_regime) | **CLOS — NO_MISMATCH_CONFIRMED** | Code prouvé + absence totale en production |

---

### A.5 Décision à prendre — par Mathieu (non tranchée ici)

**Question ouverte :** Quelle trajectoire architecturale adopter pour la divergence `check()` / `check_packet()` ?

**Option A — Convergence des scores**  
Faire converger les deux valeurs comparées par `check()` et `check_packet()` vers une seule et même valeur de référence, de sorte que les deux méthodes appliquent le même test sur la même donnée.

**Option B — check_packet() comme source unique de vérité**  
Faire de `check_packet()` la seule source de vérité pour `results["gate"]` et `block_stats_lifetime`, en dépréciant `check()` (qui serait alors maintenu uniquement pour compatibilité legacy le temps de la transition).

**Option C — Statu quo + alerte de surveillance**  
Laisser l'architecture actuelle telle quelle et ajouter une alerte de monitoring activée si `risk_failed` devient `first_blocker` dominant — ce qui signalerait que Meta ne filtre plus en amont et que le risque latent devient actif.

**Aucune de ces trois options n'a été mise en œuvre.** Ce document documente uniquement la question.  
Source de référence pour la décision : ce brief (addendum 31/08/2026).

---

*Addendum rédigé le 31/08/2026 — investigation VPS read-only, aucune modification de code applicatif.*
