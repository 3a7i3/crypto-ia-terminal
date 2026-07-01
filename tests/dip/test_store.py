"""Tests DIPStore (core/store.py)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from dip.core.store import DIPStore, LRUCache
from dip.core.types import now_us

# ── LRUCache ──────────────────────────────────────────────────────────────────


class TestLRUCache:

    def test_set_get(self):
        cache: LRUCache[str] = LRUCache(max_entries=3, ttl_seconds=60)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_eviction_max(self):
        cache: LRUCache[str] = LRUCache(max_entries=2, ttl_seconds=60)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")  # k1 doit être évincé
        assert cache.get("k1") is None
        assert cache.get("k2") == "v2"

    def test_ttl_expiry(self):
        import time

        cache: LRUCache[str] = LRUCache(max_entries=10, ttl_seconds=0)
        cache.set("k1", "v1")
        time.sleep(0.01)
        assert cache.get("k1") is None

    def test_delete(self):
        cache: LRUCache[str] = LRUCache(max_entries=10, ttl_seconds=60)
        cache.set("k1", "v1")
        cache.delete("k1")
        assert cache.get("k1") is None

    def test_size(self):
        cache: LRUCache[str] = LRUCache(max_entries=10, ttl_seconds=60)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        assert cache.size() == 2


# ── DIPStore ──────────────────────────────────────────────────────────────────


class TestDIPStore:

    def test_upsert_and_get_decision(self, tmp_store):
        pid = str(uuid.uuid4())
        tmp_store.upsert_decision(
            pid,
            {
                "packet_id": pid,
                "symbol": "ETHUSDT",
                "direction": "SHORT",
                "regime": "TRENDING_DOWN",
                "status": "REJECTED",
                "created_at_us": now_us(),
                "hash": "x",
            },
        )
        row = tmp_store.get_decision(pid)
        assert row is not None
        assert row["symbol"] == "ETHUSDT"
        assert row["status"] == "REJECTED"

    def test_get_decisions_filter_symbol(self, populated_store):
        rows = populated_store.get_decisions(symbol="BTCUSDT")
        assert len(rows) == 10
        for r in rows:
            assert r["symbol"] == "BTCUSDT"

    def test_get_decisions_filter_status(self, populated_store):
        rejected = populated_store.get_decisions(status="REJECTED")
        assert len(rejected) == 8
        approved = populated_store.get_decisions(status="APPROVED")
        assert len(approved) == 2

    def test_get_decisions_limit(self, populated_store):
        rows = populated_store.get_decisions(limit=3)
        assert len(rows) == 3

    def test_count_decisions(self, populated_store):
        total = populated_store.count_decisions()
        assert total == 10

    def test_insert_and_get_alert(self, tmp_store):
        alert_id = f"alert_{uuid.uuid4().hex[:8]}"
        tmp_store.insert_alert(
            {
                "alert_id": alert_id,
                "rule_id": "R01",
                "severity": "HIGH",
                "title": "Test alert",
                "description": "Test description",
                "metric_value": 0.85,
                "threshold": 0.80,
                "layer": None,
                "symbol": None,
                "module": "test",
                "created_at_us": now_us(),
            }
        )
        alerts = tmp_store.get_active_alerts()
        assert any(a["alert_id"] == alert_id for a in alerts)

    def test_acknowledge_alert(self, tmp_store):
        alert_id = f"alert_{uuid.uuid4().hex[:8]}"
        tmp_store.insert_alert(
            {
                "alert_id": alert_id,
                "rule_id": "R01",
                "severity": "WARNING",
                "title": "Test",
                "description": "Ack test",
                "created_at_us": now_us(),
            }
        )
        tmp_store.acknowledge_alert(alert_id, "test_user")
        active = tmp_store.get_active_alerts()
        assert not any(a["alert_id"] == alert_id for a in active)

    def test_insert_audit(self, tmp_store):
        tmp_store.insert_audit(
            {
                "trail_id": str(uuid.uuid4()),
                "entity_id": "pkt_001",
                "action_type": "GRAPH_BUILT",
                "module": "test",
                "user_id": None,
                "details_json": "{}",
                "created_at_us": now_us(),
            }
        )
        trail = tmp_store.get_audit_trail("pkt_001")
        assert len(trail) == 1

    def test_upsert_knowledge(self, tmp_store):
        tmp_store.upsert_knowledge(
            {
                "entry_id": "entry_001",
                "entry_type": "REJECTION_CLUSTER",
                "description": "Test pattern",
                "frequency": 0.75,
                "sample_size": 100,
                "confidence": 0.80,
                "layers_involved": '["NoTradeLayer"]',
                "symbols": '["BTCUSDT"]',
                "regimes": '["SIDEWAYS"]',
                "first_seen_us": now_us(),
                "last_seen_us": now_us(),
                "trend": "STABLE",
            }
        )
        entries = tmp_store.get_knowledge()
        assert len(entries) == 1
        assert entries[0]["description"] == "Test pattern"

    def test_singleton_pattern(self, tmp_path):
        DIPStore._instance = None
        db = tmp_path / "s1.sqlite"
        s1 = DIPStore.instance(db_path=db)
        s2 = DIPStore.instance()
        assert s1 is s2
        DIPStore._instance = None
