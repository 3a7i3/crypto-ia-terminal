from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from observability import market_radar_snapshot as producer
from tools.prepare_market_catalogue import prepare_catalogue

END = datetime(2026, 10, 29, 5, 32, 36, tzinfo=timezone.utc)


def fixture(tmp_path):
    root = tmp_path / "recovered"
    (root / "databases").mkdir(parents=True)
    names = ["databases/decision_packets_2026-10-28.jsonl",
             "databases/decision_packets_2026-10-29.jsonl"]
    packets = [
        {"symbol": "BTC/USDT", "confidence": 72, "side": "BUY", "regime": "RANGE",
         "created_at": (END - timedelta(seconds=10)).isoformat(), "packet_id": "one",
         "entry_price": 123, "secret": "MUST_NOT_ESCAPE"},
        {"symbol": "ETH/USDT", "confidence": 55, "side": "SELL", "regime": "RANGE",
         "created_at": (END - timedelta(seconds=20)).isoformat(), "packet_id": "two",
         "metadata": {"exchange": "mexc"}},
        {"symbol": "OLD/USDT", "confidence": 99, "side": "BUY", "regime": "RANGE",
         "created_at": (END - timedelta(hours=25)).isoformat(), "packet_id": "old"},
    ]
    for name, rows in zip(names, [packets[:2], packets[2:]]):
        (root / name).write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    reference = producer.build_market_snapshot(source_packets=packets, top_n=20, now_fn=lambda: END.timestamp())
    ref_name = "databases/cryptoradar_market_snapshot.json"
    (root / ref_name).write_text(json.dumps(reference))
    manifest = tmp_path / "received-manifest.json"
    entries = {}
    for name in [*names, ref_name]:
        raw = (root / name).read_bytes()
        entries[name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    manifest.write_text(json.dumps(entries))
    return {
        "source_root": root, "manifest_path": manifest,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "inputs": names, "as_of": END, "window_hours": 24,
        "reference_snapshot": ref_name, "output_dir": tmp_path / "candidate",
    }


def test_real_offline_projection_preserves_inputs_dates_and_unknown_provenance(tmp_path):
    args = fixture(tmp_path)
    before = {p: p.read_bytes() for p in args["source_root"].rglob("*") if p.is_file()}
    report = prepare_catalogue(**args)
    path = args["output_dir"] / "cryptoradar_market_snapshot.json"
    doc = json.loads(path.read_text())
    assert doc["schema_version"] == "1.1.0"
    assert doc["generated_at_utc"] == "2026-10-29T05:32:36Z"
    assert doc["catalogue"]["coverage"]["included_packets"] == 2
    assert doc["catalogue"]["coverage"]["outside_window_packets"] == 1
    assert [r["symbol"] for r in doc["catalogue"]["rows"]] == ["BTC/USDT", "ETH/USDT"]
    assert "ETH/USDT" not in [r["symbol"] for r in doc["catalogue"]["qualified_rows"]]
    assert report["original_v1_0_comparison"]["status"] == "SEMANTIC_MATCH"
    assert report["original_v1_0_comparison"]["proves_original_producer_sha"] is False
    assert report["input_provenance"]["native_venue_claim_counts"] == {"mexc": 1}
    assert report["input_provenance"]["venue_attestation"] == "UNRESOLVED"
    assert report["active_path_written"] is False
    assert path.stat().st_mode & 0o777 == 0o444
    assert args["output_dir"].stat().st_mode & 0o777 == 0o700
    for p, raw in before.items():
        assert p.read_bytes() == raw
    blob = path.read_text()
    for word in ["entry_price", "secret", "MUST_NOT_ESCAPE", "metadata"]:
        assert word not in blob


@pytest.mark.parametrize("change", [
    lambda a: a.update(manifest_sha256="0" * 64),
    lambda a: a.update(as_of=END.replace(tzinfo=None)),
    lambda a: a["inputs"].append(a["inputs"][0]),
    lambda a: a.update(inputs=["../outside.jsonl"]),
    lambda a: a.update(inputs=["databases/operator_snapshot.json"]),
])
def test_invalid_scope_or_provenance_refuses_before_output(tmp_path, change):
    args = fixture(tmp_path)
    change(args)
    with pytest.raises(ValueError):
        prepare_catalogue(**args)
    assert not args["output_dir"].exists()


def test_source_hash_mismatch_cannot_be_published(tmp_path):
    args = fixture(tmp_path)
    (args["source_root"] / args["inputs"][0]).write_text("{}\n")
    with pytest.raises(ValueError, match="manifest"):
        prepare_catalogue(**args)
    assert not args["output_dir"].exists()


def test_malformed_jsonl_is_not_silently_counted_as_a_complete_catalogue(tmp_path):
    args = fixture(tmp_path)
    name = args["inputs"][0]
    (args["source_root"] / name).write_text("{broken\n")
    entries = json.loads(args["manifest_path"].read_text())
    raw = (args["source_root"] / name).read_bytes()
    entries[name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    args["manifest_path"].write_text(json.dumps(entries))
    args["manifest_sha256"] = hashlib.sha256(args["manifest_path"].read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        prepare_catalogue(**args)
    assert not args["output_dir"].exists()


def test_existing_output_and_active_presentation_path_are_refused(tmp_path):
    args = fixture(tmp_path)
    args["output_dir"].mkdir()
    with pytest.raises(ValueError, match="already exist"):
        prepare_catalogue(**args)
    assert list(args["output_dir"].iterdir()) == []
    args["output_dir"] = tmp_path / "presentation"
    with pytest.raises(ValueError, match="presentation"):
        prepare_catalogue(**args)
    assert not args["output_dir"].exists()


def test_symlink_input_and_output_inside_recovered_tree_are_refused(tmp_path):
    args = fixture(tmp_path)
    name = args["inputs"][0]
    path = args["source_root"] / name
    real = tmp_path / "original.jsonl"
    path.rename(real)
    path.symlink_to(real)
    with pytest.raises(ValueError):
        prepare_catalogue(**args)
    assert not args["output_dir"].exists()
    args["output_dir"] = args["source_root"] / "new-output"
    with pytest.raises(ValueError, match="outside the recovered"):
        prepare_catalogue(**args)


def test_explicit_empty_packet_input_never_calls_the_runtime_loader(monkeypatch):
    monkeypatch.setattr(producer.radar_bot, "load_recent_packets",
                        lambda _: pytest.fail("runtime loader called"))
    doc = producer.build_market_snapshot(source_packets=[], include_catalogue=True,
                                         now_fn=lambda: END.timestamp())
    assert doc["catalogue"]["rows"] == []
