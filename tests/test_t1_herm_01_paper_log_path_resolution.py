"""
tests/test_t1_herm_01_paper_log_path_resolution.py — T1-HERM-01 / DS-001.

Preuves comportementales (pas d'inspection de source) que
infra/wallet_sync.py, paper_trading/dataset_validator.py et
paper_trading/recorder.py résolvent PAPER_TRADE_LOG À L'APPEL, jamais
comme défaut de signature figé à l'import ni comme constante de module
liée à l'import (ADR-0008).

Chaque scénario importe le module d'ABORD, puis positionne
PAPER_TRADE_LOG APRÈS coup — l'ordre hostile qui faisait échouer le code
pré-correction (le module avait déjà figé l'ancien chemin/défaut).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import time

REPO_PROD_LEDGER = "databases/paper_trades.jsonl"


def _hash_or_none(path):
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _write_close_event(path, trade_id: str, pnl_usd: float) -> None:
    now = time.time()
    evt = {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": now,
        "ts_iso": "2026-09-12T00:00:00Z",
        "symbol": "BTC/USDT",
        "side": "buy",
        "price": 65000.0,
        "size_usd": 50.0,
        "mode": "paper",
        "schema_version": 5,
        "pnl_usd": pnl_usd,
        "pnl_pct": 0.01,
        "reason": "take_profit",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(evt) + "\n")


class TestScenarioE_NoProductionFilesystemMutation:
    """E — preuve que cette suite ne touche jamais databases/paper_trades.jsonl."""

    def test_repo_ledger_untouched_before_and_after(self, monkeypatch, tmp_path):
        before = _hash_or_none(REPO_PROD_LEDGER)

        import infra.wallet_sync as ws
        import paper_trading.dataset_validator as dv
        import paper_trading.recorder as rec

        tmp_ledger = tmp_path / "hostile_e.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(tmp_ledger))
        _write_close_event(tmp_ledger, "e1", 5.0)

        ws.get_scientific_capital()
        dv.validate_log()
        dv.validate_corpus()
        rec.PaperTradeRecorder()

        after = _hash_or_none(REPO_PROD_LEDGER)
        assert before == after, (
            "databases/paper_trades.jsonl a été modifié par la suite T1-HERM-01"
        )


class TestScenarioA_WalletSyncHostileImportOrdering:
    """A — WalletSync.get_scientific_capital() doit lire le PAPER_TRADE_LOG
    courant, même positionné APRÈS l'import du module."""

    def test_scientific_capital_reads_post_import_env_path(self, monkeypatch, tmp_path):
        # 1. import AVANT toute variable d'env dédiée à ce test
        import infra.wallet_sync as ws

        importlib.reload(ws)  # neutralise toute contamination d'un test précédent

        # 2. positionne PAPER_TRADE_LOG APRÈS l'import — l'ordre hostile.
        ledger_b = tmp_path / "ledger_b.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(ledger_b))

        # 3. écrit un CLOSE connu dans le ledger B
        _write_close_event(ledger_b, "b1", 42.5)

        # 4. invoque le chemin scientific-capital
        capital = ws.get_scientific_capital()

        # 5. preuve que B est lu : le capital reflète le PnL de B
        assert capital == ws._PAPER_CAPITAL + 42.5

        # 6. preuve que le ledger repo par défaut n'est PAS celui utilisé :
        # un ledger B vide donnerait exactement _PAPER_CAPITAL — ce n'est pas
        # le cas ici, donc B (et non databases/paper_trades.jsonl) a été lu.
        assert not (tmp_path / "databases").exists()

    def test_wallet_sync_init_baseline_reads_post_import_env_path(
        self, monkeypatch, tmp_path
    ):
        import infra.wallet_sync as ws

        importlib.reload(ws)

        ledger_b = tmp_path / "ledger_b2.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(ledger_b))
        _write_close_event(ledger_b, "b2", 7.0)

        wallet = ws.WalletSync(mode="paper")
        assert wallet.session_pnl_since_restart() == 0.0  # baseline == courant

        _write_close_event(ledger_b, "b3", 3.0)
        assert wallet.session_pnl_since_restart() == 3.0

    def test_get_balance_paper_reads_post_import_env_path(self, monkeypatch, tmp_path):
        import infra.wallet_sync as ws

        importlib.reload(ws)

        ledger_b = tmp_path / "ledger_b3.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(ledger_b))
        _write_close_event(ledger_b, "b4", 11.0)

        wallet = ws.WalletSync(mode="paper")
        assert wallet.get_balance() == ws._PAPER_CAPITAL + 11.0


