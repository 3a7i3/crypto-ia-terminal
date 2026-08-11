"""
Contrôles de sécurité statiques sur les fichiers sensibles du dépôt.

Note — un test `test_no_world_read_access` vérifiait ici que
`core/quant/logging_alerts.py` n'était pas world-readable. Il a été retiré :
git ne versionne que le bit exécutable, pas le bit de lecture. Toute copie
fraîche du dépôt applique l'umask du système (644 par défaut), donc ce test
échouait systématiquement en CI et sur tout clone, et aucun `chmod` committé
ne pouvait le satisfaire.

Le besoin qu'il exprimait — ne pas exposer de credentials via ce module —
reste couvert par `test_no_hardcoded_secrets` ci-dessous, qui inspecte le
contenu et non les permissions.

Une vérification des permissions au déploiement a du sens, mais sa place est
dans `scripts/vps_healthcheck.sh`, sur la machine réelle — pas dans un test
exécuté sur un checkout git.
"""

import unittest


class TestSecurityPermissions(unittest.TestCase):
    def test_no_hardcoded_secrets(self):
        # Vérifie qu'aucune valeur de secret n'est en dur dans logging_alerts.py
        with open("core/quant/logging_alerts.py", encoding="utf-8") as f:
            content = f.read().lower()
            # On ne veut pas de password/token/secret en dur (ex: = "..." ou = '...')
            self.assertNotIn('password"', content, "Mot de passe en dur détecté !")
            self.assertNotIn("password'", content, "Mot de passe en dur détecté !")
            self.assertNotIn('token"', content, "Token en dur détecté !")
            self.assertNotIn("token'", content, "Token en dur détecté !")
            self.assertNotIn('secret"', content, "Secret en dur détecté !")
            self.assertNotIn("secret'", content, "Secret en dur détecté !")


if __name__ == "__main__":
    unittest.main()
