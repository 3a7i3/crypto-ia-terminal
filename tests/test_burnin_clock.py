"""Horloge de burn-in — une seule source, qui survit aux redémarrages.

Régression couverte (constat opérateur 2026-08-07) : le panneau MEXC SIM
affichait « Duree : J0.8 / 7 (session depuis restart) » alors que l'époque V4
courait depuis des semaines. Deux compteurs mesuraient la même durée et tous
deux repartaient de zéro au redémarrage — un burn-in de 7 jours devenait
inatteignable dès que le service redémarrait plus souvent que tous les 7 jours.
"""

import json
import time

import pytest

from system import burnin_clock


@pytest.fixture(autouse=True)
def _isolated_clock(tmp_path, monkeypatch):
    """État persisté et dataset isolés — jamais ceux du dépôt."""
    monkeypatch.setenv("BURNIN_CLOCK_STATE", str(tmp_path / "burnin_clock.json"))
    monkeypatch.setenv("PAPER_TRADE_LOG", str(tmp_path / "paper_trades.jsonl"))
    monkeypatch.delenv("BURNIN_START_TS", raising=False)
    burnin_clock._CACHE = None
    yield
    burnin_clock._CACHE = None


def _simulate_restart():
    """Un redémarrage = un nouveau process = cache vide, état sur disque."""
    burnin_clock._CACHE = None


# ── Ordre de résolution ───────────────────────────────────────────────────────


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("BURNIN_START_TS", "2026-07-20T00:00:00Z")

    assert burnin_clock.burnin_start(refresh=True) == pytest.approx(1784505600.0)
    assert burnin_clock.burnin_source() == burnin_clock.SOURCE_ENV


def test_env_override_accepts_epoch_seconds(monkeypatch):
    monkeypatch.setenv("BURNIN_START_TS", "1784505600")

    assert burnin_clock.burnin_start(refresh=True) == pytest.approx(1784505600.0)


def test_falls_back_to_epoch_when_dataset_empty():
    started = burnin_clock.burnin_start(refresh=True)

    assert started == pytest.approx(burnin_clock._epoch().timestamp())
    assert burnin_clock.burnin_source() == burnin_clock.SOURCE_EPOCH


def test_first_clean_trade_anchors_the_clock(tmp_path):
    first = burnin_clock._epoch().timestamp() + 3600
    log = tmp_path / "paper_trades.jsonl"
    log.write_text(
        "\n".join(
            json.dumps(
                {
                    "event": "CLOSE",
                    "ts": ts,
                    "price": 1200.0,
                    "score": 72,
                    "duration_s": 900,
                    "regime": "bull",
                }
            )
            for ts in (first + 7200, first, first + 3600)
        )
        + "\n",
        encoding="utf-8",
    )

    assert burnin_clock.burnin_start(refresh=True) == pytest.approx(first)
    assert burnin_clock.burnin_source() == burnin_clock.SOURCE_FIRST_TRADE


# ── Le point qui motive tout le module ────────────────────────────────────────


def test_clock_survives_restart(monkeypatch):
    monkeypatch.setenv("BURNIN_START_TS", "2026-07-20T00:00:00Z")
    started = burnin_clock.burnin_start(refresh=True)

    # L'override disparaît (variable d'env non repassée au redémarrage) :
    # l'état persisté doit prendre le relais, pas `time.time()`.
    monkeypatch.delenv("BURNIN_START_TS")
    _simulate_restart()

    assert burnin_clock.burnin_start() == pytest.approx(started)
    assert burnin_clock.burnin_source() == burnin_clock.SOURCE_STATE


def test_days_elapsed_does_not_reset_on_restart(monkeypatch):
    monkeypatch.setenv(
        "BURNIN_START_TS", str(time.time() - 12.5 * burnin_clock.SECONDS_PER_DAY)
    )
    burnin_clock.burnin_start(refresh=True)
    monkeypatch.delenv("BURNIN_START_TS")

    _simulate_restart()

    assert burnin_clock.days_elapsed() == pytest.approx(12.5, abs=0.01)


def test_state_of_a_past_epoch_is_ignored(tmp_path):
    stale = tmp_path / "burnin_clock.json"
    stale.write_text(
        json.dumps(
            {"started_at": 1_700_000_000.0, "epoch": "2026-07-09T07:45:00+00:00"}
        ),
        encoding="utf-8",
    )

    started = burnin_clock.burnin_start(refresh=True)

    assert started != pytest.approx(1_700_000_000.0)
    assert burnin_clock.burnin_source() == burnin_clock.SOURCE_EPOCH


def test_reset_is_an_explicit_gesture():
    burnin_clock.burnin_start(refresh=True)

    burnin_clock.reset(started_at=1_784_937_600.0)
    _simulate_restart()

    assert burnin_clock.burnin_start() == pytest.approx(1_784_937_600.0)


def test_days_elapsed_never_negative(monkeypatch):
    monkeypatch.setenv("BURNIN_START_TS", str(time.time() + 86400))
    burnin_clock.burnin_start(refresh=True)

    assert burnin_clock.days_elapsed() == 0.0


def test_snapshot_exposes_provenance():
    snap = burnin_clock.snapshot()

    assert snap["source"] == burnin_clock.SOURCE_EPOCH
    assert snap["epoch"] == burnin_clock._epoch().isoformat()
    assert snap["days_elapsed"] >= 0.0


# ── Consommateurs ─────────────────────────────────────────────────────────────


def test_capital_throttle_uses_the_shared_clock(monkeypatch):
    from capital_deployment.capital_throttle import CapitalThrottle

    monkeypatch.setenv(
        "BURNIN_START_TS", str(time.time() - 9 * burnin_clock.SECONDS_PER_DAY)
    )
    burnin_clock.burnin_start(refresh=True)

    alloc = CapitalThrottle(total_capital=500.0, phase="F-01").allocation()

    assert alloc.days_elapsed() == pytest.approx(9.0, abs=0.01)
    assert alloc.time_requirement_met()  # 9 j > 7 j : plus remis à zéro


def test_explicit_started_at_still_wins(monkeypatch):
    from capital_deployment.capital_throttle import CapitalThrottle

    monkeypatch.setenv("BURNIN_START_TS", str(time.time() - 9 * 86400))
    burnin_clock.burnin_start(refresh=True)

    alloc = CapitalThrottle(
        total_capital=500.0, phase="F-01", started_at=time.time() - 86400
    ).allocation()

    assert alloc.days_elapsed() == pytest.approx(1.0, abs=0.01)


def test_mexc_report_shows_shared_clock_not_session_uptime(monkeypatch):
    from paper_trading import mexc_simulator

    monkeypatch.setenv(
        "BURNIN_START_TS", str(time.time() - 21.3 * burnin_clock.SECONDS_PER_DAY)
    )
    burnin_clock.burnin_start(refresh=True)

    line = mexc_simulator._burnin_line()

    assert line == "Burn-in  : J21.3 / 7 (horloge partagee)"
    assert "restart" not in line


def test_mexc_report_omits_the_line_rather_than_lying(monkeypatch):
    from paper_trading import mexc_simulator

    monkeypatch.setattr(
        burnin_clock,
        "days_elapsed",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("horloge HS")),
    )

    assert mexc_simulator._burnin_line() == ""


def test_performance_tracker_has_no_local_clock():
    from paper_trading.mexc_simulator import PerformanceTracker

    assert not hasattr(PerformanceTracker(), "days_running")
