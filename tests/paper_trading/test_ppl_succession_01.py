"""PPL-SUCCESSION-01 — interrupted predecessor succession (offline, synthetic).

Contract: docs/contracts/PPL_SUCCESSION_01_INTERRUPTED_PREDECESSOR.md.
Every ledger/store here is synthetic and lives in a temporary directory.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import math
import multiprocessing
import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from paper_trading import durable_event_store as ppl_wire
from paper_trading import ppl_admission_gate as gate_module
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import (
    LedgerEventType,
    make_position_opened_event,
    make_position_unresolved_event,
)
from paper_trading.ppl_admission_gate import (
    OPEN_DECISION_SCHEMA,
    AdmissionGate,
    AdmissionGateRefusal,
)
from paper_trading.ppl_authority_runtime import (
    AuthorityEpochManifest,
    AuthorityManifestError,
    CutoverQuiescence,
    EpochRotationQuiescence,
    PPLAuthorityRuntime,
    _event_id,
    authority_manifest_sha256,
    build_burn_in_experiment_manifest,
    build_cutover_manifest,
    build_experiment_manifest,
    load_authority_manifest,
    write_authority_manifest,
)
from paper_trading.ppl_interrupted_succession import (
    CAPITAL_DECISION_SCHEMA,
    DECISION_KIND,
    DECISION_SCHEMA,
    EXCLUSIVITY_SCHEMA,
    REQUIRED_EVIDENCE_ROLES,
    REQUIRED_EXCLUSIVITY_OBSERVATIONS,
    ActivationClearance,
    SuccessionRefusal,
    build_interrupted_successor_manifest,
    issue_activation_clearance,
    issue_resume_clearance,
    validate_clearance_for_use,
    verify_interruption_evidence,
)
from research_data.paper_exporter import export_paper_dataset
from tests.research_data import test_rl_data_01_exporter as fixtures

CODE_SHA = "a" * 40
CONFIG_HASH = "b" * 64
LEGACY = b'{"legacy":"boundary"}\n'
PRED_EPOCH = "PRED-INTERRUPTED-EPOCH"
SUCC_EPOCH = "SUCCESSOR-EPOCH-TEST"
NOW = 1_800_000_000.0


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _js(obj) -> bytes:
    return json.dumps(obj, sort_keys=True).encode("utf-8")


# --------------------------------------------------------------- fixtures


def _canon(obj) -> bytes:
    return json.dumps(
        obj, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _tail_events(variant: str):
    """Events appended to the exporter fixture (3 events: created, open, close)."""
    epoch = PRED_EPOCH
    tail = []
    for idx, trade in enumerate(("trade-2", "trade-3")):
        tail.append(
            make_position_opened_event(
                event_id=f"ev-open-{trade}",
                paper_epoch_id=epoch,
                sequence=4 + idx,
                timestamp=30.0 + idx,
                trade_id=trade,
                symbol=f"S{idx}/USDT",
                side="LONG",
                principal=10.0,
                entry_price=100.0,
                entry_fee=0.01,
                decision_id=f"packet-{trade}",
                schema_version=2,
                tp_price=120.0,
                sl_price=90.0,
                timeout_at=100.0,
                recovery_eligible_until=200.0,
            )
        )
    unresolved = ("trade-2", "trade-3") if variant == "interrupted" else ("trade-2",)
    for idx, trade in enumerate(unresolved):
        tail.append(
            make_position_unresolved_event(
                event_id=f"ev-unres-{trade}",
                paper_epoch_id=epoch,
                sequence=6 + idx,
                timestamp=60.0 + idx,
                trade_id=trade,
                reason="recovery_window_expired",
                schema_version=2,
            )
        )
    return tail


def _export_native(tmp: Path, variant: str = "interrupted", *, burn_in: bool = True):
    """A real export produced by ``research_data.paper_exporter`` (no hand-made schema)."""
    with mock.patch.object(fixtures, "EPOCH", PRED_EPOCH):
        source = fixtures._fixture(tmp / "fixture")
        with source["epoch_path"].open("ab") as handle:
            for event in _tail_events(variant):
                handle.write(ppl_wire._canonical_line(event))
        if burn_in:
            fixtures._promote_fixture_identity_to_burn_in(source)
        request = fixtures._burn_in_capture_request(
            source, tmp / "capture", extracted_at="2026-09-26T03:30:00Z"
        )
        result = export_paper_dataset(request)
    return fixtures._tree_bytes(result.dataset_path)


def _reseal(dataset: dict) -> None:
    """Recompute the identity hashes after a mutation, so only a *semantic*
    native check can refuse (a document coherent with its own hashes)."""
    boundary_id = _sha(_canon(dataset["source_boundary_identity"]))
    dataset["source_boundary_id"] = boundary_id
    identity = dataset["dataset_identity"]
    identity["source_boundary_id"] = boundary_id
    for item in identity["components"]:
        if item.get("name") == "authoritative_core":
            item["source_boundary_id"] = boundary_id
    dataset["dataset_id"] = _sha(_canon(identity))


class Bundle:
    """All byte-level inputs of a valid succession, individually mutable."""

    def __init__(self, tmp_path: Path, variant: str = "interrupted", *, burn_in: bool = True):
        self.tmp = tmp_path
        self.files = _export_native(tmp_path, variant, burn_in=burn_in)
        self.ledger = self.files["authoritative/ppl_events.jsonl"]
        ledger_sha = _sha(self.ledger)
        self.artifacts = {
            "closure_dossier": b"dossier bytes",
            "approved_archive": b"archive bytes",
            "closure_comment_body": b"comment body bytes",
        }
        self.dataset = json.loads(self.files["manifest.json"])
        self.dataset_id = self.dataset["dataset_id"]
        count = len(self.ledger.splitlines())
        self.decision = {
            "schema": DECISION_SCHEMA,
            "decision_kind": DECISION_KIND,
            "predecessor_paper_epoch_id": PRED_EPOCH,
            "predecessor_ledger_sha256": ledger_sha,
            "predecessor_dataset_id": self.dataset_id,
            "predecessor_event_count": count,
            "acknowledged_unknowns": {
                "pending_order_count": "UNKNOWN",
                "lifecycle_transitions_in_flight": "UNKNOWN",
            },
            "fin_status": "UNRESOLVED",
            "certified_equity": None,
            "unresolved_capital": 20.0 if variant == "interrupted" else 10.0,
            "evidence_sha256": {k: _sha(v) for k, v in self.artifacts.items()},
            "decided_by": "operator",
            "decided_at_utc": "2026-11-08T00:00:00Z",
        }
        self.capital = {
            "schema": CAPITAL_DECISION_SCHEMA,
            "successor_paper_epoch_id": SUCC_EPOCH,
            "initial_virtual_capital": 1000.0,
            "provenance": "OPERATOR_DECLARED_NOMINAL",
            "decided_by": "operator",
            "decided_at_utc": "2026-11-08T00:00:00Z",
        }

    def kwargs(self) -> dict:
        return {
            "ledger_bytes": self.ledger,
            "dataset_files": {**self.files, "manifest.json": _js(self.dataset)},
            "operator_decision_bytes": _js(self.decision),
            "evidence_artifacts": dict(self.artifacts),
            "successor_paper_epoch_id": SUCC_EPOCH,
            "capital_decision_bytes": _js(self.capital),
        }

    def record(self):
        return verify_interruption_evidence(**self.kwargs())


@pytest.fixture
def bundle(tmp_path):
    return Bundle(tmp_path)


def _manifest(record):
    return build_interrupted_successor_manifest(
        record=record, created_at=5.0, code_sha=CODE_SHA, config_snapshot_hash=CONFIG_HASH
    )


class Exclusivity:
    def __init__(self, tmp_path: Path, bundle: Bundle, record, manifest):
        self.pred_root = tmp_path / "pred-store"
        self.succ_root = tmp_path / "succ-store"
        self.pred_root.mkdir(exist_ok=True)
        self.ledger_now = bundle.ledger
        self.record = record
        self.manifest = manifest
        self.proof, self.artifacts = self.build("BOOTSTRAP", NOW)

    def build(self, purpose: str, now: float):
        names = [
            n
            for n in REQUIRED_EXCLUSIVITY_OBSERVATIONS
            if purpose == "BOOTSTRAP" or n != "successor_store_empty_or_absent"
        ]
        artifacts = {n: f"proof {n} {purpose} {now}".encode() for n in names}
        proof = {
            "schema": EXCLUSIVITY_SCHEMA,
            "purpose": purpose,
            "successor_paper_epoch_id": SUCC_EPOCH,
            "manifest_sha256": authority_manifest_sha256(self.manifest),
            "record_sha256": self.record.record_sha256,
            "predecessor_ledger_sha256": self.record.predecessor_ledger_sha256,
            "predecessor_store_root": str(self.pred_root.resolve()),
            "successor_store_root": str(self.succ_root.resolve()),
            "observations": {
                n: {
                    "result": "PASS",
                    "observed_at": now - 10.0,
                    "observer": "operator-readonly",
                    "method": "synthetic",
                    "evidence_sha256": _sha(artifacts[n]),
                }
                for n in names
            },
        }
        return proof, artifacts

    def args(self, **over):
        args = {
            "manifest": self.manifest,
            "record": self.record,
            "proof_bytes": _js(self.proof),
            "observation_artifacts": dict(self.artifacts),
            "predecessor_ledger_bytes_now": self.ledger_now,
            "predecessor_store_root": self.pred_root,
            "successor_store_root": self.succ_root,
            "now": NOW,
        }
        args.update(over)
        return args

    def issue(self, **over):
        return issue_activation_clearance(**self.args(**over))

    def issue_resume(self, now: float, **over):
        proof, artifacts = self.build("RESUME", now)
        args = self.args(
            proof_bytes=_js(proof), observation_artifacts=artifacts, now=now
        )
        args.update(over)
        return issue_resume_clearance(**args)


# -------------------------------------------- T1/T2: existing gate unchanged


def test_t1_existing_quiescence_refusals_unchanged():
    bad = EpochRotationQuiescence(0, 0, 0, False)
    for build in (build_experiment_manifest, build_burn_in_experiment_manifest):
        with pytest.raises(AuthorityManifestError):
            build(
                paper_epoch_id="X",
                created_at=1.0,
                initial_virtual_capital=1.0,
                code_sha=CODE_SHA,
                config_snapshot_hash=CONFIG_HASH,
                legacy_log_bytes=LEGACY,
                quiescence=bad,
                predecessor_authority_epoch_id="P",
            )
    for q in (
        EpochRotationQuiescence(1, 0, 0, True),
        EpochRotationQuiescence(0, 1, 0, True),
        EpochRotationQuiescence(0, 0, 1, True),
    ):
        assert not q.quiescent
    with pytest.raises(AuthorityManifestError):
        build_cutover_manifest(
            paper_epoch_id="X",
            created_at=1.0,
            initial_virtual_capital=1.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_log_bytes=LEGACY,
            quiescence=CutoverQuiescence(0, 0, 0, False),
        )


# Reference digests were produced by the pre-change runtime (main 85376c5e).
_REFERENCE = {
    "v1": "798b85ef76660bd68c6ed193a17610572c21da6104b9178dd9678e1cb5da828b",
    "v2": "2fa4e26d8fb03d2709d8535fe2a27ef9d70c37872736f52a783fd443cd94da1b",
    "v3": "8bf9900c6fdba112c02580200158883b3b0aca5f2a9b8f234bbaf6fe1448e00d",
}
_REFERENCE_EVENT_IDS = {
    "v1": "ppl02e-3e7a0d5df43eb4ca7fe46c9e93d33a3725059e4b69c3d6cc342520ef6bd59ce7",
    "v2": "f00-2518382843c4c78f4f69e44ba2647d4cc88509a1ff05bcdcb91b08029f799baa",
    "v3": "burnin-f2d050679162b18672d793058ce2a4357c500be7d0b03ac816fae422312f7c0b",
}


def _legacy_manifests():
    q = EpochRotationQuiescence(0, 0, 0, True)
    return {
        "v1": build_cutover_manifest(
            paper_epoch_id="PPL-AUTH-TEST",
            created_at=1.0,
            initial_virtual_capital=100.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_log_bytes=LEGACY,
            quiescence=CutoverQuiescence(0, 0, 0, True),
            predecessor_shadow_epoch_id="SHADOW-PREDECESSOR",
        ),
        "v2": build_experiment_manifest(
            paper_epoch_id="F00-EPOCH-TEST",
            created_at=1.0,
            initial_virtual_capital=100.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_log_bytes=LEGACY,
            quiescence=q,
            predecessor_authority_epoch_id="PRED",
        ),
        "v3": build_burn_in_experiment_manifest(
            paper_epoch_id="BURN-IN-EPOCH-TEST",
            created_at=2.0,
            initial_virtual_capital=101.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_log_bytes=LEGACY,
            quiescence=q,
            predecessor_authority_epoch_id="PRED",
        ),
    }


@pytest.mark.parametrize("key", ["v1", "v2", "v3"])
def test_t2_existing_manifests_bytes_and_event_ids_unchanged(tmp_path, key):
    manifest = _legacy_manifests()[key]
    path = tmp_path / "m.json"
    write_authority_manifest(path, manifest)
    assert _sha(path.read_bytes()) == _REFERENCE[key]
    assert authority_manifest_sha256(manifest) == _REFERENCE[key]
    assert load_authority_manifest(path) == manifest
    # the reference generator used the first LedgerEventType member
    first = next(iter(LedgerEventType))
    assert _event_id(manifest, first, "T1") == _REFERENCE_EVENT_IDS[key]


def test_t2_existing_roles_refuse_succession_field():
    base = _legacy_manifests()["v3"]
    with pytest.raises(ValueError):
        AuthorityEpochManifest(
            paper_epoch_id="X",
            created_at=1.0,
            initial_virtual_capital=1.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_boundary_sha256="d" * 64,
            legacy_event_count=0,
            predecessor_authority_epoch_id="P",
            epoch_role=base.epoch_role,
            manifest_schema_version=base.manifest_schema_version,
            interruption_succession_sha256="e" * 64,
        )


# ------------------------------------------------ T3: v4 manifest round-trip


def test_t3_successor_manifest_roundtrip_and_exact_fields(bundle, tmp_path):
    record = bundle.record()
    manifest = _manifest(record)
    path = tmp_path / "succ.json"
    write_authority_manifest(path, manifest)
    loaded = load_authority_manifest(path)
    assert loaded == manifest
    assert loaded.manifest_schema_version == 4
    assert loaded.interruption_succession_sha256 == record.record_sha256
    assert loaded.predecessor_authority_epoch_id == PRED_EPOCH
    data = json.loads(path.read_text())
    data["extra"] = 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(AuthorityManifestError):
        load_authority_manifest(bad)
    data.pop("extra")
    data.pop("interruption_succession_sha256")
    bad2 = tmp_path / "bad2.json"
    bad2.write_text(json.dumps(data))
    with pytest.raises(AuthorityManifestError):
        load_authority_manifest(bad2)


def test_t3_successor_manifest_validation():
    kwargs = {
        "paper_epoch_id": "S",
        "created_at": 1.0,
        "initial_virtual_capital": 1.0,
        "code_sha": CODE_SHA,
        "config_snapshot_hash": CONFIG_HASH,
        "legacy_boundary_sha256": "d" * 64,
        "legacy_event_count": 1,
        "epoch_role": "BURN_IN_SUCCESSOR_AFTER_INTERRUPTION",
        "manifest_schema_version": 4,
    }
    with pytest.raises(ValueError):  # missing predecessor + digest
        AuthorityEpochManifest(**kwargs)
    with pytest.raises(ValueError):  # same epoch id as predecessor
        AuthorityEpochManifest(
            **kwargs, predecessor_authority_epoch_id="S", interruption_succession_sha256="e" * 64
        )
    with pytest.raises(ValueError):  # bad digest
        AuthorityEpochManifest(
            **kwargs, predecessor_authority_epoch_id="P", interruption_succession_sha256="E" * 64
        )
    with pytest.raises(ValueError):  # wrong schema
        AuthorityEpochManifest(
            **{**kwargs, "manifest_schema_version": 3},
            predecessor_authority_epoch_id="P",
            interruption_succession_sha256="e" * 64,
        )


# --------------------------------------------- T4: valid + deterministic


def test_t4_valid_bundle_is_deterministic_and_keeps_unknowns(bundle):
    first, second = bundle.record(), bundle.record()
    assert first == second and first.record_sha256 == second.record_sha256
    assert first.predecessor_event_count == 7
    assert first.predecessor_opened_count == 3
    assert first.predecessor_closed_count == 1
    assert first.predecessor_unresolved_count == 2
    assert first.predecessor_open_positions == 0
    assert first.predecessor_unresolved_capital == 20.0
    assert first.pending_order_count == "UNKNOWN"
    assert first.lifecycle_transitions_in_flight == "UNKNOWN"
    assert first.fin_status == "UNRESOLVED" and first.certified_equity is None
    assert first.predecessor_unresolved_capital_transfer == "NONE"
    assert first.successor_initial_virtual_capital == 1000.0
    manifest = _manifest(first)
    assert manifest.paper_epoch_id == SUCC_EPOCH
    assert manifest.initial_virtual_capital == 1000.0  # declared, not 1000 - 20 or +20


# ------------------------------------------------ T5: absent evidence


@pytest.mark.parametrize(
    "key",
    [
        "ledger_bytes",
        "dataset_files",
        "operator_decision_bytes",
        "capital_decision_bytes",
    ],
)
@pytest.mark.parametrize("empty", [None, b"", ""])
def test_t5_absent_evidence_refused(bundle, key, empty):
    kwargs = bundle.kwargs()
    kwargs[key] = empty
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


@pytest.mark.parametrize("role", REQUIRED_EVIDENCE_ROLES)
def test_t5_missing_artifact_refused(bundle, role):
    kwargs = bundle.kwargs()
    kwargs["evidence_artifacts"].pop(role)
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


# ------------------------------------------------ T6: altered evidence


def _flip(raw: bytes) -> bytes:
    return raw[:-2] + bytes([raw[-2] ^ 0x01]) + raw[-1:]


def test_t6_altered_ledger_refused(bundle):
    kwargs = bundle.kwargs()
    kwargs["ledger_bytes"] = _flip(bundle.ledger)
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


@pytest.mark.parametrize("role", REQUIRED_EVIDENCE_ROLES)
def test_t6_altered_artifact_refused(bundle, role):
    kwargs = bundle.kwargs()
    kwargs["evidence_artifacts"][role] = kwargs["evidence_artifacts"][role] + b"x"
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


def test_t6_altered_dataset_manifest_refused(bundle):
    bundle.dataset["components"]["ppl_events"]["sha256"] = "0" * 64
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_t6_truncated_ledger_refused_even_with_matching_decision(tmp_path):
    # a complete, natively valid export whose last event is missing: an OPEN is
    # left behind -> not an interrupted-closed ledger
    with pytest.raises(SuccessionRefusal):
        Bundle(tmp_path, variant="open").record()


# --------------------------------------------- T7: inconsistent evidence


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.decision.__setitem__("predecessor_paper_epoch_id", "OTHER-EPOCH"),
        lambda b: b.decision.__setitem__("predecessor_event_count", 8),
        lambda b: b.decision.__setitem__("unresolved_capital", 10.0),
        lambda b: b.decision.__setitem__("predecessor_dataset_id", "f" * 64),
        lambda b: b.decision.__setitem__("predecessor_ledger_sha256", "9" * 64),
        lambda b: b.dataset.__setitem__("paper_epoch_id", "OTHER-EPOCH"),
        lambda b: b.dataset["components"]["ppl_events"].__setitem__("record_count", 8),
        lambda b: b.decision.__setitem__("schema", "OTHER-SCHEMA"),
        lambda b: b.decision.__setitem__("decision_kind", "NORMAL_ROTATION"),
    ],
)
def test_t7_inconsistent_evidence_refused(bundle, mutate):
    mutate(bundle)
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_t7_successor_equal_to_predecessor_refused(bundle):
    kwargs = bundle.kwargs()
    kwargs["successor_paper_epoch_id"] = PRED_EPOCH
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


def test_t7_capital_decision_for_another_successor_refused(bundle):
    bundle.capital["successor_paper_epoch_id"] = "ANOTHER"
    with pytest.raises(SuccessionRefusal):
        bundle.record()


# -------------------------------- T8: URL / boolean / unknown field refused


def test_t8_url_or_boolean_instead_of_bytes_refused(bundle):
    for replacement in ("https://github.com/x/y/issues/282#issuecomment-1", True, 1):
        kwargs = bundle.kwargs()
        kwargs["evidence_artifacts"]["closure_comment_body"] = replacement
        with pytest.raises(SuccessionRefusal):
            verify_interruption_evidence(**kwargs)
        for key in ("operator_decision_bytes", "dataset_files", "ledger_bytes"):
            kwargs = bundle.kwargs()
            kwargs[key] = replacement
            with pytest.raises(SuccessionRefusal):
                verify_interruption_evidence(**kwargs)


def test_t8_url_in_place_of_cited_hash_refused(bundle):
    bundle.decision["evidence_sha256"]["closure_comment_body"] = (
        "https://github.com/3a7i3/crypto-ia-terminal/issues/282#issuecomment-6712166490"
    )
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_t8_boolean_decision_without_content_refused(bundle):
    only_flag = _js({"accepted": True})
    kwargs = bundle.kwargs()
    kwargs["operator_decision_bytes"] = only_flag
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


def test_t8_unknown_field_and_duplicate_key_refused(bundle):
    bundle.decision["accepted"] = True
    with pytest.raises(SuccessionRefusal):
        bundle.record()
    bundle.decision.pop("accepted")
    kwargs = bundle.kwargs()
    raw = kwargs["operator_decision_bytes"].decode()
    kwargs["operator_decision_bytes"] = raw.replace(
        '"fin_status"', '"fin_status": "UNRESOLVED", "fin_status"', 1
    ).encode()
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


# --------------------------------------- T9: UNKNOWN is never a number


@pytest.mark.parametrize("bad", [0, 0.0, None, False, "0", "unknown", "NONE", -1])
@pytest.mark.parametrize("field", ["pending_order_count", "lifecycle_transitions_in_flight"])
def test_t9_unknown_counter_not_convertible(bundle, field, bad):
    bundle.decision["acknowledged_unknowns"][field] = bad
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_t9_missing_unknown_counter_refused(bundle):
    bundle.decision["acknowledged_unknowns"].pop("pending_order_count")
    with pytest.raises(SuccessionRefusal):
        bundle.record()


# --------------------------------- T10/T11: lifecycle + financial status


def test_t10_open_position_in_predecessor_refused(tmp_path):
    b = Bundle(tmp_path, variant="open")
    assert b.decision["unresolved_capital"] == 10.0  # consistent with the ledger
    with pytest.raises(SuccessionRefusal, match="open positions"):
        b.record()


@pytest.mark.parametrize(
    "field,value",
    [("fin_status", "RECONCILED"), ("certified_equity", 1000.0), ("unresolved_capital", 0)],
)
def test_t11_financial_status_not_rewritten(bundle, field, value):
    bundle.decision[field] = value
    with pytest.raises(SuccessionRefusal):
        bundle.record()


# ------------------------------------------------ T12: capital provenance


@pytest.mark.parametrize(
    "kind",
    ["PREDECESSOR_CASH", "PREDECESSOR_EQUITY", "WALLET_PAPER_CAPITAL", "API_BALANCE", ""],
)
def test_t12_capital_provenance_refused(bundle, kind):
    bundle.capital["provenance"] = kind
    with pytest.raises(SuccessionRefusal):
        bundle.record()


@pytest.mark.parametrize("value", [0, -5, True, "1000", float("nan")])
def test_t12_capital_value_refused(bundle, value):
    bundle.capital["initial_virtual_capital"] = value
    kwargs = bundle.kwargs()
    if isinstance(value, float) and math.isnan(value):
        kwargs["capital_decision_bytes"] = (
            json.dumps(bundle.capital).encode()  # allows NaN token
        )
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


def test_t12_no_implicit_capital_transfer(bundle):
    record = bundle.record()
    assert record.predecessor_unresolved_capital == 20.0
    assert record.successor_initial_virtual_capital == bundle.capital["initial_virtual_capital"]
    assert record.predecessor_unresolved_capital_transfer == "NONE"
    bundle.capital["initial_virtual_capital"] = 1020.0
    # a different declared nominal produces a different record: never derived
    assert bundle.record().record_sha256 != record.record_sha256


# ----------------------------------------------- T13: store separation


def _exclusivity(tmp_path, bundle):
    record = bundle.record()
    manifest = _manifest(record)
    return Exclusivity(tmp_path, bundle, record, manifest)


def test_t13_successor_store_must_be_distinct_and_empty(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    assert ex.issue().paper_epoch_id == SUCC_EPOCH  # control: valid proof passes
    with pytest.raises(SuccessionRefusal):  # same root
        ex.issue(successor_store_root=ex.pred_root)
    inner = ex.pred_root / "inner"
    with pytest.raises(SuccessionRefusal):  # nested in predecessor root
        ex.issue(successor_store_root=inner)
    outer_pred = tmp_path / "pred-store" / "x"
    outer_pred.mkdir()
    with pytest.raises(SuccessionRefusal):  # predecessor nested inside successor
        ex.issue(predecessor_store_root=outer_pred, successor_store_root=ex.pred_root)
    link = tmp_path / "link-store"
    link.symlink_to(ex.succ_root.parent)
    with pytest.raises(SuccessionRefusal):  # symlink
        ex.issue(successor_store_root=link)
    ex.succ_root.mkdir()
    (ex.succ_root / "epochs").mkdir()
    (ex.succ_root / "epochs" / "e.jsonl").write_text("{}\n")
    with pytest.raises(SuccessionRefusal):  # not empty
        ex.issue()


# --------------------------------- T14/T15: exclusivity is a separate proof


def test_t14_documentary_closure_is_not_an_exclusivity_proof(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    with pytest.raises(SuccessionRefusal):
        ex.issue(proof_bytes=_js(bundle.decision))
    with pytest.raises(SuccessionRefusal):
        ex.issue(proof_bytes=b"")
    with pytest.raises(SuccessionRefusal):
        ex.issue(proof_bytes=True)
    with pytest.raises(SuccessionRefusal):
        ex.issue(observation_artifacts={})


def test_t15_exclusivity_proof_rejections(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    name = REQUIRED_EXCLUSIVITY_OBSERVATIONS[0]

    def reissue(mutator):
        proof = json.loads(json.dumps(ex.proof))
        arts = dict(ex.artifacts)
        mutator(proof, arts)
        with pytest.raises(SuccessionRefusal):
            ex.issue(proof_bytes=_js(proof), observation_artifacts=arts)

    reissue(lambda p, a: p["observations"][name].__setitem__("result", "FAIL"))
    reissue(lambda p, a: p["observations"][name].__setitem__("observed_at", NOW - 10_000))
    reissue(lambda p, a: p["observations"][name].__setitem__("observed_at", NOW + 5))
    reissue(lambda p, a: a.__setitem__(name, b"tampered"))
    reissue(lambda p, a: p["observations"].pop(name))
    reissue(lambda p, a: p["observations"][name].__setitem__("evidence_sha256", "http://x"))
    reissue(lambda p, a: p.__setitem__("manifest_sha256", "1" * 64))
    reissue(lambda p, a: p.__setitem__("record_sha256", "1" * 64))
    reissue(lambda p, a: p.__setitem__("successor_paper_epoch_id", "ANOTHER"))
    reissue(lambda p, a: p.__setitem__("successor_store_root", "/elsewhere"))
    reissue(lambda p, a: p.__setitem__("predecessor_ledger_sha256", "2" * 64))
    with pytest.raises(SuccessionRefusal):  # predecessor ledger modified since closure
        ex.issue(predecessor_ledger_bytes_now=bundle.ledger + b"\n{}")
    with pytest.raises(SuccessionRefusal):  # manifest of another record
        other = Bundle(tmp_path / "o")
        other.capital["initial_virtual_capital"] = 5.0
        ex.issue(manifest=_manifest(other.record()))


# ------------------------------------------- T16: runtime bind fails closed


def _runtime(tmp_path, manifest, clearance=None):
    return PPLAuthorityRuntime(
        manifest=manifest,
        store=DurableEventStore(tmp_path / "succ-store"),
        activation_clearance=clearance,
    )


def test_t16_bind_refuses_successor_without_matching_clearance(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    clearance = ex.issue()
    # no clearance
    runtime = _runtime(tmp_path, ex.manifest)
    with pytest.raises(AuthorityManifestError):
        runtime.bind(now=NOW)
    assert not (tmp_path / "succ-store").exists()
    # clearance of another manifest
    other = Bundle(tmp_path / "other")
    other.capital["initial_virtual_capital"] = 7.0
    other_manifest = _manifest(other.record())
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, other_manifest, clearance).bind(now=NOW)
    # forged clearance object with the right epoch but wrong manifest bytes
    forged = type("F", (), {"paper_epoch_id": SUCC_EPOCH, "manifest_sha256": "0" * 64})()
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, forged).bind(now=NOW)
    # right epoch and right manifest hash on a duck-typed object is still refused
    duck = type(
        "D",
        (),
        {"paper_epoch_id": SUCC_EPOCH, "manifest_sha256": authority_manifest_sha256(ex.manifest)},
    )()
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, duck).bind(now=NOW)
    assert not (tmp_path / "succ-store").exists()


def test_t16_bind_with_valid_clearance_creates_one_birth_event(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    clearance = ex.issue()
    runtime = _runtime(tmp_path, ex.manifest, clearance)
    state = runtime.bind(now=NOW)
    assert state.paper_epoch_id == SUCC_EPOCH
    assert state.available_cash == 1000.0 and state.unresolved_capital == 0.0
    events = runtime.store.load_epoch(SUCC_EPOCH)
    assert len(events) == 1 and events[0].event_id.startswith("burnsucc-")
    again = _runtime(tmp_path, ex.manifest, ex.issue_resume(NOW + 1))
    again.bind(now=NOW + 1)
    assert len(runtime.store.load_epoch(SUCC_EPOCH)) == 1


def test_t16_other_roles_bind_without_clearance(tmp_path):
    manifest = _legacy_manifests()["v3"]
    runtime = PPLAuthorityRuntime(
        manifest=manifest, store=DurableEventStore(tmp_path / "s")
    )
    assert runtime.bind(now=NOW).paper_epoch_id == "BURN-IN-EPOCH-TEST"


# ----------------------------------------------------- T17/T18: the gate


def _gate(tmp_path, manifest_sha="m" * 64, epoch=SUCC_EPOCH):
    return AdmissionGate(tmp_path / "gate.jsonl", paper_epoch_id=epoch, manifest_sha256=manifest_sha)


def _clearance_for(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    return ex, ex.issue()


def _open_decision(manifest_sha, clearance, **over):
    doc = {
        "schema": OPEN_DECISION_SCHEMA,
        "paper_epoch_id": SUCC_EPOCH,
        "manifest_sha256": manifest_sha,
        "clearance_proof_sha256": clearance.exclusivity_proof_sha256,
        "decided_by": "operator",
        "decided_at_utc": "2026-11-08T00:00:00Z",
    }
    doc.update(over)
    return _js(doc)


def test_t17_gate_closed_by_default_open_once_close_always(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    assert gate.state() == "CLOSED" and not gate.is_open()
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    assert gate.is_open()
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    gate.close(decided_by="op", reason="stop")
    assert gate.state() == "CLOSED"
    with pytest.raises(AdmissionGateRefusal):  # one-time, even after a close
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    assert gate.state() == "CLOSED"


def test_t17_gate_refuses_mismatched_opening(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    other_gate = _gate(tmp_path, "z" * 64)
    with pytest.raises(AdmissionGateRefusal):  # clearance for another manifest
        other_gate.open(decision_bytes=_open_decision("z" * 64, clearance), clearance=clearance, now=NOW)
    gate = _gate(tmp_path, msha)
    for decision in (
        b"",
        b"true",
        _open_decision(msha, clearance, paper_epoch_id="OTHER"),
        _open_decision(msha, clearance, manifest_sha256="y" * 64),
        _open_decision(msha, clearance, clearance_proof_sha256="0" * 64),
        _open_decision(msha, clearance, schema="x"),
        _open_decision(msha, clearance, decided_by=""),
        _js({"approved": True}),
    ):
        with pytest.raises(AdmissionGateRefusal):
            gate.open(decision_bytes=decision, clearance=clearance, now=NOW)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=object(), now=NOW)
    assert gate.state() == "CLOSED"
    assert not (tmp_path / "gate.jsonl").exists()


def test_t17_gate_fail_closed_on_corruption_or_wrong_binding(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    path = tmp_path / "gate.jsonl"
    original = path.read_bytes()
    # another epoch / manifest reading the same journal sees CLOSED
    assert _gate(tmp_path, "q" * 64).state() == "CLOSED"
    assert _gate(tmp_path, msha, epoch="OTHER").state() == "CLOSED"
    # byte tampering, garbage, truncation, reordering all read as CLOSED
    for tampered in (
        original.replace(b'"OPEN"', b'"OPEN "'),
        original.replace(b"operator", b"intruder"),
        b"garbage\n",
        b"",
        original + b"not json\n",
    ):
        path.write_bytes(tampered)
        assert gate.state() == "CLOSED"
    path.write_bytes(original)
    assert gate.state() == "OPEN"
    # symlink journal is refused
    real = tmp_path / "real.jsonl"
    real.write_bytes(original)
    path.unlink()
    path.symlink_to(real)
    assert gate.state() == "CLOSED"
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)


def test_t17_chain_break_detected(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    gate.close(decided_by="op", reason="r")
    path = tmp_path / "gate.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(lines[1])  # drop the OPEN record: chain no longer starts at genesis
    assert gate.state() == "CLOSED"
    path.write_bytes(lines[1] + lines[0])  # reorder
    assert gate.state() == "CLOSED"


@pytest.mark.parametrize("ceiling", ["0", "2", "99"])
def test_t18_gate_independent_of_pb_max_positions(tmp_path, bundle, monkeypatch, ceiling):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    monkeypatch.setenv("PB_MAX_POSITIONS", ceiling)
    assert gate.state() == "CLOSED"  # a high ceiling never opens it
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    monkeypatch.setenv("PB_MAX_POSITIONS", "0")
    assert gate.state() == "OPEN"  # a zero ceiling never closes it either
    monkeypatch.delenv("PB_MAX_POSITIONS")
    assert gate.state() == "OPEN"


# ------------------------------------- T19: predecessor authority reuse


def test_t19_successor_cannot_take_predecessor_identity_or_store(tmp_path, bundle):
    """Narrow scope: a *successor* manifest/store cannot alias the predecessor's.

    NOT covered: someone resuming the old v3 epoch with its own v3 manifest and
    store.  That scenario needs a separate lot (e.g. a persisted retirement mark).
    """
    record = bundle.record()
    manifest = _manifest(record)
    # a manifest naming the predecessor epoch as its own id is invalid
    with pytest.raises(ValueError):
        AuthorityEpochManifest(
            paper_epoch_id=PRED_EPOCH,
            created_at=1.0,
            initial_virtual_capital=1000.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            legacy_boundary_sha256=record.predecessor_ledger_sha256,
            legacy_event_count=7,
            predecessor_authority_epoch_id=PRED_EPOCH,
            epoch_role="BURN_IN_SUCCESSOR_AFTER_INTERRUPTION",
            manifest_schema_version=4,
            interruption_succession_sha256=record.record_sha256,
        )
    # the successor runtime cannot write into the predecessor's store root
    ex = Exclusivity(tmp_path, bundle, record, manifest)
    with pytest.raises(SuccessionRefusal):
        ex.issue(successor_store_root=ex.pred_root)
    # the sealed predecessor ledger is never modified by any step above
    assert _sha(bundle.ledger) == record.predecessor_ledger_sha256
    # a record verified for another successor id cannot back this manifest
    other_kwargs = bundle.kwargs()
    other_kwargs["successor_paper_epoch_id"] = "ANOTHER-SUCCESSOR"
    bundle.capital["successor_paper_epoch_id"] = "ANOTHER-SUCCESSOR"
    other_kwargs["capital_decision_bytes"] = _js(bundle.capital)
    other = verify_interruption_evidence(**other_kwargs)
    with pytest.raises(SuccessionRefusal):
        ex.issue(record=other)


# ======================================================================
# Review R1-R4 regressions
# ======================================================================

# ------------------------- R1: the clearance is validated where it is used


def test_r1_clearance_cannot_be_built_from_fields(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    real = ex.issue()
    unsealed = ActivationClearance(
        paper_epoch_id=real.paper_epoch_id,
        manifest_sha256=real.manifest_sha256,
        record_sha256=real.record_sha256,
        exclusivity_proof_sha256=real.exclusivity_proof_sha256,
        successor_store_root=real.successor_store_root,
        purpose=real.purpose,
        issued_at=real.issued_at,
        max_age_s=real.max_age_s,
    )
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, unsealed).bind(now=NOW)
    assert not ex.succ_root.exists()
    gate = _gate(tmp_path, real.manifest_sha256)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(real.manifest_sha256, real), clearance=unsealed, now=NOW)


@pytest.mark.parametrize(
    "change",
    [
        {"successor_store_root": "/elsewhere"},
        {"issued_at": NOW + 1_000_000.0},
        {"max_age_s": 10.0**9},
        {"record_sha256": "1" * 64},
        {"exclusivity_proof_sha256": "2" * 64},
    ],
)
def test_r1_modified_clearance_fails_seal(tmp_path, bundle, change):
    ex = _exclusivity(tmp_path, bundle)
    tampered = dataclasses.replace(ex.issue(), **change)  # keeps the old seal
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, tampered).bind(now=NOW)
    assert not ex.succ_root.exists()


def test_r1_clearance_bound_to_its_store_root(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    clearance = ex.issue()
    other = PPLAuthorityRuntime(
        manifest=ex.manifest,
        store=DurableEventStore(tmp_path / "another-store"),
        activation_clearance=clearance,
    )
    with pytest.raises(AuthorityManifestError):
        other.bind(now=NOW)
    assert not (tmp_path / "another-store").exists()


def test_r1_clearance_bound_to_its_record(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    clearance = ex.issue()
    other = Bundle(tmp_path / "other")
    other.capital["initial_virtual_capital"] = 9.0
    with pytest.raises(SuccessionRefusal):
        validate_clearance_for_use(
            clearance,
            manifest=_manifest(other.record()),
            store_root=ex.succ_root,
            now=NOW,
            resume=False,
        )


def test_r1_bootstrap_requires_fresh_clearance(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    clearance = ex.issue()
    stale_now = NOW + clearance.max_age_s + 1
    with pytest.raises(AuthorityManifestError):  # bootstrap: stale
        _runtime(tmp_path, ex.manifest, clearance).bind(now=stale_now)
    with pytest.raises(AuthorityManifestError):  # bootstrap: from the future
        _runtime(tmp_path, ex.manifest, clearance).bind(now=NOW - 1)
    assert not ex.succ_root.exists()
    _runtime(tmp_path, ex.manifest, clearance).bind(now=NOW + 5)  # birth, fresh


def test_r1_resume_needs_its_own_fresh_resume_clearance(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    boot = ex.issue()
    _runtime(tmp_path, ex.manifest, boot).bind(now=NOW)
    ledger_before = _tree(ex.succ_root)
    later = NOW + 10**6
    # the bootstrap permit cannot authorise a resume, however it is presented
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, boot).bind(now=NOW + 5)
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, None).bind(now=later)
    # a bootstrap proof cannot be replayed to obtain a resume clearance
    with pytest.raises(SuccessionRefusal):
        issue_resume_clearance(**ex.args(now=later))
    # and the bootstrap issuer still refuses the populated store
    with pytest.raises(SuccessionRefusal):
        ex.issue(now=later)
    resume = ex.issue_resume(later)
    runtime = _runtime(tmp_path, ex.manifest, resume)
    runtime.bind(now=later)
    assert len(runtime.store.load_epoch(SUCC_EPOCH)) == 1  # no second birth
    assert _tree(ex.succ_root) == ledger_before  # existing events untouched
    # a resume clearance is itself fresh-only
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, resume).bind(now=later + resume.max_age_s + 1)


def _tree(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_r1_resume_refuses_wrong_bindings(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    _runtime(tmp_path, ex.manifest, ex.issue()).bind(now=NOW)
    later = NOW + 3600
    resume = ex.issue_resume(later)
    # another record / manifest
    other = Bundle(tmp_path / "other")
    other.capital["initial_virtual_capital"] = 9.0
    other_manifest = _manifest(other.record())
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, other_manifest, resume).bind(now=later)
    with pytest.raises(SuccessionRefusal):
        ex.issue_resume(later, manifest=other_manifest, record=other.record())
    # a manifest with the same record but another birth (different created_at)
    different = build_interrupted_successor_manifest(
        record=ex.record, created_at=6.0, code_sha=CODE_SHA, config_snapshot_hash=CONFIG_HASH
    )
    exd = Exclusivity(tmp_path, bundle, ex.record, different)
    with pytest.raises(SuccessionRefusal):
        exd.issue_resume(later)
    # wrong root / predecessor root / nested roots
    with pytest.raises(SuccessionRefusal):
        ex.issue_resume(later, successor_store_root=tmp_path / "elsewhere")
    with pytest.raises(SuccessionRefusal):
        ex.issue_resume(later, successor_store_root=ex.pred_root)
    # no birth in an empty store
    empty = tmp_path / "empty-store"
    empty.mkdir()
    proof, arts = ex.build("RESUME", later)
    proof["successor_store_root"] = str(empty.resolve())
    with pytest.raises(SuccessionRefusal):
        issue_resume_clearance(
            **ex.args(
                proof_bytes=_js(proof), observation_artifacts=arts, now=later,
                successor_store_root=empty,
            )
        )
    # predecessor ledger changed since the closure
    with pytest.raises(SuccessionRefusal):
        ex.issue_resume(later, predecessor_ledger_bytes_now=ex.ledger_now + b"\n")
    # stale observations / FAIL / missing observation
    proof, arts = ex.build("RESUME", later)
    first = next(iter(arts))
    proof["observations"][first]["observed_at"] = later - 10**5
    with pytest.raises(SuccessionRefusal):
        issue_resume_clearance(**ex.args(proof_bytes=_js(proof), observation_artifacts=arts, now=later))
    proof, arts = ex.build("RESUME", later)
    proof["observations"].pop(first)
    arts.pop(first)
    with pytest.raises(SuccessionRefusal):
        issue_resume_clearance(**ex.args(proof_bytes=_js(proof), observation_artifacts=arts, now=later))


_CHILD = """
import json, sys
from pathlib import Path
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ppl_authority_runtime import PPLAuthorityRuntime, load_authority_manifest
from paper_trading.ppl_interrupted_succession import (
    issue_activation_clearance, issue_resume_clearance, verify_interruption_evidence)

