# Exemple de job GitHub Actions pour notifier sur Discord après un build
# Ajoutez ce bloc à .github/workflows/ci.yml :
#
#   - name: Discord Notification
#     uses: Ilshidur/action-discord@v2
#     with:
#       webhook_id: ${{ secrets.DISCORD_WEBHOOK_ID }}
#       webhook_token: ${{ secrets.DISCORD_WEBHOOK_TOKEN }}
#       message: 'Build terminé : ${{ job.status }}'
#
# Pour GitLab CI, ajoutez un job avec curl :
#   script:
#     - 'curl -H "Content-Type: application/json" -d "{\"content\":\"Build terminé : $CI_JOB_STATUS\"}" $DISCORD_WEBHOOK_URL'
