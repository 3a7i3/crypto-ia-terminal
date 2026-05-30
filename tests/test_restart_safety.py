"""
P11-B — Restart Safety.

Valide que le système survit à un crash brutal et redémarre sans dérive d'état.

4 sous-phases :
  B1 — Snapshot Recovery     : état persisté rechargé sans perte
  B2 — Mid-Execution Crash   : réconciliation après crash pré-confirmation
  B3 — Audit Recovery        : intégrité HMAC-SHA256 après crash
  B4 — Full Advisor Restart  : 0 dérive equity/capital/positions sur crash/restart
"""

from __future__ import annotations

import json
import pickle
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ══════════════════════════════════════════════════════════════════════════════
# B1 — Snapshot Recovery
# ══════════════════════════════════════════════════════════════════════════════


class TestB1SnapshotRecovery:
    """Boot → persist → crash → restart → état identique."""

    # ── WarmupStateMachine ────────────────────────────────────────────────────

    def test_warmup_state_persisted_on_init(self, tmp_path, monkeypatch):
        """WarmupSM écrit warmup_state.json dès l'init (état BOOTING signé)."""
        state_file = tmp_path / "warmup.json"
        monkeypatch.setenv("P10_STATE_PERSIST_PATH", str(state_file))

        import cold_start.warmup_state_machine as wsm_mod

        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()

        assert state_file.exists(), "warmup_state.json doit exister après init"
        record = json.loads(state_file.read_text())
        assert record["state"] == "BOOTING"
        assert "signature" in record

    def test_warmup_state_survives_restart(self, tmp_path, monkeypatch):
        """Crash après transition → restart lit le bon état."""
        state_file = tmp_path / "warmup.json"
        import cold_start.warmup_state_machine as wsm_mod

        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()
        # Simuler progression vers FETCHING_MARKET_DATA
        sm._advance(confidence=0.90)
        assert sm.state == wsm_mod.WarmupState.FETCHING_MARKET_DATA

        # «Crash» — recréer une nouvelle instance (simule restart)
        sm2 = wsm_mod.WarmupStateMachine.__new__(wsm_mod.WarmupStateMachine)
        sm2._state = wsm_mod.WarmupState.BOOTING
        sm2._history = []
        sm2._consecutive_failures = 0

        persisted = sm2.load_persisted_state()
        assert (
            persisted == "FETCHING_MARKET_DATA"
        ), f"Restart doit lire FETCHING_MARKET_DATA, obtenu: {persisted}"

    def test_corrupted_warmup_state_rejected(self, tmp_path, monkeypatch):
        """État persisté corrompu → load_persisted_state() retourne None."""
        state_file = tmp_path / "warmup.json"
        import cold_start.warmup_state_machine as wsm_mod

        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()

        # Corrompre la signature
        record = json.loads(state_file.read_text())
        record["signature"] = "0" * 64  # signature invalide
        state_file.write_text(json.dumps(record))

        persisted = sm.load_persisted_state()
        assert persisted is None, "État corrompu doit être rejeté"

    def test_missing_warmup_file_returns_none(self, tmp_path, monkeypatch):
        """Pas de warmup_state.json → load_persisted_state() retourne None."""
        state_file = tmp_path / "nonexistent.json"
        import cold_start.warmup_state_machine as wsm_mod

        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine.__new__(wsm_mod.WarmupStateMachine)
        sm._state = wsm_mod.WarmupState.BOOTING
        sm._history = []
        sm._consecutive_failures = 0

        assert sm.load_persisted_state() is None

    def test_warmup_state_replay_full_sequence(self, tmp_path, monkeypatch):
        """Chaque avancement est persisté — sequence cohérente."""
        state_file = tmp_path / "warmup.json"
        import cold_start.warmup_state_machine as wsm_mod

        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()
        expected_sequence = [
            wsm_mod.WarmupState.BOOTING,
            wsm_mod.WarmupState.FETCHING_MARKET_DATA,
            wsm_mod.WarmupState.BUILDING_FEATURES,
        ]

        for _ in range(2):
            sm._advance(confidence=1.0)

        persisted = sm.load_persisted_state()
        assert persisted == wsm_mod.WarmupState.BUILDING_FEATURES.name

        # Snapshot reflète aussi l'historique
        snap = sm.snapshot()
        assert snap["state"] == wsm_mod.WarmupState.BUILDING_FEATURES.name
        assert len(snap["history"]) >= 3  # BOOTING + FETCHING + BUILDING

    # ── StartupCache ──────────────────────────────────────────────────────────

    def test_startup_cache_runtime_state_round_trip(self, tmp_path, monkeypatch):
        """save_runtime_state → load_runtime_state → données identiques."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            sc_mod.StartupCache, "STATE_CACHE", tmp_path / "runtime_state.pkl"
        )
        monkeypatch.setattr(
            sc_mod.StartupCache,
            "TIMESTAMP_FILE",
            tmp_path / "last_snapshot.txt",
        )

        cache = sc_mod.StartupCache()
        state = {
            "capital": 10_000.0,
            "open_positions": ["BTC/USDT", "ETH/USDT"],
            "cycle": 42,
            "equity": 10_250.0,
        }

        saved = cache.save_runtime_state(state)
        assert saved is True

        loaded = cache.load_runtime_state(max_age_seconds=300)
        assert loaded is not None, "État doit être rechargé"
        assert loaded["capital"] == 10_000.0
        assert loaded["equity"] == 10_250.0
        assert loaded["cycle"] == 42

    def test_startup_cache_stale_state_rejected(self, tmp_path, monkeypatch):
        """État vieux de plus de max_age_seconds → None (pas de zombie state)."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            sc_mod.StartupCache, "STATE_CACHE", tmp_path / "runtime_state.pkl"
        )

        cache = sc_mod.StartupCache()

        # Sauvegarder avec timestamp passé (3600s)
        stale_snapshot = {
            "timestamp": time.time() - 3601,
            "state": {"capital": 9000.0, "cycle": 1},
        }
        (tmp_path / "runtime_state.pkl").write_bytes(pickle.dumps(stale_snapshot))

        loaded = cache.load_runtime_state(max_age_seconds=300)
        assert loaded is None, "État périmé doit être rejeté"

    def test_startup_cache_corrupted_pickle_returns_none(self, tmp_path, monkeypatch):
        """Pickle corrompu → None (pas de crash)."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            sc_mod.StartupCache, "STATE_CACHE", tmp_path / "runtime_state.pkl"
        )

        (tmp_path / "runtime_state.pkl").write_bytes(b"CORRUPTED_PICKLE_DATA")

        cache = sc_mod.StartupCache()
        loaded = cache.load_runtime_state()
        assert loaded is None, "Pickle corrompu doit retourner None"

    def test_startup_cache_config_round_trip(self, tmp_path, monkeypatch):
        """save_config → load_config → config identique."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            sc_mod.StartupCache, "CONFIG_CACHE", tmp_path / "configs.json"
        )

        cache = sc_mod.StartupCache()
        config = {"exchange": "binance", "symbol": "BTC/USDT", "leverage": 3}
        cache.save_config(config, name="test")

        loaded = cache.load_config(max_age_seconds=3600)
        assert loaded == config

    def test_startup_cache_absent_file_returns_none(self, tmp_path, monkeypatch):
        """Pas de fichier state → None (premier démarrage)."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            sc_mod.StartupCache, "STATE_CACHE", tmp_path / "no_state.pkl"
        )

        cache = sc_mod.StartupCache()
        assert cache.load_runtime_state() is None


# ══════════════════════════════════════════════════════════════════════════════
# B2 — Mid-Execution Crash
# ══════════════════════════════════════════════════════════════════════════════


class TestB2MidExecutionCrash:
    """Crash avant confirmation d'ordre → réconciliation sans double position."""

    def _make_reconciler(self, exchange_positions, internal_positions):
        """Factory : retourne un PositionReconciler avec mocks."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.return_value = exchange_positions

        pm = MagicMock()
        pm.get_open_positions.return_value = internal_positions

        rec = PositionReconciler(exchange, pm)
        return rec

    def _make_exchange_pos(
        self, symbol: str, side: str = "long", price: float = 50000.0
    ):
        return {"symbol": symbol, "side": side, "contracts": 0.1, "markPrice": price}

    def _make_internal_pos(self, symbol: str, price: float = 50000.0):
        pos = MagicMock()
        pos.symbol = symbol
        pos.entry_price = price  # reconciler utilise entry_price pour le drift
        return pos

    # ── Ghost positions ────────────────────────────────────────────────────────

    def test_ghost_position_detected_after_crash(self):
        """Crash avant fermeture → position interne orpheline détectée."""
        internal = [self._make_internal_pos("BTC/USDT")]
        rec = self._make_reconciler(exchange_positions=[], internal_positions=internal)

        report = rec.reconcile(force=True)

        assert "BTC/USDT" in report.ghost_positions
        assert report.has_drift
        assert not report.is_clean

    def test_ghost_detection_multiple_symbols(self):
        """Plusieurs ghost positions détectées simultanément."""
        internal = [
            self._make_internal_pos("BTC/USDT"),
            self._make_internal_pos("ETH/USDT"),
        ]
        rec = self._make_reconciler(exchange_positions=[], internal_positions=internal)

        report = rec.reconcile(force=True)

        assert len(report.ghost_positions) == 2
        assert "BTC/USDT" in report.ghost_positions
        assert "ETH/USDT" in report.ghost_positions

    # ── Orphan positions ───────────────────────────────────────────────────────

    def test_orphan_position_detected_after_crash(self):
        """Ordre exécuté sur exchange mais crash avant mise à jour interne."""
        exchange = [self._make_exchange_pos("ETH/USDT")]
        rec = self._make_reconciler(exchange_positions=exchange, internal_positions=[])

        report = rec.reconcile(force=True)

        assert "ETH/USDT" in report.orphan_positions
        assert report.has_drift

    def test_orphan_is_potential_double_position(self):
        """Un orphan + une position interne identique = risque de double position."""
        exchange = [self._make_exchange_pos("BTC/USDT")]
        internal = [self._make_internal_pos("BTC/USDT")]

        # Les deux concordent → pas d'orphan
        rec = self._make_reconciler(
            exchange_positions=exchange, internal_positions=internal
        )
        report = rec.reconcile(force=True)

        assert "BTC/USDT" not in report.orphan_positions
        assert "BTC/USDT" not in report.ghost_positions

    # ── État propre ────────────────────────────────────────────────────────────

    def test_clean_state_after_clean_restart(self):
        """Exchange == interne → réconciliation CLEAN."""
        exchange = [self._make_exchange_pos("BTC/USDT", price=50000.0)]
        internal = [self._make_internal_pos("BTC/USDT", price=50000.0)]

        rec = self._make_reconciler(
            exchange_positions=exchange, internal_positions=internal
        )
        report = rec.reconcile(force=True)

        assert report.is_clean
        assert not report.has_drift

    def test_no_positions_both_sides_is_clean(self):
        """Aucune position des deux côtés → CLEAN (premier démarrage normal)."""
        rec = self._make_reconciler(exchange_positions=[], internal_positions=[])
        report = rec.reconcile(force=True)

        assert report.is_clean
        assert report.exchange_positions == 0
        assert report.internal_positions == 0

    # ── Exchange unreachable ───────────────────────────────────────────────────

    def test_exchange_unreachable_flags_report(self):
        """Exchange inaccessible au restart → pas de crash, rapport explicite."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.side_effect = ConnectionError("Exchange offline")

        pm = MagicMock()
        pm.get_open_positions.return_value = []

        rec = PositionReconciler(exchange, pm)
        report = rec.reconcile(force=True)

        assert not report.exchange_reachable
        assert report.error is not None
        assert report.has_drift

    def test_reconcile_never_raises(self):
        """reconcile() ne lève jamais d'exception, même avec exchange crashé."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.side_effect = RuntimeError("Unexpected crash")

        pm = MagicMock()
        rec = PositionReconciler(exchange, pm)

        try:
            report = rec.reconcile(force=True)
        except Exception as exc:
            pytest.fail(f"reconcile() a levé une exception: {exc}")

    # ── Price drift ────────────────────────────────────────────────────────────

    def test_price_drift_detected(self):
        """Prix exchange vs interne écart > 2% → drift détecté."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            self._make_exchange_pos("BTC/USDT", price=50000.0)
        ]

        internal_pos = MagicMock()
        internal_pos.symbol = "BTC/USDT"
        internal_pos.entry_price = 48000.0  # écart 4% > seuil 2%

        pm = MagicMock()
        pm.get_open_positions.return_value = [internal_pos]

        rec = PositionReconciler(exchange, pm)
        report = rec.reconcile(force=True)

        assert len(report.price_drifts) > 0

    def test_price_drift_within_threshold_is_clean(self):
        """Prix exchange vs interne écart < 2% → pas de drift."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            self._make_exchange_pos("BTC/USDT", price=50000.0)
        ]

        internal_pos = MagicMock()
        internal_pos.symbol = "BTC/USDT"
        internal_pos.entry_price = 50500.0  # écart 1% < seuil 2%

        pm = MagicMock()
        pm.get_open_positions.return_value = [internal_pos]

        rec = PositionReconciler(exchange, pm)
        report = rec.reconcile(force=True)

        assert len(report.price_drifts) == 0

    # ── Rate limiting ──────────────────────────────────────────────────────────

    def test_reconcile_skipped_if_too_soon(self):
        """Réconciliation ignorée si appelée trop tôt (protection rate-limit)."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.return_value = []
        pm = MagicMock()
        pm.get_open_positions.return_value = []

        rec = PositionReconciler(exchange, pm)
        rec.reconcile(force=True)  # première réconciliation

        # Deuxième sans force → skipped
        report2 = rec.reconcile(force=False)
        assert report2.error == "skipped — too soon"

    def test_reconcile_forced_ignores_rate_limit(self):
        """force=True bypasse le cooldown."""
        from system.position_reconciler import PositionReconciler

        exchange = MagicMock()
        exchange.fetch_positions.return_value = []
        pm = MagicMock()
        pm.get_open_positions.return_value = []

        rec = PositionReconciler(exchange, pm)
        rec.reconcile(force=True)
        report2 = rec.reconcile(force=True)

        assert report2.error != "skipped — too soon"


