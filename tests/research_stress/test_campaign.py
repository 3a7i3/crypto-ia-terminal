"""Preuves source-only sur fixtures synthétiques ; aucune donnée production."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from decimal import ROUND_DOWN, localcontext
from pathlib import Path

import pytest

from research_stress.campaign import build_report, risk_envelopes, verify_report
from research_stress.protocol import ProtocolError, canonical, digest, strict_json, validate_protocol
from tests.research_replay.test_rl_replay_01_factual import _build_dataset, _closed_population, _unresolved_population

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs/research/paper_stress_401/protocol.json"
SHA = "a" * 40


@pytest.fixture
def protocol():
    return strict_json(PROTOCOL.read_bytes())


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_no_dataset_never_manufactures_performance(protocol):
    envelope = build_report(protocol, research_code_sha=SHA)
    verify_report(envelope, protocol)
    assert envelope["report"]["readiness"] == "INSUFFICIENT_EVIDENCE"
    assert envelope["report"]["factual_baseline"]["status"] == "NOT_AVAILABLE"
    assert all(r["results"] is None for r in envelope["report"]["comparisons"].values())


def test_known_analytic_loss_and_joint_vs_factorial(protocol):
    rows = risk_envelopes(protocol)
    assert len(rows) == 9
    arms = {r["arm_ids"][0]: r for r in rows if r["arm_ids"]}
    assert [arms[a]["max_notional_usdt"] for a in "ABC"] == ["20", "200", "500"]
    scenario = arms["C"]["scenarios"][0]
    # 500*(0.1) + 500*(2*10 + 2*5 + 2)/10000 = 51.6
    assert scenario["loss_usdt"] == "51.60"
    assert scenario["breaches_proposed_loss_stop"] is False
    assert any(s["breaches_proposed_loss_stop"] for s in arms["C"]["scenarios"])
    assert all(len(r["scenarios"]) == 72 for r in rows)
    assert arms["C"]["all_same_symbol_breaches_concentration_stop"] is True
    assert arms["C"]["breaches_proposed_exposure_stop"] is False


def test_global_decimal_context_does_not_change_results(protocol):
    reference = canonical(risk_envelopes(protocol))
    with localcontext() as ctx:
        ctx.prec = 3
        ctx.rounding = ROUND_DOWN
        assert canonical(risk_envelopes(protocol)) == reference


@pytest.mark.parametrize("key,value", [
    ("activation_allowed", True), ("status", "RUNNING"), ("capital_usdt", "0"),
    ("capital_usdt", "NaN"), ("capital_usdt", "Infinity"), ("capital_usdt", "-1"),
    ("capital_usdt", 1000), ("protected_epoch", "future"),
])
def test_invalid_protocol_fails_closed(protocol, key, value):
    protocol[key] = value
    with pytest.raises(ProtocolError):
        build_report(protocol, research_code_sha=SHA)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'[]', b'{'])
def test_strict_json(raw):
    with pytest.raises(ProtocolError):
        strict_json(raw)


def test_duplicate_arms_and_unknown_fields_rejected(protocol):
    protocol["arms"][1] = protocol["arms"][0]
    with pytest.raises(ProtocolError):
        validate_protocol(protocol)


def test_missing_liquidity_is_not_a_zero_cost(protocol):
    protocol["cost_grid"].pop("spread_bps")
    with pytest.raises(ProtocolError):
        risk_envelopes(protocol)


def test_stale_missing_policy_and_unknown_timeout(protocol):
    assert protocol["temporal"]["baseline_timeout_seconds"] is None
    protocol["stopping_proposals"]["max_stale_marks"] = 1
    with pytest.raises(ProtocolError):
        validate_protocol(protocol)


def test_deterministic_and_source_config_identity(protocol):
    a = build_report(protocol, research_code_sha=SHA)
    assert canonical(a) == canonical(build_report(protocol, research_code_sha=SHA))
    assert a["report"]["report_id"] != build_report(protocol, research_code_sha="b"*40)["report"]["report_id"]
    alternate = copy.deepcopy(protocol)
    alternate["capital_usdt"] = "2000"
    assert a["report"]["report_id"] != build_report(alternate, research_code_sha=SHA)["report"]["report_id"]


def test_tampered_report_rejected_even_with_rehashed_content(protocol):
    envelope = build_report(protocol, research_code_sha=SHA)
    envelope["report"]["risk_envelopes"][0]["max_notional_usdt"] = "0"
    envelope["manifest"]["report_sha256"] = digest(envelope["report"])
    with pytest.raises(ValueError):
        verify_report(envelope, protocol)


def test_factual_integration_deterministic_and_no_source_mutation(protocol, tmp_path):
    dataset = _build_dataset(tmp_path, _closed_population())
    protected = tmp_path / "protected-runtime-synthetic"
    protected.mkdir()
    (protected / "ledger").write_bytes(b"SYNTHETIC_PROTECTED_LEDGER")
    before = snapshot(tmp_path)
    report = build_report(protocol, research_code_sha=SHA, dataset_path=dataset,
                          input_class="SYNTHETIC_TEST_ONLY")
    assert snapshot(tmp_path) == before
    verify_report(report, protocol)
    baseline = report["report"]["factual_baseline"]
    assert baseline["net_pnl_distribution_usdt"]["n"] == 3
    assert baseline["net_pnl_distribution_usdt"]["values"] == pytest.approx([8.0, 8.0, -7.0])
    assert report["report"]["identity"]["input_class"] == "SYNTHETIC_TEST_ONLY"
    assert canonical(report) == canonical(build_report(protocol, research_code_sha=SHA,
        dataset_path=dataset, input_class="SYNTHETIC_TEST_ONLY"))


def test_unresolved_is_not_zero_pnl(protocol, tmp_path):
    dataset = _build_dataset(tmp_path, _unresolved_population())
    result = build_report(protocol, research_code_sha=SHA, dataset_path=dataset,
                          input_class="SYNTHETIC_TEST_ONLY")
    assert result["report"]["factual_baseline"]["net_pnl_distribution_usdt"]["n"] == 0
    assert result["report"]["factual_baseline"]["net_pnl_distribution_usdt"]["mean"] is None


def test_corrupt_dataset_aborts_before_results(protocol, tmp_path):
    dataset = _build_dataset(tmp_path, _closed_population())
    (dataset / "authoritative/ppl_events.jsonl").write_bytes(b"{}\n")
    with pytest.raises(ValueError):
        build_report(protocol, research_code_sha=SHA, dataset_path=dataset,
                     input_class="DECLARED_IMMUTABLE_RESEARCH_COPY")


def test_input_class_required(protocol, tmp_path):
    with pytest.raises(ValueError):
        build_report(protocol, research_code_sha=SHA, dataset_path=tmp_path)


def test_import_and_run_with_mutation_network_process_denied(tmp_path):
    # Nouvelle VM Python : couvre les imports transitifs, pas seulement l'AST.
    code = '''
import sys, os
from pathlib import Path
protocol_raw = Path(sys.argv[1]).read_bytes()
def guard(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.system', 'os.spawn', 'os.exec')):
        raise RuntimeError('Effet réseau/process interdit: ' + event)
    if event == 'open':
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            raise RuntimeError('Écriture interdite')
    if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.link', 'os.symlink', 'os.chmod'):
        raise RuntimeError('Mutation interdite')
sys.addaudithook(guard)
from research_stress.campaign import build_report
from research_stress.protocol import strict_json
build_report(strict_json(protocol_raw), research_code_sha='a'*40)
assert 'paper_trading.mexc_simulator' not in sys.modules
assert 'paper_trading.durable_event_store' not in sys.modules
assert 'core.advisor_loop' not in sys.modules
'''
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
    before = snapshot(tmp_path)
    run = subprocess.run([sys.executable, "-B", "-c", code, str(PROTOCOL)], cwd=tmp_path,
                         env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert snapshot(tmp_path) == before


def test_cli_stdout_reproducible(tmp_path):
    args = [sys.executable, "-B", "-m", "research_stress", "--protocol", str(PROTOCOL),
            "--research-code-sha", SHA]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
    first = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, check=True)
    second = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, check=True)
    assert first.stdout == second.stdout
    verify_report(json.loads(first.stdout), strict_json(PROTOCOL.read_bytes()))
    assert snapshot(tmp_path) == {}
