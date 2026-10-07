# Historique comptable PPL — préparation source

Base : main@7638475dc1a18340c252cb1ce7bfdc143297c601.

Le contrôle opérateur du 7 octobre 2026 expose un préfixe de 171 événements
contigus de BURN-IN-EPOCH-01-20260926T064144Z : 86 ouvertures, 84 fermetures et
une création. Le manifeste v3 confirme le schéma événementiel v2, le code
116634be0d3c015cce1cfa58be7da7255414fbfd et la configuration gelée.
Ce contrôle ne fournit pas les octets complets du snapshot à la revue locale.

## Frontière

Le producteur offline reçoit une capture du comparator validée et le manifeste,
rejoue chaque préfixe avec le projecteur PPL existant et publie un artefact distinct.
Il ne construit aucun runtime, store ou client exchange. Il ne modifie aucun
calcul PPL, ne charge aucune configuration secrète et refuse les sorties dans
/home/mathieu/crypto_ai_terminal. Pas de collecteur, cron ou boucle automatique.
Les fichiers producteurs sont lus une fois par invocation explicite.

L'API GET /api/operator/v1/ppl-accounting-history lit seulement cet artefact.
Variable : PPL_ACCOUNTING_HISTORY_PATH ; défaut :
/opt/crypto-ai-terminal/operator/presentation/ppl_accounting_history.json.
Elle n'importe ni le producteur, ni le projecteur. 503 en l'absence d'artefact
ou si son contrat est invalide. Age calculé depuis la source, jamais depuis
l'heure de replay. Aucun cache de données runtime ni fallback synthétique.

## Sémantique

- Résultat réalisé cumulé : modèle PPL v2 float, après frais d'entrée/sortie.
- Disponible : cash du projecteur, sans prétendre à une valorisation de portefeuille.
- Répartition : disponible + principal réservé + principal non résolu au coût.
  Dénominateur et parts calculés par le producteur, pas par React. Le capital
  non résolu n'est pas une valeur économique certifiée récupérable.
- Unité : unité comptable PAPER. Aucune conversion USD/USDT/USDC supposée.
- Aucune courbe de marché, funding, equity ou performance Research inventée.

Le mode AUTHORITY_STATUS ne publie pas de checkpoint comptable indépendant :
replay_validated=true, checkpoint_verified=false. DERIVED_OBSERVATION n'est pas
FINANCIAL_OBSERVATION ni une certification FIN. L'artefact comporte hashes des
captures, SHA producteur, SHA epoch, config, séquence et référence de chaque point.
Un préfixe historique, même reconstruit aujourd'hui, reste daté de sa source.

Contrat v1 borné à 1000 événements/2 MB. Gap, duplication, mismatch manifest,
autorité non établie, timestamp régressif ou futur : échec fermé. Les points
sont tracés en escalier aux événements, sans bougies ou interpolation de prix.
Une observation unique est un point. La table exacte et les preuves restent
repliables. Les sources FIN d'autres epochs ne sont jamais fusionnées.

## Avant déploiement

La préparation locale utilise des fixtures exclusivement synthétiques.
Exécuter le producteur sur les fichiers réels du VPS dans un clone isolé propre,
avec sortie staging distincte ; examiner le résultat avant toute publication.
L'ancienne API du VPS reste inchangée : ce code n'est pas déployé par cette PR.
La migration de l'API nécessitera son venv distinct, les chemins absolus de toutes
les sources, un préflight, le backup des unités et un rollback Operator.
Advisor, checkout, epoch et configuration doivent rester inchangés.

La source n'ajoute pas de producteur pour les fichiers Burn-in, Runtime Service
et Research absents. Les endpoints récents resteront honnêtement 503 sur ces
sources absentes. Le laboratoire historique attend des évaluations versionnées.
Aucune certification U8 ou L4 n'est émise.

## Vérifications locales

- Frontend : 420/420 tests, 32 fichiers, aucune omission.
- Python : 119/119 (11 nouveaux tests accounting, 12 comparator API, 96 cross-stack).
- Transport/PWA : 7/7.
- TypeScript et builds production/démonstration : PASS.
- Diff whitespace et compilation Python : PASS.
- Limite visuelle : téléchargement Chromium indisponible (archive vide/invalide),
  donc aucune nouvelle capture navigateur ne constitue une preuve dans cette revue.
- Pas de vérification sur les 171 événements réels : leurs octets n'ont pas été transmis.

Les modifications des tests de navigation attendent explicitement la septième
source indépendante, GET accounting-history. Les fixtures accounting sont
synthétiques et confinées au répertoire de tests.

## Correctifs après CI initiale

Le contrôle des routes Direction inclut la nouvelle source accounting et simule explicitement son absence (503). Le test de preuve Advisor périmée attend la résolution de la source. Les conteneurs Finance ont une largeur bornée pour éviter le débordement intrinsèque des piles imbriquées sur tablette. Les nouveaux fichiers Python sont formatés ; le lint baseline passe sans nouvelle violation. Les 420 tests frontend, les 11 tests accounting et le build production passent après ces correctifs. La validation visuelle CI reste à confirmer.

Le résultat staging transmis par l’opérateur pour les 171 événements indique replay_validated=true et checkpoint_verified=false, source datée 2026-10-07T23:29:51Z. Ce résultat n’est pas une certification financière indépendante.
