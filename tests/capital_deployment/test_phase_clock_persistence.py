"""Horloge de phase — elle doit survivre au redémarrage du processus.

Défaut corrigé. `PhaseAllocation.started_at` valait `time.time()` à chaque
construction, sans persistance : le compteur repartait à zéro à **chaque**
démarrage. Le critère `min_duration_days` (7 j pour F-01) n'était donc
satisfiable que si le moteur tournait 7 jours consécutifs sans un seul
redémarrage — déploiement, migration ou crash inclus.

Preuve empirique du 2026-08-05 : le bot affichait « Jour 3.2 / 7 » alors que le
processus avait exactement 3 jours d'uptime. Le compteur mesurait l'âge du
**processus**, pas celui de la **phase**.

Deux propriétés sont verrouillées ici, et elles tirent en sens opposés :

1. **Un redémarrage à phase identique conserve le temps écoulé.**
2. **Un changement de phase le remet à zéro** — une nouvelle phase démarre sa
   propre horloge, ce n'est pas une régression mais la définition.
"""

from __future__ import annotations

import importlib
import json
import time

import pytest


@pytest.fixture()
def throttle_mod(tmp_path, monkeypatch):
    """Module rechargé avec une horloge isolée dans tmp_path."""
    monkeypatch.setenv("PHASE_CLOCK_PATH", str(tmp_path / "phase_clock.json"))
    import capital_deployment.capital_throttle as ct

    importlib.reload(ct)
    yield ct
    monkeypatch.delenv("PHASE_CLOCK_PATH", raising=False)
    importlib.reload(ct)


def _reculer_horloge(mod, jours: float) -> None:
    """Simule `jours` écoulés en reculant l'horodatage persisté."""
    p = mod._PHASE_CLOCK_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    data["started_at"] = time.time() - jours * 86400.0
    p.write_text(json.dumps(data), encoding="utf-8")


class TestSurvieAuRedemarrage:
    def test_redemarrage_meme_phase_conserve_le_temps(self, throttle_mod):
        throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        _reculer_horloge(throttle_mod, 3.2)

        rejoue = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert rejoue.allocation().days_elapsed() == pytest.approx(3.2, abs=0.01)

    def test_le_critere_de_duree_devient_atteignable(self, throttle_mod):
        throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        _reculer_horloge(throttle_mod, 8.0)  # > min_duration_days = 7

        rejoue = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert rejoue.allocation().time_requirement_met() is True

    def test_premier_demarrage_part_de_zero(self, throttle_mod):
        t = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert t.allocation().days_elapsed() < 0.001


class TestChangementDePhase:
    def test_nouvelle_phase_repart_de_zero(self, throttle_mod):
        throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        _reculer_horloge(throttle_mod, 9.0)

        suivante = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-02")
        assert suivante.allocation().days_elapsed() < 0.001

    def test_advance_to_repart_de_zero(self, throttle_mod):
        t = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        _reculer_horloge(throttle_mod, 9.0)
        suivante = t.advance_to("F-02", certified=True)
        assert suivante.allocation().days_elapsed() < 0.001


class TestAucunImpactSurLeSizing:
    """La persistance mesure le temps ; elle ne touche à aucune décision."""

    def test_capital_alloue_identique_avant_et_apres_restauration(self, throttle_mod):
        avant = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        _reculer_horloge(throttle_mod, 5.0)
        apres = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")

        assert apres.allocated_capital == avant.allocated_capital
        assert apres.throttled_size(500.0) == avant.throttled_size(500.0)
        assert apres.max_single_position() == avant.max_single_position()


class TestRobustesse:
    """Une horloge d'observation ne doit jamais empêcher le moteur de démarrer."""

    def test_fichier_corrompu_repart_de_zero_sans_lever(self, throttle_mod):
        throttle_mod._PHASE_CLOCK_PATH.write_text("{ corrompu", encoding="utf-8")
        t = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert t.allocation().days_elapsed() < 0.001

    def test_horodatage_futur_ne_produit_jamais_de_duree_negative(self, throttle_mod):
        throttle_mod._PHASE_CLOCK_PATH.write_text(
            json.dumps({"phase": "F-01", "started_at": time.time() + 99_999}),
            encoding="utf-8",
        )
        t = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert t.allocation().days_elapsed() >= 0.0

    def test_fichier_absent_repart_de_zero(self, throttle_mod):
        if throttle_mod._PHASE_CLOCK_PATH.exists():
            throttle_mod._PHASE_CLOCK_PATH.unlink()
        t = throttle_mod.CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert t.allocation().days_elapsed() < 0.001

    def test_started_at_explicite_fait_autorite(self, throttle_mod):
        """L'appelant qui fournit une date prime sur le fichier (tests, rejeu)."""
        impose = time.time() - 4.0 * 86400.0
        t = throttle_mod.CapitalThrottle(
            total_capital=10_000.0, phase="F-01", started_at=impose
        )
        assert t.allocation().days_elapsed() == pytest.approx(4.0, abs=0.01)
