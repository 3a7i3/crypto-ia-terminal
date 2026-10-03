from tests.cross_stack.generate_research_publication_fixture import (
    generate_research_publication_fixture,
)
from observability.research_lab_schema import snapshot_sha256


def test_u4_builder_artifact_reader_api(tmp_path):
    result = generate_research_publication_fixture(tmp_path)
    assert result["http_status"] == 200
    assert result["_proof"]["builder_invoked"]
    assert result["_proof"]["snapshot_sha256"] == snapshot_sha256(result["body"])
    assert result["body"]["population"]["n"] == 3
    assert (
        result["body"]["provenance"]["source_artifacts"][1]["sha256"]
        == result["_proof"]["manifest_sha256"]
    )
