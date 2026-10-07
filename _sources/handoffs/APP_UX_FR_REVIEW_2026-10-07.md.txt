# Revue frontend FR — Machine et Laboratoire quantitatif

Branche locale : `ux/machine-laboratoire-fr`. Base GitHub et HEAD distant revérifié le 7 octobre 2026 : `69f16dc9ebcc665848f3fb38d5fba3bf586abf45` (inchangé). Aucun AGENTS.md trouvé. Aucun push, merge, déploiement ni accès VPS.

## Audit et périmètre

Lecture de #323 APP-UNIFY, #283 UX, #282 burn-in, #286 immutabilité, de leurs commentaires pertinents, des contrats API/frontend, des documents Machine/Laboratoire, de la certification U7 source et des scripts/preuves visuelles existants. U7 reste une certification de la source antérieure : ce changement ne la renouvelle pas. U8 demeure non autorisé et non certifié runtime ; #286 actif ; frontière formellement certifiée L3. Aucun résultat de cette revue ne certifie L4.

Les écrans juxtaposaient des mesures et preuves dans de petites cartes. Les contrats financiers publient des snapshots, sans série temporelle de portefeuille ou résultat réalisé. Le principal déployé/réservé ne peut être additionné. Les stratégies publient des évaluations indépendantes et des cohortes : aucune filiation de versions ne permet une progression globale. Les deux prototypes HTML cités n'étaient pas présents dans l'espace accessible.

## Résultat

- `/` ouvre la synthèse Machine : trois faits prioritaires, puis État, Portefeuille et finances, Marché. Aucune synthèse de santé inventée ; fraîcheur et autorité restent propres à chaque source.
- CryptoRadar : un seul tableau, symbole fixe, défilement contenu, recherche/filtres et fiche clavier/tactile. Ordre source conservé. Seulement les champs publiés ; score explicitement distinct d'une probabilité de gain.
- Finance : capital regroupé, résultat/frais regroupés, valeurs décimales exactes inspectables, contrôles et réconciliation repliables. Aucun nouveau total, ratio ou calcul financier.
- Laboratoire : tableau de stratégies, évaluation et population, métriques avec effectifs, critères, solidité et rang par cohorte comparable ; fiche méthodologique. Filtres et preuves ouverts à la demande.
- Présentation française via une couche dédiée ; noms API/enums inchangés. Les textes et identifiants des artefacts producteurs restent bruts dans les preuves pour conserver leur sens et leur provenance.
- Comparaison renommée « Comparaison ancien simulateur / journal PPL », avec explication d'audit et autorité du snapshot historique conservée.

## Démonstration et données manquantes

`npm run dev:demo` sert une entrée séparée avec un bandeau permanent **DÉMONSTRATION · DONNÉES FICTIVES** et trois scénarios : publication synthétique, ancienne, absente. Les API sont résolues uniquement depuis les fixtures locales, sans proxy ni repli runtime ; mutations rejetées. Les courbes et la répartition fictives sont indépendantes des snapshots. Le bundle de production n'importe pas ces séries.

En production : « Historique non disponible ». Il manque une série publiée de portefeuille et de résultat réalisé, une répartition avec dénominateur et parts non chevauchantes publiées, et des liens explicites entre évaluations/versions comparables. Contrat proposé, **DRAFT non implémenté** : `docs/contracts/APP_UX_FR_HISTORY_PRESENTATION_DRAFT.md`. Aucun collecteur ajouté. Capital disponible ≠ liquidité du marché ; inconnu ≠ zéro ; PnL positif ≠ validation.

`build:demo` vérifie la compilation de l'entrée de démonstration ; le middleware de fixtures appartient au serveur de développement. Utiliser `dev:demo` pour l'aperçu interactif, pas un serveur statique générique de `dist-demo`.

## Vérifications

- TypeScript et build production : PASS ; build démonstration : PASS.
- Vitest : **415/415**, aucun test sauté. Contrats, nulls, zéros explicites, sources indépendantes et navigation conservés ; deux tests ajoutés sur valeurs inconnues/zéro et Advisor ancien.
- Python cross-stack : **96/96** (avertissement de dépréciation Starlette/httpx uniquement).
- Transport local/PWA Node : **7/7**.
- Navigateur démonstration : **128 contrôles PASS**, largeurs 320, 390, 820, 1440 : absence de débordement de page, tableau unique, ordre source, recherche, filtres, focus/Escape, valeurs exactes, provenance, lecture seule, scénarios anciens/manquants, aucune exception navigateur.
- Preuves locales U2b, U3a, U3b, U4, U6, WEB-DIR-D3, WEB-01 marché, FIN-02, WEB-02 comparaison, WEB-RL recherche : PASS. E2E production via serveur HTTP/API synthétique local WEB-01G : PASS. Les scripts ont été adaptés aux libellés français et à la navigation effective sans retirer les invariants de source.
- `git diff --check` : PASS. Les avertissements Vite sur le futur chargement natif de configuration sont informatifs.

## Aperçu et reproduction

Depuis la racine du dépôt, environnement Python local avec les dépendances CI :

```bash
python -m pip install -r requirements-ci.txt
for module in fixtures market_fixture scanner_fixture microstructure_fixture ppl_comparison_fixture research_lab_fixture research_publication_fixture burn_in_fixture runtime_service_fixture strategy_board_fixture financial_clarity_fixture event_center_fixture storage_fixture; do
  python -m tests.cross_stack.generate_$module --out frontend/.cross-stack-fixtures
done
cd frontend
npm ci
npm run dev:demo
```

Ouvrir `http://localhost:3002`. Aucun credential nécessaire, aucun service externe.

```bash
npm test -- --run
npm run build
npm run build:demo
npm run test:runtime
npm install --no-save --package-lock=false playwright@1.56.1
npx playwright install chromium
node scripts/capture_ux_fr_visual.mjs
```

Depuis la racine : `python -m pytest tests/cross_stack -q`.

Galerie locale : `frontend/artifacts/ux-fr/index.html`. Captures avant issues du main d'origine : 49 ; après : 68 captures finales, états anciens/manquants et fiches compris. Toutes synthétiques, aucune preuve runtime ; comparer la hiérarchie, pas les valeurs entre scénarios. Les fichiers lourds sont ignorés par Git et fournis dans une archive locale. Diff complet fourni séparément. Proposition de PR : `APP_UX_FR_PR_PROPOSAL.md`.
