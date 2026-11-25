"""Peak memory of one radar-batch evaluation against the bytes it reads (SYNTHETIC, offline).

    python -m tests.radar_selection.measure_batch_memory [TOTAL_BYTES ...]

For each target, a SYNTHETIC evidence tree is written to a temporary directory:
the frozen BBO evidence of the repository plus Scanner catalogues inflated with
invented markets (compact JSON, the densest form) until the five catalogues
reach the target together. The batch is built by ``build_batches``, then read and
evaluated in a fresh interpreter under ``tracemalloc``. One line of JSON per target.

This measures the R1-B test capacity (``contract.MAX_BATCH_REF_BYTES``); it does
not certify any production capacity.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.radar_selection import build_batches as bb

ROOT = Path(__file__).resolve().parents[2]


def _compact(doc) -> bytes:
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def inflated_bodies(target_total: int) -> dict:
    """The R1-B catalogues, each grown with invented markets to about target_total / 5 bytes."""
    bodies = bb.catalogue_bodies()
    per = target_total // 5

    def ms(d, i):
        r = copy.deepcopy(d["symbols"][0])
        r.update(symbol=f"Z{i}USDT", baseAsset=f"Z{i}")
        d["symbols"].append(r)

    def mc(d, i):
        r = copy.deepcopy(d["data"][0])
        r.update(symbol=f"Z{i}_USDT", baseCoin=f"Z{i}")
        d["data"].append(r)

    def kp(d, i):
        r = copy.deepcopy(next(iter(d["result"].values())))
        r.update(altname=f"Z{i}USDT", wsname=f"Z{i}/USDT", base=f"Z{i}")
        d["result"][f"Z{i}USDT"] = r

    def ka(d, i):
        d["result"][f"Z{i}"] = {"aclass": "currency", "altname": f"Z{i}", "decimals": 8}

    def kf(d, i):
        r = copy.deepcopy(d["instruments"][0])
        r.update(symbol=f"PF_Z{i}USD", base=f"Z{i}", pair=f"Z{i}:USD")
        d["instruments"].append(r)

    for name, add in (("mexc_spot_exchange_info", ms), ("mexc_contract_detail", mc),
                      ("kraken_asset_pairs", kp), ("kraken_assets", ka), ("kraken_futures_instruments", kf)):
        doc, i = bodies[name], 0
        while len(_compact(doc)) < per:
            add(doc, i)
            i += 1
        if len(_compact(doc)) > per and i:
            # drop the last market added when it overshoots the share
            for key in ("symbols", "data", "instruments"):
                if isinstance(doc.get(key), list):
                    doc[key].pop()
                    break
            else:
                doc["result"].pop(next(reversed(doc["result"])))
    return bodies


def write_tree(target_total: int, out: Path) -> dict:
    """Write an evidence tree (frozen BBO + inflated catalogues + spec + batch) under ``out``."""
    import shutil
    shutil.copytree(bb.EVIDENCE / "bbo", out / "bbo")
    bodies = inflated_bodies(target_total)
    from observability.radar_selection import contract as c
    saved = bb.catalogue_bodies, bb._json, c.MAX_BATCH_REF_BYTES
    # The tree may exceed the cap on purpose: it is built without it, then read with it.
    bb.catalogue_bodies, bb._json, c.MAX_BATCH_REF_BYTES = (lambda: copy.deepcopy(bodies)), _compact, 10**12
    try:
        files = bb.generated(out)
    finally:
        bb.catalogue_bodies, bb._json, c.MAX_BATCH_REF_BYTES = saved
    for rel, data in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return {"catalogue_bytes": sum(len(v) for k, v in files.items()
                                   if k.startswith("scanner/") and not k.endswith("manifest.json"))}


PROBE = r'''
import json, sys, time, tracemalloc
from observability.radar_selection import contract as c, engine, refs
from observability.radar_selection.batch import load_batch, refs as batch_refs
from observability.radar_selection.fixture import RadarRefusal
if len(sys.argv) > 3:
    c.MAX_BATCH_REF_BYTES = int(sys.argv[3])   # informational: what the cap prevents
root = refs.evidence_root(sys.argv[1])
raw = refs.read_ref(root, sys.argv[2], c.TEST_BUDGETS.max_input_bytes)
tracemalloc.start()
t, read, result = time.perf_counter(), None, "EVALUATED"
try:
    doc = load_batch(raw)["doc"]
    blobs = refs.read_all(root, batch_refs(doc), total=c.MAX_BATCH_REF_BYTES)
    read = sum(len(v) for v in blobs.values())
    engine.evaluate_batch(raw, blobs, None, "DEEP_OBSERVATION")
except RadarRefusal as exc:
    result = exc.code
peak = tracemalloc.get_traced_memory()[1]
print(json.dumps({"bytes_read": read, "peak_bytes": peak, "seconds": round(time.perf_counter() - t, 2),
                  "result": result}))
'''


def _probe(tmp: str, cap: int | None = None) -> dict:
    args = [sys.executable, "-c", PROBE, tmp, bb.BATCH] + ([str(cap)] if cap else [])
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True,
                          env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})
    return json.loads(proc.stdout)


def measure(target_total: int, uncapped: bool = False) -> dict:
    """Measured with the real cap; ``uncapped`` adds the same tree read without it (informational)."""
    with tempfile.TemporaryDirectory() as tmp:
        info = write_tree(target_total, Path(tmp))
        out = {"target": target_total, **info, **_probe(tmp)}
        if uncapped:
            out["without_cap"] = _probe(tmp, 10**12)
    return out


def main(argv=None) -> int:
    targets = [int(a) for a in (sys.argv[1:] if argv is None else argv)] or [200_000, 500_000, 700_000, 900_000,
                                                                          1_200_000]
    for t in targets:
        print(json.dumps(measure(t, uncapped=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
