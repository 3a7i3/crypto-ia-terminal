from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _pytest_run_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("run: pytest")
    ]


def test_coverage_publication_workflows_collect_only_maintained_tests() -> None:
    for name in ("coverage.yml", "codecov.yml", "coveralls.yml"):
        text = _workflow(name)
        runs = _pytest_run_lines(text)

        assert runs, f"{name}: no pytest run command found"
        assert all(
            "pytest tests/" in line for line in runs
        ), f"{name}: pytest collection is not explicitly rooted in tests/"
        assert all(
            not line.startswith("run: pytest --cov")
            for line in runs
        ), f"{name}: bare repository-root pytest coverage collection detected"


def test_coverage_publication_excludes_resource_sensitive_markers() -> None:
    for name in ("coverage.yml", "codecov.yml", "coveralls.yml"):
        text = _workflow(name)

        assert '--ignore=tests/stress' in text
        assert '-m "not performance and not slow"' in text


def test_panels_workflow_keeps_maintained_suite_binding() -> None:
    text = _workflow("test-panels.yml")

    assert "run: pytest tests/" in text


def test_panels_e2e_entrypoint_is_optional_and_explicit() -> None:
    text = _workflow("test-panels.yml")
    entrypoint = "test_panels_with_report.py"

    assert entrypoint in text
    assert f"hashFiles('{entrypoint}') != ''" in text
    assert f"hashFiles('{entrypoint}') == ''" in text
    assert f"run: python {entrypoint}" in text


def test_ci_scope_does_not_add_alternative_panel_entrypoint() -> None:
    text = _workflow("test-panels.yml")
    python_runs = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("run: python ")
    ]

    assert python_runs == ["run: python test_panels_with_report.py"]
