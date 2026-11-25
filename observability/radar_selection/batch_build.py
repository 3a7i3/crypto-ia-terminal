"""R1-B — build a ``radar-batch/1.0.0`` from existing sealed artifacts (offline).

    python -m observability.radar_selection.batch_build --evidence-root DIR \\
        --spec REF --state-dir DIR --out NAME

The operator writes a small spec (``radar-batch-spec/1.0.0``) under the evidence
root: dataset identity, evidence kind, evaluation time, policy, the Scanner run
to reference and its pinned manifest SHA-256, and for each BBO source the pinned
anchor and journal manifest plus the replayed windows to use. The builder only
references and projects; it never parses a catalogue, replays a journal, opens a
connection or writes outside ``--state-dir``. The result is checked by the same
verifier as the Radar before it is written (atomically, never replacing a file).

Exit codes: 0 written, 3 input refused (nothing written), 4 usage error.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import adapter_bbo as bbo
from . import adapter_scanner as scanner
from . import contract as c
from .batch import load_batch, refs, valid_ref, verify_batch
from .fixture import POLICY_KEYS, RadarRefusal, _keys, canonical, sha256_hex, strict_loads

SPEC_SCHEMA = "radar-batch-spec/1.0.0"
SPEC_KEYS = {"spec_schema", "dataset_id", "description", "evidence_kind", "evaluation_time_ms", "policy",
             "source_access", "previous_universe", "scanner_run", "scanner_manifest_sha256", "bbo_sources"}
BBO_SPEC_KEYS = {"pair", "anchor_ref", "anchor_sha256", "manifest_ref", "manifest_sha256", "window_refs"}
MAX_SPEC_BYTES = 200_000


def _pinned_blob(blobs: dict, ref: str, sha: str, code: str) -> bytes:
    data = blobs.get(ref)
    if data is None:
        raise RadarRefusal(f"{code}_MISSING:{ref}")
    if sha256_hex(data) != sha:
        raise RadarRefusal(f"{code}_PIN_MISMATCH:{ref}")
    return data


def spec_refs(spec: dict) -> dict:
    """References a spec needs before the batch exists: {ref: ceiling}."""
    out = {f"{spec['scanner_run']}/manifest.json": c.MAX_ARTIFACT_BYTES}
    for s in spec["bbo_sources"]:
        out[s["anchor_ref"]] = c.MAX_ARTIFACT_BYTES
        out[s["manifest_ref"]] = c.MAX_ARTIFACT_BYTES
        for r in s["window_refs"]:
            out[r] = c.MAX_ARTIFACT_BYTES
    return out


def load_spec(raw: bytes) -> dict:
    spec = strict_loads(raw, MAX_SPEC_BYTES)
    _keys(spec, SPEC_KEYS, "$")
    if spec["spec_schema"] != SPEC_SCHEMA:
        raise RadarRefusal("SPEC_SCHEMA")
    _keys(spec["policy"], POLICY_KEYS, "$.policy")
    if not valid_ref(spec["scanner_run"]):
        raise RadarRefusal("REF_SYNTAX:$.scanner_run")
    if not isinstance(spec["bbo_sources"], list) or len(spec["bbo_sources"]) > c.MAX_BATCH_SOURCES:
        raise RadarRefusal("SOURCES_BOUND")
    for i, s in enumerate(spec["bbo_sources"]):
        _keys(s, BBO_SPEC_KEYS, f"$.bbo_sources[{i}]")
        wr = s["window_refs"]
        if not isinstance(wr, list) or not 1 <= len(wr) <= c.MAX_WINDOWS_PER_OBSERVATION:
            raise RadarRefusal(f"ARTIFACTS_BOUND:$.bbo_sources[{i}]")
        for r in [s["anchor_ref"], s["manifest_ref"], *wr]:
            if not valid_ref(r):
                raise RadarRefusal(f"REF_SYNTAX:$.bbo_sources[{i}]")
    return spec


def build_batch(spec: dict, blobs: dict) -> dict:
    """Pure: spec + bytes of its references -> a verified radar-batch document."""
    run = spec["scanner_run"]
    mraw = _pinned_blob(blobs, f"{run}/manifest.json", spec["scanner_manifest_sha256"], "SCANNER_MANIFEST")
    cat = scanner.catalogue_refs(mraw, run)
    sources, observations = [], []
    for s in spec["bbo_sources"]:
        anchor = bbo.parse(_pinned_blob(blobs, s["anchor_ref"], s["anchor_sha256"], "ANCHOR"), "ANCHOR_MALFORMED")
        entry = bbo.anchor_pair(anchor, s["pair"])
        pv = entry["provenance"]
        if not pv["archive_name"].endswith(".tar.gz"):
            raise RadarRefusal("CORPUS_ID_UNDERIVABLE")
        corpus_id = pv["archive_name"][:-len(".tar.gz")]
        source_id = f"bbo:{corpus_id}"
        manifest = bbo.parse(_pinned_blob(blobs, s["manifest_ref"], s["manifest_sha256"], "BBO_MANIFEST"),
                             "MANIFEST_MALFORMED")
        binding = bbo.bind_manifest(manifest, entry, spec["evidence_kind"])
        windows, artifacts = [], []
        for r in s["window_refs"]:
            data = blobs.get(r)
            if data is None:
                raise RadarRefusal("WINDOW_MISSING:" + r)
            windows.append(bbo.parse(data, "WINDOW_MALFORMED"))
            artifacts.append({"ref": r, "sha256": sha256_hex(data), "bytes": len(data)})
        cov = bbo.check_windows(windows, entry)
        sources.append({
            "source_id": source_id, "kind": "BBO_REPLAY_WINDOWS",
            "producer_module": "observability.radar_composite.bbo_pilot",
            "producer_commit": pv["collection_commit"], "corpus_id": corpus_id, "pair": s["pair"],
            "anchor": {"ref": s["anchor_ref"], "sha256": s["anchor_sha256"]},
            "manifest": {"ref": s["manifest_ref"], "sha256": s["manifest_sha256"]},
            "artifacts": artifacts, "coverage": {"start_ms": cov["start_ms"], "end_ms": cov["end_ms"]},
        })
        observations.extend(bbo.project(source_id, windows, binding))
    batch = {
        "batch_schema": c.BATCH_SCHEMA, "adapter_version": c.ADAPTER_VERSION,
        "dataset_id": spec["dataset_id"], "description": spec["description"],
        "evidence_kind": spec["evidence_kind"], "evaluation_time_ms": spec["evaluation_time_ms"],
        "policy": spec["policy"], **cat, "source_access": spec["source_access"],
        "previous_universe": spec["previous_universe"], "sources": sources,
        "observations": sorted(observations, key=lambda o: (o["venue"], o["market_type"], o["native_symbol"],
                                                             o["source_id"])),
    }
    # Self-check with the Radar's own verifier: a builder never writes a batch the Radar would refuse.
    loaded = load_batch(canonical(batch))
    verified = verify_batch(loaded["doc"], blobs)
    bad = [s for s in verified["inputs"]["sources"] if s["state"] != "VERIFIED"] \
        + verified["inputs"]["refused_observations"]
    if verified["inputs"]["catalogue_manifest"]["state"] != "VERIFIED":
        bad.append(verified["inputs"]["catalogue_manifest"])
    if bad:
        raise RadarRefusal("BUILD_SELF_CHECK:" + str(bad[0].get("reason"))[:80])
    return batch


def _write_new(state_dir: Path, name: str, data: bytes) -> Path:
    if not valid_ref(name) or "/" in name:
        raise RadarRefusal("OUT_NAME")
    dest = state_dir / name
    tmp = state_dir / f".{name}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(tmp, dest)   # never replaces an existing file
    finally:
        os.unlink(tmp)       # an interrupted write leaves nothing behind
    return dest


def main(argv: list | None = None, out=None, err=None) -> int:
    from .refs import evidence_root, read_all, read_ref
    from .terminal import install_offline_guard
    argv = list(sys.argv[1:] if argv is None else argv)
    out, err = out or sys.stdout, err or sys.stderr
    opts = {"--evidence-root": None, "--spec": None, "--state-dir": None, "--out": None}
    while argv and argv[0] in opts and len(argv) >= 2:
        opts[argv[0]] = argv[1]
        argv = argv[2:]
    if argv or any(v is None for v in opts.values()):
        err.write("usage: python -m observability.radar_selection.batch_build --evidence-root DIR "
                  "--spec REF --state-dir DIR --out NAME\n")
        return 4
    try:
        root = evidence_root(opts["--evidence-root"])
        state_dir = Path(opts["--state-dir"])
        install_offline_guard(state_dir, read_roots=[root])
        spec = load_spec(read_ref(root, opts["--spec"], MAX_SPEC_BYTES))
        blobs = read_all(root, spec_refs(spec), total=c.MAX_BATCH_REF_BYTES)
        batch = build_batch(spec, blobs)
        blobs.update(read_all(root, {r: m for r, m in refs(batch).items() if r not in blobs},
                              total=c.MAX_BATCH_REF_BYTES - sum(map(len, blobs.values()))))
        verify_batch(batch, blobs)
        data = canonical(batch)
        dest = _write_new(Path(os.path.realpath(state_dir)), opts["--out"], data)
    except (RadarRefusal, FileExistsError) as exc:
        err.write(f"ENTRÉE REFUSÉE: {exc}\n")
        return 3
    out.write(f"lot écrit : {dest.name} · {len(data)} octets · sha256 {sha256_hex(data)}\n"
              f"sources : {len(batch['sources'])} · observations : {len(batch['observations'])} · "
              f"preuve : {batch['evidence_kind']} · admission : {c.ADMISSION}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
