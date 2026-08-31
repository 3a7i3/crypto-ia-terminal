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
