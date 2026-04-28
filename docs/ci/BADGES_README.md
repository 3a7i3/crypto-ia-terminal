# Badges à ajouter en haut de votre README.md

## GitHub Actions (statut CI)

![CI](https://github.com/<user>/<repo>/actions/workflows/ci.yml/badge.svg)

## Codecov (couverture)

[![codecov](https://codecov.io/gh/<user>/<repo>/branch/main/graph/badge.svg)](https://codecov.io/gh/<user>/<repo>)

## GitLab CI (statut pipeline)

[![GitLab CI](https://gitlab.com/<user>/<repo>/badges/main/pipeline.svg)](https://gitlab.com/<user>/<repo>/pipelines)

---

Remplacez `<user>` et `<repo>` par vos identifiants GitHub ou GitLab.

Pour activer Codecov :
- Créez un compte sur https://codecov.io/ et connectez votre repo.
- Ajoutez le job `codecov/codecov-action@v4` dans GitHub Actions, ou `bash <(curl -s https://codecov.io/bash)` dans GitLab.
- Le badge s'active automatiquement après le premier push de couverture.
