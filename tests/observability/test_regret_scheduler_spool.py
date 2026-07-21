"""Spool du RegretScheduler — la file des candidats survit aux restarts.

Leçon 2026-07-21 : la file vivait en mémoire seule ; chaque restart coûtait
jusqu'à ~24 h de couverture regret (trou détecté par le garde-fou de fraîcheur
MC-001). Corollaire de validité testé ici : un horizon trop en retard est
abandonné, jamais évalué avec un prix hors-fenêtre.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from observability.regret_scheduler import _HORIZONS, RegretScheduler


def _obs(obs_id="obs-1", ts=None, symbol="BTC/USDT"):
    return SimpleNamespace(
        actionable=True,
        trade_allowed=False,
        side="BUY",
        score=70.0,
        observation_id=obs_id,
        symbol=symbol,
        price=100.0,
        ts=ts if ts is not None else time.time(),
        regime="sideways",
        first_blocker="gate",
        all_blockers=["gate"],
        personality_name="test",
    )


def test_spool_roundtrip_survit_au_restart(tmp_path):
    a = RegretScheduler(store_dir=tmp_path)
    a.on_observation(_obs())
    a._save_spool()

    b = RegretScheduler(store_dir=tmp_path)  # « restart »
    assert "obs-1" in b._candidates
    assert set(b._candidates["obs-1"].pending_horizons) == set(_HORIZONS)


def test_tick_ecrit_le_spool_quand_l_etat_change(tmp_path):
    s = RegretScheduler(store_dir=tmp_path)
    s.on_observation(_obs())
    s._tick()
    assert (tmp_path / "pending_spool.json").exists()


def test_horizon_trop_en_retard_abandonne_jamais_falsifie(tmp_path):
    s = RegretScheduler(store_dir=tmp_path)
    s.on_observation(_obs(ts=time.time() - 7200))  # signal vieux de 2 h
    s.update_price_cache({"BTC/USDT": 105.0})
    s._tick()
    c = s._candidates["obs-1"]
    # 5m/15m/30m/1h expirés hors tolérance → abandonnés SANS résultat
    for h in ("5m", "15m", "30m", "1h"):
        assert h not in c.results and h not in c.pending_horizons
    # 4h/12h/24h encore à venir → toujours en attente
    for h in ("4h", "12h", "24h"):
        assert h in c.pending_horizons


def test_horizon_echu_dans_la_tolerance_evalue(tmp_path):
    s = RegretScheduler(store_dir=tmp_path)
    s.on_observation(_obs(ts=time.time() - 320))  # 5m échu depuis ~20 s
    s.update_price_cache({"BTC/USDT": 105.0})
    s._tick()
    assert s._candidates["obs-1"].results["5m"]["regret_type"] == "MISSED_WIN"


def test_spool_corrompu_ignore_jamais_fatal(tmp_path):
    (tmp_path / "pending_spool.json").write_text("{pas du json", encoding="utf-8")
    s = RegretScheduler(store_dir=tmp_path)  # ne doit pas lever
    assert s._candidates == {}


def test_candidat_complet_jamais_respoole(tmp_path):
    s = RegretScheduler(store_dir=tmp_path)
    s.on_observation(_obs())
    s._candidates["obs-1"].complete = True
    s._save_spool()
    assert RegretScheduler(store_dir=tmp_path)._candidates == {}
