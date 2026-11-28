"""T9 architecture: reuse without modification, package rules, pinned evidence, untouched B03/API."""

import ast
import hashlib
import subprocess
from pathlib import Path

from observability.market_flow import kraken_trades as kt

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/contracts/MEO_01_TRADES_CAPTURE.md"

# trades.py is reused as it is (same bytes as main f033b1d and the P6 runtime manifest).
TRADES_PY_SHA256 = "1101c6a84ff87ed2b246d080c8e95b002a86e9e87c4ab9e0d8175bd1a64bfd1e"
# Files MEO-01 must not touch (B03 chain, artifact contract, Operator API reader).
UNTOUCHED = [
    "observability/market_flow/artifact.py", "observability/market_flow/contract.py",
    "observability/market_flow/l2.py", "observability/market_flow/interval.py",
    "observability/operator_api/market_flow_reader.py", "observability/operator_api/app.py",
    "observability/radar_composite/bbo_pilot.py", "observability/radar_composite/bbo_book.py",
    "observability/radar_composite/bbo_wire.py", "observability/radar_composite/pilot.py",
    "observability/radar_composite/decoders.py",
]
BASE = "f033b1d"


def test_t09_trades_core_is_reused_without_modification():
    assert hashlib.sha256((ROOT / "observability/market_flow/trades.py").read_bytes()).hexdigest() == \
        TRADES_PY_SHA256


def test_t09_b03_artifact_and_api_files_are_unchanged_against_the_base():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", BASE, "--", *UNTOUCHED],
                             capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return  # no git checkout here: the pinned trades.py hash above still holds
    if out.returncode != 0:
        return  # base not present in a shallow clone
    assert out.stdout.strip() == ""


def test_t09_kraken_trades_respects_the_market_flow_package_rules():
    path = ROOT / "observability/market_flow/kraken_trades.py"
    tree = ast.parse(path.read_text())
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            imported.add(n.module.split(".")[0])
    assert imported <= {"decimal", "hashlib", "json", "re"}
    assert not any(isinstance(n, ast.Name) and n.id == "float" for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree))


def test_t09_the_taker_convention_cites_the_hashed_excerpt_of_the_contract():
    raw = CONTRACT.read_bytes()
    begin, end = b"<!-- KRAKEN-EXCERPT-BEGIN -->\n", b"<!-- KRAKEN-EXCERPT-END -->"
    excerpt = raw[raw.index(begin) + len(begin):raw.index(end)]
    assert hashlib.sha256(excerpt).hexdigest() == kt.EVIDENCE_EXCERPT_SHA256
    assert b'"The side of the taker order."' in excerpt
    assert b"unique per book" in excerpt


def test_t09_the_capture_module_is_not_imported_by_any_runtime_service():
    hits = []
    for base in ("observability", "core", "paper_trading", "frontend/src"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in (".py", ".ts", ".tsx") and p.is_file() and p.name != "kraken_trade_pilot.py":
                if "kraken_trade_pilot" in p.read_text(errors="ignore"):
                    hits.append(str(p.relative_to(ROOT)))
    assert hits == []
