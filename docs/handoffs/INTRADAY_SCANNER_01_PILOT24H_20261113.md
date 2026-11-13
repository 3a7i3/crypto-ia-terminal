# INTRADAY-SCANNER-01 — état vérifié et pilote de collecte MEXC (2026-11-13)

> **Statut à la clôture de ce relevé : `PILOT_24H_RUNNING`, et NON `PILOT_24H_CERTIFIED`.**
> Rapport arrêté au **2026-11-13 04:03:25 UTC**. Toute affirmation de l'état ultérieur exige une nouvelle lecture du VPS.
> Ce document est un **handoff / journal de décision**, pas une demande de déploiement, de fusion ou d'activation d'une epoch.

## 1. Mission et frontières

Construire une infrastructure de **recherche intraday personnelle**, séparée de la chaîne PAPER trading : d'abord un flux passif de cotations MEXC spot/perp, ensuite une présélection de marchés par qualité (liquidité, spread, activité), enfin un scanner technique à spécifier et tester (EMA, ADX/DMI, RSI, RVOL, ATR, VWAP, structure et unités de temps).

- **Autorisation opérateur** : premier passage isolé, campagne de trois passages supplémentaires, puis pilote **24 h / 15 min**, limité à l'observation de données publiques. Aucun trading, ordre, signal exécutable, Advisor réel, nouvelle epoch ou changement de la gate.
- **GitHub** : base lue `main@87155f3aacb11d266ae45ffb95810f698c0db3cf` (C1a fusionné). La validation source de C1b et sa publication relèvent d'un **chantier distinct**. Préserver #282, #286 et D-EPOCH-PATH.
- **VPS observé** : `crypto-restore-01`, utilisateur non privilégié `lecanada26` (uid 1001) ; release en cours `85376c5e7725c9fa45f8d05fb0051f25a127aba4`. Le working tree de cette release était propre à la dernière lecture.
- **Ne pas assimiler Git et runtime** : les fichiers `scripts/systemd/crypto-market-observer.*` du dépôt visent l'ancien utilisateur/chemin `mathieu` ; **ils n'ont pas été installés**. Le pilote utilise des unités **systemd utilisateur** dédiées, hors dépôt et hors release.
- **Operator App** : l'API/Web étaient actifs, mais `/api/operator/v1/market` fournissait toujours une capture `STALE` dont le dernier DecisionPacket datait du **2026-10-29 05:29:04 UTC**. La collecte MEXC décrite ici ne met **pas** automatiquement à jour cette vue. `/api/operator/v1/market-flow` répondait `MARKET_FLOW_NOT_CONFIGURED`.

## 2. Emplacements exacts sur le VPS

Racine persistante du pilote, séparée du dépôt et de la release :
`/home/lecanada26/crypto-install/personal-market-observation-v0/`

| Artefact | Chemin relatif à la racine ci-dessus | Description |
|---|---|---|
| Captures | `market_pulse_YYYY-MM-DD.jsonl.gz` | Cotations MEXC publiques, append gzip |
| Sidecar | `latest_tick.json` | Dernière observation spot ; ne doit pas être branchée au PAPER |
| Manifeste | `pilot24h/manifest.json` | Identité de release, fenêtre, limites et configuration déclarée |
| Runner | `pilot24h/runner.py` | Garde de durée, compte, version et collecte ; créé localement sur le VPS |
| Journal | `pilot24h/runs.jsonl` | Evénements `COLLECT_PASS`, `COLLECT_FAIL`, `EXPIRED`, etc. |

Unités installées dans **`/home/lecanada26/.config/systemd/user/`** :

- `cat-market-observer-pilot24h.service` — one-shot Python sur release `85376c5e`.
- `cat-market-observer-pilot24h.timer` — première activation à 60 s, puis ~15 min après l'activation précédente.

Ni `crypto-market-radar.timer`, ni `crypto-market-observer.timer` (systemd global), ni l'Advisor n'ont été démarrés dans cette mission.

## 3. Séquence d'observation vérifiée

| UTC | Opération | Résultat |
|---|---|---|
| 2026-11-13 03:31:33 | Première collecte manuelle isolée | 1 768 spot + 1 188 swap ; rc 0 |
| 2026-11-13 03:33:45 | Collecte bornée 1/3 | Identique en nombre ; rc 0 ; ~6 s |
| 2026-11-13 03:34:51 | Collecte bornée 2/3 | Identique en nombre ; rc 0 ; ~7 s |
| 2026-11-13 03:35:58 | Collecte bornée 3/3 | Identique en nombre ; rc 0 ; ~6 s |
| 2026-11-13 03:59:06 | Manifeste pilote créé | Début déclaré, expiry +24 h |
| 2026-11-13 04:00:20–04:00:26 | **Premier cycle systemd utilisateur** | `COLLECT_PASS`, rc 0, 1 768 spot + 1 188 swap, 6,166 s |
| 2026-11-13 04:03:25 | Contrôle read-only | Timer `active/waiting` ; prochain cycle programmé vers 04:15:20 UTC ; 1 PASS dans `runs.jsonl` |

