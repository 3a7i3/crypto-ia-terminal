"""
Alignement des outils de mesure sur le loader canonique — INV-DATASET-001.

Contexte (audit empirique n°1, 2026-07-28) : au franchissement du gate N>=100,
trois outils mesuraient trois populations différentes à partir du même fichier.

    tools/cri_calculator.py      106 CLOSE  (borne d'époque appliquée)
    scripts/burnin_calibration_v3.py  631 CLOSE  (filtres qualité, pas de borne)
    scripts/prelive_gate.py           649 CLOSE  (aucun filtre)

Le verdict de burn-in en dépendait : NO_GO sur 631 (drawdown 33.55 % hérité des
époques mortes), DEGRADED sur les 106 canoniques. Le désalignement avait donc un
impact décisionnel, il n'était pas cosmétique.

Invariants verrouillés ici :
  ALIGN-01  les trois chemins de lecture rendent exactement la même population
  ALIGN-02  la borne d'époque est appliquée par tous
  ALIGN-03  les filtres de qualité sont appliqués par tous
  ALIGN-04  la provenance reconstitue la population sans ambiguïté
  ALIGN-05  gate D refuse un rapport de burn-in expiré
  ALIGN-06  gate D refuse un rapport calculé sur une autre population
  ALIGN-07  gate D lit le verdict réellement écrit par le producteur
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.burnin_calibration_v3 import _load_real_trades
from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE
from tools.cri_calculator import load_clean_trades, trades_provenance

_AFTER = CLEAN_DATA_SINCE_ACTIVE.timestamp() + 3600
_BEFORE = CLEAN_DATA_SINCE_ACTIVE.timestamp() - 3600


def _close(trade_id: str, ts: float, **overrides) -> dict:
    event = {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": ts,
        "symbol": "BTC/USDT",
        "price": 98000.0,
        "exit_price": 98500.0,
        "score": 75,
        "regime": "bull_trend",
        "duration_s": 3600.0,
        "pnl_usd": 1.0,
        "pnl_pct": 0.01,
    }
    event.update(overrides)
    return event


def _corpus(path: Path) -> dict[str, int]:
    """Corpus couvrant chaque motif d'exclusion. Rend les effectifs attendus."""
    events = [
        # Canoniques — doivent survivre à tous les filtres
        _close("keep-1", _AFTER),
        _close("keep-2", _AFTER, pnl_usd=-2.0, pnl_pct=-0.02),
        # Antérieur à la borne d'époque
        _close("old-1", _BEFORE),
        # Fixture de test : prix synthétique ET score nul, APRÈS la borne
        _close("fixture-1", _AFTER, price=101.0, exit_price=101.0, score=0),
        # Artefact de restauration : clôture instantanée sans contexte
        _close(
            "restore-1",
            _AFTER,
            duration_s=0.0,
            score=0,
            regime="unknown",
        ),
        # Événement non-CLOSE
        {"event": "OPEN", "trade_id": "open-1", "ts": _AFTER},
    ]
    path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    return {"canonical": 2, "close_events": 5}


# ── ALIGN-01/02/03 : une seule population ────────────────────────────────────


def test_burnin_and_canonical_loader_agree(tmp_path, monkeypatch):
    path = tmp_path / "paper_trades.jsonl"
    expected = _corpus(path)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(path))

    canonical = load_clean_trades(path)
    burnin = _load_real_trades(path)

    assert len(canonical) == expected["canonical"]
    assert [t["trade_id"] for t in burnin] == [t["trade_id"] for t in canonical]


def test_prelive_reads_the_same_population(tmp_path, monkeypatch):
    path = tmp_path / "paper_trades.jsonl"
    expected = _corpus(path)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(path))

    from scripts import prelive_gate

    prelive = prelive_gate._read_closes()
    canonical = load_clean_trades(path)

    assert len(prelive) == expected["canonical"]
    assert [t["trade_id"] for t in prelive] == [t["trade_id"] for t in canonical]


@pytest.mark.parametrize("excluded_id", ["old-1", "fixture-1", "restore-1"])
def test_every_exclusion_motive_is_applied(tmp_path, monkeypatch, excluded_id):
    path = tmp_path / "paper_trades.jsonl"
    _corpus(path)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(path))

    from scripts import prelive_gate

    for population in (
        load_clean_trades(path),
        _load_real_trades(path),
        prelive_gate._read_closes(),
    ):
        assert excluded_id not in {t["trade_id"] for t in population}


