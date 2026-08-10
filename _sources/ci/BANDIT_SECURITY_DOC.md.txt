# Bandit security scan job for GitHub Actions
# Ajoutez ce job à .github/workflows/ci.yml :
#
#   - name: Security scan (bandit)
#     run: |
#       pip install bandit
#       bandit -r .
#
# Pour GitLab CI, ajoutez dans .gitlab-ci.yml :
#
# security:
#   stage: test
#   script:
#     - pip install bandit
#     - bandit -r .
#
# Le pipeline échouera si des vulnérabilités critiques sont détectées.
