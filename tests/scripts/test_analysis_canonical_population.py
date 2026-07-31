"""
tests/scripts/test_analysis_canonical_population.py

Verrouille `analysis.base.load_canonical_trades` — le point d'entrée des tests
d'hypothèses H1-H6 — sur le loader canonique unique (INV-DATASET-001).

Contexte du correctif (2026-07-31) : `analysis/regime_audit.py` codait en dur
la borne v1 (2026-06-25, ADR-0011) et lisait `analysis/base.load_trades`, hors
borne d'époque. Pire, il projetait `opened_at` depuis un champ `timestamp` que
le recorder n'écrit pas (il écrit `ts`) : le filtre de date écartait alors
100 % des trades et l'outil affichait « Trades propres : 0 » quelle que soit
la population réelle. Ces tests interdisent le retour de ces deux défauts.
"""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

import pytest

from analysis.base import load_canonical_trades
from tools.cri_calculator import CLEAN_DATA_SINCE_ACTIVE, load_clean_trades

# Deux instants encadrant la borne d'époque active, dérivés d'elle et jamais
# écrits en dur : le jour où la borne bouge, ces tests suivent.
_AFTER_TS = CLEAN_DATA_SINCE_ACTIVE.timestamp() + 86_400.0
_BEFORE_TS = CLEAN_DATA_SINCE_ACTIVE.timestamp() - 86_400.0


def _iso(ts: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _pair(trade_id: str, ts: float, **close_extra: object) -> list[dict]:
    """Un couple OPEN/CLOSE minimal mais réaliste (schéma du recorder v3)."""
    close: dict[str, object] = {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": ts + 3600.0,
        "ts_iso": _iso(ts + 3600.0),
        "symbol": "BTC/USDT",
        "side": "buy",
        "price": 61_000.0,
        "exit_price": 61_000.0,
        "size_usd": 3.0,
        "regime": "bull_trend",
        "score": 80,
        "pnl_usd": 1.5,
        "pnl_pct": 2.5,
        "duration_s": 3600.0,
        "reason": "TP",
    }
    close.update(close_extra)
    return [
        {
            "event": "OPEN",
            "trade_id": trade_id,
            "ts": ts,
            "ts_iso": _iso(ts),
            "symbol": "BTC/USDT",
            "side": "buy",
            "price": 60_000.0,
            "size_usd": 3.0,
            "regime": "bull_trend",
            "score": 80,
        },
        close,
    ]


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )


def test_population_identique_au_loader_canonique(tmp_path: Path) -> None:
    """La population EST celle de load_clean_trades — ni plus, ni moins."""
    p = tmp_path / "paper_trades.jsonl"
    _write(p, _pair("OLD", _BEFORE_TS) + _pair("NEW", _AFTER_TS))

    canonical_ids = {d["trade_id"] for d in load_clean_trades(p)}
    trade_ids = {t.trade_id for t in load_canonical_trades(str(p))}

    assert trade_ids == canonical_ids
    assert trade_ids == {"NEW"}, "un CLOSE antérieur à la borne doit être écarté"


def test_enrichissement_ne_filtre_jamais(tmp_path: Path) -> None:
    """Un CLOSE canonique sans OPEN correspondant reste dans la population.

    La jointure sert à enrichir (entry_price, opened_at), jamais à exclure :
    exclure ici ferait diverger le N de l'audit du N canonique du CRI.
    """
    p = tmp_path / "paper_trades.jsonl"
    orphan_close = _pair("ORPHAN", _AFTER_TS)[1]
    _write(p, _pair("PAIRED", _AFTER_TS) + [orphan_close])

    trades = load_canonical_trades(str(p))

    assert {t.trade_id for t in trades} == {"PAIRED", "ORPHAN"}
    assert len(trades) == len(load_clean_trades(p))
    orphan = next(t for t in trades if t.trade_id == "ORPHAN")
    assert orphan.entry_price == 0.0, "sans OPEN, entry_price est inconnu, pas exclu"
    assert orphan.regime == "bull_trend", "les champs portés par CLOSE restent lus"


def test_opened_at_lit_le_champ_ts_reellement_ecrit(tmp_path: Path) -> None:
    """Régression : `ts` est le nom écrit par le recorder, pas `timestamp`.

    Lire `timestamp` laissait `opened_at=None` sur 100 % des trades, ce qui
    rendait tout filtre de date destructeur et l'audit muet.
    """
    p = tmp_path / "paper_trades.jsonl"
    _write(p, _pair("T1", _AFTER_TS))

    trades = load_canonical_trades(str(p))

    assert len(trades) == 1
    assert trades[0].opened_at == pytest.approx(_AFTER_TS)


def test_atr_absent_reste_none_sans_exclure_le_trade(tmp_path: Path) -> None:
    """H4 doit être non concluante par ABSENCE de donnée, pas par N filtré."""
    p = tmp_path / "paper_trades.jsonl"
    _write(p, _pair("T1", _AFTER_TS))

    trades = load_canonical_trades(str(p))

    assert len(trades) == 1, "l'absence d'atr_pct n'écarte pas le trade"
    assert trades[0].atr_pct is None
    assert trades[0].volume_usd is None


def test_atr_present_est_projete(tmp_path: Path) -> None:
    """Le jour où le recorder écrira atr_pct, H4 doit s'alimenter seule."""
    p = tmp_path / "paper_trades.jsonl"
    records = _pair("T1", _AFTER_TS)
    records[0]["atr_pct"] = 2.4  # porté par l'OPEN
    _write(p, records)

    trades = load_canonical_trades(str(p))

    assert trades[0].atr_pct == pytest.approx(2.4)


def test_fichier_absent_echoue_bruyamment(tmp_path: Path) -> None:
    """Un fichier introuvable lève, il ne rend pas une population vide.

    `load_clean_trades` rend [] sur fichier absent ; propager ce [] ferait
    afficher « N canonique : 0 », indiscernable d'un dataset réellement vide.
    """
    with pytest.raises(FileNotFoundError):
        load_canonical_trades(str(tmp_path / "jamais_ecrit.jsonl"))


def test_regime_audit_ne_reintroduit_pas_de_borne_locale() -> None:
    """`--since` par défaut ne doit ôter aucun trade de la population.

    Le défaut historique était une constante CLEAN_SINCE codée en dur dans le
    runner, qui court-circuitait la borne canonique.
    """
    import analysis.regime_audit as ra

    source = Path(ra.__file__).read_text(encoding="utf-8")
    assert "CLEAN_SINCE" not in source, "borne d'époque locale réintroduite"

    trades = ["sentinelle"]
    assert ra._filter_by_date(trades, None) is trades
