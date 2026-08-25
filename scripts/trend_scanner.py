#!/usr/bin/env python3
"""trend_scanner.py — Scanner de tendances multi-TF avec niveaux cles."""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DP_DIR = Path(os.getenv("DP_LOG_DIR", str(PROJECT/"databases")))
DB_PATH = Path(os.getenv("MARKET_DB_PATH", str(PROJECT/"databases"/"market_data.sqlite")))

def load_recent_packets(hours=24):
    now = datetime.utcnow()
    dates = set()
    for h in range(int(hours)+1):
        dates.add((now-timedelta(hours=h)).strftime("%Y-%m-%d"))
    packets = []
    for d in sorted(dates):
        fp = DP_DIR/f"decision_packets_{d}.jsonl"
        if not fp.exists():
            continue
        with open(fp,"r",encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line:
                    continue
                try:
                    packets.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return packets

def compute_symbol_stats(packets, min_confidence=0):
    by_sym = defaultdict(list)
    for p in packets:
        conf = p.get("confidence",0)
        if conf < min_confidence:
            continue
        sym = p.get("symbol","")
        if sym:
            by_sym[sym].append(p)
    results = []
    for sym,pks in by_sym.items():
        confs = [p.get("confidence",0) for p in pks]
        avg_c = sum(confs)/len(confs)
        sides = [p.get("side","") for p in pks]
        lo = sum(1 for s in sides if s in ("BUY","LONG"))
        sh = sum(1 for s in sides if s in ("SELL","SHORT"))
        if lo>sh:
            dom,pct="LONG",lo/len(sides)*100
        elif sh>lo:
            dom,pct="SHORT",sh/len(sides)*100
        else:
            dom,pct="MIXED",50.0
        wl = [p for p in pks if p.get("entry_price")]
        lat = wl[-1] if wl else pks[-1]
        regs = defaultdict(int)
        for p in pks:
            regs[p.get("regime","?")]+=1
        dreg = max(regs,key=regs.get)
        results.append({"symbol":sym,"avg_confidence":round(avg_c,1),
            "max_confidence":max(confs),"n_signals":len(pks),
            "dominant_side":dom,"dominance_pct":round(pct,0),
            "regime":dreg,"entry":lat.get("entry_price"),
            "sl":lat.get("stop_loss"),"tp":lat.get("take_profit"),
            "r_multiple":lat.get("r_multiple")})
    results.sort(key=lambda r:r["avg_confidence"],reverse=True)
    return results

def find_support_resistance(symbol, n_candles=200):
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH),timeout=5)
        rows = conn.execute(
            "SELECT high,low,close FROM ohlcv WHERE symbol=? ORDER BY timestamp DESC LIMIT ?",
            (symbol,n_candles)).fetchall()
        conn.close()
    except Exception:
        return {}
    if len(rows)<10:
        return {}
    highs=[r[0] for r in rows if r[0]]
    lows=[r[1] for r in rows if r[1]]
    closes=[r[2] for r in rows if r[2]]
    if not closes:
        return {}
    current=closes[0]
    pr=max(highs)-min(lows) if highs and lows else 1
    if pr<=0:
        return {}
    n_bins=50
    bs=pr/n_bins
    zones=defaultdict(int)
    for p in highs+lows:
        zones[int((p-min(lows))/bs)]+=1
    sups,ress=[],[]
    for zi,cnt in sorted(zones.items(),key=lambda x:x[1],reverse=True)[:10]:
        if cnt<3:
            continue
        lv=min(lows)+zi*bs+bs/2
        if lv<current:
            sups.append({"price":round(lv,8),"touches":cnt})
        else:
            ress.append({"price":round(lv,8),"touches":cnt})
    sups.sort(key=lambda x:x["price"],reverse=True)
    ress.sort(key=lambda x:x["price"])
    tc=0
    direction="flat"
    if len(closes)>=2:
        direction="up" if closes[0]>=closes[1] else "down"
        for i in range(1,len(closes)):
            if direction=="up" and closes[i-1]>=closes[i]:
                tc+=1
            elif direction=="down" and closes[i-1]<=closes[i]:
                tc+=1
            else:
                break
    rec=closes[:max(tc,5)]
    return {"supports":sups[:3],"resistances":ress[:3],
        "trend_direction":direction,"trend_candles":tc,
        "trend_high":round(max(rec),8),"trend_low":round(min(rec),8),
        "current":round(current,8)}

