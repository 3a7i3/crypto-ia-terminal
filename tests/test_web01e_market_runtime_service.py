"""WEB-01E — source contract for the passive MARKET runtime service.

These tests inspect only committed unit text. They do not call systemd, read
runtime environment files, open credentials, or contact an exchange/Telegram.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "scripts" / "systemd" / "crypto-market-snapshot.service"


def _text() -> str:
    return UNIT.read_text(encoding="utf-8")


def _lines_with(prefix: str) -> list[str]:
    return [line for line in _text().splitlines() if line.startswith(prefix)]


def test_market_snapshot_unit_is_passive_zero_key_service() -> None:
    text = _text()

    # WEB-01E needs only explicit non-secret paths/configuration. It must not
    # inherit the global or dedicated secret stores.
    assert _lines_with("EnvironmentFile=") == []
    assert ".env.secrets" not in "\n".join(_lines_with("Environment="))

    env_lines = "\n".join(_lines_with("Environment="))
    for secret_name_fragment in (
        "API_KEY",
        "API_SECRET",
        "SECRET_KEY",
        "BOT_TOKEN",
        "CHAT_ID",
        "PASSWORD",
    ):
        assert secret_name_fragment not in env_lines

    # No dependency directive is allowed to start/require an authority process.
    assert "After=crypto-advisor.service" in text
    assert "Wants=crypto-advisor.service" not in text
    assert "Requires=crypto-advisor.service" not in text
    assert "BindsTo=crypto-advisor.service" not in text


def test_market_snapshot_unit_has_exact_read_write_boundary() -> None:
    text = _text()

    assert "User=mathieu" in text
    assert "WorkingDirectory=/home/mathieu/crypto_ai_terminal" in text
    assert (
        "Environment=DP_LOG_DIR=/home/mathieu/crypto_ai_terminal/databases"
        in text
    )
    assert (
        "Environment=RADAR_MARKET_SNAPSHOT_PATH="
        "/home/mathieu/crypto_ai_terminal/databases/cryptoradar_market_snapshot.json"
        in text
    )
    assert (
        "ExecStart=/home/mathieu/crypto_ai_terminal/.venv/bin/python "
        "-m observability.market_radar_snapshot --interval 30"
        in text
    )
    assert "--once" not in "\n".join(_lines_with("ExecStart="))


def test_market_snapshot_unit_has_controlled_lifecycle_and_hardening() -> None:
    text = _text()

    assert "Restart=on-failure" in text
    assert "RestartSec=10s" in text
    assert "TimeoutStopSec=30" in text
    assert "NoNewPrivileges=true" in text
    assert "PrivateTmp=true" in text
    assert "ProtectSystem=full" in text
    assert "StandardOutput=journal" in text
    assert "StandardError=journal" in text
    assert "WantedBy=multi-user.target" in text
