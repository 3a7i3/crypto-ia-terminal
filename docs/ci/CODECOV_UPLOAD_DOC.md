# GitHub Actions job to upload coverage to Codecov
# Ajoutez ce bloc à .github/workflows/ci.yml après les tests :
#
#   - name: Upload coverage to Codecov
#     uses: codecov/codecov-action@v4
#     with:
#       token: ${{ secrets.CODECOV_TOKEN }}
#       files: ./coverage.xml
#       fail_ci_if_error: true
#
# Pour générer coverage.xml, ajoutez à la commande pytest :
#   pytest --cov=. --cov-report=xml
#
# Pour GitLab CI, ajoutez :
#   script:
#     - pytest --cov=. --cov-report=xml
#     - bash <(curl -s https://codecov.io/bash)
