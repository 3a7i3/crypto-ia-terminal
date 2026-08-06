"""Verrou d'instance — SIGTERM doit declencher une sortie PROPRE.

`atexit` ne s'execute pas quand le process est tue par un signal : l'action
par defaut de SIGTERM termine immediatement. systemd envoie SIGTERM a chaque
`systemctl stop|restart`, donc le verrou survivait a tous les redemarrages et
chaque boot annoncait « verrou precedent non nettoye — arret non-propre,
crash ou signal non intercepte ».

Mesure du 2026-08-06 : quatre redemarrages, quatre fois le meme message. Un
vrai crash etait donc indiscernable d'un arret normal — le marqueur de
demarrage le plus utile ne distinguait plus rien.
"""

from __future__ import annotations

import signal

import pytest

from core import advisor_loop


@pytest.fixture
def handlers_restaures():
    """Installe puis restaure : ces handlers sont un etat global du process."""
    surveilles = [signal.SIGTERM, signal.SIGINT]
    anciens = {s: signal.getsignal(s) for s in surveilles}
    yield surveilles
    for s, ancien in anciens.items():
        signal.signal(s, ancien)


class TestArretPropre:
    def test_les_signaux_d_arret_sont_intercepetes(self, handlers_restaures):
        advisor_loop._install_stop_handlers()

        for sig in handlers_restaures:
            courant = signal.getsignal(sig)
            assert callable(courant), f"{sig.name} sans gestionnaire"
            assert courant not in (signal.SIG_DFL, signal.SIG_IGN)

    def test_le_gestionnaire_sort_avec_le_code_zero(self, handlers_restaures):
        advisor_loop._install_stop_handlers()
        gestionnaire = signal.getsignal(signal.SIGTERM)

        with pytest.raises(SystemExit) as sortie:
            gestionnaire(signal.SIGTERM, None)

        assert sortie.value.code == 0, "un arret demande n'est pas un echec"

    def test_systemexit_traverse_les_gardes_du_moteur(self):
        """Pourquoi sys.exit et non une exception ordinaire.

        Le moteur est truffe de `except Exception` qui avalent tout pour ne
        jamais mourir. SystemExit derive de BaseException, pas d'Exception :
        il traverse ces gardes et laisse `atexit` liberer le verrou.
        """
        assert not issubclass(SystemExit, Exception)
        assert issubclass(SystemExit, BaseException)

    def test_installer_deux_fois_reste_sans_effet_de_bord(self, handlers_restaures):
        advisor_loop._install_stop_handlers()
        premier = signal.getsignal(signal.SIGTERM)
        advisor_loop._install_stop_handlers()

        assert callable(signal.getsignal(signal.SIGTERM))
        assert premier is not signal.SIG_DFL
