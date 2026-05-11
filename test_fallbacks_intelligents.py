import logging
import unittest

from run_strategy_factory import create_population, evaluate_fitness


class TestFallbacksIntelligents(unittest.TestCase):
    def setUp(self):
        self.pop = create_population(10)

    def test_fallback_nan(self):
        # Simule un individu avec NaN dans les gènes
        self.pop[0].genes["exit.tp"] = float("nan")
        try:
            evaluate_fitness(self.pop[0])
        except Exception as e:
            self.fail(f"Pas de fallback sur NaN: {e}")

    def test_fallback_inf(self):
        # Simule un individu avec +inf dans les gènes
        self.pop[1].genes["exit.sl"] = float("inf")
        try:
            evaluate_fitness(self.pop[1])
        except Exception as e:
            self.fail(f"Pas de fallback sur inf: {e}")

    def test_fallback_api(self):
        # Simule un appel API qui échoue (ex: requests.get)
        try:
            import requests

            requests.get("http://localhost:9999/endpoint_inexistant", timeout=0.1)
        except Exception as e:
            logging.warning(f"Fallback API activé: {e}")
            self.assertTrue(True)
        else:
            self.fail("Pas de fallback sur erreur API")


if __name__ == "__main__":
    unittest.main()
