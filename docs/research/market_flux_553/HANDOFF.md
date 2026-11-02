# Passation CryptoRadar Flux (#551/#553) — état au 2026-11-02

| Étape | Statut |
|---|---|
| #552 revue + prototype L2 (R1–R4, version de flux) | REVU par l'opérateur au HEAD 754c78c0, corrigé ; nouvelle revue du HEAD courant attendue. NON FUSIONNÉ |
| Cœur Flux (trades, CVD, L2, heatmap, replay, artifact) | PRÉPARÉ, CI à confirmer, dépend de #552. NON FUSIONNÉ |
| Reader/API GET `market-flow` | PRÉPARÉ (cette PR), dépend du cœur. NON FUSIONNÉ |
| Validateur TypeScript, fixtures cross-stack, vue Marché → Flux, audit visuel | **NON FAIT** (prochaine PR ; nécessite `npm ci`, la modification de `cross-stack-compat.yml` et un audit mobile/bureau) |
| Release épinglée | NON FAITE (après fusion) |
| Installation isolée INACTIVE | NON FAITE : prérequis fusion non remplis ; connecteur Remote Desktop Commander indisponible dans la session |
| Dossiers collecte / publication / rollback | PRÉPARÉS (ce dossier) |
| INSTALLÉ / DÉMARRÉ / RÉELLEMENT VÉRIFIÉ | rien |

Reprendre : revue indépendante de #552, #554 et de la PR reader ; rebaser les PR dépendantes sur `main` après fusion
et recalculer diff et CI ; puis TypeScript/UI.
