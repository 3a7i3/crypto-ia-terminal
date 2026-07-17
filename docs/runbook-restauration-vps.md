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

# 3. Environnement Python
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

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

## Pièges connus

- **Ne pas** lancer deux moteurs en parallèle (ancienne + nouvelle instance) :
  arrêter `crypto-advisor` sur l'ancienne AVANT le premier démarrage sur la
  neuve (verrou d'instance local, mais rien n'empêche 2 machines distinctes).
- `.env` : mettre à jour `VPS_HOST` côté poste local (déploiements futurs).
- Les timers sont en UTC (`TZ=UTC` dans les unités) — ne pas « corriger ».
- Le disque : prévoir ≥ 40 Go (leçon du 29 Go à 92%).
- IP sortante neuve : si l'API MEXC est restreinte par IP, mettre à jour la
  whitelist dans le compte MEXC avant le démarrage.
