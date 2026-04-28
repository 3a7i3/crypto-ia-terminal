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
    class TestGenome(unittest.TestCase):
        def test_neutralise(self):
            pass

else:
    # ...existing code...
    import os
    import sys
    import unittest

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import uuid

    from run_strategy_factory import Genome, crossover

    class TestGenome(unittest.TestCase):
        def test_genome_id_unique(self):
            g1 = Genome()
            g2 = Genome()
            self.assertNotEqual(g1.id, g2.id)

        def test_genome_id_length(self):
            g1 = Genome()
            self.assertEqual(len(g1.id), 8)

        def test_crossover_parent_ids(self):
            p1 = Genome()
            p2 = Genome()
            child = crossover(p1, p2)
            self.assertEqual(child.parent_ids, [p1.id, p2.id])


if __name__ == "__main__":
    unittest.main()
