import unittest


class TestSecurityPermissions(unittest.TestCase):
    # CI-00B (Phase 4): l'ancien test_no_world_read_access vérifiait que des
    # fichiers *versionnés dans git* n'étaient pas world-readable. C'est un
    # invariant structurellement intestable ici : `git checkout` restaure
    # systématiquement les fichiers en 0644, quel que soit leur contenu —
    # git ne transporte pas de permissions restrictives. L'invariant de
    # sécurité réel (les secrets runtime ne doivent jamais être lisibles par
    # d'autres utilisateurs) est désormais testé contre le mécanisme qui
    # matérialise ces secrets sur disque :
    # scripts/confidential_files_perms.py, couvert par
    # tests/test_confidential_files_perms_hardening.py.

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
