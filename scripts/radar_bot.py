#!/usr/bin/env python3
"""radar_bot.py — Bot Telegram interactif CryptoRadar. LECTURE SEULE."""

from __future__ import annotations
import json, os, sys, time, traceback, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DP_DIR = Path(os.getenv("DP_LOG_DIR", str(PROJECT / "databases")))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ALLOWED_CHATS = {CHAT_ID} if CHAT_ID else set()

def tg_request(method, payload=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if payload:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def send_message(chat_id, text):
    MAX_LEN = 4000
    chunks = [text] if len(text) <= MAX_LEN else []
    if not chunks:
        chunk = ""
        for line in text.split("\n"):
            if len(chunk) + len(line) + 1 > MAX_LEN:
                chunks.append(chunk)
                chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk.strip():
            chunks.append(chunk)
    for i, ch in enumerate(chunks):
        tg_request("sendMessage", {"chat_id": chat_id, "text": ch, "disable_web_page_preview": True})
        if i < len(chunks) - 1:
            time.sleep(0.3)

def load_recent_packets(hours=24):
    now = datetime.utcnow()
    dates = set()
    for h in range(int(hours) + 1):
        dates.add((now - timedelta(hours=h)).strftime("%Y-%m-%d"))
    packets = []
    for date_str in sorted(dates):
        fp = DP_DIR / f"decision_packets_{date_str}.jsonl"
        if not fp.exists():
            continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    packets.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return packets

def compute_symbol_stats(packets, min_conf=0):
    by_sym = defaultdict(list)
    for p in packets:
        conf = p.get("confidence", 0)
        if conf < min_conf:
            continue
        sym = p.get("symbol", "")
        if sym:
            by_sym[sym].append(p)
    results = []
    for sym, pks in by_sym.items():
        confs = [p.get("confidence", 0) for p in pks]
        avg = sum(confs) / len(confs)
        sides = [p.get("side", "") for p in pks]
        longs = sum(1 for s in sides if s in ("BUY", "LONG"))
        shorts = sum(1 for s in sides if s in ("SELL", "SHORT"))
        if longs > shorts:
            dom, dom_pct = "LONG", longs / len(sides) * 100
        elif shorts > longs:
            dom, dom_pct = "SHORT", shorts / len(sides) * 100
        else:
            dom, dom_pct = "MIXED", 50.0
        regimes = defaultdict(int)
        for p in pks:
            regimes[p.get("regime", "?")] += 1
        regime = max(regimes, key=regimes.get)
        latest = ([p for p in pks if p.get("entry_price")] or pks)[-1]
        results.append({"symbol": sym, "avg_confidence": round(avg, 1),
            "max_confidence": max(confs), "n_signals": len(pks),
            "dominant_side": dom, "dominance_pct": round(dom_pct, 0),
            "regime": regime, "entry": latest.get("entry_price"),
            "sl": latest.get("stop_loss"), "tp": latest.get("take_profit"),
            "r_multiple": latest.get("r_multiple")})
    results.sort(key=lambda r: r["avg_confidence"], reverse=True)
    return results

def extract_signals(packets):
    signals = []
    seen = set()
    for p in packets:
        entry = p.get("entry_price")
        sl = p.get("stop_loss")
        tp = p.get("take_profit")
        if not entry or not sl or not tp:
            continue
        sym = p.get("symbol", "?")
        side = p.get("side", "?")
        key = f"{sym}:{side}:{round(entry, 4)}"
        if key in seen:
            continue
        seen.add(key)
        if side in ("BUY", "LONG"):
            risk = (entry - sl) / entry * 100 if entry > 0 else 0
            reward = (tp - entry) / entry * 100 if entry > 0 else 0
        else:
            risk = (sl - entry) / entry * 100 if entry > 0 else 0
            reward = (entry - tp) / entry * 100 if entry > 0 else 0
        signals.append({"symbol": sym, "side": side, "entry": entry,
            "sl": sl, "tp": tp, "r_multiple": p.get("r_multiple"),
            "confidence": p.get("confidence", 0), "regime": p.get("regime", "?"),
            "risk_pct": round(risk, 2), "reward_pct": round(reward, 2)})
    signals.sort(key=lambda s: s["confidence"], reverse=True)
    return signals

def cmd_scan(args):
    top_n = 10
    if args.strip().isdigit():
        top_n = min(int(args.strip()), 50)
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=65)[:top_n]
    if not stats:
        return "\U0001f4ca SCAN — Aucun symbole avec conf >= 65"
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\U0001f4ca SCAN — {now_str}", f"Top {len(stats)} (24h, conf>=65)\n"]
    for s in stats:
        icon = "\U0001f7e2" if s["dominant_side"] == "LONG" else "\U0001f534" if s["dominant_side"] == "SHORT" else "⚪"
        lines.append(f"{icon} {s['symbol']} | {s['dominant_side']} {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
        lines.append("")
    return "\n".join(lines)

def cmd_signals(args):
    hours = 24
    a = args.strip().lower()
    if a:
        try:
            hours = float(a.replace("h", ""))
        except ValueError:
            pass
    packets = load_recent_packets(hours)
    sigs = extract_signals(packets)[:15]
    if not sigs:
        return f"\U0001f4cb SIGNALS ({hours:.0f}h) — Aucun signal avec Entry/SL/TP"
    lines = [f"\U0001f4cb SIGNALS — {len(sigs)} signaux ({hours:.0f}h)\n"]
    for s in sigs:
        icon = "\U0001f7e2" if s["side"] in ("BUY", "LONG") else "\U0001f534"
        d = "LONG" if s["side"] in ("BUY", "LONG") else "SHORT"
        r_str = f" | R:R {s['r_multiple']:.1f}" if s.get("r_multiple") else ""
        lines.append(f"{icon} {s['symbol']} {d}\n   Entry: {s['entry']:.6g}\n   SL: {s['sl']:.6g} (-{s['risk_pct']:.1f}%) | TP: {s['tp']:.6g} (+{s['reward_pct']:.1f}%)\n   Conf: {s['confidence']:.0f}/100 | {s['regime']}{r_str}\n")
    return "\n".join(lines)

def cmd_top50(_args):
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=60)[:50]
    if not stats:
        return "\U0001f4ca TOP50 — Aucun symbole"
    lines = ["\U0001f4ca TOP 50 — conf>=60 (24h)\n"]
    for i, s in enumerate(stats, 1):
        icon = "\U0001f7e2" if s["dominant_side"] == "LONG" else "\U0001f534" if s["dominant_side"] == "SHORT" else "⚪"
        lines.append(f"{i:2d}. {icon} {s['symbol']:12s} {s['dominant_side']:5s} {s['dominance_pct']:3.0f}% | conf {s['avg_confidence']:.0f} | {s['regime']}")
    return "\n".join(lines)

