from pathlib import Path

advisor = Path("core/advisor_loop.py")
src = advisor.read_text(encoding="utf-8")
old = '''def _validated_in_both_domains(execution_cert: Any, scan_cert: Any) -> list[str]:
    """Intersection ordonnée des symboles validés par les deux domaines."""
    execution_valid = set(execution_cert.validated_symbols)
    scan_valid = set(scan_cert.validated_symbols)
    return [
        symbol
        for symbol in execution_cert.configured_symbols
        if symbol in execution_valid and symbol in scan_valid
    ]
'''
new = '''def _validated_in_both_domains(execution_cert: Any, scan_cert: Any) -> list[str]:
    """Intersection canonique ordonnée des symboles validés dans les deux domaines."""
    execution_valid = list(execution_cert.validated_symbols)
    scan_valid = set(scan_cert.validated_symbols)
    return [
        symbol
        for symbol in execution_valid
        if symbol in scan_valid
    ]
'''
if src.count(old) != 1:
    raise SystemExit("MASTER target helper not found exactly once")
advisor.write_text(src.replace(old, new), encoding="utf-8")

core = Path("core/universe_certification.py")
core_src = core.read_text(encoding="utf-8")
replacements = {
    '"""Find only the ticker belonging to the selected derivative market."""':
        '"""Find only the ticker belonging to the selected certified market."""',
    '    derivative market exists, is not explicitly inactive, and has a finite\n':
        '    allowed market exists, is not explicitly inactive, and has a finite\n',
}
for old_text, new_text in replacements.items():
    if core_src.count(old_text) != 1:
        raise SystemExit(
            f"MASTER documentation target not found exactly once: {old_text!r}"
        )
    core_src = core_src.replace(old_text, new_text)
core.write_text(core_src, encoding="utf-8")

tests = Path("tests/test_advisor_loop_universe_certification_wiring.py")
test_src = tests.read_text(encoding="utf-8")
marker = "def test_settle_suffixed_pin_normalizes_dual_domain_intersection"
if marker in test_src:
    raise SystemExit("MASTER regression test already exists")
test_src += '''


def test_settle_suffixed_pin_normalizes_dual_domain_intersection(
    monkeypatch, _artifact_path
):
    markets, tickers = _dual_domain_markets_tickers(
        "BTC/USDT:USDT", "BTC/USDT", 65000.0
    )
    _patch_same_evidence(monkeypatch, markets, tickers)

    symbols, snapshot = advisor_loop._resolve_pinned_universe_boot(
        ["BTC/USDT:USDT"]
    )

    assert symbols == ["BTC/USDT"]
    assert snapshot == {"n_symbols_configured": 1, "n_symbols_validated": 1}
    payload = json.loads(_artifact_path.read_text(encoding="utf-8"))
    assert payload["validated_symbols"] == ["BTC/USDT"]
'''
tests.write_text(test_src, encoding="utf-8")
