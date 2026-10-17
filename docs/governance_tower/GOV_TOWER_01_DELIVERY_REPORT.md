# GOV-TOWER-01 — Rapport de livraison (source seulement)

Mission : [#461](https://github.com/3a7i3/crypto-ia-terminal/issues/461) · Garde
[#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) ACTIVE · Date : 2026-10-17.

**Verdict : `GOV_TOWER_01_SOURCE_IMPLEMENTED_READY_FOR_INDEPENDENT_REVIEW`** pour la source,
sous réserve de la CI au SHA exact de la PR brouillon. Aucune preuve réelle (GitHub, VPS,
modèle) n'est apportée : voir § 4.

| Gate | Verdict |
|---|---|
| GT01_SOURCE_READY_FOR_REVIEW | OUI (§ 2, § 3) |
| GT01_LIVE_GITHUB_PROVEN | **NOT_PROVEN** (§ 4) |
| GT01_LIVE_VPS_PROVEN | **NOT_PROVEN** |
| GT01_LLM_ADAPTER_TESTED_OFFLINE | OUI (42 tests) |
| GT01_LLM_LIVE | **DISABLED** |
| GT01_RUNTIME_DEPLOYED | **FALSE** |
| GT01_OPERATIONAL_AUTHORITY | **DENIED** |
| ACTIVE_BURN_IN_IMMUTABILITY_GUARD | ACTIVE (inchangé) |
| GATE_O | OPEN (inchangé) |

## 1. Base, branche et fichiers touchés

- Base : `main` @ `191ffce9c677bcea3c5e970666ead09b7c2760cf` (fusion #460).
- Branche : `claude/gov-tower-01-real-observability-doqneu`. SHA de livraison : celui du commit
  qui introduit ce rapport (voir la PR brouillon) ; la CI fait foi à ce SHA.
- Aucun fichier hors `governance_tower/`, `tests/governance_tower/`, `docs/governance_tower/`
  et `scripts/governance_tower/` n'est modifié. Aucun workflow, aucune unité, aucune dépendance.

| Fichier | Nature |
|---|---|
| `governance_tower/contracts.py` | EXTEND : domaines, intentions, `Diagnostic`, `CodeExcerpt` |
| `governance_tower/coverage.py` | NEW : cartographie déclarée (17 domaines) |
| `governance_tower/providers/github.py` | EXTEND : 5 lectures ciblées + `budget_status` |
| `governance_tower/providers/host.py` | EXTEND : identité d'hôte, monotonicité, en-têtes |
| `governance_tower/scenarios.py`, `fixtures/github/*`, `fixtures/host/*` | EXTEND : 3 scénarios SYNTHETIC |
| `governance_tower/sentinel/{policy,tools,agent,analysis,reasoner}.py`, `__main__.py` | EXTEND : intentions, diagnostics, rendu |
| `governance_tower/sentinel/llm_adapter.py` | NEW : adaptateur hors ligne |
| `governance_tower/server.py` | EXTEND : `/api/status` (raisonneur, modèle externe, budget) |
| `governance_tower/ui/{app.js,styles.css,sample_run.json}` | EXTEND : diagnostics, extraits, bandeaux |
| `tests/governance_tower/test_gt01_*.py` (5) | NEW : 191 tests |
| `tests/governance_tower/test_gt_{github_provider,scenarios,ui_static}.py` | EXTEND |
| `scripts/governance_tower/gt01_ui_e2e.mjs` | NEW : parcours navigateur |
| `docs/governance_tower/GOV_TOWER_01_*.md`, `GT01_*.md`, `RUNBOOK_LOCAL.md`, `REUSE_MATRIX.md`, `screenshots/gt01_*` | docs |

## 2. Matrice des missions

| Mission | État | Livré |
|---|---|---|
| M0 inventaire, contrats | DONE | [GOV_TOWER_01_ARCHITECTURE.md](GOV_TOWER_01_ARCHITECTURE.md), contrats étendus, `coverage.py` |
| M1 lecteur GitHub | DONE (source) | fichier par SHA avec empreinte Git, issue, PR, CI par SHA, branche, budget ; preuve réelle NOT_PROVEN |
| M2 snapshots VPS | DONE (synthétique) | contrôles d'identité, rejeu, en-têtes ; [protocole GT01-V](GT01_V_VPS_READ_PROTOCOL.md) non exécuté |
| M3 diagnostics croisés | DONE | 16 codes, observation → interprétation → vérification → proposition |
| M4 contrat LLM | DONE (hors ligne) | [GT01_LLM_CONTRACT.md](GT01_LLM_CONTRACT.md) ; aucun transport réel |
| M5 UI à un panneau | DONE | cartes de diagnostic, extraits numérotés, bandeau des sources, preuves repliées, budget ; aucun menu ni bouton nouveau |
| M6 sécurité, régression, E2E, rapport | DONE | § 3, § 5, [matrice de tests](GOV_TOWER_01_TEST_MATRIX.md) |

Parallélisme : M1, M2 et M4 partagent `contracts.py`, `agent.py` et `reasoner.py` ; ils ont été
intégrés séquentiellement par un seul intégrateur sur une seule branche, sans worktrees parallèles.

## 3. Tests réellement exécutés (2026-10-17, conteneur de développement)

Versions : Python 3.13, pytest 9.1.1, ruff 0.16.8 (la CI épingle 0.15.8), Node 22.22.0,
Playwright 1.56.1 / Chromium 1194. Dépendances : `requirements-ci.txt` sauf `ta` (ne compile
pas dans ce conteneur ; aucun test collecté n'en dépend ici).

| Contrôle | Base `191ffce` | Branche | Écart |
|---|---|---|---|
| `pytest -q -m "not performance and not slow" tests/` | 8045 passed, 20 skipped, 2 xfailed, 1 failed | **8245 passed**, 20 skipped, 2 xfailed, 1 failed | +200 réussis, aucun nouvel échec |
| `pytest -q tests/governance_tower` (root) | — | 588 passed, 1 failed | — |
| `pytest -q tests/governance_tower` (utilisateur non-root `nobody`) | — | **589 passed** | — |
| `scripts/ci/ruff_baseline_gate.py check` | — | 0 nouvelle violation (945 ≤ 957) | — |
| `node --check governance_tower/ui/app.js` | — | OK | — |
| `git diff --check` | — | OK | — |
| E2E navigateur `gt01_ui_e2e.mjs` | — | **29 / 29** | — |

L'unique échec, identique sur la base, est
`test_gt_host_provider.py::test_snapshot_permission_denial_is_not_a_missing_source` : le test
retire les droits de lecture d'un fichier, ce que root ignore. Il passe en non-root (ligne ci-dessus).
Aucun test n'a été supprimé, ignoré ni affaibli ; aucune baseline n'a été modifiée.

Défauts trouvés et corrigés par les nouveaux tests : expurgation appliquée deux fois dans
l'adaptateur (le secret d'une question n'était plus détecté) ; « relance la CI » n'était pas
refusé ; « Le VPS exécute-t-il la même version que GitHub ? » était routé vers l'hôte seul.

Captures (390 et 1440 px) : `docs/governance_tower/screenshots/gt01_*.png`. En capture pleine
page, le formulaire collant se superpose au contenu : artefact de la capture, pas du rendu.

## 4. Preuves LIVE_READ (séparées des fixtures)

**Aucune.** Tout ce qui précède est SYNTHETIC.

- GitHub (GT01-G) : une seule requête de sondage a été envoyée, sans jeton de l'environnement
  (`env -u GH_TOKEN -u GITHUB_TOKEN`), le 2026-10-17 à 03:40:02 UTC :
  `GET https://api.github.com/repos/3a7i3/crypto-ia-terminal` → `200`,
  `X-RateLimit-Limit: 15000`. Une lecture anonyme donnerait `60` : le proxy sortant de ce
  conteneur authentifie les requêtes avec une identité qui n'est ni celle de Sentinel ni une
  identité contrôlée par Mathieu. Le smoke-test n'a donc **pas** été exécuté via
  `HttpGithubProvider` : `GT01_LIVE_GITHUB_PROVEN = NOT_PROVEN`.
- VPS : aucune lecture. Aucun outil d'accès distant n'a été utilisé.
- Modèle : aucun appel.

## 5. Sécurité

Menaces testées : traversée et chemins sensibles (avant requête), binaires et clés privées,
réponses GitHub forgées (chemin, type, empreinte, base64), redirections, quotas, fuite du jeton,
injection d'instructions dans fichier/issue/PR/titres (citée, jamais suivie), XSS
(`<script>`, `<img onerror>` affichés comme texte en navigateur réel, aucune boîte de dialogue),
snapshot rejoué ou d'un autre hôte, Content-Type inattendu, horloge future, sortie de modèle
hostile (balisage, demande d'outil, revendication d'action/autorité/santé, secret, caractères
de contrôle, preuve inventée ou VPS non admise), requêtes d'écriture (relance CI, fermeture,
commentaire, approbation, merge).

Non résolu :

- La détection d'instructions est lexicale : une formulation nouvelle peut passer ; elle reste
  sans effet sur les outils (aucun outil d'écriture n'existe).
- Le snapshot `storage` ne publie pas `host_id` : son rattachement à l'hôte n'est pas vérifiable.
- Le hash de configuration runtime n'est publié par aucun snapshot : `NON VÉRIFIÉ`.
- En démo, l'âge de la bannière compare les fixtures figées à l'horloge réelle (VPS « Périmé »)
  alors que les diagnostics suivent l'horloge des fixtures.
- Le parcours E2E n'est pas exécuté par la CI.

## 6. Coûts et données qui iraient à un modèle

Coût réel : **nul** (aucun appel). Estimation hors ligne : ≈ 1 800 jetons d'entrée pour la
question de version sur le scénario nominal (1 jeton ≈ 3 caractères, non mesuré), plafonds
6 000 en entrée et 1 200 en sortie. Données : observations GitHub expurgées, diagnostics,
référence #286 déclarée ; observations VPS **retenues par défaut**. Détail :
[GT01_LLM_CONTRACT.md](GT01_LLM_CONTRACT.md).

## 7. CI

Voir la PR brouillon : la CI au SHA exact de sa tête fait foi ; ce rapport ne la présume pas.

## 8. Approbations nécessaires (par priorité)

1. **GT01-V, lecture VPS réelle** : autoriser une exécution unique du
   [protocole](GT01_V_VPS_READ_PROTOCOL.md) via un tunnel que vous ouvrez.
2. **Identité GitHub de Sentinel / GitHub App** : création par vous ; ensuite seulement, un
   smoke-test daté avec cette identité (`GT_GITHUB_TOKEN` côté serveur, lecture seule).
3. **GT01-I, modèle externe** : choix du modèle, des données (VPS ou non), du budget et des
   tests adversariaux réels.
4. **GT01-R, authentification et exposition** : aujourd'hui loopback seul, sans authentification.
5. **Release** : revue indépendante, fusion de la source, puis décision distincte de publication.
