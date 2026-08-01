"""observation/accounts/ — collecteurs de comptes réels (ADR-0019, Phase A).

Observateur **strictement passif** : il lit, il mesure, il rend des
structures de données. Il ne passe jamais d'ordre, ne modifie jamais un
portefeuille, ne modifie jamais une configuration, ne décide jamais.

Les quatre collecteurs sont des fonctions ``(client) -> enregistrement`` :
aucun état partagé, aucun cache, aucun client construit tant qu'un client est
injecté — c'est ce qui permet aux tests de n'utiliser que de faux clients.

  - `collect_account`     soldes spot et futures, marge, equity (borne basse)
  - `collect_positions`   positions ouvertes, seuil de poussière obligatoire
  - `collect_real_trades` historique futures réel (`fetch_positions_history`)
  - `collect_paper_trades` historique paper, **même schéma** que le réel
  - `collect_transfers`   transferts (2 sens), dépôts, retraits

Support : `collect_orders` / `reconcile_position_ids` portent le mapping des
codes `side` bruts, la lecture d'`externalOid` et le recoupement par
`positionId`.

Hors périmètre, explicitement :
  - persistance JSONL, rotation, rétention, Event Ledger et Event ID → **T3** ;
  - vues Telegram → T4 ;
  - toute alerte, tout verdict, toute détection d'anomalie → **Phase B,
    NON autorisée** sous la signature de l'ADR-0019 (invariant OBS-I).

Limite assumée, jamais masquée : l'historique **spot** ne peut pas être
exhaustif (voir `trade_collector`).
"""

from __future__ import annotations

from .account_collector import AccountRecord, AssetBalance, collect_account
from .order_reader import (
    OrderRecord,
    OrdersRecord,
    PositionIdReconciliation,
    collect_orders,
    reconcile_position_ids,
)
from .position_collector import OpenPosition, PositionsRecord, collect_positions
from .trade_collector import (
    TradeHistory,
    TradeRecord,
    collect_paper_trades,
    collect_real_trades,
)
from .transfer_collector import MoneyMovement, TransfersRecord, collect_transfers

__all__ = [
    "AccountRecord",
    "AssetBalance",
    "MoneyMovement",
    "OpenPosition",
    "OrderRecord",
    "OrdersRecord",
    "PositionIdReconciliation",
    "PositionsRecord",
    "TradeHistory",
    "TradeRecord",
    "TransfersRecord",
    "collect_account",
    "collect_orders",
    "collect_paper_trades",
    "collect_positions",
    "collect_real_trades",
    "collect_transfers",
    "reconcile_position_ids",
]
