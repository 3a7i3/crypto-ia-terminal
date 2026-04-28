import os
import unittest

SENSITIVE_FILES = [
    "core/quant/logging_alerts.py",  # contient potentiellement des credentials
    "strategy_factory_config.ini",  # config utilisateur
    "results/best_strategies_cross_world.json",  # résultats sensibles
]


class TestSecurityPermissions(unittest.TestCase):
    def test_no_world_read_access(self):
        # Vérifie que les fichiers sensibles ne sont pas world-readable
        for f in SENSITIVE_FILES:
            if os.path.exists(f):
                mode = os.stat(f).st_mode
                # 0o004 = world read, 0o002 = world write
                self.assertFalse(mode & 0o004, f"{f} est world-readable !")
                self.assertFalse(mode & 0o002, f"{f} est world-writable !")

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
