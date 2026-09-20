from __future__ import annotations

import hashlib
import json

import pytest

from paper_trading.ppl_authority_runtime import (
    AuthorityManifestError,
    CutoverQuiescence,
    EpochRotationQuiescence,
    build_authority_runtime_from_env,
    build_cutover_manifest,
    build_experiment_manifest,
    load_authority_manifest,
    write_authority_manifest,
)
from paper_trading.ppl_capital import scientific_capital_from_ppl
from tools.cri_calculator import load_clean_trades


TRANSITION_EPOCH = "PPL02E-AUTH-002-TEST"
SHADOW_EPOCH = "PPL02D-SHADOW-002-TEST"
F00_EPOCH = "F00-EPOCH-01-TEST"
LEGACY_BYTES = b'{"event":"CLOSE","trade_id":"legacy"}\n'


def cutover_quiescence() -> CutoverQuiescence:
    return CutoverQuiescence(
        legacy_open_positions=0,
        legacy_pending_orders=0,
        legacy_transitions_in_flight=0,
        legacy_process_stopped=True,
    )


def rotation_quiescence() -> EpochRotationQuiescence:
    return EpochRotationQuiescence(
        authority_open_positions=0,
        authority_pending_orders=0,
        authority_transitions_in_flight=0,
        authority_process_stopped=True,
    )


def transition_manifest():
    return build_cutover_manifest(
        paper_epoch_id=TRANSITION_EPOCH,
        created_at=10.0,
        initial_virtual_capital=100.0,
        code_sha="sha-transition",
        config_snapshot_hash="cfg-transition",
        legacy_log_bytes=LEGACY_BYTES,
        quiescence=cutover_quiescence(),
        predecessor_shadow_epoch_id=SHADOW_EPOCH,
    )


def experiment_manifest():
    return build_experiment_manifest(
        paper_epoch_id=F00_EPOCH,
        created_at=20.0,
        initial_virtual_capital=678.4625,
        code_sha="sha-f00",
        config_snapshot_hash="cfg-f00",
        legacy_log_bytes=LEGACY_BYTES,
        quiescence=rotation_quiescence(),
        predecessor_authority_epoch_id=TRANSITION_EPOCH,
    )


