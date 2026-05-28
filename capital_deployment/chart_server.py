"""
capital_deployment/chart_server.py — Mini serveur Flask pour graphiques temps réel

Démarre un serveur HTTP léger qui expose :
  GET /              → page HTML avec Chart.js (PnL, positions, KPIs)
  GET /api/pnl       → historique PnL cumulatif [{ts, pnl, cumul}]
  GET /api/positions → positions ouvertes [{symbol, side, entry, current, pnl_pct, tp, sl, age_min, size_usd}]
  GET /api/kpis      → KPIs actuels {win_rate, sharpe, max_drawdown, total_trades, phase}
  GET /api/summary   → tout en un (pour polling unique)

Usage dans advisor_loop.py :
    from capital_deployment.chart_server import ChartServer
    chart = ChartServer.from_env(provider)
    chart.start()

Env vars :
  CHART_SERVER_HOST   (défaut: 0.0.0.0)
  CHART_SERVER_PORT   (défaut: 8080)
  CHART_SERVER_URL    URL publique affichée dans /charts (ex: https://34.171.188.99:8080)
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.chart_server")

_STATIC = Path(__file__).parent / "static"


class ChartServer:
    """
    Serveur HTTP minimal (stdlib uniquement) exposant les données du bot
    sous forme d'API JSON + page HTML Chart.js.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        get_trades: Optional[Callable[[], Any]] = None,
        get_positions: Optional[Callable[[], Any]] = None,
        get_kpis: Optional[Callable[[], Any]] = None,
        get_phase: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._host = host
        self._port = port
        self.get_trades = get_trades
        self.get_positions = get_positions
        self.get_kpis = get_kpis
        self.get_phase = get_phase
        self._server: Optional[HTTPServer] = None

    @classmethod
    def from_env(cls, provider: Any) -> "ChartServer":
        return cls(
            host=os.getenv("CHART_SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("CHART_SERVER_PORT", "8080")),
            get_trades=getattr(provider, "get_trades", None),
            get_positions=getattr(provider, "get_positions", None),
            get_kpis=getattr(provider, "get_kpis", None),
            get_phase=getattr(provider, "get_phase", None),
        )

    def start(self) -> None:
        server = self
        _static = _STATIC

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # silence access logs
                pass

            def _json(self, data: Any) -> None:
                body = json.dumps(data, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _html(self, body: bytes) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _404(self) -> None:
                self.send_response(404)
                self.end_headers()

            def do_GET(self):
                p = self.path.split("?")[0]

                if p in ("/", "/index.html"):
                    html_path = _static / "index.html"
                    if html_path.exists():
                        self._html(html_path.read_bytes())
                    else:
                        self._html(_inline_html().encode("utf-8"))
                    return

                if p == "/api/pnl":
                    self._json(_build_pnl(server))
                elif p == "/api/positions":
                    self._json(_build_positions(server))
                elif p == "/api/kpis":
                    self._json(_build_kpis(server))
                elif p == "/api/summary":
                    self._json(
                        {
                            "pnl": _build_pnl(server),
                            "positions": _build_positions(server),
                            "kpis": _build_kpis(server),
                            "ts": time.time(),
                        }
                    )
                else:
                    self._404()

        _STATIC.mkdir(parents=True, exist_ok=True)
        self._server = HTTPServer((self._host, self._port), _Handler)
        t = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="ChartSrv"
        )
        t.start()
        _log.info("[ChartServer] Demarre sur http://%s:%s", self._host, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()


# ── Builders ──────────────────────────────────────────────────────────────────


def _build_pnl(srv: ChartServer) -> list[dict]:
    try:
        trades = srv.get_trades() if srv.get_trades else None
        if not trades:
            return []
        cumul = 0.0
        out = []
        for t in trades:
            pnl = float(t.get("pnl", 0))
            cumul += pnl
            ts_ = float(t.get("ts", t.get("closed_at", 0)))
            out.append(
                {
                    "ts": ts_,
                    "pnl": round(pnl, 4),
                    "cumul": round(cumul, 4),
                    "symbol": t.get("symbol", ""),
                    "side": t.get("side", ""),
                }
            )
        return out
    except Exception as exc:
        _log.debug("[ChartServer] pnl error: %s", exc)
        return []


def _build_positions(srv: ChartServer) -> list[dict]:
    try:
        pos = srv.get_positions() if srv.get_positions else None
        if not pos:
            return []
        result = []
        for p in pos:
            entry = float(p.get("entry", p.get("entry_price", 0)))
            cur = float(p.get("current", p.get("current_price", 0)))
            dist = (cur - entry) / entry * 100 if entry > 0 else 0
            result.append(
                {
                    "symbol": p.get("symbol", "?"),
                    "side": p.get("side", "?"),
                    "entry": round(entry, 6),
                    "current": round(cur, 6),
                    "dist_pct": round(dist, 3),
                    "pnl_usd": round(float(p.get("pnl_usd", 0)), 2),
                    "pnl_pct": round(float(p.get("pnl_pct", 0)), 2),
                    "tp": round(float(p.get("tp", 0)), 6),
                    "sl": round(float(p.get("sl", 0)), 6),
                    "size_usd": round(float(p.get("size_usd", 0)), 2),
                    "age_min": round(float(p.get("age_min", 0)), 1),
                    "volatility": round(float(p.get("volatility", 0)), 4),
                    "regime": p.get("regime", ""),
                }
            )
        return result
    except Exception as exc:
        _log.debug("[ChartServer] positions error: %s", exc)
        return []


def _build_kpis(srv: ChartServer) -> dict:
    try:
        kpis = srv.get_kpis() if srv.get_kpis else None
        phase = srv.get_phase() if srv.get_phase else "?"
        if not kpis:
            return {"phase": phase}
        return {
            "phase": phase,
            "win_rate": round(float(getattr(kpis, "win_rate", 0)) * 100, 1),
            "sharpe": round(float(getattr(kpis, "sharpe", 0)), 3),
            "max_drawdown": round(float(getattr(kpis, "max_drawdown", 0)) * 100, 2),
            "current_dd": round(float(getattr(kpis, "current_drawdown", 0)) * 100, 2),
            "total_trades": int(getattr(kpis, "total_trades", 0)),
            "days_elapsed": round(float(getattr(kpis, "days_elapsed", 0)), 1),
        }
    except Exception as exc:
        _log.debug("[ChartServer] kpis error: %s", exc)
        return {}


# ── Page HTML inline (fallback si static/index.html absent) ───────────────────


def _inline_html() -> str:
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Crypto AI — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', monospace; font-size: 13px; }
  header { background: #161b22; padding: 12px 20px; border-bottom: 1px solid #30363d;
           display: flex; justify-content: space-between; align-items: center; }
  h1 { font-size: 16px; color: #58a6ff; }
  #status { font-size: 11px; color: #8b949e; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 16px; padding: 16px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .card h2 { font-size: 12px; color: #8b949e; margin-bottom: 12px; text-transform: uppercase; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
  .kpi { background: #0d1117; border-radius: 6px; padding: 10px; text-align: center; }
  .kpi .val { font-size: 20px; font-weight: bold; }
  .kpi .lbl { font-size: 10px; color: #8b949e; margin-top: 2px; }
  .green { color: #3fb950; } .red { color: #f85149; } .blue { color: #58a6ff; } .yellow { color: #d29922; }
  table { width: 100%; border-collapse: collapse; }
  td, th { padding: 6px 8px; text-align: left; border-bottom: 1px solid #21262d; font-size: 11px; }
  th { color: #8b949e; font-weight: normal; }
  .pos-long  { color: #3fb950; } .pos-short { color: #f85149; }
  canvas { max-height: 200px; }
  .phase-badge { background: #1f6feb; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
</style>
</head>
<body>
<header>
  <div style="display:flex;align-items:center;gap:12px">
    <h1>Crypto AI Terminal</h1>
    <span id="phase-badge" class="phase-badge">—</span>
  </div>
  <span id="status">connexion...</span>
</header>

<div class="grid">
  <!-- KPIs -->
  <div class="card" style="grid-column:1/-1">
    <h2>Performance</h2>
    <div class="kpis">
      <div class="kpi"><div class="val green" id="kpi-wr">—</div><div class="lbl">Win Rate</div></div>
      <div class="kpi"><div class="val blue"  id="kpi-sharpe">—</div><div class="lbl">Sharpe</div></div>
      <div class="kpi"><div class="val red"   id="kpi-dd">—</div><div class="lbl">Max DD</div></div>
      <div class="kpi"><div class="val"       id="kpi-trades">—</div><div class="lbl">Trades</div></div>
      <div class="kpi"><div class="val"       id="kpi-cumul">—</div><div class="lbl">PnL cumulatif</div></div>
      <div class="kpi"><div class="val"       id="kpi-days">—</div><div class="lbl">Jours</div></div>
    </div>
  </div>

  <!-- PnL Chart -->
  <div class="card" style="grid-column:span 2">
    <h2>PnL Cumulatif</h2>
    <canvas id="pnl-chart"></canvas>
  </div>

  <!-- Positions -->
  <div class="card" style="grid-column:1/-1">
    <h2>Positions ouvertes</h2>
    <div id="positions-empty" style="color:#8b949e;font-size:12px">Aucune position ouverte</div>
    <table id="positions-table" style="display:none">
      <thead>
        <tr>
          <th>Symbole</th><th>Side</th><th>Entry</th><th>Actuel</th>
          <th>Dist%</th><th>PnL</th><th>TP</th><th>SL</th>
          <th>Vol $</th><th>Duree</th><th>Volatilite</th>
        </tr>
      </thead>
      <tbody id="positions-body"></tbody>
    </table>
  </div>
</div>

<script>
const REFRESH = 5000; // ms
let pnlChart = null;
let lastTs = 0;

function fmt(n, dec=2) { return n == null ? '—' : Number(n).toFixed(dec); }
function fmtAge(min) {
  if (!min) return '—';
  if (min >= 60) return Math.floor(min/60)+'h'+String(Math.floor(min%60)).padStart(2,'0')+'m';
  return Math.floor(min)+'m';
}
function colorClass(v) { return v > 0 ? 'green' : v < 0 ? 'red' : ''; }

async function fetchSummary() {
  try {
    const r = await fetch('/api/summary');
    const d = await r.json();
    renderKpis(d.kpis, d.pnl);
    renderPnl(d.pnl);
    renderPositions(d.positions);
    lastTs = d.ts;
    document.getElementById('status').textContent =
      'Mis à jour ' + new Date().toLocaleTimeString('fr-FR');
  } catch(e) {
    document.getElementById('status').textContent = 'Erreur connexion';
  }
}

function renderKpis(kpis, pnl) {
  if (!kpis) return;
  document.getElementById('phase-badge').textContent = kpis.phase || '—';
  document.getElementById('kpi-wr').textContent = (kpis.win_rate ?? '—') + '%';
  document.getElementById('kpi-sharpe').textContent = fmt(kpis.sharpe, 3);
  const dd = kpis.max_drawdown;
  const ddEl = document.getElementById('kpi-dd');
  ddEl.textContent = '-' + fmt(dd) + '%';
  ddEl.className = 'val ' + (dd > 5 ? 'red' : dd > 2 ? 'yellow' : 'green');
  document.getElementById('kpi-trades').textContent = kpis.total_trades ?? '—';
  document.getElementById('kpi-days').textContent = fmt(kpis.days_elapsed, 1) + 'j';
  if (pnl && pnl.length) {
    const cumul = pnl[pnl.length-1].cumul;
    const el = document.getElementById('kpi-cumul');
    el.textContent = (cumul >= 0 ? '+' : '') + '$' + fmt(cumul);
    el.className = 'val ' + colorClass(cumul);
  }
}

function renderPnl(data) {
  if (!data || !data.length) return;
  const labels = data.map((d,i) => {
    if (!d.ts) return '#'+i;
    const dt = new Date(d.ts * 1000);
    return dt.toLocaleDateString('fr-FR',{month:'short',day:'numeric'})+' '+
           dt.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
  });
  const values = data.map(d => d.cumul);
  const color  = values[values.length-1] >= 0 ? '#3fb950' : '#f85149';

  if (!pnlChart) {
    const ctx = document.getElementById('pnl-chart').getContext('2d');
    pnlChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'PnL cumulatif ($)',
          data: values,
          borderColor: color,
          backgroundColor: color + '18',
          fill: true,
          tension: 0.3,
          pointRadius: data.length > 40 ? 0 : 3,
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8b949e', maxTicksLimit: 8, font:{size:10} }, grid: { color: '#21262d' } },
          y: { ticks: { color: '#8b949e', font:{size:10} }, grid: { color: '#21262d' } }
        }
      }
    });
  } else {
    pnlChart.data.labels = labels;
    pnlChart.data.datasets[0].data = values;
    pnlChart.data.datasets[0].borderColor = color;
    pnlChart.data.datasets[0].backgroundColor = color + '18';
    pnlChart.update('none');
  }
}

function renderPositions(data) {
  const tbody = document.getElementById('positions-body');
  const empty = document.getElementById('positions-empty');
  const table = document.getElementById('positions-table');
  tbody.innerHTML = '';
  if (!data || !data.length) {
    empty.style.display = '';
    table.style.display = 'none';
    return;
  }
  empty.style.display = 'none';
  table.style.display = '';
  data.forEach(p => {
    const side  = p.side.toUpperCase();
    const sc    = side === 'LONG' ? 'pos-long' : 'pos-short';
    const pnlC  = colorClass(p.pnl_usd);
    const distC = colorClass(p.dist_pct);
    tbody.insertAdjacentHTML('beforeend', `<tr>
      <td><b>${p.symbol}</b></td>
      <td class="${sc}">${side}</td>
      <td>$${fmt(p.entry,4)}</td>
      <td>$${fmt(p.current,4)}</td>
      <td class="${distC}">${p.dist_pct>0?'+':''}${fmt(p.dist_pct,2)}%</td>
      <td class="${pnlC}">${p.pnl_usd>=0?'+':''}$${fmt(p.pnl_usd)}</td>
      <td style="color:#3fb950">${p.tp ? '$'+fmt(p.tp,4) : '—'}</td>
      <td style="color:#f85149">${p.sl ? '$'+fmt(p.sl,4) : '—'}</td>
      <td>$${fmt(p.size_usd)}</td>
      <td>${fmtAge(p.age_min)}</td>
      <td>${p.volatility ? fmt(p.volatility,4) : '—'}</td>
    </tr>`);
  });
}

fetchSummary();
setInterval(fetchSummary, REFRESH);
</script>
</body>
</html>"""
