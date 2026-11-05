# Passation CryptoRadar Flux (#551/#553) — 2026-11-05 UTC (lot 3A)

Base source du relevé du 2026-11-04 : `main@9433c18b5077cc957bfdf2c8bd707070dc5c67d1`.
Mise à jour du lot 3A faite sur `main@dfb6b9b1840c7353f8d1fdc35869081fffac4718`
(tree `3f02691ea03bcf46f3fc20980bf4add3edb4c10e`) ; elle ne porte pas son propre
SHA, qui est celui de la PR (voir l'historique git du fichier).
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
| Types, validateur strict et client GET TypeScript Flux (3A) | **ÉCRITS ET TESTÉS EN SOURCE** dans la PR du lot 3A, en attente de revue indépendante ; non fusionnés tant que cette PR ne l'est pas | Aucun consommateur : ni vue, ni hook, ni route, ni appel au chargement |
| Fixtures Flux générées via replay → reader → route et corpus Python/TS (3A) | **ÉCRITS ET TESTÉS EN SOURCE** dans la même PR | Corpus synthétique ; ni preuve fournisseur ni donnée réelle |
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

## Lot 3A — contrat frontend Flux : état source

Périmètre : 14 fichiers (12 créations, 2 modifications), contrat TypeScript 1.0.0,
sans vue ni branchement. Le garde-fou #286 reste ACTIVE ; #397 HOLD ; #374 PARKED.

| Fichier | Rôle |
|---|---|
| `frontend/src/lib/marketFlowTypes.ts` | Types immuables et variantes discriminées ; ns/décimales en texte, compteurs en entiers sûrs |
| `frontend/src/lib/marketFlowExact.ts` | Grammaires ns/décimal, arithmétique BigInt bornée aux assertions du contrat Python, règles de texte Python (table `isprintable` de CPython 3.11 / Unicode 14.0.0, longueur en points de code) |
| `frontend/src/lib/marketFlowJson.ts` | Lecture stricte du JSON brut : UTF-8 strict, BOM refusé, clés dupliquées (après échappement), lexèmes non entiers ou hors plage sûre, profondeur 64, borne d'octets 4 001 024 |
| `frontend/src/lib/marketFlowValidation.ts` | Port des règles de forme et de cohérence de l'oracle Python ; `validateMarketFlowArtifact` / `validateMarketFlowPublication` (prédicats typés) et variantes `check…` qui rendent le premier refus |
| `frontend/src/lib/marketFlowClient.ts` | `fetchMarketFlow` : GET unique `/api/operator/v1/market-flow`, `no-store`, `redirect: error`, délai 5 s couvrant en-têtes et corps, annulation externe, lecture bornée par les octets reçus ; résultat `success` / `api_error` / `transport_error` |
| cinq suites `frontend/src/test/marketFlow*.test.ts` | Exact, JSON brut, validation, client, corpus différentiel Python/TS |
| `tests/cross_stack/generate_market_flow_fixture.py`, `test_market_flow_integration.py` | Génération réelle hors réseau et preuves Python |
| `.github/workflows/cross-stack-compat.yml` | Générateur et cinq suites ajoutés à la liste explicite du gate |

Comportements à retenir :

- **Pipeline réel** : `synthetic_session → artifact.replay → fichier temporaire → MarketFlowReader → TestClient GET → octets bruts → lecteur strict, validateur et client TS`. Douze cas natifs (dont ns > 2**53, ns à 30 chiffres, ETH-USD avec texte non-BMP, as_of à cheval, book INVALID/NO_SNAPSHOT, motif natif MALFORMED_MESSAGE, `event_time` daté et epoch placeholder, silence dépassé, profondeur limitée, sans trades). Les variantes dérivées (HISTORICAL, classifications de fraîcheur) sont étiquetées comme telles : ce ne sont ni des sorties natives ni une preuve historique.
- **Corpus différentiel** : plus de 42 000 mutations (une par nœud et par opération, sur six artifacts natifs, plus des frontières Unicode) portent chacune le verdict de l'oracle Python ; le TypeScript doit rendre le même. Un échantillon passe aussi par le vrai reader. Le test échoue, sans skip, si le manifeste, un cas, un fichier ou un hash manque ; une version Python/Unicode différente de 3.11 / 14.0.0 fait échouer le test de la table au lieu de masquer la divergence.
- **Succès** : seul un HTTP 200 dont le JSON brut est strict et dont la publication (clés de l'artifact + `serving`) est valide. Un 200 invalide est `transport_error` (`CONTRACT_INVALID`, `INVALID_JSON`, `INVALID_UTF8`, `BODY_TOO_LARGE`…), jamais un `api_error` au code inventé. Un non-200 garde son statut HTTP ; le code n'est repris que s'il est publié tel quel (`{"error_code": "<CODE>"}`).
- **Rien d'autre** : aucun polling, retry, hook, composant, route, service worker, fetch ou timer à l'import ; aucune horloge navigateur ne qualifie une fraîcheur ; aucune fraîcheur ni qualification fournisseur n'est déduite d'un 200.

Commandes (depuis la racine du dépôt, Python 3.11, Node ≥ 20.19) :

```
python -m tests.cross_stack.generate_market_flow_fixture --out frontend/.cross-stack-fixtures
cd frontend && npm ci
CROSS_STACK_FIXTURES_DIR="$PWD/.cross-stack-fixtures" npx vitest run src/test/marketFlowExact.test.ts \
  src/test/marketFlowJson.test.ts src/test/marketFlowValidation.test.ts src/test/marketFlowClient.test.ts \
  src/test/marketFlow.compat.test.ts
npm run build
pytest -q tests/market_flow tests/cross_stack/test_market_flow_integration.py
```

Limites connues, à ne pas effacer :

- Les bornes de transport (4 001 024 octets, profondeur 64) sont des propositions éprouvées sur charges synthétiques, pas des bornes du contrat Python : le reader borne le fichier à 4 000 000 octets puis ajoute au plus 66 octets de `serving` en sérialisation compacte ; une profondeur valide est de 7. Mesures locales : ~3,86 Mo lus et validés en ~0,1 s.
- La table d'impression Unicode est celle de Python 3.11 / Unicode 14.0.0. Un autre Python (ou une nouvelle version d'Unicode) exige de régénérer la table ; le gate le signale par un échec.
- `CHANGED_DURING_READ` du reader n'est pas produit par le corpus (course de fichier non reproductible hors réseau) ; son mapping `api_error` est celui de tout code `MARKET_FLOW_*`.
- Un 200 valide prouve la conformité formelle d'une fixture : ni fraîcheur, ni admission fournisseur, ni donnée réelle.
- Le corpus est fini : ce n'est pas une preuve pour tout JSON ni toute version d'Unicode.

États : **3A source** écrit et testé, PR en attente de revue indépendante, non fusionné ;
**3B (vue Marché → Flux) NON FAIT** ; **installation, collecte, publication NON EFFECTUÉES** ;
**données réelles NON ADMISES** ; revue, fusion, installation, service, admission et
certification sont des étapes distinctes dont aucune n'est déduite de la CI. Résultats
et SHA exacts : dans la PR, au HEAD relu.

Les [dossiers de collecte](COLLECTION_DOSSIER.md) et de
[publication](PUBLICATION_DOSSIER.md) restent des préparations. Une fusion
source ne crée aucun GO d'installation, collecte ou activation. #286 ACTIVE.