def test_transition_manifest_v1_round_trip_remains_backward_compatible(tmp_path):
    path = tmp_path / "transition.manifest.json"
    manifest = transition_manifest()

    write_authority_manifest(path, manifest)
    loaded = load_authority_manifest(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert loaded == manifest
    assert payload["manifest_schema_version"] == 1
    assert payload["epoch_role"] == "PPL_AUTHORITY_TRANSITION"
    assert payload["predecessor_shadow_epoch_id"] == SHADOW_EPOCH
    assert "predecessor_authority_epoch_id" not in payload


def test_transition_event_identity_domain_is_unchanged(tmp_path):
    path = tmp_path / "transition.manifest.json"
    store_root = tmp_path / "store"
    write_authority_manifest(path, transition_manifest())

    runtime = build_authority_runtime_from_env(
        {
            "PPL_AUTHORITY_MANIFEST": str(path),
            "PPL_AUTHORITY_STORE_ROOT": str(store_root),
            "PPL_AUTHORITY_EPOCH_ID": TRANSITION_EPOCH,
        }
    )
    runtime.bind(now=11.0)

    event = runtime.consistent_view().events[0]
    raw = "\x1f".join(
        (
            "PPL-02E-R4-AUTHORITY-V1",
            TRANSITION_EPOCH,
            "EPOCH_CREATED",
            "epoch",
        )
    )
    expected = f"ppl02e-{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    assert event.event_id == expected


def test_f00_experiment_manifest_v2_round_trip_has_truthful_predecessor(tmp_path):
    path = tmp_path / "f00.manifest.json"
    manifest = experiment_manifest()

    write_authority_manifest(path, manifest)
    loaded = load_authority_manifest(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert loaded == manifest
    assert payload["manifest_schema_version"] == 2
    assert payload["epoch_role"] == "F00_EXPERIMENT"
    assert payload["predecessor_authority_epoch_id"] == TRANSITION_EPOCH
    assert payload["ppl_event_schema_version"] == 2
    assert "predecessor_shadow_epoch_id" not in payload


@pytest.mark.parametrize(
    "quiescence",
    [
        EpochRotationQuiescence(1, 0, 0, True),
        EpochRotationQuiescence(0, 1, 0, True),
        EpochRotationQuiescence(0, 0, 1, True),
        EpochRotationQuiescence(0, 0, 0, False),
    ],
)
def test_f00_experiment_manifest_requires_quiescent_authority_boundary(quiescence):
    with pytest.raises(AuthorityManifestError, match="experiment epoch rotation"):
        build_experiment_manifest(
            paper_epoch_id=F00_EPOCH,
            created_at=20.0,
            initial_virtual_capital=678.4625,
            code_sha="sha-f00",
            config_snapshot_hash="cfg-f00",
            legacy_log_bytes=LEGACY_BYTES,
            quiescence=quiescence,
            predecessor_authority_epoch_id=TRANSITION_EPOCH,
        )


def test_f00_experiment_manifest_requires_authority_predecessor():
    with pytest.raises(ValueError, match="predecessor_authority_epoch_id"):
        build_experiment_manifest(
            paper_epoch_id=F00_EPOCH,
            created_at=20.0,
            initial_virtual_capital=678.4625,
            code_sha="sha-f00",
            config_snapshot_hash="cfg-f00",
            legacy_log_bytes=LEGACY_BYTES,
            quiescence=rotation_quiescence(),
            predecessor_authority_epoch_id="",
        )


def test_manifest_loader_rejects_role_schema_mismatch(tmp_path):
    path = tmp_path / "f00.manifest.json"
    write_authority_manifest(path, experiment_manifest())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["epoch_role"] = "PPL_AUTHORITY_TRANSITION"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        AuthorityManifestError,
        match="unsupported authority manifest role/schema combination",
    ):
        load_authority_manifest(path)


def test_manifest_loader_rejects_partial_experiment_manifest(tmp_path):
    path = tmp_path / "f00.manifest.json"
    write_authority_manifest(path, experiment_manifest())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("predecessor_authority_epoch_id")
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(AuthorityManifestError, match="fields mismatch"):
        load_authority_manifest(path)


def test_f00_runtime_requires_exact_configured_epoch_and_restart_is_idempotent(
    tmp_path,
):
    path = tmp_path / "f00.manifest.json"
    store_root = tmp_path / "store"
    write_authority_manifest(path, experiment_manifest())

    with pytest.raises(AuthorityManifestError, match="does not match"):
        build_authority_runtime_from_env(
            {
                "PPL_AUTHORITY_MANIFEST": str(path),
                "PPL_AUTHORITY_STORE_ROOT": str(store_root),
                "PPL_AUTHORITY_EPOCH_ID": "WRONG-EPOCH",
            }
        )

    env = {
        "PPL_AUTHORITY_MANIFEST": str(path),
        "PPL_AUTHORITY_STORE_ROOT": str(store_root),
        "PPL_AUTHORITY_EPOCH_ID": F00_EPOCH,
    }

    runtime = build_authority_runtime_from_env(env)
    first_state = runtime.bind(now=21.0)
    first_events = runtime.consistent_view().events

    restarted = build_authority_runtime_from_env(env)
    second_state = restarted.bind(now=22.0)
    second_events = restarted.consistent_view().events

    assert first_state.paper_epoch_id == F00_EPOCH
    assert second_state.paper_epoch_id == F00_EPOCH
    assert len(first_events) == 1
    assert second_events == first_events
    assert first_events[0].event_type.value == "EPOCH_CREATED"
    assert first_events[0].schema_version == 2
    assert first_events[0].event_id.startswith("f00-")


def test_f00_rotation_never_mutates_predecessor_epoch_bytes(tmp_path):
    transition_path = tmp_path / "transition.manifest.json"
    experiment_path = tmp_path / "f00.manifest.json"
    store_root = tmp_path / "store"

    write_authority_manifest(transition_path, transition_manifest())
    old_runtime = build_authority_runtime_from_env(
        {
            "PPL_AUTHORITY_MANIFEST": str(transition_path),
            "PPL_AUTHORITY_STORE_ROOT": str(store_root),
            "PPL_AUTHORITY_EPOCH_ID": TRANSITION_EPOCH,
        }
    )
    old_runtime.bind(now=11.0)

    old_epoch_path = (
        store_root
        / "epochs"
        / f"{hashlib.sha256(TRANSITION_EPOCH.encode('utf-8')).hexdigest()}.jsonl"
    )
    old_bytes_before = old_epoch_path.read_bytes()

    write_authority_manifest(experiment_path, experiment_manifest())
    new_runtime = build_authority_runtime_from_env(
        {
            "PPL_AUTHORITY_MANIFEST": str(experiment_path),
            "PPL_AUTHORITY_STORE_ROOT": str(store_root),
            "PPL_AUTHORITY_EPOCH_ID": F00_EPOCH,
        }
    )
    new_runtime.bind(now=21.0)

    assert old_epoch_path.read_bytes() == old_bytes_before
    assert scientific_capital_from_ppl(store_root, F00_EPOCH) == pytest.approx(
        678.4625
    )


def test_f00_scientific_population_remains_exact_epoch(tmp_path, monkeypatch):
    path = tmp_path / "paper_trades.jsonl"
    rows = [
        {
            "event": "CLOSE",
            "trade_id": "keep",
            "ts": 1.0,
            "price": 0.42,
            "pnl_usd": 1.0,
            "source_authority": "PPL",
            "paper_epoch_id": F00_EPOCH,
            "score": 0,
            "regime": "unknown",
        },
        {
            "event": "CLOSE",
            "trade_id": "old",
            "ts": 1.0,
            "price": 0.42,
            "pnl_usd": 2.0,
            "source_authority": "PPL",
            "paper_epoch_id": TRANSITION_EPOCH,
            "score": 0,
            "regime": "unknown",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.setenv("PPL_AUTHORITY_EPOCH_ID", F00_EPOCH)

    assert [row["trade_id"] for row in load_clean_trades(path)] == ["keep"]
