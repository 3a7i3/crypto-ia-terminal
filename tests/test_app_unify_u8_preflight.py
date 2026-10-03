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
