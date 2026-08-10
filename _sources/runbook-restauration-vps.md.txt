# Runbook — Restaurer la machine sur une instance neuve (sans crash)

**Objectif opérateur (2026-07-16)** : pouvoir redémarrer la machine complète
sur n'importe quelle instance Linux neuve (GCP, Hetzner, OVH…) à partir du
dépôt git et d'une sauvegarde des données — en ~1 heure, sans rien perdre.

## Ce qui vit où

| Élément | Où il est sûr | Restauration |
|---|---|---|
| Code + ADR + unités systemd | git (local + GitHub) | `git clone` |
| Données scientifiques (paper_trades, regret, rejections, observation, runtime_config) | sauvegarde tar (voir § Sauvegarde) | extraction dans `databases/` |
| Secrets + config opérateur (`.env` : clés MEXC, tokens Telegram, VPS_*, UNIVERSE_PINNED_SYMBOLS) | dans la sauvegarde tar (JAMAIS dans git) | copie à la racine |
| État systemd (5 unités + 3 timers) | copies de référence versionnées `scripts/systemd/` | `cp` + `enable` |

## Sauvegarde (à refaire régulièrement — dernière : 2026-07-16, 16 Mo)

```bash
# côté VPS (via ssh) :
cd ~/crypto_ai_terminal && tar czf /tmp/vps_science_backup_$(date +%Y%m%d).tar.gz \
  --exclude='*.bak_*' databases/paper_trades.jsonl databases/regret_analysis.jsonl \
  databases/regret databases/rejections databases/observation \
  databases/runtime_config.json databases/gate_rejections.csv .env
# côté poste local :
scp -i <clé> <user>@<hôte>:/tmp/vps_science_backup_*.tar.gz backups/vps/
```

La sauvegarde contient `.env` (secrets) → la garder hors git, disque local uniquement.

## Restauration sur instance neuve (Ubuntu 22.04+, 2 vCPU / 8 Go suffisent)

```bash
# 1. Dépendances système
sudo apt update && sudo apt install -y python3.11 python3.11-venv git

# 2. Code
git clone https://github.com/3a7i3/crypto-ia-terminal.git ~/crypto_ai_terminal
cd ~/crypto_ai_terminal

# 3. Environnement Python — utiliser l'inventaire GELÉ de production
#    (requirements.txt avait dérivé : ccxt manquant, découvert lors de la
#    préparation du 2026-07-18) :
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-vps-frozen-20260718.txt

# 4. Données + secrets (depuis la sauvegarde rapatriée sur la nouvelle machine)
tar xzf vps_science_backup_YYYYMMDD.tar.gz -C ~/crypto_ai_terminal
# → restaure databases/* et .env à leur place

# 5. Adapter les chemins des unités si l'utilisateur n'est pas
#    "mathieuhasard111" (sed sur User= et les chemins /home/...)
sudo cp scripts/systemd/crypto-*.service scripts/systemd/crypto-*.timer /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Démarrage — moteur d'abord, observation ensuite
sudo systemctl enable --now crypto-advisor.service
sudo systemctl enable --now crypto-watchdog.service
sudo systemctl enable --now crypto-market-observer.timer
sudo systemctl enable --now crypto-market-radar.timer
sudo systemctl enable --now crypto-market-horizons.timer
```

## Vérifications post-restauration (dans l'ordre)

1. `journalctl -u crypto-advisor -f` : boot propre, « ÉPINGLÉ (ADR-0015/0017) :
   N symboles », capital WalletSync continu (le ledger restauré fait foi —
   aucune discontinuité de capital attendue), DatasetGate sans violation.
2. Telegram : message « Crypto AI Terminal demarre » + rapport suivant
   cohérent (Trades = N canonique restauré, positions restaurées).
3. `python tools/cri_calculator.py` : N identique à la valeur d'avant
   migration (le dataset a voyagé intact).
4. `python observation/market_observer.py --summary` : le pouls reprend.
5. `python tools/throughput_probe.py --days 7` : lecture normale.

## Bascule ancienne → nouvelle instance (planifiée J-5 avant l'échéance GCP)

Fenêtre décidée par l'opérateur (2026-07-18) : bascule autour du
**31/07-01/08** (échéance essai ≈ 05/08). Ordre STRICT — jamais deux
moteurs en parallèle :

1. **J-5, préparation (sans toucher à l'ancienne)** : instance neuve créée
   par l'opérateur (voir § Restauration : specs, clé SSH) → Claude Code
   exécute les étapes 1-5 du runbook sur la neuve (code + venv + unités),
   **SANS démarrer aucun service** (`enable` sans `--now` interdit ici :
   ne pas enable du tout).
2. **Répétition générale** : restaurer une sauvegarde fraîche sur la
   neuve, lancer les vérifications 3-5 (cri_calculator, pouls --summary,
   throughput_probe) — moteur toujours éteint. Toute anomalie se règle
   ici, pendant que l'ancienne trade normalement.
3. **Jour J** : (a) `sudo systemctl stop crypto-advisor crypto-watchdog`
   + stop des 3 timers sur l'ANCIENNE ; (b) sauvegarde finale (tar) et
   transfert direct ancienne→neuve (delta de quelques heures) ;
   (c) extraction sur la neuve ; (d) démarrage des services sur la neuve
   (ordre du § Restauration) ; (e) vérifications post-restauration ;
   (f) `.env` local : nouveau `VPS_HOST` ; whitelist IP MEXC si active.
4. **J+1** : re-vérifier N/CRI identiques + premier rapport Telegram
   cohérent, PUIS seulement éteindre/supprimer l'ancienne instance
   (les données y restent ~30 j après fin d'essai de toute façon).

Interruption de trading attendue : < 30 minutes (étape 3).

## Pièges connus

- **Ne pas** lancer deux moteurs en parallèle (ancienne + nouvelle instance) :
  arrêter `crypto-advisor` sur l'ancienne AVANT le premier démarrage sur la
  neuve (verrou d'instance local, mais rien n'empêche 2 machines distinctes).
- `.env` : mettre à jour `VPS_HOST` côté poste local (déploiements futurs).
- Les timers sont en UTC (`TZ=UTC` dans les unités) — ne pas « corriger ».
- Le disque : prévoir ≥ 40 Go (leçon du 29 Go à 92%).
- IP sortante neuve : si l'API MEXC est restreinte par IP, mettre à jour la
  whitelist dans le compte MEXC avant le démarrage.
