# APP-UNIFY-01 U2 — BurnInStatusSnapshot + historique PAPER

Issue : #328  
Parent : #323  
Freeze : #286  
Baseline : `a2032b13982ae270cb8cd6e0f96c45ed6d53b721`

## Architecture

```text
PPL append-only + BURN_IN_EXPERIMENT_CONFIG_V1
              ↓
BurnInStatusSnapshot producer READ-ONLY
              ↓
atomic JSON presentation artifact
              ↓
strict Operator API reader
              ↓
GET /api/operator/v1/burn-in
              ↓
Direction + PAPER LIVE / Burn-in
```

L'API ne lit jamais le PPL JSONL. Le frontend ne lit jamais le PPL JSONL.
Le producteur ne crée pas de lock PPL et n'écrit jamais dans le store
autoritaire.

## Scientific T0

`scientific_t0_utc` est distinct de `EPOCH_CREATED`.

Le producteur n'infère jamais T0 depuis l'epoch. Sans source gouvernée
explicitement injectée, le snapshot publie :

```json
{"status":"NOT_AVAILABLE","value_utc":null,"source":null}
```

## Historique

Une ligne par lifecycle PPL, triée par séquence OPEN décroissante.

- OPEN : aucune sortie/PnL terminal fabriqué.
- CLOSED : gross/net PnL dérivés avec la formule canonique PPL puis réconciliés
  contre `PaperPortfolioState.realized_pnl`.
- UNRESOLVED : aucun exit/PnL fabriqué ; la raison durable est conservée.

## Configuration

La projection exige l'identité triple :

```text
PPL epoch.paper_epoch_id == config.paper_epoch_id
PPL epoch.code_sha == config.runtime_source_sha
PPL epoch.config_snapshot_hash == config.snapshot_sha256
```

Seule une whitelist de paramètres matériels est exposée.

## Runtime

Cette tranche est SOURCE-ONLY. Aucun déploiement, restart Advisor, mutation
systemd/PPL/FIN/epoch/config/risk/sizing, TESTNET/LIVE ou exchange n'est
autorisé par cette certification.
