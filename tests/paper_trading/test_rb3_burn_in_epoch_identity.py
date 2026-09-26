"""RB3 — explicit burn-in epoch identity without F00 semantic reuse."""

from __future__ import annotations

import hashlib
import json

import pytest

from paper_trading.ledger_events import LedgerEventType
from paper_trading.ppl_authority_runtime import (
    AuthorityEpochManifest,
    CutoverQuiescence,
    EpochRotationQuiescence,
    _event_id,
    build_burn_in_experiment_manifest,
    build_cutover_manifest,
    build_experiment_manifest,
    load_authority_manifest,
    write_authority_manifest,
)


CODE_SHA = "a" * 40
CONFIG_HASH = "b" * 64
LEGACY = b'{"legacy":"boundary"}\n'
PREDECESSOR = "PPL-AUTH-PREDECESSOR"


def _rotation_quiescence() -> EpochRotationQuiescence:
    return EpochRotationQuiescence(
        authority_open_positions=0,
        authority_pending_orders=0,
        authority_transitions_in_flight=0,
        authority_process_stopped=True,
    )


def _f00() -> AuthorityEpochManifest:
    return build_experiment_manifest(
        paper_epoch_id="F00-EPOCH-TEST",
        created_at=1.0,
        initial_virtual_capital=100.0,
        code_sha=CODE_SHA,
        config_snapshot_hash=CONFIG_HASH,
        legacy_log_bytes=LEGACY,
        quiescence=_rotation_quiescence(),
        predecessor_authority_epoch_id=PREDECESSOR,
    )


def _burn_in() -> AuthorityEpochManifest:
    return build_burn_in_experiment_manifest(
        paper_epoch_id="BURN-IN-EPOCH-TEST",
        created_at=2.0,
        initial_virtual_capital=101.0,
        code_sha=CODE_SHA,
        config_snapshot_hash=CONFIG_HASH,
        legacy_log_bytes=LEGACY,
        quiescence=_rotation_quiescence(),
        predecessor_authority_epoch_id=PREDECESSOR,
    )


def test_existing_transition_and_f00_semantics_remain_v1_v2():
    transition = build_cutover_manifest(
        paper_epoch_id="PPL-AUTH-TEST",
        created_at=1.0,
        initial_virtual_capital=100.0,
        code_sha=CODE_SHA,
        config_snapshot_hash=CONFIG_HASH,
        legacy_log_bytes=LEGACY,
        quiescence=CutoverQuiescence(
            legacy_open_positions=0,
            legacy_pending_orders=0,
            legacy_transitions_in_flight=0,
            legacy_process_stopped=True,
        ),
        predecessor_shadow_epoch_id="SHADOW-PREDECESSOR",
    )
    f00 = _f00()

    assert transition.epoch_role == "PPL_AUTHORITY_TRANSITION"
    assert transition.manifest_schema_version == 1
    assert f00.epoch_role == "F00_EXPERIMENT"
    assert f00.manifest_schema_version == 2


def test_burn_in_manifest_has_explicit_v3_role_and_distinct_event_domain():
    f00 = _f00()
    burn_in = _burn_in()

    assert burn_in.epoch_role == "BURN_IN_EXPERIMENT"
    assert burn_in.manifest_schema_version == 3
    assert burn_in.ppl_event_schema_version == 2

    f00_id = _event_id(f00, LedgerEventType.EPOCH_CREATED, "birth")
    burn_in_id = _event_id(burn_in, LedgerEventType.EPOCH_CREATED, "birth")

    expected_f00 = "f00-" + hashlib.sha256(
        "\x1f".join(
            (
                "F00-EPOCH-AUTHORITY-V1",
                f00.paper_epoch_id,
                LedgerEventType.EPOCH_CREATED.value,
                "birth",
            )
        ).encode("utf-8")
    ).hexdigest()
    expected_burn_in = "burnin-" + hashlib.sha256(
        "\x1f".join(
            (
                "BURN-IN-EPOCH-AUTHORITY-V1",
                burn_in.paper_epoch_id,
                LedgerEventType.EPOCH_CREATED.value,
                "birth",
            )
        ).encode("utf-8")
    ).hexdigest()

    assert f00_id == expected_f00
    assert burn_in_id == expected_burn_in
    assert f00_id != burn_in_id


def test_burn_in_manifest_roundtrip_is_exact_and_write_once(tmp_path):
    manifest = _burn_in()
    path = tmp_path / "burn-in.manifest.json"

    write_authority_manifest(path, manifest)
    raw = json.loads(path.read_text(encoding="utf-8"))

    assert frozenset(raw) == {
        "manifest_schema_version",
        "paper_epoch_id",
        "created_at",
        "initial_virtual_capital",
        "code_sha",
        "config_snapshot_hash",
        "legacy_boundary_sha256",
        "legacy_event_count",
        "epoch_role",
        "ppl_event_schema_version",
        "predecessor_authority_epoch_id",
    }
    assert raw["epoch_role"] == "BURN_IN_EXPERIMENT"
    assert raw["manifest_schema_version"] == 3
    assert load_authority_manifest(path) == manifest

    with pytest.raises(FileExistsError):
        write_authority_manifest(path, manifest)


def test_burn_in_role_cannot_silently_reuse_f00_schema():
    with pytest.raises(ValueError, match="must use schema v3"):
        AuthorityEpochManifest(
            paper_epoch_id="BURN-IN-EPOCH-TEST",
            created_at=1.0,
            initial_virtual_capital=100.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_boundary_sha256="c" * 64,
            legacy_event_count=0,
            predecessor_authority_epoch_id=PREDECESSOR,
            epoch_role="BURN_IN_EXPERIMENT",
            manifest_schema_version=2,
        )
