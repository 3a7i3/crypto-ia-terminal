# generator.py
class StrategyGenerator:
    def __init__(self, features, templates):
        self.features = features
        self.templates = templates

    def generate(self):
        """
        Génère toutes les combinaisons (feature, template).
        """
        return [(f, t) for f in self.features for t in self.templates]
