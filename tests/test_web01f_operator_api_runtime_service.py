from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api.app import app

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "scripts" / "systemd" / "crypto-operator-api.service"


def _unit_text() -> str:
    return UNIT.read_text(encoding="utf-8")


def _directives(prefix: str) -> list[str]:
    return [line for line in _unit_text().splitlines() if line.startswith(prefix)]


def test_unit_is_loopback_only_and_uses_certified_operator_app():
    text = _unit_text()
    exec_lines = _directives("ExecStart=")

    assert len(exec_lines) == 1
    exec_start = exec_lines[0]
    assert "/home/mathieu/crypto_ai_terminal/.venv/bin/python -m uvicorn" in exec_start
    assert "observability.operator_api.app:app" in exec_start
    assert "--host 127.0.0.1" in exec_start
    assert "--port 8090" in exec_start
    assert "--reload" not in exec_start
    assert "0.0.0.0" not in exec_start
    assert "::" not in exec_start


def test_unit_has_explicit_read_only_artifact_paths_and_no_secret_store():
    text = _unit_text()
    env_lines = _directives("Environment=")
    env_file_lines = _directives("EnvironmentFile=")

    assert env_file_lines == []
    assert (
        "Environment=OPERATOR_SNAPSHOT_PATH="
        "/home/mathieu/crypto_ai_terminal/databases/operator_snapshot.json"
    ) in env_lines
    assert (
        "Environment=OPERATOR_RUNTIME_MANIFEST_PATH="
        "/home/mathieu/crypto_ai_terminal/databases/operator_runtime_manifest.json"
    ) in env_lines
    assert (
        "Environment=RADAR_MARKET_SNAPSHOT_PATH="
        "/home/mathieu/crypto_ai_terminal/databases/cryptoradar_market_snapshot.json"
    ) in env_lines
    assert "Environment=RADAR_MARKET_STALE_AFTER_S=90" in env_lines

    forbidden = (
        ".env.secrets",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "MEXC_API_KEY",
        "MEXC_API_SECRET",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "KRAKEN_API_KEY",
        "KRAKEN_API_SECRET",
    )
    assert all(token not in text for token in forbidden)


def test_unit_has_no_authority_start_dependency():
    dependency_lines = [
        line
        for line in _unit_text().splitlines()
        if line.startswith(("Wants=", "Requires=", "BindsTo="))
    ]
    assert dependency_lines == []


def test_unit_has_bounded_restart_and_filesystem_hardening():
    text = _unit_text()

    assert "User=mathieu" in text
    assert "WorkingDirectory=/home/mathieu/crypto_ai_terminal" in text
    assert "Restart=on-failure" in text
    assert "RestartSec=10s" in text
    assert "NoNewPrivileges=true" in text
    assert "PrivateTmp=true" in text
    assert "ProtectSystem=full" in text
    assert "StandardOutput=journal" in text
    assert "StandardError=journal" in text


def test_operator_api_exposes_only_get_business_routes():
    business_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/operator/v1/")
        or getattr(route, "path", "") == "/healthz"
    ]

    assert business_routes
    assert {route.path for route in business_routes} >= {
        "/healthz",
        "/api/operator/v1/snapshot",
        "/api/operator/v1/market",
    }
    for route in business_routes:
        assert set(route.methods or ()) <= {"GET"}, route.path


def test_healthz_claims_only_api_transport_readiness():
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_transport_process"] == "ready"
    note = payload["note"].lower()
    assert "no claim" in note
    assert "publisher liveness" in note
