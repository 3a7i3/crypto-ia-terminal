# Runbook — INTRADAY-SCANNER-01 / Pilote MEXC 24 h

**Statut** : compte rendu d'une activation **effectuée** sur `crypto-restore-01` le 2026-11-13. Ce texte n'autorise aucune nouvelle installation, réactivation ou fusion.

## Inventaire : ce qui est installé, ce qui ne l'est pas

Le pilote fonctionne avec `systemd --user` sous `lecanada26` (uid 1001, `loginctl Linger=yes`). Les unités **ne se trouvent pas** dans `/etc/systemd/system/` :

```text
/home/lecanada26/.config/systemd/user/
  cat-market-observer-pilot24h.service
  cat-market-observer-pilot24h.timer

/home/lecanada26/crypto-install/personal-market-observation-v0/
  market_pulse_YYYY-MM-DD.jsonl.gz
  latest_tick.json
  pilot24h/
    runner.py
    manifest.json
    runs.jsonl
```

La release consommée en lecture est `/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4`. Le programme métier appelé est `observation.market_observer.snapshot_once`. La release Git est restée propre. Le projet ne possède pas à ce stade de reproduction Git canonique pour le **runner local** et ses deux unités spécifiques.

**Empreintes SHA-256 relevées le 2026-11-13 04:03:25 UTC :**

| Fichier runtime | SHA-256 |
|---|---|
| `pilot24h/runner.py` | `7895ee98de7417d66ab1ebeb76d732937424bd9c68f010bd73a110b3b39a1de4` |
| `pilot24h/manifest.json` | `b523b29c80087003995feccea7f08941b317468318367725889cf723c7aa99b9` |
| `cat-market-observer-pilot24h.service` | `002d98746022f271fd9c1e1291ace4ebacc186867f6135d27e72b643c948b931` |
| `cat-market-observer-pilot24h.timer` | `360954dea2d5aca971296f17f1fe13ddbcad603d607a76617108409efef73445` |

Ces hashes attestent l'identité des artefacts **observés** ; ils ne certifient ni leur qualité production ni une installation depuis GitHub.

## Inspection strictement en lecture seule

Sur la machine, en session autorisée avec le compte `lecanada26`, sans afficher de fichiers `.env` ou de secrets :

```bash
systemctl --user list-timers --all cat-market-observer-pilot24h.timer
systemctl --user show cat-market-observer-pilot24h.timer \
  -p ActiveState -p SubState -p UnitFileState -p LastTriggerUSec
systemctl --user show cat-market-observer-pilot24h.service \
  -p ActiveState -p Result -p ExecMainStatus
journalctl --user -u cat-market-observer-pilot24h.service --no-pager -n 30
tail -n 20 /home/lecanada26/crypto-install/personal-market-observation-v0/pilot24h/runs.jsonl
du -sh /home/lecanada26/crypto-install/personal-market-observation-v0
df -h /
```

Pour lire le manifeste, consulter **seulement** les attributs attendus : `started_epoch`, `expires_epoch`, `interval_seconds`, `release_head` et `data_dir`. Ne pas exposer de tokens, même si aucun token n'est attendu dans cet artefact.

Journal `runs.jsonl` : `COLLECT_PASS` inclut les comptes spot/swap, la durée, `bytes_written` et `free_gb`; `COLLECT_FAIL`, `COLLECT_EXCEPTION`, `REFUSED_*`, `EXPIRED` et `TIMER_DISABLE` sont des événements à examiner. Une réussite de service systemd sans `COLLECT_PASS` doit être analysée.

L'API `/api/operator/v1/market` de la release active lit un **snapshot historique de DecisionPackets**, non ce pouls MEXC. Le statut `STALE` dans l'app ne constitue donc pas un échec de la collecte MEXC, et la nouvelle collecte ne rend pas cette vue `FRESH`.

## Stop, échéance et contrôles de sûreté

