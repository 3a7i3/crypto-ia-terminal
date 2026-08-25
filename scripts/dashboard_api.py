#!/usr/bin/env python3
"""dashboard_api.py — API + Dashboard CryptoRadar. LECTURE SEULE."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from fastapi import FastAPI,HTTPException
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
        if not hmac.compare_digest(sig, expected):
            return False
        return 0 <= time.time() - int(ts) < 86400 * 7
    except Exception:
        return False

_LOGIN_HTML = '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0f1117;color:#e0e0e0;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh}.c{background:#1a1d27;padding:2rem;border-radius:12px;width:min(90vw,360px)}h2{margin-bottom:1rem;color:#3987e5}input{width:100%;padding:12px;border:1px solid #333;border-radius:8px;background:#0f1117;color:#fff;font-size:1rem;margin-bottom:1rem}button{width:100%;padding:12px;border:none;border-radius:8px;background:#2a78d6;color:#fff;font-size:1rem;cursor:pointer}.e{color:#e34948;font-size:.85rem;display:none}</style></head><body><div class="c"><h2>CryptoRadar</h2><p class="e" id="e">Mot de passe incorrect</p><form onsubmit="return d(event)"><input type="password" id="p" placeholder="Mot de passe" autofocus><button>Connexion</button></form></div><script>async function d(e){e.preventDefault();const r=await fetch("/login",{method:"POST",body:new URLSearchParams({password:document.getElementById("p").value})});if(r.ok)location.reload();else document.getElementById("e").style.display="block"}</script></body></html>'
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not DASHBOARD_PASSWORD:
            return await call_next(request)
        token = request.cookies.get("radar_session")
        if token and _verify_token(token):
            return await call_next(request)
        if request.url.path == "/login" and request.method == "POST":
            form = await request.form()
            if hmac.compare_digest(form.get("password",""), DASHBOARD_PASSWORD):
                resp = JSONResponse({"ok": True})
                resp.set_cookie("radar_session", _make_token(), max_age=604800, httponly=True, samesite="lax")
                return resp
            raise HTTPException(401)
        if request.url.path.startswith("/api/"):
            raise HTTPException(401)
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
        if not fp.exists():
            continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    packets.append(json.loads(line))
                except Exception:
                    continue
    return packets

def compute_stats(packets, min_conf=0):
    by_sym = defaultdict(list)
    for p in packets:
        c = p.get("confidence",0)
        if c < min_conf:
            continue
        s = p.get("symbol","")
        if s:
            by_sym[s].append(p)
    results = []
    for sym, pks in by_sym.items():
        confs = [p.get("confidence",0) for p in pks]
        avg = sum(confs)/len(confs)
        sides = [p.get("side","") for p in pks]
        lo = sum(1 for s in sides if s in ("BUY","LONG"))
        sh = sum(1 for s in sides if s in ("SELL","SHORT"))
        if lo > sh:
            dom, pct = "LONG", lo/len(sides)*100
        elif sh > lo:
            dom, pct = "SHORT", sh/len(sides)*100
        else:
            dom, pct = "MIXED", 50.0
        regs = defaultdict(int)
        for p in pks:
            regs[p.get("regime","?")] += 1
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
        if not e or not sl or not tp:
            continue
        sym,side = p.get("symbol","?"),p.get("side","?")
        k = f"{sym}:{side}"
        if side in ("BUY","LONG"):
            ri = (e-sl)/e*100 if e>0 else 0
            re = (tp-e)/e*100 if e>0 else 0
        else:
            ri = (sl-e)/e*100 if e>0 else 0
            re = (e-tp)/e*100 if e>0 else 0
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
    if not m:
        raise HTTPException(404)
    confs = [p.get("confidence",0) for p in m]
    sides = [p.get("side","") for p in m]
    lo = sum(1 for s in sides if s in ("BUY","LONG"))
    sh = sum(1 for s in sides if s in ("SELL","SHORT"))
    regs = defaultdict(int)
    for p in m:
        regs[p.get("regime","?")] += 1
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
                        if t:
                            lt = t
                    except Exception:
                        pass
    dfs = sorted(DP_DIR.glob("decision_packets_*.jsonl"))
    ts = sum(f.stat().st_size for f in dfs)
    return {"packets_today":n,"last_packet":lt[:19] if lt else None,
        "dp_files":len(dfs),"dp_total_gb":round(ts/1e9,2)}

try:
    import sys as _sys
    _sys.path.insert(0, str(PROJECT))
    from trade_analysis.integrations import dashboard_adapter as _lmi
except Exception:  # pragma: no cover - LMI optionnel
    _lmi = None

@app.get("/api/lmi/status")
def api_lmi_status():
    if _lmi is None:
        return {"running": False, "error": "lmi_unavailable"}
    return _lmi.lmi_status()

@app.get("/api/lmi/table")
def api_lmi_table():
    if _lmi is None:
        return {"data": [], "count": 0}
    return _lmi.lmi_table()

@app.get("/api/lmi/symbol/{symbol}")
def api_lmi_symbol(symbol: str):
    if _lmi is None:
        raise HTTPException(503)
    d = _lmi.lmi_symbol(symbol)
    if d is None:
        raise HTTPException(404)
    return d

@app.get("/api/lmi/events")
def api_lmi_events(min_confidence: float = 0.6):
    if _lmi is None:
        return {"data": [], "count": 0}
    return _lmi.lmi_events(min_confidence=min_confidence)

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
<div class="tabs"><button class="tab on" onclick="sw('scanner')">Scanner</button><button class="tab" onclick="sw('signals')">Signaux</button><button class="tab" onclick="sw('live')">Live Market</button></div>
<div id="t-scanner">
<div class="sr" id="tiles"></div>
<div class="fl"><button class="fb on" onclick="fs('ALL')">Tous</button><button class="fb" onclick="fs('LONG')">LONG</button><button class="fb" onclick="fs('SHORT')">SHORT</button><input class="si" placeholder="Chercher..." oninput="fq(this.value)"></div>
<div class="tw"><table><thead><tr><th>#</th><th>Symbole</th><th>Direction</th><th>Confiance</th><th>Max</th><th>Signaux</th><th>Regime</th><th>Entry</th><th>SL</th><th>TP</th></tr></thead><tbody id="tb"></tbody></table></div>
</div>
<div id="t-signals" style="display:none">
<div class="fl"><button class="fb on" onclick="fss('ALL')">Tous</button><button class="fb" onclick="fss('LONG')">LONG</button><button class="fb" onclick="fss('SHORT')">SHORT</button></div>
<div class="sc" id="scs"></div>
</div>
<div id="t-live" style="display:none">
<div class="sr" id="lmi-tiles"></div>
<div class="fl">
<span style="color:var(--tm);font-size:.75rem;align-self:center">Etat</span>
<button class="fb on" onclick="lf('state','ALL',event)">Tous</button>
<button class="fb" onclick="lf('state','accumulation',event)">Accumulation</button>
<button class="fb" onclick="lf('state','distribution',event)">Distribution</button>
<button class="fb" onclick="lf('state','conflict',event)">Conflict</button>
<button class="fb" onclick="lf('state','vacuum_up',event)">Vacuum</button>
<input class="si" placeholder="Chercher..." oninput="lfq(this.value)">
</div>
<div class="tw"><table><thead><tr><th>Symbole</th><th>Etat</th><th>Conf</th><th>Buy</th><th>Sell</th><th>Flux USD</th><th>Resist.</th><th>Fragil.</th><th>Prix</th></tr></thead><tbody id="lmi-tb"></tbody></table></div>
<p style="padding:0 20px 20px;color:var(--tm);font-size:.75rem">⚠️ Observation de recherche — pas un signal de trading (ADR-0007)</p>
</div>
<script>
let D=[],S=[],L=[],ct='scanner',sf='ALL',ssf='ALL',sq='',lsf='ALL',lq='';
const LMIC={accumulation:'#0ca30c',distribution:'#d03b3b',absorption_buy:'#e0b400',absorption_sell:'#e0b400',fragility_up:'#e08000',fragility_down:'#e08000',compression:'#2a78d6',expansion:'#c000c0',exhaustion_buy:'#a000a0',exhaustion_sell:'#a000a0',vacuum_up:'#00b0b0',vacuum_down:'#00b0b0',conflict:'#f0b90b',quiet:'#7a7a6e'};
function sw(t){ct=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));document.querySelector('.tab[onclick*="'+t+'"]').classList.add('on');document.getElementById('t-scanner').style.display=t==='scanner'?'':'none';document.getElementById('t-signals').style.display=t==='signals'?'':'none';document.getElementById('t-live').style.display=t==='live'?'':'none';if(t==='live')loadLMI()}
function lf(k,v,e){lsf=v;document.querySelectorAll('#t-live .fb').forEach(b=>b.classList.remove('on'));e.target.classList.add('on');rL()}
function lfq(v){lq=v.toUpperCase();rL()}
function rLT(){const a=L.filter(r=>!r.stale).length,ev=L.filter(r=>r.state!=='quiet'&&!r.stale).length,fl=L.reduce((s,r)=>s+(r.total_flow_usd||0),0);document.getElementById('lmi-tiles').innerHTML='<div class="st"><div class="l">Observes</div><div class="v">'+L.length+'</div></div><div class="st"><div class="l">Actifs</div><div class="v lo">'+a+'</div></div><div class="st"><div class="l">Events</div><div class="v">'+ev+'</div></div><div class="st"><div class="l">Flux USD</div><div class="v">'+fmU(fl)+'</div></div>'}
function fmU(v){v=v||0;if(Math.abs(v)>=1e6)return(v/1e6).toFixed(1)+'M';if(Math.abs(v)>=1e3)return(v/1e3).toFixed(0)+'k';return v.toFixed(0)}
function rL(){let d=L;if(lsf!=='ALL')d=d.filter(r=>r.state===lsf);if(lq)d=d.filter(r=>r.symbol.includes(lq));document.getElementById('lmi-tb').innerHTML=d.map(r=>{const c=LMIC[r.state]||'#7a7a6e',o=r.stale?'opacity:.4':'';return'<tr style="'+o+'"><td><strong>'+r.symbol+'</strong></td><td><span style="color:'+c+';font-weight:600">'+r.state.toUpperCase()+'</span></td><td>'+(r.state_confidence*100).toFixed(0)+'</td><td class="sl">'+r.buy_pressure+'</td><td class="ss">'+r.sell_pressure+'</td><td>'+fmU(r.total_flow_usd)+'</td><td>'+fmU(r.resistance)+'</td><td>'+r.fragility.toFixed(2)+'</td><td>'+fm(r.price)+'</td></tr>'}).join('')||'<tr><td colspan="9" style="text-align:center;color:var(--tm);padding:24px">Observatoire inactif ou aucune donnee live</td></tr>';rLT()}
async function loadLMI(){try{const r=await fetch('/api/lmi/table').then(r=>r.json());L=r.data||[];rL()}catch(e){console.error(e)}}
function fs(s){sf=s;document.querySelectorAll('#t-scanner .fb').forEach(b=>b.classList.remove('on'));event.target.classList.add('on');rS()}
function fss(s){ssf=s;document.querySelectorAll('#t-signals .fb').forEach(b=>b.classList.remove('on'));event.target.classList.add('on');rG()}
function fq(v){sq=v.toUpperCase();rS()}
function fm(v){if(v==null)return'\u2014';if(Math.abs(v)>=1)return v.toLocaleString('fr-FR',{maximumFractionDigits:4});return v.toPrecision(4)}
function rT(){const l=D.filter(s=>s.dominant_side==='LONG').length,sh=D.filter(s=>s.dominant_side==='SHORT').length,ac=D.length?(D.reduce((a,s)=>a+s.avg_confidence,0)/D.length).toFixed(0):'\u2014',mx=D.length?Math.max(...D.map(s=>s.max_confidence)):'\u2014';document.getElementById('tiles').innerHTML='<div class="st"><div class="l">Symboles</div><div class="v">'+D.length+'</div></div><div class="st"><div class="l">LONG</div><div class="v lo">'+l+'</div></div><div class="st"><div class="l">SHORT</div><div class="v sh">'+sh+'</div></div><div class="st"><div class="l">Conf Moy</div><div class="v">'+ac+'</div></div><div class="st"><div class="l">Conf Max</div><div class="v">'+mx+'</div></div>'}
function rS(){let d=D;if(sf!=='ALL')d=d.filter(s=>s.dominant_side===sf);if(sq)d=d.filter(s=>s.symbol.toUpperCase().includes(sq));document.getElementById('tb').innerHTML=d.map((s,i)=>'<tr class="'+(s.avg_confidence>=80?'hot':'')+'"><td>'+(i+1)+'</td><td><strong>'+s.symbol+'</strong></td><td><span class="'+(s.dominant_side==='LONG'?'sl':'ss')+'">'+s.dominant_side+' '+s.dominance_pct+'%</span></td><td><span class="cb" style="width:'+Math.max(4,s.avg_confidence*.8)+'px"></span> '+s.avg_confidence+'</td><td>'+s.max_confidence+'</td><td>'+s.n_signals+'</td><td><span class="rt">'+s.regime.replace('TREND_','')+'</span></td><td>'+fm(s.entry)+'</td><td>'+fm(s.sl)+'</td><td>'+fm(s.tp)+'</td></tr>').join('');rT()}
function rG(){let d=S;if(ssf!=='ALL')d=d.filter(s=>ssf==='LONG'?['BUY','LONG'].includes(s.side):['SELL','SHORT'].includes(s.side));document.getElementById('scs').innerHTML=d.slice(0,30).map(s=>{const il=['BUY','LONG'].includes(s.side),dc=il?'sl':'ss',dr=il?'LONG':'SHORT',rr=s.r_multiple?'R:R '+s.r_multiple.toFixed(1):'';return'<div class="sg '+(s.confidence>=80?'hot':'')+'"><div class="sgh"><span class="sgs">'+s.symbol+'</span><span class="'+dc+'">'+dr+'</span></div><div class="sgl"><div><div class="ll">Entry</div><div class="lv">'+fm(s.entry)+'</div></div><div><div class="ll">Stop Loss</div><div class="lv" style="color:var(--sh)">'+fm(s.sl)+'</div><div class="lp">-'+s.risk_pct+'%</div></div><div><div class="ll">Take Profit</div><div class="lv" style="color:var(--lo)">'+fm(s.tp)+'</div><div class="lp">+'+s.reward_pct+'%</div></div></div><div class="sgm"><span>Conf: '+s.confidence+'/100</span><span>'+s.regime.replace('TREND_','')+'</span><span>'+rr+'</span></div></div>'}).join('')}
async function load(){try{const[a,b,c]=await Promise.all([fetch('/api/scan?top=50&min_conf=60').then(r=>r.json()),fetch('/api/signals?hours=24&limit=50').then(r=>r.json()),fetch('/api/status').then(r=>r.json())]);D=a.data;S=b.data;rS();rG();const dt=document.getElementById('dot'),lp=c.last_packet;if(lp){const ago=Math.floor((Date.now()-new Date(lp+'Z').getTime())/60000);document.getElementById('lu').textContent=ago<60?ago+'min ago':Math.floor(ago/60)+'h ago';dt.className='dot'+(ago>10?' off':'')}document.getElementById('pc').textContent=c.packets_today+' pkts';const rb=document.getElementById('rb');rb.style.width='100%';rb.style.transition='none';requestAnimationFrame(()=>{rb.style.transition='width 30s linear';rb.style.width='0%'})}catch(e){console.error(e);document.getElementById('dot').className='dot off'}}
load();setInterval(load,30000);
setInterval(()=>{if(ct==='live')loadLMI()},5000);
</script></body></html>"""

if __name__ == "__main__":
    import uvicorn
    print(f"[Dashboard] http://0.0.0.0:{DASHBOARD_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="warning")