**Campagne manuelle de 4 captures (avant pilote)** : 11 824 enregistrements, 2 956 identifiants distincts par `(exchange, marché, symbole)` par capture ; ensemble des identifiants inchangé sur cette fenêtre courte (Jaccard = 1,0), 0 livre croisé (`bid > ask`), 2 950 volumes quote strictement positifs par capture (6 non positifs). Variation du dernier prix entre captures adjacentes : environ 84 à 87 % des identifiants. Spread médian sur cet **univers non filtré** : ~0,35 %, avec p95 ~2,9 %. Cela ne représente pas le spread d'une watchlist qualifiée.

Les horodatages `ts` sont ceux de la **capture locale du lot** ; ils ne prouvent **pas** l'âge de chaque ticker source. La qualité intraday du marché ne doit pas être inférée de ces seuls timestamps.

## 4. Paramètres et limites de la campagne

- **Deadline** : début `2026-11-13T03:59:06Z`, expiration `2026-11-14T03:59:06Z`.
- **Cadence** : 15 min, `Persistent=false`, un seul process `oneshot` par activation, timeout systemd 90 s.
- **Source** : `OBS_EXCHANGES=mexc`, MEXC public spot/swap via CCXT 4.5.92 dans Python 3.11.17 de la release.
- **Secrets et notifications** : environnement Python réinitialisé sans clés exchange ; `RADAR_TELEGRAM_DIGEST=false` ; aucune commande de trading.
- **Stockage** : racine 0700 ; fichiers 0600 ; garde d'espace disque `OBS_MIN_FREE_DISK_GB=10`, rétention `OBS_RETENTION_DAYS=2` **limitée au dossier d'observation dédié** ; 61 Go libres sur le disque racine au contrôle.
- **Garantie de fin bornée** : dès que le runner s'exécute **après** `expires_epoch`, il refuse de collecter, écrit `EXPIRED`, puis **tente** `systemctl --user disable --now` sur son timer. Le timer n'est **pas** désactivé à la seconde exacte du deadline : la vérification de désactivation doit être faite après le prochain déclenchement. Un échec de la commande de désactivation doit être signalé, pas masqué.
- **État de GitHub** : le code `runner.py` et les deux unités ci-dessus sont **des artefacts runtime hors dépôt** ; leurs empreintes sont conservées dans le runbook, mais **pas encore soumis comme implémentation à intégrer dans `main`**. La présente PR est documentaire seulement.

## 5. Plan et critères de décision après les 24 h

**Phase actuelle :** observer et mesurer, ne pas intervenir dans le système PAPER.

1. À l'échéance, lire `pilot24h/manifest.json`, `runs.jsonl` et les métadonnées des fichiers de captures. Vérifier l'arrêt de collecte, le nombre de cycles attendus/réalisés, les PASS/FAIL et les trous de 15 min.
2. Comparer la population spot/swap, la continuité des identifiants, la fréquence des volumes manquants, les spreads, l'espace disque et les erreurs source/timeout. Distinguer le timestamp du batch de la fraîcheur des cotations par marché.
3. Vérifier que le timer a été désactivé et qu'aucun collecteur ne reste en tâche de fond. Ne pas extrapoler les quatre captures initiales à 24 h.
4. Rendre un verdict `GO_REVIEW_FOR_RADAR` ou `NO_GO_REMEDIATE`, avec limites, puis **demander un GO distinct** avant d'activer le radar quotidien.
5. Le scanner personnel avec EMA/ADX/RSI/RVOL/ATR/VWAP nécessitera des **OHLCV multi-timeframes**, un univers éligible et un protocole de comparaison historique. Le pouls de `fetch_tickers` ne permet pas à lui seul de calculer correctement ces indicateurs.

**Décisions durables :** collecte et trading séparés ; aucun lien avec la gate PPL ; radar et notifications désactivés pendant le pilote ; aucune fusion/deploy implicite ; aucune modification automatique de l'Operator App.

Références de conception : [MARKET-TIMING-01](../research/MARKET_TIMING_01_PROTOCOL.md) et [scanner 500–1000 paires](../design/scanner-500-paires.md). Voir [runbook d'exploitation](../runbooks/INTRADAY_SCANNER_01_PILOT24H_OPERATIONS.md).
