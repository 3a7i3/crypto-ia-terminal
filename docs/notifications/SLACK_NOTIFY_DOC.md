# Exemple de job GitHub Actions pour notifier sur Slack après un build
# Ajoutez ce bloc à .github/workflows/ci.yml :
#
#   - name: Slack Notification
#     uses: slackapi/slack-github-action@v1.25.0
#     with:
#       payload: '{"text":"Build terminé : ${{ job.status }}"}'
#     env:
#       SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
#
# Pour GitLab CI, ajoutez un job avec curl :
#   script:
#     - 'curl -X POST -H "Content-type: application/json" --data "{\"text\":\"Build terminé : $CI_JOB_STATUS\"}" $SLACK_WEBHOOK_URL'
