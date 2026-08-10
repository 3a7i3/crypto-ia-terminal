# Exemple de job GitHub Actions pour notifier sur Microsoft Teams après un build
# Ajoutez ce bloc à .github/workflows/ci.yml :
#
#   - name: Teams Notification
#     uses: skitionek/notify-microsoft-teams@v1
#     with:
#       webhook_url: ${{ secrets.TEAMS_WEBHOOK_URL }}
#       message: 'Build terminé : ${{ job.status }}'
#
# Pour GitLab CI, ajoutez un job avec curl :
#   script:
#     - 'curl -H "Content-Type: application/json" -d "{\"text\":\"Build terminé : $CI_JOB_STATUS\"}" $TEAMS_WEBHOOK_URL'
