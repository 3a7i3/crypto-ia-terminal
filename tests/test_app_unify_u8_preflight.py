from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from scripts.app_unify_u8_preflight import validate_source_contract


ROOT = Path(__file__).resolve().parents[1]


def test_u8_source_package_contract_is_self_consistent():
    assert validate_source_contract(ROOT) == []


@pytest.mark.parametrize(
    ("module_name", "attribute", "env_name"),
    [
        (
            "observability.operator_api.runtime_service_reader",
            "DEFAULT_RUNTIME_SERVICE_PATH",
            "RUNTIME_SERVICE_SNAPSHOT_PATH",
        ),
        (
            "observability.operator_api.market_microstructure_reader",
            "DEFAULT_PATH",
            "MARKET_MICROSTRUCTURE_SNAPSHOT_PATH",
        ),
        (
            "observability.operator_api.research_lab_reader",
            "DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH",
            "RESEARCH_LAB_SNAPSHOT_PATH",
        ),
        (
            "observability.operator_api.research_strategy_board_reader",
            "DEFAULT_PATH",
            "RESEARCH_STRATEGY_BOARD_SNAPSHOT_PATH",
        ),
    ],
)
def test_u8_artifact_readers_support_explicit_paths(
    monkeypatch, tmp_path, module_name, attribute, env_name
):
    target = tmp_path / f"{env_name.lower()}.json"
    monkeypatch.setenv(env_name, str(target))
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    try:
        assert getattr(module, attribute) == target
    finally:
        sys.modules.pop(module_name, None)


def test_u8_preflight_requires_explicit_accounting_history_path(tmp_path):
    for relative in (
        "deploy/app_unify_u8/crypto-operator-api.service",
        "deploy/app_unify_u8/crypto-operator-web.service",
        "deploy/app_unify_u8/requirements-operator-api.txt",
        "deploy/app_unify_u8/requirements-operator-api.lock.txt",
        "frontend/scripts/web01_local_frontend_server.mjs",
        "observability/operator_api/runtime_service_reader.py",
        "observability/operator_api/market_microstructure_reader.py",
        "observability/operator_api/research_lab_reader.py",
        "observability/operator_api/research_strategy_board_reader.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (ROOT / relative).read_text(encoding="utf-8")
        if relative.endswith("crypto-operator-api.service"):
            text = "\n".join(
                line for line in text.splitlines()
                if "PPL_ACCOUNTING_HISTORY_PATH" not in line
            )
        target.write_text(text, encoding="utf-8")
    assert (
        "API_EXPLICIT_ARTIFACT_PATH_MISSING:PPL_ACCOUNTING_HISTORY_PATH"
        in validate_source_contract(tmp_path)
    )


def test_u8_preflight_rejects_lock_that_drifts_from_direct_pins(tmp_path):
    import shutil

    for relative in (
        "deploy/app_unify_u8/crypto-operator-api.service",
        "deploy/app_unify_u8/crypto-operator-web.service",
        "deploy/app_unify_u8/requirements-operator-api.txt",
        "deploy/app_unify_u8/requirements-operator-api.lock.txt",
        "frontend/scripts/web01_local_frontend_server.mjs",
        "observability/operator_api/runtime_service_reader.py",
        "observability/operator_api/market_microstructure_reader.py",
        "observability/operator_api/research_lab_reader.py",
        "observability/operator_api/research_strategy_board_reader.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, target)
    lock = tmp_path / "deploy/app_unify_u8/requirements-operator-api.lock.txt"
    lock.write_text(lock.read_text().replace("fastapi==", "fastapi==0.0.0+drift#", 1))
    assert any(
        error.startswith("LOCK_DOES_NOT_PIN_DIRECT_DEPENDENCY:fastapi")
        for error in validate_source_contract(tmp_path)
    )


def test_u8_preflight_rejects_unvalidated_web_port_override(tmp_path):
    # M1-C5 F1-b: the pre-reconciliation form `Number(process.env.CAT_WEB_PORT || 8181)`
    # must be refused, as must a server without the Radar Spot loopback target.
    import shutil

    for relative in (
        "deploy/app_unify_u8/crypto-operator-api.service",
        "deploy/app_unify_u8/crypto-operator-web.service",
        "deploy/app_unify_u8/requirements-operator-api.txt",
        "deploy/app_unify_u8/requirements-operator-api.lock.txt",
        "frontend/scripts/web01_local_frontend_server.mjs",
        "observability/operator_api/runtime_service_reader.py",
        "observability/operator_api/market_microstructure_reader.py",
        "observability/operator_api/research_lab_reader.py",
        "observability/operator_api/research_strategy_board_reader.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, target)
    assert validate_source_contract(tmp_path) == []
    server = tmp_path / "frontend/scripts/web01_local_frontend_server.mjs"
    text = server.read_text(encoding="utf-8")
    server.write_text(
        text.replace(
            "export const FRONTEND_PORT = 8181;",
            "export const FRONTEND_PORT = Number(process.env.CAT_WEB_PORT || 8181);",
        ).replace('SPOT_RADAR_API_TARGET = "http://127.0.0.1:18906"', 'SPOT_RADAR_API_TARGET = "http://10.0.0.1:18906"'),
        encoding="utf-8",
    )
    errors = validate_source_contract(tmp_path)
    assert "WEB_PORT_CONTRACT_MISSING" in errors
    assert "WEB_PORT_OVERRIDE_VALIDATION_MISSING" in errors
    assert "WEB_SPOT_RADAR_TARGET_CONTRACT_MISSING" in errors
