from observability.runtime_service_contract import validate_runtime_service_snapshot
from tests.cross_stack.generate_runtime_service_fixture import generate


def test_runtime_service_real_producer_api_boundary(tmp_path):
    fixture = generate(tmp_path)
    assert fixture["http_status"] == 200
    assert validate_runtime_service_snapshot(fixture["body"], transport=True)
    assert fixture["body"]["service"]["main_pid"] == 4321
    assert fixture["body"]["service"]["restart_count"] == 0
    assert fixture["body"]["deployment"]["status"] == "PRESENT"
    assert fixture["_proof"]["deployment_evidence_unchanged"]
    assert len(fixture["_proof"]["systemd_commands"]) == 1