# ══════════════════════════════════════════════════════════════════════════════
# B3 — Audit Recovery
# ══════════════════════════════════════════════════════════════════════════════


class TestB3AuditRecovery:
    """Intégrité HMAC-SHA256 après crash — 0 corruption, 0 rupture de chaîne."""

    def _make_log(self, tmp_path: Path):
        from crypto.tamper_evident_logs import TamperEvidentLog

        return TamperEvidentLog(log_path=tmp_path / "audit.jsonl")

    # ── Reload basic ──────────────────────────────────────────────────────────

    def test_audit_log_survives_reload(self, tmp_path):
        """Écriture N entrées → crash → reload → verify_all() True."""
        log = self._make_log(tmp_path)
        for i in range(100):
            log.write("INFO", f"event_{i}", {"seq": i})

        # Simuler crash → nouveau TamperEvidentLog sur le même fichier
        log2 = self._make_log(tmp_path)
        assert log2.verify_all(), "Intégrité doit être maintenue après reload"
        assert len(log2._entries) == 100

    def test_audit_log_large_reload(self, tmp_path):
        """1000 entrées → reload → verify_all() < 2s."""
        log = self._make_log(tmp_path)
        for i in range(1000):
            log.write("TRADE", f"msg_{i}", {"val": i * 1.5})

        log2 = self._make_log(tmp_path)
        t0 = time.monotonic()
        ok = log2.verify_all()
        elapsed = time.monotonic() - t0

        assert ok, "1000 entrées doivent passer verify_all()"
        assert elapsed < 2.0, f"verify_all() trop lent: {elapsed:.2f}s"

    def test_empty_log_verify_all_true(self, tmp_path):
        """Journal vide → verify_all() True (invariant genesis)."""
        log = self._make_log(tmp_path)
        assert log.verify_all()

    # ── Détection de corruption ────────────────────────────────────────────────

    def test_modified_entry_detected(self, tmp_path):
        """Modification d'un champ → HMAC invalide → verify_all() False."""
        log = self._make_log(tmp_path)
        for i in range(10):
            log.write("INFO", f"msg_{i}")

        # Lire JSONL, modifier message de l'entrée #5
        lines = (tmp_path / "audit.jsonl").read_text().splitlines()
        entry5 = json.loads(lines[5])
        entry5["message"] = "TAMPERED"
        lines[5] = json.dumps(entry5)
        (tmp_path / "audit.jsonl").write_text("\n".join(lines))

        log2 = self._make_log(tmp_path)
        assert not log2.verify_all(), "Entrée modifiée doit être détectée"

    def test_deleted_entry_breaks_chain(self, tmp_path):
        """Suppression d'une entrée → chaînage cassé → verify_all() False."""
        log = self._make_log(tmp_path)
        for i in range(10):
            log.write("INFO", f"msg_{i}")

        # Supprimer l'entrée #5
        lines = (tmp_path / "audit.jsonl").read_text().splitlines()
        del lines[5]
        (tmp_path / "audit.jsonl").write_text("\n".join(lines))

        log2 = self._make_log(tmp_path)
        assert not log2.verify_all(), "Suppression doit casser la chaîne"

    def test_inserted_entry_breaks_chain(self, tmp_path):
        """Insertion d'une entrée forgée → chaîne incohérente → verify_all() False."""
        log = self._make_log(tmp_path)
        for i in range(5):
            log.write("INFO", f"msg_{i}")

        # Insérer une fausse entrée entre les lignes 2 et 3
        lines = (tmp_path / "audit.jsonl").read_text().splitlines()
        fake_entry = {
            "seq": 99,
            "ts": time.time(),
            "level": "CRITICAL",
            "message": "FORGED",
            "data": {},
            "prev_hmac": "0" * 64,
            "hmac": "a" * 64,
        }
        lines.insert(3, json.dumps(fake_entry))
        (tmp_path / "audit.jsonl").write_text("\n".join(lines))

        log2 = self._make_log(tmp_path)
        assert not log2.verify_all(), "Insertion forgée doit être détectée"

    def test_truncated_file_partial_valid(self, tmp_path):
        """Fichier tronqué au milieu → entries récupérées jusqu'au point de coupure."""
        log = self._make_log(tmp_path)
        for i in range(20):
            log.write("INFO", f"msg_{i}")

        # Tronquer le fichier à la moitié
        content = (tmp_path / "audit.jsonl").read_bytes()
        (tmp_path / "audit.jsonl").write_bytes(content[: len(content) // 2])

        # Doit charger sans crash — les entrées valides passent verify_all
        try:
            log2 = self._make_log(tmp_path)
            # Soit le chargement partiel est propre, soit la vérification échoue
            # Dans les deux cas, pas d'exception levée
        except Exception as exc:
            pytest.fail(f"Chargement de journal tronqué a levé une exception: {exc}")

    def test_hmac_key_mismatch_detected(self, tmp_path):
        """Journal signé avec clé A → relecture avec clé B → verify_all() False."""
        log_a = self._make_log(tmp_path)
        for i in range(5):
            log_a.write("INFO", f"msg_{i}")

        # Ouvrir avec une clé différente
        from crypto.tamper_evident_logs import TamperEvidentLog

        log_b = TamperEvidentLog(
            master_secret=b"different_key_that_will_fail",
            log_path=tmp_path / "audit.jsonl",
        )
        assert not log_b.verify_all(), "Mauvaise clé HMAC doit être détectée"

    def test_genesis_hmac_tampering_detected(self, tmp_path):
        """Modification du prev_hmac de la première entrée → détection."""
        log = self._make_log(tmp_path)
        for i in range(5):
            log.write("INFO", f"msg_{i}")

        lines = (tmp_path / "audit.jsonl").read_text().splitlines()
        first = json.loads(lines[0])
        first["prev_hmac"] = "f" * 64  # genesis doit être "0"*64
        lines[0] = json.dumps(first)
        (tmp_path / "audit.jsonl").write_text("\n".join(lines))

        log2 = self._make_log(tmp_path)
        assert not log2.verify_all()


# ══════════════════════════════════════════════════════════════════════════════
# B4 — Full Advisor Restart
# ══════════════════════════════════════════════════════════════════════════════


class TestB4FullAdvisorRestart:
    """
    Simulation complète : run N cycles → crash → restart → 0 dérive.

    Teste que capital, positions, equity et order history sont identiques
    après un redémarrage brutal, dans les limites de tolérance explicite.
    """

    # ── State round-trip ──────────────────────────────────────────────────────

    def test_full_state_round_trip_zero_drift(self, tmp_path, monkeypatch):
        """Snapshot complet → reload → aucun champ modifié."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(sc_mod.StartupCache, "STATE_CACHE", tmp_path / "state.pkl")

        cache = sc_mod.StartupCache()
        state = {
            "capital": 10_000.0,
            "equity": 10_342.50,
            "open_positions": ["BTC/USDT"],
            "total_trades": 127,
            "win_rate": 0.58,
            "session_pnl": 342.50,
            "risk_state": "NORMAL",
        }

        cache.save_runtime_state(state)
        loaded = cache.load_runtime_state(max_age_seconds=300)

        assert loaded is not None
        for key, val in state.items():
            assert loaded[key] == val, f"Dérive détectée sur '{key}'"

    def test_capital_preserved_after_restart(self, tmp_path, monkeypatch):
        """Capital identique avant et après restart — pas de double-dépense."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(sc_mod.StartupCache, "STATE_CACHE", tmp_path / "state.pkl")

        cache = sc_mod.StartupCache()
        capital_before = 9_850.75
        cache.save_runtime_state({"capital": capital_before, "cycle": 50})

        loaded = cache.load_runtime_state(max_age_seconds=300)
        assert loaded["capital"] == capital_before

    def test_open_positions_preserved_after_restart(self, tmp_path, monkeypatch):
        """Positions ouvertes identiques après restart — pas de ghost."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(sc_mod.StartupCache, "STATE_CACHE", tmp_path / "state.pkl")

        cache = sc_mod.StartupCache()
        positions_before = [
            {"symbol": "BTC/USDT", "side": "LONG", "size": 0.1, "entry": 50000.0},
            {"symbol": "ETH/USDT", "side": "SHORT", "size": 1.0, "entry": 3000.0},
        ]
        cache.save_runtime_state({"positions": positions_before, "capital": 10_000.0})

        loaded = cache.load_runtime_state(max_age_seconds=300)
        assert loaded["positions"] == positions_before

    # ── Multiple crash/restart cycles ──────────────────────────────────────────

    def test_multiple_restart_cycles_no_drift(self, tmp_path, monkeypatch):
        """5 cycles crash/restart successifs → capital identique à chaque fois."""
        import startup_cache as sc_mod

        monkeypatch.setattr(sc_mod.StartupCache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(sc_mod.StartupCache, "STATE_CACHE", tmp_path / "state.pkl")

        initial_capital = 10_000.0
        for restart in range(5):
            cache = sc_mod.StartupCache()
            loaded = cache.load_runtime_state(max_age_seconds=300)
            capital = loaded["capital"] if loaded else initial_capital

            # Simuler un cycle de trading (gain fictif)
            capital += 10.0 * (restart + 1)
            cache.save_runtime_state({"capital": capital, "restart_count": restart})

        # Après 5 crashes, l'état final doit refléter les 5 cycles
        final = sc_mod.StartupCache()
        monkeypatch.setattr(final, "STATE_CACHE", tmp_path / "state.pkl")
        final_state = final.load_runtime_state(max_age_seconds=300)

        assert final_state is not None
        assert final_state["restart_count"] == 4
        # 10 + 20 + 30 + 40 + 50 = 150 ajoutés
        assert abs(final_state["capital"] - (initial_capital + 150.0)) < 1e-9

    # ── Warmup state consistency ───────────────────────────────────────────────

    def test_warmup_state_consistent_across_restarts(self, tmp_path, monkeypatch):
        """WarmupState persisté identique à chaque rechargement successif."""
        import cold_start.warmup_state_machine as wsm_mod

        state_file = tmp_path / "warmup.json"
        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()
        sm._advance(confidence=1.0)
        sm._advance(confidence=1.0)

        expected = sm.state.name

        # 3 reloads successifs → état identique
        for _ in range(3):
            sm_reload = wsm_mod.WarmupStateMachine.__new__(wsm_mod.WarmupStateMachine)
            sm_reload._state = wsm_mod.WarmupState.BOOTING
            sm_reload._history = []
            sm_reload._consecutive_failures = 0

            persisted = sm_reload.load_persisted_state()
            assert (
                persisted == expected
            ), f"Reload {_ + 1}/3 — attendu {expected}, obtenu {persisted}"

    # ── Signed state integrity ─────────────────────────────────────────────────

    def test_signed_warmup_state_cannot_be_forged(self, tmp_path, monkeypatch):
        """Tentative de forge d'état LIVE_READY → rejeté car signature invalide."""
        import cold_start.warmup_state_machine as wsm_mod

        state_file = tmp_path / "warmup.json"
        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()

        # Forger un état LIVE_READY avec fausse signature
        forged = {
            "state": "LIVE_READY",
            "ts": round(time.time(), 3),
            "extra": {"consecutive_failures": 0},
            "signature": "deadbeef" * 8,
        }
        state_file.write_text(json.dumps(forged))

        persisted = sm.load_persisted_state()
        assert persisted is None, "État forgé LIVE_READY doit être rejeté"

    def test_restart_state_timestamp_coherent(self, tmp_path, monkeypatch):
        """Timestamp de l'état persisté est dans le passé (jamais dans le futur)."""
        import cold_start.warmup_state_machine as wsm_mod

        state_file = tmp_path / "warmup.json"
        monkeypatch.setattr(wsm_mod, "_STATE_PERSIST_PATH", state_file)

        sm = wsm_mod.WarmupStateMachine()
        record = json.loads(state_file.read_text())

        assert (
            record["ts"] <= time.time() + 1.0
        ), "Timestamp persisté ne doit pas être dans le futur"
