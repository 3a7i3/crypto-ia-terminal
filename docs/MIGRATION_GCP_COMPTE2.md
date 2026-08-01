# Migration vers le second compte GCP — paramètres et procédure

Relevé sur `crypto-advisor-2` le 2026-08-01. Chaque valeur est **mesurée**,
aucune n'est supposée. Échéance de l'essai gratuit du compte n°1 : **~2026-08-05**.

---

## 1. Spécification de l'instance actuelle

| Paramètre | Valeur mesurée |
|---|---|
| Nom | `crypto-advisor-2` |
| Projet | `hale-photon-495606-n2` (compte `mathieuhasard111@gmail.com`) |
| Type | `e2-standard-2` — 2 vCPU, 7,8 Gio RAM |
| Zone | `asia-southeast1-a` (Singapour) |
| Disque | 80 Go `pd-balanced`, **occupé à 32 %** (25 Go / 54 Go libres) |
| Image | Ubuntu 22.04.5 LTS (jammy), noyau `6.8.0-1063-gcp`, amd64 |
| IP externe | `35.240.166.72`, `PREMIUM`, `ONE_TO_ONE_NAT` (éphémère) |
| Ordonnancement | `automaticRestart: true`, `onHostMaintenance: MIGRATE`, **non préemptible** |
| Fuseau | `Etc/UTC` |
| Firewall hôte | **aucun** — UFW installé mais `ENABLED=no`, iptables en `ACCEPT` sans règle |
| Ports en écoute | 22 (sshd), **8080 (`advisor_loop.py`, sur `0.0.0.0`)**, 20201/20202 (agent Ops) |

### Deux observations qui appellent une décision

**Le disque est surdimensionné.** 80 Go pour 25 Go utilisés, dont ~4 Go de
télémétrie régénérable qu'on ne migrera pas. **40 Go suffisent largement** et
coûtent moitié moins.

**Le port 8080 du moteur écoute sur toutes les interfaces, sans firewall
hôte.** Ce n'est pas nouveau et ce n'est pas un incident, mais la migration est
le bon moment pour le corriger — soit en le liant à `127.0.0.1`, soit par une
règle de pare-feu GCP. À décider, pas à reproduire par défaut.

---

## 2. Choix de zone — le point le moins évident

L'instance actuelle est à **Singapour**, l'opérateur est au **Canada**. Le
réflexe serait de rapprocher la machine de soi. **Ce serait probablement une
erreur** : la latence qui compte est celle vers **MEXC**, pas vers l'écran.

- Le moteur émet ~43 appels API/heure vers MEXC et lit le marché en continu.
- L'opérateur consulte des messages Telegram : quelques centaines de
  millisecondes de plus n'ont aucun effet.
- Les serveurs MEXC sont en Asie ; `asia-southeast1` est vraisemblablement le
  meilleur choix, et c'est celui en place.

**Recommandation : rester en `asia-southeast1-a`.** Changer de continent
modifierait une variable d'exécution (la latence d'exécution) au milieu d'un
burn-in scientifique — exactement ce que le gel cherche à éviter.

Si tu veux malgré tout rapprocher la machine, `northamerica-northeast1-a`
(Montréal) existe, mais alors **note-le comme un changement d'époque** : les
mesures de latence avant/après ne seront plus comparables.

---

## 3. Commande de création

À exécuter **après** `gcloud auth login` avec le second compte et
`gcloud config set project <PROJET_2>`.

```bash
gcloud compute instances create crypto-advisor-3 \
  --project=PROJET_2 \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=40GB \
  --boot-disk-type=pd-balanced \
  --boot-disk-device-name=crypto-advisor-3 \
  --maintenance-policy=MIGRATE \
  --no-preemptible \
  --scopes=https://www.googleapis.com/auth/devstorage.read_only,https://www.googleapis.com/auth/logging.write,https://www.googleapis.com/auth/monitoring.write,https://www.googleapis.com/auth/service.management.readonly,https://www.googleapis.com/auth/servicecontrol,https://www.googleapis.com/auth/trace.append \
  --metadata=enable-osconfig=TRUE \
  --tags=crypto-advisor
```

**Vérifier ensuite la disponibilité de `e2-standard-2` dans la zone** : les
quotas d'un compte neuf sont parfois plus serrés que ceux d'un compte rodé.

### Réserver une IP statique — fortement recommandé

L'IP actuelle est **éphémère** : elle change à chaque arrêt/démarrage de la VM.
Comme les clés MEXC sont whitelistées par IP, une IP éphémère signifie
**refaire la whitelist à chaque redémarrage**.

```bash
gcloud compute addresses create crypto-advisor-ip --region=asia-southeast1
gcloud compute instances delete-access-config crypto-advisor-3 \
  --zone=asia-southeast1-a --access-config-name="External NAT"
gcloud compute instances add-access-config crypto-advisor-3 \
  --zone=asia-southeast1-a --access-config-name="External NAT" \
  --address=$(gcloud compute addresses describe crypto-advisor-ip \
      --region=asia-southeast1 --format='value(address)')
```

Coût d'une IP statique attachée à une VM active : négligeable (elle n'est
facturée que si elle est réservée sans être utilisée).

---

## 4. Ordre d'exécution

