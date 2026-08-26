# Hygiène des secrets — repo public

Ce dépôt est **public**. Aucune clé, token ou credential ne doit jamais y être committé.

## Défenses en place

1. **`.gitignore`** exclut les fichiers à secrets : `.env`, `.env.*`, `*.env`,
   `secrets.*`, `*_secret*`, `*_credentials*`, et `.claude/settings.local.json`
   (fichier local de Claude Code — c'est là qu'un token Dash0 avait fuité, cf.
   `evidence/EVT-2026-08-26-vps-drift/`).
2. **Hook `gitleaks`** dans `.pre-commit-config.yaml` : **refuse** tout commit
   contenant un motif de clé/token. Contrairement à `bandit` (qui tourne en
   `--exit-zero` et ne bloque pas), gitleaks fait échouer le commit.

## Activation (obligatoire après un clone)

Le hook est dormant tant qu'il n'est pas installé localement :

```bash
pip install pre-commit
pre-commit install            # installe les hooks git
pre-commit run gitleaks --all-files   # scan complet immédiat (optionnel)
```

## Si un secret fuite malgré tout

Un secret poussé sur un repo public est **compromis définitivement** (caches
GitHub, forks, GH Archive, scanners tiers). La seule vraie parade :

1. **Révoquer / rotationner** le secret côté fournisseur — la suppression Git
   seule ne protège rien.
2. Retirer le fichier du suivi (`git rm --cached`) + confirmer le `.gitignore`.
3. Purge d'historique optionnelle (cf. `SECRET_PURGE_RUNBOOK` du bundle) —
   cosmétique une fois le secret déjà harvested ; la révocation prime.
