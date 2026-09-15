"""WEB-01G source contract: local read-only frontend runtime only."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "scripts" / "systemd" / "crypto-operator-web.service"
SERVER = ROOT / "frontend" / "scripts" / "web01_local_frontend_server.mjs"
SERVICE_MATRIX = ROOT / "scripts" / "claude-service-matrix.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_unit_is_loopback_only_zero_key_and_hardened() -> None:
    text = _text(UNIT)
    assert "User=mathieu" in text
    assert "WorkingDirectory=/home/mathieu/crypto_ai_terminal/frontend" in text
    assert "Environment=PATH=/usr/local/bin:/usr/bin:/bin" in text
    assert "ExecStart=/usr/bin/env node /home/mathieu/crypto_ai_terminal/frontend/scripts/web01_local_frontend_server.mjs" in text
    assert "EnvironmentFile=" not in text
    for forbidden in (".env", "SECRET", "TOKEN", "API_KEY", "API_SECRET", "TELEGRAM", "MEXC", "BINANCE", "KRAKEN", "0.0.0.0", "[::]"):
        assert forbidden not in text
    for required in ("Restart=on-failure", "RestartSec=10s", "NoNewPrivileges=true", "PrivateTmp=true", "ProtectSystem=full", "StandardOutput=journal", "StandardError=journal"):
        assert required in text
    assert not any(line.startswith(("Wants=", "Requires=", "BindsTo=")) for line in text.splitlines())


def test_server_is_fixed_loopback_get_head_proxy_without_runtime_artifact_access() -> None:
    text = _text(SERVER)
    assert 'LOOPBACK_HOST = "127.0.0.1"' in text
    assert "FRONTEND_PORT = 8181" in text
    assert 'OPERATOR_API_TARGET = "http://127.0.0.1:8090"' in text
    assert "0.0.0.0" not in text and "[::]" not in text
    assert 'request.method === "GET" || request.method === "HEAD"' in text
    assert "METHOD_NOT_ALLOWED" in text
    assert "OPERATOR_API_UNAVAILABLE" in text
    assert "isApiPath(url.pathname)" in text
    assert "requested ?? path.join(distRoot, \"index.html\")" in text
    for forbidden in ("databases/", "cryptoradar_market_snapshot", "operator_snapshot", "readFile", "fetch(", "POST", "PUT", "PATCH", "DELETE", "TELEGRAM", "API_KEY", "API_SECRET"):
        assert forbidden not in text


def test_frontend_service_is_registered_in_read_only_service_matrix() -> None:
    text = _text(SERVICE_MATRIX)
    assert 'ServiceSpec("crypto-operator-web.service", "operator_web_local", "interface")' in text
