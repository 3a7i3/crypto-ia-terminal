from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import f00_experiment_config_freeze as freeze


EPOCH = "F00-EPOCH-01-TEST"
SHA = "a" * 40


def _env_files(tmp_path: Path) -> list[Path]:
    base = tmp_path / ".env"
    secrets = tmp_path / ".env.secrets"
    overlay = tmp_path / "f00.cutover.env"

    base.write_text(
        "\n".join(
            [
                "SIGNAL_MIN_SCORE=40",
                "EXEC_MAX_ORDER_USD=50",
                "PB_MAX_POSITIONS=5",
                "PPL_API_SECRET=must-never-appear",
                "EXCHANGE_ID=mexc",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    secrets.write_text(
        "API_KEY=top-secret\nPB_MAX_POSITIONS=3\n",
        encoding="utf-8",
    )
    overlay.write_text(
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
    return [base, secrets, overlay]


def _production_source(tmp_path: Path, source: str) -> None:
    path = tmp_path / "core" / "runtime_config.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _patch_clean_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(freeze, "_require_clean_repo", lambda _root: SHA)


def test_capture_respects_precedence_excludes_secrets_and_resolves_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(
        tmp_path,
        """
import os

SIGNAL = int(os.getenv("SIGNAL_MIN_SCORE", "70"))
RAMP = int(os.getenv("REGIME_RAMP_CYCLES", "4"))
MAX_ORDER = float(os.getenv("EXEC_MAX_ORDER_USD", "50"))
SECRET = os.getenv("PPL_API_SECRET", "never")
""",
    )

    activation_path = tmp_path / "f00.admission.env"
    activation_bytes = b"PB_MAX_POSITIONS=2\n"
    payload = freeze.build_snapshot_payload(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        activation_path=activation_path,
        activation_bytes=activation_bytes,
    )

    params = payload["parameters"]
    assert params["SIGNAL_MIN_SCORE"]["value"] == "40"
    assert params["SIGNAL_MIN_SCORE"]["provenance"] == "EXPLICIT_ENVIRONMENT_FILE"
    assert params["PB_MAX_POSITIONS"]["value"] == "2"
    assert params["PB_MAX_POSITIONS"]["source"] == "f00.admission.env"
    assert payload["prestart_guard"]["PB_MAX_POSITIONS"] == "0"
    assert payload["activation_overlay"]["overrides"]["PB_MAX_POSITIONS"] == "2"
    assert params["REGIME_RAMP_CYCLES"]["value"] == "4"
    assert params["REGIME_RAMP_CYCLES"]["provenance"] == "CODE_DEFAULT"
    assert params["EXEC_MAX_ORDER_USD"]["value"] == "50"

    assert "PPL_API_SECRET" not in params
    assert "API_KEY" not in params
    assert payload["runtime_source_sha"] == SHA
    assert payload["paper_epoch_id"] == EPOCH


def test_unset_conflicting_material_defaults_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(
        tmp_path,
        """
import os

A = int(os.getenv("REGIME_RAMP_CYCLES", "4"))
B = int(os.getenv("REGIME_RAMP_CYCLES", "7"))
""",
    )

    with pytest.raises(freeze.ConfigFreezeError, match="conflicting code defaults"):
        freeze.build_snapshot_payload(
            repo_root=tmp_path,
            env_files=env_files,
            paper_epoch_id=EPOCH,
            activation_path=tmp_path / "f00.admission.env",
            activation_bytes=b"PB_MAX_POSITIONS=2\n",
        )


def test_explicit_value_resolves_conflicting_code_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    env_files[0].write_text(
        env_files[0].read_text(encoding="utf-8") + "REGIME_RAMP_CYCLES=6\n",
        encoding="utf-8",
    )
    _production_source(
        tmp_path,
        """
import os

A = int(os.getenv("REGIME_RAMP_CYCLES", "4"))
B = int(os.getenv("REGIME_RAMP_CYCLES", "7"))
""",
    )

    payload = freeze.build_snapshot_payload(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        activation_path=tmp_path / "f00.admission.env",
        activation_bytes=b"PB_MAX_POSITIONS=2\n",
    )
    assert payload["parameters"]["REGIME_RAMP_CYCLES"]["value"] == "6"
    assert (
        payload["parameters"]["REGIME_RAMP_CYCLES"]["provenance"]
        == "EXPLICIT_ENVIRONMENT_FILE"
    )


def test_unset_nonliteral_default_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(
        tmp_path,
        """
import os

_DEFAULT = "4"
RAMP = int(os.getenv("REGIME_RAMP_CYCLES", _DEFAULT))
""",
    )

    with pytest.raises(freeze.ConfigFreezeError, match="non-literal default"):
        freeze.build_snapshot_payload(
            repo_root=tmp_path,
            env_files=env_files,
            paper_epoch_id=EPOCH,
            activation_path=tmp_path / "f00.admission.env",
            activation_bytes=b"PB_MAX_POSITIONS=2\n",
        )


def test_capture_is_immutable_and_validate_detects_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(
        tmp_path,
        """
import os

RAMP = int(os.getenv("REGIME_RAMP_CYCLES", "4"))
""",
    )
    output = tmp_path / "snapshot.json"
    activation_output = tmp_path / "f00.admission.env"

    document = freeze.capture(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        output=output,
        activation_output=activation_output,
        activation_pb_max_positions=2,
    )
    assert output.exists()
    assert document["snapshot_sha256"] == freeze.snapshot_sha256(
        {k: v for k, v in document.items() if k != "snapshot_sha256"}
    )

    result = freeze.validate(repo_root=tmp_path, snapshot_path=output)
    assert result["snapshot_sha256"] == document["snapshot_sha256"]

    with pytest.raises(freeze.ConfigFreezeError, match="will not be overwritten"):
        freeze.capture(
            repo_root=tmp_path,
            env_files=env_files,
            paper_epoch_id=EPOCH,
            output=output,
            activation_output=activation_output,
            activation_pb_max_positions=2,
        )

    env_files[0].write_text(
        env_files[0].read_text(encoding="utf-8").replace(
            "SIGNAL_MIN_SCORE=40", "SIGNAL_MIN_SCORE=41"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        freeze.ConfigFreezeError,
        match="differs from frozen snapshot",
    ):
        freeze.validate(repo_root=tmp_path, snapshot_path=output)


def test_snapshot_document_contains_no_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(tmp_path, "import os\nX=os.getenv('REGIME_RAMP_CYCLES','4')\n")
    output = tmp_path / "snapshot.json"
    activation_output = tmp_path / "f00.admission.env"

    freeze.capture(
        repo_root=tmp_path,
        env_files=env_files,
        paper_epoch_id=EPOCH,
        output=output,
        activation_output=activation_output,
        activation_pb_max_positions=2,
    )

    raw = output.read_text(encoding="utf-8")
    doc = json.loads(raw)
    assert "must-never-appear" not in raw
    assert "top-secret" not in raw
    assert "PPL_API_SECRET" not in doc["parameters"]


def test_activation_overlay_rejects_extra_material_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(tmp_path, "import os\nX=os.getenv('REGIME_RAMP_CYCLES','4')\n")

    with pytest.raises(freeze.ConfigFreezeError, match="may not change material parameter"):
        freeze.build_snapshot_payload(
            repo_root=tmp_path,
            env_files=env_files,
            paper_epoch_id=EPOCH,
            activation_path=tmp_path / "f00.admission.env",
            activation_bytes=b"PB_MAX_POSITIONS=2\nSIGNAL_MIN_SCORE=99\n",
        )


def test_activation_overlay_requires_positive_pb_max_positions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clean_repo(monkeypatch)
    env_files = _env_files(tmp_path)
    _production_source(tmp_path, "import os\nX=os.getenv('REGIME_RAMP_CYCLES','4')\n")

    with pytest.raises(freeze.ConfigFreezeError, match="must be >= 1"):
        freeze.build_snapshot_payload(
            repo_root=tmp_path,
            env_files=env_files,
            paper_epoch_id=EPOCH,
            activation_path=tmp_path / "f00.admission.env",
            activation_bytes=b"PB_MAX_POSITIONS=0\n",
        )
