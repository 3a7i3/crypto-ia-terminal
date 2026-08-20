#!/usr/bin/env python3
"""dashboard_api.py — API + Dashboard CryptoRadar. LECTURE SEULE."""
from __future__ import annotations
import hashlib,hmac,json,os,secrets,time
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

PROJECT = Path(__file__).resolve().parent.parent
DP_DIR = Path(os.getenv("DP_LOG_DIR", str(PROJECT / "databases")))
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8050"))
app = FastAPI(title="CryptoRadar", docs_url=None, redoc_url=None)
_SECRET = secrets.token_hex(32)

def _make_token():
    ts = str(int(time.time()))
    sig = hmac.new(_SECRET.encode(), ts.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{ts}.{sig}"

def _verify_token(token):
    try:
        ts, sig = token.split(".")
        expected = hmac.new(_SECRET.encode(), ts.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected): return False
        return 0 <= time.time() - int(ts) < 86400 * 7
    except: return False

_LOGIN_HTML = '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0f1117;color:#e0e0e0;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh}.c{background:#1a1d27;padding:2rem;border-radius:12px;width:min(90vw,360px)}h2{margin-bottom:1rem;color:#3987e5}input{width:100%;padding:12px;border:1px solid #333;border-radius:8px;background:#0f1117;color:#fff;font-size:1rem;margin-bottom:1rem}button{width:100%;padding:12px;border:none;border-radius:8px;background:#2a78d6;color:#fff;font-size:1rem;cursor:pointer}.e{color:#e34948;font-size:.85rem;display:none}</style></head><body><div class="c"><h2>CryptoRadar</h2><p class="e" id="e">Mot de passe incorrect</p><form onsubmit="return d(event)"><input type="password" id="p" placeholder="Mot de passe" autofocus><button>Connexion</button></form></div><script>async function d(e){e.preventDefault();const r=await fetch("/login",{method:"POST",body:new URLSearchParams({password:document.getElementById("p").value})});if(r.ok)location.reload();else document.getElementById("e").style.display="block"}</script></body></html>'
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not DASHBOARD_PASSWORD: return await call_next(request)
        token = request.cookies.get("radar_session")
        if token and _verify_token(token): return await call_next(request)
        if request.url.path == "/login" and request.method == "POST":
            form = await request.form()
            if hmac.compare_digest(form.get("password",""), DASHBOARD_PASSWORD):
                resp = JSONResponse({"ok": True})
                resp.set_cookie("radar_session", _make_token(), max_age=604800, httponly=True, samesite="lax")
                return resp
            raise HTTPException(401)
        if request.url.path.startswith("/api/"): raise HTTPException(401)
        return HTMLResponse(_LOGIN_HTML)

app.add_middleware(AuthMiddleware)

def load_recent_packets(hours=24):
    now = datetime.utcnow()
    dates = set()
    for h in range(int(hours)+1):
        dates.add((now - timedelta(hours=h)).strftime("%Y-%m-%d"))
    packets = []
    for ds in sorted(dates):
        fp = DP_DIR / f"decision_packets_{ds}.jsonl"
        if not fp.exists(): continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: packets.append(json.loads(line))
                except: continue
    return packets

def compute_stats(packets, min_conf=0):
    by_sym = defaultdict(list)
    for p in packets:
        c = p.get("confidence",0)
        if c < min_conf: continue
        s = p.get("symbol","")
        if s: by_sym[s].append(p)
    results = []
    for sym, pks in by_sym.items():
        confs = [p.get("confidence",0) for p in pks]
        avg = sum(confs)/len(confs)
        sides = [p.get("side","") for p in pks]
        lo = sum(1 for s in sides if s in ("BUY","LONG"))
        sh = sum(1 for s in sides if s in ("SELL","SHORT"))
        if lo > sh: dom, pct = "LONG", lo/len(sides)*100
        elif sh > lo: dom, pct = "SHORT", sh/len(sides)*100
        else: dom, pct = "MIXED", 50.0
        regs = defaultdict(int)
        for p in pks: regs[p.get("regime","?")] += 1
        reg = max(regs, key=regs.get)
        lat = ([p for p in pks if p.get("entry_price")] or pks)[-1]
        results.append({"symbol":sym,"avg_confidence":round(avg,1),"max_confidence":max(confs),
            "n_signals":len(pks),"dominant_side":dom,"dominance_pct":round(pct,0),
            "regime":reg,"entry":lat.get("entry_price"),"sl":lat.get("stop_loss"),
            "tp":lat.get("take_profit"),"r_multiple":lat.get("r_multiple")})
    results.sort(key=lambda r: r["avg_confidence"], reverse=True)
    return results

def extract_signals(packets):
    best = {}
    for p in packets:
        e,sl,tp = p.get("entry_price"),p.get("stop_loss"),p.get("take_profit")
        if not e or not sl or not tp: continue
        sym,side = p.get("symbol","?"),p.get("side","?")
        k = f"{sym}:{side}"
        if side in ("BUY","LONG"):
            ri = (e-sl)/e*100 if e>0 else 0; re = (tp-e)/e*100 if e>0 else 0
        else:
            ri = (sl-e)/e*100 if e>0 else 0; re = (e-tp)/e*100 if e>0 else 0
        best[k] = {"symbol":sym,"side":side,"entry":e,"sl":sl,"tp":tp,
            "r_multiple":p.get("r_multiple"),"confidence":p.get("confidence",0),
            "regime":p.get("regime","?"),"risk_pct":round(ri,2),"reward_pct":round(re,2)}
    sigs = list(best.values())
    sigs.sort(key=lambda s: s["confidence"], reverse=True)
    return sigs

@app.get("/api/scan")
def api_scan(top:int=10, min_conf:float=65):
    pkts = load_recent_packets(24)
    st = compute_stats(pkts, min_conf)[:top]
    return {"data":st,"count":len(st),"timestamp":datetime.utcnow().isoformat()+"Z"}

@app.get("/api/signals")
def api_signals(hours:float=24, limit:int=30):
    pkts = load_recent_packets(hours)
    sg = extract_signals(pkts)[:limit]
    return {"data":sg,"count":len(sg),"timestamp":datetime.utcnow().isoformat()+"Z"}

@app.get("/api/symbol/{symbol}")
def api_symbol(symbol:str):
    pkts = load_recent_packets(24)
    q = symbol.upper()
    m = [p for p in pkts if q in p.get("symbol","").upper()]
    if not m: raise HTTPException(404)
    confs = [p.get("confidence",0) for p in m]
    sides = [p.get("side","") for p in m]
    lo = sum(1 for s in sides if s in ("BUY","LONG"))
    sh = sum(1 for s in sides if s in ("SELL","SHORT"))
    regs = defaultdict(int)
    for p in m: regs[p.get("regime","?")] += 1
    wl = [p for p in m if p.get("entry_price")]
    la = wl[-1] if wl else None
    return {"symbol":m[0].get("symbol",symbol),"n_signals":len(m),
        "avg_confidence":round(sum(confs)/len(confs),1),"max_confidence":max(confs),
        "longs":lo,"shorts":sh,"dominant_regime":max(regs,key=regs.get),
        "last_signal":{"side":la.get("side"),"entry":la.get("entry_price"),
        "sl":la.get("stop_loss"),"tp":la.get("take_profit"),
        "r_multiple":la.get("r_multiple")} if la else None}

@app.get("/api/status")
def api_status():
    now = datetime.utcnow()
    fp = DP_DIR / f"decision_packets_{now.strftime('%Y-%m-%d')}.jsonl"
    n,lt = 0,""
    if fp.exists():
        with open(fp,"r") as f:
            for line in f:
                if line.strip():
                    n += 1
                    try:
                        t = json.loads(line).get("created_at","")
                        if t: lt = t
                    except: pass
    dfs = sorted(DP_DIR.glob("decision_packets_*.jsonl"))
    ts = sum(f.stat().st_size for f in dfs)
    return {"packets_today":n,"last_packet":lt[:19] if lt else None,
        "dp_files":len(dfs),"dp_total_gb":round(ts/1e9,2)}
    confs = [p.get("confidence",0) for p in m]
    sides = [p.get("side","") for p in m]
    lo = sum(1 for s in sides if s in ("BUY","LONG"))
    sh = sum(1 for s in sides if s in ("SELL","SHORT"))
    regs = defaultdict(int)
    for p in m: regs[p.get("regime","?")] += 1
    wl = [p for p in m if p.get("entry_price")]
    la = wl[-1] if wl else None
    return {"symbol":m[0].get("symbol",symbol),"n_signals":len(m),
        "avg_confidence":round(sum(confs)/len(confs),1),"max_confidence":max(confs),
        "longs":lo,"shorts":sh,"dominant_regime":max(regs,key=regs.get),
        "last_signal":{"side":la.get("side"),"entry":la.get("entry_price"),
        "sl":la.get("stop_loss"),"tp":la.get("take_profit"),
        "r_multiple":la.get("r_multiple")} if la else None}

@app.get("/api/status")
def api_status():
    now = datetime.utcnow()
    fp = DP_DIR / f"decision_packets_{now.strftime('%Y-%m-%d')}.jsonl"
    n,lt = 0,""
    if fp.exists():
        with open(fp,"r") as f:
            for line in f:
                if line.strip():
                    n += 1
                    try:
                        t = json.loads(line).get("created_at","")
                        if t: lt = t
                    except: pass
    dfs = sorted(DP_DIR.glob("decision_packets_*.jsonl"))
    ts = sum(f.stat().st_size for f in dfs)
    return {"packets_today":n,"last_packet":lt[:19] if lt else None,
        "dp_files":len(dfs),"dp_total_gb":round(ts/1e9,2)}

def _load_live_positions():
    """Lit live_snapshot.json ecrit par advisor_loop chaque cycle."""
    fp = DP_DIR / "live_snapshot.json"
    if not fp.exists(): return []
    try: snap = json.loads(fp.read_text(encoding="utf-8"))
    except: return []
    return snap.get("positions",[]) or []

def _pnl_at_price(pos, price):
    """P&L hypothetique d'une position ouverte a un prix donne.
    LONG : (price - entry) / entry ; SHORT : (entry - price) / entry.
    Retourne (pnl_pct, pnl_usd) — pnl_usd base sur size_usd + leverage."""
    entry = float(pos.get("entry",0) or 0)
    if entry <= 0: return 0.0, 0.0
    side = str(pos.get("side","")).lower()
    lev = float(pos.get("leverage",1) or 1)
    size_usd = float(pos.get("size_usd",0) or 0)
    if side in ("long","buy"): pct = (price - entry) / entry
    elif side in ("short","sell"): pct = (entry - price) / entry
    else: return 0.0, 0.0
    return round(pct * 100, 4), round(pct * size_usd * lev, 2)

@app.get("/api/portfolio-impact")
def api_portfolio_impact(symbol:str="", price:float=0.0):
    """Impact d'un prix hypothetique sur les positions ouvertes.
    - symbol vide -> agrege sur toutes les positions
    - price=0 -> utilise le prix courant de chaque position (baseline)
    Observer strict (ADR-0007) : aucune decision n'est prise ici."""
    positions = _load_live_positions()
    if symbol:
        q = symbol.upper().replace("/","").replace("-","")
        positions = [p for p in positions if q in str(p.get("symbol","")).upper().replace("/","").replace("-","")]
    if not positions:
        return {"symbol":symbol or "all","price":price,"n_positions":0,
                "n_profit":0,"n_loss":0,"pct_profit":0.0,"pct_loss":0.0,
                "total_pnl_usd":0.0,"avg_pnl_pct":0.0,"positions":[]}
    details = []
    n_profit = n_loss = 0
    total_pnl_usd = sum_pnl_pct = 0.0
    for p in positions:
        use_price = price if price > 0 else float(p.get("current",p.get("entry",0)) or 0)
        pct, usd = _pnl_at_price(p, use_price)
        in_profit = pct > 0
        if in_profit: n_profit += 1
        else: n_loss += 1
        total_pnl_usd += usd
        sum_pnl_pct += pct
        details.append({
            "symbol":p.get("symbol",""),"side":p.get("side",""),
            "entry":p.get("entry"),"current":p.get("current"),
            "sl":p.get("sl"),"tp":p.get("tp"),
            "leverage":p.get("leverage",1),"size_usd":p.get("size_usd",0),
            "pnl_pct_at_price":pct,"pnl_usd_at_price":usd,"in_profit":in_profit,
        })
    n = len(positions)
    return {"symbol":symbol or "all","price":price,"n_positions":n,
            "n_profit":n_profit,"n_loss":n_loss,
            "pct_profit":round(100*n_profit/n,1),"pct_loss":round(100*n_loss/n,1),
            "total_pnl_usd":round(total_pnl_usd,2),
            "avg_pnl_pct":round(sum_pnl_pct/n,2),
            "positions":details,"timestamp":datetime.utcnow().isoformat()+"Z"}

@app.get("/api/portfolio-symbols")
def api_portfolio_symbols():
    """Liste les symboles ayant au moins une position ouverte (pour dropdown UI)."""
    positions = _load_live_positions()
    syms = sorted({str(p.get("symbol","")) for p in positions if p.get("symbol")})
    return {"data":syms,"count":len(syms)}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASH

_DASH = r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CryptoRadar</title><style>
:root{color-scheme:dark;--s0:#0f1117;--s1:#1a1d27;--s2:#242836;--tp:#fff;--ts:#c3c2b7;--tm:#7a7a6e;--bd:#2e3240;--lo:#0ca30c;--sh:#d03b3b;--ac:#2a78d6;--ah:#3987e5}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--s0);color:var(--tp);font-family:system-ui}
.hd{background:var(--s1);border-bottom:1px solid var(--bd);padding:12px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}
.hd h1{font-size:1.1rem}.hd h1 span{color:var(--ac)}.hr{display:flex;align-items:center;gap:12px;font-size:.85rem;color:var(--tm)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--lo);display:inline-block}.dot.off{background:var(--sh)}
.tabs{display:flex;gap:2px;padding:8px 20px;background:var(--s1);border-bottom:1px solid var(--bd)}
.tab{padding:8px 16px;border-radius:6px;cursor:pointer;font-size:.85rem;color:var(--ts);background:none;border:none}
.tab:hover{background:var(--s2);color:var(--tp)}.tab.on{background:var(--ac);color:#fff}
.sr{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;padding:16px 20px}
.st{background:var(--s1);border-radius:10px;padding:14px;border:1px solid var(--bd)}
.st .l{font-size:.75rem;color:var(--tm);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.st .v{font-size:1.5rem;font-weight:700}.st .v.lo{color:var(--lo)}.st .v.sh{color:var(--sh)}
.fl{display:flex;gap:8px;padding:12px 20px;flex-wrap:wrap}
.fb{padding:6px 14px;border-radius:6px;border:1px solid var(--bd);background:var(--s1);color:var(--ts);font-size:.8rem;cursor:pointer}
.fb:hover{border-color:var(--ac);color:var(--tp)}.fb.on{background:var(--ac);color:#fff;border-color:var(--ac)}
.si{padding:6px 12px;border-radius:6px;border:1px solid var(--bd);background:var(--s1);color:var(--tp);font-size:.8rem;width:160px}
.tw{padding:0 20px 20px;overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:10px 12px;color:var(--tm);font-weight:500;font-size:.75rem;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bd);background:var(--s0)}
td{padding:10px 12px;border-bottom:1px solid var(--bd);white-space:nowrap}tr:hover td{background:var(--s1)}
.sl{color:var(--lo);font-weight:600}.ss{color:var(--sh);font-weight:600}
.cb{display:inline-block;height:6px;border-radius:3px;background:var(--ac);min-width:4px}
.rt{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;background:var(--s2);color:var(--ts)}
.sc{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;padding:0 20px 20px}
.sg{background:var(--s1);border-radius:10px;padding:16px;border:1px solid var(--bd)}.sg:hover{border-color:var(--ac)}
.sgh{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.sgs{font-weight:700;font-size:1rem}
.sgl{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:.8rem;text-align:center}
.sgl .ll{color:var(--tm);font-size:.7rem}.sgl .lv{font-weight:600;margin-top:2px}.sgl .lp{font-size:.7rem;margin-top:1px}
.sgm{margin-top:8px;display:flex;gap:12px;font-size:.75rem;color:var(--tm)}
.rb{height:2px;background:var(--ac);transition:width 30s linear;position:fixed;top:0;left:0;z-index:20}
@media(max-width:600px){.sr{grid-template-columns:1fr 1fr;gap:8px;padding:12px}.sc{grid-template-columns:1fr;padding:0 12px 12px}td,th{padding:8px 6px;font-size:.8rem}}
.sg.hot{border:1.5px solid #f0b90b;box-shadow:0 0 12px rgba(240,185,11,.25)}.sg.hot .sgs{color:#f0b90b}tr.hot{background:rgba(240,185,11,.08)!important}tr.hot td:nth-child(2) strong{color:#f0b90b}</style></head><body>
<div class="rb" id="rb"></div>
<div class="hd"><h1><span>Crypto</span>Radar</h1><div class="hr"><span class="dot" id="dot"></span><span id="lu">--</span><span id="pc">--</span></div></div>
<div class="tabs"><button class="tab on" onclick="sw('scanner')">Scanner</button><button class="tab" onclick="sw('signals')">Signaux</button><button class="tab" onclick="sw('impact')">Impact</button></div>
<div id="t-scanner">
<div class="sr" id="tiles"></div>
<div class="fl"><button class="fb on" onclick="fs('ALL')">Tous</button><button class="fb" onclick="fs('LONG')">LONG</button><button class="fb" onclick="fs('SHORT')">SHORT</button><input class="si" placeholder="Chercher..." oninput="fq(this.value)"></div>
<div class="tw"><table><thead><tr><th>#</th><th>Symbole</th><th>Direction</th><th>Confiance</th><th>Max</th><th>Signaux</th><th>Regime</th><th>Entry</th><th>SL</th><th>TP</th></tr></thead><tbody id="tb"></tbody></table></div>
</div>
<div id="t-signals" style="display:none">
<div class="fl"><button class="fb on" onclick="fss('ALL')">Tous</button><button class="fb" onclick="fss('LONG')">LONG</button><button class="fb" onclick="fss('SHORT')">SHORT</button></div>
<div class="sc" id="scs"></div>
</div>
<div id="t-impact" style="display:none">
<div class="fl">
  <select class="si" id="ipsym" onchange="rI()"><option value="">Toutes positions</option></select>
  <input class="si" id="ippx" type="number" step="0.0001" placeholder="Prix hypothetique (0 = live)" oninput="rI()">
  <button class="fb" onclick="lI()">Rafraichir</button>
</div>
<div class="sr" id="ipT"></div>
<div class="tw"><table><thead><tr><th>Symbole</th><th>Side</th><th>Entry</th><th>Cur</th><th>SL</th><th>TP</th><th>Lev</th><th>Size $</th><th>PnL %</th><th>PnL $</th><th>Etat</th></tr></thead><tbody id="ipTb"></tbody></table></div>
</div>
<script>
let D=[],S=[],ct='scanner',sf='ALL',ssf='ALL',sq='';
function sw(t){ct=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));document.querySelector('.tab[onclick*="'+t+'"]').classList.add('on');document.getElementById('t-scanner').style.display=t==='scanner'?'':'none';document.getElementById('t-signals').style.display=t==='signals'?'':'none'}
function fs(s){sf=s;document.querySelectorAll('#t-scanner .fb').forEach(b=>b.classList.remove('on'));event.target.classList.add('on');rS()}
function fss(s){ssf=s;document.querySelectorAll('#t-signals .fb').forEach(b=>b.classList.remove('on'));event.target.classList.add('on');rG()}
function fq(v){sq=v.toUpperCase();rS()}
function fm(v){if(v==null)return'\u2014';if(Math.abs(v)>=1)return v.toLocaleString('fr-FR',{maximumFractionDigits:4});return v.toPrecision(4)}
function rT(){const l=D.filter(s=>s.dominant_side==='LONG').length,sh=D.filter(s=>s.dominant_side==='SHORT').length,ac=D.length?(D.reduce((a,s)=>a+s.avg_confidence,0)/D.length).toFixed(0):'\u2014',mx=D.length?Math.max(...D.map(s=>s.max_confidence)):'\u2014';document.getElementById('tiles').innerHTML='<div class="st"><div class="l">Symboles</div><div class="v">'+D.length+'</div></div><div class="st"><div class="l">LONG</div><div class="v lo">'+l+'</div></div><div class="st"><div class="l">SHORT</div><div class="v sh">'+sh+'</div></div><div class="st"><div class="l">Conf Moy</div><div class="v">'+ac+'</div></div><div class="st"><div class="l">Conf Max</div><div class="v">'+mx+'</div></div>'}
function rS(){let d=D;if(sf!=='ALL')d=d.filter(s=>s.dominant_side===sf);if(sq)d=d.filter(s=>s.symbol.toUpperCase().includes(sq));document.getElementById('tb').innerHTML=d.map((s,i)=>'<tr class="'+(s.avg_confidence>=80?'hot':'')+'"><td>'+(i+1)+'</td><td><strong>'+s.symbol+'</strong></td><td><span class="'+(s.dominant_side==='LONG'?'sl':'ss')+'">'+s.dominant_side+' '+s.dominance_pct+'%</span></td><td><span class="cb" style="width:'+Math.max(4,s.avg_confidence*.8)+'px"></span> '+s.avg_confidence+'</td><td>'+s.max_confidence+'</td><td>'+s.n_signals+'</td><td><span class="rt">'+s.regime.replace('TREND_','')+'</span></td><td>'+fm(s.entry)+'</td><td>'+fm(s.sl)+'</td><td>'+fm(s.tp)+'</td></tr>').join('');rT()}
function rG(){let d=S;if(ssf!=='ALL')d=d.filter(s=>ssf==='LONG'?['BUY','LONG'].includes(s.side):['SELL','SHORT'].includes(s.side));document.getElementById('scs').innerHTML=d.slice(0,30).map(s=>{const il=['BUY','LONG'].includes(s.side),dc=il?'sl':'ss',dr=il?'LONG':'SHORT',rr=s.r_multiple?'R:R '+s.r_multiple.toFixed(1):'';return'<div class="sg '+(s.confidence>=80?'hot':'')+'"><div class="sgh"><span class="sgs">'+s.symbol+'</span><span class="'+dc+'">'+dr+'</span></div><div class="sgl"><div><div class="ll">Entry</div><div class="lv">'+fm(s.entry)+'</div></div><div><div class="ll">Stop Loss</div><div class="lv" style="color:var(--sh)">'+fm(s.sl)+'</div><div class="lp">-'+s.risk_pct+'%</div></div><div><div class="ll">Take Profit</div><div class="lv" style="color:var(--lo)">'+fm(s.tp)+'</div><div class="lp">+'+s.reward_pct+'%</div></div></div><div class="sgm"><span>Conf: '+s.confidence+'/100</span><span>'+s.regime.replace('TREND_','')+'</span><span>'+rr+'</span></div></div>'}).join('')}
async function lI(){try{const sy=document.getElementById('ipsym').value,px=parseFloat(document.getElementById('ippx').value)||0;const q='/api/portfolio-impact?symbol='+encodeURIComponent(sy)+'&price='+px;const r=await fetch(q).then(x=>x.json());rI(r)}catch(e){console.error(e)}}
async function lIS(){try{const r=await fetch('/api/portfolio-symbols').then(x=>x.json());const sel=document.getElementById('ipsym'),cur=sel.value;sel.innerHTML='<option value="">Toutes positions</option>'+r.data.map(s=>'<option value="'+s+'"'+(s===cur?' selected':'')+'>'+s+'</option>').join('')}catch(e){}}
function rI(r){if(!r){lI();return}const t=document.getElementById('ipT');if(!r.n_positions){t.innerHTML='<div class="st"><div class="l">Aucune position</div><div class="v">—</div></div>';document.getElementById('ipTb').innerHTML='';return}t.innerHTML='<div class="st"><div class="l">Positions</div><div class="v">'+r.n_positions+'</div></div><div class="st"><div class="l">En profit</div><div class="v lo">'+r.n_profit+'</div></div><div class="st"><div class="l">En perte</div><div class="v sh">'+r.n_loss+'</div></div><div class="st"><div class="l">% Profit</div><div class="v">'+r.pct_profit+'%</div></div><div class="st"><div class="l">Total PnL $</div><div class="v '+(r.total_pnl_usd>=0?'lo':'sh')+'">'+r.total_pnl_usd.toFixed(2)+'</div></div><div class="st"><div class="l">Avg PnL %</div><div class="v '+(r.avg_pnl_pct>=0?'lo':'sh')+'">'+r.avg_pnl_pct.toFixed(2)+'%</div></div>';document.getElementById('ipTb').innerHTML=r.positions.map(p=>{const sc=String(p.side).toLowerCase().startsWith('l')?'sl':'ss';const pc=p.pnl_pct_at_price>=0?'lo':'sh';return'<tr><td><strong>'+p.symbol+'</strong></td><td><span class="'+sc+'">'+String(p.side).toUpperCase()+'</span></td><td>'+fm(p.entry)+'</td><td>'+fm(p.current)+'</td><td>'+fm(p.sl)+'</td><td>'+fm(p.tp)+'</td><td>'+p.leverage+'x</td><td>'+(p.size_usd||0).toFixed(0)+'</td><td class="'+pc+'">'+p.pnl_pct_at_price.toFixed(2)+'%</td><td class="'+pc+'">'+p.pnl_usd_at_price.toFixed(2)+'</td><td>'+(p.in_profit?'✅':'❌')+'</td></tr>'}).join('')}
async function load(){try{const[a,b,c]=await Promise.all([fetch('/api/scan?top=50&min_conf=60').then(r=>r.json()),fetch('/api/signals?hours=24&limit=50').then(r=>r.json()),fetch('/api/status').then(r=>r.json())]);D=a.data;S=b.data;rS();rG();const dt=document.getElementById('dot'),lp=c.last_packet;if(lp){const ago=Math.floor((Date.now()-new Date(lp+'Z').getTime())/60000);document.getElementById('lu').textContent=ago<60?ago+'min ago':Math.floor(ago/60)+'h ago';dt.className='dot'+(ago>10?' off':'')}document.getElementById('pc').textContent=c.packets_today+' pkts';const rb=document.getElementById('rb');rb.style.width='100%';rb.style.transition='none';requestAnimationFrame(()=>{rb.style.transition='width 30s linear';rb.style.width='0%'})}catch(e){console.error(e);document.getElementById('dot').className='dot off'}}
load();lIS();lI();setInterval(load,30000);setInterval(()=>{lIS();if(document.getElementById('t-impact').style.display!=='none')lI()},30000);
</script></body></html>"""

if __name__ == "__main__":
    import uvicorn
    print(f"[Dashboard] http://0.0.0.0:{DASHBOARD_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="warning")
