"""
P1 — DASHBOARD WEBSOCKET — Serveur live updates
FastAPI + WebSocket pour updates temps réel
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from datetime import datetime
from typing import Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DashboardManager:
    """Gestionnaire de l'état du dashboard et des updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.current_metrics: Dict[str, Any] = {
            "timestamp": None,
            "equity": 10000,
            "daily_pnl": 0,
            "total_trades": 0,
            "winrate": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "profit_factor": 0.0,
            "open_positions": 0,
            "regime": "range",
            "alerts": [],
            "recommendations": []
        }

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connecte. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client deconnecte. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Envoie un message à tous les clients connectes"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Erreur envoi: {e}")
                disconnected.append(connection)

        # Nettoyer les connexions mortes
        for conn in disconnected:
            self.disconnect(conn)

    async def update_metrics(self, metrics: Dict[str, Any]):
        """Met à jour les métriques et broadcast"""
        self.current_metrics.update(metrics)
        self.current_metrics["timestamp"] = datetime.now().isoformat()

        await self.broadcast({
            "type": "metrics_update",
            "data": self.current_metrics
        })

    async def send_alert(self, alert_type: str, message: str, severity: str = "warning"):
        """Envoie une alerte"""
        alert = {
            "type": "alert",
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat()
        }
        self.current_metrics["alerts"].append(alert)
        await self.broadcast(alert)

    async def send_recommendation(self, recommendation: str):
        """Envoie une recommandation"""
        rec = {
            "type": "recommendation",
            "message": recommendation,
            "timestamp": datetime.now().isoformat()
        }
        self.current_metrics["recommendations"].append(rec)
        await self.broadcast(rec)

    def get_current_state(self) -> Dict[str, Any]:
        """Retourne l'état actuel pour nouveau client"""
        return {
            "type": "current_state",
            "data": self.current_metrics
        }


# Instance globale
dashboard_manager = DashboardManager()


# FastAPI app
app = FastAPI(title="Trading Dashboard WebSocket")


