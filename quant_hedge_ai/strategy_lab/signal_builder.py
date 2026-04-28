# signal_builder.py
class SignalBuilder:
    def __init__(self, template, params):
        self.template = template
        self.params = params

    def build(self, data):
        """
        Applique la logique du template (supposée être une string formatée) sur les données.
        Supporte :
        - 'IF var > threshold: BUY ELSE: HOLD'
        - 'IF var1 > threshold AND var2 < rsi_level: BUY ELSE: HOLD'
        Retourne une liste de signaux.
        """
        logic = self.template.inject_params(self.params)
        import re

        # Cas complexe : AND
        m = re.match(
            r"IF (\w+) > ([\d\.]+) AND (\w+) < ([\d\.]+): BUY ELSE: HOLD", logic
        )
        if m:
            var1, threshold1, var2, threshold2 = (
                m.group(1),
                float(m.group(2)),
                m.group(3),
                float(m.group(4)),
            )
            return [
                (
                    "BUY"
                    if (data[var1][i] > threshold1 and data[var2][i] < threshold2)
                    else "HOLD"
                )
                for i in range(len(data[var1]))
            ]
        # Cas simple
        m = re.match(r"IF (\w+) > ([\d\.]+): BUY ELSE: HOLD", logic)
        if m:
            var, threshold = m.group(1), float(m.group(2))
            return ["BUY" if v > threshold else "HOLD" for v in data[var]]
        raise ValueError("Format de logique non supporté")
