import unittest

missing = []
try:
    import pandas
except ImportError:
    missing.append("pandas")
try:
    import pytest
except ImportError:
    missing.append("pytest")
if missing:

    @unittest.skip(f"Modules manquants : {', '.join(missing)}")
    class TestRobustness(unittest.TestCase):
        def test_neutralise(self):
            pass

else:
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import unittest

    from run_strategy_factory import Genome, apply_extinction

    class TestRobustness(unittest.TestCase):
        def test_extinction_total(self):
            # Cas où tous les individus sont d'une espèce rare (moins que min_species_size)
            pop = [Genome({"entry.type": "rare"}) for _ in range(3)]
            survivors = apply_extinction(pop, min_species_size=5)
            self.assertEqual(
                len(survivors),
                0,
                "Tous les individus doivent être éliminés si l'espèce est trop rare.",
            )

        def test_population_vide(self):
            # Cas d'une population vide
            survivors = apply_extinction([], min_species_size=5)
            self.assertEqual(
                survivors,
                [],
                "La fonction doit retourner une liste vide si la population est vide.",
            )

        def test_csv_corrompu_nan_inf(self):
            import tempfile

            import numpy as np
            import pandas as pd

            # Création d'un CSV avec NaN et inf
            df = pd.DataFrame(
                {
                    "id": [1, 2],
                    "fitness": [np.nan, np.inf],
                    "species": ["A", "B"],
                    "exit.tp": [0.1, 0.2],
                    "exit.sl": [0.1, 0.2],
                }
            )
            with tempfile.NamedTemporaryFile(
                suffix=".csv", delete=False, mode="w", newline=""
            ) as tmp:
                df.to_csv(tmp.name, index=False)
                from test_validate_population_csv import validate_csv_file

                valid, msg = validate_csv_file(tmp.name)
                self.assertFalse(valid)
                self.assertIn("Valeurs manquantes", msg)
            # Création d'un CSV malformé
            with tempfile.NamedTemporaryFile(
                suffix=".csv", delete=False, mode="w", newline=""
            ) as tmp:
                tmp.write(
                    "id,fitness,species,exit.tp,exit.sl\n1,0.5,A,0.1,0.2\n2,0.6,B,0.1"
                )  # ligne incomplète
                tmp.flush()
                valid, msg = validate_csv_file(tmp.name)
                self.assertFalse(valid)
                self.assertIn("Erreur de lecture", msg)

    if __name__ == "__main__":
        unittest.main()