@app.get("/")
async def get_dashboard():
    """Serve le dashboard HTML"""
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Dashboard Live</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Courier New', monospace;
            background: #0a0e27;
            color: #e0e0e0;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #4ade80;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .metric-card {
            background: #1e2749;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }

        .metric-card h3 {
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }

        .metric-value {
            font-size: 28px;
            font-weight: bold;
            color: #4ade80;
            font-family: 'Courier New', monospace;
        }

        .metric-value.negative {
            color: #ef4444;
        }

        .metric-value.neutral {
            color: #f59e0b;
        }

        .alerts {
            background: #1e2749;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            max-height: 300px;
            overflow-y: auto;
        }

        .alerts h2 {
            margin-bottom: 15px;
            color: #4ade80;
        }

        .alert-item {
            background: #0f1729;
            padding: 10px;
            margin-bottom: 10px;
            border-left: 3px solid #f59e0b;
            border-radius: 4px;
            font-size: 12px;
        }

        .alert-item.critical {
            border-left-color: #ef4444;
        }

        .alert-item.success {
            border-left-color: #4ade80;
        }

        .status {
            text-align: center;
            font-size: 12px;
            color: #64748b;
        }

        .status.connected {
            color: #4ade80;
        }

        .status.disconnected {
            color: #ef4444;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Dashboard Live</h1>

        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Equity</h3>
                <div class="metric-value" id="equity">$10,000.00</div>
            </div>

            <div class="metric-card">
                <h3>Daily PnL</h3>
                <div class="metric-value" id="daily_pnl">$0.00</div>
            </div>

            <div class="metric-card">
                <h3>Win Rate</h3>
                <div class="metric-value" id="winrate">0%</div>
            </div>

            <div class="metric-card">
                <h3>Profit Factor</h3>
                <div class="metric-value" id="profit_factor">1.0</div>
            </div>

            <div class="metric-card">
                <h3>Sharpe Ratio</h3>
                <div class="metric-value" id="sharpe_ratio">0.0</div>
            </div>

            <div class="metric-card">
                <h3>Max Drawdown</h3>
                <div class="metric-value" id="max_drawdown">0%</div>
            </div>

            <div class="metric-card">
                <h3>Open Positions</h3>
                <div class="metric-value" id="open_positions">0</div>
            </div>

            <div class="metric-card">
                <h3>Regime</h3>
                <div class="metric-value" id="regime">range</div>
            </div>
        </div>

        <div class="alerts">
            <h2>Alerts & Events</h2>
            <div id="alerts-list"></div>
        </div>

        <div class="status disconnected" id="status">
            Connection: Connecting...
        </div>
    </div>

    <script>
        const statusEl = document.getElementById('status');
        const alertsList = document.getElementById('alerts-list');

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = protocol + '//' + window.location.host + '/ws';
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            statusEl.textContent = 'Connection: Connected';
            statusEl.className = 'status connected';
            console.log('WebSocket connected');
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            statusEl.textContent = 'Connection: Error';
            statusEl.className = 'status disconnected';
        };

        ws.onclose = () => {
            statusEl.textContent = 'Connection: Disconnected';
            statusEl.className = 'status disconnected';
            console.log('WebSocket disconnected');

            // Reconnect after 3 seconds
            setTimeout(() => {
                location.reload();
            }, 3000);
        };

        function handleMessage(msg) {
            if (msg.type === 'current_state') {
                updateDashboard(msg.data);
            } else if (msg.type === 'metrics_update') {
                updateDashboard(msg.data);
            } else if (msg.type === 'alert') {
                addAlert(msg);
            } else if (msg.type === 'recommendation') {
                addRecommendation(msg);
            }
        }

        function updateDashboard(data) {
            document.getElementById('equity').textContent = '$' + data.equity.toLocaleString('en-US', {minimumFractionDigits: 2});

            const pnlEl = document.getElementById('daily_pnl');
            pnlEl.textContent = (data.daily_pnl >= 0 ? '+' : '') + '$' + data.daily_pnl.toLocaleString('en-US', {minimumFractionDigits: 2});
            pnlEl.className = 'metric-value' + (data.daily_pnl < 0 ? ' negative' : '');

            document.getElementById('winrate').textContent = (data.winrate * 100).toFixed(1) + '%';
            document.getElementById('profit_factor').textContent = data.profit_factor.toFixed(2);
            document.getElementById('sharpe_ratio').textContent = data.sharpe_ratio.toFixed(2);

            const ddEl = document.getElementById('max_drawdown');
            ddEl.textContent = (data.max_drawdown * 100).toFixed(2) + '%';
            ddEl.className = 'metric-value' + (data.max_drawdown > 0.15 ? ' negative' : '');

            document.getElementById('open_positions').textContent = data.open_positions;
            document.getElementById('regime').textContent = data.regime;
        }

        function addAlert(alert) {
            const div = document.createElement('div');
            div.className = 'alert-item ' + alert.severity;
            const time = new Date(alert.timestamp).toLocaleTimeString();
            div.textContent = `[${time}] ${alert.message}`;
            alertsList.insertBefore(div, alertsList.firstChild);

            if (alertsList.children.length > 10) {
                alertsList.removeChild(alertsList.lastChild);
            }
        }

        function addRecommendation(rec) {
            addAlert({
                timestamp: rec.timestamp,
                message: 'REC: ' + rec.message,
                severity: 'success'
            });
        }
    </script>
</body>
</html>
    """)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket pour les clients"""
    await dashboard_manager.connect(websocket)

    try:
        # Envoyer l'état actuel au nouveau client
        await websocket.send_json(dashboard_manager.get_current_state())

        # Garder la connexion active
        while True:
            data = await websocket.receive_text()
            logger.info(f"Message recu: {data}")

    except WebSocketDisconnect:
        dashboard_manager.disconnect(websocket)
        logger.info("Client deconnecte")


@app.post("/api/metrics")
async def post_metrics(metrics: Dict[str, Any]):
    """API pour mettre à jour les métriques"""
    await dashboard_manager.update_metrics(metrics)
    return {"status": "ok"}


@app.post("/api/alert")
async def post_alert(alert: Dict[str, Any]):
    """API pour envoyer une alerte"""
    await dashboard_manager.send_alert(
        alert_type=alert.get("type", "unknown"),
        message=alert.get("message", ""),
        severity=alert.get("severity", "warning")
    )
    return {"status": "ok"}


@app.get("/api/status")
async def get_status():
    """API pour obtenir le statut"""
    return {
        "connected_clients": len(dashboard_manager.active_connections),
        "current_metrics": dashboard_manager.current_metrics
    }


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("Dashboard WebSocket running on http://localhost:8000")
    print("="*70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
