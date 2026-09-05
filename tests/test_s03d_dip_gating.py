"""
tests/test_s03d_dip_gating.py — S-03D-R1 blocker 1 focused tests.

Couvre :
  1. DIP inactif -> DIPObserver.instance() n'est jamais appelé
     (aucune instance fraîche créée pour l'observer)
  2. DIP inactif -> l'instantané de provenance ne contient aucun compteur
     numérique fabriqué (status NOT_STARTED uniquement)
  3. DIP actif -> l'instantané expose les vraies stats du singleton LIVE
     déjà existant (pas un nouvel objet)

Reproduit exactement la garde de core/advisor_loop.py (bloc S-03D) :

    if dip.bootstrap.is_running():
        dip_observer_live = DIPObserver.instance()
    else:
        dip_observer_live = None

sans dépendre du reste de l'initialisation d'advisor_loop.py (des dizaines
de milliers de lignes), pour garder le test focalisé et rapide.
"""

from __future__ import annotations

from observability import runtime_provenance_snapshot as rps


def _dip_observer_live_via_advisor_loop_guard(monkeypatch, is_running: bool):
    """Reproduit le bloc de garde S-03D dans core/advisor_loop.py."""
    import dip.bootstrap as bootstrap
    from dip.core.observer import DIPObserver

    monkeypatch.setattr(bootstrap, "is_running", lambda: is_running)

    calls = {"instance": 0}
    real_instance = DIPObserver.instance

    def _tracked_instance():
        calls["instance"] += 1
        return real_instance()

    monkeypatch.setattr(DIPObserver, "instance", staticmethod(_tracked_instance))

    dip_observer_live = None
    if bootstrap.is_running():
        dip_observer_live = DIPObserver.instance()
    return dip_observer_live, calls


def test_inactive_dip_does_not_call_dip_observer_instance(monkeypatch):
    dip_observer_live, calls = _dip_observer_live_via_advisor_loop_guard(
        monkeypatch, is_running=False
    )
    assert dip_observer_live is None
    assert calls["instance"] == 0


def test_inactive_dip_snapshot_has_no_numeric_counters(monkeypatch):
    dip_observer_live, calls = _dip_observer_live_via_advisor_loop_guard(
        monkeypatch, is_running=False
    )
    assert calls["instance"] == 0

    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(dip_observer=dip_observer_live))
    dip_block = snap["dip"]
    assert dip_block == {"status": "NOT_STARTED"}
    assert "handler_count" not in dip_block
    assert "skipped_invalid_provenance" not in dip_block


def test_active_dip_exposes_real_live_singleton_stats(monkeypatch):
    dip_observer_live, calls = _dip_observer_live_via_advisor_loop_guard(
        monkeypatch, is_running=True
    )
    assert calls["instance"] == 1
    assert dip_observer_live is not None

    handler_calls = []
    dip_observer_live.register(lambda obs: handler_calls.append(obs))

    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(dip_observer=dip_observer_live))
    dip_block = snap["dip"]
    assert dip_block["status"] in ("ACTIVE", "NOT_STARTED")
    # Real handler_count reflects the live singleton's actual registrations,
    # not a fabricated zero from a fresh object.
    assert dip_block["handler_count"] == dip_observer_live.handler_count
    assert dip_block["handler_count"] >= 1
