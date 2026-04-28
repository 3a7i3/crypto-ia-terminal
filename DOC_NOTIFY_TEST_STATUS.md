# Documentation d’utilisation – notify_test_status.py

## Fonction
Ce script automatise l’exécution des tests, la génération d’un rapport, et l’envoi de notifications (Discord, email, Telegram) selon le résultat.

## Utilisation rapide

1. **Configurer les notifications** (optionnel, selon besoins) :
   - **Discord** :
     - Crée un webhook dans ton serveur Discord.
     - Dans PowerShell :
       `$env:DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/TON_WEBHOOK"`
   - **Email** :
     - Active : `$env:EMAIL_ENABLED="1"`
     - Configure :
       `$env:EMAIL_TO="destinataire@email.com"`
       `$env:EMAIL_SMTP_SERVER="smtp.serveur.com"`
       `$env:EMAIL_SMTP_PORT="587"`
       `$env:EMAIL_SMTP_USER="utilisateur@email.com"`
       `$env:EMAIL_SMTP_PASSWORD="motdepasse"`
   - **Telegram** :
     - Active : `$env:TELEGRAM_ENABLED="1"`
     - Configure :
       `$env:TELEGRAM_BOT_TOKEN="<token>"`
       `$env:TELEGRAM_CHAT_ID="<chat_id>"`

2. **Lancer le script** :
   ```powershell
   C:/Users/WINDOWS/AppData/Local/Programs/Python/Python314/python.exe notify_test_status.py
   ```

## Fonctionnement
- Exécute tous les tests avec pytest
- Génère un rapport Markdown (test_report.md)
- Envoie une notification sur Discord, email, Telegram selon le résultat
- Les notifications sont envoyées en cas d’échec ou de warning

## Personnalisation
- Modifie le contenu des messages dans notify_test_status.py si besoin
- Ajoute d’autres canaux en suivant le modèle des fonctions existantes

## Dépannage
- Si une notification ne part pas, vérifie la variable d’environnement correspondante
- Si un test échoue, consulte test_report.md pour le détail
- Pour forcer l’envoi sur tous les statuts, adapte la condition dans check_test_report

---

Pour toute question ou extension, adapte notify_test_status.py ou demande une nouvelle fonctionnalité !
