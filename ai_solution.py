```html
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cockpit Operator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            background-color: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }

        .status-indicator {
            font-size: 1.2em;
            color: #666;
            margin-bottom: 10px;
        }

        .section {
            background-color: #fff;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .section-title {
            font-size: 1.1em;
            color: #333;
            margin-bottom: 10px;
            font-weight: bold;
        }

        .key-metrics {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 15px;
        }

        .metric-item {
            background-color: #f8f8f8;
            padding: 10px;
            border-radius: 5px;
            max-width: 200px;
        }

        .metric-title {
            font-size: 1em;
            color: #666;
            margin-bottom: 5px;
        }

        .metric-value {
            font-size: 1.1em;
            color: #333;
        }

        .info-box {
            background-color: #f8f8f8;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }

        .info-title {
            font-size: 1em;
            color: #666;
            margin-bottom: 10px;
        }

        .status-indicator {
            font-size: 1.2em;
            color: #666;
            margin-bottom: 10px;
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }

            .section {
                padding: 10px;
            }

            .metric-item {
                max-width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Cockpit Operator</h1>
            <div class="status-indicator">État global: Actif</div>
        </div>

        <div class="section">
            <div class="section-title">Vue d'ensemble</div>
            <div class="key-metrics">
                <div class="metric-item">
                    <div class="metric-title">Mode actif</div>
                    <div class="metric-value">PAPER</div>
                </div>
                <div class="metric-item">
                    <div class="metric-title">Epoch active</div>
                    <div class="metric-value">#315</div>
                </div>
                <div class="metric-item">
                    <div class="metric-title">Positions ouvertes</div>
                    <div class="metric-value">12</div>
                </div>
                <div class="metric-item">
                    <div class="metric-title">Capital libre</div>
                    <div class="metric-value">€5,000</div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">État du système</div>
            <div class="info-box">
                <div class="info-title">Dernier événement PPL</div>
                <div class="info-content">Aucun événement depuis 30 minutes</div>
            </div>
            <div class="info-box">
                <div class="info-title">État du burn-in</div>
                <div class="info-content">Actif: #282</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Données scientifiques</div>
            <div class="info-box">
                <div class="info-title">PnL total</div>
                <div class="info-content">€1,234</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Informations détaillées</div>
            <div class="info-box">
                <div class="info-title">Dernière mise à jour</div>
                <div class="info-content">2026-09-30 14:30</div>
            </div>
        </div>
    </div>
</body>
</html>
```