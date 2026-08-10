# Observer Certification Standard v1.0

**Document type:** Normative reference  
**Status:** ACTIVE  
**Effective date:** 2026-07-01  
**Scope:** DIP (Decision Intelligence Platform) observation pipeline  
**Authority:** ADR-0007, Scientific Debt Rule, Data Governance Spec v1.0

---

## 1. Raison d'etre

Le moteur de trading produit des decisions. Le DIP les observe.

Avant de faire confiance aux donnees produites par le DIP pour calibrer le moteur
ou valider une hypothese scientifique (H1-H6), il faut certifier deux choses
separement :

**1. L'outil de mesure lui-meme est fiable.**  
(Le DIP capture exactement ce que le moteur produit.)

**2. Les donnees qu'il a collectees sont fiables.**  
(Les observations sont completes, coherentes, reproductibles.)

Ce standard definit les niveaux de certification, les criteres, les metriques
et les procedures de revocation.

---

## 2. Niveaux de certification

```
LEVEL 1: Certified Software
LEVEL 2: Certified Instrumentation
LEVEL 3: Certified Live Observer
LEVEL 4: Certified Dataset Producer
```

Chaque niveau est un prerequis du suivant. La certification ne peut
pas sauter un niveau.

---

### Level 1 — Certified Software

**Definition:** Le code du DIP fonctionne correctement sur des scenarios de test controles.

**Criteres:**
- IV-001 a IV-010 : 10/10 PASS
- Aucun test de regression echoue
- Aucune exception non geree dans les modules D01-D14

**Outils:**
```
python tools/instrumentation_validator.py
python -m pytest tests/dip/test_instrumentation_validation.py
```

**Score minimum:** 10/10 checks PASS (100%)

**Ce que ce niveau garantit:**
- Le code du DIP est correct sur des donnees synthetiques
- Les modules D01-D14 fonctionnent de maniere isolee
- Les structures de donnees sont integres

**Ce que ce niveau NE garantit PAS:**
- Que le DIP capture fidellement les evenements du moteur reel
- Que les donnees de production sont completes
- Que l'observateur ne manque aucun evenement

---

### Level 2 — Certified Instrumentation

**Definition:** Le DIP instrumente correctement le moteur en conditions controlees,
avec des donnees synthetiques representant des scenarios de production reels.

**Criteres:**
- Level 1 attaint
- IV-LIVE-001 a IV-LIVE-010 : 8/10 minimum PASS (hors SKIP)
- Instrumentation Integrity Index (III) >= 95/100
- Aucun check FAIL dans les categories Coverage, Replay, RootCause

**Outils:**
```
python tools/live_observer_validator.py
python -m pytest tests/dip/test_live_observer_validation.py
```

**Score minimum:** III >= 95/100

**Ce que ce niveau garantit:**
- Le pipeline complet (D01 -> D14) fonctionne de bout en bout
- Le replay est deterministe et structurellement fidele
- La causalite est acyclique et sans inversion
- La memoire est stable sur 1000 observations
- La coherence inter-modules est verifiee

**Ce que ce niveau NE garantit PAS:**
- Que le DIP capte 100% des evenements du moteur VPS reel
- Que les timestamps de production sont coherents
- Que les trades executes ont un parent dans le DIP

---

### Level 3 — Certified Live Observer

**Definition:** Le DIP observe fidellement le moteur de trading reel sur le VPS,
sans manquer d'evenement, sans incoherence, sans fuite.

**Criteres:**
- Level 2 attaint
- FEATURE_DIP=true actif sur VPS depuis >= 48h
- IV-LIVE-001 a IV-LIVE-010 : 10/10 PASS sur donnees de production
- Observer Confidence Score (OCS) >= 90/100
- Aucun ID duplique sur 100% de la periode observee
- Zero orphan detecte sur 100% de la periode
- Latence DIP < 50ms en P99

**Conditions necessaires:**
- Minimum 100 decisions enregistrees dans DIPStore (production)
- Minimum 24h de collecte continue sans interruption
- Zero alert CRITICAL active (D12)

