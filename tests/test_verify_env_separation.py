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
        assert report["DUPLICATE_WITHIN_ENV_COUNT"] == "0"
        assert report["DUPLICATE_WITHIN_SECRETS_COUNT"] == "0"
        assert report["CROSS_FILE_DUPLICATE_KEY_COUNT"] == "0"
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

    def test_detects_duplicate_keys_within_env(self, tmp_path, registry_file):
        env_file = tmp_path / ".env.dummy"
        env_file.write_text(
            "NON_SECRET_A=1\nNON_SECRET_A=2\nNON_SECRET_B=3\n", encoding="utf-8"
        )
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text("EXAMPLE_API_KEY=xyz\n", encoding="utf-8")
        secrets_file.chmod(0o600)

        result = run_verifier(env_file, secrets_file, registry_file)
        report = parse_report(result.stdout)

        assert report["DUPLICATE_WITHIN_ENV_COUNT"] == "1"
        assert report["DUPLICATE_WITHIN_SECRETS_COUNT"] == "0"
        assert report["CROSS_FILE_DUPLICATE_KEY_COUNT"] == "0", (
            "un doublon INTRA-fichier (.env) ne doit jamais être compté "
            "comme un doublon CROSS-FILE — ce sont deux propriétés "
            "distinctes"
        )

    def test_cross_file_duplicate_key_detected_without_leaking_values(
        self, tmp_path, registry_file
    ):
        """ENV-01R blocker #3 — SHARED_KEY defined in both .env (foo) and
        .env.secrets (bar): CROSS_FILE_DUPLICATE_KEY_COUNT must report 1,
        and neither value may ever appear in the script's output."""
        env_file = tmp_path / ".env.dummy"
        env_file.write_text("SHARED_KEY=foo\n", encoding="utf-8")
        secrets_file = tmp_path / ".env.secrets.dummy"
        secrets_file.write_text("SHARED_KEY=bar\n", encoding="utf-8")
        secrets_file.chmod(0o600)

        result = run_verifier(env_file, secrets_file, registry_file)
        report = parse_report(result.stdout)

        assert report["CROSS_FILE_DUPLICATE_KEY_COUNT"] == "1"
        assert report["DUPLICATE_WITHIN_ENV_COUNT"] == "0"
        assert report["DUPLICATE_WITHIN_SECRETS_COUNT"] == "0"

        assert "foo" not in result.stdout
        assert "bar" not in result.stdout
        assert "foo" not in result.stderr
        assert "bar" not in result.stderr

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


# ═══════════════════════════════════════════════════════════════════════════
# ENV-01R2 — Active Telegram template coverage
#
# Source-only test: reads the TRACKED template `.env.secrets.example` at the
# repo root and asserts that every currently source-documented ACTIVE
# Telegram bot token/chat-id NAME (per docs/architecture/TELEGRAM_BOT_REGISTRY.md
# § "Bots actifs (5 bots)") has a placeholder line present (name declared,
# value empty). This never opens the real, untracked `.env` / `.env.secrets`
# files — only the tracked example template and doc/source names hardcoded
# below from the registry.
# ═══════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_EXAMPLE = REPO_ROOT / ".env.secrets.example"

# Active per docs/architecture/TELEGRAM_BOT_REGISTRY.md § "Bots actifs (5 bots)"
# (contrat fonctionnel v2.0, 2026-08-28). None of these are RETIRED/LEGACY.
ACTIVE_TELEGRAM_TEMPLATE_NAMES = [
    "RADAR_BOT_TOKEN",
    "RADAR_CHAT_ID",
    "MON_PORTFOLIO_BOT_TOKEN",
    "MON_PORTFOLIO_CHAT_ID",
    "QUANT_CRYPTO_BOT_TOKEN",
    "QUANT_CRYPTO_CHAT_ID",
    "RAPPORT_AUTOMATIQUE_BOT_TOKEN",
    "RAPPORT_AUTOMATIQUE_CHAT_ID",
    "PAPER_ARENA_BOT_TOKEN",
    "PAPER_ARENA_CHAT_ID",
]


class TestActiveTelegramTemplateCoverage:
    def test_secrets_example_exists(self):
        assert SECRETS_EXAMPLE.is_file(), (
            f"tracked template missing: {SECRETS_EXAMPLE}"
        )

    @pytest.mark.parametrize("name", ACTIVE_TELEGRAM_TEMPLATE_NAMES)
    def test_active_bot_name_has_empty_placeholder(self, name):
        """Every active Telegram bot token/chat-id name must appear as a
        bare `NAME=` (or `NAME=   # comment`) placeholder in the tracked
        template, with no value to its right — never a real credential."""
        content = SECRETS_EXAMPLE.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.startswith(f"{name}=")]
        assert lines, f"{name} placeholder not found in {SECRETS_EXAMPLE.name}"
        for line in lines:
            value = line.split("=", 1)[1].split("#", 1)[0].strip()
            assert value == "", (
                f"{name} must be an empty placeholder in the tracked template, "
                f"found non-empty value on line: {line!r}"
            )

    def test_radar_not_described_as_generic_telegram_bot_token(self):
        """TELEGRAM_BOT_TOKEN must never be documented as Radar's polling
        identity (@RadarCrypto1_bot) in the tracked secrets template — Radar
        is a dedicated identity with no fallback (RADAR_BOT_TOKEN)."""
        content = SECRETS_EXAMPLE.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "RadarCrypto1_bot" in line:
                assert "TELEGRAM_BOT_TOKEN" not in line, (
                    f"TELEGRAM_BOT_TOKEN wrongly tied to @RadarCrypto1_bot: {line!r}"
                )
