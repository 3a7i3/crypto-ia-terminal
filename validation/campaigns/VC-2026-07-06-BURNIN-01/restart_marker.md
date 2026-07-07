# RESTART-2026-07-06

Validation Campaign: VC-2026-07-06-BURNIN-01
Protocol Version: VP-1.0
SHA: 7537d00
Dataset UUID: 5b584286-d869-4e4e-b4f6-42990ff80911

## Motif

- Merge OBS-001/OBS-002
- Fix wallet_sync (continuité du ledger)
- Épinglage de la base CapitalThrottle sur WALLET_PAPER_CAPITAL (ADR-0011)
- REAL_BOT_REPORT_EVERY : 12 → 72

## Objectif

Préserver la stationnarité du processus de validation et garantir un sizing
invariant aux redémarrages.

## Validation Mode

- [x] CapitalThrottle pinned (ADR-0011)
- [x] Wallet ledger continuous
- [x] P7 enabled
- [ ] P7 frozen

## Critères d'acceptation

- [ ] Positions ouvertes = 0
- [ ] Déploiement SHA vérifié
- [ ] Restart effectué
- [ ] Premier ordre : size_usd == 10.00
- [ ] Aucun changement inattendu du pipeline d'exécution

## Décision

GO — Redémarrage autorisé  
GO CONDITIONNEL — Campagne expérimentale (qualification P7 en cours)
