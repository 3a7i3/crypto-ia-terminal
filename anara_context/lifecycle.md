# Cycle de vie d'une décision — crypto_ai_terminal

## Vue d'ensemble

Chaque opportunité de trading traverse un pipeline de 6 agents avant d'être
exécutée ou rejetée. Le tout est encapsulé dans un **DecisionPacket** — un
objet immuable qui voyage à travers les couches sans jamais être détruit.

---

## Pipeline nominal (flux heureux)

```
LiveSignalEngine  →  ConvictionEngine  →  GlobalRiskGate
       ↓                    ↓                    ↓
  SIGNAL_GENERATED    CONTEXT_ENRICHED      RISK_EVALUATED
                                                 ↓
                                           PortfolioBrain
                                                 ↓
                                             APPROVED
                                                 ↓
                                           OrderSizer
                                                 ↓
                                        EXECUTION_PENDING
                                                 ↓
                                        ExecutionEngine
                                                 ↓
                                            EXECUTED
```

---

## Les 6 agents et leur rôle

### 1. LiveSignalEngine — Détection
- Agrège 4 sources (indicateurs, MTF, volume, régime)
- Produit : score 0-100, direction (LONG/SHORT/FLAT), régime marché
- **Ne juge pas** — détecte et structure

### 2. ConvictionEngine — Évaluation
- 5 dimensions : tendance, momentum, régime, volume, qualité signal
- Calcule le niveau de conviction (SKIP → VERY_HIGH)
- **Enrichit uniquement** — ne peut pas rejeter

### 3. GlobalRiskGate — Protection
- 5 conditions binaires : session, drawdown journalier, kill switch, pertes
  consécutives, nombre de positions
- **Seul autorisé à REJECT en flux normal**
- Un seul "non" = REJECTED immédiat

### 4. PortfolioBrain — Gouvernance portefeuille
- 8 checks : exposition totale, concentration, corrélation, fragmentation,
  levier, direction balance, budget positions, liquidité
- **Peut REJECT sur dépassement portefeuille**
- Ne connaît pas le sizing (séparation institutionnelle)

### 5. OrderSizer — Sizing
- Formule Kelly + facteur volatilité ATR + facteur drawdown
- Lit les advisories des couches précédentes
- **Ne peut pas rejeter** — calcule uniquement

### 6. ExecutionEngine — Exécution
- Place l'ordre sur l'exchange (paper / testnet / live)
- Mode déterminé par la variable `ORDER_MODE`
- **Exécute — ne décide pas**

---

## Résolutions possibles

| État | Type | Déclencheur | Signification dashboard |
|------|------|-------------|------------------------|
| EXECUTED | Succès | ExecutionEngine | Capital engagé — surveiller position |
| REJECTED | Bloc normal | GlobalRiskGate / PortfolioBrain | Règle de risque activée — normal |
| VETOED | Bloc absolu | ExecutiveOverride | Intervention gouvernance — vérifier |
| FAILED | Erreur | ExecutionEngine | Problème technique — aucun capital engagé |
| EXPIRED | Timeout | System | Signal périmé — TTL dépassé |
| CANCELLED | Manuel | Opérateur / Override | Annulation volontaire |

---

## Post-mortem (après clôture de position)

Chaque trade fermé est analysé par **MistakeMemory** :

| Catégorie | Conviction | Résultat | Interprétation |
|-----------|------------|---------|----------------|
| **VALIDATED** | Élevée | Gagnant | Trade correct — répliquer |
| **LUCKY** | Faible | Gagnant | Chanceux — ne pas sur-apprendre |
| **UNLUCKY** | Élevée | Perdant | Malchance — ne pas sur-corriger |
| **MISTAKE** | Faible | Perdant | Vraie erreur — générer règle auto |

Les **MISTAKE** génèrent automatiquement des règles de blocage pour les
patterns identifiés (régime + signal → perte répétée).

---

## Principes d'observabilité

1. **Tout rejet visible** — raison détaillée dans le dashboard avec l'agent responsable
2. **Duration_ms par cycle** — temps cognitif enregistré de CREATED à résolution finale
3. **Chaque décision tracée** — `databases/black_box.jsonl` — immuable, une ligne par événement
4. **État history complet** — chaque transition horodatée avec acteur et durée

---

## Métriques dashboard clés

| Métrique | Source | Affichage |
|----------|--------|-----------|
| Taux d'exécution | advisor_loop | % de signaux → EXECUTED |
| Taux de rejet | black_box | % REJECTED par agent |
| Durée cycle | advisor_loop | ms de CREATED → résolution |
| Conviction moyenne | conviction_engine | score 0-100 |
| Taux d'erreur | mistake_memory | % MISTAKE sur trades fermés |
| Drawdown session | global_risk_gate | % perte depuis ouverture |