```
1. gcloud auth login                       (compte n°2)
2. créer l'instance + l'IP statique        ← ressource facturable, décision opérateur
3. relever la nouvelle IP publique
4. >>> AJOUTER CETTE IP À LA WHITELIST MEXC <<<     ← manuel, chez MEXC
5. bash scripts/bootstrap_vps.sh --check   (diagnostic)
6. bash scripts/bootstrap_vps.sh --confirm (couches 1 à 3)
7. déployer le code au commit voulu        (PAS un git clone seul, voir §5)
8. ARRÊTER le moteur sur l'ancienne machine
     sudo systemctl stop crypto-advisor crypto-watchdog
9. copier les données (§6)
10. reconstituer le .env (§7)
11. bash scripts/compare_vps.sh ancien nouveau
12. démarrer les services sur la nouvelle machine
13. observer un cycle complet AVANT d'éteindre l'ancienne
```

**Ne pas sauter l'étape 8.** Copier un `.jsonl` en cours d'écriture tronque sa
dernière ligne.

---

## 5. Le piège principal : le VPS n'est pas son dépôt git

`git HEAD` sur `crypto-advisor-2` est à **`5d1955e`**, et les tags de
déploiement s'arrêtent à **`deploy-20260705`** — alors qu'une vingtaine de
fichiers y ont été copiés par `scp` depuis, dont `core/advisor_loop.py`,
`observability/real_accounts.py` et `system_snapshot_renderers.py`.

`deploy_vps.sh` copie des fichiers ; il ne pousse pas de commit. **Le VPS a donc
divergé sans que rien ne l'enregistre.**

Conséquence : **un `git clone` seul produirait une machine différente de la
production**. Deux voies :

- **Voie propre (recommandée)** : cloner, puis déployer explicitement le commit
  voulu depuis le poste local via `deploy_vps.sh`. On repart d'un état connu.
- **Voie fidèle** : `rsync` le code depuis l'ancienne machine, ce qui reproduit
  la production telle quelle — dérive comprise.

Dans les deux cas, `compare_vps.sh` tranche : il compare l'**empreinte SHA256
de tout le code Python**, pas les commits. Sur une production vivante, le commit
ne dit plus rien.

---

## 6. Données — ce qui se copie, ce qui reste

**IRREMPLAÇABLE (~850 Mo)** — produit par le runtime, n'existe nulle part ailleurs :

```
databases/paper_trades.jsonl          le dataset scientifique (N=139 canonique V4)
databases/runtime_config.json         PARAMÈTRES DE RISQUE LIVE
databases/regret/                     63 Mo
databases/rejections/                390 Mo
databases/observation/               367 Mo
databases/shadow_execution/           32 Mo
databases/integrity_audit.jsonl
```

`runtime_config.json` fait six lignes mais commande le moteur :
`EXEC_MAX_ORDER_USD 50`, `SIGNAL_MIN_SCORE 70`, `EO_DD_VETO 0.1`,
`EO_DD_RECOVERY 0.04`, `EXCHANGE_HEARTBEAT_S 15`, version `CFG-20260714-0003`.

**RÉGÉNÉRABLE (~4,2 Go) — à laisser derrière** :
`decision_packets_*.jsonl` (~2,3 Go), `black_box.jsonl` (529 Mo, chiffré et
corrompu à 97 % depuis mai), `cycle_data*.jsonl`, `logs/` (1,1 Go), `cache/`.

Une copie vérifiée du palier scientifique existe déjà en local :
`backups/vps-corpus-20260731/` (SHA256 contrôlés). La migration peut s'appuyer
dessus si l'ancienne machine devenait inaccessible.

---

## 7. Configuration — 180 variables, dont ~10 secrets

**À re-saisir à la main** (jamais dans un script, jamais dans git) :
`MEXC_API_KEY`, `MEXC_API_SECRET`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`,
`TELEGRAM_BOT_TOKEN`, `INTEL_BOT_TOKEN`, `P10_PORTFOLIO_BOT_TOKEN`,
`REAL_ACCOUNT_BOT_TOKEN`, `PAPER_ARENA_TG_TOKEN`, `EMAIL_SMTP_PASS`.

Les ~170 autres sont de la configuration non secrète et se copient telles quelles.

**Défaut à corriger pendant la migration** : `WALLET_PAPER_CAPITAL` et
`PB_MIN_POSITION_USD` apparaissent **deux fois** dans le `.env` de production.
La dernière occurrence gagne, silencieusement. Dédoublonner.

**Dette de sécurité ouverte** : le PAT GitHub est en clair dans l'URL du remote
`.git/config` (constaté le 2026-07-28, toujours pas révoqué). La migration est
l'occasion de le révoquer et de passer par un credential helper.

---

## 8. Ce que `compare_vps.sh` ne peut pas vérifier

Trois choses restent manuelles, et ce sont celles qui cassent le plus souvent :

1. **La whitelist IP MEXC.** Sans elle, toute lecture de compte échoue — y
   compris l'Observatory autorisé par l'ADR-0019.
2. **La justesse des valeurs de secrets.** Le script compare les *noms* de
   variables, jamais les valeurs. Une clé mal recopiée passe le contrôle.
3. **Qu'un cycle moteur tourne réellement.** Observer les logs sur au moins un
   cycle complet avant d'éteindre l'ancienne machine.
