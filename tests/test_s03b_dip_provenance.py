"""
S-03B-R1 — tests focalisés : garde de provenance à l'ingress DIP.

Couvre :
  - observation à provenance invalide -> aucun handler appelé, compteur
    skipped_invalid_provenance incrémenté
  - observation valide -> distribution normale inchangée
  - isolation par handler (un handler qui lève une exception n'affecte pas
    les autres) inchangée

Fixtures en mémoire uniquement — pas de bus réel, pas de fichier runtime.
"""

from __future__ import annotations

from types import SimpleNamespace

from dip.core.observer import DIPObserver


def _make_obs(**kwargs):
    defaults = dict(
        packet_id="pkt-123",
        provenance_valid=True,
        observation_id="obs-1",
        symbol="BTC/USDT",
        cycle=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_invalid_provenance_observation_not_dispatched_case_a():
    observer = DIPObserver()
    calls = []
    observer.register(lambda obs: calls.append(obs))

    obs = _make_obs(packet_id="", provenance_valid=False)
    observer._on_observation(obs)

    assert calls == []
    assert observer.get_stats()["skipped_invalid_provenance"] == 1


def test_valid_provenance_observation_dispatched_normally_case_b():
    observer = DIPObserver()
    calls = []
    observer.register(lambda obs: calls.append(obs))

    obs = _make_obs(packet_id="pkt-abc", provenance_valid=True)
    observer._on_observation(obs)

    assert len(calls) == 1
    assert calls[0] is obs
    assert observer.get_stats()["skipped_invalid_provenance"] == 0


def test_empty_packet_id_skipped_even_if_provenance_valid_true():
    observer = DIPObserver()
    calls = []
    observer.register(lambda obs: calls.append(obs))

    obs = _make_obs(packet_id="", provenance_valid=True)
    observer._on_observation(obs)

    assert calls == []
    assert observer.get_stats()["skipped_invalid_provenance"] == 1


def test_handler_exception_isolation_unchanged_case_c():
    observer = DIPObserver()
    good_calls = []

    def bad_handler(obs):
        raise RuntimeError("boom")

    def good_handler(obs):
        good_calls.append(obs)

    observer.register(bad_handler)
    observer.register(good_handler)

    obs = _make_obs()
    observer._on_observation(obs)

    assert len(good_calls) == 1
    assert observer.get_stats()["skipped_invalid_provenance"] == 0