**Ce que ce niveau garantit:**
- Toutes les decisions du moteur sont capturees
- Tous les rejets ont un parent valide
- La chaine causale est complete et reproducible
- Les donnees peuvent etre utilisees pour valider H1-H6

---

### Level 4 — Certified Dataset Producer

**Definition:** Le DIP a produit un dataset certifie, utilisable pour la validation
scientifique et la calibration du moteur.

**Criteres:**
- Level 3 attaint
- DatasetCertifier score >= 80/100 (DG-001 a DG-024)
- Calibration Readiness Index (CRI) >= 90/100
- N >= 500 trades (150 winners, 150 losers, 100 MISSED_WIN, 100 GOOD_REFUSAL)
- EXP-001 status: IN_PROGRESS ou CONCLUDED (pas PENDING)

**Ce que ce niveau garantit:**
- Le dataset repond aux exigences de la regle du statisticien
- Les hypotheses H1-H6 peuvent etre testees
- La calibration du moteur est autorisee (ACE)

---

## 3. Metriques

### 3.1 Instrumentation Integrity Index (III)

Score composite mesurant la qualite technique de l'instrumentation.

```
III [0, 100] = moyenne ponderee des scores de tous les checks IV + IV-LIVE

Poids:
  IV-001 a IV-010   : 4% chacun (total 40%)
  IV-LIVE-001 a 010 : 6% chacun (total 60%)

  Les checks SKIP sont exclus du denominateur.
  Un check FAIL contribue 0%.
  Un check PASS avec score partiel contribue score * poids.
```

**Sous-scores du III:**

| Dimension      | Checks                     | Description                            |
|---------------|----------------------------|----------------------------------------|
| Coverage      | IV-001, IV-LIVE-001        | Taux de capture des decisions          |
| Completeness  | IV-002, IV-LIVE-002        | Completude des rejets                  |
| Lifecycle     | IV-LIVE-003                | Chaine complete Decision->Outcome      |
| Integrity     | IV-LIVE-004, IV-LIVE-006   | Orphelins, unicite des IDs             |
| Timeline      | IV-005, IV-LIVE-005        | Monotonie des timestamps               |
| Memory        | IV-LIVE-007                | Stabilite memoire                      |
| Replay        | IV-006, IV-LIVE-008        | Fidelite et determinisme du replay     |
| Consistency   | IV-LIVE-009                | Coherence inter-modules                |
| RootCause     | IV-003, IV-009, IV-LIVE-010| Acyclicite et validite causale         |
| Graph         | IV-004                     | Completude structurelle du graphe      |
| Storage       | IV-010, IV-LIVE-006        | Ordre et unicite dans le store         |
| Heatmap       | IV-008                     | Couverture des couches dans la matrice |

### 3.2 Observer Confidence Score (OCS)

Score mesurant la confiance scientifique dans les donnees produites par le DIP.

```
OCS [0, 100] = somme ponderee de:

  III                        : 30%
  Live Validation Rate       : 25%  (checks IV-LIVE PASS / total non-SKIP)
  Replay Fidelity            : 20%  (avg score IV-006 + IV-LIVE-008)
  Dataset Certification      : 15%  (score DatasetCertifier / 100)
  Scientific Lineage         : 10%  (EXP-001 IN_PROGRESS ou CONCLUDED = 1.0)
```

**Seuil d'utilisation scientifique:** OCS >= 90/100

En dessous de ce seuil, les donnees ne peuvent pas etre utilisees pour :
- Valider H1-H6
- Calibrer des parametres du moteur
- Justifier un passage en trading reel

---

## 4. Checks IV-001 a IV-010 (Software Certification)

