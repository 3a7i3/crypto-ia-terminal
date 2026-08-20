#!/usr/bin/env python3
"""daily_signal_report.py — Rapport quotidien de signaux de trading."""
from __future__ import annotations
import argparse, json, os, re, sys, time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DP_DIR = Path(os.getenv("DP_LOG_DIR", str(PROJECT / "databases")))

def load_packets(date_str=None, last_hours=None):
    if date_str:
        files = [DP_DIR / f"decision_packets_{date_str}.jsonl"]
    else:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        files = [DP_DIR / f"decision_packets_{today}.jsonl"]
    cutoff = time.time() - last_hours * 3600 if last_hours else None
    packets = []
    for fp in files:
        if not fp.exists(): continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: packets.append(json.loads(line))
                except json.JSONDecodeError: continue
    if cutoff:
        filtered = []
        for p in packets:
            ts = p.get("created_at") or p.get("metadata",{}).get("lse_timestamp","")
            if isinstance(ts,(int,float)) and ts >= cutoff:
                filtered.append(p)
            elif isinstance(ts, str):
                try:
                    dt2 = datetime.fromisoformat(ts.replace("Z","+00:00"))
                    if dt2.timestamp() >= cutoff: filtered.append(p)
                except (ValueError,AttributeError): filtered.append(p)
        packets = filtered
    return packets

def extract_signals(packets):
    signals, seen = [], set()
    for p in packets:
        entry = p.get("entry_price")
        sl = p.get("stop_loss")
        tp = p.get("take_profit")
        if not entry or not sl or not tp: continue
        symbol = p.get("symbol","?")
        side = p.get("side","?")
        r_mult = p.get("r_multiple")
        confidence = p.get("confidence",0)
        regime = p.get("regime","?")
        key = f"{symbol}:{side}:{round(entry,4)}"
        if key in seen: continue
        seen.add(key)
        if side in ("BUY","LONG"):
            risk_pct = (entry-sl)/entry*100 if entry>0 else 0
            reward_pct = (tp-entry)/entry*100 if entry>0 else 0
        else:
            risk_pct = (sl-entry)/entry*100 if entry>0 else 0
            reward_pct = (entry-tp)/entry*100 if entry>0 else 0
        signals.append({
            "symbol":symbol, "side":side, "entry":entry,
            "sl":sl, "tp":tp, "r_multiple":r_mult,
            "confidence":confidence, "regime":regime,
            "risk_pct":round(risk_pct,2), "reward_pct":round(reward_pct,2),
        })
    signals.sort(key=lambda s: s.get("confidence",0), reverse=True)
    return signals

def format_signal(s):
    icon = "\U0001f7e2" if s["side"] in ("BUY","LONG") else "\U0001f534"
    d = "LONG" if s["side"] in ("BUY","LONG") else "SHORT"
    r_str = f" | R:R {s['r_multiple']:.1f}" if s.get("r_multiple") else ""
    return (f"{icon} {s['symbol']} {d}\n"
            f"   Entry: {s['entry']:.6g}\n"
            f"   SL:    {s['sl']:.6g}  (-{s['risk_pct']:.1f}%)\n"
            f"   TP:    {s['tp']:.6g}  (+{s['reward_pct']:.1f}%)\n"
            f"   Conf: {s['confidence']:.0f}/100 | {s['regime']}{r_str}")

def format_report(signals, date_str):
    if not signals:
        return f"\U0001f4cb SIGNAUX {date_str}\n\nAucun signal avec niveaux entry/SL/TP."
    longs = [s for s in signals if s["side"] in ("BUY","LONG")]
    shorts = [s for s in signals if s["side"] not in ("BUY","LONG")]
    lines = [f"\U0001f4cb SIGNAUX {date_str} -- {len(signals)} signal(s)\n"]
    if longs:
        lines.append(f"-- LONG ({len(longs)}) --")
        for s in longs[:10]: lines.append(format_signal(s)); lines.append("")
    if shorts:
        lines.append(f"-- SHORT ({len(shorts)}) --")
        for s in shorts[:10]: lines.append(format_signal(s)); lines.append("")
    if len(signals)>20: lines.append(f"... et {len(signals)-20} autre(s)")
    return "\n".join(lines)

def send_telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id:
        print("[ERREUR] TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        return False
    import urllib.request
    MAX_LEN = 4000
    chunks = [text] if len(text)<=MAX_LEN else []
    if not chunks:
        chunk = ""
        for line in text.split("\n"):
            if len(chunk)+len(line)+1>MAX_LEN: chunks.append(chunk); chunk=line+"\n"
            else: chunk+=line+"\n"
        if chunk.strip(): chunks.append(chunk)
    ok = True
    for i,ch in enumerate(chunks):
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id":chat_id,"text":ch,"disable_web_page_preview":True}).encode()
            req = urllib.request.Request(url,data=payload,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=10) as resp:
                if resp.status!=200: print(f"[WARN] HTTP {resp.status}"); ok=False
        except Exception as e: print(f"[ERREUR] {e}"); ok=False
        if i<len(chunks)-1: time.sleep(0.5)
    return ok

def main():
    parser = argparse.ArgumentParser(description="Rapport signaux trading")
    parser.add_argument("--date", help="YYYY-MM-DD (defaut: aujourd'hui)")
    parser.add_argument("--last", help="Dernieres N heures (ex: 4h)")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans envoyer")
    parser.add_argument("--min-confidence", type=float, default=0)
    args = parser.parse_args()
    date_str = args.date or datetime.utcnow().strftime("%Y-%m-%d")
    last_hours = None
    if args.last:
        m = re.match(r"(\d+(?:\.\d+)?)h?", args.last)
        if m: last_hours = float(m.group(1))
    packets = load_packets(date_str=args.date, last_hours=last_hours)
    print(f"Packets charges: {len(packets)}")
    signals = extract_signals(packets)
    if args.min_confidence > 0:
        signals = [s for s in signals if s["confidence"]>=args.min_confidence]
    print(f"Signaux avec entry/SL/TP: {len(signals)}")
    report = format_report(signals, date_str)
    print("\n" + report)
    if not args.dry_run and signals:
        if send_telegram(report): print("\n[OK] Rapport envoye via Telegram")
        else: print("\n[ECHEC] Envoi echoue")
    elif args.dry_run: print("\n[DRY-RUN] Pas d'envoi")
    elif not signals: print("\n[INFO] Aucun signal")

if __name__ == "__main__":
    main()
