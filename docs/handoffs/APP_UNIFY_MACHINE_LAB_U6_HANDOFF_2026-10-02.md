# Machine / Laboratoire — reprise source U6

Parent #323 · tranche #338 · 2026-10-02 · #286 ACTIVE.
Branche `feat/app-unify-machine-lab-u6`, base
`de8281f3fa2a7994e2836b4139cc8457d389030a` (merge U4 #337).
La PR associée et son HEAD réel font foi : ne pas inférer une fusion ou un
déploiement depuis ce document. Aucun accès ni changement VPS dans cette tranche.

## Résultat

U4 #336/#337 a été stabilisé, son HEAD `01b8969c9dcf26532f57ead95c96ba8a4f6dd10c`
revérifié et fusionné. Avant fusion : 29 checks success, 2 skips Walkforwards,
aucun pending/failure, aucune revue/thread, base main U3b vérifiée, #286 ouvert.

La suite source implémente :

- l'inventaire transversal des capacités, consommateurs et manques, plus index
  AST de 913 fichiers Python / 8 342 déclarations à la base U4 ;
- deux espaces principaux, Machine → Direction et Laboratoire → Research ;
- anciens liens profonds/routes conservés, CryptoRadar identifié dans Machine ;
- contraste, textes, contrôles, cartes mobile Finance/Portfolio, lisibilité
  Scanner/LMI/burn-in, provenance repliable, suppression des requêtes de fonts ;
- décimales financières abrégées par manipulation des strings/BigInt, sans
  conversion de la valeur canonique en Number ; valeur exacte accessible ;
- un petit écart non nul devient `< 0,01` ou `> −0,01`, jamais un faux zéro ;
- domaine ResearchStrategyBoardSnapshot indépendant : sélection explicite →
  candidat/évaluation/assessment → builder passif → artifact atomique → GET →
  grille de critères/détail, avec rangs copiés dans leurs cohortes exactes ;
- vert/rouge/jaune/gris avec icône et texte, recherche/type/cohorte, raisons,
  N, force statistique, limites, identités et provenance au clic ;
- absence d'assessment ≠ vert implicite, résultat manquant ≠ catalogue vide,
  refresh en erreur ≠ conservation d'un faux état actuel.

Le contrat fermé est
[APP_UNIFY_RESEARCH_STRATEGY_BOARD_CONTRACT.md](../contracts/APP_UNIFY_RESEARCH_STRATEGY_BOARD_CONTRACT.md).
Le builder n'authentifie pas la certification déclarée et ne produit aucun
assessment scientifique. L'API lit seulement la projection. Aucun artifact
Research réel ou activation du registre n'est publié par cette tranche.

## Validation locale

- 132 tests Python : `tests/cross_stack/`, U4, WEB-RL et reader/API FIN ;
- 376 tests frontend avec fixtures cross-stack générées ;
- 7 contrats de transport local/PWA ; build TypeScript/Vite PASS ;
- Ruff baseline : 947 findings existants, zéro nouvelle violation ;
- grille Lab et Finance passent par les vrais publishers/producers/readers/API,
  avec entrées exclusivement synthétiques et clocks de fixture explicites ;
- preuve U6 aux largeurs 1440/820/390 : deux espaces, erreurs/vide, critères
  cliquables et focus, layout mobile, valeurs exactes FIN, zéro overflow et GET
  canonique uniquement. Captures complètes et de viewport dans les artifacts CI.
- preuve Direction mise à jour : l'en-tête défile avec le document et ne
  recouvre pas les titres après scroll ; aucun simple test de sticky conservé ;
- fixture candidate testée avec racines absolues et relatives, y compris le
  comportement différent de `mkdtemp` entre Python 3.11 et 3.12.

Commandes : générateurs `tests.cross_stack.generate_*` de la workflow
`machine-lab-u6-visual-proof.yml`, puis `npm run build`, `npx vitest run` et
`node scripts/capture_machine_lab_u6_visual.mjs` depuis `frontend/`.
Les tests avec fixtures sont également exécutés dans la gate cross-stack ;
la CI frontend sans fixtures les saute explicitement.
Les counts locaux ne remplacent pas la vérification des checks au HEAD réel.

## Suite

1. Reprendre la PR de #338, revérifier HEAD/main, checks, revues et threads
   avant sa fusion source ; pas de déploiement lié à cette fusion.
2. Compléter les manques CryptoRadar issus de
   [l'inventaire](../plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md), avec
   nouveaux profils d'observation explicites si nécessaires. Le endpoint ancien
   « events » décrit des états notables courants, pas un journal à reconstruire.
3. Faire admettre les vraies publications de candidats/évaluations/assessments
   par Research avant de montrer des résultats réels ou leurs classements.
   Sans source, la grille reste indisponible ou ses critères gris.
4. U8 : gate runtime distincte et identité de build/appareil ; ensuite retrait
   des anciennes surfaces seulement après parité, consommateurs et rollback.

#315 Gate O reste ouvert. Aucun changement runtime/VPS/Advisor/PPL/FIN/epoch/
config/risk/sizing/Watchdog/exchange, aucune commande de trading, relance de
moteur ou promotion de stratégie. Les preuves internes restent conservées.
