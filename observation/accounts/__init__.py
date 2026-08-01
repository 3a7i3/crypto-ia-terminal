"""observation/accounts/ — collecteurs de comptes réels (ADR-0019, Phase A).

Observateur **strictement passif** : il lit, il mesure, il rend des
structures de données. Il ne passe jamais d'ordre, ne modifie jamais un
portefeuille, ne modifie jamais une configuration, ne décide jamais.

Périmètre de ce package (ticket T2) :
  - `_common`  : primitives partagées (mapping `side`, poussière, origine…)

Hors périmètre, explicitement :
  - persistance JSONL, rotation, rétention, Event Ledger et Event ID → **T3** ;
  - vues Telegram → T4 ;
  - toute alerte, tout verdict, toute détection d'anomalie → **Phase B,
    NON autorisée** sous la signature de l'ADR-0019 (invariant OBS-I).

Les collecteurs sont des fonctions pures ``(client) -> enregistrement`` :
aucun état partagé, aucun cache, aucun client construit implicitement quand
un client est injecté. Les tests injectent tous un faux client ccxt.
"""

from __future__ import annotations
