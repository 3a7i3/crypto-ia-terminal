# Handoff — session 2026-07-20/21

## Ce qu'on a fait

1. **Compte n°1 (soldes réels multi-exchange)** — déployé (tag
   `deploy-20260720-2302`), vérifié live MEXC $7.29 + Binance $0.91. Puis
   **entête « Statut Compte Réel » branchée** sur l'agrégat compte n°1 en
   observation (commit `f427895`, `deploy-20260720-2328`) — affichait $0, montre
   maintenant le vrai total. Affichage uniquement, sizing intact (ADR-0007).
2. **Direction Execution Lab / Knowledge Base** (recherche, passive) — cadrée avec
   Mathieu : voir mémoire `project_execution_lab_v2` + `research/execution_lab/market_laws.md`.
   - Probe #1 (MAE/MFE) : l'exécution N'EST PAS le goulot ; c'est confondu avec
     l'alpha (WR 26 %).
   - Probe #2 (Signal Survival) : impulsions haussières **réversent** (propriété
     locale, LAW-001 niveau E1, PAS « mean-reversion validée »).
3. **Dossier Go/No-Go V4** — voir `docs/go_no_go/DOSSIER_GO_NO_GO_V4.md`.
   Découverte majeure : **rupture de traçabilité** du pipeline regret (ancien
   mort le 10/07, le CRI lisait le fichier mort → faux zéros). Corrigé :
   MC-001 + ADR-0018 + patch CRI (source canonique v2 + fraîcheur + validité).

## Où on en est

- **CRI = 8.0** (valide, source corrigée ; était 6.75 censuré). N(V4)=30 (9W/21L).
- Verrous regret **atteints** à 1h (MW=158/GR=141) ; le goulot est **N trades pris**.
- Verdict dossier : **NO-GO propre** (insuffisance de N, pas échec).

## Ce qui reste (par priorité)

1. **Décision infra GCP** (Mathieu, avant ~05/08) : activer facturation / pause /
   migrer. + promouvoir 35.240.166.72 en **IP statique** (sinon whitelist MEXC casse).
2. **Déployer** le patch CRI + MC-001 sur le VPS quand tu valides (ce soir =
   commit local seulement, pas déployé). Puis relancer `cri_calculator.py` sur le VPS.
3. **Pipeline regret v1** : investiguer *pourquoi* l'ancien `RegretEngine` s'est
   tu le 10/07 (optionnel — v2 le remplace ; utile pour l'autopsie).
4. **Vérif visuelle Telegram** du panneau Compte n°1 (rendu, pas juste la lecture).
5. Execution/Knowledge Base : **laisser le pouls accumuler** (2e fenêtre pour
   LAW-001 → E2) ; ne rien construire de plus tant que l'alpha n'est pas tranché.

## Invariants respectés

Zéro contact avec le moteur de trading. Tout est mesure/gouvernance/affichage.
Claude ne manipule jamais les valeurs de clés. Rien déployé sans go explicite.
