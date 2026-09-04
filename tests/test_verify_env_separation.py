"""
tests/test_verify_env_separation.py — ENV-01 : tests du vérificateur
scripts/verify_env_separation.sh.

CRITIQUE : ce test n'invoque le script QUE contre des fixtures TEMPORAIRES
factices (tmp_path), jamais contre un vrai `.env` / `.env.secrets` du dépôt.
Aucune valeur factice ici ne ressemble à un secret réel — ce sont des
placeholders de test (`dummy_secret_value`, `xyz`, etc.).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_env_separation.sh"


def run_verifier(env_path, secrets_path, registry_path, extra_args=None):
    args = [
        "bash",
        str(SCRIPT),
        "--env",
        str(env_path),
        "--secrets",
        str(secrets_path),
        "--registry",
        str(registry_path),
    ]
    if extra_args:
        args.extend(extra_args)
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return result


def parse_report(stdout: str) -> dict:
    report = {}
    for line in stdout.splitlines():
        if "=" in line and not line.startswith("---"):
            key, _, value = line.partition("=")
            report[key] = value
    return report


@pytest.fixture
def registry_file(tmp_path):
    path = tmp_path / ".env.secrets.example.dummy"
    path.write_text("EXAMPLE_SECRET_TOKEN=\nEXAMPLE_API_KEY=\n", encoding="utf-8")
    return path


class TestVerifierNeverPrintsValues:
    def test_clean_separation_reports_zero_leak(self, tmp_path, registry_file):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text("NON_SECRET_A=1\nNON_SECRET_B=2\n", encoding="utf-8")
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text(
            "EXAMPLE_SECRET_TOKEN=dummy_secret_value\nEXAMPLE_API_KEY=xyz\n",
            encoding="utf-8",
        )
        secrets_file.chmod(0o600)

        result = run_verifier(env_file, secrets_file, registry_file)
        assert result.returncode == 0
        report = parse_report(result.stdout)

        assert report["ENV_FILE_PRESENT"] == "YES"
        assert report["SECRETS_FILE_PRESENT"] == "YES"
        assert report["SECRET_KEYS_IN_ENV_COUNT"] == "0"
        assert report["DUPLICATE_KEY_COUNT"] == "0"
        assert report["SECRETS_MODE_OK"] == "YES"

        # Values never appear anywhere in stdout/stderr.
        assert "dummy_secret_value" not in result.stdout
        assert "xyz" not in result.stdout
        assert "dummy_secret_value" not in result.stderr

    def test_detects_secret_leaked_into_env(self, tmp_path, registry_file):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text(
            "NON_SECRET_A=1\nEXAMPLE_SECRET_TOKEN=should_not_be_here\n",
            encoding="utf-8",
        )
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text("EXAMPLE_API_KEY=xyz\n", encoding="utf-8")
        secrets_file.chmod(0o600)

        result = run_verifier(env_file, secrets_file, registry_file)
        report = parse_report(result.stdout)

        assert report["SECRET_KEYS_IN_ENV_COUNT"] == "1", (
            "le vérificateur doit détecter EXAMPLE_SECRET_TOKEN (nom "
            "connu comme secret-class) présent dans .env"
        )
        assert "should_not_be_here" not in result.stdout

    def test_detects_duplicate_keys(self, tmp_path, registry_file):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text(
            "NON_SECRET_A=1\nNON_SECRET_A=2\nNON_SECRET_B=3\n", encoding="utf-8"
        )
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text("EXAMPLE_API_KEY=xyz\n", encoding="utf-8")
        secrets_file.chmod(0o600)

        result = run_verifier(env_file, secrets_file, registry_file)
        report = parse_report(result.stdout)

        assert report["DUPLICATE_KEY_COUNT"] == "1"

    def test_flags_insecure_secrets_file_permissions(self, tmp_path, registry_file):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text("NON_SECRET_A=1\n", encoding="utf-8")
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text("EXAMPLE_API_KEY=xyz\n", encoding="utf-8")
        secrets_file.chmod(0o644)  # world-readable — should be flagged

        result = run_verifier(env_file, secrets_file, registry_file)
        report = parse_report(result.stdout)

        assert report["SECRETS_MODE_OK"] == "NO"

    def test_missing_files_are_reported_as_absent_not_crashed(
        self, tmp_path, registry_file
    ):
        env_file = tmp_path / "does_not_exist.env"
        secrets_file = tmp_path / "does_not_exist.secrets"

        result = run_verifier(env_file, secrets_file, registry_file)
        report = parse_report(result.stdout)

        assert result.returncode == 0
        assert report["ENV_FILE_PRESENT"] == "NO"
        assert report["SECRETS_FILE_PRESENT"] == "NO"
        assert report["SECRET_KEYS_IN_ENV_COUNT"] == "0"

    def test_verbose_names_mode_shows_set_unset_never_values(
        self, tmp_path, registry_file
    ):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text("NON_SECRET_A=1\n", encoding="utf-8")
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text(
            "EXAMPLE_SECRET_TOKEN=super_secret_value_123\n", encoding="utf-8"
        )
        secrets_file.chmod(0o600)

        result = run_verifier(
            env_file, secrets_file, registry_file, extra_args=["--verbose-names"]
        )

        assert "EXAMPLE_SECRET_TOKEN=SET" in result.stdout
        assert "EXAMPLE_API_KEY=UNSET" in result.stdout
        assert "super_secret_value_123" not in result.stdout
        assert "super_secret_value_123" not in result.stderr

    def test_default_mode_omits_verbose_names_block(self, tmp_path, registry_file):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text("NON_SECRET_A=1\n", encoding="utf-8")
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text("EXAMPLE_API_KEY=xyz\n", encoding="utf-8")
        secrets_file.chmod(0o600)

        result = run_verifier(env_file, secrets_file, registry_file)

        assert "verbose-names" not in result.stdout
        assert "SET" not in result.stdout
        assert "UNSET" not in result.stdout


def test_script_never_reads_real_repo_env_files():
    """Static guard: nothing in this test module ever points the verifier at
    the repository's real .env or .env.secrets — every fixture above is a
    tmp_path file with a `.dummy` suffix."""
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    real_env_marker = "--env" + "\", \"" + ".env" + "\""
    real_secrets_marker = "--secrets" + "\", \"" + ".env.secrets" + "\""
    body_lines = [ln for ln in lines if "forbidden" not in ln and "real_" not in ln]
    body = "\n".join(body_lines)
    assert real_env_marker not in body
    assert real_secrets_marker not in body
