"""Tests blacklist PerpUniverseService."""

from __future__ import annotations

import os

from core.perp_universe_service import _HARDCODED_BLACKLIST, PerpUniverseService


def _svc(extra_blacklist: str = "") -> PerpUniverseService:
    env = {"SYMBOL_BLACKLIST": extra_blacklist}
    with _patch_env(env):
        return PerpUniverseService()


class _patch_env:
    def __init__(self, overrides: dict[str, str]) -> None:
        self._overrides = overrides
        self._saved: dict[str, str | None] = {}

    def __enter__(self) -> "_patch_env":
        for k, v in self._overrides.items():
            self._saved[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *_) -> None:
        for k, saved in self._saved.items():
            if saved is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved


class TestHardcodedBlacklist:
    def test_hardcoded_tokens_present(self):
        for sym in (
            "ASTEROID/USDT",
            "RAIN/USDT",
            "STAR/USDT",
            "UPC/USDT",
            "EUR/USDT",
            "XMR/USDT",
            "MX/USDT",
            "GOLD(PAXG)/USDT",
            "BTW/USDT",
            "ARX/USDT",
        ):
            assert sym in _HARDCODED_BLACKLIST, f"{sym} manquant"

    def test_service_inherits_hardcoded(self):
        svc = _svc()
        assert "ASTEROID/USDT" in svc._blacklist
        assert "STAR/USDT" in svc._blacklist
        assert "UPC/USDT" in svc._blacklist


class TestEnvBlacklist:
    def test_extra_token_added(self):
        svc = _svc("JUNK/USDT,SCAM/USDT")
        assert "JUNK/USDT" in svc._blacklist
        assert "SCAM/USDT" in svc._blacklist

    def test_extra_token_uppercase_normalized(self):
        svc = _svc("junk/usdt")
        assert "JUNK/USDT" in svc._blacklist

    def test_empty_env_var_no_extra(self):
        svc = _svc("")
        # Only the hardcoded ones
        assert svc._blacklist == _HARDCODED_BLACKLIST


class TestFilterBlacklist:
    def setup_method(self):
        self.svc = _svc()

    def test_removes_exact_match(self):
        result = self.svc._filter_blacklist(["ASTEROID/USDT", "BTC/USDT"])
        assert result == ["BTC/USDT"]

    def test_removes_base_match(self):
        # STAR without /USDT quote variant (base still matches STAR/USDT blacklist)
        result = self.svc._filter_blacklist(["STAR/USDT", "ETH/USDT"])
        assert result == ["ETH/USDT"]

    def test_keeps_non_blacklisted(self):
        syms = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        assert self.svc._filter_blacklist(syms) == syms

    def test_empty_input(self):
        assert self.svc._filter_blacklist([]) == []

    def test_all_blacklisted(self):
        result = self.svc._filter_blacklist(["ASTEROID/USDT", "STAR/USDT", "UPC/USDT"])
        assert result == []

    def test_case_insensitive_input(self):
        result = self.svc._filter_blacklist(["asteroid/usdt", "BTC/USDT"])
        assert result == ["BTC/USDT"]
