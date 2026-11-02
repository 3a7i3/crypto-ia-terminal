# Passation CryptoRadar Flux (#551/#553) — état au 2026-11-02

Revues citées : **revue technique Codex** (indépendante de l'auteur, **pas une validation humaine**).

| Étape | Statut |
|---|---|
| #552 revue + prototype L2 (R1–R4) | REVU (Codex, HEAD f8efe3c0) et FUSIONNÉ sous le mandat : main 46b6fb3a |
| Cœur Flux #554 | CORRIGÉ pour F1–F5 de la revue Codex au HEAD d7c3276a (arithmétique exacte, frontière as_of par réception complète, contrat imbriqué fermé, identité flux/carnet, convention de côté). Nouvelle revue du nouveau HEAD ATTENDUE. NON FUSIONNÉ, brouillon |
| Reader/API GET `market-flow` #555 | Contre-exemples imbriqués ajoutés (NaN, clé inconnue, identité, NOT_COVERED à zéro, ns numériques refusés en 503 typé). Dépend de #554. NON FUSIONNÉ, brouillon |
| CI | #554/#555 visaient des branches intermédiaires : aucun des quatre checks requis n'avait tourné. Les PR ciblent `main` ; la CI complète doit être lue au nouveau HEAD (non revendiquée tant qu'elle n'est pas lue) |
| Validateur TypeScript, fixtures cross-stack, vue Marché → Flux, audit visuel | **NON FAIT** : à écrire sur le contrat imbriqué corrigé, après relecture ; rien n'est figé avant |
| Release épinglée | NON FAITE (après fusion) |
| Installation isolée INACTIVE | NON FAITE : prérequis fusion non remplis |
| Dossiers collecte / publication / rollback | PRÉPARÉS ; budgets, SHA et chemins de rollback réels à remplir à la décision |
| INSTALLÉ / DÉMARRÉ / RÉELLEMENT VÉRIFIÉ | rien |

Contrat : les durées en ns du bloc `book` sont des chaînes décimales ; `inputs` expose trois compteurs
(`events_after_as_of_not_read`, `events_straddling_as_of_not_read`, `l2_events_not_read_after_straddle`).
Fixtures synthétiques, pas des preuves fournisseur ; la convention de côté reste non attestée.
