"""MEO-04 tests are offline: any socket is a failure. The real L3 corpus stays out of Git."""

import hashlib
import os
import shutil
import socket
from pathlib import Path

import pytest

from observability.radar_composite import kraken_trade_pilot as ktp

L3_ARCHIVE_SHA256 = "4b06e0327aea7719d80a9b3179982078288c7f3a54797080d48335b45b9aa5bd"
L3_READING_SHA256 = "eade163d5d4a9da9350e86b969e3ec078f6fe4b22491cbac2cc1f61ac0f651e5"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="session")
def synthetic_capture(tmp_path_factory):
    """One SYNTHETIC sealed capture (the MEO-01 dry run), produced once and never modified."""
    out = tmp_path_factory.mktemp("meo04cap").resolve() / "c"
    _, code = ktp.dry_run(out)
    assert code == 0
    for p in out.iterdir():
        p.chmod(0o444)
    return out


@pytest.fixture
def capture_copy(synthetic_capture, tmp_path):
    """A writable copy, for tests that alter a member."""
    dst = tmp_path.resolve() / "copy"
    shutil.copytree(synthetic_capture, dst)
    for p in dst.iterdir():
        p.chmod(0o644)
    return dst


def _real(env, sha):
    value = os.environ.get(env)
    if not value:
        pytest.skip(f"{env} not set: the real L3 corpus is kept out of Git (D6)")
    p = Path(value).resolve()
    assert hashlib.sha256(p.read_bytes()).hexdigest() == sha, f"{env} is not the reference file"
    return p


@pytest.fixture
def l3_archive():
    return _real("MEO04_L3_ARCHIVE", L3_ARCHIVE_SHA256)


@pytest.fixture
def l3_reading():
    return _real("MEO04_L3_READING", L3_READING_SHA256)
