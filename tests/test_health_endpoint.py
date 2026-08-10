"""Tests HealthServer — endpoint HTTP /health."""

from __future__ import annotations

import json
import time
import threading
import pytest
import urllib.request
import urllib.error

from quant_hedge_ai.health_endpoint import HealthServer


# ── Fixture partagée ─────────────────────────────────────────────────────────

@pytest.fixture
def server():
    """Démarre un HealthServer sur un port libre, l'arrête après le test."""
    s = HealthServer(port=18765)
    s.start()
    time.sleep(0.05)   # laisser le thread démarrer
    yield s
    s.stop()


def _get(path: str, port: int = 18765) -> dict:
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


# ── Tests cycle de vie ────────────────────────────────────────────────────────

class TestLifecycle:
    def test_start_sets_is_running(self, server):
        assert server.is_running is True

    def test_stop_clears_is_running(self):
        s = HealthServer(port=18766)
        s.start()
        time.sleep(0.05)
        s.stop()
        assert s.is_running is False

    def test_double_start_no_crash(self, server):
        server.start()   # second appel — doit être silencieux
        assert server.is_running is True

    def test_stop_without_start_no_crash(self):
        s = HealthServer(port=18767)
        s.stop()          # jamais démarré — pas d'erreur


# ── Tests /health ─────────────────────────────────────────────────────────────

class TestHealthRoute:
    def test_returns_200(self, server):
        data = _get("/health")
        assert "status" in data

    def test_status_ok_no_components(self, server):
        data = _get("/health")
        assert data["status"] == "ok"

    def test_has_uptime(self, server):
        data = _get("/health")
        assert data["uptime_seconds"] >= 0

    def test_has_timestamp(self, server):
        data = _get("/health")
        assert "timestamp" in data

    def test_components_ok_count(self, server):
        server.update("paper_engine", {"ok": True, "balance": 9800.0})
        data = _get("/health")
        assert data["components_ok"] >= 1

    def test_degraded_component_reflected(self, server):
        server.update("exchange", {"ok": False, "error": "timeout"})
        data = _get("/health")
        assert data["status"] == "degraded"
        assert data["components_degraded"] >= 1

    def test_trailing_slash_ok(self, server):
        data = _get("/health/")
        assert "status" in data


# ── Tests /health/detail ──────────────────────────────────────────────────────

class TestHealthDetail:
    def test_returns_components_dict(self, server):
        server.update("paper_engine", {"balance": 9500.0, "ok": True})
        data = _get("/health/detail")
        assert "paper_engine" in data["components"]

    def test_component_statuses_present(self, server):
        server.update("signal_engine", {"ok": True})
        data = _get("/health/detail")
        assert "component_statuses" in data

    def test_degraded_status_propagated(self, server):
        server.update("risk_gate", {"ok": False})
        data = _get("/health/detail")
        assert data["component_statuses"]["risk_gate"] == "degraded"

    def test_custom_status_field(self, server):
        server.update("pieuvre", {"status": "critical"})
        data = _get("/health/detail")
        assert data["component_statuses"]["pieuvre"] == "critical"


# ── Tests /metrics ────────────────────────────────────────────────────────────

class TestMetrics:
    def test_returns_flat_dict(self, server):
        data = _get("/metrics")
        assert "uptime_seconds" in data
        assert "global_status" in data

    def test_numeric_fields_exported(self, server):
        server.update("paper_engine", {"balance": 9800.0, "ok": True})
        data = _get("/metrics")
        assert "paper_engine_balance" in data
        assert data["paper_engine_balance"] == 9800.0

    def test_private_fields_excluded(self, server):
        server.update("paper_engine", {"balance": 100.0})
        data = _get("/metrics")
        assert not any(k.startswith("_") for k in data)

    def test_non_numeric_fields_excluded(self, server):
        server.update("comp", {"name": "test", "balance": 1.0})
        data = _get("/metrics")
        assert "comp_name" not in data


# ── Tests 404 ─────────────────────────────────────────────────────────────────

class TestNotFound:
    def test_unknown_path_returns_404(self, server):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _get("/unknown")
        assert exc_info.value.code == 404


# ── Tests update / remove ─────────────────────────────────────────────────────

class TestUpdate:
    def test_update_adds_component(self, server):
        server.update("scanner", {"ok": True, "symbols": 10})
        assert "scanner" in server._components

    def test_update_is_thread_safe(self, server):
        errors = []
        def writer(i: int):
            try:
                server.update(f"comp_{i}", {"value": i})
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_remove_component(self, server):
        server.update("temp", {"ok": True})
        server.remove("temp")
        assert "temp" not in server._components

    def test_remove_nonexistent_no_crash(self, server):
        server.remove("does_not_exist")   # ne doit pas lever


# ── Tests status global ───────────────────────────────────────────────────────

class TestGlobalStatus:
    def test_all_ok_gives_ok(self, server):
        server.update("a", {"ok": True})
        server.update("b", {"ok": True})
        assert server._global_status() == "ok"

    def test_one_degraded_gives_degraded(self, server):
        server.update("a", {"ok": True})
        server.update("b", {"ok": False})
        assert server._global_status() == "degraded"

    def test_critical_trumps_degraded(self, server):
        server.update("a", {"ok": False})
        server.update("b", {"status": "critical"})
        assert server._global_status() == "critical"

    def test_empty_components_gives_ok(self):
        s = HealthServer(port=19999)
        assert s._global_status() == "ok"
