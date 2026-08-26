# EVT-2026-08-26-vps-drift

| Champ | Valeur |
|---|---|
| type | repository / runtime divergence + secret exposure |
| status | investigated (Git side) — VPS side pending |
| captured_from | conteneur cloud éphémère (clone frais de `origin/main`), pas le VPS |
| repo_head | `a8ca108` (merge PR #54 « chore: configure Dash0 plugin for observability ») |

## Résumé

Une campagne d'audit de « dérive Git/VPS » supposait qu'un commit `7254647c`
modifiant `core/advisor_loop.py` devait être autopsié (ADR-0007, passivité des
observers) avant merge. La vérification terrain contredit ce narratif sur trois
points, et révèle une exposition de secret non anticipée.

## Faits établis (côté Git, reproductibles depuis ce conteneur)

1. **`7254647c` n'existe dans aucun ref ni reflog.** Commit local au VPS, jamais
   poussé. Invisible et non-autopsiable depuis un clone GitHub. Preuve :
   `7254647c-absence-proof.txt`.

2. **Le Dash0 réellement mergé (PR #54, `6b9902a`) est un changement de config
   uniquement** : `.claude/settings.local.json`, +13 lignes, un seul fichier. Il
   **ne touche pas** `core/advisor_loop.py`. Preuves : `dash0-pr54-merged.stat.txt`,
   `dash0-pr54-6b9902a.patch` (token rédigé), `advisor_loop-history.txt` (dernier
   changement = `abb975c` / #42, sans rapport).

3. **Corollaire ADR-0007** : le verrou de passivité de `advisor_loop.py` visait un
   objet absent de Git. Ce qui est sur `main` est un fichier de settings d'outillage,
   pas du code runtime — passif par construction. Le doute de passivité réel, s'il
   existe, ne peut porter que sur le `7254647c` VPS-local, à traiter en session VPS.

4. **Exposition de secret (non anticipée, prioritaire)** : `settings.local.json`
   contient en clair un `AUTH_TOKEN` Dash0 et une cible SSH prod, et **n'était pas
   gitignoré**. Fichier introduit par `6cc645b` puis token par `6b9902a` (mergé main).

## Classification A/B/C/D

| Fichier / objet | Catégorie | Décision |
|---|---|---|
| `.claude/settings.local.json` | **D — DEBRIS** (config machine-locale committée par erreur, porte un secret) | untrack + gitignore (fait, cette branche) ; rotation token + purge historique (opérateur) |
| PR #54 `.claude/settings.local.json` diff | **B — RUNTIME/tooling** | conservé comme preuve rédigée dans ce bundle |
| `core/advisor_loop.py` | **A — PRODUCT** | non modifié — hors périmètre de cet incident |
| `7254647c` (VPS-local) | **UNKNOWN** | ni PRODUCT ni sûr tant que non capturé/autopsié depuis le VPS |

## Ce qui reste à capturer (nécessite le VPS, hors de ce conteneur)

Freeze runtime, fingerprint (`systemctl cat/show`, `/proc/<PID>/{cwd,exe,environ}`,
`python --version`, `pip freeze`, hashes des fichiers critiques), et l'autopsie de
`7254647c`. Aucune de ces étapes n'est exécutable depuis un clone GitHub.
