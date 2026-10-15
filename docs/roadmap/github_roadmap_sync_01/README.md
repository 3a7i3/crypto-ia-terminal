# GITHUB-ROADMAP-SYNC-01 — synchronisation GitHub du tableau « Travaux et roadmap »

Statut : **SOURCE LOCALE · brouillon · NON DÉPLOYÉ**. Aucun déploiement VPS, webhook, planification ni jeton.
Source/UI uniquement ; le garde-fou [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) n'est pas touché.

## Ce que fait la v1

Un bouton « Actualiser depuis GitHub » lit, à la demande, `3a7i3/crypto-ia-terminal` en lecture seule depuis le navigateur :
labels, jalons, issues et PR (pagination suivie), PR ouvertes et PR citées par le registre, et les check runs du **HEAD exact**
de chaque PR (`/commits/<head_sha>/check-runs`, chaque run doit porter ce `head_sha`).

1. Le relevé produit un **candidat** ; rien n'est remplacé.
2. L'**aperçu** liste les différences par mission (état d'issue/PR, HEAD, CI, labels, jalon), le nombre d'objets GitHub non
   rattachés et les écarts « à vérifier » entre registre et GitHub.
3. « Remplacer le relevé affiché » valide le candidat ; « Ignorer » le jette.
4. Seuls les relevés **complets** sont conservés (`localStorage`, confort par navigateur, jamais une autorité). Un relevé
   partiel affiche ses erreurs, ne peut pas être appliqué, et le dernier relevé réussi reste affiché et stocké.

Le fichier du registre éditorial (`machineWorkboardRegister.ts`) n'est jamais réécrit par la synchro : il change par PR.

## Quatre statuts séparés

| Piste | Origine | Jamais déduit de |
|---|---|---|
| Statut GitHub | observé (issue, PR brouillon/ouverte/fusionnée/fermée, CI au HEAD) | — |
| Intégration source | registre (`integration`) | l'état GitHub |
| Déploiement VPS | registre (`deployment`) | une fusion, la CI |
| Certification | registre (`certification`) | une issue fermée, un label |

Absent du registre = « Non renseigné » (jamais un zéro ni un vert implicite). Les valeurs ajoutées ne reprennent que ce que
le texte du registre affirmait déjà (11 intégrations source plus U7, 4 certifications, 1 non-installation).
« Aucun contrôle » ≠ « succès » ; une CI non lue reste `UNKNOWN`.

## Rapprochement explicite

Mission ↔ GitHub uniquement par les numéros `issue` et `pr` du registre. Aucun « closes #n », aucun label, aucune lecture
de description ou de commentaire. Les objets ouverts qu'aucune mission ne cite sont listés, pas ajoutés.

## Évaluation de l'accès sans authentification

- Dépôt public, CORS ouvert (`Access-Control-Allow-Origin: *`), pas de CSP sur l'unité web : les appels navigateur passent.
- Coût estimé : ~450 objets → 5 pages d'issues, 1 page de PR ouvertes, 1 GET par PR citée non ouverte (~13), 1 lecture de
  check runs par HEAD (~15-20), labels et jalons : **≈ 40-45 requêtes** par relevé complet.
- Limite anonyme : **60 requêtes/h par IP**. Un relevé en consomme les trois quarts ; un second relevé dans l'heure est refusé.
- Garde-fous : `/rate_limit` (non décompté) est lu avant tout ; sous 12 requêtes restantes ou si le coût des détails dépasse
  le quota, rien n'est dépensé. Budget dur 55 requêtes, 10 pages max par liste, arrêt net à un 403/429 épuisé.
- Verdict : **suffisant pour un usage ponctuel par une personne ; fragile** (IP partagée, relevés répétés).
  Le bac à sable de développement passe par un proxy authentifié (quota 15000) : la limite anonyme n'a donc **pas** été
  mesurée en conditions réelles, seulement lue dans la documentation GitHub.
- Palier suivant si besoin : route serveur GET-only avec jeton fine-grained lecture seule gardé côté serveur, cache ETag.
  **Non implémenté ici** (il touche l'unité web/VPS, donc une gate distincte).

## Erreurs visibles, jamais de faux succès

`NETWORK`, `RATE_LIMITED`, `RATE_LIMIT_INSUFFICIENT`, `HTTP_ERROR`, `INVALID_RESPONSE`, `TRUNCATED`, `BUDGET_EXCEEDED`,
`CHECKS_MISMATCH`, `ABORTED`. Un 404 sur une PR citée est un constat (« introuvable »), pas un échec.
Titres et labels GitHub sont du texte affiché échappé (React), jamais interprété ni suivi.

## Limites connues

- Une PR qui change de HEAD pendant le relevé n'est vue qu'au relevé suivant.
- Le stockage est par navigateur : pas de snapshot partagé entre appareils.
- Le registre actuel dit encore « non déployé » pour le frontend alors qu'il a été activé le 2026-10-14 : la synchro montre
  l'écart GitHub/registre, elle ne le corrige pas. Mettre à jour le registre est une PR éditoriale séparée.
- Les captures de `captures/` utilisent un **GitHub simulé** (interception réseau) : aucune preuve runtime ni VPS.

## Vérification locale

`npx tsc --noEmit`, `npx vitest run` (398 passent), `npm run build`, `pytest tests/test_workboard_frontend_release.py` (9 passent).
Tests : `src/test/githubRoadmapSync.test.ts` (lecteur, rapprochement, différences, stockage) et
`src/test/MachineWorkboardGithubSync.test.tsx` (parcours UI). `src/test/githubFake.ts` simule l'API.
