"""Source policy checks only: never dispatch a workflow or publish Pages."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def test_sphinx_has_no_automatic_or_indirect_entrypoint():
    doc = workflow("sphinx.yml")
    assert set(doc["on"]) == {"workflow_dispatch"}
    assert doc["permissions"] == {"contents": "read"}
    job = doc["jobs"]["build-docs"]
    guard = "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    assert job["if"] == guard
    assert job["permissions"] == {"contents": "write"}
    deploy = [step for step in job["steps"] if step.get("uses", "").startswith("peaceiris/actions-gh-pages@")]
    assert len(deploy) == 1
    assert deploy[0]["if"] == guard


def test_required_source_gates_keep_automatic_read_only_validation():
    required = {
        "ci.yml": {"LINT REGRESSION GATE", "TEST REGRESSION GATE"},
        "orchestrator-healthcheck.yml": {"integrity"},
        "cross-stack-compat.yml": {"CROSS-STACK COMPATIBILITY GATE"},
    }
    for name, contexts in required.items():
        doc = workflow(name)
        assert {"pull_request", "push"} <= set(doc["on"])
        assert doc["permissions"] == {"contents": "read"}
        names = {job.get("name", key) for key, job in doc["jobs"].items()}
        assert contexts <= names


def test_no_tracked_workflow_has_indirect_automatic_publication_entrypoint():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        doc = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        assert not {"workflow_run", "workflow_call", "repository_dispatch", "pull_request_target"} & set(doc["on"])
        assert not any("uses" in job for job in doc["jobs"].values())
