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
    class TestMutationExtreme(unittest.TestCase):
        def test_neutralise(self):
            pass

else:
    # ...existing code...
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import unittest

    from run_strategy_factory import Genome, mutate

    class TestMutationExtreme(unittest.TestCase):
        def test_mutation_extreme(self):
            g = Genome()
            # On force tous les gènes à la borne inférieure
            for k, v in g.genes.items():
                if isinstance(v, float):
                    g.genes[k] = -1e9
            mutated = mutate(g, mutation_rate=1, intensity=1)
            # Tous les gènes bornés doivent être >= à la borne basse du GENE_SPACE
            from run_strategy_factory import GENE_SPACE

            for k, v in mutated.genes.items():
                if k in GENE_SPACE and isinstance(GENE_SPACE[k], tuple):
                    self.assertGreaterEqual(v, GENE_SPACE[k][0])
                    self.assertLessEqual(v, GENE_SPACE[k][1])


if __name__ == "__main__":
    unittest.main()
