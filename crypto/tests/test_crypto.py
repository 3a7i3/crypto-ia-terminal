"""
test_crypto.py — Tests P10-C : Souveraineté Cryptographique (C-01 → C-06)

Structure :
  §1  key_derivation   (8 tests)
  §2  BlackBoxEncryption C-01  (12 tests)
  §3  DecisionSigner C-02      (12 tests)
  §4  ApiKeyVault C-03         (14 tests)
  §5  SecureChannels C-04      (10 tests)
  §6  AuditTrail C-05          (12 tests)
  §7  TamperEvidentLog C-06    (12 tests)
  §8  Intégration système      (10 tests)

Total : 89 tests
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# §1 — key_derivation
# ─────────────────────────────────────────────────────────────────────────────


class TestKeyDerivation:
    def test_derive_key_returns_32_bytes(self):
        from crypto.key_derivation import CTX_BLACKBOX, derive_key

        k = derive_key(CTX_BLACKBOX)
        assert len(k) == 32

    def test_different_contexts_different_keys(self):
        from crypto.key_derivation import CTX_BLACKBOX, CTX_DECISION, derive_key

        k1 = derive_key(CTX_BLACKBOX)
        k2 = derive_key(CTX_DECISION)
        assert k1 != k2

    def test_same_context_same_key(self):
        from crypto.key_derivation import CTX_BLACKBOX, derive_key

        assert derive_key(CTX_BLACKBOX) == derive_key(CTX_BLACKBOX)

    def test_custom_master_secret(self):
        from crypto.key_derivation import CTX_BLACKBOX, derive_key

        k1 = derive_key(CTX_BLACKBOX, master_secret=b"secret_a")
        k2 = derive_key(CTX_BLACKBOX, master_secret=b"secret_b")
        assert k1 != k2

    def test_derive_key_custom_length(self):
        from crypto.key_derivation import CTX_BLACKBOX, derive_key

        k = derive_key(CTX_BLACKBOX, length=16)
        assert len(k) == 16

    def test_derive_key_from_password(self):
        from crypto.key_derivation import derive_key_from_password

        salt = os.urandom(32)
        k = derive_key_from_password("my_password", salt)
        assert len(k) == 32

    def test_derive_key_from_password_deterministic(self):
        from crypto.key_derivation import derive_key_from_password

        salt = b"A" * 32
        k1 = derive_key_from_password("pw", salt)
        k2 = derive_key_from_password("pw", salt)
        assert k1 == k2

    def test_zero_bytes(self):
        from crypto.key_derivation import zero_bytes

        buf = bytearray(b"\xff" * 16)
        zero_bytes(buf)
        assert all(b == 0 for b in buf)


# ─────────────────────────────────────────────────────────────────────────────
# §2 — BlackBoxEncryption (C-01)
# ─────────────────────────────────────────────────────────────────────────────


class TestBlackBoxEncryption:
    def test_encrypt_returns_bytes(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        blob = enc.encrypt({"event": "TEST"})
        assert isinstance(blob, bytes)

    def test_nonce_size(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        blob = enc.encrypt(b"hello")
        assert len(blob) > 12  # nonce(12) + at minimum 1 byte + tag(16)

    def test_encrypt_decrypt_roundtrip_dict(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        blob = enc.encrypt({"symbol": "BTC", "price": 50000})
        result = enc.decrypt_to_dict(blob)
        assert result["symbol"] == "BTC"
        assert result["price"] == 50000

    def test_encrypt_decrypt_roundtrip_bytes(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        original = b"raw bytes payload"
        blob = enc.encrypt(original)
        assert enc.decrypt(blob) == original

    def test_tampered_ciphertext_raises(self):
        from cryptography.exceptions import InvalidTag

        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        blob = enc.encrypt({"x": 1})
        tampered = blob[:-1] + bytes([blob[-1] ^ 0xFF])
        with pytest.raises(InvalidTag):
            enc.decrypt(tampered)

    def test_different_master_secret_cannot_decrypt(self):
        from cryptography.exceptions import InvalidTag

        from crypto.blackbox_encryption import BlackBoxEncryption

        enc_a = BlackBoxEncryption(master_secret=b"secret_a")
        enc_b = BlackBoxEncryption(master_secret=b"secret_b")
        blob = enc_a.encrypt({"data": "private"})
        with pytest.raises(Exception):
            enc_b.decrypt(blob)

    def test_each_encrypt_uses_different_nonce(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        b1 = enc.encrypt({"x": 1})
        b2 = enc.encrypt({"x": 1})
        assert b1[:12] != b2[:12]  # nonces différents

    def test_too_short_blob_raises(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        with pytest.raises(ValueError):
            enc.decrypt(b"short")

    def test_encrypt_line_base64(self):
        import base64

        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        line = enc.encrypt_line({"event": "TRADE"})
        assert isinstance(line, str)
        # doit être du base64 valide
        base64.b64decode(line)

    def test_decrypt_line_roundtrip(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        entry = {"event": "TRADE", "price": 42.0}
        line = enc.encrypt_line(entry)
        result = enc.decrypt_line(line)
        assert result == entry

    def test_reencrypt_with_new_key(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption(master_secret=b"old_key")
        blob = enc.encrypt({"data": "sensitive"})
        new_blob = enc.reencrypt(blob, b"new_key")
        enc_new = BlackBoxEncryption(master_secret=b"new_key")
        result = enc_new.decrypt_to_dict(new_blob)
        assert result["data"] == "sensitive"

    def test_encrypt_string(self):
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption()
        blob = enc.encrypt("hello world")
        assert enc.decrypt(blob) == b"hello world"


# ─────────────────────────────────────────────────────────────────────────────
# §3 — DecisionSigner (C-02)
# ─────────────────────────────────────────────────────────────────────────────


class TestDecisionSigner:
    @pytest.fixture
    def signer(self, tmp_path):
        from crypto.decision_signer import DecisionSigner

        return DecisionSigner(
            master_secret=b"test_master", key_path=tmp_path / "sig.key"
        )

    def test_sign_adds_fields(self, signer):
        result = signer.sign({"symbol": "BTC/USDT", "action": "BUY"})
        assert "signed_at" in result
        assert "ed25519_signature" in result

    def test_sign_verify_roundtrip(self, signer):
        packet = {"symbol": "BTC/USDT", "action": "BUY", "size": 100.0}
        signed = signer.sign(packet)
        assert signer.verify(signed)

    def test_modify_field_invalidates_signature(self, signer):
        signed = signer.sign({"symbol": "BTC/USDT", "action": "BUY"})
        tampered = dict(signed)
        tampered["action"] = "SELL"
        assert not signer.verify(tampered)

    def test_modify_signed_at_invalidates(self, signer):
        signed = signer.sign({"x": 1})
        tampered = dict(signed)
        tampered["signed_at"] = 0.0
        assert not signer.verify(tampered)

    def test_missing_signature_returns_false(self, signer):
        packet = {"symbol": "BTC/USDT"}
        assert not signer.verify(packet)

    def test_corrupted_signature_returns_false(self, signer):
        signed = signer.sign({"x": 1})
        corrupted = dict(signed)
        corrupted["ed25519_signature"] = "AAAA"
        assert not signer.verify(corrupted)

    def test_public_key_hex_is_64_chars(self, signer):
        pk = signer.public_key_hex()
        assert len(pk) == 64  # Ed25519 = 32 bytes = 64 hex chars

    def test_key_persisted_and_reloaded(self, tmp_path):
        from crypto.decision_signer import DecisionSigner

        key_path = tmp_path / "sig.key"
        s1 = DecisionSigner(master_secret=b"test", key_path=key_path)
        pk1 = s1.public_key_hex()
        s2 = DecisionSigner(master_secret=b"test", key_path=key_path)
        assert s2.public_key_hex() == pk1

    def test_sign_idempotent_fields(self, signer):
        # Re-signer un paquet déjà signé ne duplique pas les champs
        p = {"x": 1}
        s1 = signer.sign(p)
        s2 = signer.sign(s1)
        assert list(s2.keys()).count("ed25519_signature") == 1

    def test_verify_with_different_signer_fails(self, tmp_path):
        from crypto.decision_signer import DecisionSigner

        s1 = DecisionSigner(master_secret=b"key_a", key_path=tmp_path / "k1.key")
        s2 = DecisionSigner(master_secret=b"key_b", key_path=tmp_path / "k2.key")
        signed = s1.sign({"data": "test"})
        assert not s2.verify(signed)

    def test_add_extra_field_invalidates(self, signer):
        signed = signer.sign({"action": "BUY"})
        tampered = dict(signed)
        tampered["extra_field"] = "injected"
        assert not signer.verify(tampered)

    def test_sign_empty_packet(self, signer):
        signed = signer.sign({})
        assert signer.verify(signed)


# ─────────────────────────────────────────────────────────────────────────────
# §4 — ApiKeyVault (C-03)
# ─────────────────────────────────────────────────────────────────────────────


class TestApiKeyVault:
    @pytest.fixture
    def vault(self, tmp_path):
        from crypto.api_key_vault import ApiKeyVault

        return ApiKeyVault(
            master_secret=b"vault_test_key", vault_path=tmp_path / "vault.json"
        )

    def test_store_and_use(self, vault):
        vault.store("binance", b"my_api_key_12345")
        with vault.use("binance") as key:
            assert bytes(key) == b"my_api_key_12345"

    def test_key_zeroed_after_use(self, vault):
        vault.store("test", b"secret")
        with vault.use("test") as key:
            buf_ref = key
        assert all(b == 0 for b in buf_ref)

    def test_store_string_secret(self, vault):
        vault.store("kraken", "string_secret")
        with vault.use("kraken") as key:
            assert bytes(key) == b"string_secret"

    def test_list_keys(self, vault):
        vault.store("a", b"1")
        vault.store("b", b"2")
        keys = vault.list_keys()
        assert set(keys) == {"a", "b"}

    def test_exists(self, vault):
        assert not vault.exists("missing")
        vault.store("x", b"val")
        assert vault.exists("x")

    def test_delete(self, vault):
        vault.store("key1", b"value")
        assert vault.delete("key1")
        assert not vault.exists("key1")

    def test_delete_nonexistent(self, vault):
        assert not vault.delete("no_such_key")

    def test_unknown_key_raises(self, vault):
        with pytest.raises(KeyError):
            with vault.use("nonexistent"):
                pass

    def test_access_log_recorded(self, vault):
        vault.store("k", b"v")
        with vault.use("k"):
            pass
        log = vault.access_log()
        actions = [e["action"] for e in log]
        assert "store" in actions
        assert "use" in actions

    def test_tampered_vault_file_raises(self, tmp_path):
        from cryptography.exceptions import InvalidTag

        from crypto.api_key_vault import ApiKeyVault

        vp = tmp_path / "vault.json"
        v = ApiKeyVault(master_secret=b"key", vault_path=vp)
        v.store("secret", b"top_secret")
        # Corrompre le fichier
        data = json.loads(vp.read_text())
        name = list(data["entries"].keys())[0]
        hex_blob = data["entries"][name]
        corrupted = hex_blob[:-2] + "ff"
        data["entries"][name] = corrupted
        vp.write_text(json.dumps(data))
        v2 = ApiKeyVault(master_secret=b"key", vault_path=vp)
        with pytest.raises(Exception):
            with v2.use("secret"):
                pass

    def test_rekey_preserves_secrets(self, tmp_path):
        from crypto.api_key_vault import ApiKeyVault

        vp = tmp_path / "vault.json"
        v = ApiKeyVault(master_secret=b"old_key", vault_path=vp)
        v.store("api", b"my_precious_secret")
        v.rekey(new_master_secret=b"new_key")
        with v.use("api") as key:
            assert bytes(key) == b"my_precious_secret"

    def test_rekey_old_vault_unreadable_with_new_key(self, tmp_path):
        from cryptography.exceptions import InvalidTag

        from crypto.api_key_vault import ApiKeyVault

        vp = tmp_path / "vault.json"
        v_old = ApiKeyVault(master_secret=b"old_key", vault_path=vp)
        v_old.store("api", b"secret")
        # Snapshot avant rekey
        old_data = json.loads(vp.read_text())
        # Rekey
        v_old.rekey(new_master_secret=b"new_key")
        # Tenter de lire avec l'ancienne clé → doit lever une exception
        v_stale = ApiKeyVault(master_secret=b"old_key", vault_path=vp)
        with pytest.raises(Exception):
            with v_stale.use("api"):
                pass

    def test_vault_persists_across_instances(self, tmp_path):
        from crypto.api_key_vault import ApiKeyVault

        vp = tmp_path / "vault.json"
        v1 = ApiKeyVault(master_secret=b"pk", vault_path=vp)
        v1.store("persistent", b"data")
        v2 = ApiKeyVault(master_secret=b"pk", vault_path=vp)
        with v2.use("persistent") as key:
            assert bytes(key) == b"data"


# ─────────────────────────────────────────────────────────────────────────────
# §5 — SecureChannels (C-04)
# ─────────────────────────────────────────────────────────────────────────────


class TestSecureChannels:
    @pytest.fixture
    def ch(self):
        from crypto.secure_channels import SecureChannels

        return SecureChannels()

    def test_pin_and_get_pins(self, ch):
        ch.pin("binance", "abc123", "def456")
        pins = ch.get_pins("binance")
        assert "abc123" in pins
        assert "def456" in pins

    def test_no_pins_empty_list(self, ch):
        assert ch.get_pins("unknown") == []

    def test_verify_pin_correct(self, ch):
        cert_der = b"fake_cert_data"
        sha = hashlib.sha256(cert_der).hexdigest()
        ch.pin("exchange", sha)
        ch.verify_pin("exchange", cert_der)  # ne doit pas lever

    def test_verify_pin_wrong_raises(self, ch):
        from crypto.secure_channels import CertificatePinError

        ch.pin("exchange", "wrong_hash_" + "a" * 52)
        with pytest.raises(CertificatePinError):
            ch.verify_pin("exchange", b"real_cert_bytes")

    def test_verify_pin_no_pins_raises(self, ch):
        from crypto.secure_channels import CertificatePinError

        with pytest.raises(CertificatePinError):
            ch.verify_pin("no_pin_exchange", b"cert")

    def test_cert_sha256_utility(self, ch):
        data = b"certificate_data"
        expected = hashlib.sha256(data).hexdigest()
        assert ch.cert_sha256(data) == expected

    def test_build_ssl_context_tls13(self, ch):
        import ssl

        ctx = ch.build_ssl_context()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_is_cipher_approved(self, ch):
        assert ch.is_cipher_approved("TLS_AES_256_GCM_SHA384")
        assert ch.is_cipher_approved("TLS_CHACHA20_POLY1305_SHA256")
        assert not ch.is_cipher_approved("AES128-SHA")

    def test_telegram_cert_returns_sha256(self, ch):
        cert_der = b"telegram_cert"
        result = ch.verify_telegram_cert(cert_der)
        assert result == hashlib.sha256(cert_der).hexdigest()

    def test_connection_history_initially_empty(self, ch):
        assert ch.connection_history() == []


# ─────────────────────────────────────────────────────────────────────────────
# §6 — AuditTrail (C-05)
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditTrail:
    @pytest.fixture
    def trail(self, tmp_path):
        from crypto.audit_trail import AuditTrail

        return AuditTrail(trail_path=tmp_path / "audit.jsonl")

    def test_append_creates_block(self, trail):
        b = trail.append("TRADE", {"symbol": "BTC"})
        assert b.index == 0
        assert b.event == "TRADE"
        assert len(b.hash) == 64

    def test_chain_grows(self, trail):
        trail.append("E1")
        trail.append("E2")
        trail.append("E3")
        assert len(trail) == 3

    def test_verify_chain_empty(self, trail):
        assert trail.verify_chain()

    def test_verify_chain_valid(self, trail):
        for i in range(5):
            trail.append(f"EVENT_{i}", {"i": i})
        assert trail.verify_chain()

    def test_first_block_prev_hash_is_genesis(self, trail):
        from crypto.audit_trail import _GENESIS_HASH

        b = trail.append("FIRST")
        assert b.prev_hash == _GENESIS_HASH

    def test_chaining_prev_hash(self, trail):
        b0 = trail.append("E0")
        b1 = trail.append("E1")
        assert b1.prev_hash == b0.hash

    def test_tampered_block_fails_verify(self, trail):
        trail.append("E0")
        trail.append("E1")
        # Modifier directement un bloc en mémoire
        trail._blocks[0].data = {"injected": True}
        assert not trail.verify_chain()

    def test_find_tampered_block(self, trail):
        trail.append("E0")
        trail.append("E1")
        trail._blocks[1].data = {"tampered": True}
        idx = trail.find_tampered_block()
        assert idx == 1

    def test_find_tampered_none_if_valid(self, trail):
        trail.append("E0")
        assert (
            trail.find_tampered_none_if_valid() is None
            if hasattr(trail, "find_tampered_none_if_valid")
            else trail.find_tampered_block() is None
        )

    def test_persistence_and_reload(self, tmp_path):
        from crypto.audit_trail import AuditTrail

        p = tmp_path / "trail.jsonl"
        t1 = AuditTrail(trail_path=p)
        t1.append("BOOT")
        t1.append("TRADE")
        t2 = AuditTrail(trail_path=p)
        assert len(t2) == 2
        assert t2.verify_chain()

    def test_last_hash(self, trail):
        from crypto.audit_trail import _GENESIS_HASH

        assert trail.last_hash() == _GENESIS_HASH
        b = trail.append("E")
        assert trail.last_hash() == b.hash

    def test_blocks_returns_copy(self, trail):
        trail.append("E")
        b = trail.blocks()
        b.clear()
        assert len(trail) == 1  # original non modifié


# ─────────────────────────────────────────────────────────────────────────────
# §7 — TamperEvidentLog (C-06)
# ─────────────────────────────────────────────────────────────────────────────


class TestTamperEvidentLog:
    @pytest.fixture
    def tlog(self, tmp_path):
        from crypto.tamper_evident_logs import TamperEvidentLog

        return TamperEvidentLog(
            master_secret=b"test_key", log_path=tmp_path / "tamper.jsonl"
        )

    def test_write_creates_entry(self, tlog):
        e = tlog.write("INFO", "boot complete")
        assert e.seq == 0
        assert e.level == "INFO"
        assert len(e.hmac) == 64

    def test_chain_grows(self, tlog):
        tlog.write("INFO", "a")
        tlog.write("TRADE", "b")
        tlog.write("RISK", "c")
        assert len(tlog) == 3

    def test_verify_all_empty(self, tlog):
        assert tlog.verify_all()

    def test_verify_all_valid(self, tlog):
        for i in range(10):
            tlog.write("INFO", f"msg {i}")
        assert tlog.verify_all()

    def test_first_entry_prev_hmac_is_genesis(self, tlog):
        from crypto.tamper_evident_logs import _GENESIS_HMAC

        e = tlog.write("INFO", "first")
        assert e.prev_hmac == _GENESIS_HMAC

    def test_chaining(self, tlog):
        e0 = tlog.write("INFO", "a")
        e1 = tlog.write("INFO", "b")
        assert e1.prev_hmac == e0.hmac

    def test_tampered_entry_fails_verify(self, tlog):
        tlog.write("INFO", "original")
        tlog._entries[0].message = "tampered"
        assert not tlog.verify_all()

    def test_find_tampered_entry(self, tlog):
        tlog.write("INFO", "a")
        tlog.write("INFO", "b")
        tlog._entries[0].message = "tampered"
        idx = tlog.find_tampered_entry()
        assert idx == 0

    def test_find_tampered_none_if_valid(self, tlog):
        tlog.write("INFO", "clean")
        assert tlog.find_tampered_entry() is None

    def test_persistence_and_reload(self, tmp_path):
        from crypto.tamper_evident_logs import TamperEvidentLog

        p = tmp_path / "log.jsonl"
        l1 = TamperEvidentLog(master_secret=b"k", log_path=p)
        l1.write("INFO", "entry1")
        l1.write("TRADE", "entry2")
        l2 = TamperEvidentLog(master_secret=b"k", log_path=p)
        assert len(l2) == 2
        assert l2.verify_all()

    def test_10k_entries_under_1s(self, tmp_path):
        from crypto.tamper_evident_logs import BufferedTamperEvidentLog

        # Utilise BufferedTamperEvidentLog pour isoler les I/O disque du test
        # de performance de verify_all() (objectif : HMAC batch < 1s)
        p = tmp_path / "perf.jsonl"
        tl = BufferedTamperEvidentLog(
            master_secret=b"perf_key", log_path=p, flush_every_n_entries=10_001
        )
        for i in range(10_000):
            tl.write("INFO", f"msg {i}", {"i": i})
        t0 = time.perf_counter()
        result = tl.verify_all()
        elapsed = time.perf_counter() - t0
        assert result
        assert elapsed < 1.0, f"verify_all() trop lent: {elapsed:.2f}s pour 10k entrées"

    def test_last_hmac(self, tlog):
        from crypto.tamper_evident_logs import _GENESIS_HMAC

        assert tlog.last_hmac() == _GENESIS_HMAC
        e = tlog.write("INFO", "x")
        assert tlog.last_hmac() == e.hmac


# ─────────────────────────────────────────────────────────────────────────────
# §7b — BufferedTamperEvidentLog
# ─────────────────────────────────────────────────────────────────────────────


class TestBufferedTamperEvidentLog:
    @pytest.fixture
    def blog(self, tmp_path):
        from crypto.tamper_evident_logs import BufferedTamperEvidentLog

        return BufferedTamperEvidentLog(
            master_secret=b"buf_key",
            log_path=tmp_path / "buffered.jsonl",
            flush_every_n_entries=100,
        )

    def test_write_and_verify_all_correct(self, blog):
        for i in range(50):
            blog.write("INFO", f"msg {i}")
        blog.flush()
        assert blog.verify_all()

    def test_chain_integrity_preserved(self, blog):
        e0 = blog.write("INFO", "a")
        e1 = blog.write("TRADE", "b")
        assert e1.prev_hmac == e0.hmac

    def test_auto_flush_at_threshold(self, blog, tmp_path):
        p = tmp_path / "buffered.jsonl"
        for i in range(100):
            blog.write("INFO", f"{i}")
        # 100 entrées = seuil atteint → flush automatique
        assert p.stat().st_size > 0, "Flush automatique n'a pas écrit sur disque"

    def test_shutdown_flushes_remaining(self, tmp_path):
        from crypto.tamper_evident_logs import BufferedTamperEvidentLog

        p = tmp_path / "shutdown.jsonl"
        log = BufferedTamperEvidentLog(
            master_secret=b"k", log_path=p, flush_every_n_entries=1000
        )
        for i in range(10):
            log.write("INFO", f"pre-shutdown {i}")
        assert not p.exists() or p.stat().st_size == 0, "Pas encore flushé"
        log.shutdown()
        assert (
            p.exists() and p.stat().st_size > 0
        ), "shutdown() doit flusher les entrées restantes"

    def test_persistence_after_shutdown(self, tmp_path):
        from crypto.tamper_evident_logs import (
            BufferedTamperEvidentLog,
            TamperEvidentLog,
        )

        p = tmp_path / "persist.jsonl"
        log = BufferedTamperEvidentLog(
            master_secret=b"k", log_path=p, flush_every_n_entries=1000
        )
        for i in range(5):
            log.write("INFO", f"entry {i}")
        log.shutdown()

        reloaded = TamperEvidentLog(master_secret=b"k", log_path=p)
        assert len(reloaded) == 5
        assert reloaded.verify_all()

    def test_10k_writes_under_2s(self, tmp_path):
        """10k writes bufferisés doivent être ~50× plus rapides que non bufferisés."""
        from crypto.tamper_evident_logs import BufferedTamperEvidentLog

        p = tmp_path / "speed.jsonl"
        log = BufferedTamperEvidentLog(
            master_secret=b"k", log_path=p, flush_every_n_entries=100
        )
        t0 = time.perf_counter()
        for i in range(10_000):
            log.write("INFO", f"msg {i}", {"i": i})
        log.shutdown()
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"10k writes bufferisés trop lents: {elapsed:.2f}s"

    def test_flush_explicit(self, blog, tmp_path):
        p = tmp_path / "buffered.jsonl"
        blog.write("INFO", "entry1")
        assert (
            not p.exists() or p.stat().st_size == 0
        ), "Pas encore flushé avant appel explicite"
        blog.flush()
        assert p.exists() and p.stat().st_size > 0, "flush() doit écrire sur disque"

    def test_verify_all_after_reload(self, tmp_path):
        from crypto.tamper_evident_logs import (
            BufferedTamperEvidentLog,
            TamperEvidentLog,
        )

        p = tmp_path / "reload.jsonl"
        log = BufferedTamperEvidentLog(
            master_secret=b"k2", log_path=p, flush_every_n_entries=10
        )
        for i in range(25):
            log.write("TRADE", f"trade {i}")
        log.shutdown()

        reloaded = TamperEvidentLog(master_secret=b"k2", log_path=p)
        assert len(reloaded) == 25
        assert reloaded.verify_all()


# ─────────────────────────────────────────────────────────────────────────────
# §8 — Intégration système (C-01 BlackBox + C-02 DecisionPacket)
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Tests d'intégration crypto dans le système réel."""

    # ── C-01 BlackBox ─────────────────────────────────────────────────────────

    def test_blackbox_writes_encrypted(self, tmp_path):
        """Les entrées BlackBox ne sont pas en clair sur disque."""
        import json as _json

        from quant_hedge_ai.agents.intelligence.black_box import BlackBox

        bb = BlackBox(path=str(tmp_path / "bb.jsonl"))
        bb.record_system_event("BOOT", "test")
        raw = (tmp_path / "bb.jsonl").read_text()
        for line in raw.strip().splitlines():
            assert not line.startswith("{"), "Entrée en clair détectée dans BlackBox"

    def test_blackbox_round_trip(self, tmp_path):
        """Écriture chiffrée + rechargement depuis disque → données intactes."""
        from quant_hedge_ai.agents.intelligence.black_box import BlackBox

        bb = BlackBox(path=str(tmp_path / "bb.jsonl"))
        bb.record_system_event("BOOT", "integration test")
        bb.record_halt("test halt", level="WARNING")
        bb2 = BlackBox(path=str(tmp_path / "bb.jsonl"))
        bb2._ensure_loaded()
        entries = bb2.query(limit=10)
        assert len(entries) == 2

    def test_blackbox_migration_plaintext_fallback(self, tmp_path):
        """Fichier pre-C-01 en clair → chargé sans erreur (migration)."""
        import json as _json
        from dataclasses import asdict

        from quant_hedge_ai.agents.intelligence.black_box import BlackBox, BlackBoxEntry

        # Créer un fichier pré-C-01 en clair
        entry = BlackBoxEntry(
            ts=1000.0,
            decision_type="SYSTEM_EVENT",
            symbol="SYSTEM",
            signal="EVENT",
            score=0,
            regime="unknown",
            personality="system",
            price=0.0,
            reason="legacy entry",
        )
        p = tmp_path / "bb_legacy.jsonl"
        p.write_text(_json.dumps(asdict(entry)) + "\n", encoding="utf-8")
        bb = BlackBox(path=str(p))
        bb._ensure_loaded()
        assert len(bb._entries) == 1
        assert bb._entries[0].reason == "legacy entry"

    def test_blackbox_new_writes_encrypted_after_migration(self, tmp_path):
        """Après chargement d'un fichier legacy, les nouveaux écrits sont chiffrés."""
        import json as _json
        from dataclasses import asdict

        from quant_hedge_ai.agents.intelligence.black_box import BlackBox, BlackBoxEntry

        entry = BlackBoxEntry(
            ts=1000.0,
            decision_type="SYSTEM_EVENT",
            symbol="SYSTEM",
            signal="EVENT",
            score=0,
            regime="unknown",
            personality="system",
            price=0.0,
            reason="legacy",
        )
        p = tmp_path / "bb.jsonl"
        p.write_text(_json.dumps(asdict(entry)) + "\n", encoding="utf-8")
        bb = BlackBox(path=str(p))
        bb.record_system_event("NEW_BOOT")
        lines = p.read_text().strip().splitlines()
        # Ligne 0 = legacy en clair, ligne 1 = chiffrée
        assert not lines[1].startswith("{")

    # ── C-02 DecisionPacket ───────────────────────────────────────────────────

    def test_decision_packet_seal_and_verify(self, tmp_path):
        """seal() signe le packet, verify_signature() confirme."""
        from core.decision_packet import DecisionPacket, DecisionSide, DecisionState
        from crypto.decision_signer import DecisionSigner

        signer = DecisionSigner(master_secret=b"test", key_path=tmp_path / "k.key")
        p = DecisionPacket(symbol="BTC/USDT", side=DecisionSide.LONG)
        assert not p.is_sealed()
        p.transition_to(DecisionState.SIGNAL_GENERATED, "sig", "ok")
        p.transition_to(DecisionState.CONTEXT_ENRICHED, "ctx", "ok")
        p.transition_to(DecisionState.RISK_EVALUATED, "risk", "ok")
        p.transition_to(DecisionState.APPROVED, "pb", "ok")
        p.transition_to(DecisionState.EXECUTION_PENDING, "exec", "ok")
        p.transition_to(DecisionState.EXECUTED, "exec", "done")
        p.seal(signer)
        assert p.is_sealed()
        assert p.verify_signature(signer)

    def test_decision_packet_tamper_detected(self, tmp_path):
        """Modifier confidence après seal → verify_signature retourne False."""
        from core.decision_packet import DecisionPacket, DecisionSide, DecisionState
        from crypto.decision_signer import DecisionSigner

        signer = DecisionSigner(master_secret=b"test", key_path=tmp_path / "k.key")
        p = DecisionPacket(symbol="ETH/USDT", side=DecisionSide.LONG, confidence=50.0)
        p.transition_to(DecisionState.SIGNAL_GENERATED, "s", "")
        p.transition_to(DecisionState.CONTEXT_ENRICHED, "c", "")
        p.transition_to(DecisionState.RISK_EVALUATED, "r", "")
        p.transition_to(DecisionState.APPROVED, "a", "")
        p.transition_to(DecisionState.EXECUTION_PENDING, "e", "")
        p.transition_to(DecisionState.EXECUTED, "e", "")
        p.seal(signer)
        p.confidence = 99.0
        assert not p.verify_signature(signer)

    def test_decision_packet_not_sealed_by_default(self):
        """Nouveau packet non scellé par défaut."""
        from core.decision_packet import DecisionPacket

        p = DecisionPacket(symbol="SOL/USDT")
        assert not p.is_sealed()
        assert p.ed25519_signature == ""

    def test_decision_packet_to_dict_includes_signature(self, tmp_path):
        """to_dict() inclut ed25519_signature et signed_at."""
        from core.decision_packet import DecisionPacket, DecisionSide, DecisionState
        from crypto.decision_signer import DecisionSigner

        signer = DecisionSigner(master_secret=b"test", key_path=tmp_path / "k.key")
        p = DecisionPacket(symbol="BTC/USDT", side=DecisionSide.LONG)
        p.transition_to(DecisionState.SIGNAL_GENERATED, "s", "")
        p.transition_to(DecisionState.CONTEXT_ENRICHED, "c", "")
        p.transition_to(DecisionState.RISK_EVALUATED, "r", "")
        p.transition_to(DecisionState.APPROVED, "a", "")
        p.transition_to(DecisionState.EXECUTION_PENDING, "e", "")
        p.transition_to(DecisionState.EXECUTED, "e", "")
        p.seal(signer)
        d = p.to_dict()
        assert "ed25519_signature" in d
        assert "signed_at" in d
        assert d["ed25519_signature"] != ""

    def test_decision_packet_from_dict_roundtrip(self, tmp_path):
        """from_dict() reconstruit un packet avec signature vérifiable."""
        from core.decision_packet import DecisionPacket, DecisionSide, DecisionState
        from crypto.decision_signer import DecisionSigner

        signer = DecisionSigner(master_secret=b"test", key_path=tmp_path / "k.key")
        p = DecisionPacket(symbol="BTC/USDT", side=DecisionSide.LONG)
        p.transition_to(DecisionState.SIGNAL_GENERATED, "s", "")
        p.transition_to(DecisionState.CONTEXT_ENRICHED, "c", "")
        p.transition_to(DecisionState.RISK_EVALUATED, "r", "")
        p.transition_to(DecisionState.APPROVED, "a", "")
        p.transition_to(DecisionState.EXECUTION_PENDING, "e", "")
        p.transition_to(DecisionState.EXECUTED, "e", "")
        p.seal(signer)
        p2 = DecisionPacket.from_dict(p.to_dict())
        assert p2.is_sealed()
        assert p2.verify_signature(signer)

    def test_decision_packet_rejected_can_be_sealed(self, tmp_path):
        """Un packet REJECTED peut aussi être scellé."""
        from core.decision_packet import DecisionPacket, DecisionSide
        from crypto.decision_signer import DecisionSigner

        signer = DecisionSigner(master_secret=b"test", key_path=tmp_path / "k.key")
        p = DecisionPacket(symbol="LTC/USDT", side=DecisionSide.LONG)
        p.reject("risk_gate", "volatilité trop élevée")
        p.seal(signer)
        assert p.is_sealed()
        assert p.verify_signature(signer)
