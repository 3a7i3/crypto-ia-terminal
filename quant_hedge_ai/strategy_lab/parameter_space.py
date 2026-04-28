# parameter_space.py
class ParameterSpace:
    def __init__(self, strategy_name):
        self.strategy_name = strategy_name

    def get_grid(self):
        """
        Retourne une grille de paramètres simple selon la stratégie.
        """
        if self.strategy_name == "momentum":
            return [
                {"threshold": 0.01},
                {"threshold": 0.02},
                {"threshold": 0.03},
            ]
        elif self.strategy_name == "breakout":
            return [
                {"window": 10},
                {"window": 20},
            ]
        else:
            return [{}]
