# ranker.py
class StrategyRanker:
    def __init__(self, weights):
        self.weights = weights  # {'sharpe': 0.4, 'drawdown': 0.3, ...}

    def rank(self, strategies_metrics):
        """
        Calcule un score pondéré pour chaque stratégie.
        strategies_metrics: list of dicts, chaque dict contient les métriques.
        Retourne une liste de tuples (index, score).
        """
        results = []
        for i, metrics in enumerate(strategies_metrics):
            score = 0.0
            for k, w in self.weights.items():
                score += metrics.get(k, 0) * w
            results.append((i, score))
        return results
