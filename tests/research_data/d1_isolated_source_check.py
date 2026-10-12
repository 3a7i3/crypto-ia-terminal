"""Synthetic-only source isolation check; never a governed real-data runner."""

import hashlib
import json
import socket  # noqa: F401 -- preload before denying socket and file IO.
import sys
import types
from pathlib import Path

root = Path(__file__).resolve().parents[2]
example = json.loads(
    (root / "docs/research/paper_stress_404/D1_E_SYNTHETIC_EXAMPLE.json").read_text()
)
pins = {
    "stress_d1_evidence_contract": "22a46c388d6dee90582e6bc407f8dbfb39103c9125888d92e828306150393636",
    "stress_d1_producer_attempts": "6fdaac443bb19245801b2f54f0fae5daf2bb5a59430a6722bb2f31a4c33792b7",
    "stress_d1_durability": "1bc36290ccd29b8ed6192057e87d36040ecc92f3150c0a77206fa1b5bbb0e5e6",
}
pkg = types.ModuleType("research_data")
pkg.__path__ = []
sys.modules["research_data"] = pkg
for name, pin in pins.items():
    path = root / "research_data" / (name + ".py")
    source = path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == pin
    module = types.ModuleType("research_data." + name)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(source, str(path), "exec"), module.__dict__)


def deny_io(event, args):
    if event == "open" or event.startswith("socket."):
        raise RuntimeError("ISOLATED_SOURCE_CHECK_IO_DENIED")


sys.addaudithook(deny_io)
assert example["evidence_kind"] == "SYNTHETIC_METHOD_ONLY_NOT_RUNTIME_PROOF"
encoded = example["bundle_bytes_utf8"]
args = {
    "roster_bytes": encoded["roster"].encode(),
    "receipt_bytes": encoded["receipts"].encode(),
    "record_bytes": encoded["records"].encode(),
    "fsync_witness_bytes": encoded["fsync"].encode(),
    "boundary": example["boundary"],
    "fence": example["fence"],
    "expected_hashes": example["expected_hashes"],
}
result = sys.modules["research_data.stress_d1_durability"].verify_durability_chains(
    **args
)
assert result == example["output"]
b = example["boundary"]
r = {
    "boundary": b,
    "roster_id": "r1",
    "cycle_id": "c1",
    "symbol": "BTC",
    "selected_for_analysis": True,
    "selected_at": "2026-10-10T23:59:59Z",
    "attempt_ids": ["a1"],
}
c = {
    "boundary": b,
    "roster_id": "r1",
    "cycle_id": "c1",
    "symbol": "BTC",
    "attempt_id": "a1",
    "started_at": "2026-10-10T23:59:59Z",
    "ended_at": "2026-10-11T00:00:00Z",
    "outcome": "RETURN_NO_PACKET",
    "packet_id": None,
}
accounted = sys.modules[
    "research_data.stress_d1_producer_attempts"
].reconcile_producer_attempts([r], [c], [], boundary=b)
assert accounted["counts"]["PROVEN_RETURN_NO_PACKET"] == 1
assert accounted["paper_stress_runtime_go"] == "DENIED"
assert not any(
    m.startswith(("paper_trading", "runtime", "observability", "core"))
    for m in sys.modules
)
print(
    json.dumps(
        {
            "isolated_source_check": "PASS",
            "explicit_source_hashes": pins,
            "synthetic_chain_output_matches": True,
            "runtime_modules_loaded": False,
            "io_allowed_during_calls": False,
        }
    )
)