def multi_tf_trend(symbol):
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH),timeout=5)
        rows = conn.execute(
            "SELECT close FROM ohlcv WHERE symbol=? ORDER BY timestamp DESC LIMIT 720",
            (symbol,)).fetchall()
        conn.close()
    except Exception:
        return {}
    if len(rows)<2:
        return {}
    closes=[r[0] for r in rows if r[0]]
    if not closes:
        return {}
    now_p=closes[0]
    t={}
    if len(closes)>1:
        t["30m"]="up" if now_p>closes[1] else "down"
    if len(closes)>4:
        t["4h"]="up" if now_p>closes[4] else "down"
    if len(closes)>24:
        t["24h"]="up" if now_p>closes[24] else "down"
    if len(closes)>168:
        t["7j"]="up" if now_p>closes[168] else "down"
    if len(closes)>700:
        t["30j"]="up" if now_p>closes[700] else "down"
    return t

def format_trend_table(stats, enriched):
    now_str=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines=[f"\U0001f4ca TREND SCANNER -- {now_str}",f"Top {len(stats)} par confiance\n"]
    for s in stats:
        sym=s["symbol"]
        icon="\U0001f7e2" if s["dominant_side"]=="LONG" else "\U0001f534" if s["dominant_side"]=="SHORT" else " "
        lines.append(f"{icon} {sym} | {s['dominant_side']} {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        info=enriched.get(sym,{})
        tf=info.get("tf",{})
        if tf:
            ar=[f"{p}:{'↑' if tf[p]=='up' else '↓'}" for p in ["30m","4h","24h","7j","30j"] if p in tf]
            if ar:
                lines.append(f"   TF: {' '.join(ar)}")
        sr=info.get("sr",{})
        if sr:
            td=sr.get("trend_direction","?")
            tc=sr.get("trend_candles",0)
            ta="↑" if td=="up" else "↓"
            lines.append(f"   Trend: {ta} depuis {tc} bougies | range [{sr.get('trend_low','?')} -- {sr.get('trend_high','?')}]")
            su=sr.get("supports",[])
            re=sr.get("resistances",[])
            su=sr.get("supports",[])
            re=sr.get("resistances",[])
            if su:
                s_fmt=', '.join(str(round(x['price'],6))+'('+str(x['touches'])+'x)' for x in su[:2])
                lines.append('   S: '+s_fmt)
            if re:
                r_fmt=', '.join(str(round(x['price'],6))+'('+str(x['touches'])+'x)' for x in re[:2])
                lines.append('   R: '+r_fmt)
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
        lines.append("")
    return "\n".join(lines)

def send_telegram(text):
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id:
        print("[ERREUR] TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        return False
    import urllib.request
    chunks=[text] if len(text)<=4000 else []
    if not chunks:
        chunk=""
        for line in text.split("\n"):
            if len(chunk)+len(line)+1>4000:
                chunks.append(chunk)
                chunk=line+"\n"
            else:
                chunk+=line+"\n"
        if chunk.strip():
            chunks.append(chunk)
    ok=True
    for i,ch in enumerate(chunks):
        try:
            url=f"https://api.telegram.org/bot{token}/sendMessage"
            pl=json.dumps({"chat_id":chat_id,"text":ch,"disable_web_page_preview":True}).encode()
            req=urllib.request.Request(url,data=pl,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=10) as resp:
                if resp.status!=200:
                    ok=False
        except Exception as e:
            print(f"[ERREUR] {e}")
            ok=False
        if i<len(chunks)-1:
            time.sleep(0.5)
    return ok

def main():
    parser=argparse.ArgumentParser(description="Scanner tendances trading")
    parser.add_argument("--top",type=int,default=20)
    parser.add_argument("--hours",type=float,default=24)
    parser.add_argument("--min-confidence",type=float,default=65)
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    print(f"[Scanner] Chargement DPs ({args.hours}h)...")
    packets=load_recent_packets(args.hours)
    print(f"[Scanner] {len(packets)} packets")
    stats=compute_symbol_stats(packets,min_confidence=args.min_confidence)[:args.top]
    print(f"[Scanner] {len(stats)} symboles conf>={args.min_confidence}")
    if not stats:
        print("[Scanner] Aucun symbole")
        return
    enriched={}
    print("[Scanner] Analyse S/R et multi-TF...")
    for s in stats:
        sym=s["symbol"]
        enriched[sym]={"sr":find_support_resistance(sym),"tf":multi_tf_trend(sym)}
    report=format_trend_table(stats,enriched)
    print("\n"+report)
    if not args.dry_run:
        if send_telegram(report):
            print("\n[OK] Envoye")
        else:
            print("\n[ECHEC] Envoi echoue")
    else:
        print("\n[DRY-RUN]")

if __name__=="__main__":
    main()
