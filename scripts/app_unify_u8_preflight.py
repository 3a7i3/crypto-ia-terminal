#!/usr/bin/env python3
"""APP-UNIFY U8 source preflight.

This command is deliberately local-only. It performs no network access, SSH,
systemd action, file mutation, deployment, restart, or secret inspection.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ROOT = "/opt/crypto-ai-terminal/operator"
RUNTIME_ROOT = "/home/mathieu/crypto_ai_terminal"

REQUIRED_FILES = (
    "deploy/app_unify_u8/crypto-operator-api.service",
    "deploy/app_unify_u8/crypto-operator-web.service",
    "deploy/app_unify_u8/requirements-operator-api.txt",
    "deploy/app_unify_u8/requirements-operator-api.lock.txt",
    "frontend/scripts/web01_local_frontend_server.mjs",
    "observability/operator_api/runtime_service_reader.py",
    "observability/operator_api/market_microstructure_reader.py",
    "observability/operator_api/research_lab_reader.py",
    "observability/operator_api/research_strategy_board_reader.py",
)

REQUIRED_API_ENV = (
    "OPERATOR_SNAPSHOT_PATH",
    "OPERATOR_RUNTIME_MANIFEST_PATH",
    "RADAR_MARKET_SNAPSHOT_PATH",
    "PPL_COMPARISON_SNAPSHOT_PATH",
    "FINANCIAL_RECONCILIATION_SNAPSHOT_PATH",
    "BURN_IN_STATUS_SNAPSHOT_PATH",
    "RUNTIME_SERVICE_SNAPSHOT_PATH",
    "MARKET_MICROSTRUCTURE_SNAPSHOT_PATH",
    "RESEARCH_LAB_SNAPSHOT_PATH",
    "RESEARCH_STRATEGY_BOARD_SNAPSHOT_PATH",
)

PATH_OVERRIDE_SOURCES = {
    "observability/operator_api/runtime_service_reader.py":
        "RUNTIME_SERVICE_SNAPSHOT_PATH",
    "observability/operator_api/market_microstructure_reader.py":
        "MARKET_MICROSTRUCTURE_SNAPSHOT_PATH",
    "observability/operator_api/research_lab_reader.py":
        "RESEARCH_LAB_SNAPSHOT_PATH",
    "observability/operator_api/research_strategy_board_reader.py":
        "RESEARCH_STRATEGY_BOARD_SNAPSHOT_PATH",
}


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _pins(text: str):
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            yield name.strip().lower().replace("_", "-"), version.strip()


def validate_source_contract(root: Path) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"MISSING_FILE:{relative}")

    if errors:
        return errors

    api = _read(root, "deploy/app_unify_u8/crypto-operator-api.service")
    web = _read(root, "deploy/app_unify_u8/crypto-operator-web.service")
    frontend = _read(root, "frontend/scripts/web01_local_frontend_server.mjs")

    if f"WorkingDirectory={RELEASE_ROOT}/current" not in api:
        errors.append("API_RELEASE_ROOT_NOT_ISOLATED")
    if f"PYTHONPATH={RELEASE_ROOT}/current" not in api:
        errors.append("API_PYTHONPATH_NOT_ISOLATED")
    if "--host 127.0.0.1 --port 8090" not in api:
        errors.append("API_LOOPBACK_BIND_MISSING")
    if "ProtectHome=read-only" not in api:
        errors.append("API_RUNTIME_DATA_READONLY_HOME_MISSING")
    if f"ReadOnlyPaths={RUNTIME_ROOT}/databases" not in api:
        errors.append("API_RUNTIME_DATA_READONLY_PATH_MISSING")

    if (
        f"Environment=PPL_ACCOUNTING_HISTORY_PATH={RELEASE_ROOT}/presentation/"
        "ppl_accounting_history.json" not in api
    ):
        errors.append("API_EXPLICIT_ARTIFACT_PATH_MISSING:PPL_ACCOUNTING_HISTORY_PATH")

    direct = dict(_pins(_read(root, "deploy/app_unify_u8/requirements-operator-api.txt")))
    locked = dict(_pins(_read(root, "deploy/app_unify_u8/requirements-operator-api.lock.txt")))
    for package, version in direct.items():
        if locked.get(package) != version:
            errors.append(f"LOCK_DOES_NOT_PIN_DIRECT_DEPENDENCY:{package}=={version}")
    if len(locked) <= len(direct):
        errors.append("LOCK_HAS_NO_TRANSITIVE_PINS")

    for name in REQUIRED_API_ENV:
        needle = f"Environment={name}={RUNTIME_ROOT}/databases/"
        if needle not in api:
            errors.append(f"API_EXPLICIT_ARTIFACT_PATH_MISSING:{name}")

    if f"WorkingDirectory={RELEASE_ROOT}/current/frontend" not in web:
        errors.append("WEB_RELEASE_ROOT_NOT_ISOLATED")
    if f"{RELEASE_ROOT}/current/frontend/scripts/web01_local_frontend_server.mjs" not in web:
        errors.append("WEB_RELEASE_SCRIPT_NOT_ISOLATED")

    for label, unit in (("API", api), ("WEB", web)):
        environment_lines = [
            line for line in unit.splitlines() if line.startswith("Environment=")
        ]
        if any("EnvironmentFile=" in line for line in unit.splitlines()):
            errors.append(f"{label}_ENVIRONMENT_FILE_FORBIDDEN")
        sensitive = ("TOKEN=", "PASSWORD=", "API_KEY=", "SECRET=")
        if any(any(marker in line for marker in sensitive) for line in environment_lines):
            errors.append(f"{label}_SECRET_ENV_FORBIDDEN")
        if "0.0.0.0" in unit or "[::]" in unit:
            errors.append(f"{label}_PUBLIC_BIND_FORBIDDEN")

    if 'LOOPBACK_HOST = "127.0.0.1"' not in frontend:
        errors.append("WEB_LOOPBACK_CONTRACT_MISSING")
    if "FRONTEND_PORT = 8181" not in frontend:
        errors.append("WEB_PORT_CONTRACT_MISSING")
    if 'OPERATOR_API_TARGET = "http://127.0.0.1:8090"' not in frontend:
        errors.append("WEB_API_TARGET_CONTRACT_MISSING")
    if 'request.method === "GET" || request.method === "HEAD"' not in frontend:
        errors.append("WEB_GET_HEAD_ONLY_CONTRACT_MISSING")

    for relative, env_name in PATH_OVERRIDE_SOURCES.items():
        if env_name not in _read(root, relative):
            errors.append(f"PATH_OVERRIDE_MISSING:{env_name}")

    return errors


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Development-only escape hatch; never use for a deployment gate.",
    )
    args = parser.parse_args(argv)

    expected = args.expected_sha.strip().lower()
    if not SHA_RE.fullmatch(expected):
        print("APP_UNIFY_U8_PREFLIGHT_FAIL=EXPECTED_SHA_MUST_BE_FULL_40_HEX")
        return 2

    root = Path(__file__).resolve().parents[1]
    try:
        head = _git(root, "rev-parse", "HEAD").lower()
        dirty = bool(_git(root, "status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"APP_UNIFY_U8_PREFLIGHT_FAIL=GIT_UNAVAILABLE:{type(exc).__name__}")
        return 2

    errors = validate_source_contract(root)
    if head != expected:
        errors.append(f"HEAD_MISMATCH:{head}")
    if dirty and not args.allow_dirty:
        errors.append("WORKTREE_DIRTY")

    if errors:
        print(json.dumps({"verdict": "APP_UNIFY_U8_SOURCE_PREFLIGHT_FAIL", "errors": errors}, sort_keys=True))
        return 1

    print(
        json.dumps(
            {
                "verdict": "APP_UNIFY_U8_SOURCE_PREFLIGHT_PASS",
                "source_sha": head,
                "network_actions": 0,
                "runtime_mutations": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
