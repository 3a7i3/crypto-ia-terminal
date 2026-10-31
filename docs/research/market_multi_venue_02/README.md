# Préparation multi-plateformes — où la trouver

Mission [#536](https://github.com/3a7i3/crypto-ia-terminal/issues/536). Contrat : [MARKET_MULTI_VENUE_02](../../contracts/MARKET_MULTI_VENUE_02.md).

## Dans l’app préparée

Ouvrir **Marché → Comparaison des plateformes**. Le scanner reste le premier onglet.
Choisir un instrument et une référence ; cliquer sur une plateforme pour voir sa provenance et ses dates.
Les instruments en USD, USDT ou USDC et les produits spot/dérivés restent distincts.
L’exemple synthétique sert à vérifier l’interface ; il ne prouve aucune connexion à une plateforme.

## Dans le dépôt

Les décodeurs de réponses fournies sont dans `observability/market_venues/`.
Le lecteur de publication est dans `observability/operator_api/venue_comparison_reader.py`.
L’écran est dans `frontend/src/views/MarketVenuesView.tsx`.
Le [registre des 25 candidats](../market_multi_venue_01/venue_candidates.json) distingue huit décodeurs offline des adaptateurs réseau encore absents. Il ne s’agit pas de 25 exchanges connectés.

## Reproduire sans service actif

Depuis un checkout isolé avec les dépendances CI et frontend installées :

```bash
python -m pytest -q tests/cross_stack/ tests/market_venues/
python -m tests.cross_stack.generate_market_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_venue_comparison_fixture --out frontend/.cross-stack-fixtures
cd frontend
CROSS_STACK_FIXTURES_DIR="$PWD/.cross-stack-fixtures" npx vitest run src/test/venueComparison.compat.test.tsx
npm run build
CROSS_STACK_FIXTURES_DIR="$PWD/.cross-stack-fixtures" node scripts/capture_venue_comparison_visual.mjs
```

La dernière commande exige Playwright/Chromium installés avec sandbox disponible (voir `.github/workflows/cross-stack-compat.yml`). Les images et `checks.json` vont dans `frontend/artifacts/market-venues/`, ignoré par Git.
Le script fournit les réponses et le build au navigateur par interception locale ; il ne démarre pas de serveur et ne contacte ni API active ni exchange.

Cette tranche prépare la source et les preuves. L’app actuellement servie n’est pas modifiée. Sans publication séparément admise et configurée, le nouvel endpoint retourne une source indisponible.