d = Path(sys.argv[1]); mode = sys.argv[2]
cfg = json.loads((d / "cfg.json").read_text())
rb = lambda *p: d.joinpath(*p).read_bytes()
record = verify_interruption_evidence(
    ledger_bytes=rb("ledger"),
    dataset_files={r: rb("dataset", r) for r in cfg["dataset_rels"]},
    operator_decision_bytes=rb("decision.json"),
    evidence_artifacts={k: rb("artifacts", k) for k in cfg["artifact_roles"]},
    successor_paper_epoch_id=cfg["succ"],
    capital_decision_bytes=rb("capital.json"))
manifest = load_authority_manifest(d / "manifest.json")
issue = issue_activation_clearance if mode == "bootstrap" else issue_resume_clearance
clearance = issue(
    manifest=manifest, record=record, proof_bytes=rb("proof-" + mode + ".json"),
    observation_artifacts={k: rb("obs-" + mode, k) for k in cfg["obs"][mode]},
    predecessor_ledger_bytes_now=rb("ledger"),
    predecessor_store_root=cfg["pred_root"], successor_store_root=cfg["succ_root"],
    now=cfg["now"][mode])
runtime = PPLAuthorityRuntime(
    manifest=manifest, store=DurableEventStore(cfg["succ_root"]), activation_clearance=clearance)