class TestScenarioB_DatasetValidatorHostileImportOrdering:
    """B — validate_log()/validate_corpus() sans argument doivent lire
    PAPER_TRADE_LOG courant, même positionné APRÈS l'import du module."""

    def test_validate_log_reads_post_import_env_path(self, monkeypatch, tmp_path):
        import paper_trading.dataset_validator as dv

        ledger = tmp_path / "hostile_b_log.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(ledger))

        with open(ledger, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "event": "OPEN",
                        "trade_id": "hb1",
                        "ts": time.time(),
                        "ts_iso": "2026-09-12T00:00:00Z",
                        "symbol": "BTC/USDT",
                        "side": "buy",
                        "price": 100.0,
                        "size_usd": 10.0,
                        "mode": "paper",
                        "schema_version": 999,  # invalide -> violation garantie
                    }
                )
                + "\n"
            )

        result = dv.validate_log()
        assert not result.valid
        assert any("schema_version=999" in v for v in result.violations)

    def test_validate_corpus_reads_post_import_env_path(self, monkeypatch, tmp_path):
        import paper_trading.dataset_validator as dv

        ledger = tmp_path / "hostile_b_corpus.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(ledger))
        _write_close_event(ledger, "hb2", 1.0)

        report = dv.validate_corpus()
        assert report.close_count == 1


class TestScenarioC_ExplicitPathPrecedence:
    """C — un log_path explicite l'emporte toujours sur PAPER_TRADE_LOG."""

    def test_validate_log_explicit_path_overrides_env(self, monkeypatch, tmp_path):
        import paper_trading.dataset_validator as dv

        env_ledger = tmp_path / "env_ledger.jsonl"
        explicit_ledger = tmp_path / "explicit_ledger.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(env_ledger))

        _write_close_event(explicit_ledger, "c1", 9.0)
        # env_ledger reste vide/absent

        report_explicit = dv.validate_corpus(str(explicit_ledger))
        assert report_explicit.close_count == 1

        report_env = dv.validate_corpus()
        assert report_env.close_count == 0

    def test_validate_corpus_explicit_path_overrides_env(self, monkeypatch, tmp_path):
        import paper_trading.dataset_validator as dv

        env_ledger = tmp_path / "env_ledger2.jsonl"
        explicit_ledger = tmp_path / "explicit_ledger2.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(env_ledger))
        _write_close_event(env_ledger, "c2", 2.0)
        _write_close_event(explicit_ledger, "c3", 4.0)
        _write_close_event(explicit_ledger, "c4", 6.0)

        report = dv.validate_corpus(str(explicit_ledger))
        assert report.close_count == 2


class TestScenarioD_RecorderHostileImportOrdering:
    """D — PaperTradeRecorder() sans argument doit utiliser le PAPER_TRADE_LOG
    courant, même positionné APRÈS l'import du module."""

    def test_recorder_uses_post_import_env_path(self, monkeypatch, tmp_path):
        import paper_trading.recorder as rec

        ledger = tmp_path / "hostile_d.jsonl"
        monkeypatch.setenv("PAPER_TRADE_LOG", str(ledger))

        recorder = rec.PaperTradeRecorder()
        assert recorder._path == ledger

        # record_close() ne dépend pas de config.parameter_audit (contrairement
        # à record_open()), donc n'exige pas les dépendances optionnelles
        # (pydantic) potentiellement absentes de l'environnement local — la
        # preuve porte sur la résolution du chemin, pas sur ce chemin de code.
        recorder.record_close(
            trade_id="d1",
            exit_price=3010.0,
            pnl_usd=1.5,
            pnl_pct=0.005,
            reason="take_profit",
        )
        assert ledger.exists()
        assert not (tmp_path / "databases").exists()
