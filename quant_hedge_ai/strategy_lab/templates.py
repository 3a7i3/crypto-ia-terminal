# templates.py
class StrategyTemplate:
    def __init__(self, name, logic):
        self.name = name
        self.logic = logic  # Fonction ou string à parser

    def inject_params(self, params):
        """
        Injecte les paramètres dans la logique du template (string format).
        Exemple : logic = 'IF momentum_14 > {threshold}: BUY ELSE: HOLD'
        params = {'threshold': 0.03}
        """
        return self.logic.format(**params)
