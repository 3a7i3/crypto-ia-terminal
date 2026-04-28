# Exemple de script PowerShell pour initialiser les variables d'environnement SMTP
$env:SMTP_USER = "votre.email@domaine.com"
$env:SMTP_PASS = "votre_mot_de_passe_application"
$env:SMTP_SERVER = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:ALERT_EMAIL = "destinataire@domaine.com"

Write-Host "Variables SMTP définies pour la session PowerShell."