- **Début déclaré** : `2026-11-13 03:59:06 UTC`.
- **Expiration déclarée** : `2026-11-14 03:59:06 UTC`.
- **Déclenchement observé** : première exécution du timer `2026-11-13 04:00:20 UTC`, `COLLECT_PASS`, 1 768 spot et 1 188 swap, rc 0.
- **Prochaine activation constatée à 04:03 UTC** : `2026-11-13 04:15:20 UTC`.
- **Comportement après expiration** : le runner vérifie la date avant la collecte. Au premier déclenchement post-expiration, il doit refuser toute collecte puis tenter de désactiver le timer. **L'arrêt effectif du timer n'est pas encore démontré.** Vérifier `TIMER_DISABLE.exit_code` et `UnitFileState` après la fin.
- **Stop manuel d'urgence** (action à n'exécuter que sur décision opérateur spécifique, pas pour la lecture de ce runbook) :
  ```bash
  systemctl --user disable --now cat-market-observer-pilot24h.timer
  ```
  Cette commande laisse les fichiers de preuves sur disque. Le service one-shot est à contrôler séparément s'il est en cours.
- **Rollback complet** : ne jamais supprimer le dossier d'observation ni les journaux avant conservation/validation des preuves. Le retrait des unités et du runner, si décidé, doit faire l'objet d'un plan de changement et d'un GO séparés.

## Points de risque à garder visibles

1. `latest_tick.json` est un sidecar pouvant être consommé par `core/topk_scheduler.py` **si on le câble**. Le répertoire de ce pilote est distinct et n'a pas été branché au moteur. Ne jamais le substituer silencieusement au chemin d'ordonnancement du PAPER.
2. Les cotations `fetch_tickers` ont un timestamp de **réception par batch** ; aucun contrôle de timestamp source individuel n'est établi. Le volume 24 h (`qv`) n'est pas un RVOL à 5 ou 15 minutes.
3. `OBS_RETENTION_DAYS=2` peut supprimer des fichiers de cette zone à mesure que le calendrier avance. Pour une expérience scientifique plus longue, prévoir une politique de conservation vérifiée et distincte.
4. La couverture MEXC peut changer ; compter les identifiants uniques `(ex, mkt, sym)`, pas additionner des « paires tradables uniques » spot + swap.
5. La source Python est figée sur une release ancienne par rapport au `main` GitHub. Éviter tout `git pull`, installation ou bascule de release pendant la campagne.
6. `Ruff`, la CI GitHub et les validations C1b **ne certifient pas** ce pilote local : les preuves runtime sont indépendantes.
7. La désactivation automatique exige l'exécution d'un cycle **après** l'expiration. Ce n'est pas un arrêt systemd exact à la seconde ; confirmer l'état réel à la clôture.

## Checklist du bilan de 24 h

- [ ] Journal complet et ordonné (sans doublon de cycles).
- [ ] Nombre de cycles attendus vs collectés ; écarts calendaires documentés.
- [ ] Taux `COLLECT_PASS`, échecs spot/swap, exceptions, timeouts.
- [ ] Série des heures effectives de capture ; lacunes identifiées.
- [ ] Stabilité des identifiants (spot et perp distincts), liquidité et spreads mesurés.
- [ ] Volumes non positifs/absents et qualité des prix, sans les recoder en zéro silencieusement.
- [ ] Taille des fichiers, place disque disponible, portée de la rétention.
- [ ] Aucun déclenchement de PAPER, Advisor, orders ou exchange privé.
- [ ] Exécution post-expiration observée, refus de collecte confirmé, timer désactivé confirmé.
- [ ] Verdict explicite **GO_REVIEW_FOR_RADAR** ou **NO_GO_REMEDIATE**. L'activation du radar quotidien nécessite un GO distinct.

Voir [compte rendu / journal de décisions](../handoffs/INTRADAY_SCANNER_01_PILOT24H_20261113.md).
