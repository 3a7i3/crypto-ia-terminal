"""Regression contract for manual-only Sphinx publication (no Actions execution)."""

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANUAL_MAIN = "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"


class ActionsLoader(yaml.SafeLoader):
    """Keep the YAML 1.2 Actions key 'on' from YAML 1.1 boolean coercion."""


ActionsLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def read_workflow():
    return yaml.load(
        (ROOT / ".github/workflows/sphinx.yml").read_text(encoding="utf-8"),
        Loader=ActionsLoader,
    )


def gate_matches(expression, event, ref):
    """Closed evaluator for this gate; not a general Actions interpreter."""
    normalized = re.sub(r"\s+", " ", expression.strip())
    if normalized != MANUAL_MAIN:
        raise ValueError("Publication condition changed: review required")
    return event == "workflow_dispatch" and ref == "refs/heads/main"


class TestSphinxPublicationGate(unittest.TestCase):
    def test_closed_event_surface(self):
        workflow = read_workflow()
        self.assertEqual(set(workflow["on"]), {"pull_request", "workflow_dispatch"})
        self.assertIn("docs/**", workflow["on"]["pull_request"]["paths"])
        self.assertIn(".github/workflows/sphinx.yml", workflow["on"]["pull_request"]["paths"])

    def test_event_ref_matrix(self):
        expression = read_workflow()["jobs"]["publish-docs"]["if"]
        for event in (
            "workflow_dispatch", "push", "pull_request", "pull_request_target",
            "workflow_run", "workflow_call", "repository_dispatch", "schedule",
        ):
            for ref in ("refs/heads/main", "refs/heads/feature", "refs/tags/main", "refs/pull/400/merge"):
                with self.subTest(event=event, ref=ref):
                    self.assertEqual(
                        gate_matches(expression, event, ref),
                        event == "workflow_dispatch" and ref == "refs/heads/main",
                    )

    def test_publication_needs_successful_validation(self):
        workflow = read_workflow()
        publish = workflow["jobs"]["publish-docs"]
        self.assertEqual(publish["needs"], "validate-docs")
        self.assertNotIn("always()", publish["if"])
        build = workflow["jobs"]["validate-docs"]
        self.assertNotIn("if", build)
        self.assertNotIn("continue-on-error", build)
        html = next(step for step in build["steps"] if step.get("name") == "Build Sphinx HTML")
        self.assertNotIn("continue-on-error", html)
        self.assertIn("sphinx-build -b html", html["run"])

    def test_least_privilege_and_secret_isolation(self):
        workflow = read_workflow()
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        jobs = workflow["jobs"]
        self.assertEqual(set(jobs), {"validate-docs", "publish-docs"})
        self.assertNotIn("permissions", jobs["validate-docs"])
        self.assertEqual(jobs["publish-docs"]["permissions"], {"contents": "write"})
        validation = yaml.dump(jobs["validate-docs"])
        for forbidden in ("secrets.", "actions-gh-pages", "curl", "git push"):
            self.assertNotIn(forbidden, validation)
        checkout = jobs["validate-docs"]["steps"][0]
        self.assertEqual(checkout["with"]["persist-credentials"], "false")

    def test_artifact_is_from_same_workflow_run(self):
        jobs = read_workflow()["jobs"]
        upload = next(step for step in jobs["validate-docs"]["steps"] if "upload-artifact" in step.get("uses", ""))
        download = jobs["publish-docs"]["steps"][0]
        self.assertEqual(download["uses"], "actions/download-artifact@v4")
        self.assertEqual(upload["with"]["name"], download["with"]["name"])
        self.assertEqual(set(download["with"]), {"name", "path"})
        deploy = jobs["publish-docs"]["steps"][1]
        self.assertEqual(download["with"]["path"], deploy["with"]["publish_dir"])

    def test_all_external_steps_are_manual_main(self):
        publish = read_workflow()["jobs"]["publish-docs"]
        for step in publish["steps"][1:]:
            with self.subTest(step=step["name"]):
                condition = step["if"]
                if condition.startswith("always() && "):
                    condition = condition.removeprefix("always() && ")
                self.assertEqual(condition, MANUAL_MAIN)

    def test_missing_condition_is_rejected(self):
        for condition in ("true", "github.ref == 'refs/heads/main'", MANUAL_MAIN + " || true"):
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    gate_matches(condition, "push", "refs/heads/main")


if __name__ == "__main__":
    unittest.main()
