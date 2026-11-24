# CAT R0 — Contre-revue de la PR #607 (Radar)

2026-11-24 · HEAD `d8edf17` · branche `claude/project-thread-dg0k91` · lecture et exécution locales SYNTHETIC uniquement, aucune modification de code.

## Verdict

**GO pour Ready for review** après correction de R1 (option A retenue par l'opérateur, `radar-ranking/1.1.0`, test C11). Verdict initial : NO-GO levable par R1.
Le reste (isolation, absence d'autorité, CI) est conforme. La réserve R1 touche
l'invariant `UNKNOWN ≠ 0` dans le classement des candidats.

## 1. Scores INCOMPLETE et leur lecture

Constat (`selection.py:157-190`) : un composant inconnu (L2, spread, activité,
coût) ne rapporte aucun point ; le score devient `INCOMPLETE` avec `missing` et
`max_reachable`. Le classement (`select_candidates`) trie ensuite sur la valeur
brute, sans distinguer COMPLETE et INCOMPLETE.

Mesure sur les 4 univers :

| Univers | Marchés INCOMPLETE | Candidats proposés |
|---|---|---|
| calm | 19 (L2 manquant, max 85) | 1 COMPLETE (94), 2 INCOMPLETE (82, 64.50) |
| volatile | 17 | 1 COMPLETE, 2 INCOMPLETE |
| gaps | 6 (dont `mexc:spot:BTC/USDT` : coût + L2 manquants, max 75) | 1 COMPLETE, 2 INCOMPLETE |
| incoherent | 3 | 3 INCOMPLETE, aucun COMPLETE |

**R1 (bloquant)** : dans le classement, un composant inconnu pèse comme 0. Un
marché COMPLETE à 80 passe derrière un INCOMPLETE à 82, et un INCOMPLETE est
pénalisé de façon arbitraire par rapport à un autre selon ce qui manque. C'est
`UNKNOWN = 0` appliqué au rang, même si l'état reste visible.

Consommateurs : aucun module hors du paquet n'importe `radar_selection`
(grep du dépôt). Le terminal affiche `quality` et `max_reachable` dans `inspect`
et la qualité dans `candidates`, mais `status` affiche le score seul (R2,
mineur). L'export JSON porte tous les champs ; un futur consommateur qui lit
`score.value` seul fera la même confusion.

Options pour R1 (décision opérateur, pas une nouvelle fonctionnalité) :
- A. Classer COMPLETE avant INCOMPLETE, puis par valeur (petit correctif + test) — recommandé.
- B. Garder le tri, mais documenter dans le contrat que le rang est indicatif et que `quality` prime.
- C. Exclure les INCOMPLETE des candidats (univers `incoherent` → zéro candidat, raison explicite).

## 2. Frontière Radar → Admission scientifique → Observation approfondie

| Étage | Produit | Autorité | État dans le dépôt |
|---|---|---|---|
| Radar R0 | évaluation, 0 à 3 propositions `PROPOSED_NOT_AUTHORIZED` | aucune (`execution/collection/experiment_authority = false`) | livré (#607) |
| Admission scientifique (C2-C) | décision d'admission d'un marché à un dataset | gate humaine gouvernée | **non définie** dans le dépôt (seule C2-R existe, #604) |
| Observation approfondie (C2-D) | collecte L2/observation d'un marché admis | mission + gate distinctes | **non définie** |

Règles à acter dans le contrat avant tout étage suivant : (1) l'entrée d'C2-C
est l'export Radar figé par son `evaluation_sha256`, jamais un appel au Radar ;
(2) aucune transition automatique : chaque passage exige une décision humaine
traçable ; (3) un `UNKNOWN` Radar reste `UNKNOWN` en entrée d'admission ;
(4) la référence `kraken:spot:BTC/USDT` reste `NOT_YET_HISTORICALLY_ADMITTED`
tant que C2-C n'existe pas. Le contrat actuel (§ autorité, l. 220) dit déjà que
la proposition est soumise à C2-C/C2-D ; il ne définit pas ces gates et ne doit
pas le faire seul : C2-C et C2-D restent **UNKNOWN** jusqu'à leur spécification.

## 3. Réconciliation des tests

| Source | Résultat | Commentaire |
|---|---|---|
| Local 3.11, suite complète (avant correction E01) | 12 880 PASS, 3 FAIL | 2 quirks root (colony supervisor, gt_host_provider), sans lien R0 ; E01 échouait avant précision |
| Local 3.11 et 3.13, `tests/radar_selection` après correction | 71 PASS | E01 vert |
| CI GitHub sur `d8edf17` (définitif) | 28 checks : **26 success, 2 skipped, 0 échec** | TEST REGRESSION GATE, LINT, COVERAGE, CROSS-STACK, semgrep verts ; skipped : Walk-forward validation, publish-docs (conditionnels, normaux sur une PR) |

Les deux échecs root ne se reproduisent pas en CI (utilisateur non privilégié),
ce qui confirme leur nature d'environnement. La précision E01 s'est faite avant
le commit de validation ; elle ne masque pas une régression (la liste interdite
reste celle des modules de transport). Correction à porter au rapport de
validation : citer le résultat CI définitif ci-dessus.

## 4. Aucun déclenchement automatique

- `deep_observation_jobs` est un littéral `[]` (`engine.py:138`), sans producteur.
- Imports du paquet : bibliothèque standard + `scanner_universe.{catalogues,universe}` uniquement ; aucun appel replay, collecte, PAPER, PPL, FIN, Advisor.
- Hook d'audit : socket, DNS, subprocess, `os.system`, fork, écriture hors `--state-dir` refusés (E01, E05, E06).
- `select`/`pin` n'écrivent que `preferences.json` ; aucun consommateur ne les lit hors du Radar.
- Aucun workflow, cron ou unité ne référence `radar_selection`.

Conclusion : aucun chemin de code ne permet à un candidat de lancer une
collecte, un replay ou une expérience.

## 5. Pour lever le NO-GO

1. Décision sur R1 (A recommandé).
2. Mettre à jour le rapport de validation avec le §3 et le contrat avec les quatre règles du §2.
3. R2 (qualité affichée dans `status`) peut suivre dans le même commit.
