"""SEC-API-01-R1 — dashboard authentication boundary tests."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "scripts" / "dashboard_api.py"


def _load_dashboard(monkeypatch, tmp_path, password: str | None):
    monkeypatch.setenv("DP_LOG_DIR", str(tmp_path))
    if password is None:
        monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("DASHBOARD_PASSWORD", password)

    name = f"sec_api_01_dashboard_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, DASHBOARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_fails_closed_without_password(monkeypatch, tmp_path):
    module = _load_dashboard(monkeypatch, tmp_path, None)

    with TestClient(module.app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert response.json()["detail"] == "dashboard authentication not configured"


def test_dashboard_root_shows_login_when_password_configured(monkeypatch, tmp_path):
    module = _load_dashboard(monkeypatch, tmp_path, "synthetic-test-password")

    with TestClient(module.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "CryptoRadar" in response.text
    assert 'type="password"' in response.text


def test_dashboard_unauthenticated_api_returns_401_not_500(monkeypatch, tmp_path):
    module = _load_dashboard(monkeypatch, tmp_path, "synthetic-test-password")

    with TestClient(module.app) as client:
        response = client.get("/api/status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_dashboard_bad_login_returns_401_not_500(monkeypatch, tmp_path):
    module = _load_dashboard(monkeypatch, tmp_path, "synthetic-test-password")

    with TestClient(module.app) as client:
        response = client.post("/login", data={"password": "wrong-password"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_dashboard_valid_login_sets_session_and_allows_api(monkeypatch, tmp_path):
    password = "synthetic-test-password"
    module = _load_dashboard(monkeypatch, tmp_path, password)

    with TestClient(module.app) as client:
        login = client.post("/login", data={"password": password})
        protected = client.get("/api/status")

    assert login.status_code == 200
    assert login.json() == {"ok": True}
    assert "radar_session" in login.cookies
    assert protected.status_code == 200
