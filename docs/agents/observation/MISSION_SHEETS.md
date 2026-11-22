# Famille Observation — fiches de mission et frontières

Statut : **fiches seulement**. Aucun des trois profils ci-dessous n'a de banc, de runner
ni de liaison serveur ; une mission qui les vise est refusée `BLOCKED
AGENT_NOT_QUALIFIED_FOR_BENCH` par [`contract.py`](../../../agent_bench/observation/contract.py).
Contrat commun : [AGENT_OBSERVATION_MISSION_V1](../../contracts/AGENT_OBSERVATION_MISSION_V1.md).
Profils lus à `857404f8` ; leurs fichiers `.agent.md` ne sont pas modifiés (blobs vérifiés
par le registre #597).

## 0. Frontières de la famille

| Question | Propriétaire unique | Les autres… |
|---|---|---|
| D'où vient **un dataset**, qui l'écrit, qui le lit, comment le joindre, est-il frais ? | `data-provenance-auditor` | citent son rapport, ne refont pas la chaîne |
| Que **mesure** une métrique affichée, où est-elle calculée, quelle est sa source de vérité, est-elle dupliquée ? | `observability-cartographer` | — |
| **Qu'existe-t-il** dans une zone du dépôt à un SHA : modules, symboles, appels, états persistants, flags, tests ? | `repository-cartographer` | — |
| **Qu'est-ce qu'un changement proposé toucherait**, et quels risques d'architecture introduit-il ? | `repo-architect` | — |

Règle de non-duplication : un profil qui a besoin d'un fait appartenant à un autre le
reçoit **en entrée** (rapport scellé + `content_sha256`), il ne le recalcule pas.

### Chevauchement repository-cartographer / repo-architect — frontière proposée

Constat (lecture intégrale des deux profils) : tous deux « cartographient » modules,
dépendances, points d'entrée, tests et code legacy ; tous deux sont lecture seule ;
`repo-architect` n'a ni `tools` ni front matter fermé (`REVIEW_REQUIRED`, A0 §16 I3) et
renvoie vers des profils « Test Engineer » qui n'existent pas.

Proposition (à valider par Mathieu avant toute fonction) :

- **repository-cartographer = descriptif.** Entrée : SHA + zone (`read_paths`). Sortie :
  graphe `CALLS/READS/WRITES/IMPORTS/CONFIGURES` prouvé, états persistants, flags, tests.
  Ne juge pas un changement.
- **repo-architect = prospectif, sans extraction propre.** Entrée **obligatoire** : un
  rapport `repository-cartographer` scellé du même SHA + un diff ou une mission
  candidate. Sortie : maillons touchés, frontières Research/PAPER/Live franchies,
  autorités concernées (PPL/FIN/#286), risques, tests manquants. Il ne parcourt pas le
  dépôt lui-même ; s'il manque un fait, il le liste comme inconnue à demander au
  cartographe.
- Alternative si la valeur prospective n'est pas voulue : **retirer** `repo-architect`
  (classification `ARCHIVE`, CLAUDE.md §5) et garder un seul cartographe. Ne pas créer
  deux fonctions d'extraction.

## 1. observability-cartographer

- **Classe/niveau envisagés** : `SENSOR` F0 (A0 inventaire).
- **Question bornée V1** : pour **une** surface opérateur (une vue ou un message) et
  ses métriques affichées, établir `source de vérité → calcul canonique → présentation`,
  avec formule, unité, numérateur/dénominateur, sémantique null/0/périmé.
- **Entrées** : contrat commun + `surface_id` (fichier de vue ou renderer) + rapport
  `data-provenance-auditor` des datasets lus par la surface.
- **Sorties propres** : `metric_id`, classification (`CANONICAL_EXISTING`,
  `PRESENTATION_ONLY`, `DUPLICATED`, `DERIVED`, `SOURCE_UNRESOLVED`…), constats
  `DUPLICATED_CALCULATION`, `NULL_ZERO_AMBIGUITY`, `LABEL_SOURCE_MISMATCH`.
- **Hors périmètre** : chaîne d'un dataset (déléguée), cycle de vie des messages Telegram
  et `message_id` (exige une observation runtime : mission séparée), bots dont le code
  n'est pas dans le dépôt.
- **Critères propres d'acceptation (banc futur)** : fixtures avec (a) métrique calculée
  deux fois avec deux formules, (b) frontend qui recalcule un PnL (interdit CLAUDE.md §1),
  (c) `null` affiché `0`, (d) label sans source, (e) métrique sans unité ; aucun faux
  `CANONICAL_EXISTING`.
- **Dépendance** : pilote DPA recevable.

## 2. repository-cartographer

- **Classe/niveau envisagés** : `SENSOR` F0.
- **Question bornée V1** : pour une zone (≤ 30 fichiers), produire le graphe des
  relations prouvées et la liste des points d'entrée, états persistants, flags et tests,
  avec `DEFINED ≠ INSTANTIATED ≠ CALLED ≠ DECISION_ACTIVE`.
- **Entrées** : contrat commun + `zone` = `read_paths` ; `question.kind` futur
  `REPOSITORY_MAP`.
- **Sorties propres** : arêtes `{from, to, relation, evidence}` ; nœuds classés
  (`ENTRYPOINT`, `CANONICAL`, `ADAPTER`, `LEGACY`, `UNREACHABLE`, `INCONCLUSIVE`…) ;
  bypass/fallbacks détectés.
- **Hors périmètre** : jugement d'un changement (repo-architect), statut runtime d'un
  module (mission VPS séparée).
- **Critères propres (banc futur)** : fixtures avec import non appelé, appel via
  fallback, deux producteurs d'un même fichier, module importé seulement par des tests,
  flag lu sur un seul chemin ; un module n'est jamais `CALLED` parce qu'il existe.
- **Réutilisation** : `agent_bench/observation/source_index.py` couvre déjà
  imports/écritures/lectures/routes ; à étendre plutôt qu'à dupliquer.

## 3. repo-architect

- **Préalable** : décision sur la frontière ci-dessus ; réécriture du profil (front
  matter fermé, `tools: ["read","search"]`, verdicts non auto-certifiants) par PR humaine.
- **Classe/niveau envisagés** : `SENSOR` F0 (la proposition de spécification relèverait
  de F2 `SCOPE_DRAFT_PREPARE`, non admis ici).
- **Question bornée V1** : « ce diff touche-t-il une autorité ou une frontière gelée ? »
- **Entrées** : contrat commun + rapport `repository-cartographer` scellé (même SHA) +
  diff (`git:commit:<sha40>` ou patch avec empreinte).
- **Sorties propres** : `touched_components`, `boundaries_crossed`
  (Research/PAPER/Live, PPL/FIN, #286), `risks`, `missing_tests`, inconnues.
- **Critères propres (banc futur)** : diff inoffensif (aucune frontière), diff touchant
  un seuil gelé, diff qui ajoute un lecteur frontend recalculant une valeur, diff hors
  zone cartographiée ⇒ `INCONCLUSIVE` et non « sans risque ».

## 4. Ordre conseillé

1. `repository-cartographer` — fondation statique, réutilise l'index du pilote,
   fixtures faciles à prédéfinir.
2. `observability-cartographer` — consomme DPA et le cartographe ; partie Telegram
   limitée au code source.
3. `repo-architect` — seulement après la décision de frontière (ou archivage), car il
   consomme le rapport du cartographe.
