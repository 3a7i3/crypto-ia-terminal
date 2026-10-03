from tests.cross_stack.generate_microstructure_fixture import generate_microstructure_fixture


def test_microstructure_real_projection_artifact_reader_get_roundtrip(tmp_path):
    result = generate_microstructure_fixture(tmp_path)
    assert result["http_status"] == 200
    assert result["_proof"]["source_unchanged"]
    assert result["body"]["coverage"]["requested"] == 3
    assert [r["freshness_classification"] for r in result["body"]["rows"]] == ["FRESH", "STALE", "NOT_AVAILABLE"]
