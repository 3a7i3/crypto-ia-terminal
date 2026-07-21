# Dossier Go/No-Go — Époque V4

**Date : 2026-07-21** · Borne : `CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` ·
Reproductible via `tools/cri_calculator.py` (source regret : MC-001 / ADR-0018)

## Verdict

> **NO-GO — par insuffisance de preuves (N=30), PAS par échec démontré.**
> À N=30 trades pris, le moteur n'est ni prouvé profitable ni prouvé non
> profitable : **indécidé**. Evidence Score = 0.

Ce verdict découle mécaniquement des règles pré-enregistrées, pas d'une opinion.

## 1. Validité expérimentale (Instrumentation Gates)

*Distinguer un manque de données d'un défaut de collecte.*

| Collecte | État |
|---|---|
| Trades (`paper_trades.jsonl`) | ✅ |
| Horizons (`horizon_eval`) | ✅ |
| Pouls (`market_pulse`) | ✅ |
| Regrets — source canonique `regret-v2` | ✅ (rétablie ADR-0018 ; ancien `regret-v1` mort 2026-07-10) |
| CRI | ✅ **valide** (source fraîche ; avant ADR-0018 : ⚠️ partiellement censuré) |

## 2. Scorecard scientifique (Evidence Gates)

| Critère | Requis | Réel V4 | État |
|---|---|---|---|
| N trades | 500 | 30 | ❌ |
| Winners / Losers | 150 / 150 | 9 / 21 | ❌ |
| MISSED_WIN @1h | 100 | 158 | ✅ |
| GOOD_REFUSAL @1h | 100 | 141 | ✅ |
| Par couche (@1h) | 30 | meta=220, gate=79 | ✅ |
| Par régime (@1h) | 50 | bear=182, hv=53, bull=51 (sideways=13) | ⚠️ partiel |
| **CRI** | ≥ 90 | **8.0** (n=6, cov=20, drift=0, bal=6) | ❌ |

**Lecture** : la couverture des *refus* est atteinte (verrous regret ✅). Le
blocage est l'axe **alpha des trades pris** (N=30, WR 26 %) — patience, pas défaut.

## 3. Gouvernance (Governance Gates)

- Verrous EXP-001 (H1/H2/H3 non-Inconclusive, zéro contradiction) : **non
  évaluables** tant que N < min_n_required. À compléter quand N croît.
- Source de mesure sous contrat versionné (MC-001) + assertion de fraîcheur : ✅.

## 4. Trajectoire vs deadline GCP (~2026-08-05)

À ~7 trades/j : N=100 (gate L2 S1→S5) ≈ **10 j** (checkpoint atteignable) ;
N=500 ≈ **67 j** = impossible avant la deadline. → Le livrable réaliste avant le
5 août n'est pas un GO mais **ce dossier honnête** + une **décision opérationnelle
d'infrastructure** (payer/continuer, pause+snapshot, migrer, ou viser le
checkpoint L2) — décision opérateur.

## 5. Décision demandée à l'opérateur

Le verdict scientifique (inconclusive) est réglé. La question ouverte est
**infrastructure** : maintenir le burn-in vers le checkpoint L2 (N=100) implique
d'activer la facturation GCP avant l'échéance. Recommandation : viser L2, source
regret désormais saine → chaque jour de burn-in produit enfin des preuves
exploitables.
