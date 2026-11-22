# Audit initial — famille Observation, pilote en banc isolé

Date : 2026-11-22. Nature : **audit source READ-ONLY**, aucune observation VPS.

## 1. Point de départ

| Élément | Valeur |
|---|---|
| SHA analysé | `857404f8ebfbcf9df4a3f36052ab5357ea9b8d7b` (tête de la PR #597, brouillon) |
| Empilement | #597 → #596 (`098304d9`) → #595 → #591 → `main@f52dbb5` |
| Branche de ce lot | `claude/project-thread-f7rql7`, créée **sur** `857404f8` ; la branche de #597 (`claude/project-thread-i3bh0g`) n'est pas modifiée |
| Changements en cours | arbre propre au départ ; ce lot n'ajoute que des fichiers nouveaux (`agent_bench/`, `tests/agent_bench/`, `docs/…`) ; aucun fichier de `.github/` ni de `frontend/` n'est modifié |

## 2. Lectures intégrales

- Profils : `.github/agents/data-provenance-auditor.agent.md` (180 l.),
  `observability-cartographer.agent.md` (173 l.), `repository-cartographer.agent.md`
  (189 l.), `.github/repo-architect.agent.md` (103 l.).
- Contrats : A0 Forest (562 l.), A1 Registry (674 l.), A1 Capability Catalog ;
  inventaires `AGENT_ECON_A0_GITHUB_AGENTS_INVENTORY.md` et
  `AGENTS_SYSTEM_CATALOGUE_2026-11-21.md` ; registre `agentIdentityRegistry.v1.json` (#597).
- Garde-fou #286 (état 2026-10-05) : « tests isolés » et « architecture contract-only »
  sont des travaux parallèles autorisés ; « agent runtime » reste interdit.

## 3. Faits

1. **Aucun runner** : les 4 profils sont `wiring_status: NOT_WIRED`, `runner_id: null`
   (registre #597). Aucun workflow, script, unité ni processus ne les référence (audit
   #596). Ce lot ne change pas ce fait.
2. **Les profils sont des prompts, pas du code.** Le « pilote » exécutable de ce lot est
   donc une **référence déterministe** qui applique la mission du profil
   `data-provenance-auditor` sous un contrat vérifiable. Il prouve le contrat et le banc ;
   il ne mesure pas la qualité d'un futur agent à modèle. Un runner futur devra produire
   des rapports au même format, jugés par le même banc.
3. A1 est `CONTRACT-ONLY / NON DÉPLOYÉ` ; aucun `AgentSpec` n'existe. Ce lot n'en crée
   pas et ne touche pas `docs/contracts/AGENT_ECON_*`. Le banc n'est ni worker, ni
   scheduler, ni provider (A0 §12, phase A6 non ouverte).
4. Version exacte d'un profil = blob git SHA-1 déjà vérifié par le test du registre
   #597 ; le contrat réutilise cette valeur (`profile.blob_sha1`).
5. `repo-architect` : front matter non fermé, aucun `tools`, renvoie vers des profils
   inexistants (`REVIEW_REQUIRED`, A0 §16 I3).

## 4. Preuves du dépôt ≠ observations VPS

Toutes les preuves de ce lot sont **source** (fichier, symbole, ligne, sha256) ou
**fixture**. Aucune ne dit qu'un service tourne, qu'une variable est configurée sur
l'hôte, ni qu'une collecte a eu lieu. Les observations VPS connues (collecte BBO du
2026-11-20, archives sur `~/cat-collect-bbo/`) ne sont **pas** relues ici et ne sont pas
utilisées comme preuve. La publication réelle du VPS n'est pas lue ; la capture du
pilote est la fixture synthétique versionnée.

## 5. Chevauchement repository-cartographer / repo-architect

Les deux profils décrivent la même extraction (modules, dépendances, points d'entrée,
tests, legacy). Frontière proposée (détail : [fiches](../agents/observation/MISSION_SHEETS.md)) :
le **cartographe décrit** ce qui existe à un SHA ; l'**architecte évalue** un changement
proposé en **consommant** le rapport du cartographe, sans extraction propre — ou
`repo-architect` est archivé. Aucune fonction n'est créée pour l'un ou l'autre avant
décision.

## 6. Dataset pilote retenu : `bbo-composite-history/1.0.0`

| Critère | Constat |
|---|---|
| Lié à la mission prioritaire (Market Radar Spot) | oui : vue « Composite historique » de `SpotRadarMap` |
| Chaîne complète en source | collecte `bbo_pilot.py` → construction `bbo_history.py` → fichier → `BboHistoryReader` → `GET /api/operator/v1/bbo-composite-history` → `bboHistoryClient.ts` → `BboCompositeHistory.tsx` → `SpotRadarMap.tsx` |
| Schéma versionné, validateur, tests | `validate_history`, `tests/radar_composite/test_bbo_history.py` (8 passés, 1 ignoré ici) |
| Capture sans VPS ni secret | fixture `observability/radar_composite/fixtures/bbo_composite_history_synthetic.json` |
| Taille bornée | 8 fichiers, ~170 Ko |
| Identifiants, unités, horodatages explicites | `pair`, `window.index/start_ms`, `*_ms` en epoch ms, `gap_max_bps` décimal, `generated_at_utc`, empreintes `events/frames/summary/window/archive_sha256` |

Écartés : ledgers PPL/FIN et datasets PAPER (autorités gelées #286, hors domaine d'un
agent A0 §9) ; Footprint (rejeu plus large, plusieurs producteurs).

## 7. Inconnues au départ

- Le fichier lu par l'Operator API (`OPERATOR_BBO_HISTORY_PATH`) est-il celui écrit par
  `bbo_history build --out` ? (non prouvable en source)
- La publication réelle est-elle installée sur l'hôte ? (non observé dans ce lot)
- Les journaux amont (`events.jsonl`, ouverts en ajout) contiennent-ils des rejeux ?

## 8. Écart avec le périmètre

Aucun écart matériel : #286 autorise tests isolés et architecture contract-only ; aucun
runner, aucun déploiement, aucun accès VPS. Le travail a donc enchaîné sans attendre.