def cmd_longs(_args):
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=65)
    longs = [s for s in stats if s["dominant_side"] == "LONG"][:15]
    if not longs:
        return "\U0001f7e2 LONGS — Aucun"
    lines = [f"\U0001f7e2 TOP LONGS — {len(longs)} symboles (24h)\n"]
    for s in longs:
        lines.append(f"\U0001f7e2 {s['symbol']} | {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
        lines.append("")
    return "\n".join(lines)

def cmd_shorts(_args):
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=65)
    shorts = [s for s in stats if s["dominant_side"] == "SHORT"][:15]
    if not shorts:
        return "\U0001f534 SHORTS — Aucun"
    lines = [f"\U0001f534 TOP SHORTS — {len(shorts)} symboles (24h)\n"]
    for s in shorts:
        lines.append(f"\U0001f534 {s['symbol']} | {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
        lines.append("")
    return "\n".join(lines)

def cmd_symbol(args):
    query = args.strip().upper()
    if not query:
        return "Usage: /symbol BTC  ou  /symbol BTC/USDT"
    packets = load_recent_packets(24)
    matching = [p for p in packets if query in p.get("symbol", "").upper()]
    if not matching:
        return f"Aucun signal pour '{query}' (24h)"
    sym_name = matching[0].get("symbol", query)
    confs = [p.get("confidence", 0) for p in matching]
    sides = [p.get("side", "") for p in matching]
    longs = sum(1 for s in sides if s in ("BUY", "LONG"))
    shorts = sum(1 for s in sides if s in ("SELL", "SHORT"))
    regimes = defaultdict(int)
    for p in matching:
        regimes[p.get("regime", "?")] += 1
    dom_regime = max(regimes, key=regimes.get)
    with_levels = [p for p in matching if p.get("entry_price")]
    lines = [f"\U0001f50d {sym_name} — detail 24h\n",
        f"Signals: {len(matching)}",
        f"Conf:    avg {sum(confs)/len(confs):.1f} | max {max(confs):.0f} | min {min(confs):.0f}",
        f"LONG:    {longs}  |  SHORT: {shorts}",
        f"Regime:  {dom_regime}"]
    if with_levels:
        last = with_levels[-1]
        e, sl, tp = last["entry_price"], last.get("stop_loss", 0), last.get("take_profit", 0)
        side = last.get("side", "?")
        icon = "\U0001f7e2" if side in ("BUY", "LONG") else "\U0001f534"
        d = "LONG" if side in ("BUY", "LONG") else "SHORT"
        lines.append(f"\n{icon} Dernier signal: {d}")
        lines.append(f"   Entry: {e:.6g}")
        lines.append(f"   SL:    {sl:.6g}")
        lines.append(f"   TP:    {tp:.6g}")
        r = last.get("r_multiple")
        if r:
            lines.append(f"   R:R    {r:.1f}")
    return "\n".join(lines)

def cmd_status(_args):
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    fp = DP_DIR / f"decision_packets_{today}.jsonl"
    n_today = 0
    last_ts = ""
    if fp.exists():
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n_today += 1
                try:
                    p = json.loads(line)
                    ts = p.get("created_at", "")
                    if ts:
                        last_ts = ts
                except Exception:
                    pass
    db_path = PROJECT / "databases" / "market_data.sqlite"
    db_size = db_path.stat().st_size if db_path.exists() else 0
    dp_files = sorted(DP_DIR.glob("decision_packets_*.jsonl"))
    n_files = len(dp_files)
    total_size = sum(f.stat().st_size for f in dp_files)
    lines = [f"STATUS — {now.strftime('%Y-%m-%d %H:%M UTC')}\n",
        f"Packets aujourd'hui: {n_today}",
        f"Dernier packet:      {last_ts[:19] if last_ts else '?'}",
        f"Fichiers DP:         {n_files} ({total_size / 1e9:.1f} GB)",
        f"market_data.sqlite:  {db_size / 1e6:.1f} MB"]
    return "\n".join(lines)

def cmd_lmi(args):
    """Live Market Interaction — observation microstructure (lecture seule)."""
    try:
        from trade_analysis.integrations.radar_adapter import (
            format_lmi_message, format_lmi_overview)
    except Exception:
        return "Module LMI indisponible."
    sym = args.strip().split()[0] if args.strip() else ""
    if sym:
        return format_lmi_message(sym)
    return format_lmi_overview()

def cmd_help(_args):
    return ("\U0001f916 CryptoRadar Bot\n\n"
        "/scan        Top 10 par confiance (24h)\n"
        "/scan 5      Top N symboles\n"
        "/signals     Signaux avec Entry/SL/TP (24h)\n"
        "/signals 4h  Signaux des N dernieres heures\n"
        "/top50       Top 50 compact\n"
        "/longs       Uniquement les LONG\n"
        "/shorts      Uniquement les SHORT\n"
        "/symbol BTC  Detail d'un symbole\n"
        "/lmi         Observatoire Live Market (tous)\n"
        "/lmi BTC     Microstructure live d'un symbole\n"
        "/status      Etat du systeme\n"
        "/help        Cette aide")

COMMANDS = {"scan": cmd_scan, "signals": cmd_signals, "top50": cmd_top50,
    "longs": cmd_longs, "shorts": cmd_shorts, "symbol": cmd_symbol,
    "lmi": cmd_lmi, "status": cmd_status, "help": cmd_help, "start": cmd_help}

def poll_loop():
    print(f"[RadarBot] Demarre — polling Telegram...")
    offset = 0
    while True:
        try:
            result = tg_request("getUpdates", {"timeout": 30, "offset": offset})
            updates = result.get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not text or not chat_id:
                    continue
                if ALLOWED_CHATS and chat_id not in ALLOWED_CHATS:
                    print(f"[RadarBot] Chat non autorise: {chat_id}")
                    continue
                if not text.startswith("/"):
                    continue
                parts = text[1:].split(maxsplit=1)
                cmd = parts[0].lower().split("@")[0]
                args = parts[1] if len(parts) > 1 else ""
                handler = COMMANDS.get(cmd)
                if handler:
                    print(f"[RadarBot] /{cmd} {args} (chat={chat_id})")
                    try:
                        reply = handler(args)
                        send_message(chat_id, reply)
                    except Exception as exc:
                        print(f"[RadarBot] Erreur: {exc}")
                        traceback.print_exc()
                        send_message(chat_id, f"Erreur: {exc}")
                else:
                    send_message(chat_id, f"Commande inconnue: /{cmd}\nTape /help")
        except urllib.error.URLError as e:
            print(f"[RadarBot] Erreur reseau: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[RadarBot] Erreur: {e}")
            traceback.print_exc()
            time.sleep(5)

def main():
    if not TOKEN:
        print("[ERREUR] TELEGRAM_BOT_TOKEN manquant")
        sys.exit(1)
    if "--once" in sys.argv:
        result = tg_request("getUpdates", {"timeout": 0})
        updates = result.get("result", [])
        print(f"[RadarBot] {len(updates)} messages en attente")
        for upd in updates:
            msg = upd.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if text.startswith("/"):
                parts = text[1:].split(maxsplit=1)
                cmd = parts[0].lower().split("@")[0]
                args = parts[1] if len(parts) > 1 else ""
                handler = COMMANDS.get(cmd)
                if handler:
                    send_message(chat_id, handler(args))
        return
    poll_loop()

if __name__ == "__main__":
    main()
