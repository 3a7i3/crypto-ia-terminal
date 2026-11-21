"""Synthetic store for the read API and the Comparaison view (lot 2). No venue contacted.

Legs (cadence 300 s, 25 h of history ending at T0):
- exchange_a  BTC_USDT   OI in CONTRACTS (0.0001 BTC), funding every 8 h, complete history;
- exchange_b  PF_XBTUSD  OI in BASE, funding every 1 h, 40 min gap in the last hour (partial coverage),
  spot reference not qualified;
- exchange_c  BTC-PERP   OI in CONTRACTS, contract size changed 3 h ago (0.0001 -> 0.001):
  windows across the change and its chart series are not comparable;
- exchange_d  BTCUSDT    declared in the roster, never observed.
"""

import json
from datetime import timedelta
from pathlib import Path

from observability.derivatives_positioning import PositioningStore
from tests.derivatives_positioning.support import T0, iso, ms, obs_a, obs_b, sha

AS_OF_MS = ms(T0) + 30_000
CADENCE_S = 300
STEPS = 25 * 12  # 25 h


def obs_c(at, size, oi):
    doc = obs_a(at, oi=oi)
    doc.update(venue="exchange_c", native_symbol="BTC-PERP")
    doc["provenance"] = {"source": "synthetic:exchange_c/ticker", "payload_sha256": sha("c" + iso(at) + oi)}
    doc["measures"]["open_interest"] = {"value": oi, "unit": "CONTRACTS", "contract_size_base": size}
    doc["measures"]["spot_reference"] = {"unavailable": "NO_SPOT_MARKET_DECLARED"}
    doc["measures"]["index_price"] = {"unavailable": "INDEX_NOT_PUBLISHED"}
    return doc


ROSTER = {
    "_comment": "Synthétique : aucune plateforme contactée.",
    "evidence_kind": "SYNTHETIC", "chart_window_s": 86_400,
    "legs": [
        {"venue": "exchange_a", "native_symbol": "BTC_USDT", "contract_type": "PERPETUAL_LINEAR", "cadence_s": CADENCE_S},
        {"venue": "exchange_b", "native_symbol": "PF_XBTUSD", "contract_type": "PERPETUAL_LINEAR", "cadence_s": CADENCE_S},
        {"venue": "exchange_c", "native_symbol": "BTC-PERP", "contract_type": "PERPETUAL_LINEAR", "cadence_s": CADENCE_S},
        {"venue": "exchange_d", "native_symbol": "BTCUSDT", "contract_type": "PERPETUAL_LINEAR", "cadence_s": CADENCE_S},
    ],
}


def build(data_dir, roster_path=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    docs = []
    for k in range(STEPS + 1):
        at = T0 - timedelta(seconds=(STEPS - k) * CADENCE_S)
        mark = "%d.%d" % (64_000 + k * 3, k % 10)
        docs.append(obs_a(at, oi=str(1_200_000 + k * 150), mark=mark))
        if not 3 <= STEPS - k <= 10:  # 40 min hole in the last hour
            docs.append(obs_b(at, oi="%d.%d" % (120 + k // 10, k % 10), mark=mark))
        changed = STEPS - k <= 36  # last 3 h use the new contract size
        docs.append(obs_c(at, "0.001" if changed else "0.0001", str(125_000 + k * 20 if changed else 1_250_000 + k * 200)))
    with PositioningStore(data_dir, now_ms=lambda: AS_OF_MS) as store:
        result = store.ingest_batch(docs)
        assert result.ok and all(r.status == "INSERTED" for r in result.results)
    roster_path = Path(roster_path or data_dir.parent / "roster.json")
    roster_path.write_text(json.dumps(ROSTER, indent=2), encoding="utf-8")
    return data_dir, roster_path
