"""
tests/scripts/test_radar_bot.py — Régression forensique pour scripts/radar_bot.py.

Vérifie que le bot CryptoRadar respecte le contrat d'isolation des tokens
Telegram (docs/TELEGRAM_CONSTITUTION.md, Principe 3 : "No Cross-Identity
Token Fallback") :

  - RADAR_BOT_TOKEN / RADAR_CHAT_ID alimentent seuls le bot.
  - TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ne peuvent JAMAIS servir de repli.
  - L'absence de RADAR_BOT_TOKEN provoque une sortie explicite (exit code 1)
    avec un message d'erreur clair, sans jamais exposer de valeur secrète.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.radar_bot as radar_bot

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RADAR_BOT_PATH = REPO_ROOT / "scripts" / "radar_bot.py"

# Variables d'environnement Telegram à neutraliser avant chaque test, pour ne
# pas hériter accidentellement de valeurs définies dans l'environnement CI/dev.
_ENV_VARS = (
    "RADAR_BOT_TOKEN",
    "RADAR_CHAT_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)


def _reload_radar_bot():
    """Recharge scripts.radar_bot pour ré-évaluer TOKEN/CHAT_ID au niveau module."""
    return importlib.reload(radar_bot)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Neutralise les variables Telegram avant chaque test, puis recharge le module."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    _reload_radar_bot()
    yield
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    _reload_radar_bot()


def _run_subprocess(env_overrides: dict) -> subprocess.CompletedProcess:
    """Exécute scripts/radar_bot.py dans un sous-processus avec un env contrôlé."""
    import os

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in _ENV_VARS
    }
    env.update(env_overrides)
    # Empêche tout accès réseau accidentel si TOKEN était présent par erreur :
    # le sous-processus est censé sortir avant tout appel réseau.
    return subprocess.run(
        [sys.executable, str(RADAR_BOT_PATH)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


# ── TEST 1 : RADAR_BOT_TOKEN feeds RadarBot ───────────────────────────────────


def test_radar_bot_token_feeds_radarbot(monkeypatch):
    monkeypatch.setenv("RADAR_BOT_TOKEN", "dedicated-radar-token")
    mod = _reload_radar_bot()
    assert mod.TOKEN == "dedicated-radar-token"


# ── TEST 2 : TELEGRAM_BOT_TOKEN alone cannot feed RadarBot ───────────────────


def test_telegram_bot_token_alone_cannot_feed_radarbot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "generic-alerts-token")
    mod = _reload_radar_bot()
    assert mod.TOKEN == ""
    assert mod.TOKEN != "generic-alerts-token"


# ── TEST 3 : absent RADAR_BOT_TOKEN → explicit exit code 1 ──────────────────


def test_missing_radar_bot_token_exits_with_code_1():
    result = _run_subprocess(env_overrides={})
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "RADAR_BOT_TOKEN" in combined


def test_telegram_bot_token_present_still_exits_with_code_1():
    """Même si TELEGRAM_BOT_TOKEN est défini, l'absence de RADAR_BOT_TOKEN doit
    provoquer la sortie — la présence d'un token générique ne doit jamais
    "sauver" le démarrage du bot CryptoRadar."""
    result = _run_subprocess(env_overrides={"TELEGRAM_BOT_TOKEN": "generic-alerts-token"})
    assert result.returncode == 1


# ── TEST 4 : RADAR_CHAT_ID is used ───────────────────────────────────────────


def test_radar_chat_id_is_used(monkeypatch):
    monkeypatch.setenv("RADAR_BOT_TOKEN", "dedicated-radar-token")
    monkeypatch.setenv("RADAR_CHAT_ID", "123456789")
    mod = _reload_radar_bot()
    assert mod.CHAT_ID == "123456789"
    assert mod.ALLOWED_CHATS == {"123456789"}


def test_telegram_chat_id_alone_does_not_feed_chat_id(monkeypatch):
    monkeypatch.setenv("RADAR_BOT_TOKEN", "dedicated-radar-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999999999")
    mod = _reload_radar_bot()
    assert mod.CHAT_ID == ""
    assert mod.CHAT_ID != "999999999"
    assert mod.ALLOWED_CHATS == set()


# ── TEST 5 : no cross-identity token fallback ────────────────────────────────


def test_no_cross_identity_token_fallback_in_source():
    """Le code source ne doit contenir aucun repli TELEGRAM_BOT_TOKEN/CHAT_ID
    pour alimenter TOKEN/CHAT_ID de CryptoRadar (Principe 3 de la constitution)."""
    source = RADAR_BOT_PATH.read_text(encoding="utf-8")
    forbidden_patterns = (
        'os.getenv("RADAR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")',
        "os.getenv('RADAR_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')",
        'os.getenv("RADAR_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")',
        "os.getenv('RADAR_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID')",
    )
    for pattern in forbidden_patterns:
        assert pattern not in source, f"Forbidden fallback pattern found: {pattern}"


def test_no_cross_identity_token_fallback_at_runtime(monkeypatch):
    """Même avec RADAR_BOT_TOKEN absent et TELEGRAM_BOT_TOKEN présent, TOKEN
    doit rester vide — aucune valeur ne doit "fuiter" d'une identité à l'autre."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "should-never-leak-into-radar")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "should-never-leak-into-radar-chat")
    mod = _reload_radar_bot()
    assert mod.TOKEN == ""
    assert mod.CHAT_ID == ""


# ── TEST 6 : no secret values in error messages ──────────────────────────────


def test_no_secret_values_in_error_messages():
    """Le message d'erreur affiché en l'absence de RADAR_BOT_TOKEN ne doit
    jamais contenir de valeur de token/chat, même si une autre variable
    Telegram "secrète" est définie dans l'environnement."""
    secret_value = "super-secret-token-should-not-leak-12345"
    result = _run_subprocess(env_overrides={"TELEGRAM_BOT_TOKEN": secret_value})
    combined = result.stdout + result.stderr
    assert secret_value not in combined
    assert result.returncode == 1
