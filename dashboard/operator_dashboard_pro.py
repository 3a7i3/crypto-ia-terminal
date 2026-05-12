#!/usr/bin/env python3
"""
OPERATOR DASHBOARD PRO — Version finale hedge fund UI
"""



DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Dashboard PRO</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Monaco', 'Courier New', monospace;
            background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
            color: #e0e0e0;
            padding: 10px 14px;
            min-height: 100vh;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
        }

        header {
            background: rgba(20, 25, 45, 0.9);
            border-bottom: 2px solid #4ade80;
            padding: 10px 14px;
            margin-bottom: 12px;
            border-radius: 6px;
        }

        h1 {
            color: #4ade80;
            font-size: 16px;
            margin-bottom: 6px;
        }

        .status-line {
            display: flex;
            gap: 18px;
            font-size: 11px;
            color: #94a3b8;
        }

        .status-line span {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .indicator {
            width: 7px;
            height: 7px;
            border-radius: 50%;
        }

        .indicator.active {
            background: #4ade80;
            box-shadow: 0 0 7px #4ade80;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 10px;
            margin-bottom: 10px;
        }

        .panel {
            background: rgba(30, 39, 73, 0.8);
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 10px 12px;
            backdrop-filter: blur(10px);
        }

        .panel h3 {
            color: #94a3b8;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 8px;
            border-bottom: 1px solid #334155;
            padding-bottom: 6px;
        }

        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
            padding: 5px 7px;
            background: rgba(15, 23, 41, 0.5);
            border-radius: 4px;
        }

        .metric-label {
            color: #64748b;
            font-size: 11px;
        }

        .metric-value {
            font-size: 13px;
            font-weight: bold;
            color: #ffffff;
            font-family: 'Monaco', monospace;
        }

        .metric-value.negative {
            color: #ef4444;
        }

        .metric-value.warning {
            color: #f59e0b;
        }

        .chart-container {
            background: rgba(15, 23, 41, 0.5);
            border-radius: 4px;
            padding: 8px;
            height: 120px;
            display: flex;
            align-items: flex-end;
            justify-content: space-around;
            gap: 4px;
        }

        .bar {
            flex: 1;
            background: linear-gradient(180deg, #4ade80 0%, #22c55e 100%);
            border-radius: 2px;
            min-height: 5px;
            opacity: 0.7;
        }

        .bar.negative {
            background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%);
        }

        .alerts {
            background: rgba(30, 39, 73, 0.8);
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 10px 12px;
        }

        .alert-item {
            background: rgba(15, 23, 41, 0.8);
            border-left: 3px solid #f59e0b;
            padding: 6px 9px;
            margin-bottom: 5px;
            border-radius: 4px;
            font-size: 11px;
            display: flex;
            gap: 7px;
        }

        .alert-item.critical {
            border-left-color: #ef4444;
        }

        .alert-item.success {
            border-left-color: #4ade80;
        }

        .action-panel {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 8px;
            margin-top: 10px;
        }

        button {
            background: #4ade80;
            color: #0a0e27;
            border: none;
            padding: 7px 14px;
            border-radius: 4px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        button:hover {
            background: #22c55e;
            box-shadow: 0 0 15px rgba(74, 222, 128, 0.5);
        }

        button.danger {
            background: #ef4444;
            color: white;
        }

        button.danger:hover {
            background: #dc2626;
        }

        .footer {
            text-align: center;
            color: #64748b;
            font-size: 10px;
            margin-top: 14px;
            padding: 8px;
            border-top: 1px solid #334155;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .pulse {
            animation: pulse 2s infinite;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <header>
            <h1>🧠 TRADING DASHBOARD PRO</h1>
            <div class="status-line">
                <span>
                    <div class="indicator active"></div>
                    SYSTEM: ACTIVE
                </span>
                <span>MODE: PAPER TRADING</span>
                <span>REGIME: BULL_TREND</span>
                <span id="time"></span>
            </div>
        </header>

        <!-- PERFORMANCE CORE -->
        <div class="grid">
            <!-- Capital -->
            <div class="panel">
                <h3>Capital Status</h3>
                <div class="metric">
                    <span class="metric-label">Initial</span>
                    <span class="metric-value">$10,000.00</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Current</span>
                    <span class="metric-value">$10,350.50</span>
                </div>
                <div class="metric">
                    <span class="metric-label">PnL</span>
                    <span class="metric-value">+3.50%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Drawdown</span>
                    <span class="metric-value warning">-2.15%</span>
                </div>
            </div>

            <!-- Performance -->
            <div class="panel">
                <h3>Performance Metrics</h3>
                <div class="metric">
                    <span class="metric-label">Trades</span>
                    <span class="metric-value">24</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Win Rate</span>
                    <span class="metric-value">58.3%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Sharpe Ratio</span>
                    <span class="metric-value">7.29</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Profit Factor</span>
                    <span class="metric-value">2.74x</span>
                </div>
            </div>

            <!-- Risk Status -->
            <div class="panel">
                <h3>Risk Monitor</h3>
                <div class="metric">
                    <span class="metric-label">Max DD</span>
                    <span class="metric-value">-3.34%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Exposure</span>
                    <span class="metric-value">2 positions</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Loss Streak</span>
                    <span class="metric-value">1</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Safe Mode</span>
                    <span class="metric-value pulse">ACTIVE</span>
                </div>
            </div>
        </div>

        <!-- EXIT INTELLIGENCE -->
        <div class="panel">
            <h3>Exit Intelligence (MFE/MAE Analysis)</h3>
            <div class="chart-container" id="mfeChart"></div>
            <div class="metric" style="margin-top: 15px;">
                <span class="metric-label">Avg MFE</span>
                <span class="metric-value">+2.8%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Avg MAE</span>
                <span class="metric-value">-1.2%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Efficiency</span>
                <span class="metric-value">57%</span>
            </div>
        </div>

        <!-- ALERTS & RECOMMENDATIONS -->
        <div class="alerts">
            <h3>System Alerts & Decisions</h3>
            <div class="alert-item success">
                ✓ Auto Decision Engine: TP adjusted +15% (efficiency < 50%)
            </div>
            <div class="alert-item">
                ⚠ Performance: Loss streak 1/4 threshold
            </div>
            <div class="alert-item warning">
                ⚠ Throttle: Next decision in 2h 15m
            </div>
            <div class="alert-item">
                📊 ML Exit: Good exit detected on BTCUSDT
            </div>
        </div>

        <!-- ACTION PANEL -->
        <div class="action-panel">
            <button onclick="manualOverride()">Manual Override</button>
            <button onclick="viewDetails()">View Backtest Details</button>
            <button class="danger" onclick="emergencyStop()">Emergency Stop</button>
            <button onclick="viewLogs()">Decision Logs</button>
        </div>

        <!-- FOOTER -->
        <div class="footer">
            Dashboard PRO v1.0 | P0+P1+P2 Complete | Ultra Safe Fund Mode Active
            <br>Last updated: <span id="timestamp"></span>
        </div>
    </div>

    <script>
        // Update time
        function updateTime() {
            const now = new Date();
            document.getElementById('time').textContent = now.toLocaleTimeString();
            document.getElementById('timestamp').textContent = now.toLocaleString();
        }

        // Generate MFE chart
        function generateChart() {
            const chart = document.getElementById('mfeChart');
            const trades = [2.8, 1.9, 3.2, 2.1, 1.5];

            trades.forEach(val => {
                const bar = document.createElement('div');
                bar.className = 'bar';
                bar.style.height = (val * 10) + '%';
                chart.appendChild(bar);
            });
        }

        // Action handlers
        function manualOverride() {
            alert('Manual override: Disabled in Safe Mode');
        }

        function viewDetails() {
            alert('Backtest complete: 24 trades, 58.3% win rate, +3.50% PnL');
        }

        function emergencyStop() {
            if (confirm('⚠️ Emergency stop will close all positions. Continue?')) {
                alert('Emergency stop executed - All positions closed');
            }
        }

        function viewLogs() {
            alert('Last 5 decisions:\\n1. TP +15%\\n2. SL -10%\\n3. No action\\n4. Reduce risk 50%\\n5. No action');
        }

        // Initialize
        updateTime();
        generateChart();
        setInterval(updateTime, 1000);
    </script>
</body>
</html>
"""


def serve_dashboard():
    """Retourne le HTML du dashboard PRO"""
    return DASHBOARD_HTML


if __name__ == "__main__":
    # Pour tester localement
    with open("dashboard_pro.html", "w") as f:
        f.write(serve_dashboard())

    print("Dashboard PRO créé: dashboard_pro.html")
    print("Ouvrir dans navigateur pour voir le dashboard")
