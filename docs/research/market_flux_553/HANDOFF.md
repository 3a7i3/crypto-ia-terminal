# Passation CryptoRadar Flux (#551/#553) — 2026-11-04 UTC

Base source : `main@9433c18b5077cc957bfdf2c8bd707070dc5c67d1`.
Ce relevé remplace l'état du 2026-11-02, conservé dans
[l'historique du fichier](https://github.com/3a7i3/crypto-ia-terminal/blob/9433c18b5077cc957bfdf2c8bd707070dc5c67d1/docs/research/market_flux_553/HANDOFF.md).
Les revues Codex sont techniques, indépendantes de l'auteur, pas des approbations
humaines. Le [checkpoint lot 2](../../handoffs/LOT2_TRACKING_RECONCILIATION_20261104.md)
porte les preuves et décisions détaillées.

| Étape | État source vérifié | Installation / activation / preuve |
|---|---|---|
| #552 prototype L2 hors réseau | **FUSIONNÉ**, HEAD `f8efe3c05305394b841ddea87c7a4ef5da894b4e`, fusion `46b6fb3ad1a91b08f9a0d25f4e4ed7ad070a1f7e` | Fixtures synthétiques ; aucune preuve fournisseur |
| #554 cœur trades/CVD, L2, heatmap/replay | **FUSIONNÉ**, HEAD `fc3a3d53f3d8eab261a10e6218b048d5541d3100`, fusion `24d497423f26972b27f7647865b39e6dfadc3ff0` | Présence sur main, pas preuve d'un service actif |
| #555 reader/API GET `market-flow` | **FUSIONNÉ**, HEAD `c6d21a9f7efd12c6b7cc6dd4f8d17a05509d2ef6`, fusion `9b960aa6e8ccd7500ea74ad9153f0c0be617fbb8` | Route source disponible ; 404 sur la release #537 au dernier audit |
| #556 refus SOURCE_CHANGED sur bruit d'ancêtres | **FUSIONNÉ**, fusion `9433c18b5077cc957bfdf2c8bd707070dc5c67d1` | CI post-fusion : 19 workflows / 24 check-runs SUCCESS, preuve source bornée à ce commit |
| Types, validateur et client TypeScript Flux | **NON FAITS**, lot 3A proposé | Aucun consommateur frontend Flux validé |
| Fixtures Flux générées via builder/reader/API et corpus Python/TS | **NON FAITS**, à livrer avec 3A | Les suites cross-stack existantes ne prouvent pas encore cette composition |
| Vue Marché → Flux et audit visuel | **NON FAITS**, lot 3B après 3A | `frontend/src/views/MarketView.tsx` expose Scanner et Comparaison, pas Flux |
| Release Flux épinglée / installation inactive | **NON FAITES pour Flux** | Les paquets isolés antérieurs de #550 ne sont pas une release Flux |
| Collecte bornée / publication passive | Dossiers **PRÉPARÉS, NON AUTORISÉS, NON EXÉCUTÉS** | SHA, budgets, admissibilité, custody et rollback réels à fixer avant décision distincte |
| Flux démarré et réellement vérifié | **NON ÉTABLI** | Aucun nouvel audit runtime ni capture exécutée dans le lot 2 |

Dernière observation runtime disponible, **historique** : 2026-11-03
18:35:26 UTC. API/Web observés sur la release
`1da7376829f82eacfb52794ec267be97523fb244` (#537). Le snapshot `/market`
était daté du `2026-10-29T05:32:36Z` ; son HTTP 200 ne prouvait aucune fraîcheur.
`/market-flow` répondait 404. Après une future release compatible, l'absence de
`OPERATOR_MARKET_FLOW_PATH` doit donner le refus 503 typé
`MARKET_FLOW_NOT_CONFIGURED`, pas des données inventées.

## Prochaine mission proposée — 3A, contrat frontend

Auditer le contrat imbriqué intégré, puis faire valider le plan avant de coder :
types/validation stricte/client et génération de fixtures depuis le vrai
builder/reader/API. Exécuter les corpus Python/TypeScript ; refuser types
invalides, enums inconnus, NaN et identités/dates incohérentes ; conserver les
ns exactes et les motifs de refus natifs. La vue 3B et les opérations de
release/collecte/publication restent séparées.

Contrat acquis : durées ns du bloc `book` en chaînes décimales ; compteurs
`inputs` : `events_after_as_of_not_read`, `events_straddling_as_of_not_read`,
`l2_events_not_read_after_straddle`. Fixtures `SYNTHETIC`, jamais des preuves
fournisseur ; convention de côté non attestée.

Les [dossiers de collecte](COLLECTION_DOSSIER.md) et de
[publication](PUBLICATION_DOSSIER.md) restent des préparations. Une fusion
source ne crée aucun GO d'installation, collecte ou activation. #286 ACTIVE.