runtime.bind(now=cfg["now"][mode])
events = DurableEventStore(cfg["succ_root"]).load_epoch(cfg["succ"])
print(json.dumps({"events": len(events), "ids": [e.event_id for e in events]}))
"""


def _run_child(workdir: Path, mode: str):
    repo = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, str(workdir / "child.py"), str(workdir), mode],
        cwd=repo,
        env={"PYTHONPATH": str(repo), "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_r1_two_successive_processes_birth_then_resume(tmp_path, bundle):
    """A real restart: process A bootstraps and exits; process B (new interpreter,
    new HMAC key) resumes with a RESUME clearance.  One birth, events untouched."""
    record = bundle.record()
    manifest = _manifest(record)
    ex = Exclusivity(tmp_path, bundle, record, manifest)
    work = tmp_path / "work"
    (work / "dataset" / "authoritative").mkdir(parents=True)
    (work / "artifacts").mkdir()
    for rel, raw in {**bundle.files, "manifest.json": _js(bundle.dataset)}.items():
        target = work / "dataset" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for role, raw in bundle.artifacts.items():
        (work / "artifacts" / role).write_bytes(raw)
    (work / "ledger").write_bytes(bundle.ledger)
    (work / "decision.json").write_bytes(_js(bundle.decision))
    (work / "capital.json").write_bytes(_js(bundle.capital))
    write_authority_manifest(work / "manifest.json", manifest)
    (work / "child.py").write_text(_CHILD)
    resume_now = NOW + 7200
    proof_b, arts_b = ex.build("BOOTSTRAP", NOW)
    proof_r, arts_r = ex.build("RESUME", resume_now)
    (work / "proof-bootstrap.json").write_bytes(_js(proof_b))
    (work / "proof-resume.json").write_bytes(_js(proof_r))
    for mode, arts in (("bootstrap", arts_b), ("resume", arts_r)):
        (work / f"obs-{mode}").mkdir()
        for name, raw in arts.items():
            (work / f"obs-{mode}" / name).write_bytes(raw)
    (work / "cfg.json").write_text(
        json.dumps(
            {
                "dataset_rels": sorted({*bundle.files, "manifest.json"}),
                "artifact_roles": sorted(bundle.artifacts),
                "succ": SUCC_EPOCH,
                "succ_root": str(ex.succ_root.resolve()),
                "pred_root": str(ex.pred_root.resolve()),
                "now": {"bootstrap": NOW, "resume": resume_now},
                "obs": {"bootstrap": sorted(arts_b), "resume": sorted(arts_r)},
            }
        )
    )

    first = _run_child(work, "bootstrap")
    assert first.returncode == 0, first.stderr
    born = json.loads(first.stdout)
    assert born["events"] == 1 and born["ids"][0].startswith("burnsucc-")
    after_birth = _tree(ex.succ_root)

    # a second *bootstrap* process on the populated store is refused (no 2nd birth)
    again = _run_child(work, "bootstrap")
    assert again.returncode != 0 and "not empty" in again.stderr
    assert _tree(ex.succ_root) == after_birth

    second = _run_child(work, "resume")
    assert second.returncode == 0, second.stderr
    resumed = json.loads(second.stdout)
    assert resumed == born  # same single birth event, same id
    assert _tree(ex.succ_root) == after_birth  # not one byte changed


def test_r1_bootstrap_refused_when_successor_store_not_empty(tmp_path, bundle):
    ex = _exclusivity(tmp_path, bundle)
    clearance = ex.issue()
    (ex.succ_root / "epochs").mkdir(parents=True)
    (ex.succ_root / "epochs" / "x.jsonl").write_text("{}\n")
    with pytest.raises(AuthorityManifestError):
        _runtime(tmp_path, ex.manifest, clearance).bind(now=NOW)


def test_r1_gate_checks_clearance_freshness_and_binding(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    decision = _open_decision(msha, clearance)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=decision, clearance=clearance, now=NOW + clearance.max_age_s + 1)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=decision, clearance=dataclasses.replace(clearance, max_age_s=1e9), now=NOW)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=decision, clearance=clearance, now=True)
    assert gate.state() == "CLOSED"
    gate.open(decision_bytes=decision, clearance=clearance, now=NOW + 1)
    assert gate.is_open()


# ------------------- R2: closure priority, concurrency, persistence failure


def test_r2_close_before_open_is_permanent(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    assert gate.close(decided_by="op", reason="early") is True
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    fresh = _gate(tmp_path, msha)  # another instance reads the same durable closure
    assert fresh.state() == "CLOSED"
    with pytest.raises(AdmissionGateRefusal):
        fresh.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)


def test_r2_marker_beats_an_open_journal(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    other = _gate(tmp_path, msha)
    assert other.is_open()
    other.close(decided_by="op", reason="stop")
    assert not gate.is_open() and not other.is_open()
    (tmp_path / "gate.jsonl").write_bytes(b"")  # even a wiped journal cannot reopen
    assert _gate(tmp_path, msha).state() == "CLOSED"


_MP = {}


def _mp_open(index):
    gate = _MP["gate"](index)
    try:
        gate.open(
            decision_bytes=_MP["decision"], clearance=_MP["clearance"], now=NOW
        )
        return "OPENED"
    except AdmissionGateRefusal:
        return "REFUSED"


def _mp_close(index):
    _MP["gate"](index).close(decided_by=f"p{index}", reason="race")
    return "CLOSED"


def test_r2_concurrent_processes_open_exactly_once(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    _MP.update(
        gate=lambda i: _gate(tmp_path, msha),
        decision=_open_decision(msha, clearance),
        clearance=clearance,
    )
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(8) as pool:
        results = pool.map(_mp_open, range(8))
    assert results.count("OPENED") == 1 and results.count("REFUSED") == 7
    gate = _gate(tmp_path, msha)
    assert gate.is_open()
    assert len(gate._records()) == 1  # valid chain, a single OPEN


def test_r2_close_wins_a_race_with_open(tmp_path, bundle):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    _MP.update(
        gate=lambda i: _gate(tmp_path, msha),
        decision=_open_decision(msha, clearance),
        clearance=clearance,
    )
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(8) as pool:
        jobs = [pool.apply_async(_mp_open if i % 2 == 0 else _mp_close, (i,)) for i in range(8)]
        [j.get(timeout=30) for j in jobs]
    gate = _gate(tmp_path, msha)
    assert gate.state() == "CLOSED"
    assert gate._records() is not None  # chain stayed valid whatever the order


def test_r2_lock_timeout_leaves_gate_closed(tmp_path, bundle, monkeypatch):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    monkeypatch.setattr(gate_module, "LOCK_TIMEOUT_S", 0.05)
    holder = os.open(tmp_path / "gate.jsonl.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        with pytest.raises(AdmissionGateRefusal):
            gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
        assert gate.state() == "CLOSED"
    finally:
        os.close(holder)


def test_r2_open_persistence_failure_stays_closed(tmp_path, bundle, monkeypatch):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)

    def broken(fd):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", broken)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    monkeypatch.undo()
    assert gate.state() == "CLOSED"
    assert _gate(tmp_path, msha).state() == "CLOSED"  # the partial OPEN cannot read as OPEN


def test_r2_close_without_any_persistence_still_closes_instance(tmp_path, bundle, monkeypatch):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    real_open = os.open

    def refuse(path, *args, **kwargs):
        if str(path).endswith((".closed", ".lock")):
            raise OSError("read-only filesystem")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse)
    assert gate.close(decided_by="op", reason="stop") is False  # not durable, never raises
    monkeypatch.undo()
    assert gate.state() == "CLOSED"  # this instance is closed regardless
    assert _gate(tmp_path, msha).is_open()  # documented limit: nothing was persisted


# ------------------------------- R4: native export, schemas, versions, bindings


def test_r4_real_exporter_output_is_accepted(bundle):
    manifest = bundle.dataset
    assert manifest["dataset_schema_version"] == 1  # produced by the exporter itself
    assert manifest["authoritative_manifest"]["epoch_role"] == "BURN_IN_EXPERIMENT"
    record = bundle.record()
    assert record.predecessor_dataset_id == bundle.dataset_id
    assert record.dataset_tree_sha256 and record.dataset_manifest_sha256


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("dataset_schema_version"),
        lambda m: m.__setitem__("dataset_schema_version", 2),
        lambda m: m.__setitem__("dataset_schema_version", True),
        lambda m: m.__setitem__("completeness_status", "PARTIAL"),
        lambda m: m.__setitem__("derivation", "OTHER"),
        lambda m: m.__setitem__("source_domain", "LIVE"),
        lambda m: m.__setitem__("source_authority", "RESEARCH"),
        lambda m: m["components"]["ppl_events"].__setitem__("sha256", "0" * 64),
        lambda m: m["components"]["burn_in_experiment_manifest"].__setitem__("status", "PARTIAL"),
        lambda m: m.__setitem__("authoritative_manifest", {}),
    ],
)
def test_r4_native_manifest_fields_are_enforced(bundle, mutate):
    mutate(bundle.dataset)
    with pytest.raises(SuccessionRefusal):
        bundle.record()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.__setitem__("identity_schema", "TEST-BOUNDARY"),
        lambda b: b.__setitem__("ppl_birth_code_sha", "9" * 40),
        lambda b: b.__setitem__("legacy_event_count", 99),
        lambda b: b.__setitem__("experiment_runtime_source_sha", "8" * 40),
        lambda b: b.__setitem__("source_event_count", 99),
        lambda b: b.__setitem__("source_first_sequence", 2),
        lambda b: b.__setitem__("source_last_timestamp", 12345.0),
        lambda b: b.__setitem__("ppl_stream_sha256", "7" * 64),
        lambda b: b.__setitem__("paper_epoch_id", "OTHER-EPOCH"),
        lambda b: b.__setitem__("source_authority", "FIN"),
        lambda b: b.__setitem__("extra_field", 1),
        lambda b: b.pop("legacy_boundary_sha256"),
    ],
)
def test_r4_self_consistent_but_non_native_boundary_refused(bundle, mutate):
    mutate(bundle.dataset["source_boundary_identity"])
    _reseal(bundle.dataset)  # every hash coherent again: only native semantics can refuse
    bundle.decision["predecessor_dataset_id"] = bundle.dataset["dataset_id"]
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_r4_identity_component_set_and_core_binding_enforced(bundle):
    comps = bundle.dataset["dataset_identity"]["components"]
    comps[:] = [c for c in comps if c["name"] != "regret"]
    _reseal(bundle.dataset)
    bundle.decision["predecessor_dataset_id"] = bundle.dataset["dataset_id"]
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_r4_core_partial_refused_even_when_resealed(bundle):
    for item in bundle.dataset["dataset_identity"]["components"]:
        if item["name"] == "authoritative_core":
            item["status"] = "PARTIAL"
    _reseal(bundle.dataset)
    bundle.decision["predecessor_dataset_id"] = bundle.dataset["dataset_id"]
    with pytest.raises(SuccessionRefusal):
        bundle.record()


def test_r4_tampered_authoritative_files_refused(bundle):
    for name in (
        "authoritative/burn_in_experiment_manifest.json",
        "authoritative/burn_in_experiment_config.json",
    ):
        files = {**bundle.files, "manifest.json": _js(bundle.dataset)}
        files[name] = files[name] + b" "
        kwargs = bundle.kwargs()
        kwargs["dataset_files"] = files
        with pytest.raises(SuccessionRefusal):
            verify_interruption_evidence(**kwargs)
    # dataset ledger differs from the ledger the decision is bound to
    files = {**bundle.files, "manifest.json": _js(bundle.dataset)}
    files["authoritative/ppl_events.jsonl"] = bundle.ledger + b"\n"
    kwargs = bundle.kwargs()
    kwargs["dataset_files"] = files
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


def test_r4_f00_role_export_is_not_a_burn_in_predecessor(tmp_path):
    with pytest.raises(SuccessionRefusal):
        Bundle(tmp_path, burn_in=False).record()


def test_r4_unsafe_or_missing_files_refused(bundle):
    base = {**bundle.files, "manifest.json": _js(bundle.dataset)}
    for extra in ("../evil", "/abs/evil", "a/../../evil", ""):
        kwargs = bundle.kwargs()
        kwargs["dataset_files"] = {**base, extra: b"x"}
        with pytest.raises(SuccessionRefusal):
            verify_interruption_evidence(**kwargs)
    for missing in ("manifest.json", "authoritative/ppl_events.jsonl"):
        kwargs = bundle.kwargs()
        kwargs["dataset_files"] = {k: v for k, v in base.items() if k != missing}
        with pytest.raises(SuccessionRefusal):
            verify_interruption_evidence(**kwargs)
    kwargs = bundle.kwargs()
    kwargs["dataset_files"] = {**base, "extra.bin": "not-bytes"}
    with pytest.raises(SuccessionRefusal):
        verify_interruption_evidence(**kwargs)


# ------------------------------------------------- R2: finite time at the gate


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), float("-inf"), True, False, "1", None, [1.0]]
)
def test_r2_non_finite_or_invalid_now_refused_before_any_mutation(tmp_path, bundle, bad):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    with pytest.raises(AdmissionGateRefusal):
        gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=bad)
    assert gate.state() == "CLOSED"
    assert not (tmp_path / "gate.jsonl").exists()  # nothing was written
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW + 1)
    assert gate.is_open()  # positive control with a finite fresh time


# ------------------------------------------- R3: durability is proven, not assumed


def _fsync_fails(monkeypatch):
    def broken(fd):
        raise OSError("storage unavailable")

    monkeypatch.setattr(os, "fsync", broken)


def test_r3_existing_marker_is_not_durable_by_presence(tmp_path, monkeypatch):
    g1 = _gate(tmp_path)
    _fsync_fails(monkeypatch)
    assert g1.close(decided_by="op", reason="r") is False  # marker created, sync failed
    assert (tmp_path / "gate.jsonl.closed").exists()
    assert g1.close(decided_by="op", reason="r") is False  # FileExistsError path: re-confirm fails
    g2 = _gate(tmp_path)  # another instance, same failure
    assert g2.close(decided_by="op", reason="r") is False
    assert g2.state() == "CLOSED"  # closed for every reader, durable for none
    monkeypatch.undo()  # storage is back
    assert g1.close(decided_by="op", reason="r") is True  # now proven: file + directory synced
    assert _gate(tmp_path).close(decided_by="op", reason="r") is True


def test_r3_directory_sync_failure_is_not_durable(tmp_path, monkeypatch):
    gate = _gate(tmp_path)
    real_fsync = os.fsync
    calls = {"n": 0}

    def file_ok_dir_fails(fd):
        calls["n"] += 1
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory sync failed")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", file_ok_dir_fails)
    assert gate.close(decided_by="op", reason="r") is False
    assert gate.close(decided_by="op", reason="r") is False
    monkeypatch.undo()
    assert gate.close(decided_by="op", reason="r") is True


def test_r3_short_marker_writes_are_completed_or_not_durable(tmp_path, monkeypatch):
    real_write = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: real_write(fd, bytes(data)[:3]))
    gate = _gate(tmp_path)
    assert gate.close(decided_by="op", reason="r") is True  # looped until complete
    doc = json.loads((tmp_path / "gate.jsonl.closed").read_bytes())
    assert doc["paper_epoch_id"] == SUCC_EPOCH
    monkeypatch.undo()
    # a zero-length write is a failure, never a silent truncation
    other = tmp_path / "other"
    other.mkdir()
    g2 = AdmissionGate(other / "gate.jsonl", paper_epoch_id=SUCC_EPOCH, manifest_sha256="m" * 64)
    monkeypatch.setattr(os, "write", lambda fd, data: 0)
    assert g2.close(decided_by="op", reason="r") is False
    assert g2.state() == "CLOSED"
    monkeypatch.undo()
    # the incomplete marker is repaired in place once writes work again
    assert g2.close(decided_by="op", reason="r") is True
    assert json.loads((other / "gate.jsonl.closed").read_bytes())["manifest_sha256"] == "m" * 64


def test_r3_marker_missing_but_valid_close_record(tmp_path, bundle, monkeypatch):
    _, clearance = _clearance_for(tmp_path, bundle)
    msha = clearance.manifest_sha256
    gate = _gate(tmp_path, msha)
    gate.open(decision_bytes=_open_decision(msha, clearance), clearance=clearance, now=NOW)
    assert gate.close(decided_by="op", reason="stop") is True
    (tmp_path / "gate.jsonl.closed").unlink()  # marker lost; CLOSE record remains valid
    fresh = _gate(tmp_path, msha)
    assert fresh.state() == "CLOSED"  # the valid CLOSE alone keeps it closed
    real_open = os.open

    def no_marker(path, *args, **kwargs):
        if str(path).endswith(".closed"):
            raise OSError("cannot create marker")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", no_marker)
    _fsync_fails(monkeypatch)
    assert fresh.close(decided_by="op", reason="again") is False  # journal cannot be re-synced
    monkeypatch.undo()
    monkeypatch.setattr(os, "open", no_marker)
    assert fresh.close(decided_by="op", reason="again") is True  # journal file+dir sync proven
    monkeypatch.undo()
    assert fresh.close(decided_by="op", reason="again") is True
    assert (tmp_path / "gate.jsonl.closed").exists()  # marker restored


def test_r3_marker_must_be_a_regular_file(tmp_path):
    gate = _gate(tmp_path)
    (tmp_path / "target").write_text("x")
    (tmp_path / "gate.jsonl.closed").symlink_to(tmp_path / "target")
    assert gate.state() == "CLOSED"  # a symlink marker still closes
    assert gate.close(decided_by="op", reason="r") is False  # but is never durable proof
