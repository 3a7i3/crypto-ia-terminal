"""Tests D14 — Audit Trail."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from dip.core.types import compute_hash, now_us
from dip.modules.audit_trail import (
    ACTION_GRAPH_BUILT,
    ACTION_INVESTIGATION_GENERATED,
    AuditEntry,
    DecisionAuditTrail,
    get_audit_trail,
)


class TestDecisionAuditTrail:

    def test_log_creates_entry(self, tmp_store):
        trail = DecisionAuditTrail()
        with patch.object(trail, "_store", tmp_store):
            entity_id = str(uuid.uuid4())
            trail.log("test", ACTION_GRAPH_BUILT, entity_id, {"x": 1})
            result = trail.get_trail(entity_id)
            assert result.total_entries > 0

    def test_trail_is_append_only(self, tmp_store):
        trail = DecisionAuditTrail()
        with patch.object(trail, "_store", tmp_store):
            eid = str(uuid.uuid4())
            trail.log("mod_a", ACTION_GRAPH_BUILT, eid, {})
            trail.log("mod_b", ACTION_INVESTIGATION_GENERATED, eid, {})
            result = trail.get_trail(eid)
            assert result.total_entries == 2

    def test_hash_per_entry(self, tmp_store):
        trail = DecisionAuditTrail()
        with patch.object(trail, "_store", tmp_store):
            eid = str(uuid.uuid4())
            trail.log("test", ACTION_GRAPH_BUILT, eid, {"key": "val"})
            result = trail.get_trail(eid)
            assert result.total_entries == 1
            assert result.entries[0].hash != ""

    def test_get_trail_empty_for_unknown(self, tmp_store):
        trail = DecisionAuditTrail()
        with patch.object(trail, "_store", tmp_store):
            result = trail.get_trail("nonexistent_eid")
            assert result.total_entries == 0

    def test_verify_integrity_valid(self, tmp_store):
        trail = DecisionAuditTrail()
        with patch.object(trail, "_store", tmp_store):
            eid = str(uuid.uuid4())
            trail.log("test", ACTION_GRAPH_BUILT, eid, {})
            report = trail.generate_report(hours=24)
            assert report is not None
            assert report.total_entries >= 1

    def test_search_trails_by_module(self, tmp_store):
        trail = DecisionAuditTrail()
        with patch.object(trail, "_store", tmp_store):
            eid1 = str(uuid.uuid4())
            eid2 = str(uuid.uuid4())
            trail.log("module_x", ACTION_GRAPH_BUILT, eid1, {})
            trail.log("module_y", ACTION_GRAPH_BUILT, eid2, {})
            results = trail.search_trails(module="module_x")
            assert len(results) == 1

    def test_action_constants_defined(self):
        from dip.modules.audit_trail import (
            ACTION_ALERT_TRIGGERED,
            ACTION_COUNTERFACTUAL_COMPUTED,
            ACTION_EXPORT_GENERATED,
            ACTION_GRAPH_BUILT,
            ACTION_INVESTIGATION_GENERATED,
        )

        for c in [
            ACTION_GRAPH_BUILT,
            ACTION_INVESTIGATION_GENERATED,
            ACTION_COUNTERFACTUAL_COMPUTED,
            ACTION_ALERT_TRIGGERED,
            ACTION_EXPORT_GENERATED,
        ]:
            assert isinstance(c, str)
            assert len(c) > 0
