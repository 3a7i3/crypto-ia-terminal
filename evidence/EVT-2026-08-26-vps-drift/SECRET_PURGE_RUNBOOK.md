# Runbook — rotation + purge du token Dash0

> Secret exposé : `AUTH_TOKEN` Dash0 dans `.claude/settings.local.json`, mergé
> dans `main` via PR #54 (`6b9902a`). Introduit initialement par `6cc645b`.
> Gestes destructifs (réécriture de `main`) : **opérateur uniquement**.

## Ordre impératif — rotation AVANT purge

Tant que le token n'est pas révoqué, il reste récupérable depuis la PR #54, les
forks, les clones et les caches GitHub. **La purge d'historique seule ne protège
rien.** Rotationner d'abord.

### 1. Rotation (console Dash0) — à faire en premier
- Révoquer / régénérer `auth_0OVEaSMg27…(voir Dash0)` dans Dash0.
- Placer le nouveau token hors Git : variable d'environnement ou `.claude/settings.local.json`
  **local et gitignoré** (fait sur la branche d'audit : le fichier est untracked +
  listé dans `.gitignore`).

### 2. Untrack + gitignore (fait sur `claude/vps-git-runtime-audit-yae8f5`)
- `git rm --cached .claude/settings.local.json`
- entrée `.gitignore` ajoutée.
- Empêche toute réintroduction future ; ne nettoie pas l'historique passé.

### 3. Purge d'historique (opérateur — réécrit `main`, force-push)
Une fois le token révoqué (étape 1) :
```
# sauvegarde d'abord
git clone --mirror git@github.com:3a7i3/crypto-ia-terminal.git backup-before-purge.git

# purge le fichier de tout l'historique (git-filter-repo recommandé)
git filter-repo --path .claude/settings.local.json --invert-paths

# ou, si le fichier doit rester non-suivi mais nettoyé de l'historique :
#   BFG:  bfg --delete-files settings.local.json
git push --force --all
git push --force --tags
```
- Prévenir les collaborateurs : tout clone existant doit être re-cloné (les SHA changent).
- Les refs de PR GitHub (`refs/pull/54/*`) peuvent conserver le blob côté GitHub —
  la rotation (étape 1) est ce qui neutralise réellement le risque.

### 4. Vérification post-purge
```
git log --all --oneline -- .claude/settings.local.json   # doit être vide
git grep -n "auth_0OVEaSMg27" $(git rev-list --all)       # doit ne rien retourner
```