| ID     | Nom                          | Ce qui est verifie                                      |
|--------|------------------------------|--------------------------------------------------------|
| IV-001 | Packet Coverage              | N obs injectees = N dans DIPStore                      |
| IV-002 | Rejection Events             | Chaque rejet -> noeud BLOCKED + first_blocker non-null |
| IV-003 | Regret Parent Uniqueness     | Chaque rejet -> exactement 1 RootCause                 |
| IV-004 | Graph Completeness           | Nodes, edges, critical_path valides                    |
| IV-005 | Timeline Coherence           | Timestamps monotones, pas de doublons                  |
| IV-006 | Replay Fidelity              | Replay deterministe et fidele au verdict               |
| IV-007 | Counterfactual Reproducibility | Meme entree -> meme sortie contrefactuelle           |
| IV-008 | Heatmap Layer Coverage       | 12/12 couches dans la matrice                          |
| IV-009 | Causal Acyclicity            | CauseTree sans cycle ni doublon                        |
| IV-010 | Timestamp Monotonicity       | Ordre causal preserve dans le store                    |

---

## 5. Checks IV-LIVE-001 a IV-LIVE-010 (Instrumentation Certification)

| ID          | Nom                      | Ce qui est verifie                                   | Mode SKIP si...              |
|-------------|--------------------------|------------------------------------------------------|------------------------------|
| IV-LIVE-001 | Coverage Validation      | 100% des decisions indexees dans DIPStore            | DIPStore vide                |
| IV-LIVE-002 | Rejection Completeness   | 100% des rejets ont un root_cause_layer              | < MIN_DECISIONS              |
| IV-LIVE-003 | Lifecycle Completeness   | Chaine Decision->Trade complete sans rupture         | trade_log.sqlite vide        |
| IV-LIVE-004 | Parent Integrity         | Zero orphelin dans dip_observations + counterfactuals| < MIN_DECISIONS              |
| IV-LIVE-005 | Timestamp Integrity      | Monotonie stricte, zero duplication, zero inversion  | < MIN_DECISIONS              |
| IV-LIVE-006 | DecisionID Integrity     | Zero ID duplique sur toute la periode               | < MIN_DECISIONS              |
| IV-LIVE-007 | Memory Stability         | < 2 KB/observation sur 1000 injections              | Jamais (toujours actif)      |
| IV-LIVE-008 | Replay Fidelity (struct) | Replay identique bit-for-bit a la decision originale | < MIN_DECISIONS              |
| IV-LIVE-009 | Reporting Consistency    | Graph, CausalTree, Explainability coherents          | Jamais (toujours actif)      |
| IV-LIVE-010 | Root Cause Integrity     | CauseTree = reconstruction exacte du pipeline        | < MIN_DECISIONS              |

**MIN_DECISIONS = 50** pour les checks marques "< MIN_DECISIONS"

---

## 6. Procedures

### 6.1 Procedure de certification initiale

```
Etape 1: Executer les checks software
  python tools/instrumentation_validator.py
  Verifier: 10/10 PASS

Etape 2: Executer les checks d'instrumentation
  python tools/live_observer_validator.py
  Verifier: III >= 95

Etape 3: Activer le DIP en production
  FEATURE_DIP=true (VPS)

Etape 4: Collecter 100 decisions minimum (>= 48h)

Etape 5: Executer les checks live sur donnees de production
  python tools/live_observer_validator.py --live
  Verifier: 10/10 PASS, OCS >= 90

Etape 6: Enregistrer la certification
  python tools/live_observer_validator.py --export certification.json
```

### 6.2 Procedure de revocation

La certification Level 3 ou 4 est automatiquement retiree si:

- Un check IV-LIVE echoue sur donnees de production
- Un dataset perd sa certification (DatasetCertifier score < 70)
- Le replay devient non-deterministe
- Un orphan est detecte dans DIPStore
- Une fuite memoire depasse 5 KB/observation
- Une alert CRITICAL active (D12) reste non-acquittee > 24h
- La latence DIP depasse 50ms en P99 pendant > 1h

Lors d'une revocation:
1. Le DIP reste actif (passif = jamais de downtime)
2. Le dataset en cours est marque TAINTED (DatasetCertifier)
3. Un rapport de revocation est genere automatiquement
4. La re-certification necessite de reprendre a l'etape 3

### 6.3 Procedure de re-certification

Apres correction d'un defaut ayant entraine une revocation:

