# Déploiement Oracle Cloud Free Tier — Guide étape par étape

## Étape 1 — Créer le compte Oracle Cloud

1. Aller sur https://cloud.oracle.com → **Start for free**
2. Remplir avec ton email (mathieuhasard111@gmail.com)
3. Carte bancaire requise pour vérification — **aucun débit sans action de ta part**
4. Choisir la région la plus proche (ex: `eu-paris-1` ou `ca-montreal-1`)

---

## Étape 2 — Créer la VM (instance gratuite)

1. Menu → **Compute** → **Instances** → **Create Instance**
2. Nom : `crypto-advisor`
3. Image : **Ubuntu 22.04** (Canonical)
4. Shape : **VM.Standard.E2.1.Micro** (Always Free — 1 OCPU, 1 GB RAM)
5. Réseau : laisser par défaut (VCN auto-créé)
6. **SSH key** : Générer une nouvelle paire → télécharger `crypto-advisor.key`
7. Cliquer **Create**

---

## Étape 3 — Ouvrir le port pour SSH (déjà ouvert par défaut)

Dans le menu réseau de l'instance :
- Port 22 (SSH) : ouvert par défaut ✓

---

## Étape 4 — Se connecter à la VM

```bash
# Sur ton PC (dans le dossier où tu as téléchargé la clé)
chmod 400 crypto-advisor.key
ssh -i crypto-advisor.key ubuntu@<IP_DE_LA_VM>
```

L'IP est visible dans la console Oracle → Instances → Public IP address.

---

## Étape 5 — Déployer le projet depuis ton PC

```bash
# Dans le dossier crypto_ai_terminal sur ton PC
bash deploy/deploy.sh <IP_DE_LA_VM> ubuntu
```

Ce script :
- Synchronise tout le code (rsync)
- Copie le .env avec les clés API
- Exclut les fichiers sensibles (.git, logs, etc.)

---

## Étape 6 — Installer et démarrer

```bash
# Sur le VPS (après connexion SSH)
cd ~/crypto_ai_terminal
bash deploy/setup_vps.sh

# Démarrer le service
sudo systemctl start crypto-advisor

# Vérifier qu'il tourne
sudo systemctl status crypto-advisor

# Logs en temps réel
tail -f logs/advisor_loop.log
```

---

## Contrôle depuis le mobile

Le bot Telegram **répond automatiquement** — pas besoin d'application spéciale.

| Commande Telegram | Action |
|---|---|
| `/status` | État du système |
| `/STOP` | Kill switch — stoppe les trades |
| `/RESUME` | Reprend le trading |
| Rapport automatique | Toutes les 3 minutes (cycle 3, 6, 9...) |

---

## Maintenance

```bash
# Redémarrer après une mise à jour du code
bash deploy/deploy.sh <IP> ubuntu
ssh ubuntu@<IP> 'sudo systemctl restart crypto-advisor'

# Voir si le service tourne
ssh ubuntu@<IP> 'sudo systemctl status crypto-advisor'

# Logs des 50 dernières lignes
ssh ubuntu@<IP> 'tail -50 ~/crypto_ai_terminal/logs/advisor_loop.log'
```

---

## Coût

- **VM.Standard.E2.1.Micro** : gratuit à vie (Always Free)
- Bande passante : 10 TB/mois sortant gratuit
- Seul risque de coût : si tu actives des options payantes manuellement