# ── ALIGN-04 : provenance ────────────────────────────────────────────────────


def test_provenance_accounts_for_every_close_event(tmp_path):
    path = tmp_path / "paper_trades.jsonl"
    expected = _corpus(path)

    prov = trades_provenance(path)

    assert prov["n_canonical"] == expected["canonical"]
    assert prov["close_events_total"] == expected["close_events"]
    # Tout CLOSE est soit canonique, soit écarté pour un motif nommé.
    assert prov["n_canonical"] + sum(prov["excluded_by_reason"].values()) == (
        expected["close_events"]
    )
    assert set(prov["excluded_by_reason"]) == {
        "anterieur_borne_canonique",
        "fixture_de_test",
        "artefact_de_restauration",
    }
    assert prov["clean_data_since"] == CLEAN_DATA_SINCE_ACTIVE.isoformat()


# ── ALIGN-05/06/07 : gate D ne consomme pas n'importe quel rapport ───────────


def _write_burnin_report(
    tmp_path: Path, monkeypatch, *, age_h: float, verdict: str, n_canonical: int
) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(hours=age_h)
    report = {
        "generated_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "go_no_go": verdict,
        "blockers": [],
        "warnings": [],
        "trades": {"count": n_canonical},
        "dataset_provenance": {"n_canonical": n_canonical},
    }
    out = tmp_path / "burnin_v3.json"
    out.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cache" / "burn_in_reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cache" / "burn_in_reports" / "burnin_v3.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def test_gate_d_rejects_expired_report(tmp_path, monkeypatch):
    trades = tmp_path / "paper_trades.jsonl"
    _corpus(trades)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(trades))
    _write_burnin_report(tmp_path, monkeypatch, age_h=72.0, verdict="GO", n_canonical=2)

    from scripts import prelive_gate

    result = prelive_gate.gate_d_calibration()
    assert result.status == prelive_gate.STATUS_NOGO
    assert "EXPIR" in result.detail.upper()


def test_gate_d_rejects_divergent_population(tmp_path, monkeypatch):
    trades = tmp_path / "paper_trades.jsonl"
    _corpus(trades)  # 2 trades canoniques
    monkeypatch.setenv("PAPER_TRADE_LOG", str(trades))
    _write_burnin_report(
        tmp_path, monkeypatch, age_h=1.0, verdict="GO", n_canonical=631
    )

    from scripts import prelive_gate

    result = prelive_gate.gate_d_calibration()
    assert result.status == prelive_gate.STATUS_NOGO
    assert "INV-DATASET-001" in result.detail


def test_gate_d_reads_go_no_go_not_a_phantom_key(tmp_path, monkeypatch):
    """Régression : `burnin_passed` n'est écrit par aucun producteur.

    La gate retombait sur False par défaut et rendait NO-GO en toutes
    circonstances, y compris sur un rapport GO frais et cohérent.
    """
    trades = tmp_path / "paper_trades.jsonl"
    _corpus(trades)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(trades))
    _write_burnin_report(tmp_path, monkeypatch, age_h=1.0, verdict="GO", n_canonical=2)

    from scripts import prelive_gate

    result = prelive_gate.gate_d_calibration()
    assert result.status == prelive_gate.STATUS_GO, result.detail


def test_gate_d_reports_degraded_with_its_warnings(tmp_path, monkeypatch):
    trades = tmp_path / "paper_trades.jsonl"
    _corpus(trades)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(trades))
    stamp = datetime.now(timezone.utc) - timedelta(hours=1)
    report = {
        "generated_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "go_no_go": "DEGRADED",
        "blockers": [],
        "warnings": ["Profit factor < 1.0 (0.62)"],
        "dataset_provenance": {"n_canonical": 2},
    }
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cache" / "burn_in_reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cache" / "burn_in_reports" / "burnin_v3.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    from scripts import prelive_gate

    result = prelive_gate.gate_d_calibration()
    assert result.status == prelive_gate.STATUS_NOGO
    assert "Profit factor" in result.detail