```
1. Identifier et corriger la cause racine
2. Executer les checks IV-LIVE complets
3. Verifier les checks specifiques qui avaient echoue
4. Generer un nouveau certificat avec mention "Re-certification"
5. Consigner dans l'historique de certification
```

---

## 7. Historique de certification

Chaque certification est enregistree de maniere immuable (append-only) dans:

```
databases/certifications/observer_cert_history.jsonl
```

Format d'une entree:

```json
{
  "certification_id": "OBS-CERT-2026-0001",
  "generated_at": "2026-07-01T12:00:00Z",
  "level": 1,
  "level_name": "Certified Software",
  "iii": 100.0,
  "ocs": null,
  "iv_passed": 10,
  "iv_total": 10,
  "iv_live_passed": 0,
  "iv_live_total": 0,
  "iv_live_skipped": 10,
  "n_decisions_production": 0,
  "revoked": false,
  "revocation_reason": null,
  "notes": "Level 1 initial certification"
}
```

---

## 8. Compatibilite

### 8.1 ADR-0007 (Passivite absolue)

Tous les checks IV et IV-LIVE sont strictement passifs. Aucun check ne:
- Modifie un signal, score, seuil ou decision
- Interrompt le moteur de trading
- Ecrit dans les tables de decisions ou de trades

Les checks lisent uniquement les donnees existantes ou injectent des
donnees synthetiques dans des stores temporaires isoles.

### 8.2 Data Governance Spec v1.0

Les checks IV-LIVE-001 a IV-LIVE-010 completent les criteres DG-001 a DG-024
en ajoutant une couche de validation de l'observateur lui-meme.

Un dataset ne peut pas atteindre DG-Level 3 (Certified) si:
- Le DIP qui l'a produit est < Level 3 (Certified Live Observer)
- L'OCS au moment de la collection etait < 90

### 8.3 EXP-001 (Burn-in)

La certification Level 4 (Certified Dataset Producer) est prerequise pour:
- La conclusion definitive des hypotheses H1, H2, H3
- Tout passage en trading reel
- Toute modification des seuils du moteur (ACE)

### 8.4 Scientific Debt Rule

L'ajout de nouveaux checks IV-LIVE necessite:
- Un hypothesis existante (H1-H6) que le check aide a valider
- OU un besoin de mesure identifie dans ce document
- Jamais une intuition ou une opportunite technique

### 8.5 Scientific Intelligence Layer (L3.5)

L'OCS est un prerequis pour L3.5, mais il n'est pas equivalent a la
`Knowledge Confidence`.

| Score | Question |
|-------|----------|
| OCS | Peut-on faire confiance a l'observateur ? |
| Knowledge Confidence | Peut-on faire confiance a la connaissance produite ? |

Une conclusion L3.5 ne peut pas etre promue en connaissance scientifique si:
- l'observateur etait sous le seuil OCS au moment de la collecte ;
- le dataset source n'est pas CERTIFIED ou PASS ;
- l'hypothese n'est pas versionnee ;
- l'evidence ne reference pas explicitement son dataset et son experience.

---

## 9. Scientific Lineage

La chaine de confiance scientifique du projet:

```
Moteur de trading (ADR-0007: gel fonctionnel)
         |
         v
DIP Observer (certifie par IV-001..IV-010)
         |
         v
DIP Live Observer (certifie par IV-LIVE-001..IV-LIVE-010)
         |
         v
Dataset certifie (DG-001..DG-024, CRI >= 90)
         |
         v
Hypotheses H1-H6 testables
         |
         v
Scientific Intelligence Layer (Knowledge Confidence + contradictions + drift)
         |
         v
Calibration autorisee (OCS >= 90, CRI >= 90)
         |
         v
Trading reel (Phase 2)
```

Chaque niveau est une porte qu'on ne peut pas franchir sans avoir certifie le niveau precedent.

---

## 10. Revision de ce document

Ce document est versionne. Toute modification necessite:
- Un ADR signe par l'operateur
- La re-certification a partir du niveau affecte par le changement
- Une entree dans l'historique de certification

**v1.0 (2026-07-01):** Creation initiale, 4 niveaux, III + OCS, 20 checks.
