"""RB3 — burn-in config identity reuses the certified deterministic freeze engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import burn_in_experiment_config_freeze as burn_freeze
from scripts import f00_experiment_config_freeze as f00_freeze


EPOCH = "BURN-IN-EPOCH-TEST"
SHA = "d" * 40


def _env_files(tmp_path: Path) -> list[Path]:
    env = tmp_path / "runtime.env"
    env.write_text(
        "\n".join(
            [
                "PAPER_LIFECYCLE_AUTHORITY=PPL_AUTHORITY",
                "PAPER_TRADING_ENABLED=true",
                "PB_MAX_POSITIONS=0",
                f"PPL_AUTHORITY_EPOCH_ID={EPOCH}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return [env]


def test_burn_in_schema_changes_identity_not_freeze_algorithm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(f00_freeze, "_require_clean_repo", lambda _root: SHA)
    env_files = _env_files(tmp_path)
    activation = tmp_path / "burn-in.admission.env"
    activation_bytes = b"PB_MAX_POSITIONS=2\n"

    f00_payload = f00_freeze.build_snapshot_payload(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        activation_path=activation,
        activation_bytes=activation_bytes,
    )
    burn_payload = burn_freeze.build_snapshot_payload(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        activation_path=activation,
        activation_bytes=activation_bytes,
    )

    assert f00_payload["snapshot_schema"] == "F00_EXPERIMENT_CONFIG_V1"
    assert burn_payload["snapshot_schema"] == "BURN_IN_EXPERIMENT_CONFIG_V1"

    f00_without_schema = dict(f00_payload)
    burn_without_schema = dict(burn_payload)
    f00_without_schema.pop("snapshot_schema")
    burn_without_schema.pop("snapshot_schema")
    assert burn_without_schema == f00_without_schema

    assert burn_freeze.snapshot_sha256(burn_payload) != (
        f00_freeze.snapshot_sha256(f00_payload)
    )


def test_burn_in_capture_validate_is_immutable_and_rejects_f00_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(f00_freeze, "_require_clean_repo", lambda _root: SHA)
    env_files = _env_files(tmp_path)
    output = tmp_path / "burn-in-config.json"
    activation = tmp_path / "burn-in.admission.env"

    document = burn_freeze.capture(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        output=output,
        activation_output=activation,
        activation_pb_max_positions=2,
    )
    assert document["snapshot_schema"] == "BURN_IN_EXPERIMENT_CONFIG_V1"
    assert burn_freeze.validate(
        repo_root=tmp_path, snapshot_path=output
    )["snapshot_sha256"] == document["snapshot_sha256"]

    with pytest.raises(f00_freeze.ConfigFreezeError, match="unsupported snapshot schema"):
        f00_freeze.validate(repo_root=tmp_path, snapshot_path=output)

    with pytest.raises(f00_freeze.ConfigFreezeError, match="will not be overwritten"):
        burn_freeze.capture(
            repo_root=tmp_path,
            env_files=env_files,
            paper_epoch_id=EPOCH,
            output=output,
            activation_output=activation,
            activation_pb_max_positions=2,
        )
