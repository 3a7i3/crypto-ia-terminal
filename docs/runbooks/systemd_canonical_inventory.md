# Systemd Canonical Inventory — crypto_ai_terminal

## Objectif

Figer l'inventaire **canonique Git** des unités/timers systemd supportés par le
projet, afin de détecter les dérives VPS (unités orphelines non versionnées).

Ce document est normatif pour la préparation Git **avant** toute action VPS.

## Source canonique

Répertoire de référence unique :

- `/home/runner/work/crypto-ia-terminal/crypto-ia-terminal/scripts/systemd/`

## Set canonique actuel (Git)

### Services

1. `crypto-advisor.service`
2. `crypto-watchdog.service`
3. `crypto-market-observer.service` (oneshot)
4. `crypto-market-radar.service` (oneshot)
5. `crypto-market-horizons.service` (oneshot)

### Timers

1. `crypto-market-observer.timer`
2. `crypto-market-radar.timer`
3. `crypto-market-horizons.timer`

## Services additionnels versionnés (hors set 5+3)

Présents dans Git mais non inclus dans le socle de restauration 5+3 :

- `crypto-radar-bot.service`
- `crypto-quant-observer.service`
- `crypto-lmi-observatory.service`
- `crypto-dashboard.service`
- `paper-arena.service`

## Non-canon / orphelin (drift VPS)

À ce stade, les éléments suivants sont considérés **non-canoniques** tant
qu'aucune source Git signée/traçable n'est fournie :

- `crypto-backup.service`
- `crypto-backup.timer`
- `crypto-burnin-chronicle.service`
- `crypto-burnin-chronicle.timer`
- `scripts/backup_daily.sh`
- `tools/burnin_chronicle.py`

Règle opérationnelle :

- **Interdit** de recréer `backup_daily.sh` ou `burnin_chronicle.py` de façon
  arbitraire.
- **Interdit** de substituer `backup_daily.sh` par `backup_audit.sh`.
- **Interdit** de substituer `burnin_chronicle.py` par `burnin_v2_report.py`.

## Procédure minimale de contrôle de dérive (VPS, après push Git validé)

1. Snapshot des unités/timers actifs dans `/etc/systemd/system/`.
2. Vérification `git status` sur VPS (absence de modifications locales).
3. `git pull --ff-only`.
4. `systemctl daemon-reload` uniquement si des unités/timers versionnés ont
   réellement changé.
5. Validation des statuts/journaux des services.
6. Si orphelin confirmé : désactivation contrôlée du timer puis du service.

## Rollback

1. Restaurer les fichiers unit/timer depuis le snapshot.
2. `systemctl daemon-reload`.
3. Réactiver uniquement les unités/timers explicitement restaurés.
